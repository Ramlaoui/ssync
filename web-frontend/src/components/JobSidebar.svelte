<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { push } from 'svelte-spa-router';
  import type { JobInfo } from '../types/api';
  import { jobStateManager } from '../lib/JobStateManager';
  
  export let currentJobId: string = '';
  export let currentHost: string = '';
  export let collapsed = false;
  export let isMobile = false;
  export let onMobileJobSelect: (() => void) | undefined = undefined;
  
  let loading = false;
  
  // Get reactive stores from JobStateManager
  const allJobs = jobStateManager.getAllJobs();
  const runningJobs = jobStateManager.getJobsByState('R');
  const pendingJobs = jobStateManager.getJobsByState('PD');
  const connectionStatus = jobStateManager.getConnectionStatus();
  const managerState = jobStateManager.getState();
  
  // Compute recent jobs (completed, failed, cancelled, timeout)
  $: recentJobs = $allJobs.filter(j => 
    j.state === 'CD' || j.state === 'F' || j.state === 'CA' || j.state === 'TO'
  ).slice(0, 50);
  
  // Track loading state
  $: isLoading = Array.from($managerState.hostStates.values()).some(h => h.status === 'loading');
  
  async function loadJobs(forceRefresh = false) {
    if (loading) return;
    
    try {
      loading = true;
      
      if (forceRefresh) {
        await jobStateManager.forceRefresh();
      } else {
        await jobStateManager.syncAllHosts();
      }
      
      setTimeout(() => loading = false, 500);
    } catch (error) {
      console.error('Error loading jobs for sidebar:', error);
      loading = false;
    }
  }
  
  function selectJob(job: JobInfo) {
    // Navigate to the job
    push(`/jobs/${job.job_id}/${job.hostname}`);
    
    // Close mobile sidebar if callback provided
    if (isMobile && onMobileJobSelect) {
      onMobileJobSelect();
    }
  }
  
  function getStateColor(state: string): string {
    switch (state) {
      case 'R': return '#10b981';  // Green for running
      case 'PD': return '#f59e0b'; // Amber for pending
      case 'CD': return '#8b5cf6'; // Purple for completed
      case 'F': return '#ef4444';  // Red for failed
      case 'CA': return '#6b7280'; // Gray for cancelled
      case 'TO': return '#f97316'; // Orange for timeout
      default: return '#06b6d4';
    }
  }
  
  function getStateLabel(state: string): string {
    switch (state) {
      case 'R': return 'Running';
      case 'PD': return 'Pending';
      case 'CD': return 'Completed';
      case 'F': return 'Failed';
      case 'CA': return 'Cancelled';
      case 'TO': return 'Timeout';
      default: return 'Unknown';
    }
  }
  
  function formatRuntime(runtime: string | null): string {
    if (!runtime || runtime === 'N/A') return '';
    return runtime;
  }
  
  function formatJobName(name: string | null): string {
    if (!name) return 'Unnamed Job';
    // Remove file extension if present
    const cleanName = name.replace(/\.(sh|slurm|sbatch)$/, '');
    if (cleanName.length > 28) {
      return cleanName.substring(0, 25) + '...';
    }
    return cleanName;
  }
  
  onMount(() => {
    // JobStateManager automatically handles initial load
  });
  
  onDestroy(() => {
    // Cleanup handled by JobStateManager
  });
</script>

