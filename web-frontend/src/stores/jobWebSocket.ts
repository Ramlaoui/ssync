import { writable, get } from 'svelte/store';
import type { JobInfo } from '../types/api';
import { apiConfig } from '../services/api';

interface JobWebSocketState {
  connected: boolean;
  job: JobInfo | null;
  updates: JobUpdate[];
  error: string | null;
}

interface JobUpdate {
  type: 'state_change' | 'output_update' | 'job_completed' | 'error';
  timestamp: string;
  data: any;
}

interface AllJobsWebSocketState {
  connected: boolean;
  jobs: { [hostname: string]: JobInfo[] };
  updates: JobUpdate[];
  error: string | null;
}

let jobWebSocket: WebSocket | null = null;
let allJobsWebSocket: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let pingInterval: ReturnType<typeof setInterval> | null = null;
// Track current connections to prevent duplicates
let currentJobConnection: string | null = null;

// Connection quality monitoring
interface ConnectionQuality {
  reconnectAttempts: number;
  lastSuccessfulConnect: number;
  lastPongReceived: number;
  averageLatency: number;
  consecutiveFailures: number;
}

let allJobsConnectionQuality: ConnectionQuality = {
  reconnectAttempts: 0,
  lastSuccessfulConnect: 0,
  lastPongReceived: 0,
  averageLatency: 0,
  consecutiveFailures: 0
};

let jobConnectionQuality: ConnectionQuality = {
  reconnectAttempts: 0,
  lastSuccessfulConnect: 0,
  lastPongReceived: 0,
  averageLatency: 0,
  consecutiveFailures: 0
};

// Store for single job monitoring
export const jobWebSocketStore = writable<JobWebSocketState>({
  connected: false,
  job: null,
  updates: [],
  error: null
});

// Store for all jobs monitoring
export const allJobsWebSocketStore = writable<AllJobsWebSocketState>({
  connected: false,
  jobs: {},
  updates: [],
  error: null
});

// Helper functions for connection quality
function getReconnectDelay(attempts: number): number {
  // Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
  const baseDelay = 1000;
  const maxDelay = 30000;
  const delay = Math.min(baseDelay * Math.pow(2, attempts), maxDelay);
  
  // Add jitter to prevent thundering herd
  const jitter = Math.random() * 1000;
  return delay + jitter;
}

function shouldReconnect(quality: ConnectionQuality): boolean {
  // Be more aggressive with reconnection attempts
  // Only stop after many more failures
  if (quality.consecutiveFailures > 20) {
    console.warn('WebSocket: Too many consecutive failures, will retry after cooldown');
    return false;
  }
  
  // Don't give up based on time - network issues can be temporary
  // Just warn if it's been a while
  const now = Date.now();
  const timeSinceLastSuccess = now - quality.lastSuccessfulConnect;
  if (timeSinceLastSuccess > 300000) { // 5 minutes
    console.warn(`WebSocket: No successful connection for ${Math.round(timeSinceLastSuccess/60000)} minutes, but will keep trying`);
    // Don't return false - keep trying
  }
  
  return true;
}

function updateConnectionSuccess(quality: ConnectionQuality): void {
  quality.lastSuccessfulConnect = Date.now();
  quality.consecutiveFailures = 0;
  quality.reconnectAttempts = 0;
}

function updateConnectionFailure(quality: ConnectionQuality): void {
  quality.consecutiveFailures++;
  quality.reconnectAttempts++;
}

