/**
 * Centralized Job State Manager
 * 
 * Single source of truth for all job data and updates.
 * Manages WebSocket, polling, caching, and state synchronization.
 */

import { writable, derived, get, type Readable } from 'svelte/store';
import type { JobInfo, HostInfo, JobStatusResponse } from '../types/api';
import { api } from '../services/api';

// ============================================================================
// Types
// ============================================================================

type DataSource = 'websocket' | 'api' | 'cache' | 'manual';
type JobState = 'PD' | 'R' | 'CD' | 'F' | 'CA' | 'TO' | 'UNKNOWN';
type UpdatePriority = 'realtime' | 'high' | 'normal' | 'low';

interface JobUpdate {
  jobId: string;
  hostname: string;
  job: JobInfo;
  source: DataSource;
  timestamp: number;
  priority: UpdatePriority;
  messageType?: string; // Track message type for better deduplication
}

interface JobCacheEntry {
  job: JobInfo;
  lastUpdated: number;
  lastSource: DataSource;
  output?: any;
  outputTimestamp?: number;
}

interface HostState {
  hostname: string;
  status: 'connected' | 'loading' | 'error' | 'idle';
  lastSync: number;
  errorCount: number;
  jobs: Map<string, string>; // jobId -> cacheKey mapping
}

interface ManagerState {
  // Core data
  jobCache: Map<string, JobCacheEntry>;      // cacheKey -> job data
  hostStates: Map<string, HostState>;        // hostname -> host state

  // Connection state
  dataSource: DataSource;
  wsConnected: boolean;
  wsHealthy: boolean;
  pollingActive: boolean;
  wsInitialDataReceived: boolean;  // Track if we've received initial WS data
  wsInitialDataTimestamp: number;   // When we received initial WS data

  // Activity tracking
  lastActivity: number;
  isTabActive: boolean;
  isPaused: boolean;

  // Update queue
  pendingUpdates: JobUpdate[];
  processingUpdates: boolean;

  // Performance metrics
  metrics: PerformanceMetrics;
}

interface PerformanceMetrics {
  totalUpdates: number;
  cacheHits: number;
  cacheMisses: number;
  apiCalls: number;
  wsMessages: number;
  averageUpdateTime: number;
  lastUpdateTime: number;
  updateHistory: number[];
}

// ============================================================================
// Configuration
// ============================================================================

const CONFIG = {
  // Update strategies
  updateStrategy: {
    batchSize: 50,
    batchDelay: 100,
    batchDelayImmediate: 0, // For forced refreshes
    deduplicateWindow: 500, // Increased from 50ms to catch updates from different sources
  },
  
  // Cache lifetimes based on job state
  cacheLifetime: {
    completed: 300000,  // 5 min
    running: 60000,     // 1 min  
    pending: 30000,     // 30 sec
    error: 120000,      // 2 min
  },
  
  // Sync intervals
  syncIntervals: {
    websocket: 0,       // Realtime
    active: 60000,      // 1 min when active
    background: 300000, // 5 min in background
    paused: 0,          // No sync when paused
  },
  
  // Connection health
  health: {
    wsTimeout: 45000,   // 45 sec without activity = unhealthy
    maxRetries: 3,
    retryDelay: 5000,
  },
};

// ============================================================================
// Job State Manager Class
// ============================================================================

class JobStateManager {
  private state = writable<ManagerState>({
    jobCache: new Map(),
    hostStates: new Map(),
    dataSource: 'cache',
    wsConnected: false,
    wsHealthy: false,
    pollingActive: false,
    wsInitialDataReceived: false,
    wsInitialDataTimestamp: 0,
    lastActivity: Date.now(),
    isTabActive: true,
    isPaused: false,
    pendingUpdates: [],
    processingUpdates: false,
    metrics: {
      totalUpdates: 0,
      cacheHits: 0,
      cacheMisses: 0,
      apiCalls: 0,
      wsMessages: 0,
      averageUpdateTime: 0,
      lastUpdateTime: 0,
      updateHistory: [],
    },
  });
  
  private ws: WebSocket | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private updateTimer: ReturnType<typeof setTimeout> | null = null;
  private healthCheckTimer: ReturnType<typeof setInterval> | null = null;
  
