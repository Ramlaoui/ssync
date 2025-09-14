<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { push, location } from 'svelte-spa-router';
  import type { JobInfo } from '../types/api';
  import { jobStateManager } from '../lib/JobStateManager';
  import { jobUtils } from '../lib/jobUtils';
  import { navigationActions } from '../stores/navigation';
  import LoadingSpinner from './LoadingSpinner.svelte';
  
  export let currentJobId: string = '';
  export let currentHost: string = '';
  export let collapsed = false;

  // On mobile, we never want the sidebar to be collapsed
  $: actuallyCollapsed = !isMobile && collapsed;
  export let isMobile = false;
  export let onMobileJobSelect: (() => void) | undefined = undefined;
  export let onClose: (() => void) | undefined = undefined;

  let loading = false;
  let hamburgerToX = false;
  let isClosing = false;
  
  // Get reactive stores from JobStateManager
  const allJobs = jobStateManager.getAllJobs();
  const runningJobs = jobStateManager.getJobsByState('R');
  const pendingJobs = jobStateManager.getJobsByState('PD');
  const connectionStatus = jobStateManager.getConnectionStatus();
  const managerState = jobStateManager.getState();
  
  // Compute recent jobs (terminal states)
  $: recentJobs = $allJobs.filter(j => jobUtils.isTerminalState(j.state)).slice(0, 50);
  
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
    // Track where we're coming from for smart back navigation
    navigationActions.setPreviousRoute($location);

    // Navigate to the job
    push(`/jobs/${job.job_id}/${job.hostname}`);

    // Close mobile sidebar if callback provided
    if (isMobile && onMobileJobSelect) {
      onMobileJobSelect();
    }
  }
  
  // Use centralized job utilities
  
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

    // Trigger hamburger animation after sidebar slides in
    if (isMobile) {
      // Reset states on mount
      isClosing = false;
      hamburgerToX = false;

      // Start morphing to X after slide begins
      setTimeout(() => {
        hamburgerToX = true;
      }, 200); // Start morphing partway through slide animation
    }
  });
  
  onDestroy(() => {
    // Cleanup handled by JobStateManager
  });
</script>

