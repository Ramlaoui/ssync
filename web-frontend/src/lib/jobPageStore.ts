import { derived, writable, type Readable } from 'svelte/store';
import type { JobInfo, JobOutputResponse, JobScriptResponse } from '../types/api';
import { jobStateManager } from './JobStateManager';

/**
 * Optimized store for JobPage to eliminate complex reactive statements
 * and consolidate data flow
 */

// Job page parameters
export const jobPageParams = writable<{ id?: string; host?: string }>({});

// Current job derived from global job state
export const currentJob: Readable<JobInfo | null> = derived(
  [jobStateManager.getAllJobs(), jobPageParams],
  ([$allJobs, $params]) => {
    if (!$params.id || !$params.host) return null;
    return $allJobs.find(j => 
      j.job_id === $params.id && j.hostname === $params.host
    ) || null;
  }
);

// Tab-specific data stores
export const outputData = writable<JobOutputResponse | null>(null);
export const scriptData = writable<JobScriptResponse | null>(null);

// Loading states
export const loadingStates = writable({
  job: false,
  output: false,
  script: false,
  moreOutput: false
});

// Error states
export const errorStates = writable({
  job: null as string | null,
  output: null as string | null,
  script: null as string | null
});

// Active tab
export const activeTab = writable<'info' | 'output' | 'errors' | 'script'>('info');

// Progressive loading state
export const progressiveLoading = writable({
  loadedChunks: 0,
  hasMoreOutput: false,
  totalLines: 0
});

// Derived states for better performance
export const jobCanBeCancelled = derived(
  currentJob,
  ($currentJob) => $currentJob && ($currentJob.state === 'R' || $currentJob.state === 'PD')
);

export const jobIsActive = derived(
  currentJob,
  ($currentJob) => $currentJob && ($currentJob.state === 'R' || $currentJob.state === 'CG')
);

export const jobIsTerminal = derived(
  currentJob,
  ($currentJob) => $currentJob && ['CD', 'F', 'CA', 'TO'].includes($currentJob.state)
);

// Data loading coordination
export const shouldLoadOutput = derived(
  [currentJob, activeTab, outputData],
  ([$currentJob, $activeTab, $outputData]) => {
    if (!$currentJob) return false;
    if ($activeTab !== 'output' && $activeTab !== 'errors') return false;
    return !$outputData || $outputData.job_id !== $currentJob.job_id;
  }
);

export const shouldLoadScript = derived(
  [currentJob, activeTab, scriptData],
  ([$currentJob, $activeTab, $scriptData]) => {
    if (!$currentJob) return false;
    if ($activeTab !== 'script') return false;
    return !$scriptData || $scriptData.job_id !== $currentJob.job_id;
  }
);

// Combined loading state for UI
export const isLoading = derived(
  loadingStates,
  ($loadingStates) => Object.values($loadingStates).some(Boolean)
);

// Combined error state
export const hasError = derived(
  errorStates,
  ($errorStates) => Object.values($errorStates).some(Boolean)
);

// Reset functions
export function resetOutputData() {
  outputData.set(null);
  errorStates.update(state => ({ ...state, output: null }));
  progressiveLoading.set({ loadedChunks: 0, hasMoreOutput: false, totalLines: 0 });
}

export function resetScriptData() {
  scriptData.set(null);
  errorStates.update(state => ({ ...state, script: null }));
}

export function resetAllData() {
  outputData.set(null);
  scriptData.set(null);
  errorStates.set({ job: null, output: null, script: null });
  loadingStates.set({ job: false, output: false, script: false, moreOutput: false });
  progressiveLoading.set({ loadedChunks: 0, hasMoreOutput: false, totalLines: 0 });
}

// Helper to update loading state for specific operation
export function setLoadingState(operation: keyof typeof loadingStates, loading: boolean) {
  loadingStates.update(state => ({ ...state, [operation]: loading }));
}

// Helper to update error state for specific operation
export function setErrorState(operation: keyof typeof errorStates, error: string | null) {
  errorStates.update(state => ({ ...state, [operation]: error }));
}