export function connectJobWebSocket(jobId: string, hostname?: string) {
  const wsJobId = hostname ? `${hostname}:${jobId}` : jobId;
  
  // Prevent duplicate connections to the same job
  if (currentJobConnection === wsJobId && jobWebSocket?.readyState === WebSocket.OPEN) {
    console.log('[JobWebSocket] Already connected to this job:', wsJobId);
    return;
  }
  
  disconnectJobWebSocket();
  currentJobConnection = wsJobId;

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const encodedWsJobId = encodeURIComponent(wsJobId);

  // Add API key to WebSocket URL if configured
  const config = get(apiConfig);
  const apiKeyParam = config.apiKey ? `?api_key=${encodeURIComponent(config.apiKey)}` : '';
  const wsUrl = `${protocol}//${window.location.host}/ws/jobs/${encodedWsJobId}${apiKeyParam}`;

  console.log('[JobWebSocket] Connecting to:', wsUrl.replace(/api_key=[^&]+/, 'api_key=***'));
  jobWebSocket = new WebSocket(wsUrl);
  
  jobWebSocket.onopen = () => {
    console.log('[JobWebSocket] Connected successfully');
    updateConnectionSuccess(jobConnectionQuality);
    
    jobWebSocketStore.update(state => ({
      ...state,
      connected: true,
      error: null
    }));
    
    // Start ping interval - less aggressive than before
    pingInterval = setInterval(() => {
      if (jobWebSocket?.readyState === WebSocket.OPEN) {
        const pingTime = Date.now();
        jobWebSocket.send(JSON.stringify({ type: 'ping', timestamp: pingTime }));
      }
    }, 60000); // Increased from 30s to 60s
  };
  
  jobWebSocket.onmessage = (event) => {
    try {
      // Handle simple pong responses
      if (event.data === 'pong') {
        jobConnectionQuality.lastPongReceived = Date.now();
        return;
      }
      
      const data = JSON.parse(event.data);
      
      // Handle pong with timestamp for latency calculation
      if (data.type === 'pong') {
        const latency = Date.now() - data.timestamp;
        jobConnectionQuality.lastPongReceived = Date.now();
        jobConnectionQuality.averageLatency = 
          (jobConnectionQuality.averageLatency + latency) / 2;
        return;
      }
      
      if (data.type === 'initial') {
        jobWebSocketStore.update(state => ({
          ...state,
          job: data.job,
          updates: []
        }));
      } else if (data.type === 'state_change') {
        jobWebSocketStore.update(state => ({
          ...state,
          job: data.job,
          updates: [...state.updates, {
            type: 'state_change',
            timestamp: new Date().toISOString(),
            data
          }]
        }));
      } else if (data.type === 'output_update') {
        jobWebSocketStore.update(state => ({
          ...state,
          updates: [...state.updates, {
            type: 'output_update',
            timestamp: new Date().toISOString(),
            data
          }]
        }));
      } else if (data.type === 'job_completed') {
        jobWebSocketStore.update(state => ({
          ...state,
          updates: [...state.updates, {
            type: 'job_completed',
            timestamp: new Date().toISOString(),
            data
          }]
        }));
      } else if (data.type === 'error') {
        jobWebSocketStore.update(state => ({
          ...state,
          error: data.message
        }));
      }
    } catch (e) {
      console.error('Failed to parse WebSocket message:', e);
    }
  };
  
  jobWebSocket.onerror = (error) => {
    console.error('[JobWebSocket] Connection error:', error);
    jobWebSocketStore.update(state => ({
      ...state,
      error: 'WebSocket connection error'
    }));
  };
  
  jobWebSocket.onclose = () => {
    updateConnectionFailure(jobConnectionQuality);
    
    jobWebSocketStore.update(state => ({
      ...state,
      connected: false
    }));
    
    if (pingInterval) {
      clearInterval(pingInterval);
      pingInterval = null;
    }
    
    // Attempt to reconnect with exponential backoff
    if (shouldReconnect(jobConnectionQuality)) {
      const delay = getReconnectDelay(jobConnectionQuality.reconnectAttempts);
      console.log(`[JobWebSocket] Reconnecting in ${delay}ms (attempt ${jobConnectionQuality.reconnectAttempts})`);
      
      reconnectTimer = setTimeout(() => {
        // Only reconnect if we still have a tracked connection
        if (currentJobConnection) {
          const parts = currentJobConnection.split(':');
          if (parts.length === 2) {
            connectJobWebSocket(parts[1], parts[0]);
          } else {
            connectJobWebSocket(currentJobConnection);
          }
        }
      }, delay);
    }
  };
}

