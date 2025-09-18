<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import type { JobInfo } from '../types/api';
  import { jobUtils } from '../lib/jobUtils';
  import { jobStateManager } from '../lib/JobStateManager';
  import { get } from 'svelte/store';

  export let title = "Select a Job";
  export let description = "Choose a job to attach watchers to";
  export let initialJobs: JobInfo[] = [];
  export let fetchJobsOnMount = true;

  const dispatch = createEventDispatcher();
  
  let selectedJob: JobInfo | null = null;
  let searchTerm = '';
  let jobs: JobInfo[] = initialJobs;
  let isLoading = false;

  // Subscribe to job updates
  const jobsStore = jobStateManager.getAllJobs();

  // Reactive subscription to job store - update jobs whenever store changes
  $: {
    const allJobs = $jobsStore;
    const runningJobs = allJobs.filter(job => job.state === 'R' || job.state === 'PD');
    // Only update if we have new jobs or if jobs list is empty
    if (runningJobs.length > 0 || (jobs.length === 0 && !isLoading)) {
      jobs = runningJobs;
    }
  }

  onMount(async () => {
    // Fetch fresh jobs in background if requested
    if (fetchJobsOnMount) {
      isLoading = true;
      try {
        await jobStateManager.syncAllHosts();
      } catch (err) {
        console.error('Failed to fetch fresh jobs:', err);
      } finally {
        isLoading = false;
      }
    }
  });

  // Filter jobs based on search
  $: filteredJobs = jobs.filter(job => {
    if (!searchTerm) return true;
    const search = searchTerm.toLowerCase();
    return (
      job.job_id.toLowerCase().includes(search) ||
      job.hostname.toLowerCase().includes(search) ||
      job.name?.toLowerCase().includes(search) ||
      job.partition?.toLowerCase().includes(search)
    );
  });
  
  // Group jobs by hostname
  $: jobsByHost = filteredJobs.reduce((acc, job) => {
    if (!acc[job.hostname]) {
      acc[job.hostname] = [];
    }
    acc[job.hostname].push(job);
    return acc;
  }, {} as Record<string, JobInfo[]>);
  
  // Sort hosts alphabetically
  $: sortedHosts = Object.keys(jobsByHost).sort();
  
  function selectJob(job: JobInfo) {
    selectedJob = job;
  }
  
  function handleConfirm() {
    if (selectedJob) {
      dispatch('select', selectedJob);
    }
  }
  
  function handleClose() {
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
  
  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      handleClose();
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="dialog-overlay" on:click={handleClose} on:keydown={() => {}}>
  <div class="dialog-container" on:click|stopPropagation on:keydown={() => {}}>
    <div class="dialog-header">
      <div>
        <h2>{title}</h2>
        <p class="description">{description}</p>
      </div>
      <button class="close-btn" on:click={handleClose} aria-label="Close dialog">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
        </svg>
      </button>
    </div>
    
    <div class="dialog-body">
      {#if isLoading && jobs.length === 0}
        <div class="loading-state">
          <div class="spinner"></div>
          <h3>Loading Jobs...</h3>
          <p>Fetching running and pending jobs from all hosts</p>
        </div>
      {:else if jobs.length === 0}
        <div class="empty-state">
          <svg viewBox="0 0 24 24" fill="currentColor" class="empty-icon">
            <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M14,6L8,18H10L16,6H14Z"/>
          </svg>
          <h3>No Jobs Available</h3>
          <p>There are no running or pending jobs to attach watchers to.</p>
        </div>
      {:else}
        <!-- Search bar -->
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
        
        <!-- Jobs list -->
        <div class="jobs-list">
          {#if filteredJobs.length === 0}
            <div class="no-results">
              <p>No jobs match your search criteria</p>
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
                      class:selected={selectedJob === job}
                      on:click={() => selectJob(job)}
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
                        </div>
                      </div>
                      
                      {#if selectedJob === job}
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
    </div>
    
    <div class="dialog-footer">
      <button 
        type="button"
        on:click={handleClose}
        class="cancel-btn"
      >
        Cancel
      </button>
      <button 
        type="button"
        on:click={handleConfirm}
        disabled={!selectedJob}
        class="confirm-btn"
      >
        Select Job
      </button>
    </div>
  </div>
</div>

<style>
  .dialog-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fadeIn 0.2s ease;
  }
  
  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  
  .dialog-container {
    background: white;
    border-radius: 12px;
    width: 90%;
    max-width: 800px;
    max-height: 85vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
    animation: slideUp 0.3s ease;
  }
  
  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  
  .dialog-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .dialog-header h2 {
    margin: 0;
    font-size: 1.5rem;
    color: #1f2937;
  }
  
  .description {
    margin: 0.25rem 0 0 0;
    font-size: 0.875rem;
    color: #6b7280;
  }
  
  .close-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.5rem;
    color: #6b7280;
    transition: color 0.2s;
    border-radius: 6px;
  }
  
  .close-btn:hover {
    color: #1f2937;
    background: #f3f4f6;
  }
  
  .close-btn svg {
    width: 24px;
    height: 24px;
  }
  
  .dialog-body {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
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
  
  /* Search bar */
  .search-bar {
    position: relative;
    margin-bottom: 1.5rem;
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
  .dialog-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    padding: 1.5rem;
    border-top: 1px solid #e5e7eb;
  }
  
  .cancel-btn,
  .confirm-btn {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .cancel-btn {
    background: white;
    color: #374151;
    border: 1px solid #d1d5db;
  }
  
  .cancel-btn:hover {
    background: #f3f4f6;
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
    .dialog-container {
      width: 100%;
      height: 100%;
      max-width: none;
      max-height: none;
      border-radius: 0;
    }
    
    .dialog-body {
      padding: 1rem;
    }
    
    .job-details {
      flex-direction: column;
      gap: 0.5rem;
    }
  }
</style>