/**
 * Simplified Job State Manager
 *
 * Single reactive store for all job data.
 * Backend handles all caching - frontend just fetches and displays.
 * WebSocket provides real-time updates, simple refetch on disconnect.
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

interface JobEntry {
  job: JobInfo;
  lastUpdated: number;
}

interface HostState {
  hostname: string;
  status: 'connected' | 'loading' | 'error' | 'idle';
  lastSync: number;
  errorCount: number;
  lastError?: string;
  isTimeout?: boolean;
  jobs: Set<string>; // Just job IDs
  arrayGroups: ArrayJobGroup[];
}

interface ManagerState {
  // Core data - simple Map of jobs by key
  jobs: Map<string, JobEntry>;      // cacheKey -> job data
  hostStates: Map<string, HostState>;

  // WebSocket connection state
  wsConnected: boolean;

  // Loading state
  isLoading: boolean;
}

// ============================================================================
// Job State Manager Class
// ============================================================================

class JobStateManager {
  private state = writable<ManagerState>({
    jobs: new Map(),
    hostStates: new Map(),
    wsConnected: false,
    isLoading: false,
  });

  private ws: WebSocket | null = null;
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
    this.api = dependencies?.api || api;
    this.wsFactory = dependencies?.webSocketFactory || new ProductionWebSocketFactory();
    this.preferences = dependencies?.preferences || preferences;
    this.notificationService = dependencies?.notificationService || notificationService;
    this.environment = dependencies?.environment || new ProductionEnvironment();
  }

  // ========================================================================
  // WebSocket Management
  // ========================================================================

  public connectWebSocket(): void {
    console.log('[JobStateManager] Connecting WebSocket...');

    if (!this.environment.hasWebSocket) {
      console.warn('[JobStateManager] WebSocket not available');
      return;
    }

    if (this.ws?.readyState === 1) {
      console.log('[JobStateManager] WebSocket already open');
      return;
    }

    const location = this.environment.location;
    if (!location) {
      console.warn('[JobStateManager] Location not available');
      return;
    }

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws/jobs`;

    this.ws = this.wsFactory.create(wsUrl) as WebSocket;

    this.ws.onopen = () => {
      console.log('[JobStateManager] WebSocket connected');
      this.updateState({ wsConnected: true });
      this.startPing();
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleWebSocketMessage(data);
      } catch (e) {
        console.error('[JobStateManager] Failed to parse WebSocket message:', e);
      }
    };

    this.ws.onclose = () => {
      console.log('[JobStateManager] WebSocket closed');
      this.stopPing();
      this.updateState({ wsConnected: false });

      // Reconnect after delay
      setTimeout(() => this.connectWebSocket(), 5000);
    };

    this.ws.onerror = (error) => {
      console.error('[JobStateManager] WebSocket error:', error);
    };
  }

  private handleWebSocketMessage(data: any): void {
    if (data.type === 'pong') {
      return;
    }

    console.log('[JobStateManager] WebSocket message:', data.type);

    if (data.type === 'initial' && data.jobs) {
      // Handle initial data load
      const hostsInUpdate = Object.keys(data.jobs);
      console.log(`[JobStateManager] Processing initial data from ${hostsInUpdate.length} hosts`);

      // Clear jobs for these hosts
      this.state.update(s => {
        const newJobs = new Map(s.jobs);
        hostsInUpdate.forEach(hostname => {
          const keysToDelete: string[] = [];
          newJobs.forEach((_, key) => {
            if (key.startsWith(`${hostname}:`)) {
              keysToDelete.push(key);
            }
          });
          keysToDelete.forEach(key => newJobs.delete(key));
        });
        s.jobs = newJobs;
        return s;
      });

      // Add new jobs
      for (const [hostname, jobs] of Object.entries(data.jobs)) {
        if (Array.isArray(jobs)) {
          jobs.forEach((job: any) => {
            if (job.job_id) {
              job.hostname = hostname;
              this.updateJob(job.job_id, hostname, job);
            }
          });
        }
      }
    } else if (data.type === 'job_update' || data.type === 'state_change') {
      // Single job update
      if (data.job_id && data.hostname && data.job) {
        this.updateJob(data.job_id, data.hostname, data.job);
      }
    } else if (data.type === 'batch_update' && data.updates) {
      // Batch update
      data.updates.forEach((update: any) => {
        if (update.job_id && update.hostname && update.job) {
          this.updateJob(update.job_id, update.hostname, update.job);
        }
      });
    } else if (Array.isArray(data)) {
      // Array of jobs
      data.forEach((job: any) => {
        if (job.job_id && job.hostname) {
          this.updateJob(job.job_id, job.hostname, job);
        }
      });
    } else if (data.jobs && Array.isArray(data.jobs)) {
      // Object with jobs array
      const hostname = data.hostname;
      data.jobs.forEach((job: any) => {
        if (job.job_id) {
          const h = hostname || job.hostname;
          if (h) {
            job.hostname = h;
            this.updateJob(job.job_id, h, job);
          }
        }
      });
    }
  }

  private updateJob(jobId: string, hostname: string, job: JobInfo): void {
    const cacheKey = `${hostname}:${jobId}`;

    this.state.update(s => {
      const newJobs = new Map(s.jobs);
      const existing = newJobs.get(cacheKey);

      // Ensure hostname is set
      if (!job.hostname) {
        job.hostname = hostname;
      }

      // Notify about state changes
      if (!existing) {
        console.log(`[JobStateManager] New job: ${cacheKey} (${job.state})`);
        this.notificationService.notifyNewJob(jobId, hostname, job.state, job.name || 'Unnamed job');
      } else if (existing.job.state !== job.state) {
        console.log(`[JobStateManager] State change: ${cacheKey} ${existing.job.state} -> ${job.state}`);
        this.notificationService.notifyJobStateChange(jobId, hostname, existing.job.state, job.state);
      }

      newJobs.set(cacheKey, {
        job,
        lastUpdated: Date.now(),
      });

      s.jobs = newJobs;
      return s;
    });
  }

  // ========================================================================
  // WebSocket Ping/Keepalive
  // ========================================================================

  private startPing(): void {
    if (this.pingTimer) return;

    this.pingTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === 1) {
        try {
          this.ws.send(JSON.stringify({ type: 'ping' }));
        } catch (e) {
          console.error('[JobStateManager] Failed to send ping:', e);
        }
      }
    }, 30000);
  }

  private stopPing(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  // ========================================================================
  // Data Fetching
  // ========================================================================

  public async syncAllHosts(): Promise<void> {
    console.log('[JobStateManager] Syncing all hosts...');
    this.updateState({ isLoading: true });

    try {
      // Get list of hosts
      const hostsResponse = await this.api.get<HostInfo[]>('/api/hosts');
      const hosts = hostsResponse.data || [];

      if (hosts.length === 0) {
        console.warn('[JobStateManager] No hosts found');
        this.updateState({ isLoading: false });
        return;
      }

      // Initialize host states
      this.state.update(s => {
        const newHostStates = new Map(s.hostStates);
        hosts.forEach(host => {
          if (!newHostStates.has(host.hostname)) {
            newHostStates.set(host.hostname, {
              hostname: host.hostname,
              status: 'idle',
              lastSync: 0,
              errorCount: 0,
              jobs: new Set(),
              arrayGroups: [],
            });
          }
        });
        s.hostStates = newHostStates;
        return s;
      });

      // Sync each host in parallel
      await Promise.allSettled(hosts.map(host => this.syncHost(host.hostname)));

      console.log('[JobStateManager] All hosts synced');
    } catch (error) {
      console.error('[JobStateManager] Failed to sync hosts:', error);
    } finally {
      this.updateState({ isLoading: false });
    }
  }

  public async syncHost(hostname: string): Promise<void> {
    console.log(`[JobStateManager] Syncing ${hostname}...`);

    const state = get(this.state);
    const hostState = state.hostStates.get(hostname);

    if (!hostState) {
      console.warn(`[JobStateManager] Host state not found: ${hostname}`);
      return;
    }

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
      // Build URL
      const params = new URLSearchParams();
      params.append('host', hostname);
      params.append('group_array_jobs', String(get(this.preferences).groupArrayJobs));

      // Fetch from backend (backend handles caching)
      const response = await this.api.get<JobStatusResponse | JobStatusResponse[]>(
        `/api/status?${params.toString()}`
      );

      // Handle response
      let hostData: JobStatusResponse;
      if (Array.isArray(response.data)) {
        hostData = response.data[0];
      } else {
        hostData = response.data;
      }

      if (!hostData) {
        console.warn(`[JobStateManager] No data for ${hostname}`);
        return;
      }

      if (hostData && Array.isArray(hostData.jobs)) {
        const arrayGroups = hostData.array_groups || [];
        const jobIds = new Set<string>();

        // Update all jobs
        hostData.jobs.forEach(job => {
          if (!job.hostname) {
            job.hostname = hostname;
          }
          jobIds.add(job.job_id);
          this.updateJob(job.job_id, hostname, job);
        });

        // Update host state
        this.state.update(s => {
          const newHostStates = new Map(s.hostStates);
          const hs = newHostStates.get(hostname);
          if (hs) {
            newHostStates.set(hostname, {
              ...hs,
              jobs: jobIds,
              arrayGroups: arrayGroups,
              status: 'connected',
              lastSync: Date.now(),
              errorCount: 0,
            });
          }
          s.hostStates = newHostStates;
          return s;
        });

        console.log(`[JobStateManager] Synced ${hostname} (${jobIds.size} jobs)`);
      } else {
        // No jobs
        this.state.update(s => {
          const newHostStates = new Map(s.hostStates);
          const hs = newHostStates.get(hostname);
          if (hs) {
            newHostStates.set(hostname, {
              ...hs,
              arrayGroups: [],
              status: 'connected',
              lastSync: Date.now(),
              errorCount: 0,
            });
          }
          s.hostStates = newHostStates;
          return s;
        });

        console.log(`[JobStateManager] Synced ${hostname} (no jobs)`);
      }
    } catch (error: any) {
      const isTimeout = error?.message?.includes('timeout');
      const errorMessage = error?.response?.data?.detail || error?.message || 'Unknown error';

      console.error(`[JobStateManager] Failed to sync ${hostname}:`, errorMessage);

      this.state.update(s => {
        const newHostStates = new Map(s.hostStates);
        const hs = newHostStates.get(hostname);
        if (hs) {
          newHostStates.set(hostname, {
            ...hs,
            status: 'error',
            errorCount: hs.errorCount + 1,
            lastError: errorMessage,
            isTimeout: isTimeout,
          });
        }
        s.hostStates = newHostStates;
        return s;
      });

      if (isTimeout) {
        this.notificationService.notify({
          type: 'error',
          message: `Connection to ${hostname} timed out`,
          duration: 5000,
        });
      }
    }
  }

  // ========================================================================
  // Single Job Fetching
  // ========================================================================

  public async fetchJob(jobId: string, hostname: string): Promise<JobInfo | null> {
    const cacheKey = `${hostname}:${jobId}`;
    const state = get(this.state);
    const cached = state.jobs.get(cacheKey);

    // Return cached if available (for immediate display)
    // But still fetch in background for latest data
    if (cached) {
      // Fetch in background
      this.fetchJobFromBackend(jobId, hostname);
      return cached.job;
    }

    // Fetch synchronously
    return await this.fetchJobFromBackend(jobId, hostname);
  }

  private async fetchJobFromBackend(jobId: string, hostname: string): Promise<JobInfo | null> {
    try {
      const response = await this.api.get<JobInfo>(
        `/api/jobs/${encodeURIComponent(jobId)}?host=${hostname}`
      );
      const job = response.data;

      // Update state
      this.updateJob(jobId, hostname, job);

      return job;
    } catch (error) {
      console.error(`[JobStateManager] Failed to fetch job ${jobId}:`, error);
      return null;
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

    // Clear state
    this.state.update(s => ({
      ...s,
      jobs: new Map(),
    }));

    // Sync data from backend
    await this.syncAllHosts();

    // Connect WebSocket for real-time updates
    this.connectWebSocket();

    console.log('[JobStateManager] Initialized');
  }

  public destroy(): void {
    this.ws?.close();
    this.stopPing();
  }

  public refresh(): Promise<void> {
    return this.syncAllHosts();
  }

  public getState(): Readable<ManagerState> {
    return { subscribe: this.state.subscribe };
  }

  // ========================================================================
  // Derived Stores
  // ========================================================================

  public getAllJobs(): Readable<JobInfo[]> {
    return derived(this.state, $state => {
      const jobs = Array.from($state.jobs.values())
        .map(entry => entry.job)
        .sort((a, b) => {
          const timeA = new Date(a.submit_time || 0).getTime();
          const timeB = new Date(b.submit_time || 0).getTime();
          return timeB - timeA;
        });

      return jobs;
    });
  }

  public getJobsByState(state: string): Readable<JobInfo[]> {
    return derived(this.getAllJobs(), $jobs =>
      $jobs.filter(job => job.state === state)
    );
  }

  public getHostJobs(hostname: string): Readable<JobInfo[]> {
    return derived(this.state, $state => {
      const hostState = $state.hostStates.get(hostname);
      if (!hostState) return [];

      const jobs: JobInfo[] = [];
      hostState.jobs.forEach((jobId) => {
        const cacheKey = `${hostname}:${jobId}`;
        const entry = $state.jobs.get(cacheKey);
        if (entry) jobs.push(entry.job);
      });

      return jobs;
    });
  }

  public getJob(jobId: string, hostname: string): Readable<JobInfo | null> {
    const cacheKey = `${hostname}:${jobId}`;
    return derived(this.state, $state => {
      const entry = $state.jobs.get(cacheKey);
      return entry?.job || null;
    });
  }

  public getConnectionStatus(): Readable<{
    connected: boolean;
    isLoading: boolean;
  }> {
    return derived(this.state, $state => ({
      connected: $state.wsConnected,
      isLoading: $state.isLoading,
    }));
  }

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

  public getHostStates(): Readable<Map<string, HostState>> {
    return derived(this.state, $state => $state.hostStates);
  }

  public getIsLoading(): Readable<boolean> {
    return derived(this.state, $state => $state.isLoading);
  }
}

// ============================================================================
// Export Singleton Instance and Class
// ============================================================================

export { JobStateManager };

export const jobStateManager = new JobStateManager();

// Initialize on import (only in browser)
if (typeof window !== 'undefined' && !import.meta.env.VITEST) {
  jobStateManager.initialize();
}
