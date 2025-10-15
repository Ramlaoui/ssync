<script lang="ts">
  import { run } from 'svelte/legacy';

  import { createEventDispatcher, onMount } from 'svelte';
  import type { JobInfo } from '../types/api';
  import { jobUtils } from '../lib/jobUtils';
  import { jobStateManager } from '../lib/JobStateManager';
  import { get } from 'svelte/store';
  import Dialog from '../lib/components/ui/Dialog.svelte';
  import { api } from '../services/api';

  interface Props {
    title?: string;
    description?: string;
    initialJobs?: JobInfo[];
    fetchJobsOnMount?: boolean;
    preSelectedJobId?: string | null;
    preSelectedHostname?: string | null;
    open?: boolean;
    allowMultiSelect?: boolean;
    includeCompletedJobs?: boolean; // Allow completed/canceled jobs for static watchers
  }

  let {
    title = "Select a Job",
    description = "Choose a job to attach watchers to",
    initialJobs = [],
    fetchJobsOnMount = true,
    preSelectedJobId = null,
    preSelectedHostname = null,
    open = $bindable(true),
    allowMultiSelect = false,
    includeCompletedJobs = false
  }: Props = $props();

  const dispatch = createEventDispatcher();

  let selectedJob: JobInfo | null = $state(null);
  let selectedJobs: JobInfo[] = $state([]);
  let searchTerm = $state('');
  let jobs: JobInfo[] = $state(initialJobs);
  let isLoading = $state(false);
  let watcherCounts: Map<string, number> = new Map();
  let activeTab: 'running' | 'other' = $state('running');  // Tab state

  // Subscribe to job updates
  const jobsStore = jobStateManager.getAllJobs();

  // Reactive subscription to job store - update jobs whenever store changes
  run(() => {
    const allJobs = $jobsStore;

    // Filter based on includeCompletedJobs flag
    const filteredJobs = includeCompletedJobs
      ? allJobs  // Show all jobs (including completed/canceled)
      : allJobs.filter(job => job.state === 'R' || job.state === 'PD');  // Only running/pending

    // Only update if we have new jobs or if jobs list is empty
    if (filteredJobs.length > 0 || (jobs.length === 0 && !isLoading)) {
      jobs = filteredJobs;
    }
  });

  // Separate jobs into running and other
  let runningJobs = $derived(jobs.filter(job => job.state === 'R' || job.state === 'PD'));
  let otherJobs = $derived(jobs.filter(job => job.state !== 'R' && job.state !== 'PD'));

  // Jobs to display based on active tab
  let displayJobs = $derived(activeTab === 'running' ? runningJobs : otherJobs);

  async function fetchWatcherCounts() {
    // Fetch watcher counts for all jobs
    try {
      const response = await api.get('/api/watchers');
      const allWatchers = response.data.watchers || [];

      // Count watchers per job
      const counts = new Map<string, number>();
      allWatchers.forEach((watcher: any) => {
        const jobKey = `${watcher.job_id}-${watcher.hostname}`;
        counts.set(jobKey, (counts.get(jobKey) || 0) + 1);
      });

      watcherCounts = counts;
    } catch (err) {
      console.error('Failed to fetch watcher counts:', err);
      // Don't fail the whole dialog if this fails
    }
  }

  function getWatcherCount(job: JobInfo): number {
    const jobKey = `${job.job_id}-${job.hostname}`;
    return watcherCounts.get(jobKey) || 0;
  }

  onMount(async () => {
    // Pre-select job if specified
    if (preSelectedJobId && preSelectedHostname) {
      const preSelected = jobs.find(job =>
        job.job_id === preSelectedJobId && job.hostname === preSelectedHostname
      );
      if (preSelected) {
        selectedJob = preSelected;
      }
    }

    // Fetch watcher counts in parallel
    fetchWatcherCounts();

    // Fetch fresh jobs in background if requested
    if (fetchJobsOnMount) {
      isLoading = true;
      try {
        await jobStateManager.syncAllHosts();

        // Try to pre-select again after fetching fresh jobs
        if (preSelectedJobId && preSelectedHostname && !selectedJob) {
          const allJobs = get(jobsStore);
          const preSelected = allJobs.find(job =>
            job.job_id === preSelectedJobId && job.hostname === preSelectedHostname
          );
          if (preSelected) {
            selectedJob = preSelected;
          }
        }
      } catch (err) {
        console.error('Failed to fetch fresh jobs:', err);
      } finally {
        isLoading = false;
      }
    }
  });

  // Filter jobs based on search (apply to displayJobs from active tab)
  let filteredJobs = $derived(displayJobs.filter(job => {
    if (!searchTerm) return true;
    const search = searchTerm.toLowerCase();
    return (
      job.job_id.toLowerCase().includes(search) ||
      job.hostname.toLowerCase().includes(search) ||
      job.name?.toLowerCase().includes(search) ||
      job.partition?.toLowerCase().includes(search)
    );
  }));

  // Group jobs by hostname
  let jobsByHost = $derived(filteredJobs.reduce((acc, job) => {
    if (!acc[job.hostname]) {
      acc[job.hostname] = [];
    }
    acc[job.hostname].push(job);
    return acc;
  }, {} as Record<string, JobInfo[]>));

  // Sort hosts alphabetically
  let sortedHosts = $derived(Object.keys(jobsByHost).sort());

  function switchTab(tab: 'running' | 'other') {
    activeTab = tab;
    // Clear search when switching tabs for better UX
    searchTerm = '';
  }
  
  function selectJob(job: JobInfo) {
    if (allowMultiSelect) {
      // Multi-select mode: toggle job in array
      const jobKey = `${job.job_id}-${job.hostname}`;
      const existingIndex = selectedJobs.findIndex(j =>
        `${j.job_id}-${j.hostname}` === jobKey
      );

      if (existingIndex >= 0) {
        selectedJobs = selectedJobs.filter((_, i) => i !== existingIndex);
      } else {
        selectedJobs = [...selectedJobs, job];
      }
    } else {
      // Single select mode
      selectedJob = job;
    }
  }

  function isJobSelected(job: JobInfo): boolean {
    if (allowMultiSelect) {
      const jobKey = `${job.job_id}-${job.hostname}`;
      return selectedJobs.some(j => `${j.job_id}-${j.hostname}` === jobKey);
    } else {
      return selectedJob === job;
    }
  }

  function selectAll() {
    selectedJobs = [...filteredJobs];
  }

  function clearSelection() {
    selectedJobs = [];
  }

  function handleConfirm(action: 'apply' | 'edit' = 'apply') {
    if (allowMultiSelect) {
      if (selectedJobs.length > 0) {
        // For multi-select, wrap the jobs array with metadata
        const payload = {
          jobs: selectedJobs,
          action: action
        };
        dispatch('select', payload);
      }
    } else {
      if (selectedJob) {
        dispatch('select', selectedJob);
      }
    }
  }
  
  function handleClose() {
    open = false;
    dispatch('close');
  }

  function formatJobState(state: string): string {
    const states: Record<string, string> = {
      'R': 'Running',
      'PD': 'Pending',
      'CG': 'Completing',
      'CD': 'Completed',
      'F': 'Failed',
      'TO': 'Timeout',
      'CA': 'Cancelled'
    };
    return states[state] || state;
  }
  
  // Use centralized job utilities
  
  function formatTime(dateString: string | undefined): string {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return `${Math.floor(diff / 86400000)}d ago`;
  }
  
