<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { push } from "svelte-spa-router";
  import { jobsStore } from "../stores/jobs";
  import { api } from "../services/api";
  import type { JobInfo, JobOutputResponse, JobScriptResponse } from "../types/api";
  import JobSidebar from "../components/JobSidebar.svelte";

  export let params: { id?: string; host?: string } = {};

  let job: JobInfo | null = null;
  let loading = true;
  let error: string | null = null;
  let refreshInterval: ReturnType<typeof setInterval>;
  let mounted = true;
  let sidebarCollapsed = false;
  let showMobileSidebar = false;
  let isMobile = false;
  
  // Tab state
  let activeTab: 'info' | 'output' | 'errors' | 'script' = 'info';
  
  // Output data
  let outputData: JobOutputResponse | null = null;
  let loadingOutput = false;
  let outputError: string | null = null;
  
  // Script data
  let scriptData: JobScriptResponse | null = null;
  let loadingScript = false;
  let scriptError: string | null = null;
  
  // Cancel job state
  let cancellingJob = false;
  let cancelError: string | null = null;

  $: canCancelJob = job && (job.state === 'R' || job.state === 'PD');

  async function loadJob(forceRefresh = false) {
    if (!params.id || !params.host) {
      error = "Invalid job parameters";
      loading = false;
      return;
    }

    try {
      loading = true;
      error = null;
      
      const fetchedJob = await jobsStore.fetchJob(params.id, params.host, forceRefresh);
      
      if (mounted) {
        if (fetchedJob) {
          job = fetchedJob;
          error = null;
        } else {
          error = `Job ${params.id} not found on ${params.host}`;
        }
      }
    } catch (err: any) {
      if (mounted) {
        error = `Failed to load job: ${err.message || 'Unknown error'}`;
      }
    } finally {
      if (mounted) {
        loading = false;
      }
    }
  }

  async function loadOutput(): Promise<void> {
    if (!job || loadingOutput) return;
    
    // Don't reload if we already have data for this job
    if (outputData && outputData.job_id === job.job_id) {
      return;
    }
    
    loadingOutput = true;
    outputError = null;
    
    try {
      outputData = await jobsStore.fetchJobOutput(job.job_id, job.hostname);
      if (!outputData) {
        outputError = 'No output data available';
      }
    } catch (error: unknown) {
      console.error('Error loading job output:', error);
      outputError = (error as Error).message || 'Failed to load output';
    } finally {
      loadingOutput = false;
    }
  }

  async function loadScript(): Promise<void> {
    if (!job || loadingScript) return;
    
    // Don't reload if we already have data for this job
    if (scriptData && scriptData.job_id === job.job_id) {
      return;
    }
    
    loadingScript = true;
    scriptError = null;
    
    try {
      const response = await api.get<JobScriptResponse>(`/api/jobs/${job.job_id}/script?host=${encodeURIComponent(job.hostname)}`);
      scriptData = response.data;
    } catch (error: unknown) {
      console.error('Error loading job script:', error);
      scriptError = (error as Error).message || 'Failed to load script';
    } finally {
      loadingScript = false;
    }
  }

  function retryLoadOutput(): void {
    outputData = null;
    outputError = null;
    loadOutput();
  }

  function retryLoadScript(): void {
    scriptData = null;
    scriptError = null;
    loadScript();
  }
  
  // Watch for tab changes to load data as needed
  $: if (job && activeTab) {
    if ((activeTab === 'output' || activeTab === 'errors') && (!outputData || outputData.job_id !== job.job_id)) {
      loadOutput();
    } else if (activeTab === 'script' && (!scriptData || scriptData.job_id !== job.job_id)) {
      loadScript();
    }
  }

  function handleClose() {
    push('/');
  }

  function handleRefresh() {
    loadJob(true);
  }

  async function cancelJob(): Promise<void> {
    if (!job || cancellingJob) return;
    
    const confirmed = confirm(`Are you sure you want to cancel job ${job.job_id}?`);
    if (!confirmed) return;
    
    cancellingJob = true;
    cancelError = null;
    
    try {
      await api.post(`/api/jobs/${job.job_id}/cancel?host=${encodeURIComponent(job.hostname)}`);
      job.state = 'CA';
      alert(`Job ${job.job_id} has been cancelled successfully.`);
    } catch (error: unknown) {
      console.error('Error cancelling job:', error);
      cancelError = (error as Error).message || 'Failed to cancel job';
      alert(`Failed to cancel job: ${cancelError}`);
    } finally {
      cancellingJob = false;
    }
  }

  function formatTime(timeStr: string | null): string {
    if (!timeStr || timeStr === 'N/A') return 'N/A';
    try {
      return new Date(timeStr).toLocaleString();
    } catch {
      return timeStr;
    }
  }

  function getStateColor(state: string): string {
    switch (state) {
      case 'R': return '#10b981';
      case 'PD': return '#f59e0b';
      case 'CD': return '#8b5cf6';
      case 'F': return '#ef4444';
      case 'CA': return '#6b7280';
      case 'TO': return '#f97316';
      default: return '#06b6d4';
    }
  }

  function getStateLabel(state: string): string {
    switch (state) {
      case 'R': return 'RUNNING';
      case 'PD': return 'PENDING';
      case 'CD': return 'COMPLETED';
      case 'F': return 'FAILED';
      case 'CA': return 'CANCELLED';
      case 'TO': return 'TIMEOUT';
      default: return 'UNKNOWN';
    }
  }

  onMount(() => {
    mounted = true;
    loadJob();
    
    // Check if mobile
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    // Load collapsed state from localStorage
    const saved = localStorage.getItem('jobSidebarCollapsed');
    if (saved) {
      sidebarCollapsed = saved === 'true';
    }
    
    // Auto-refresh running jobs
    refreshInterval = setInterval(() => {
      if (job && (job.state === 'R' || job.state === 'PD')) {
        loadJob();
      }
    }, 30000);
  });
  
  function checkMobile() {
    isMobile = window.innerWidth < 768;
    if (isMobile) {
      sidebarCollapsed = false; // Don't collapse on mobile
    }
  }

  onDestroy(() => {
    mounted = false;
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
    window.removeEventListener('resize', checkMobile);
  });
  
  function toggleSidebar() {
    sidebarCollapsed = !sidebarCollapsed;
    localStorage.setItem('jobSidebarCollapsed', String(sidebarCollapsed));
  }

  // Track params changes
  let lastParams = { id: params.id, host: params.host };
  
  $: if (mounted && params.id && params.host && 
      (params.id !== lastParams.id || params.host !== lastParams.host)) {
    lastParams = { id: params.id, host: params.host };
    // Reset data when switching jobs
    outputData = null;
    scriptData = null;
    outputError = null;
    scriptError = null;
    loadJob();
  }
  
  // Reactive statements need to check job ID to re-trigger on job change
  $: if (job && (activeTab === 'output' || activeTab === 'errors')) {
    // Check if we need to load output for this specific job
    if (!outputData || outputData.job_id !== job.job_id) {
      loadOutput();
    }
  }
  
  $: if (job && activeTab === 'script') {
    // Check if we need to load script for this specific job
    if (!scriptData || scriptData.job_id !== job.job_id) {
      loadScript();
    }
  }
