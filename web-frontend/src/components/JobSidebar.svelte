<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { push } from 'svelte-spa-router';
  import type { JobInfo } from '../types/api';
  import { jobsStore, sidebarJobs } from '../stores/jobs';
  
  export let currentJobId: string = '';
  export let currentHost: string = '';
  export let collapsed = false;
  export let isMobile = false;
  
  let loading = false;
  let refreshInterval: ReturnType<typeof setInterval>;
  
  // Subscribe to the derived store - these will automatically update when the global store changes
  $: jobs = $sidebarJobs.jobs;
  $: runningJobs = $sidebarJobs.runningJobs;
  $: pendingJobs = $sidebarJobs.pendingJobs;
  $: recentJobs = $sidebarJobs.recentJobs;
  
  async function loadJobs(forceRefresh = false) {
    if (loading) return; // Prevent multiple simultaneous loads
    
    try {
      loading = true;
      await jobsStore.loadSidebarJobs(forceRefresh);
    } catch (error) {
      console.error('Error loading jobs for sidebar:', error);
    } finally {
      loading = false;
    }
  }
  
  function selectJob(job: JobInfo) {
    // Navigate to the job
    push(`/jobs/${job.job_id}/${job.hostname}`);
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
    loadJobs();
    
    // Refresh every 2 minutes (120 seconds)
    refreshInterval = setInterval(() => {
      loadJobs(true);
    }, 120000);
  });
  
  onDestroy(() => {
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
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
    <button class="refresh-btn" on:click={() => loadJobs(true)} disabled={loading} aria-label="Refresh jobs">
      <svg viewBox="0 0 24 24" fill="currentColor" class:spinning={loading}>
        <path d="M12,6V9L16,5L12,1V4A8,8 0 0,0 4,12C4,13.57 4.46,15.03 5.24,16.26L6.7,14.8C6.25,13.97 6,13 6,12A6,6 0 0,1 12,6M18.76,7.74L17.3,9.2C17.74,10.04 18,11 18,12A6,6 0 0,1 12,18V15L8,19L12,23V20A8,8 0 0,0 20,12C20,10.43 19.54,8.97 18.76,7.74Z" />
      </svg>
    </button>
    {/if}
  </div>
  
  {#if !collapsed || isMobile}
  <div class="sidebar-content">
    {#if loading && jobs.length === 0}
      <div class="loading-state">
        <div class="spinner"></div>
        <span>Loading jobs...</span>
      </div>
    {:else}
      <!-- Running Jobs -->
      {#if runningJobs.length > 0}
        <div class="job-section">
          <h4 class="section-title">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M8.5,7.5L7.5,8.5L10.5,11.5L7.5,14.5L8.5,15.5L11.5,12.5L14.5,15.5L15.5,14.5L12.5,11.5L15.5,8.5L14.5,7.5L11.5,10.5L8.5,7.5Z" />
            </svg>
            Running ({runningJobs.length})
          </h4>
          <div class="job-list">
            {#each runningJobs as job}
              <button 
                class="job-item"
                class:active={job.job_id === currentJobId && job.hostname === currentHost}
                on:click={() => selectJob(job)}
              >
                <div class="job-header">
                  <div class="job-id-group">
                    <span class="status-dot running" style="background-color: {getStateColor(job.state)}"></span>
                    <span class="job-id">{job.job_id}</span>
                  </div>
                  <span class="job-runtime">{formatRuntime(job.runtime)}</span>
                </div>
                <div class="job-name">{formatJobName(job.name)}</div>
                <div class="job-footer">
                  <span class="job-host">{job.hostname}</span>
                </div>
              </button>
            {/each}
          </div>
        </div>
      {/if}
      
      <!-- Pending Jobs -->
      {#if pendingJobs.length > 0}
        <div class="job-section">
          <h4 class="section-title">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z" />
            </svg>
            Pending ({pendingJobs.length})
          </h4>
          <div class="job-list">
            {#each pendingJobs as job}
              <button 
                class="job-item"
                class:active={job.job_id === currentJobId && job.hostname === currentHost}
                on:click={() => selectJob(job)}
              >
                <div class="job-header">
                  <div class="job-id-group">
                    <span class="status-dot" style="background-color: {getStateColor(job.state)}"></span>
                    <span class="job-id">{job.job_id}</span>
                  </div>
                </div>
                <div class="job-name">{formatJobName(job.name)}</div>
                <div class="job-footer">
                  <span class="job-host">{job.hostname}</span>
                  <span class="job-reason">{job.reason || 'Pending'}</span>
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
              <path d="M13,3A9,9 0 0,0 4,12H1L4.89,15.89L4.96,16.03L9,12H6A7,7 0 0,1 13,5A7,7 0 0,1 20,12A7,7 0 0,1 13,19C11.07,19 9.32,18.21 8.06,16.94L6.64,18.36C8.27,20 10.5,21 13,21A9,9 0 0,0 22,12A9,9 0 0,0 13,3M12,8V13L16.28,15.54L17,14.33L13.5,12.25V8H12Z" />
            </svg>
            Recent
          </h4>
          <div class="job-list">
            {#each recentJobs as job}
              <button 
                class="job-item"
                class:active={job.job_id === currentJobId && job.hostname === currentHost}
                on:click={() => selectJob(job)}
              >
                <div class="job-header">
                  <div class="job-id-group">
                    <span class="status-dot" style="background-color: {getStateColor(job.state)}"></span>
                    <span class="job-id">{job.job_id}</span>
                  </div>
                </div>
                <div class="job-name">{formatJobName(job.name)}</div>
                <div class="job-footer">
                  <span class="job-host">{job.hostname}</span>
                  <span class="job-state-text">{getStateLabel(job.state)}</span>
                </div>
              </button>
            {/each}
          </div>
        </div>
      {/if}
      
      {#if jobs.length === 0}
        <div class="empty-state">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M19,8L15,12H18A6,6 0 0,1 12,18C11,18 10.03,17.75 9.2,17.3L7.74,18.76C8.97,19.54 10.43,20 12,20A8,8 0 0,0 20,12H23M6,12A6,6 0 0,1 12,6C13,6 13.97,6.25 14.8,6.7L16.26,5.24C15.03,4.46 13.57,4 12,4A8,8 0 0,0 4,12H1L5,16L9,12" />
          </svg>
          <span>No jobs found</span>
        </div>
      {/if}
    {/if}
  </div>
  {/if}
</div>

<style>
  .job-sidebar {
    width: 280px;
    background: white;
    border-right: 1px solid #e2e8f0;
    display: flex;
    flex-direction: column;
    transition: width 0.3s ease;
    position: relative;
  }
  
  .job-sidebar.collapsed {
    width: 0;
    border-right: none;
    overflow: hidden;
  }
  
  .toggle-btn {
    position: absolute;
    left: 16px;
    top: 16px;
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 10;
    outline: none !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }
  
  .job-sidebar.collapsed .toggle-btn {
    position: fixed;
    left: 8px;
    top: 50%;
    transform: translateY(-50%);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
    background: white;
    border: 1px solid #cbd5e1;
  }
  
  .toggle-btn:hover {
    background: #f1f5f9;
    border-color: #cbd5e1;
    transform: scale(1.05);
  }
  
  .toggle-btn:focus {
    outline: none !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  }
  
  .toggle-btn svg {
    width: 20px;
    height: 20px;
    color: #64748b;
    transition: transform 0.3s ease;
  }
  
  .sidebar-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem 1rem 1rem 52px;
    border-bottom: 1px solid #e2e8f0;
    background: #f8fafc;
    min-width: 280px;
  }
  
  .sidebar-header h3 {
    flex: 1;
    margin: 0;
    font-size: 0.9rem;
    font-weight: 600;
    color: #1e293b;
  }
  
  .refresh-btn {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
    outline: none !important;
  }
  
  .refresh-btn:focus {
    outline: none !important;
    box-shadow: none !important;
  }
  
  .refresh-btn:hover:not(:disabled) {
    background: #f1f5f9;
    border-color: #cbd5e1;
  }
  
  .refresh-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .refresh-btn svg {
    width: 16px;
    height: 16px;
  }
  
  .spinning {
    animation: spin 1s linear infinite;
  }
  
  .sidebar-content {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem;
    min-width: 280px;
  }
  
  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    gap: 0.75rem;
  }
  
  .spinner {
    width: 24px;
    height: 24px;
    border: 2px solid #e2e8f0;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  
  .loading-state span {
    font-size: 0.85rem;
    color: #64748b;
  }
  
  .job-section {
    margin-bottom: 1.5rem;
  }
  
  .job-section:last-child {
    margin-bottom: 0;
  }
  
  .section-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0 0 0.625rem 0;
    padding: 0.25rem 0.5rem;
    font-size: 0.7rem;
    font-weight: 700;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  
  .section-title svg {
    width: 14px;
    height: 14px;
    opacity: 0.7;
  }
  
  .job-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .job-item {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
    padding: 0.75rem;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.15s ease;
    text-align: left;
    width: 100%;
    outline: none !important;
  }
  
  .job-item:focus {
    outline: none !important;
    box-shadow: none !important;
  }
  
  .job-item:hover {
    background: #f8fafc;
    border-color: #cbd5e1;
    transform: translateX(2px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  }
  
  .job-item.active {
    background: linear-gradient(to right, #eff6ff, #f0f9ff);
    border-color: #3b82f6;
    box-shadow: 0 2px 6px rgba(59, 130, 246, 0.15);
  }
  
  .job-item.active .job-id {
    color: #1e40af;
  }
  
  .job-item.active .job-name {
    color: #334155;
  }
  
  .job-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .job-id-group {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  
  .status-dot.running {
    animation: pulse 2s ease-in-out infinite;
  }
  
  @keyframes pulse {
    0%, 100% {
      opacity: 1;
    }
    50% {
      opacity: 0.6;
    }
  }
  
  .job-id {
    font-size: 0.95rem;
    font-weight: 600;
    color: #0f172a;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    letter-spacing: -0.01em;
  }
  
  .job-runtime {
    font-size: 0.8rem;
    color: #64748b;
    font-weight: 500;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }
  
  .job-name {
    font-size: 0.825rem;
    color: #475569;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 500;
    line-height: 1.3;
  }
  
  .job-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 0.125rem;
  }
  
  .job-host {
    font-size: 0.725rem;
    color: #94a3b8;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }
  
  .job-reason {
    font-size: 0.7rem;
    color: #f59e0b;
    font-weight: 500;
    max-width: 100px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .job-state-text {
    font-size: 0.725rem;
    color: #64748b;
    font-weight: 500;
    text-transform: capitalize;
  }
  
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    gap: 0.5rem;
  }
  
  .empty-state svg {
    width: 32px;
    height: 32px;
    color: #cbd5e1;
  }
  
  .empty-state span {
    font-size: 0.85rem;
    color: #94a3b8;
  }
  
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  
  /* Mobile styles */
  .job-sidebar.mobile {
    width: 100%;
    position: static;
    border-right: none;
    border-bottom: 1px solid #e2e8f0;
    max-height: 50vh;
  }
  
  .job-sidebar.mobile .sidebar-content {
    max-height: calc(50vh - 60px);
  }
</style>