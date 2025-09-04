import { writable, derived, get } from 'svelte/store';
import type { JobInfo, JobStatusResponse, JobOutputResponse, HostInfo } from '../types/api';
import { api } from '../services/api';

interface JobCache {
  [key: string]: {
    job: JobInfo;
    timestamp: number;
    output?: JobOutputResponse;
    outputTimestamp?: number;
  };
}

interface HostLoadingState {
  loading: boolean;
  error?: string;
  lastFetch: number;
}

interface JobsState {
  cache: JobCache;
  loading: Set<string>;
  errors: Map<string, string>;
  hostJobs: Map<string, JobStatusResponse>;
  hostLoadingStates: Map<string, HostLoadingState>;
  lastFetch: Map<string, number>;
  sidebarLastLoad: number;
  sidebarJobs: JobInfo[];
  availableHosts: HostInfo[];
}

const CACHE_DURATION = 30000; // 30 seconds cache for individual jobs
const OUTPUT_CACHE_DURATION = 10000; // 10 seconds for output cache

function createJobsStore() {
  const { subscribe, update, set } = writable<JobsState>({
    cache: {},
    loading: new Set(),
    errors: new Map(),
    hostJobs: new Map(),
    hostLoadingStates: new Map(),
    lastFetch: new Map(),
    sidebarLastLoad: 0,
    sidebarJobs: [],
    availableHosts: [],
  });

  return {
    subscribe,
    
    async fetchJob(jobId: string, hostname: string, forceRefresh = false): Promise<JobInfo | null> {
      const state = get({ subscribe });
      const cacheKey = `${hostname}:${jobId}`;
      const cached = state.cache[cacheKey];
      
      // Return cached job if still valid and not forcing refresh
      if (!forceRefresh && cached && Date.now() - cached.timestamp < CACHE_DURATION) {
        return cached.job;
      }
      
      // Prevent duplicate requests
      if (state.loading.has(cacheKey)) {
        // Wait for existing request
        return new Promise((resolve) => {
          const unsubscribe = subscribe((s) => {
            if (!s.loading.has(cacheKey)) {
              unsubscribe();
              resolve(s.cache[cacheKey]?.job || null);
            }
          });
        });
      }
      
      update(s => {
        s.loading.add(cacheKey);
        s.errors.delete(cacheKey);
        return s;
      });
      
      try {
        const response = await api.get<JobInfo>(`/api/jobs/${jobId}?host=${hostname}`);
        const job = response.data;
        
        update(s => {
          s.cache[cacheKey] = {
            job,
            timestamp: Date.now(),
            output: cached?.output,
            outputTimestamp: cached?.outputTimestamp,
          };
          s.loading.delete(cacheKey);
          return s;
        });
        
        return job;
      } catch (error: any) {
        update(s => {
          s.errors.set(cacheKey, error.message || 'Failed to fetch job');
          s.loading.delete(cacheKey);
          return s;
        });
        
        // Return cached job even if expired on error
        return cached?.job || null;
      }
    },
    
    async fetchJobOutput(jobId: string, hostname: string, forceRefresh = false): Promise<JobOutputResponse | null> {
      const state = get({ subscribe });
      const cacheKey = `${hostname}:${jobId}`;
      const cached = state.cache[cacheKey];
      
      // Return cached output if still valid
      if (!forceRefresh && cached?.output && cached.outputTimestamp && 
          Date.now() - cached.outputTimestamp < OUTPUT_CACHE_DURATION) {
        return cached.output;
      }
      
      const outputKey = `output:${cacheKey}`;
      
      // Prevent duplicate requests
      if (state.loading.has(outputKey)) {
        return new Promise((resolve) => {
          const unsubscribe = subscribe((s) => {
            if (!s.loading.has(outputKey)) {
              unsubscribe();
              resolve(s.cache[cacheKey]?.output || null);
            }
          });
        });
      }
      
      update(s => {
        s.loading.add(outputKey);
        return s;
      });
      
      try {
        const params = new URLSearchParams();
        params.append('host', hostname);
        if (forceRefresh) {
          params.append('force_refresh', 'true');
        }
        const response = await api.get<JobOutputResponse>(`/api/jobs/${jobId}/output?${params}`);
        const output = response.data;
        
        update(s => {
          if (!s.cache[cacheKey]) {
            s.cache[cacheKey] = {
              job: {} as JobInfo,
              timestamp: 0,
            };
          }
          s.cache[cacheKey].output = output;
          s.cache[cacheKey].outputTimestamp = Date.now();
          s.loading.delete(outputKey);
          return s;
        });
        
        return output;
      } catch (error: any) {
        update(s => {
          s.loading.delete(outputKey);
          return s;
        });
        return cached?.output || null;
      }
    },
    
    async fetchAvailableHosts(): Promise<HostInfo[]> {
      try {
        const response = await api.get<HostInfo[]>('/api/hosts');
        update(s => {
          s.availableHosts = response.data;
          return s;
        });
        return response.data;
      } catch (error: any) {
        console.error('Failed to fetch hosts:', error);
        const state = get({ subscribe });
        return state.availableHosts;
      }
    },
    
    async fetchAllJobsProgressive(forceRefresh = false, filters?: any): Promise<void> {
      const state = get({ subscribe });
      
      // First, get the list of available hosts if we don't have it
      if (state.availableHosts.length === 0) {
        await this.fetchAvailableHosts();
      }
      
      const hosts = get({ subscribe }).availableHosts;
      if (hosts.length === 0) {
        return;
      }
      
      // Check if we need to refresh based on cache
      const hostsNeedingRefresh = forceRefresh 
        ? hosts 
        : hosts.filter(host => {
            const hostState = state.hostLoadingStates.get(host.hostname);
            return !hostState || Date.now() - hostState.lastFetch > 15000;
          });
      
      if (hostsNeedingRefresh.length === 0) {
        return; // All hosts have fresh data
      }
      
      // Build query parameters from filters
      const params = new URLSearchParams();
      if (filters) {
        Object.entries(filters).forEach(([key, value]) => {
          if (value !== null && value !== undefined && value !== '') {
            params.append(key, String(value));
          }
        });
      }
      
      // Start fetching from each host WITHOUT awaiting
      // This allows the UI to update progressively as each host responds
      hostsNeedingRefresh.forEach(host => {
        // Mark host as loading immediately
        update(s => {
          s.hostLoadingStates.set(host.hostname, {
            loading: true,
            lastFetch: s.hostLoadingStates.get(host.hostname)?.lastFetch || 0
          });
          return s;
        });
        
        // Build URL with host and other params
        const hostParams = new URLSearchParams(params);
        hostParams.append('host', host.hostname);
        
        // Fire the request without awaiting - let it update the store when ready
        api.get<JobStatusResponse[]>(`/api/status?${hostParams}`)
          .then(response => {
            const hostData = response.data[0]; // Should return single host data
            
            update(s => {
              if (hostData) {
                s.hostJobs.set(hostData.hostname, hostData);
                
                // Update individual job cache
                hostData.jobs.forEach(job => {
                  if (!job.hostname) {
                    job.hostname = hostData.hostname;
                  }
                  
                  const jobCacheKey = `${hostData.hostname}:${job.job_id}`;
                  if (!s.cache[jobCacheKey] || s.cache[jobCacheKey].timestamp < Date.now() - CACHE_DURATION) {
                    s.cache[jobCacheKey] = {
                      job,
                      timestamp: Date.now(),
                      output: s.cache[jobCacheKey]?.output,
                      outputTimestamp: s.cache[jobCacheKey]?.outputTimestamp,
                    };
                  }
                });
              }
              
              // Update host loading state
              s.hostLoadingStates.set(host.hostname, {
                loading: false,
                lastFetch: Date.now()
              });
              return s;
            });
          })
          .catch(error => {
            // Mark host as errored but don't fail the whole operation
            update(s => {
              s.hostLoadingStates.set(host.hostname, {
                loading: false,
                error: error.message || 'Failed to fetch jobs',
                lastFetch: s.hostLoadingStates.get(host.hostname)?.lastFetch || 0
              });
              return s;
            });
          });
      });
    },
    
    getCurrentJobs(): JobInfo[] {
      // Helper method to get current jobs from the store
      const state = get({ subscribe });
      const allJobs: JobInfo[] = [];
      state.hostJobs.forEach(hostData => {
        hostData.jobs.forEach(job => {
          if (!job.hostname) {
            job.hostname = hostData.hostname;
          }
          allJobs.push(job);
        });
      });
      return allJobs;
    },
    
    // Keep old method for backward compatibility
    async fetchAllJobs(forceRefresh = false, filters?: any): Promise<JobInfo[]> {
      // Start progressive fetching with filters
      await this.fetchAllJobsProgressive(forceRefresh, filters);
      // Return current jobs immediately (may be partial)
      return this.getCurrentJobs();
    },
    
    async fetchHostJobs(hostname?: string, filters?: any): Promise<JobStatusResponse[]> {
      const state = get({ subscribe });
      const cacheKey = hostname || 'all';
      const lastFetch = state.lastFetch.get(cacheKey) || 0;
      
      // Don't fetch if recently fetched (within 5 seconds) and we have the data we need
      const hasValidCache = hostname 
        ? state.hostJobs.has(hostname)
        : state.hostJobs.size > 0;
        
      if (Date.now() - lastFetch < 5000 && hasValidCache) {
        const result: JobStatusResponse[] = [];
        if (hostname && state.hostJobs.has(hostname)) {
          result.push(state.hostJobs.get(hostname)!);
        } else if (!hostname) {
          result.push(...state.hostJobs.values());
        }
        return result;
      }
      
      const params = new URLSearchParams();
      if (hostname) params.append('host', hostname);
      if (filters) {
        Object.entries(filters).forEach(([key, value]) => {
          if (value !== null && value !== undefined && value !== '') {
            params.append(key, String(value));
          }
        });
      }
      
      try {
        const response = await api.get<JobStatusResponse[]>(`/api/status?${params}`);
        const data = response.data;
        
        update(s => {
          // Update host jobs cache
          data.forEach(hostData => {
            s.hostJobs.set(hostData.hostname, hostData);
            
            // Update individual job cache
            hostData.jobs.forEach(job => {
              const jobCacheKey = `${hostData.hostname}:${job.job_id}`;
              if (!s.cache[jobCacheKey] || s.cache[jobCacheKey].timestamp < Date.now() - CACHE_DURATION) {
                s.cache[jobCacheKey] = {
                  job,
                  timestamp: Date.now(),
                  output: s.cache[jobCacheKey]?.output,
                  outputTimestamp: s.cache[jobCacheKey]?.outputTimestamp,
                };
              }
            });
          });
          
          s.lastFetch.set(cacheKey, Date.now());
          return s;
        });
        
        return data;
      } catch (error: any) {
        console.error('Failed to fetch jobs:', error);
        // Return cached data on error
        const result: JobStatusResponse[] = [];
        if (hostname && state.hostJobs.has(hostname)) {
          result.push(state.hostJobs.get(hostname)!);
        } else if (!hostname) {
          result.push(...state.hostJobs.values());
        }
        return result;
      }
    },
    
    updateJob(hostname: string, job: JobInfo) {
      update(s => {
        const cacheKey = `${hostname}:${job.job_id}`;
        s.cache[cacheKey] = {
          job,
          timestamp: Date.now(),
          output: s.cache[cacheKey]?.output,
          outputTimestamp: s.cache[cacheKey]?.outputTimestamp,
        };
        return s;
      });
    },
    
    clearCache() {
      set({
        cache: {},
        loading: new Set(),
        errors: new Map(),
        hostJobs: new Map(),
        hostLoadingStates: new Map(),
        lastFetch: new Map(),
        sidebarJobs: [],
        sidebarLastLoad: 0,
        availableHosts: [],
      });
    },
    
    getHostLoadingState(hostname: string): HostLoadingState | undefined {
      const state = get({ subscribe });
      return state.hostLoadingStates.get(hostname);
    },
    
    getAvailableHosts(): HostInfo[] {
      const state = get({ subscribe });
      return state.availableHosts;
    },
    
    isLoading(jobId: string, hostname: string): boolean {
      const state = get({ subscribe });
      const cacheKey = `${hostname}:${jobId}`;
      return state.loading.has(cacheKey);
    },
    
    getError(jobId: string, hostname: string): string | null {
      const state = get({ subscribe });
      const cacheKey = `${hostname}:${jobId}`;
      return state.errors.get(cacheKey) || null;
    },
    
    shouldLoadSidebar(): boolean {
      const state = get({ subscribe });
      // Load if never loaded or if more than 60 seconds have passed
      // Also load if we have no sidebar jobs cached
      return state.sidebarJobs.length === 0 || Date.now() - state.sidebarLastLoad > 60000;
    },
    
    async loadSidebarJobs(forceRefresh = false): Promise<void> {
      const state = get({ subscribe });
      
      // Skip if not forcing and we have recent data
      if (!forceRefresh && state.sidebarJobs.length > 0 && Date.now() - state.sidebarLastLoad < 60000) {
        return;
      }
      
      try {
        // Start progressive fetching (non-blocking)
        this.fetchAllJobsProgressive(forceRefresh || Date.now() - state.sidebarLastLoad > 15000);
        
        // Immediately update sidebar with current jobs (may be partial)
        const currentJobs = this.getCurrentJobs();
        
        // Sort by submit time (newest first)
        const sortedJobs = currentJobs.sort((a, b) => {
          const timeA = new Date(a.submit_time || 0).getTime();
          const timeB = new Date(b.submit_time || 0).getTime();
          return timeB - timeA;
        });
        
        // Update store with sorted jobs and timestamp
        update(s => {
          s.sidebarJobs = sortedJobs;
          s.sidebarLastLoad = Date.now();
          return s;
        });
      } catch (error) {
        console.error('Error loading sidebar jobs:', error);
      }
    },
    
    getSidebarJobs(): JobInfo[] {
      const state = get({ subscribe });
      return state.sidebarJobs;
    }
  };
}

