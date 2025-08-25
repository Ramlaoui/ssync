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
    
    async fetchHostJobs(hostname?: string, filters?: any): Promise<JobStatusResponse[]> {
      const state = get({ subscribe });
      const cacheKey = hostname || 'all';
      const lastFetch = state.lastFetch.get(cacheKey) || 0;
      
      // Don't fetch if recently fetched (within 5 seconds)
      if (Date.now() - lastFetch < 5000) {
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
    }
  };
}

export const jobsStore = createJobsStore();

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