</script>

<div class="job-page">
  {#if isMobile && showMobileSidebar}
    <!-- Mobile Sidebar Overlay -->
    <div class="mobile-sidebar-overlay">
      <JobSidebar 
        currentJobId={params.id || ''}
        currentHost={params.host || ''}
        collapsed={false}
        {isMobile}
      />
      <button 
        class="mobile-toggle-btn"
        on:click={() => showMobileSidebar = false}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
        </svg>
        Close List
      </button>
    </div>
  {:else}
    <div class="page-layout" class:sidebar-collapsed={sidebarCollapsed}>
      {#if !isMobile}
        <!-- Desktop Sidebar -->
        <JobSidebar 
          currentJobId={params.id || ''}
          currentHost={params.host || ''}
          bind:collapsed={sidebarCollapsed}
          {isMobile}
        />
      {/if}
      
      <div class="job-content-area">
        <!-- Header -->
        <div class="header">
    <div class="header-left">
      {#if isMobile}
        <button 
          class="mobile-sidebar-btn" 
          on:click={() => showMobileSidebar = true}
          aria-label="Show job list"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z"/>
          </svg>
        </button>
      {:else}
        <button class="back-btn" on:click={handleClose} aria-label="Back">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z"/>
          </svg>
          Jobs
        </button>
      {/if}
      {#if job}
      <div class="divider"></div>
      <div class="job-title">
        <span class="job-label">{params.host}</span>
        <span class="separator">/</span>
        <span class="job-label">Job {job.job_id}</span>
        <span class="job-name">{job.name}</span>
      </div>
      {/if}
    </div>
    
    <div class="header-right">
      <button 
        class="refresh-btn" 
        on:click={handleRefresh} 
        disabled={loading}
      >
        <svg class:spinning={loading} viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,6V9L16,5L12,1V4A8,8 0 0,0 4,12C4,13.57 4.46,15.03 5.24,16.26L6.7,14.8C6.25,13.97 6,13 6,12A6,6 0 0,1 12,6M18.76,7.74L17.3,9.2C17.74,10.04 18,11 18,12A6,6 0 0,1 12,18V15L8,19L12,23V20A8,8 0 0,0 20,12C20,10.43 19.54,8.97 18.76,7.74Z" />
        </svg>
        {loading ? "Refreshing..." : "Refresh"}
      </button>
      
      {#if job && canCancelJob}
      <button class="cancel-btn" on:click={cancelJob} disabled={cancellingJob}>
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
        </svg>
        Cancel Job
      </button>
      {/if}
      
      {#if job}
      <span class="state-badge" style="background-color: {getStateColor(job.state)}">
        {getStateLabel(job.state)}
      </span>
      {/if}
    </div>
  </div>
  
  {#if error && !job}
    <div class="error-container">
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
      </svg>
      <h2>Unable to Load Job</h2>
      <p>{error}</p>
      <button on:click={handleRefresh}>Try Again</button>
    </div>
  {:else if job}
    <!-- Tabs -->
    <div class="tabs">
      <button class="tab" class:active={activeTab === 'info'} on:click={() => activeTab = 'info'}>
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/>
        </svg>
        Info
      </button>
      <button class="tab" class:active={activeTab === 'output'} on:click={() => activeTab = 'output'}>
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
        </svg>
        Output
      </button>
      <button class="tab" class:active={activeTab === 'errors'} on:click={() => activeTab = 'errors'}>
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
        </svg>
        Errors
      </button>
      <button class="tab" class:active={activeTab === 'script'} on:click={() => activeTab = 'script'}>
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/>
        </svg>
        Script
      </button>
    </div>
    
    <!-- Content -->
    <div class="content">
      {#if activeTab === 'info'}
        <div class="info-container">
          <!-- General Information -->
          <div class="info-card">
            <h3 class="card-title">General</h3>
            <div class="info-row">
              <span class="info-label">Job ID:</span>
              <span class="info-value">{job.job_id}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Name:</span>
              <span class="info-value">{job.name}</span>
            </div>
            <div class="info-row">
              <span class="info-label">User:</span>
              <span class="info-value">{job.user || 'N/A'}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Host:</span>
              <span class="info-value">{job.hostname}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Partition:</span>
              <span class="info-value">{job.partition || 'N/A'}</span>
            </div>
            {#if job.work_dir && job.work_dir !== 'N/A'}
            <div class="info-row full-width">
              <span class="info-label">Work Dir:</span>
              <span class="info-value mono">{job.work_dir}</span>
            </div>
            {/if}
            {#if job.reason && job.reason !== 'N/A' && job.reason !== 'None'}
            <div class="info-row full-width">
              <span class="info-label">Reason:</span>
              <span class="info-value">{job.reason}</span>
            </div>
            {/if}
          </div>
          
          <!-- Resources -->
          <div class="info-card">
            <h3 class="card-title">Resources</h3>
            <div class="info-row">
              <span class="info-label">Nodes:</span>
              <span class="info-value">{job.nodes || 'N/A'}</span>
            </div>
            <div class="info-row">
              <span class="info-label">CPUs:</span>
              <span class="info-value">{job.cpus || 'N/A'}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Memory:</span>
              <span class="info-value">{job.memory || 'N/A'}</span>
            </div>
            {#if job.gpus && job.gpus !== 'N/A'}
            <div class="info-row">
              <span class="info-label">GPUs:</span>
              <span class="info-value">{job.gpus}</span>
            </div>
            {/if}
            <div class="info-row">
              <span class="info-label">Time Limit:</span>
              <span class="info-value">{job.time_limit || 'N/A'}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Runtime:</span>
              <span class="info-value">{job.runtime || '0:00'}</span>
            </div>
          </div>
          
          <!-- Timing -->
          <div class="info-card">
            <h3 class="card-title">Timing</h3>
            <div class="info-row full-width">
              <span class="info-label">Submitted:</span>
              <span class="info-value">{formatTime(job.submit_time)}</span>
            </div>
            <div class="info-row full-width">
              <span class="info-label">Started:</span>
              <span class="info-value">{formatTime(job.start_time)}</span>
            </div>
            <div class="info-row full-width">
              <span class="info-label">Ended:</span>
              <span class="info-value">{formatTime(job.end_time)}</span>
            </div>
          </div>
        </div>
        
      {:else if activeTab === 'output'}
        <div class="output-section">
          {#if loadingOutput}
            <div class="loading-state">
              <div class="spinner"></div>
              <span>Loading output...</span>
            </div>
          {:else if outputError}
            <div class="error-state">
              <span>{outputError}</span>
              <button class="retry-btn" on:click={retryLoadOutput}>Retry</button>
            </div>
          {:else if outputData?.stdout}
            <pre class="output-content">{outputData.stdout}</pre>
          {:else}
            <div class="empty-state">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
              </svg>
              <span>No output available</span>
            </div>
          {/if}
        </div>
        
      {:else if activeTab === 'errors'}
        <div class="output-section">
          {#if loadingOutput}
            <div class="loading-state">
              <div class="spinner"></div>
              <span>Loading errors...</span>
            </div>
          {:else if outputError}
            <div class="error-state">
              <span>{outputError}</span>
              <button class="retry-btn" on:click={retryLoadOutput}>Retry</button>
            </div>
          {:else if outputData?.stderr}
            <pre class="output-content error">{outputData.stderr}</pre>
          {:else}
            <div class="empty-state">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z"/>
              </svg>
              <span>No errors</span>
            </div>
          {/if}
        </div>
        
      {:else if activeTab === 'script'}
        <div class="output-section">
          {#if loadingScript}
            <div class="loading-state">
              <div class="spinner"></div>
              <span>Loading script...</span>
            </div>
          {:else if scriptError}
            <div class="error-state">
              <span>{scriptError}</span>
              <button class="retry-btn" on:click={retryLoadScript}>Retry</button>
            </div>
          {:else if scriptData?.script_content}
            <pre class="output-content script">{scriptData.script_content}</pre>
          {:else}
            <div class="empty-state">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M14.6,16.6L19.2,12L14.6,7.4L16,6L22,12L16,18L14.6,16.6M9.4,16.6L4.8,12L9.4,7.4L8,6L2,12L8,18L9.4,16.6Z"/>
              </svg>
              <span>Script not available</span>
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .job-page {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: #f8fafc;
  }

  /* Header */
  .header {
    background: white;
    border-bottom: 1px solid #e2e8f0;
    padding: 1rem 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex: 1;
    min-width: 0;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .back-btn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 0.75rem;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    color: #64748b;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
    outline: none !important;
  }
  
  .back-btn:focus {
    outline: none !important;
    box-shadow: none !important;
  }

  .back-btn:hover {
    background: #f1f5f9;
    border-color: #cbd5e1;
    color: #475569;
  }

  .back-btn svg {
    width: 16px;
    height: 16px;
  }

  .divider {
    width: 1px;
    height: 24px;
    background: #e2e8f0;
  }

  .job-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
  }

  .job-label {
    font-size: 1rem;
    font-weight: 600;
    color: #1e293b;
  }

  .separator {
    color: #94a3b8;
    font-weight: 400;
  }

  .job-name {
    font-size: 0.875rem;
    color: #64748b;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .refresh-btn, .cancel-btn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
    outline: none !important;
  }
  
  .refresh-btn:focus, .cancel-btn:focus {
    outline: none !important;
    box-shadow: none !important;
  }

  .refresh-btn {
    background: #3b82f6;
    color: white;
  }

  .refresh-btn:hover:not(:disabled) {
    background: #2563eb;
  }

  .refresh-btn:disabled {
    background: #94a3b8;
    cursor: not-allowed;
  }

  .cancel-btn {
    background: #ef4444;
    color: white;
  }

  .cancel-btn:hover:not(:disabled) {
    background: #dc2626;
  }

  .cancel-btn:disabled {
    background: #94a3b8;
    cursor: not-allowed;
  }

  .refresh-btn svg, .cancel-btn svg {
    width: 16px;
    height: 16px;
  }

  .spinning {
    animation: spin 1s linear infinite;
  }

  .state-badge {
    padding: 0.375rem 0.875rem;
    border-radius: 20px;
    color: white;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.025em;
  }

  /* Error Container */
  .error-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    gap: 1rem;
  }

  .error-container svg {
    width: 48px;
    height: 48px;
    color: #ef4444;
  }

  .error-container h2 {
    margin: 0;
    font-size: 1.25rem;
    color: #1e293b;
  }

  .error-container p {
    margin: 0;
    color: #64748b;
  }

  .error-container button {
    padding: 0.5rem 1rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
  }

  .error-container button:hover {
    background: #2563eb;
  }

  /* Tabs */
  .tabs {
    background: white;
    border-bottom: 1px solid #e2e8f0;
    display: flex;
    padding: 0 1.5rem;
    gap: 0.5rem;
  }

  .tab {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.875rem 1rem;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: #64748b;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
    outline: none !important;
  }
  
  .tab:focus {
    outline: none !important;
    box-shadow: none !important;
  }

  .tab:hover {
    color: #475569;
  }

  .tab.active {
    color: #3b82f6;
    border-bottom-color: #3b82f6;
  }

  .tab svg {
    width: 16px;
    height: 16px;
  }

  /* Content */
  .content {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
  }

  /* Info Grid */
  .info-container {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 1rem;
  }

  .info-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    transition: all 0.2s ease;
  }
  
  .info-card:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    transform: translateY(-2px);
  }

  .card-title {
    margin: 0 0 1.25rem 0;
    font-size: 0.7rem;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .card-title::before {
    content: '';
    width: 3px;
    height: 14px;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    border-radius: 2px;
  }

  .info-row {
    display: grid;
    grid-template-columns: 110px 1fr;
    gap: 1rem;
    padding: 0.875rem 0.5rem;
    border-bottom: 1px solid #f8fafc;
    transition: background 0.15s ease;
  }
  
  .info-row:hover {
    background: #fafbfc;
    border-radius: 6px;
    margin: 0 -0.5rem;
    padding: 0.875rem 0.5rem;
  }

  .info-row:last-child {
    border-bottom: none;
  }

  .info-row.full-width {
    grid-column: 1 / -1;
  }

  .info-label {
    font-size: 0.85rem;
    font-weight: 600;
    color: #94a3b8;
    display: flex;
    align-items: center;
  }

  .info-value {
    font-size: 0.9rem;
    color: #0f172a;
    word-break: break-word;
    font-weight: 500;
    display: flex;
    align-items: center;
  }

  .info-value.mono {
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    background: linear-gradient(135deg, #f8fafc, #f1f5f9);
    padding: 0.375rem 0.625rem;
    border-radius: 6px;
    font-size: 0.825rem;
    border: 1px solid #e2e8f0;
    font-weight: 400;
  }

  /* Output Section */
  .output-section {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .output-content {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 1.25rem;
    margin: 0;
    font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', monospace;
    font-size: 0.8rem;
    line-height: 1.6;
    white-space: pre-wrap;
    overflow: auto;
    flex: 1;
  }

  .output-content.error {
    background: #fef2f2;
    border-color: #fecaca;
    color: #991b1b;
  }

  .output-content.script {
    background: #f0f9ff;
    border-color: #bae6fd;
  }

  /* States */
  .loading-state,
  .empty-state,
  .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    gap: 1rem;
  }

  .empty-state {
    color: #94a3b8;
  }

  .empty-state svg {
    width: 48px;
    height: 48px;
    opacity: 0.3;
  }

  .error-state {
    color: #ef4444;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid #e2e8f0;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .retry-btn {
    padding: 0.375rem 0.875rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .retry-btn:hover {
    background: #2563eb;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* Mobile */
  @media (max-width: 768px) {
    .header {
      padding: 1rem;
      flex-direction: column;
      align-items: stretch;
      gap: 0.75rem;
    }

    .header-right {
      justify-content: flex-end;
    }

    .tabs {
      padding: 0 1rem;
      overflow-x: auto;
    }

    .content {
      padding: 1rem;
    }

    .info-container {
      grid-template-columns: 1fr;
    }

    .info-row {
      grid-template-columns: 1fr;
      gap: 0.25rem;
    }
  }
  /* Layout with sidebar */
  .page-layout {
    display: flex;
    height: 100%;
    position: relative;
  }
  
  .job-content-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  
  /* Mobile sidebar overlay */
  .mobile-sidebar-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: white;
    z-index: 1000;
    display: flex;
    flex-direction: column;
  }
  
  .mobile-toggle-btn {
    position: absolute;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 24px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
    transition: all 0.2s ease;
  }
  
  .mobile-toggle-btn:hover {
    background: #2563eb;
    transform: translateX(-50%) translateY(-2px);
    box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4);
  }
  
  .mobile-toggle-btn svg {
    width: 18px;
    height: 18px;
  }
  
  .mobile-sidebar-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.15s ease;
    outline: none !important;
  }
  
  .mobile-sidebar-btn:focus {
    outline: none !important;
    box-shadow: none !important;
  }
  
  .mobile-sidebar-btn:hover {
    background: #f1f5f9;
    border-color: #cbd5e1;
  }
  
  .mobile-sidebar-btn svg {
    width: 20px;
    height: 20px;
    color: #64748b;
  }
</style>