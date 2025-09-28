import { writable, derived, get } from 'svelte/store';
import type { JobInfo, JobStatusResponse, JobOutputResponse, HostInfo } from '../types/api';
import { api } from '../services/api';
import { batchedUpdates } from '../lib/BatchedUpdates';

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

// Intelligent cache durations based on job state
const CACHE_DURATIONS = {
  // Completed jobs change rarely - cache for longer
  COMPLETED: 300000,    // 5 minutes for completed/failed/cancelled jobs
  STABLE: 120000,       // 2 minutes for stable running jobs
  ACTIVE: 60000,        // 1 minute for active/pending jobs
  DEFAULT: 60000        // 1 minute default
};

const OUTPUT_CACHE_DURATIONS = {
  // Output caching based on job state
  COMPLETED: 180000,    // 3 minutes for completed jobs
  RUNNING: 30000,       // 30 seconds for running jobs
  DEFAULT: 60000        // 1 minute default
};

// Helper function to get appropriate cache duration based on job state
function getCacheDuration(job?: JobInfo): number {
  if (!job) return CACHE_DURATIONS.DEFAULT;
  
  const state = job.state;
  switch (state) {
    case 'CD': // Completed
    case 'F':  // Failed
    case 'CA': // Cancelled
    case 'TO': // Timeout
      return CACHE_DURATIONS.COMPLETED;
    case 'R':  // Running
      // For running jobs, check runtime to determine stability
      if (job.runtime && job.runtime !== 'N/A') {
        const runtimeParts = job.runtime.split(':');
        if (runtimeParts.length >= 2) {
          const minutes = parseInt(runtimeParts[runtimeParts.length - 2]);
          if (minutes > 30) { // Running for more than 30 minutes = stable
            return CACHE_DURATIONS.STABLE;
          }
        }
      }
      return CACHE_DURATIONS.ACTIVE;
    case 'PD': // Pending
    default:
      return CACHE_DURATIONS.ACTIVE;
  }
}