  // ========================================================================
  // Initialization
  // ========================================================================
  
  constructor() {
    // Bind methods to ensure proper context
    this.processUpdateQueue = this.processUpdateQueue.bind(this);
    this.queueUpdate = this.queueUpdate.bind(this);
    this.handleWebSocketMessage = this.handleWebSocketMessage.bind(this);

    this.setupEventListeners();
    this.startHealthMonitoring();
  }
  
  private setupEventListeners(): void {
    // Tab visibility
    document.addEventListener('visibilitychange', () => {
      this.updateState({ isTabActive: !document.hidden });
      this.adjustSyncStrategy();
    });
    
    // User activity
    ['mousedown', 'keypress', 'scroll', 'touchstart'].forEach(event => {
      document.addEventListener(event, () => {
        this.updateState({ lastActivity: Date.now() });
      }, { passive: true });
    });
  }
  
  private startHealthMonitoring(): void {
    this.healthCheckTimer = setInterval(() => {
      const state = get(this.state);
      const now = Date.now();
      
      // Check WebSocket health
      if (state.wsConnected) {
        const wsHealthy = now - state.lastActivity < CONFIG.health.wsTimeout;
        if (wsHealthy !== state.wsHealthy) {
          this.updateState({ wsHealthy });
          if (!wsHealthy) this.startPolling();
        }
      }
      
      // Check if should pause (5 min inactive + background)
      const shouldPause = !state.isTabActive && 
                         now - state.lastActivity > 300000;
      
      if (shouldPause !== state.isPaused) {
        this.updateState({ isPaused: shouldPause });
        this.adjustSyncStrategy();
      }
    }, 10000); // Check every 10 seconds
  }
  
  // ========================================================================
  // WebSocket Management
  // ========================================================================
  