export function disconnectJobWebSocket() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  
  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }
  
  if (jobWebSocket) {
    console.log('[JobWebSocket] Disconnecting from:', currentJobConnection);
    jobWebSocket.close();
    jobWebSocket = null;
  }
  
  currentJobConnection = null;
  
  jobWebSocketStore.set({
    connected: false,
    job: null,
    updates: [],
    error: null
  });
}

export function requestJobOutput() {
  if (jobWebSocket?.readyState === WebSocket.OPEN) {
    jobWebSocket.send('get_output');
  }
}

export function connectAllJobsWebSocket() {
  disconnectAllJobsWebSocket();

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

  // Add API key to WebSocket URL if configured
  const config = get(apiConfig);
  const apiKeyParam = config.apiKey ? `?api_key=${encodeURIComponent(config.apiKey)}` : '';
  const wsUrl = `${protocol}//${window.location.host}/ws/jobs${apiKeyParam}`;

  console.log('[AllJobsWebSocket] Connecting to:', wsUrl.replace(/api_key=[^&]+/, 'api_key=***'));
  allJobsWebSocket = new WebSocket(wsUrl);
  
  allJobsWebSocket.onopen = () => {
    console.log('[AllJobsWebSocket] Connected successfully');
    updateConnectionSuccess(allJobsConnectionQuality);
    
    allJobsWebSocketStore.update(state => ({
      ...state,
      connected: true,
      error: null
    }));
    
    // Start ping interval - less aggressive than before
    if (!pingInterval) {
      pingInterval = setInterval(() => {
        if (allJobsWebSocket?.readyState === WebSocket.OPEN) {
          const pingTime = Date.now();
          allJobsWebSocket.send(JSON.stringify({ type: 'ping', timestamp: pingTime }));
        }
      }, 60000); // Increased from 30s to 60s
    }
  };
  
  allJobsWebSocket.onmessage = (event) => {
    try {
      // Handle simple pong responses
      if (event.data === 'pong') {
        allJobsConnectionQuality.lastPongReceived = Date.now();
        return;
      }
      
      const data = JSON.parse(event.data);
      
      // Handle pong with timestamp for latency calculation
      if (data.type === 'pong') {
        const latency = Date.now() - data.timestamp;
        allJobsConnectionQuality.lastPongReceived = Date.now();
        allJobsConnectionQuality.averageLatency = 
          (allJobsConnectionQuality.averageLatency + latency) / 2;
        return;
      }
      
      if (data.type === 'initial') {
        allJobsWebSocketStore.update(state => {
          // Merge initial data with existing data to prevent data loss
          // This handles cases where we had data before reconnection
          const mergedJobs = { ...state.jobs };
          
          // Update with new data from WebSocket
          for (const [hostname, jobs] of Object.entries(
            data.jobs as Record<string, JobInfo[]>
          )) {
            mergedJobs[hostname] = jobs;
          }
          
          return {
            ...state,
            jobs: mergedJobs,
            updates: []
          };
        });
      } else if (data.type === 'batch_update') {
        allJobsWebSocketStore.update(state => {
          const newJobs = { ...state.jobs };
          
          for (const update of data.updates) {
            if (update.type === 'job_update') {
              if (!newJobs[update.hostname]) {
                newJobs[update.hostname] = [];
              }
              
              const jobIndex = newJobs[update.hostname].findIndex(
                j => j.job_id === update.job_id
              );
              
              if (jobIndex >= 0) {
                newJobs[update.hostname][jobIndex] = update.job;
              } else {
                newJobs[update.hostname].push(update.job);
              }
            } else if (update.type === 'job_completed') {
              // Update the job state instead of removing it
              if (newJobs[update.hostname]) {
                const jobIndex = newJobs[update.hostname].findIndex(
                  j => j.job_id === update.job_id
                );
                if (jobIndex >= 0 && update.job) {
                  newJobs[update.hostname][jobIndex] = update.job;
                }
              }
            }
          }
          
          return {
            ...state,
            jobs: newJobs,
            updates: [...state.updates, {
              type: 'state_change',
              timestamp: data.timestamp,
              data: data.updates
            }]
          };
        });
      } else if (data.type === 'error') {
        allJobsWebSocketStore.update(state => ({
          ...state,
          error: data.message
        }));
      }
    } catch (e) {
      console.error('Failed to parse WebSocket message:', e);
    }
  };
  
  allJobsWebSocket.onerror = (error) => {
    console.error('WebSocket error:', error);
    allJobsWebSocketStore.update(state => ({
      ...state,
      error: 'WebSocket connection error'
    }));
  };
  
  allJobsWebSocket.onclose = () => {
    updateConnectionFailure(allJobsConnectionQuality);
    
    // Keep existing job data when disconnected - don't wipe it
    allJobsWebSocketStore.update(state => ({
      ...state,
      connected: false
      // NOTE: Keeping jobs data intact, not resetting to {}
    }));
    
    if (pingInterval) {
      clearInterval(pingInterval);
      pingInterval = null;
    }
    
    // Always attempt to reconnect unless explicitly disconnected
    // Reset failure count after longer period to allow retries
    const timeSinceLastSuccess = Date.now() - allJobsConnectionQuality.lastSuccessfulConnect;
    if (timeSinceLastSuccess > 600000) { // 10 minutes
      // Reset failures to allow new connection attempts
      allJobsConnectionQuality.consecutiveFailures = 0;
      allJobsConnectionQuality.reconnectAttempts = 0;
    }
    
    // Attempt to reconnect with exponential backoff
    if (shouldReconnect(allJobsConnectionQuality) || allJobsConnectionQuality.reconnectAttempts === 0) {
      const delay = getReconnectDelay(allJobsConnectionQuality.reconnectAttempts);
      console.log(`[AllJobsWebSocket] Reconnecting in ${delay}ms (attempt ${allJobsConnectionQuality.reconnectAttempts})`);
      
      reconnectTimer = setTimeout(() => {
        connectAllJobsWebSocket();
      }, delay);
    } else {
      console.log('[AllJobsWebSocket] Temporarily pausing reconnection - will retry after cooldown');
      // Set a longer timer to retry after cooldown period
      reconnectTimer = setTimeout(() => {
        allJobsConnectionQuality.consecutiveFailures = 0;
        allJobsConnectionQuality.reconnectAttempts = 0;
        connectAllJobsWebSocket();
      }, 300000); // Retry after 5 minutes
    }
  };
}

export function disconnectAllJobsWebSocket() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  
  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }
  
  if (allJobsWebSocket) {
    allJobsWebSocket.close();
    allJobsWebSocket = null;
  }
  
  // Reset connection quality when explicitly disconnecting
  allJobsConnectionQuality = {
    reconnectAttempts: 0,
    lastSuccessfulConnect: 0,
    lastPongReceived: 0,
    averageLatency: 0,
    consecutiveFailures: 0
  };
  
  allJobsWebSocketStore.set({
    connected: false,
    jobs: {},
    updates: [],
    error: null
  });
}

// Export connection quality for monitoring
export function getConnectionQuality() {
  return {
    allJobs: { ...allJobsConnectionQuality },
    singleJob: { ...jobConnectionQuality }
  };
}

// Check if WebSocket is healthy (receiving pongs)
export function isWebSocketHealthy(): boolean {
  const now = Date.now();
  const allJobsHealthy = now - allJobsConnectionQuality.lastPongReceived < 90000; // 90 seconds
  const singleJobHealthy = jobConnectionQuality.lastSuccessfulConnect === 0 || 
                          now - jobConnectionQuality.lastPongReceived < 90000;
  
  return allJobsHealthy && singleJobHealthy;
}