function getOutputCacheDuration(job?: JobInfo): number {
  if (!job) return OUTPUT_CACHE_DURATIONS.DEFAULT;
  
  const state = job.state;
  switch (state) {
    case 'CD': // Completed
    case 'F':  // Failed
    case 'CA': // Cancelled
    case 'TO': // Timeout
      return OUTPUT_CACHE_DURATIONS.COMPLETED;
    case 'R':  // Running
      return OUTPUT_CACHE_DURATIONS.RUNNING;
    default:
      return OUTPUT_CACHE_DURATIONS.DEFAULT;
  }
}

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

  // Register batched update callback for job store updates
  batchedUpdates.registerCallback('jobs-store', (updates) => {
    // Process all updates in a single store update
    update(state => {
      for (const updateItem of updates) {
        if (updateItem.type === 'job_update' && updateItem.jobId && updateItem.hostname) {
          const cacheKey = `${updateItem.hostname}:${updateItem.jobId}`;
          const existingCache = state.cache[cacheKey];
          const cacheDuration = getCacheDuration(updateItem.data);
          
          // Update cache
          state.cache[cacheKey] = {
            job: updateItem.data,
            timestamp: Date.now(),
            output: existingCache?.output,
            outputTimestamp: existingCache?.outputTimestamp,
          };
          
          // Update host jobs if needed
          const hostData = state.hostJobs.get(updateItem.hostname);
          if (hostData) {
            const jobIndex = hostData.jobs.findIndex(j => j.job_id === updateItem.jobId);
            if (jobIndex >= 0) {
              hostData.jobs[jobIndex] = updateItem.data;
            } else {
              hostData.jobs.push(updateItem.data);
            }
            state.hostJobs.set(updateItem.hostname, { ...hostData });
          }
        } else if (updateItem.type === 'host_jobs_update' && updateItem.hostname) {
          // Update entire host job list
          const jobs = updateItem.data;
          const existingHostData = state.hostJobs.get(updateItem.hostname);
          
          state.hostJobs.set(updateItem.hostname, {
            hostname: updateItem.hostname,
            jobs,
            total_jobs: jobs.length,
            query_time: new Date().toISOString(),
            cached: existingHostData?.cached || false
          });
        }
      }
      return state;
    });
  });

  return {
    subscribe,
    
    async fetchJob(jobId: string, hostname: string, forceRefresh = false): Promise<JobInfo | null> {
      const state = get({ subscribe });
      const cacheKey = `${hostname}:${jobId}`;
      const cached = state.cache[cacheKey];
      
      // Get intelligent cache duration based on job state
      const cacheDuration = getCacheDuration(cached?.job);
      
      // Return cached job if still valid and not forcing refresh
      if (!forceRefresh && cached && Date.now() - cached.timestamp < cacheDuration) {
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
      
      // Get intelligent cache duration for output based on job state
      const outputCacheDuration = getOutputCacheDuration(cached?.job);
      
      // Return cached output if still valid
      if (!forceRefresh && cached?.output && cached.outputTimestamp && 
          Date.now() - cached.outputTimestamp < outputCacheDuration) {
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
        const hosts = response.data || [];
        update(s => {
          s.availableHosts = hosts;
          return s;
        });
        console.log(`Loaded ${hosts.length} hosts`);
        return hosts;
      } catch (error: any) {
        console.error('Failed to fetch hosts:', error);
        // Try to return cached hosts if available
        const state = get({ subscribe });
        if (state.availableHosts.length > 0) {
          console.log('Using cached hosts:', state.availableHosts.length);
          return state.availableHosts;
        }
        // Return empty array instead of undefined
        return [];
      }
    },
    
    async fetchAllJobsProgressive(forceRefresh = false, filters?: any): Promise<void> {
      const state = get({ subscribe });

      // First, get the list of available hosts if we don't have it
      if (state.availableHosts.length === 0) {
        console.log('No hosts cached, fetching...');
        await this.fetchAvailableHosts();
      }

      const hosts = get({ subscribe }).availableHosts;
      if (hosts.length === 0) {
        console.warn('No hosts available to fetch jobs from');
        return;
      }

      console.log(`Fetching jobs from ${hosts.length} hosts${forceRefresh ? ' (forced refresh)' : ''}`);

      // Force refresh clears cache and fetches all hosts
      if (forceRefresh) {
        // Clear cache for all hosts to ensure fresh data
        update(s => {
          s.cache = {};
          s.hostLoadingStates.forEach((state, hostname) => {
            state.lastFetch = 0; // Reset last fetch time
          });
          return s;
        });
      }

      // Check if we need to refresh based on cache (intelligent cache time)
      const hostsNeedingRefresh = forceRefresh
        ? hosts
        : hosts.filter(host => {
            const hostState = state.hostLoadingStates.get(host.hostname);
            // Use intelligent cache duration based on whether host has errors
            const cacheTimeout = hostState?.error ? 10000 : 60000;  // 10s if error, 60s normally
            return !hostState || Date.now() - hostState.lastFetch > cacheTimeout;
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
                
                // Update individual job cache with intelligent duration
                hostData.jobs.forEach(job => {
                  if (!job.hostname) {
                    job.hostname = hostData.hostname;
                  }
                  
                  const jobCacheKey = `${hostData.hostname}:${job.job_id}`;
                  const cacheDuration = getCacheDuration(job);
                  const existingCache = s.cache[jobCacheKey];
                  
                  // Only update cache if it doesn't exist or is expired
                  if (!existingCache || existingCache.timestamp < Date.now() - cacheDuration) {
                    s.cache[jobCacheKey] = {
                      job,
                      timestamp: Date.now(),
                      output: existingCache?.output,
                      outputTimestamp: existingCache?.outputTimestamp,
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
            // Mark host as errored but preserve existing job data
            update(s => {
              const existingJobs = s.hostJobs.get(host.hostname);
              
              // Keep existing jobs data if we have it (stale data is better than no data)
              if (existingJobs && existingJobs.jobs.length > 0) {
                // Mark data as potentially stale but keep it
                s.hostJobs.set(host.hostname, {
                  ...existingJobs,
                  cached: true,  // Mark as cached/stale
                  query_time: existingJobs.query_time  // Keep original query time
                });
              }
              
              s.hostLoadingStates.set(host.hostname, {
                loading: false,
                error: error.message || 'Failed to fetch jobs',
                lastFetch: Date.now()  // Update lastFetch to retry sooner (10s timeout)
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
      try {
        // Start progressive fetching with filters
        await this.fetchAllJobsProgressive(forceRefresh, filters);
      } catch (error) {
        console.error('Error fetching jobs:', error);
      }
      // Return current jobs immediately (may be partial or empty)
      const jobs = this.getCurrentJobs();
      console.log(`fetchAllJobs returning ${jobs.length} jobs`);
      return jobs;
    },
    
    async fetchHostJobs(hostname?: string, filters?: any): Promise<JobStatusResponse[]> {
      const state = get({ subscribe });
      const cacheKey = hostname || 'all';
      const lastFetch = state.lastFetch.get(cacheKey) || 0;
      
      // Don't fetch if recently fetched (intelligent timeout) and we have the data we need
      const hasValidCache = hostname 
        ? state.hostJobs.has(hostname)
        : state.hostJobs.size > 0;
        
      if (Date.now() - lastFetch < 30000 && hasValidCache) {
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
            
            // Update individual job cache with intelligent duration
            hostData.jobs.forEach(job => {
              const jobCacheKey = `${hostData.hostname}:${job.job_id}`;
              const cacheDuration = getCacheDuration(job);
              const existingCache = s.cache[jobCacheKey];
              
              // Only update cache if it doesn't exist or is expired
              if (!existingCache || existingCache.timestamp < Date.now() - cacheDuration) {
                s.cache[jobCacheKey] = {
                  job,
                  timestamp: Date.now(),
                  output: existingCache?.output,
                  outputTimestamp: existingCache?.outputTimestamp,
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
      // Use batched updates instead of immediate store update
      batchedUpdates.queueJobUpdate(job.job_id, hostname, job, 'job_update');
    },
    
    updateJobCache(job: JobInfo, hostname: string) {
      // Use batched updates to prevent excessive re-renders
      // Determine if this is a state change or just a regular update
      const existingJob = get({ subscribe }).cache[`${hostname}:${job.job_id}`]?.job;
      const isStateChange = existingJob && existingJob.state !== job.state;
      
      batchedUpdates.queueJobUpdate(
        job.job_id, 
        hostname, 
        job, 
        isStateChange ? 'job_state_change' : 'job_update'
      );
    },
    
    async refreshHost(hostname: string): Promise<void> {
      // Force refresh a specific host
      update(s => {
        // Clear cache for this host's jobs
        Object.keys(s.cache).forEach(key => {
          if (key.startsWith(`${hostname}:`)) {
            delete s.cache[key];
          }
        });
        // Reset last fetch time to force refresh
        const hostState = s.hostLoadingStates.get(hostname);
        if (hostState) {
          hostState.lastFetch = 0;
        }
        return s;
      });

      // Now fetch the host's jobs
      const params = new URLSearchParams();
      params.append('host', hostname);

      update(s => {
        s.hostLoadingStates.set(hostname, {
          loading: true,
          lastFetch: s.hostLoadingStates.get(hostname)?.lastFetch || 0
        });
        return s;
      });

      try {
        const response = await api.get<JobStatusResponse[]>(`/api/status?${params}`);
        const hostData = response.data[0];

        update(s => {
          if (hostData) {
            s.hostJobs.set(hostData.hostname, hostData);

            // Update individual job cache
            hostData.jobs.forEach(job => {
              if (!job.hostname) {
                job.hostname = hostData.hostname;
              }

              const jobCacheKey = `${hostData.hostname}:${job.job_id}`;
              s.cache[jobCacheKey] = {
                job,
                timestamp: Date.now(),
                output: s.cache[jobCacheKey]?.output,
                outputTimestamp: s.cache[jobCacheKey]?.outputTimestamp,
              };
            });
          }

          // Update host loading state
          s.hostLoadingStates.set(hostname, {
            loading: false,
            lastFetch: Date.now()
          });
          return s;
        });
      } catch (error: any) {
        update(s => {
          s.hostLoadingStates.set(hostname, {
            loading: false,
            error: error.message || 'Failed to fetch jobs',
            lastFetch: Date.now()
          });
          return s;
        });
      }
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
      
      // Skip if not forcing and we have recent data (increased cache time)
      if (!forceRefresh && state.sidebarJobs.length > 0 && Date.now() - state.sidebarLastLoad < 120000) {
        return;
      }
      
      try {
        // Start progressive fetching (non-blocking) - increased threshold from 15s to 45s
        this.fetchAllJobsProgressive(forceRefresh || Date.now() - state.sidebarLastLoad > 45000);
        
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