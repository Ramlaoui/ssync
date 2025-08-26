import { writable, derived, get } from 'svelte/store';
import type { JobInfo, JobStatusResponse, JobOutputResponse } from '../types/api';
import { api } from '../services/api';

interface JobCache {
  [key: string]: {
    job: JobInfo;
    timestamp: number;
    output?: JobOutputResponse;
    outputTimestamp?: number;
  };
}

interface JobsState {
  cache: JobCache;
  loading: Set<string>;
  errors: Map<string, string>;
  hostJobs: Map<string, JobStatusResponse>;
  lastFetch: Map<string, number>;
  sidebarLastLoad: number;
  sidebarJobs: JobInfo[];
}

const CACHE_DURATION = 30000; // 30 seconds cache for individual jobs
const OUTPUT_CACHE_DURATION = 10000; // 10 seconds for output cache

function createJobsStore() {
  const { subscribe, update, set } = writable<JobsState>({
    cache: {},
    loading: new Set(),
    errors: new Map(),
    hostJobs: new Map(),
    lastFetch: new Map(),
    sidebarLastLoad: 0,
    sidebarJobs: [],
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
        const response = await api.get<JobOutputResponse>(`/api/jobs/${jobId}/output?host=${hostname}`);
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
    
    async fetchAllJobs(forceRefresh = false): Promise<JobInfo[]> {
      const state = get({ subscribe });
      const cacheKey = 'allJobs';
      const lastFetch = state.lastFetch.get(cacheKey) || 0;
      
      // Don't fetch if recently fetched (within 15 seconds) unless forcing refresh
      if (!forceRefresh && Date.now() - lastFetch < 15000) {
        const allJobs: JobInfo[] = [];
        state.hostJobs.forEach(hostData => {
          hostData.jobs.forEach(job => {
            // Ensure hostname is set
            if (!job.hostname) {
              job.hostname = hostData.hostname;
            }
            allJobs.push(job);
          });
        });
        return allJobs;
      }
      
      try {
        const response = await api.get<JobStatusResponse[]>('/api/status');
        const allJobs: JobInfo[] = [];
        
        update(s => {
          // Update host jobs cache
          response.data.forEach(hostData => {
            s.hostJobs.set(hostData.hostname, hostData);
            
            // Collect all jobs and update individual cache
            hostData.jobs.forEach(job => {
              // Ensure hostname is set
              if (!job.hostname) {
                job.hostname = hostData.hostname;
              }
              allJobs.push(job);
              
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
        
        return allJobs;
      } catch (error: any) {
        console.error('Failed to fetch all jobs:', error);
        // Return cached data on error
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
      }
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
        lastFetch: new Map(),
      });
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
        // Fetch all jobs with force refresh
        const allJobs = await this.fetchAllJobs(forceRefresh || Date.now() - state.sidebarLastLoad > 15000);
        
        // Sort by submit time (newest first)
        const sortedJobs = allJobs.sort((a, b) => {
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

// Derived store for sidebar jobs
export const sidebarJobs = derived(jobsStore, $state => {
  return {
    jobs: $state.sidebarJobs,
    runningJobs: $state.sidebarJobs.filter(j => j.state === 'R'),
    pendingJobs: $state.sidebarJobs.filter(j => j.state === 'PD'),
    recentJobs: $state.sidebarJobs.filter(j => j.state !== 'R' && j.state !== 'PD').slice(0, 50)
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