export const jobsStore = createJobsStore();

// Derived store for all current jobs (updates automatically as hosts respond)
export const allCurrentJobs = derived(jobsStore, $state => {
  const allJobs: JobInfo[] = [];
  $state.hostJobs.forEach(hostData => {
    hostData.jobs.forEach(job => {
      if (!job.hostname) {
        job.hostname = hostData.hostname;
      }
      allJobs.push(job);
    });
  });
  
  // Sort by submit time (newest first)
  return allJobs.sort((a, b) => {
    const timeA = new Date(a.submit_time || 0).getTime();
    const timeB = new Date(b.submit_time || 0).getTime();
    return timeB - timeA;
  });
});

// Derived store for sidebar jobs (uses live current jobs)
export const sidebarJobs = derived(allCurrentJobs, $allJobs => {
  return {
    jobs: $allJobs,
    runningJobs: $allJobs.filter(j => j.state === 'R'),
    pendingJobs: $allJobs.filter(j => j.state === 'PD'),
    recentJobs: $allJobs.filter(j => j.state !== 'R' && j.state !== 'PD').slice(0, 50)
  };
});

// Derived store for getting a specific job
export function getJob(jobId: string, hostname: string) {
  return derived(jobsStore, $state => {
    const cacheKey = `${hostname}:${jobId}`;
    return $state.cache[cacheKey]?.job || null;
  });
}

// Derived store for checking if a job is loading
export function isJobLoading(jobId: string, hostname: string) {
  return derived(jobsStore, $state => {
    const cacheKey = `${hostname}:${jobId}`;
    return $state.loading.has(cacheKey);
  });
}

// Derived store for host loading states
export const hostLoadingStates = derived(jobsStore, $state => $state.hostLoadingStates);

// Derived store for available hosts
export const availableHosts = derived(jobsStore, $state => $state.availableHosts);

// Derived store to check if any host is still loading
export const isAnyHostLoading = derived(jobsStore, $state => {
  for (const [_, hostState] of $state.hostLoadingStates) {
    if (hostState.loading) return true;
  }
  return false;
});

// Derived store for host-specific jobs with loading state
export function getHostJobs(hostname: string) {
  return derived(jobsStore, $state => {
    const hostData = $state.hostJobs.get(hostname);
    const loadingState = $state.hostLoadingStates.get(hostname);
    return {
      jobs: hostData?.jobs || [],
      loading: loadingState?.loading || false,
      error: loadingState?.error,
      total: hostData?.total_jobs || 0
    };
  });
}