<div class="job-sidebar" class:collapsed={actuallyCollapsed} class:mobile={isMobile} class:closing={isClosing}>
  <!-- Toggle button with animation (desktop only) -->
  {#if !isMobile}
  <button
    class="toggle-btn"
    class:collapsed={actuallyCollapsed}
    on:click={() => collapsed = !collapsed}
    aria-label="{actuallyCollapsed ? 'Show' : 'Hide'} job sidebar"
  >
    <svg viewBox="0 0 24 24" fill="currentColor">
      {#if actuallyCollapsed}
        <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z" />
      {:else}
        <path d="M15.41,16.58L10.83,12L15.41,7.41L14,6L8,12L14,18L15.41,16.58Z" />
      {/if}
    </svg>
  </button>
  {/if}
  
  <div class="sidebar-header">
    {#if !actuallyCollapsed}
    <h3>Jobs</h3>
    <div class="header-actions">
      <button class="refresh-btn" on:click={() => loadJobs(true)} disabled={loading || isLoading} aria-label="Refresh jobs">
        <svg viewBox="0 0 24 24" fill="currentColor" class:spinning={loading || isLoading}>
          <path d="M12,6V9L16,5L12,1V4A8,8 0 0,0 4,12C4,13.57 4.46,15.03 5.24,16.26L6.7,14.8C6.25,13.97 6,13 6,12A6,6 0 0,1 12,6M18.76,7.74L17.3,9.2C17.74,10.04 18,11 18,12A6,6 0 0,1 12,18V15L8,19L12,23V20A8,8 0 0,0 20,12C20,10.43 19.54,8.97 18.76,7.74Z" />
        </svg>
      </button>
      {#if isMobile && onClose}
        <button class="close-btn" on:click={() => {
          isClosing = true;
          hamburgerToX = false;  // Start morphing back to hamburger
          setTimeout(() => {
            onClose();
            isClosing = false;  // Reset for next open
          }, 400);
        }} aria-label="Close job list">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class={hamburgerToX ? 'hamburger-to-x' : ''}>
            <line x1="3" y1="6" x2="21" y2="6" class="hamburger-line top" />
            <line x1="3" y1="12" x2="21" y2="12" class="hamburger-line middle" />
            <line x1="3" y1="18" x2="21" y2="18" class="hamburger-line bottom" />
          </svg>
        </button>
      {/if}
    </div>
    {/if}
  </div>
  
  {#if !actuallyCollapsed}
  <div class="sidebar-content">
    {#if loading && $allJobs.length === 0}
      <div class="loading-state">
        <LoadingSpinner size="sm" message="Loading jobs..." centered={false} />
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
                <div class="job-status" style="background-color: {jobUtils.getStateColor(job.state)}"></div>
                <div class="job-info">
                  <div class="job-header">
                    <span class="job-id">{job.job_id}</span>
                    {#if job.runtime}
                      <span class="job-runtime-badge runtime-active">{formatRuntime(job.runtime)}</span>
                    {/if}
                  </div>
                  <div class="job-content">
                    <span class="job-name">{formatJobName(job.name)}</span>
                    <span class="job-state-label state-running">
                      <svg viewBox="0 0 24 24" fill="currentColor" class="state-icon">
                        <path d="M8,5.14V19.14L19,12.14L8,5.14Z" />
                      </svg>
                      Running
                    </span>
                  </div>
                  <div class="job-meta">
                    <span class="job-host">{job.hostname.toUpperCase()}</span>
                  </div>
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
                <div class="job-status" style="background-color: {jobUtils.getStateColor(job.state)}"></div>
                <div class="job-info">
                  <div class="job-header">
                    <span class="job-id">{job.job_id}</span>
                  </div>
                  <div class="job-content">
                    <span class="job-name">{formatJobName(job.name)}</span>
                    <span class="job-state-label state-pending">
                      <svg viewBox="0 0 24 24" fill="currentColor" class="state-icon">
                        <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z" />
                      </svg>
                      Pending
                    </span>
                  </div>
                  <div class="job-meta">
                    <span class="job-host">{job.hostname.toUpperCase()}</span>
                    {#if job.reason}
                      <span class="job-reason-badge">{job.reason}</span>
                    {/if}
                  </div>
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
                <div class="job-status" style="background-color: {jobUtils.getStateColor(job.state)}"></div>
                <div class="job-info">
                  <div class="job-header">
                    <span class="job-id">{job.job_id}</span>
                    {#if job.runtime}
                      <span class="job-runtime-badge">{formatRuntime(job.runtime)}</span>
                    {/if}
                  </div>
                  <div class="job-content">
                    <span class="job-name">{formatJobName(job.name)}</span>
                    <span class="job-state-label state-{job.state.toLowerCase()}">{jobUtils.getStateLabel(job.state)}</span>
                  </div>
                  <div class="job-meta">
                    <span class="job-host">{job.hostname.toUpperCase()}</span>
                  </div>
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
    height: 100%;
    max-height: 100vh;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    position: relative;
    transition: width 0.3s ease;
    overflow: hidden;
    /* Optimize composite layer creation */
    contain: layout style paint;
    transform: translateZ(0);
  }
  
  .job-sidebar.collapsed {
    width: 48px;
  }
  
  .job-sidebar.mobile {
    width: 100%;
    height: 100%;
    border-right: none;
    border-top: 1px solid var(--border-color);
    /* On mobile, always show full width regardless of collapsed state */
    animation: slideInFromLeft 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
  }

  .job-sidebar.mobile.closing {
    animation: slideOutToLeft 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
  }

  @keyframes slideInFromLeft {
    0% {
      transform: translateX(-100%);
      opacity: 0;
    }
    60% {
      opacity: 1;
    }
    100% {
      transform: translateX(0);
      opacity: 1;
    }
  }

  @keyframes slideOutToLeft {
    0% {
      transform: translateX(0);
      opacity: 1;
    }
    40% {
      opacity: 1;
    }
    100% {
      transform: translateX(-100%);
      opacity: 0;
    }
  }

  .job-sidebar.mobile.collapsed {
    width: 100%;
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

  .job-sidebar.mobile .sidebar-header {
    /* Ensure header is always visible on mobile */
    display: flex;
    padding: 0.75rem; /* Smaller padding on mobile */
  }

  .job-sidebar.mobile .sidebar-header h3 {
    font-size: 0.9rem; /* Smaller title on mobile */
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

  .close-btn {
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
    transition: all 0.15s;
  }

  .close-btn:hover {
    background: var(--bg-tertiary);
  }

  .close-btn svg {
    width: 18px;
    height: 18px;
    color: var(--text-secondary);
  }

  /* Hamburger to X animation - synchronized with sidebar slide */
  .hamburger-line {
    transition: all 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    transform-origin: center;
  }

  /* Initial hamburger state */
  .hamburger-line.top {
    transform: translateY(0) rotate(0);
  }

  .hamburger-line.middle {
    opacity: 1;
    transform: scaleX(1);
  }

  .hamburger-line.bottom {
    transform: translateY(0) rotate(0);
  }

  /* Transform to X with proper positioning */
  .hamburger-to-x .hamburger-line.top {
    transform: rotate(45deg) translateY(6px);
  }

  .hamburger-to-x .hamburger-line.middle {
    opacity: 0;
    transform: scaleX(0);
  }

  .hamburger-to-x .hamburger-line.bottom {
    transform: rotate(-45deg) translateY(-6px);
  }

  /* When closing, ensure smooth transition back */
  .job-sidebar.closing .hamburger-line {
    transition: all 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94);
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  
  .sidebar-content {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 0.5rem;
    /* Optimize scrolling performance */
    -webkit-overflow-scrolling: touch;
    scroll-behavior: smooth;
    will-change: scroll-position;
    transform: translateZ(0);
  }

  .job-sidebar.mobile .sidebar-content {
    /* Ensure content is always visible on mobile */
    display: flex;
    flex-direction: column;
    padding: 0.375rem; /* Much smaller padding on mobile */
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
    padding: 1rem;
    background: linear-gradient(135deg, #ffffff 0%, #fafbfc 100%);
    border: 1px solid #e5e7eb;
    border-radius: 0.875rem;
    cursor: pointer;
    text-align: left;
    transition: all 0.25s ease;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.08), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
    position: relative;
    overflow: hidden;
    /* Optimize rendering performance */
    backface-visibility: hidden;
    transform: translateZ(0);
    will-change: transform, box-shadow;
  }

  /* Mobile job items - much more compact */
  .job-sidebar.mobile .job-item {
    padding: 0.5rem; /* Much smaller padding */
    gap: 0.5rem; /* Smaller gap */
    border-radius: 0.5rem; /* Less rounded */
    font-size: 0.875rem; /* Smaller text */
  }
  
  .job-item:hover {
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border-color: #cbd5e1;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    transform: translateY(-1px);
  }
  
  .job-item.selected {
    background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%);
    border-color: #3b82f6;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2), 0 4px 6px -1px rgba(59, 130, 246, 0.1);
  }
  
  .job-status {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 6px;
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.8);
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
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-top: 0.25rem;
  }
  
  .job-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.25rem;
  }

  .job-content {
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
    font-size: 0.65rem;
    color: #9ca3af;
    font-weight: 600;
    letter-spacing: 0.05em;
    background: rgba(156, 163, 175, 0.1);
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
  }

  /* Mobile job elements - smaller and more compact */
  .job-sidebar.mobile .job-id {
    font-size: 0.875rem; /* Smaller job ID text */
    font-weight: 600;
  }

  .job-sidebar.mobile .job-runtime {
    font-size: 0.75rem; /* Smaller runtime text */
  }

  .job-sidebar.mobile .job-reason {
    font-size: 0.625rem; /* Even smaller reason text */
  }

  .job-sidebar.mobile .job-state-label {
    font-size: 0.625rem; /* Smaller state label */
  }

  .job-sidebar.mobile .job-host {
    font-size: 0.5rem; /* Much smaller host label */
    padding: 0.0625rem 0.25rem; /* Tighter padding */
  }

  /* Enhanced job state labels */
  .job-state-label {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.6rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 0.125rem 0.375rem;
    border-radius: 0.375rem;
    background: rgba(107, 114, 128, 0.1);
    color: #6b7280;
  }

  .state-icon {
    width: 10px;
    height: 10px;
  }

  .state-running {
    background: rgba(16, 185, 129, 0.1);
    color: #059669;
  }

  .state-pending {
    background: rgba(245, 158, 11, 0.1);
    color: #d97706;
  }

  .state-cd {
    background: rgba(139, 92, 246, 0.1);
    color: #8b5cf6;
  }

  .state-f {
    background: rgba(239, 68, 68, 0.1);
    color: #dc2626;
  }

  .state-ca {
    background: rgba(107, 114, 128, 0.1);
    color: #6b7280;
  }

  .state-to {
    background: rgba(249, 115, 22, 0.1);
    color: #ea580c;
  }

  /* Runtime and reason badges */
  .job-runtime-badge {
    display: inline-flex;
    align-items: center;
    font-size: 0.65rem;
    font-weight: 600;
    color: #374151;
    background: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%);
    padding: 0.125rem 0.5rem;
    border-radius: 0.375rem;
    border: 1px solid #d1d5db;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  }

  .runtime-active {
    background: linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%);
    color: #065f46;
    border-color: #86efac;
    animation: pulse-runtime 2s ease-in-out infinite;
  }

  @keyframes pulse-runtime {
    0%, 100% {
      opacity: 1;
      transform: translateZ(0);
    }
    50% {
      opacity: 0.8;
      transform: translateZ(0);
    }
  }

  .job-reason-badge {
    display: inline-flex;
    align-items: center;
    font-size: 0.65rem;
    font-weight: 500;
    color: #92400e;
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    padding: 0.125rem 0.375rem;
    border-radius: 0.375rem;
    border: 1px solid #f59e0b;
    max-width: 80px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>