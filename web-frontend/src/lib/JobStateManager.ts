/**
 * Centralized Job State Manager
 * 
 * Single source of truth for all job data and updates.
 * Manages WebSocket, polling, caching, and state synchronization.
 */

import { writable, derived, get, type Readable } from 'svelte/store';
import type { JobInfo, HostInfo, JobStatusResponse, ArrayJobGroup } from '../types/api';
import { api } from '../services/api';
import { notificationService } from '../services/notifications';
import { preferences } from '../stores/preferences';
import type {
  JobStateManagerDependencies,
  IApiClient,
  IWebSocketFactory,
  IPreferencesStore,
  INotificationService,
  IEnvironment
} from './JobStateManager.types';
import {
  ProductionWebSocketFactory,
  ProductionEnvironment
} from './JobStateManager.types';

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
  lastError?: string;
  lastErrorTime?: number;
  isTimeout?: boolean;
  jobs: Map<string, string>; // jobId -> cacheKey mapping
  arrayGroups: ArrayJobGroup[]; // Array job groups for this host
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
    batchSize: 100, // Increased from 50 for faster bulk processing
    batchDelay: 10, // Reduced from 100ms for faster updates
    batchDelayImmediate: 0, // For forced refreshes
    deduplicateWindow: 100, // Reduced from 500ms for faster deduplication
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
    websocket: 0,       // Realtime via WebSocket
    active: 30000,      // 30 sec when active (reduced from 60s)
    background: 60000,  // 1 min in background (reduced from 5 min)
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
  private pingTimer: ReturnType<typeof setInterval> | null = null;

  // Injected dependencies
  private api: IApiClient;
  private wsFactory: IWebSocketFactory;
  private preferences: IPreferencesStore;
  private notificationService: INotificationService;
  private environment: IEnvironment;

  // ========================================================================
  // Initialization
  // ========================================================================

  constructor(dependencies?: Partial<JobStateManagerDependencies>) {
    // Initialize dependencies with defaults
    this.api = dependencies?.api || api;
    this.wsFactory = dependencies?.webSocketFactory || new ProductionWebSocketFactory();
    this.preferences = dependencies?.preferences || preferences;
    this.notificationService = dependencies?.notificationService || notificationService;
    this.environment = dependencies?.environment || new ProductionEnvironment();
    // Bind methods to ensure proper context
    this.processUpdateQueue = this.processUpdateQueue.bind(this);
    this.queueUpdate = this.queueUpdate.bind(this);
    this.handleWebSocketMessage = this.handleWebSocketMessage.bind(this);

    // Only setup event listeners and monitoring if in browser environment
    if (this.environment.hasDocument) {
      this.setupEventListeners();
      this.startHealthMonitoring();
    }
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
    console.log('[JobStateManager] 🔌 Attempting to connect WebSocket...');

    // Check if WebSocket is available (not in test environment without proper mock)
    if (!this.environment.hasWebSocket) {
      console.warn('[JobStateManager] ⚠️ WebSocket not available in this environment');
      return;
    }

    // Check if already open (readyState 1 = OPEN)
    if (this.ws?.readyState === 1) {
      console.log('[JobStateManager] ℹ️ WebSocket already open, skipping reconnect');
      return;
    }

    // Get location from environment
    const location = this.environment.location;
    if (!location) {
      console.warn('[JobStateManager] ⚠️ Location not available');
      return;
    }

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws/jobs`;
    console.log('[JobStateManager] 🌐 WebSocket URL:', wsUrl);

    this.ws = this.wsFactory.create(wsUrl) as WebSocket;
    console.log('[JobStateManager] 📡 WebSocket object created, waiting for connection...');
    
    this.ws.onopen = () => {
      this.updateState({
        wsConnected: true,
        wsHealthy: true,
        dataSource: 'websocket',
        lastActivity: Date.now(),
      });
      this.stopPolling();
      this.startPing();
      console.log('[JobStateManager] ✅ WebSocket connected successfully to', wsUrl);
      console.log('[JobStateManager] WebSocket readyState:', this.ws?.readyState);
    };
    
    this.ws.onmessage = (event) => {
      try {
        console.log('[JobStateManager] 📨 WebSocket message received, size:', event.data.length, 'bytes');
        const data = JSON.parse(event.data);
        console.log('[JobStateManager] 📨 Parsed message type:', data.type);
        this.handleWebSocketMessage(data);
        this.updateState({ lastActivity: Date.now() });
      } catch (e) {
        console.error('[JobStateManager] ❌ Failed to parse WebSocket message:', e);
      }
    };
    
    this.ws.onclose = (event) => {
      console.log('[JobStateManager] ❌ WebSocket closed. Code:', event.code, 'Reason:', event.reason);
      this.stopPing();
      this.updateState({
        wsConnected: false,
        wsHealthy: false,
        dataSource: 'api',
        wsInitialDataReceived: false,  // Reset initial data flag
        wsInitialDataTimestamp: 0,
      });
      this.startPolling();

      // Reconnect after delay
      console.log('[JobStateManager] 🔄 Will reconnect WebSocket in', CONFIG.health.retryDelay / 1000, 'seconds');
      setTimeout(() => this.connectWebSocket(), CONFIG.health.retryDelay);
    };

    this.ws.onerror = (error) => {
      console.error('[JobStateManager] ❌ WebSocket error:', error);
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
    // ⚡ PERFORMANCE FIX: Update lastActivity even for pong messages to keep connection healthy
    if (data.type === 'pong') {
      this.updateState({ lastActivity: Date.now() });
      return;
    }

    console.log('[JobStateManager] WebSocket message received:', data.type, data);

    // Track WebSocket messages
    this.updateMetric('wsMessages', 1);

    // Handle different message formats
    if (data.type === 'initial' && data.jobs) {
      // Handle initial data load with jobs grouped by hostname
      const totalJobs = data.total || 0;
      const hostsInUpdate = Object.keys(data.jobs);
      console.log(`[JobStateManager] Processing initial data with ${totalJobs} total jobs from ${hostsInUpdate.length} hosts: ${hostsInUpdate.join(', ')}`);

      // Only mark initial data as received if it actually contains jobs
      // Empty initial data (0 jobs from 0 hosts) should not block API syncs
      if (totalJobs > 0 || hostsInUpdate.length > 0) {
        this.updateState({
          wsInitialDataReceived: true,
          wsInitialDataTimestamp: Date.now()
        });
      } else {
        console.log('[JobStateManager] Initial WebSocket data is empty (0 jobs, 0 hosts) - will allow API sync to proceed');
      }

      // Only clear cache for hosts that are included in this update
      // This prevents losing jobs from hosts that timed out or weren't included
      this.state.update(s => {
        const newCache = new Map(s.jobCache);

        // Remove jobs only for hosts included in the update
        hostsInUpdate.forEach(hostname => {
          // Remove all jobs for this host
          const keysToDelete: string[] = [];
          newCache.forEach((_, cacheKey) => {
            if (cacheKey.startsWith(`${hostname}:`)) {
              keysToDelete.push(cacheKey);
            }
          });
          keysToDelete.forEach(key => newCache.delete(key));
          console.log(`[JobStateManager] Cleared ${keysToDelete.length} cached jobs for host ${hostname} before initial load`);
        });

        s.jobCache = newCache;
        return s;
      });

      // ⚡ PERFORMANCE: Process all jobs in a single batch for faster UI update
      const allUpdates: JobUpdate[] = [];
      const timestamp = Date.now();

      console.log('[JobStateManager] 📦 Processing initial data.jobs:', Object.keys(data.jobs));
      console.log('[JobStateManager] 📦 data.jobs type:', typeof data.jobs, 'is array?', Array.isArray(data.jobs));

      for (const [hostname, jobs] of Object.entries(data.jobs)) {
        console.log(`[JobStateManager] 📦 Checking hostname="${hostname}", jobs type:`, typeof jobs, 'is array?', Array.isArray(jobs), 'length:', Array.isArray(jobs) ? jobs.length : 'N/A');
        if (Array.isArray(jobs)) {
          console.log(`[JobStateManager] Preparing ${jobs.length} jobs for ${hostname}`);
          jobs.forEach((job: any) => {
            if (job.job_id && hostname) {
              // ALWAYS set hostname from the key to ensure consistency
              job.hostname = hostname;
              allUpdates.push({
                jobId: job.job_id,
                hostname: hostname,  // Use hostname from the key, not from job object
                job: job,
                source: 'websocket',
                timestamp: timestamp,
                priority: 'high',
                messageType: 'initial',
              });
            } else {
              console.warn(`[JobStateManager] ⚠️ Skipping job without job_id:`, job);
            }
          });
        } else {
          console.warn(`[JobStateManager] ⚠️ Jobs for ${hostname} is not an array:`, typeof jobs);
        }
      }

      // Queue all updates at once for immediate batch processing
      console.log(`[JobStateManager] Queueing ${allUpdates.length} jobs for immediate processing`);
      allUpdates.forEach(update => this.queueUpdate(update, false));
      // Force immediate processing after all are queued
      if (allUpdates.length > 0) {
        if (this.updateTimer) {
          clearTimeout(this.updateTimer);
          this.updateTimer = null;
        }
        this.processUpdateQueue();
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
          // Ensure hostname is set on job object for consistency
          const hostname = job.hostname;
          job.hostname = hostname;
          this.queueUpdate({
            jobId: job.job_id,
            hostname: hostname,
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
      const contextHostname = data.hostname;
      data.jobs.forEach((job: any) => {
        if (job.job_id) {
          // Use context hostname if provided, otherwise use job's hostname
          const hostname = contextHostname || job.hostname;
          if (!hostname) {
            console.warn(`[JobStateManager] Job ${job.job_id} has no hostname, skipping`);
            return;
          }
          // Ensure hostname is set on job object for consistency
          job.hostname = hostname;
          this.queueUpdate({
            jobId: job.job_id,
            hostname: hostname,
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
    if (this.pollTimer) {
      console.log('[JobStateManager] ⚠️ Polling already running, skipping start');
      return;
    }

    const state = get(this.state);
    if (state.isPaused || state.wsHealthy) {
      console.log('[JobStateManager] ℹ️ Skipping polling - paused:', state.isPaused, 'wsHealthy:', state.wsHealthy);
      return;
    }

    const interval = state.isTabActive
      ? CONFIG.syncIntervals.active
      : CONFIG.syncIntervals.background;

    console.log(`[JobStateManager] 🔄 Starting fallback polling (${interval/1000}s interval) - tab active: ${state.isTabActive}, WS connected: ${state.wsConnected}, WS healthy: ${state.wsHealthy}`);

    this.pollTimer = setInterval(() => {
      // Force sync to bypass cache during polling - we want fresh data when in fallback mode
      this.syncAllHosts(true);
    }, interval);

    this.updateState({ pollingActive: true });
  }
  
  private stopPolling(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
      this.updateState({ pollingActive: false });
      console.log('[JobStateManager] ⏹️ Polling stopped - switching to WebSocket updates');
    }
  }

  // ========================================================================
  // WebSocket Ping/Keepalive
  // ========================================================================

  private startPing(): void {
    if (this.pingTimer) {
      console.log('[JobStateManager] ⚠️ Ping already running, skipping start');
      return;
    }

    // Send ping every 30 seconds to keep connection alive
    this.pingTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === 1) {
        try {
          this.ws.send(JSON.stringify({ type: 'ping' }));
          console.log('[JobStateManager] 🏓 Sent ping to keep WebSocket alive');
        } catch (e) {
          console.error('[JobStateManager] ❌ Failed to send ping:', e);
        }
      }
    }, 30000); // Ping every 30 seconds (well under the 45s health timeout)

    console.log('[JobStateManager] 🏓 Started WebSocket ping (30s interval)');
  }

  private stopPing(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
      console.log('[JobStateManager] 🏓 Stopped WebSocket ping');
    }
  }

  // ========================================================================
  // Data Synchronization
  // ========================================================================
  
  public async syncAllHosts(forceSync = false): Promise<void> {
    const state = get(this.state);
    if (!forceSync && state.isPaused) return;

    // ⚡ PERFORMANCE: Removed WebSocket wait check - always fetch for fastest UI update
    // WebSocket and API work in parallel, whoever is faster wins
    // This ensures blazing fast refresh when user clicks refresh button

    try {
      console.log(`[JobStateManager] Starting sync for all hosts${forceSync ? ' (FORCE REFRESH - bypassing all caches)' : ''}`);
      if (forceSync) {
        console.log('[JobStateManager] Force refresh will fetch directly from SLURM');
      }
      // Get list of hosts
      const hostsResponse = await this.api.get<HostInfo[]>('/api/hosts');
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
              arrayGroups: [],
            });
          }
        });
        s.hostStates = newHostStates;
        return s;
      });
      
      // Sync each host in parallel
      const results = await Promise.allSettled(
        hosts.map(host => this.syncHost(host.hostname, forceSync))
      );

      console.log('[JobStateManager] ✅ All host syncs completed');
      results.forEach((result, index) => {
        const hostname = hosts[index].hostname;
        if (result.status === 'fulfilled') {
          console.log(`[JobStateManager] ✓ ${hostname} sync succeeded`);
        } else {
          console.log(`[JobStateManager] ✗ ${hostname} sync failed:`, result.reason);
        }
      });
    } catch (error) {
      console.error('[JobStateManager] Failed to sync hosts:', error);
    }
  }
  
  public async syncHost(hostname: string, forceSync = false): Promise<void> {
    const syncStartTime = Date.now();
    console.log(`[JobStateManager] 🔄 Starting sync for ${hostname}${forceSync ? ' (forced)' : ''}`);

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

      // ⚡ PERFORMANCE: Reduced timeout for faster failure detection and UI responsiveness
      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error('Request timeout')), 10000); // 10s timeout (reduced from 30s)
      });

      // Build URL with array grouping parameter
      const params = new URLSearchParams();
      params.append('host', hostname);
      // Use the user's preference for array job grouping
      params.append('group_array_jobs', String(get(this.preferences).groupArrayJobs));

      // Pass force_refresh parameter when forceSync is true
      if (forceSync) {
        params.append('force_refresh', 'true');
      }

      // The API might return either an array or a single object depending on the endpoint
      // Race between API call and timeout
      const response = await Promise.race([
        this.api.get<JobStatusResponse | JobStatusResponse[]>(
          `/api/status?${params.toString()}`
        ),
        timeoutPromise
      ]);

      // Handle both array and single object responses
      let hostData: JobStatusResponse;
      if (Array.isArray(response.data)) {
        hostData = response.data[0];
      } else {
        hostData = response.data;
      }

      if (!hostData) {
        console.warn(`[JobStateManager] No data in response for ${hostname}`);
        return;
      }

      // Check if jobs field exists and is an array
      if (hostData && Array.isArray(hostData.jobs)) {
        // Extract array groups if present
        const arrayGroups = hostData.array_groups || [];

        // Prepare jobs for queueing
        const jobsToQueue: JobUpdate[] = [];

        // Update host state with job mappings and array groups
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

            // Create new host state object with array groups
            newHostStates.set(hostname, {
              ...hs,
              jobs: newJobs,
              arrayGroups: arrayGroups,
              status: 'connected',
              lastSync: now,
              errorCount: 0,
            });
          }
          s.hostStates = newHostStates;
          return s;
        });

        // Queue all job updates after state update
        console.log(`[JobStateManager] 📤 ${hostname} - About to queue ${jobsToQueue.length} jobs...`);
        // ⚡ PERFORMANCE FIX: Queue all jobs without immediate processing to avoid hanging
        // When forceSync=true and there are many jobs, calling queueUpdate with immediate=true
        // causes synchronous processUpdateQueue() for EACH job, which can hang the browser.
        // Instead, queue all jobs first, then trigger a single batch process at the end.
        jobsToQueue.forEach(update => this.queueUpdate(update, false));
        console.log(`[JobStateManager] 📥 ${hostname} - Finished queueing ${jobsToQueue.length} jobs, forcing batch process...`);

        // Force immediate batch processing of all queued jobs
        if (jobsToQueue.length > 0) {
          // Clear any pending timer and process immediately
          if (this.updateTimer) {
            clearTimeout(this.updateTimer);
            this.updateTimer = null;
          }
          console.log(`[JobStateManager] 🔄 ${hostname} - Triggering immediate batch processing...`);
          this.processUpdateQueue();
          console.log(`[JobStateManager] ✓ ${hostname} - Batch processing complete`);
        }

        const syncDuration = Date.now() - syncStartTime;
        console.log(`[JobStateManager] ✅ ${hostname} sync completed in ${syncDuration}ms (${jobsToQueue.length} jobs)`);
      } else {
        // Still mark as connected even if no jobs
        this.state.update(s => {
          const newHostStates = new Map(s.hostStates);
          const hs = newHostStates.get(hostname);
          if (hs) {
            newHostStates.set(hostname, {
              ...hs,
              arrayGroups: [],
              status: 'connected',
              lastSync: now,
              errorCount: 0,
            });
          }
          s.hostStates = newHostStates;
          return s;
        });

        const syncDuration = Date.now() - syncStartTime;
        console.log(`[JobStateManager] ✅ ${hostname} sync completed in ${syncDuration}ms (no jobs)`);
      }
    } catch (error: any) {
      const isTimeout = error?.message?.includes('timeout') || error?.message?.includes('Timeout');
      const errorMessage = error?.response?.data?.detail || error?.message || 'Unknown error';
      const syncDuration = Date.now() - syncStartTime;

      console.error(`[JobStateManager] ❌ ${hostname} sync failed after ${syncDuration}ms:`, errorMessage, isTimeout ? '(TIMEOUT)' : '');

      this.state.update(s => {
        const newHostStates = new Map(s.hostStates);
        const hs = newHostStates.get(hostname);
        if (hs) {
          newHostStates.set(hostname, {
            ...hs,
            status: 'error',
            errorCount: hs.errorCount + 1,
            lastError: errorMessage,
            lastErrorTime: Date.now(),
            isTimeout: isTimeout,
          });
        }
        s.hostStates = newHostStates;
        return s;
      });

      // Show notification for timeout
      if (isTimeout) {
        this.notificationService.notify({
          type: 'error',
          message: `Connection to ${hostname} timed out`,
          duration: 5000,
        });
      }
    }

    const totalSyncDuration = Date.now() - syncStartTime;
    console.log(`[JobStateManager] 🏁 ${hostname} sync function exiting after ${totalSyncDuration}ms`);
  }
  
  // ========================================================================
  // Update Queue Management
  // ========================================================================
  
  private queueUpdate(update: JobUpdate, immediate = false): void {
    // Validate hostname is present
    if (!update.hostname) {
      console.error(`[JobStateManager] Cannot queue update for job ${update.jobId} - missing hostname`);
      return;
    }

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

          // WebSocket updates take priority over API updates, except when forcing refresh
          // For same source, newer timestamp wins
          const shouldReplace = !existing ||
            (u.source === 'websocket' && existing.source === 'api' && u.timestamp >= existing.timestamp) ||
            (u.source === existing.source && u.timestamp > existing.timestamp) ||
            (u.priority === 'realtime' && existing.priority !== 'realtime');

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
      // ⚡ PERFORMANCE: Use zero delay for empty cache (initial load) for instant UI update
      // For subsequent updates, use minimal delay to allow batching
      const state = get(this.state);
      const delay = state.jobCache.size === 0 ? 0 : 10; // Reduced from 100ms to 10ms
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
          // Check for new jobs appearing
          if (!existing) {
            console.log(`[JobStateManager] New job detected: ${cacheKey} in state ${update.job.state} from ${update.source}`);

            // Notify about new job
            this.notificationService.notifyNewJob(
              update.jobId,
              update.hostname,
              update.job.state,
              update.job.name || 'Unnamed job'
            );
          }
          // Check for state transitions
          else if (existing.job.state !== update.job.state) {
            console.log(`[JobStateManager] Job ${cacheKey} state change: ${existing.job.state} -> ${update.job.state}`);

            // Send notification for state changes
            this.notificationService.notifyJobStateChange(
              update.jobId,
              update.hostname,
              existing.job.state,
              update.job.state
            );
          } else {
            console.log(`[JobStateManager] Updating existing job ${cacheKey} from ${update.source} (no state change)`);
          }

          // Ensure hostname is set on the job object
          if (!update.job.hostname) {
            update.job.hostname = update.hostname;
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
          console.log(`[JobStateManager] Skipping duplicate update for ${cacheKey} from ${update.source} (existing: ${existing.lastSource}, timestamp: ${existing.lastUpdated} vs ${update.timestamp})`);
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
      const response = await this.api.get<JobInfo>(`/api/jobs/${encodeURIComponent(jobId)}?host=${hostname}`);
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
    console.log('[JobStateManager] 🚀 INITIALIZING JobStateManager...');
    console.log('[JobStateManager] Current environment:', {
      hasWebSocket: this.environment.hasWebSocket,
      hasDocument: this.environment.hasDocument,
      location: this.environment.location?.host,
    });

    // Clear any existing state first
    this.state.update(s => ({
      ...s,
      jobCache: new Map(),
      pendingUpdates: [],
      processingUpdates: false,
      wsInitialDataReceived: false,
      wsInitialDataTimestamp: 0,
    }));

    console.log('[JobStateManager] ⚡ Starting initial API sync first...');
    // ⚡ PERFORMANCE FIX: Do API sync FIRST to avoid race condition with WebSocket
    // The backend prevents concurrent fetches per host, so if we start both in parallel,
    // the WebSocket gets 0 jobs because all hosts are locked by the API fetch.
    await this.forceInitialSync();

    console.log('[JobStateManager] ⚡ Now connecting WebSocket for real-time updates...');
    // Connect WebSocket AFTER initial data is loaded
    // This way the WebSocket receives the full initial state and then only updates
    this.connectWebSocket();

    console.log('[JobStateManager] ✅ Initialization complete');
  }
  
  public destroy(): void {
    this.ws?.close();
    this.stopPolling();
    this.stopPing();
    if (this.healthCheckTimer) clearInterval(this.healthCheckTimer);
    if (this.updateTimer) clearTimeout(this.updateTimer);
  }
  
  public forceRefresh(): Promise<void> {
    return this.syncAllHosts(true);
  }

  public hasRecentData(maxAge: number = 30000): boolean {
    // Check if we have recent data from any host (within maxAge milliseconds)
    const now = Date.now();
    const state = get(this.state);

    for (const [hostname, hostState] of state.hostStates) {
      if (hostState && (now - hostState.lastSync) < maxAge) {
        console.log(`[JobStateManager] Host ${hostname} has recent data (${Math.round((now - hostState.lastSync) / 1000)}s old)`);
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
      const response = await this.api.get<JobStatusResponse>('/api/status');
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
          // Double-check the cache key matches the job's actual hostname:job_id
          const expectedKey = `${entry.job.hostname}:${entry.job.job_id}`;
          if (cacheKey !== expectedKey) {
            console.warn(`[JobStateManager] Cache key mismatch: ${cacheKey} vs ${expectedKey}`);
          }

          // Use the expected key to ensure consistency
          const existingJob = uniqueJobs.get(expectedKey);
          if (!existingJob || entry.lastUpdated > ($state.jobCache.get(expectedKey)?.lastUpdated || 0)) {
            uniqueJobs.set(expectedKey, entry.job);
          }
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
      const response = await this.api.get<JobInfo>(`/api/jobs/${encodeURIComponent(jobId)}?host=${hostname}${forceRefresh ? '&force=true' : ''}`);
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

  /**
   * Get all array job groups across all hosts
   */
  public getArrayJobGroups(): Readable<ArrayJobGroup[]> {
    return derived(this.state, $state => {
      const allGroups: ArrayJobGroup[] = [];
      $state.hostStates.forEach(hostState => {
        if (hostState.arrayGroups && hostState.arrayGroups.length > 0) {
          allGroups.push(...hostState.arrayGroups);
        }
      });
      return allGroups;
    });
  }

  /**
   * Get host states (loading status, error state, etc.)
   * Returns a Map of hostname -> HostState
   */
  public getHostStates(): Readable<Map<string, HostState>> {
    return derived(this.state, $state => $state.hostStates);
  }
}

// ============================================================================
// Export Singleton Instance and Class
// ============================================================================

// Export the class for testing purposes
export { JobStateManager };

// Export singleton instance for production use
export const jobStateManager = new JobStateManager();

// Initialize on import (only in browser, not in test environment)
if (typeof window !== 'undefined' && !import.meta.env.VITEST) {
  jobStateManager.initialize();
}