</script>

<Dialog
  bind:open
  on:close={handleClose}
  {title}
  {description}
  size="xl"
  contentClass="job-selection-content"
>
      {#if isLoading && jobs.length === 0}
        <div class="loading-state">
          <div class="spinner"></div>
          <h3>Loading Jobs...</h3>
          <p>Fetching jobs from all hosts</p>
        </div>
      {:else if jobs.length === 0}
        <div class="empty-state">
          <svg viewBox="0 0 24 24" fill="currentColor" class="empty-icon">
            <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M14,6L8,18H10L16,6H14Z"/>
          </svg>
          <h3>No Jobs Available</h3>
          <p>There are no jobs to attach watchers to.</p>
        </div>
      {:else}
        <!-- Tab navigation (only show if includeCompletedJobs is true) -->
        {#if includeCompletedJobs}
          <div class="tabs-container">
            <button
              type="button"
              class="tab-button"
              class:active={activeTab === 'running'}
              onclick={() => switchTab('running')}
            >
              <svg viewBox="0 0 24 24" fill="currentColor" class="tab-icon">
                <path d="M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2M12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4M10,16.5L16,12L10,7.5V16.5Z"/>
              </svg>
              Running
              <span class="tab-count">{runningJobs.length}</span>
            </button>
            <button
              type="button"
              class="tab-button"
              class:active={activeTab === 'other'}
              onclick={() => switchTab('other')}
            >
              <svg viewBox="0 0 24 24" fill="currentColor" class="tab-icon">
                <path d="M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2M12,4A8,8 0 0,0 4,12C4,13.85 4.63,15.55 5.68,16.91L16.91,5.68C15.55,4.63 13.85,4 12,4M12,20A8,8 0 0,0 20,12C20,10.15 19.37,8.45 18.32,7.09L7.09,18.32C8.45,19.37 10.15,20 12,20Z"/>
              </svg>
              Completed / Canceled
              <span class="tab-count">{otherJobs.length}</span>
            </button>
          </div>
        {/if}

        <!-- Search bar and multi-select controls -->
        <div class="search-container">
          <div class="search-bar">
            <svg viewBox="0 0 24 24" fill="currentColor" class="search-icon">
              <path d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z"/>
            </svg>
            <input
              type="text"
              placeholder="Search by job ID, name, host, or partition..."
              bind:value={searchTerm}
              class="search-input"
            />
            {#if isLoading}
              <div class="loading-indicator">
                <div class="small-spinner"></div>
                <span>Updating...</span>
              </div>
            {/if}
          </div>

          {#if allowMultiSelect && filteredJobs.length > 0}
            <div class="multi-select-controls">
              <span class="selection-count">{selectedJobs.length} of {filteredJobs.length} selected</span>
              <div class="control-buttons">
                <button
                  type="button"
                  onclick={selectAll}
                  class="control-button"
                  disabled={selectedJobs.length === filteredJobs.length}
                >
                  Select All
                </button>
                <button
                  type="button"
                  onclick={clearSelection}
                  class="control-button"
                  disabled={selectedJobs.length === 0}
                >
                  Clear
                </button>
              </div>
            </div>
          {/if}
        </div>
        
        <!-- Jobs list -->
        <div class="jobs-list">
          {#if filteredJobs.length === 0}
            <div class="no-results">
              {#if searchTerm}
                <p>No jobs match your search criteria</p>
              {:else if includeCompletedJobs && activeTab === 'running'}
                <p>No running or pending jobs available</p>
                <p class="hint">Try the "Completed / Canceled" tab to create static watchers</p>
              {:else if includeCompletedJobs && activeTab === 'other'}
                <p>No completed or canceled jobs available</p>
                <p class="hint">Try the "Running" tab to create active watchers</p>
              {:else}
                <p>No jobs available</p>
              {/if}
            </div>
          {:else}
            {#each sortedHosts as hostname}
              <div class="host-group">
                <div class="host-header">
                  <span class="host-name">{hostname}</span>
                  <span class="job-count">{jobsByHost[hostname].length} job{jobsByHost[hostname].length !== 1 ? 's' : ''}</span>
                </div>
                
                <div class="host-jobs">
                  {#each jobsByHost[hostname] as job}
                    <button
                      class="job-item"
                      class:selected={isJobSelected(job)}
                      onclick={() => selectJob(job)}
                    >
                      <div class="job-main">
                        <div class="job-header">
                          <span class="job-id">#{job.job_id}</span>
                          <span 
                            class="job-state"
                            style="background-color: {jobUtils.getStateColor(job.state)}20; color: {jobUtils.getStateColor(job.state)}"
                          >
                            {formatJobState(job.state)}
                          </span>
                        </div>
                        
                        <div class="job-name">
                          {job.name || 'Unnamed Job'}
                        </div>
                        
                        <div class="job-details">
                          {#if job.partition}
                            <span class="detail-item">
                              <svg viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M12,6A6,6 0 0,0 6,12A6,6 0 0,0 12,18A6,6 0 0,0 18,12A6,6 0 0,0 12,6M12,8A4,4 0 0,1 16,12A4,4 0 0,1 12,16A4,4 0 0,1 8,12A4,4 0 0,1 12,8Z"/>
                              </svg>
                              {job.partition}
                            </span>
                          {/if}

                          {#if job.nodes}
                            <span class="detail-item">
                              <svg viewBox="0 0 24 24" fill="currentColor">
                                <path d="M3,3H21V7H3V3M4,8H20V21H4V8M9.5,11A0.5,0.5 0 0,0 9,11.5V13H15V11.5A0.5,0.5 0 0,0 14.5,11H9.5Z"/>
                              </svg>
                              {job.nodes} node{job.nodes > 1 ? 's' : ''}
                            </span>
                          {/if}

                          <span class="detail-item">
                            <svg viewBox="0 0 24 24" fill="currentColor">
                              <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M16.2,16.2L11,13V7H12.5V12.2L17,14.9L16.2,16.2Z"/>
                            </svg>
                            {formatTime(job.submit_time)}
                          </span>

                          {#if getWatcherCount(job) > 0}
                            <span class="detail-item watcher-count" title="{getWatcherCount(job)} watcher{getWatcherCount(job) !== 1 ? 's' : ''} attached">
                              <svg viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5M12,17C9.24,17 7,14.76 7,12C7,9.24 9.24,7 12,7C14.76,7 17,9.24 17,12C17,14.76 14.76,17 12,17M12,9C10.34,9 9,10.34 9,12C9,13.66 10.34,15 12,15C13.66,15 15,13.66 15,12C15,10.34 13.66,9 12,9Z"/>
                              </svg>
                              {getWatcherCount(job)} watcher{getWatcherCount(job) !== 1 ? 's' : ''}
                            </span>
                          {/if}
                        </div>
                      </div>

                      {#if isJobSelected(job)}
                        <div class="selected-indicator">
                          <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z"/>
                          </svg>
                        </div>
                      {/if}
                    </button>
                  {/each}
                </div>
              </div>
            {/each}
          {/if}
        </div>
      {/if}

  {#snippet footer()}
    <div  class="selection-footer">
      <button
        type="button"
        onclick={handleClose}
        class="cancel-btn"
      >
        Cancel
      </button>
      {#if allowMultiSelect && selectedJobs.length > 1}
        <!-- Multi-select with multiple jobs: show both options -->
        <button
          type="button"
          onclick={() => handleConfirm('edit')}
          class="edit-btn-footer"
          title="Edit watcher configuration before applying to all jobs"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" class="w-4 h-4">
            <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
          </svg>
          Edit & Apply to {selectedJobs.length} Jobs
        </button>
        <button
          type="button"
          onclick={() => handleConfirm('apply')}
          class="confirm-btn"
          title="Apply watcher as-is to all selected jobs"
        >
          Apply to {selectedJobs.length} Jobs
        </button>
      {:else}
        <!-- Single select or multi-select with 0-1 jobs -->
        <button
          type="button"
          onclick={() => handleConfirm('apply')}
          disabled={allowMultiSelect ? selectedJobs.length === 0 : !selectedJob}
          class="confirm-btn"
        >
          {#if allowMultiSelect}
            Select {selectedJobs.length} Job{selectedJobs.length !== 1 ? 's' : ''}
          {:else}
            Select Job
          {/if}
        </button>
      {/if}
    </div>
  {/snippet}
</Dialog>

<style>
  :global(.job-selection-content) {
    padding: 1.5rem !important;
    min-height: 200px;
  }
  
  /* Empty state */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    text-align: center;
  }
  
  .empty-icon {
    width: 64px;
    height: 64px;
    color: #d1d5db;
    margin-bottom: 1rem;
  }
  
  .empty-state h3 {
    margin: 0 0 0.5rem 0;
    font-size: 1.25rem;
    color: #374151;
  }
  
  .empty-state p {
    margin: 0;
    color: #6b7280;
    font-size: 0.875rem;
  }

  /* Loading state */
  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    text-align: center;
  }

  .loading-state h3 {
    margin: 1rem 0 0.5rem 0;
    font-size: 1.25rem;
    color: #374151;
  }

  .loading-state p {
    margin: 0;
    color: #6b7280;
    font-size: 0.875rem;
  }

  .spinner {
    width: 48px;
    height: 48px;
    border: 4px solid #e5e7eb;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  .small-spinner {
    width: 16px;
    height: 16px;
    border: 2px solid #e5e7eb;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .loading-indicator {
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.75rem;
    color: #6b7280;
  }

  /* Tabs */
  .tabs-container {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 0;
  }

  .tab-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: #6b7280;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    position: relative;
    bottom: -1px;
  }

  .tab-button:hover {
    color: #374151;
    background: #f9fafb;
  }

  .tab-button.active {
    color: #3b82f6;
    border-bottom-color: #3b82f6;
  }

  .tab-icon {
    width: 18px;
    height: 18px;
  }

  .tab-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 1.5rem;
    height: 1.5rem;
    padding: 0 0.375rem;
    background: #f3f4f6;
    color: #6b7280;
    border-radius: 0.75rem;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .tab-button.active .tab-count {
    background: #dbeafe;
    color: #3b82f6;
  }

  /* Search container */
  .search-container {
    margin-bottom: 1.5rem;
  }

  /* Search bar */
  .search-bar {
    position: relative;
    margin-bottom: 0.75rem;
  }
  
  .search-icon {
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    width: 20px;
    height: 20px;
    color: #9ca3af;
  }
  
  .search-input {
    width: 100%;
    padding: 0.75rem 0.75rem 0.75rem 44px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 0.875rem;
    transition: border-color 0.2s;
  }
  
  .search-input:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  /* Multi-select controls */
  .multi-select-controls {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
  }

  .selection-count {
    font-size: 0.875rem;
    color: #374151;
    font-weight: 500;
  }

  .control-buttons {
    display: flex;
    gap: 0.5rem;
  }

  .control-button {
    padding: 0.375rem 0.75rem;
    font-size: 0.75rem;
    border: 1px solid #d1d5db;
    background: white;
    color: #374151;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    font-weight: 500;
  }

  .control-button:hover:not(:disabled) {
    background: #f3f4f6;
    border-color: #9ca3af;
  }

  .control-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* Jobs list */
  .jobs-list {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .no-results {
    text-align: center;
    padding: 2rem;
    color: #6b7280;
  }

  .no-results p {
    margin: 0.5rem 0;
  }

  .no-results .hint {
    font-size: 0.875rem;
    color: #9ca3af;
    font-style: italic;
  }
  
  .host-group {
    background: #f9fafb;
    border-radius: 8px;
    overflow: hidden;
  }
  
  .host-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: #f3f4f6;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .host-name {
    font-weight: 600;
    color: #374151;
    font-size: 0.875rem;
  }
  
  .job-count {
    font-size: 0.75rem;
    color: #6b7280;
    background: white;
    padding: 0.25rem 0.5rem;
    border-radius: 12px;
  }
  
  .host-jobs {
    padding: 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .job-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    text-align: left;
    width: 100%;
  }
  
  .job-item:hover {
    border-color: #3b82f6;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
  }
  
  .job-item.selected {
    border-color: #3b82f6;
    background: #eff6ff;
  }
  
  .job-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .job-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  
  .job-id {
    font-weight: 600;
    color: #1f2937;
    font-size: 0.9rem;
  }
  
  .job-state {
    padding: 0.25rem 0.5rem;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
  }
  
  .job-name {
    color: #374151;
    font-size: 0.875rem;
  }
  
  .job-details {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
  }
  
  .detail-item {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: #6b7280;
  }
  
  .detail-item svg {
    width: 14px;
    height: 14px;
    opacity: 0.5;
  }

  .detail-item.watcher-count {
    color: #3b82f6;
    font-weight: 500;
    background: #eff6ff;
    padding: 0.25rem 0.5rem;
    border-radius: 12px;
  }

  .detail-item.watcher-count svg {
    opacity: 1;
    color: #3b82f6;
  }

  .selected-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: #3b82f6;
    border-radius: 50%;
    color: white;
  }
  
  .selected-indicator svg {
    width: 20px;
    height: 20px;
  }
  
  /* Footer */
  .selection-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    width: 100%;
  }
  
  .cancel-btn,
  .confirm-btn,
  .edit-btn-footer {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .cancel-btn {
    background: white;
    color: #374151;
    border: 1px solid #d1d5db;
  }

  .cancel-btn:hover {
    background: #f3f4f6;
  }

  .edit-btn-footer {
    background: white;
    color: #3b82f6;
    border: 1px solid #3b82f6;
  }

  .edit-btn-footer:hover {
    background: #eff6ff;
  }

  .confirm-btn {
    background: #3b82f6;
    color: white;
  }

  .confirm-btn:hover:not(:disabled) {
    background: #2563eb;
  }

  .confirm-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  @media (max-width: 640px) {
    :global(.job-selection-content) {
      padding: 1rem !important;
    }

    .job-details {
      flex-direction: column;
      gap: 0.5rem;
    }
  }
</style>