<div class="job-sidebar" class:collapsed class:mobile={isMobile}>
  <!-- Toggle button with animation (desktop only) -->
  {#if !isMobile}
  <button 
    class="toggle-btn"
    class:collapsed
    on:click={() => collapsed = !collapsed}
    aria-label="{collapsed ? 'Show' : 'Hide'} job sidebar"
  >
    <svg viewBox="0 0 24 24" fill="currentColor">
      {#if collapsed}
        <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z" />
      {:else}
        <path d="M15.41,16.58L10.83,12L15.41,7.41L14,6L8,12L14,18L15.41,16.58Z" />
      {/if}
    </svg>
  </button>
  {/if}
  
  <div class="sidebar-header">
    {#if !collapsed || isMobile}
    <h3>Jobs</h3>
    <div class="header-actions">
      {#if $connectionStatus.connected}
        <span class="connection-indicator" title="Source: {$connectionStatus.source}">
          <svg viewBox="0 0 24 24" fill="currentColor" class="status-icon {$connectionStatus.source}">
            {#if $connectionStatus.source === 'websocket'}
              <path d="M4.93,4.93C3.12,6.74 2,9.24 2,12C2,14.76 3.12,17.26 4.93,19.07L6.34,17.66C4.89,16.22 4,14.22 4,12C4,9.79 4.89,7.78 6.34,6.34L4.93,4.93M19.07,4.93L17.66,6.34C19.11,7.78 20,9.79 20,12C20,14.22 19.11,16.22 17.66,17.66L19.07,19.07C20.88,17.26 22,14.76 22,12C22,9.24 20.88,6.74 19.07,4.93M7.76,7.76C6.67,8.85 6,10.35 6,12C6,13.65 6.67,15.15 7.76,16.24L9.17,14.83C8.45,14.11 8,13.11 8,12C8,10.89 8.45,9.89 9.17,9.17L7.76,7.76M16.24,7.76L14.83,9.17C15.55,9.89 16,10.89 16,12C16,13.11 15.55,14.11 14.83,14.83L16.24,16.24C17.33,15.15 18,13.65 18,12C18,10.35 17.33,8.85 16.24,7.76M12,10A2,2 0 0,0 10,12A2,2 0 0,0 12,14A2,2 0 0,0 14,12A2,2 0 0,0 12,10Z" />
            {:else}
              <path d="M12,18.17L8.83,15L7.42,16.41L12,21L16.59,16.41L15.17,15M12,5.83L15.17,9L16.58,7.59L12,3L7.41,7.59L8.83,9L12,5.83Z" />
            {/if}
          </svg>
        </span>
      {/if}
      <button class="refresh-btn" on:click={() => loadJobs(true)} disabled={loading || isLoading} aria-label="Refresh jobs">
        <svg viewBox="0 0 24 24" fill="currentColor" class:spinning={loading || isLoading}>
          <path d="M12,6V9L16,5L12,1V4A8,8 0 0,0 4,12C4,13.57 4.46,15.03 5.24,16.26L6.7,14.8C6.25,13.97 6,13 6,12A6,6 0 0,1 12,6M18.76,7.74L17.3,9.2C17.74,10.04 18,11 18,12A6,6 0 0,1 12,18V15L8,19L12,23V20A8,8 0 0,0 20,12C20,10.43 19.54,8.97 18.76,7.74Z" />
        </svg>
      </button>
    </div>
    {/if}
  </div>
  
  {#if !collapsed || isMobile}
  <div class="sidebar-content">
    {#if loading && $allJobs.length === 0}
      <div class="loading-state">
        <div class="spinner"></div>
        <span>Loading jobs...</span>
      </div>
    {:else}
      <!-- Running Jobs -->
      {#if $runningJobs.length > 0}
        <div class="job-section">
          <h4 class="section-title">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M8,5.14V19.14L19,12.14L8,5.14Z" />
            </svg>
            Running ({$runningJobs.length})
          </h4>
          <div class="job-list">
            {#each $runningJobs as job (job.job_id + job.hostname)}
              <button 
                class="job-item"
                class:selected={currentJobId === job.job_id && currentHost === job.hostname}
                on:click={() => selectJob(job)}
              >
                <div class="job-status" style="background-color: {getStateColor(job.state)}"></div>
                <div class="job-info">
                  <div class="job-header">
                    <span class="job-id">{job.job_id}</span>
                    {#if job.runtime}
                      <span class="job-runtime">{formatRuntime(job.runtime)}</span>
                    {/if}
                  </div>
                  <span class="job-name">{formatJobName(job.name)}</span>
                  <span class="job-host">{job.hostname.toUpperCase()}</span>
                </div>
              </button>
            {/each}
          </div>
        </div>
      {/if}
      
      <!-- Pending Jobs -->
      {#if $pendingJobs.length > 0}
        <div class="job-section">
          <h4 class="section-title">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z" />
            </svg>
            Pending ({$pendingJobs.length})
          </h4>
          <div class="job-list">
            {#each $pendingJobs as job (job.job_id + job.hostname)}
              <button 
                class="job-item"
                class:selected={currentJobId === job.job_id && currentHost === job.hostname}
                on:click={() => selectJob(job)}
              >
                <div class="job-status" style="background-color: {getStateColor(job.state)}"></div>
                <div class="job-info">
                  <div class="job-header">
                    <span class="job-id">{job.job_id}</span>
                    {#if job.reason}
                      <span class="job-reason">{job.reason}</span>
                    {/if}
                  </div>
                  <span class="job-name">{formatJobName(job.name)}</span>
                  <span class="job-host">{job.hostname.toUpperCase()}</span>
                </div>
              </button>
            {/each}
          </div>
        </div>
      {/if}
      
      <!-- Recent Jobs -->
      {#if recentJobs.length > 0}
        <div class="job-section">
          <h4 class="section-title">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M13.5,8H12V13L16.28,15.54L17,14.33L13.5,12.25V8M13,3A9,9 0 0,0 4,12H1L4.96,16.03L9,12H6A7,7 0 0,1 13,5A7,7 0 0,1 20,12A7,7 0 0,1 13,19C11.07,19 9.32,18.21 8.06,16.94L6.64,18.36C8.27,20 10.5,21 13,21A9,9 0 0,0 22,12A9,9 0 0,0 13,3" />
            </svg>
            Recent ({recentJobs.length})
          </h4>
          <div class="job-list">
            {#each recentJobs as job (job.job_id + job.hostname)}
              <button 
                class="job-item"
                class:selected={currentJobId === job.job_id && currentHost === job.hostname}
                on:click={() => selectJob(job)}
              >
                <div class="job-status" style="background-color: {getStateColor(job.state)}"></div>
                <div class="job-info">
                  <div class="job-header">
                    <span class="job-id">{job.job_id}</span>
                    <span class="job-state-label">{getStateLabel(job.state)}</span>
                  </div>
                  <span class="job-name">{formatJobName(job.name)}</span>
                  <span class="job-host">{job.hostname.toUpperCase()}</span>
                </div>
              </button>
            {/each}
          </div>
        </div>
      {/if}
      
      {#if $allJobs.length === 0}
        <div class="empty-state">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M19,8L15,12H18A6,6 0 0,1 12,18C11,18 10.03,17.75 9.2,17.3L7.74,18.76C8.97,19.54 10.43,20 12,20A8,8 0 0,0 20,12H23M6,12A6,6 0 0,1 12,6C13,6 13.97,6.25 14.8,6.7L16.26,5.24C15.03,4.46 13.57,4 12,4A8,8 0 0,0 4,12H1L5,16L9,12" />
          </svg>
          <p>No jobs found</p>
        </div>
      {/if}
    {/if}
  </div>
  {/if}
</div>

<style>
  .job-sidebar {
    width: 280px;
    background: var(--bg-secondary);
    border-left: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    position: relative;
    transition: width 0.3s ease;
  }
  
  .job-sidebar.collapsed {
    width: 48px;
  }
  
  .job-sidebar.mobile {
    width: 100%;
    border-left: none;
    border-top: 1px solid var(--border-color);
  }
  
  .toggle-btn {
    position: absolute;
    left: -12px;
    top: 50%;
    transform: translateY(-50%);
    width: 24px;
    height: 24px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    z-index: 10;
    transition: all 0.3s ease;
  }
  
  .toggle-btn svg {
    width: 16px;
    height: 16px;
    color: var(--text-secondary);
    transition: transform 0.3s ease;
  }
  
  .toggle-btn:hover {
    background: var(--bg-tertiary);
  }
  
  .toggle-btn.collapsed svg {
    transform: rotate(180deg);
  }
  
  .sidebar-header {
    padding: 1rem;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .sidebar-header h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
  }
  
  .header-actions {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  
  .connection-indicator {
    display: flex;
    align-items: center;
  }
  
  .status-icon {
    width: 16px;
    height: 16px;
    color: var(--text-secondary);
  }
  
  .status-icon.websocket {
    color: #10b981;
  }
  
  .status-icon.api {
    color: #f59e0b;
  }
  
  .refresh-btn {
    width: 28px;
    height: 28px;
    padding: 0;
    background: transparent;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.25rem;
    transition: background 0.2s;
  }
  
  .refresh-btn:hover:not(:disabled) {
    background: var(--bg-tertiary);
  }
  
  .refresh-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .refresh-btn svg {
    width: 16px;
    height: 16px;
    color: var(--text-secondary);
  }
  
  .refresh-btn svg.spinning {
    animation: spin 1s linear infinite;
  }
  
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  
  .sidebar-content {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem;
  }
  
  .loading-state,
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    color: var(--text-secondary);
  }
  
  .spinner {
    width: 2rem;
    height: 2rem;
    border: 2px solid var(--border-color);
    border-top-color: var(--accent-color);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
  
  .empty-state svg {
    width: 2rem;
    height: 2rem;
    margin-bottom: 0.5rem;
    opacity: 0.5;
  }
  
  .empty-state p {
    margin: 0;
    font-size: 0.875rem;
  }
  
  .job-section {
    margin-bottom: 1rem;
  }
  
  .section-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0 0 0.75rem 0;
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    color: #9ca3af;
    letter-spacing: 0.05em;
  }
  
  .section-title svg {
    width: 14px;
    height: 14px;
    opacity: 0.6;
  }
  
  .job-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .job-item {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    width: 100%;
    padding: 0.75rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.75rem;
    cursor: pointer;
    text-align: left;
    transition: all 0.2s;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  }
  
  .job-item:hover {
    background: #fafbfc;
    border-color: #d1d5db;
    box-shadow: 0 2px 4px 0 rgba(0, 0, 0, 0.08);
  }
  
  .job-item.selected {
    background: #eff6ff;
    border-color: #3b82f6;
    box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.1);
  }
  
  .job-status {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 4px;
  }
  
  .job-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .job-name {
    font-size: 0.9rem;
    font-weight: 600;
    color: #111827;
    line-height: 1.2;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  
  .job-meta {
    font-size: 0.8rem;
    color: #6b7280;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  
  .job-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.25rem;
  }
  
  .job-id {
    font-size: 1rem;
    font-weight: 700;
    color: #111827;
  }
  
  .job-runtime {
    font-size: 0.875rem;
    font-weight: 500;
    color: #6b7280;
  }
  
  .job-reason {
    font-size: 0.75rem;
    color: #9ca3af;
  }
  
  .job-state-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: #6b7280;
    text-transform: uppercase;
  }
  
  .job-host {
    font-size: 0.75rem;
    color: #9ca3af;
    font-weight: 500;
    letter-spacing: 0.025em;
  }
</style>