  public connectWebSocket(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/jobs`;
    
    this.ws = new WebSocket(wsUrl);
    
    this.ws.onopen = () => {
      this.updateState({ 
        wsConnected: true, 
        wsHealthy: true,
        dataSource: 'websocket',
        lastActivity: Date.now(),
      });
      this.stopPolling();
      console.log('[JobStateManager] WebSocket connected');
    };
    
    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleWebSocketMessage(data);
        this.updateState({ lastActivity: Date.now() });
      } catch (e) {
        console.error('[JobStateManager] Failed to parse WebSocket message:', e);
      }
    };
    
    this.ws.onclose = () => {
      this.updateState({
        wsConnected: false,
        wsHealthy: false,
        dataSource: 'api',
        wsInitialDataReceived: false,  // Reset initial data flag
        wsInitialDataTimestamp: 0,
      });
      this.startPolling();

      // Reconnect after delay
      setTimeout(() => this.connectWebSocket(), CONFIG.health.retryDelay);
    };
    
    this.ws.onerror = (error) => {
      console.error('[JobStateManager] WebSocket error:', error);
    };
  }
  
  private currentViewJobId: string | null = null;
  private currentViewHostname: string | null = null;

  /**
   * Set the currently viewed job for priority updates
   */
  public setCurrentViewJob(jobId: string | null, hostname: string | null): void {
    this.currentViewJobId = jobId;
    this.currentViewHostname = hostname;
    console.log(`[JobStateManager] Current view job set to ${jobId} on ${hostname}`);
  }

  private handleWebSocketMessage(data: any): void {
    if (data.type === 'pong') return;

    console.log('[JobStateManager] WebSocket message received:', data.type, data);

    // Track WebSocket messages
    this.updateMetric('wsMessages', 1);

    // Handle different message formats
    if (data.type === 'initial' && data.jobs) {
      // Handle initial data load with jobs grouped by hostname
      console.log(`[JobStateManager] Processing initial data with ${data.total || 0} total jobs`);

      // Mark that we've received initial WebSocket data
      this.updateState({
        wsInitialDataReceived: true,
        wsInitialDataTimestamp: Date.now()
      });

      // Clear existing cache to prevent duplicates from stale data
      this.state.update(s => {
        s.jobCache.clear();
        return s;
      });

      for (const [hostname, jobs] of Object.entries(data.jobs)) {
        if (Array.isArray(jobs)) {
          console.log(`[JobStateManager] Processing ${jobs.length} jobs for ${hostname}`);
          jobs.forEach((job: any) => {
            if (job.job_id) {
              // Ensure hostname is set on the job
              if (!job.hostname) {
                job.hostname = hostname;
              }
              this.queueUpdate({
                jobId: job.job_id,
                hostname: hostname,
                job: job,
                source: 'websocket',
                timestamp: Date.now(),
                priority: 'high',
                messageType: 'initial',
              }, true); // Immediate for initial data
            }
          });
        }
      }
    } else if (data.type === 'job_update' || data.type === 'state_change') {
      // Check if this is the currently viewed job
      const isCurrentJob = this.currentViewJobId === data.job_id &&
                          this.currentViewHostname === data.hostname;

      this.queueUpdate({
        jobId: data.job_id,
        hostname: data.hostname,
        job: data.job,
        source: 'websocket',
        timestamp: Date.now(),
        priority: 'realtime',
        messageType: data.type,
      }, isCurrentJob); // Immediate for current job, normal delay for others
    } else if (data.type === 'batch_update') {
      data.updates.forEach((update: any) => {
        this.queueUpdate({
          jobId: update.job_id,
          hostname: update.hostname,
          job: update.job,
          source: 'websocket',
          timestamp: Date.now(),
          priority: 'high',
          messageType: 'batch_update',
        }, false); // Normal delay for batch updates
      });
    } else if (Array.isArray(data)) {
      // Handle array of jobs directly
      console.log(`[JobStateManager] WebSocket sent array of ${data.length} jobs`);
      data.forEach((job: any) => {
        if (job.job_id && job.hostname) {
          this.queueUpdate({
            jobId: job.job_id,
            hostname: job.hostname,
            job: job,
            source: 'websocket',
            timestamp: Date.now(),
            priority: 'high',
            messageType: 'array',
          }, true); // Immediate for direct array
        }
      });
    } else if (data.jobs && Array.isArray(data.jobs)) {
      // Handle object with jobs array
      console.log(`[JobStateManager] WebSocket sent object with ${data.jobs.length} jobs`);
      data.jobs.forEach((job: any) => {
        if (job.job_id) {
          this.queueUpdate({
            jobId: job.job_id,
            hostname: data.hostname || job.hostname,
            job: job,
            source: 'websocket',
            timestamp: Date.now(),
            priority: 'high',
            messageType: 'jobs_array',
          }, true); // Immediate for jobs array
        }
      });
    }
  }
  
  // ========================================================================
  // Polling Management
  // ========================================================================
  
  private startPolling(): void {
    if (this.pollTimer) return;
    
    const state = get(this.state);
    if (state.isPaused || state.wsHealthy) return;
    
    const interval = state.isTabActive 
      ? CONFIG.syncIntervals.active 
      : CONFIG.syncIntervals.background;
    
    this.pollTimer = setInterval(() => {
      this.syncAllHosts();
    }, interval);
    
    this.updateState({ pollingActive: true });
    console.log(`[JobStateManager] Polling started (${interval/1000}s interval)`);
  }
  
  private stopPolling(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
      this.updateState({ pollingActive: false });
      console.log('[JobStateManager] Polling stopped');
    }
  }
  
  // ========================================================================
  // Data Synchronization
  // ========================================================================
  
  public async syncAllHosts(forceSync = false): Promise<void> {
    const state = get(this.state);
    if (!forceSync && state.isPaused) return;

    // Skip API sync if we just received WebSocket initial data
    if (!forceSync && state.wsInitialDataReceived &&
        (Date.now() - state.wsInitialDataTimestamp < 5000)) {
      console.log('[JobStateManager] Skipping API sync - WebSocket initial data is fresh');
      return;
    }

    try {
      console.log('[JobStateManager] Starting sync for all hosts' + (forceSync ? ' (forced)' : ''));
      // Get list of hosts
      const hostsResponse = await api.get<HostInfo[]>('/api/hosts');
      const hosts = hostsResponse.data || [];
      console.log(`[JobStateManager] Found ${hosts.length} hosts:`, hosts.map(h => h.hostname));

      if (hosts.length === 0) {
        console.warn('[JobStateManager] No hosts returned from API');
        // Try fetching from /api/status directly if no hosts
        if (forceSync) {
          await this.fetchDirectStatus();
        }
        return;
      }
      
      // Update host states in store
      this.state.update(s => {
        // Create new Map to trigger reactivity
        const newHostStates = new Map(s.hostStates);
        hosts.forEach(host => {
          if (!newHostStates.has(host.hostname)) {
            newHostStates.set(host.hostname, {
              hostname: host.hostname,
              status: 'idle',
              lastSync: 0,
              errorCount: 0,
              jobs: new Map(),
            });
          }
        });
        s.hostStates = newHostStates;
        return s;
      });
      
      // Sync each host in parallel
      await Promise.allSettled(
        hosts.map(host => this.syncHost(host.hostname, forceSync))
      );
    } catch (error) {
      console.error('[JobStateManager] Failed to sync hosts:', error);
    }
  }
  
  public async syncHost(hostname: string, forceSync = false): Promise<void> {
    const state = get(this.state);
    const hostState = state.hostStates.get(hostname);
    
    if (!hostState) {
      console.warn(`[JobStateManager] Host state not found for ${hostname}`);
      return;
    }
    
    // Check if sync needed based on cache (skip check if forceSync)
    if (!forceSync) {
      const now = Date.now();
      const cacheExpired = now - hostState.lastSync > CONFIG.syncIntervals.active;
      if (!cacheExpired && hostState.status === 'connected') {
        console.log(`[JobStateManager] Cache still valid for ${hostname}, skipping sync`);
        return;
      }
    }
    
    console.log(`[JobStateManager] Syncing host ${hostname}`);
    
    const now = Date.now();
    
    // Update host status
    this.state.update(s => {
      const newHostStates = new Map(s.hostStates);
      const hs = newHostStates.get(hostname);
      if (hs) {
        newHostStates.set(hostname, { ...hs, status: 'loading' });
      }
      s.hostStates = newHostStates;
      return s;
    });
    
    try {
      this.updateMetric('apiCalls', 1);
      
      // The API might return either an array or a single object depending on the endpoint
      const response = await api.get<JobStatusResponse | JobStatusResponse[]>(
        `/api/status?host=${hostname}`
      );
      
      // Log raw response
      console.log(`[JobStateManager] Raw API response for ${hostname}:`, response.data);
      
      // Handle both array and single object responses
      let hostData: JobStatusResponse;
      if (Array.isArray(response.data)) {
        hostData = response.data[0];
        console.log(`[JobStateManager] Got array response for ${hostname}, array length: ${response.data.length}`);
      } else {
        hostData = response.data;
        console.log(`[JobStateManager] Got single object response for ${hostname}`);
      }
      
      if (!hostData) {
        console.warn(`[JobStateManager] No data in response for ${hostname}`);
        return;
      }
      
      // Log the actual response structure to debug
      console.log(`[JobStateManager] Full response data for ${hostname}:`, JSON.stringify(hostData, null, 2));
      
      // Check if jobs field exists and is an array
      if (hostData && Array.isArray(hostData.jobs)) {
        console.log(`[JobStateManager] Processing ${hostData.jobs.length} jobs for ${hostname}`);
        
        // Prepare jobs for queueing
        const jobsToQueue: JobUpdate[] = [];
        
        // Update host state with job mappings
        this.state.update(s => {
          const newHostStates = new Map(s.hostStates);
          const hs = newHostStates.get(hostname);
          if (hs) {
            const newJobs = new Map<string, string>();
            hostData.jobs.forEach(job => {
              // Ensure hostname is set on job
              if (!job.hostname) {
                job.hostname = hostname;
              }
              
              const cacheKey = `${hostname}:${job.job_id}`;
              newJobs.set(job.job_id, cacheKey);
              
              // Prepare update for this job
              jobsToQueue.push({
                jobId: job.job_id,
                hostname: hostname,
                job: job,
                source: 'api',
                timestamp: now,
                priority: 'normal',
                messageType: 'api_sync',
              });
            });
            
            // Create new host state object
            newHostStates.set(hostname, {
              ...hs,
              jobs: newJobs,
              status: 'connected',
              lastSync: now,
              errorCount: 0,
            });
          }
          s.hostStates = newHostStates;
          return s;
        });
        
        // Queue all job updates after state update
        console.log(`[JobStateManager] Queueing ${jobsToQueue.length} job updates for ${hostname}`);
        jobsToQueue.forEach(update => this.queueUpdate(update, forceSync));
      } else {
        console.log(`[JobStateManager] No jobs returned for ${hostname}`);
        // Still mark as connected even if no jobs
        this.state.update(s => {
          const newHostStates = new Map(s.hostStates);
          const hs = newHostStates.get(hostname);
          if (hs) {
            newHostStates.set(hostname, {
              ...hs,
              status: 'connected',
              lastSync: now,
              errorCount: 0,
            });
          }
          s.hostStates = newHostStates;
          return s;
        });
      }
    } catch (error) {
      console.error(`[JobStateManager] Failed to sync host ${hostname}:`, error);
      this.state.update(s => {
        const newHostStates = new Map(s.hostStates);
        const hs = newHostStates.get(hostname);
        if (hs) {
          newHostStates.set(hostname, {
            ...hs,
            status: 'error',
            errorCount: hs.errorCount + 1,
          });
        }
        s.hostStates = newHostStates;
        return s;
      });
    }
  }
  
  // ========================================================================
  // Update Queue Management
  // ========================================================================
  
  private queueUpdate(update: JobUpdate, immediate = false): void {
    // Update state with new pending update
    this.state.update(s => {
      // Add to queue
      s.pendingUpdates.push(update);

      // Enhanced deduplication within window
      if (s.pendingUpdates.length > 1) {
        const cutoff = Date.now() - CONFIG.updateStrategy.deduplicateWindow;
        const recent = s.pendingUpdates.filter(u => u.timestamp > cutoff);

        // Keep only latest update per job, with source priority
        const latestByJob = new Map<string, JobUpdate>();
        recent.forEach(u => {
          const key = `${u.hostname}:${u.jobId}`;
          const existing = latestByJob.get(key);

          // WebSocket updates take priority over API updates
          const shouldReplace = !existing ||
            (u.source === 'websocket' && existing.source === 'api') ||
            (u.source === existing.source && u.timestamp > existing.timestamp);

          if (shouldReplace) {
            latestByJob.set(key, u);
          }
        });

        s.pendingUpdates = Array.from(latestByJob.values());
      }

      return s;
    });
    
    // Process immediately or schedule
    if (immediate) {
      // Process synchronously for immediate updates
      if (this.updateTimer) {
        clearTimeout(this.updateTimer);
        this.updateTimer = null;
      }
      this.processUpdateQueue();
    } else if (!this.updateTimer) {
      // Use a very short delay to allow batching but process quickly
      // For initial load (empty cache), use minimal delay
      const delay = get(this.state).jobCache.size === 0 ? 0 : CONFIG.updateStrategy.batchDelay;
      this.updateTimer = setTimeout(() => {
        this.processUpdateQueue();
      }, delay);
    }
  }
  
  private processUpdateQueue(): void {
    // Safety check for undefined state
    if (!this.state) {
      console.error('[JobStateManager] State is undefined in processUpdateQueue');
      return;
    }

    const state = get(this.state);
    if (!state || state.processingUpdates || state.pendingUpdates.length === 0) return;

    const startTime = performance.now();

    // Get batch to process
    const batch = state.pendingUpdates.slice(0, CONFIG.updateStrategy.batchSize);
    const remaining = state.pendingUpdates.slice(CONFIG.updateStrategy.batchSize);

    console.log(`[JobStateManager] Processing ${batch.length} updates, ${remaining.length} remaining`);

    // Update state with processed jobs
    this.state.update(s => {
      s.processingUpdates = true;
      s.pendingUpdates = remaining;

      // Create a new Map to trigger Svelte reactivity
      const newCache = new Map(s.jobCache);

      batch.forEach((update) => {
        const cacheKey = `${update.hostname}:${update.jobId}`;
        const existing = newCache.get(cacheKey);

        // Enhanced update logic with source priority
        const shouldUpdate = !existing ||
                            (update.source === 'websocket' && existing.lastSource !== 'websocket') ||
                            (update.source === existing.lastSource && update.timestamp > existing.lastUpdated) ||
                            (existing.job.state !== update.job.state); // Always update on state change

        if (shouldUpdate) {
          // Check for state transitions - log for debugging
          if (existing && existing.job.state !== update.job.state) {
            console.log(`[JobStateManager] Job ${cacheKey} state change: ${existing.job.state} -> ${update.job.state}`);
          }

          newCache.set(cacheKey, {
            job: update.job,
            lastUpdated: update.timestamp,
            lastSource: update.source,
            output: existing?.output,
            outputTimestamp: existing?.outputTimestamp,
          });

          // Track metrics
          s.metrics.totalUpdates++;
        } else {
          console.log(`[JobStateManager] Skipping duplicate update for ${cacheKey} from ${update.source}`);
        }
      });

      // Replace the entire Map to trigger reactivity
      s.jobCache = newCache;
      s.processingUpdates = false;
      return s;
    });
    
    // Track processing time
    const processingTime = performance.now() - startTime;
    this.updateProcessingTime(processingTime);
    
    // Debug final cache state
    const finalState = get(this.state);
    console.log(`[JobStateManager] After processing ${batch.length} updates, cache now has ${finalState.jobCache.size} jobs`);
    console.log(`[JobStateManager] Cache keys:`, Array.from(finalState.jobCache.keys()));
    
    // Clear timer
    this.updateTimer = null;
    
    // Process remaining if any
    const newState = get(this.state);
    if (newState.pendingUpdates.length > 0) {
      this.updateTimer = setTimeout(() => {
        this.processUpdateQueue();
      }, CONFIG.updateStrategy.batchDelay);
    }
  }
  
  // ========================================================================
  // Cache Management
  // ========================================================================
  
  private getCacheLifetime(job: JobInfo): number {
    switch (job.state) {
      case 'CD':
      case 'F':
      case 'CA':
      case 'TO':
        return CONFIG.cacheLifetime.completed;
      case 'R':
        return CONFIG.cacheLifetime.running;
      case 'PD':
        return CONFIG.cacheLifetime.pending;
      default:
        return CONFIG.cacheLifetime.error;
    }
  }
  
  public isJobCacheValid(cacheKey: string): boolean {
    const state = get(this.state);
    const entry = state.jobCache.get(cacheKey);
    
    if (!entry) {
      this.updateMetric('cacheMisses', 1);
      return false;
    }
    
    const lifetime = this.getCacheLifetime(entry.job);
    const isValid = Date.now() - entry.lastUpdated < lifetime;
    
    if (isValid) {
      this.updateMetric('cacheHits', 1);
    } else {
      this.updateMetric('cacheMisses', 1);
    }
    
    return isValid;
  }
  
  public async fetchJob(jobId: string, hostname: string): Promise<JobInfo | null> {
    const cacheKey = `${hostname}:${jobId}`;
    const state = get(this.state);
    const cached = state.jobCache.get(cacheKey);
    
    // Return from cache if valid
    if (cached && this.isJobCacheValid(cacheKey)) {
      return cached.job;
    }
    
    // Fetch from API
    try {
      this.updateMetric('apiCalls', 1);
      const response = await api.get<JobInfo>(`/api/jobs/${jobId}?host=${hostname}`);
      const job = response.data;
      
      // Update cache
      this.queueUpdate({
        jobId,
        hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'high',
      });
      
      return job;
    } catch (error) {
      console.error(`[JobStateManager] Failed to fetch job ${jobId}:`, error);
      return cached?.job || null;
    }
  }
  
  // ========================================================================
  // Strategy Adjustment
  // ========================================================================
  
  private adjustSyncStrategy(): void {
    const state = get(this.state);
    
    // Determine optimal strategy
    if (state.isPaused) {
      this.stopPolling();
      return;
    }
    
    if (state.wsHealthy) {
      this.stopPolling();
      this.updateState({ dataSource: 'websocket' });
    } else if (state.isTabActive) {
      this.startPolling();
      this.updateState({ dataSource: 'api' });
    } else {
      // Background - reduce polling frequency
      this.stopPolling();
      this.startPolling(); // Will use background interval
    }
  }
  
  // ========================================================================
  // State Management
  // ========================================================================
  
  private updateState(partial: Partial<ManagerState>): void {
    this.state.update(s => ({ ...s, ...partial }));
  }
  
  // ========================================================================
  // Public API
  // ========================================================================
  
  public async initialize(): Promise<void> {
    console.log('[JobStateManager] Initializing...');
    // Clear any existing state first
    this.state.update(s => ({
      ...s,
      jobCache: new Map(),
      pendingUpdates: [],
      processingUpdates: false,
      wsInitialDataReceived: false,
      wsInitialDataTimestamp: 0,
    }));
    // Connect WebSocket first for real-time updates
    this.connectWebSocket();
    // Wait a bit for WebSocket to connect and send initial data
    await new Promise(resolve => setTimeout(resolve, 500));
    // Only sync if WebSocket hasn't provided data
    const state = get(this.state);
    if (!state.wsInitialDataReceived) {
      await this.forceInitialSync();
    }
  }
  
  public destroy(): void {
    this.ws?.close();
    this.stopPolling();
    if (this.healthCheckTimer) clearInterval(this.healthCheckTimer);
    if (this.updateTimer) clearTimeout(this.updateTimer);
  }
  
  public forceRefresh(): Promise<void> {
    return this.syncAllHosts(true);
  }

  public hasRecentData(maxAge: number = 30000): boolean {
    // Check if we have recent data from any host (within maxAge milliseconds)
    const now = Date.now();
    const hosts = get(this.hostConfigs);

    for (const host of hosts) {
      const hostState = this.hostStates.get(host.host);
      if (hostState && (now - hostState.lastSync) < maxAge) {
        console.log(`[JobStateManager] Host ${host.host} has recent data (${Math.round((now - hostState.lastSync) / 1000)}s old)`);
        return true;
      }
    }

    console.log('[JobStateManager] No recent data found, refresh needed');
    return false;
  }

  private async forceInitialSync(): Promise<void> {
    console.log('[JobStateManager] Forcing initial sync...');
    // Force sync all hosts immediately
    await this.syncAllHosts(true);
  }
  
  private async fetchDirectStatus(): Promise<void> {
    try {
      console.log('[JobStateManager] Fetching jobs directly from /api/status');
      const response = await api.get<JobStatusResponse>('/api/status');
      if (response.data && response.data.jobs) {
        const jobs = response.data.jobs;
        console.log(`[JobStateManager] Got ${Object.keys(jobs).length} hosts from direct status`);
        
        // Process jobs by hostname
        for (const [hostname, hostJobs] of Object.entries(jobs)) {
          if (Array.isArray(hostJobs)) {
            hostJobs.forEach((job: any) => {
              if (!job.hostname) {
                job.hostname = hostname;
              }
              this.queueUpdate({
                jobId: job.job_id,
                hostname: hostname,
                job: job,
                source: 'api',
                timestamp: Date.now(),
                priority: 'high',
              }, true); // Immediate processing for direct status
            });
          }
        }
      }
    } catch (error) {
      console.error('[JobStateManager] Failed to fetch direct status:', error);
    }
  }
  
  public getState(): Readable<ManagerState> {
    return { subscribe: this.state.subscribe };
  }
  
  // ========================================================================
  // Performance Monitoring
  // ========================================================================
  
  private updateMetric(metric: keyof PerformanceMetrics, value: number): void {
    this.state.update(s => {
      if (typeof s.metrics[metric] === 'number') {
        (s.metrics[metric] as number) += value;
      }
      return s;
    });
  }
  
  private updateProcessingTime(time: number): void {
    this.state.update(s => {
      s.metrics.lastUpdateTime = time;
      s.metrics.updateHistory.push(time);
      
      // Keep only last 100 measurements
      if (s.metrics.updateHistory.length > 100) {
        s.metrics.updateHistory.shift();
      }
      
      // Calculate average
      s.metrics.averageUpdateTime = s.metrics.updateHistory.reduce((a, b) => a + b, 0) / s.metrics.updateHistory.length;
      
      return s;
    });
  }
  
  public getMetrics(): Readable<PerformanceMetrics> {
    return derived(this.state, $state => $state.metrics);
  }
  
  public resetMetrics(): void {
    this.state.update(s => {
      s.metrics = {
        totalUpdates: 0,
        cacheHits: 0,
        cacheMisses: 0,
        apiCalls: 0,
        wsMessages: 0,
        averageUpdateTime: 0,
        lastUpdateTime: 0,
        updateHistory: [],
      };
      return s;
    });
  }
  
  // ========================================================================
  // Derived Stores
  // ========================================================================
  
  public getAllJobs(): Readable<JobInfo[]> {
    return derived(this.state, $state => {
      // Create a Map to ensure unique jobs by hostname:job_id
      const uniqueJobs = new Map<string, JobInfo>();

      // Process all cached jobs
      $state.jobCache.forEach((entry, cacheKey) => {
        // Only include jobs with valid data
        if (entry.job && entry.job.job_id && entry.job.hostname) {
          uniqueJobs.set(cacheKey, entry.job);
        }
      });

      const jobs = Array.from(uniqueJobs.values())
        .sort((a, b) => {
          const timeA = new Date(a.submit_time || 0).getTime();
          const timeB = new Date(b.submit_time || 0).getTime();
          return timeB - timeA;
        });

      console.log(`[JobStateManager] getAllJobs returning ${jobs.length} unique jobs from cache of ${$state.jobCache.size}`);
      return jobs;
    });
  }
  
  public getJobsByState(state: JobState): Readable<JobInfo[]> {
    return derived(this.getAllJobs(), $jobs => 
      $jobs.filter(job => job.state === state)
    );
  }
  
  public getHostJobs(hostname: string): Readable<JobInfo[]> {
    return derived(this.state, $state => {
      const hostState = $state.hostStates.get(hostname);
      if (!hostState) return [];

      const jobs: JobInfo[] = [];
      hostState.jobs.forEach((cacheKey) => {
        const entry = $state.jobCache.get(cacheKey);
        if (entry) jobs.push(entry.job);
      });

      return jobs;
    });
  }

  /**
   * Get a reactive store for a single job
   * Returns null if job not found
   */
  public getJob(jobId: string, hostname: string): Readable<JobInfo | null> {
    const cacheKey = `${hostname}:${jobId}`;
    return derived(this.state, $state => {
      const entry = $state.jobCache.get(cacheKey);
      return entry?.job || null;
    });
  }

  /**
   * Fetch a single job, prioritizing updates for current view
   */
  public async fetchSingleJob(jobId: string, hostname: string, forceRefresh = false): Promise<JobInfo | null> {
    const cacheKey = `${hostname}:${jobId}`;
    const state = get(this.state);
    const cached = state.jobCache.get(cacheKey);

    // Return from cache if valid and not forcing
    if (!forceRefresh && cached && this.isJobCacheValid(cacheKey)) {
      return cached.job;
    }

    // Fetch from API
    try {
      this.updateMetric('apiCalls', 1);
      const response = await api.get<JobInfo>(`/api/jobs/${jobId}?host=${hostname}${forceRefresh ? '&force=true' : ''}`);
      const job = response.data;

      // Update cache immediately for current job (bypass batch delay)
      this.queueUpdate({
        jobId,
        hostname,
        job,
        source: 'api',
        timestamp: Date.now(),
        priority: 'realtime',
      }, true); // Immediate processing

      return job;
    } catch (error) {
      console.error(`[JobStateManager] Failed to fetch job ${jobId} on ${hostname}:`, error);
      return cached?.job || null; // Return cached if available
    }
  }

  public getConnectionStatus(): Readable<{
    source: DataSource;
    connected: boolean;
    healthy: boolean;
  }> {
    return derived(this.state, $state => ({
      source: $state.dataSource,
      connected: $state.wsConnected || $state.pollingActive,
      healthy: $state.wsHealthy || !$state.isPaused,
    }));
  }
}

// ============================================================================
// Export Singleton Instance
// ============================================================================

export const jobStateManager = new JobStateManager();

// Initialize on import
if (typeof window !== 'undefined') {
  jobStateManager.initialize();
}