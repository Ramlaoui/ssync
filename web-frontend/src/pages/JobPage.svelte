<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { push } from "svelte-spa-router";
  import { jobsStore } from "../stores/jobs";
  import { api } from "../services/api";
  import type { JobInfo, JobOutputResponse, JobScriptResponse } from "../types/api";
  import OutputViewer from "../components/OutputViewer.svelte";

  export let params: { id?: string; host?: string } = {};

  let job: JobInfo | null = null;
  let loading = true;
  let error: string | null = null;
  let refreshInterval: ReturnType<typeof setInterval>;
  let mounted = true;
  
  // Tab state
  let activeTab: 'info' | 'stdout' | 'stderr' | 'script' = 'info';
  
  // Output data
  let outputData: JobOutputResponse | null = null;
  let loadingOutput = false;
  let outputError: string | null = null;
  
  // Script data
  let scriptData: JobScriptResponse | null = null;
  let loadingScript = false;
  let scriptError: string | null = null;

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

  function handleClose() {
    push("/");
  }

  function handleRefresh() {
    loadJob(true);
  }

  function getStateColor(state: string): string {
    switch (state) {
      case "R": return "#28a745";
      case "PD": return "#ffc107";
      case "CD": return "#6f42c1";
      case "F": return "#dc3545";
      case "CA": return "#6c757d";
      case "TO": return "#fd7e14";
      default: return "#17a2b8";
    }
  }

  function getStateLabel(state: string): string {
    const labels: Record<string, string> = {
      'R': 'RUNNING',
      'PD': 'PENDING',
      'CD': 'COMPLETED',
      'F': 'FAILED',
      'CA': 'CANCELLED',
      'TO': 'TIMEOUT',
      'CG': 'COMPLETING',
      'CF': 'CONFIGURING'
    };
    return labels[state] || state;
  }

  function parseGPUs(tres: string | null): string {
    if (!tres) return 'N/A';
    // Look for gpu or gres/gpu in the TRES string
    const gpuMatch = tres.match(/(?:gres\/)?gpu(?::[^=]*)?=(\d+)/i);
    return gpuMatch ? gpuMatch[1] : 'N/A';
  }


  let lastParams = { id: '', host: '' };

  onMount(() => {
    mounted = true;
    // Store initial params
    lastParams = { id: params.id || '', host: params.host || '' };
    loadJob();
    
    // Auto-refresh every 10 seconds for active jobs
    refreshInterval = setInterval(() => {
      if (job && ["R", "PD", "CF", "CG"].includes(job.state)) {
        loadJob(true);
      }
    }, 10000);
  });

  onDestroy(() => {
    mounted = false;
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
    // Clear data on unmount
    job = null;
    outputData = null;
    scriptData = null;
  });

  // Only reload if params actually changed
  $: if (mounted && params.id && params.host && 
      (params.id !== lastParams.id || params.host !== lastParams.host)) {
    lastParams = { id: params.id, host: params.host };
    loadJob();
  }
  
  $: if (job && (activeTab === 'stdout' || activeTab === 'stderr') && !outputData) {
    loadOutput();
  }
  
  $: if (job && activeTab === 'script' && !scriptData) {
    loadScript();
  }
</script>

<div class="job-page">
  <header class="job-header">
    <div class="header-content">
      <div class="nav-section">
        <button class="back-button" on:click={handleClose} aria-label="Back to jobs list">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z" />
          </svg>
          <span>Jobs</span>
        </button>
        
        {#if params.id && params.host}
          <div class="breadcrumb-section">
            <nav class="breadcrumb" aria-label="Breadcrumb">
              <span class="separator">/</span>
              <span class="current">{params.host}</span>
              <span class="separator">/</span>
              <span class="current">Job {params.id}</span>
            </nav>
          </div>
        {/if}
      </div>
      
      <button 
        class="refresh-button" 
        on:click={handleRefresh} 
        disabled={loading}
        aria-label="Refresh job data"
      >
        <svg class="refresh-icon" class:spinning={loading} viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,6V9L16,5L12,1V4A8,8 0 0,0 4,12C4,13.57 4.46,15.03 5.24,16.26L6.7,14.8C6.25,13.97 6,13 6,12A6,6 0 0,1 12,6M18.76,7.74L17.3,9.2C17.74,10.04 18,11 18,12A6,6 0 0,1 12,18V15L8,19L12,23V20A8,8 0 0,0 20,12C20,10.43 19.54,8.97 18.76,7.74Z" />
        </svg>
        <span>{loading ? "Refreshing..." : "Refresh"}</span>
      </button>
    </div>
  </header>

  <div class="job-content">
    {#if error && !job}
      <div class="error-container">
        <div class="error-box">
          <svg class="error-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
          </svg>
          <h2>Unable to Load Job</h2>
          <p>{error}</p>
          <div class="error-actions">
            <button on:click={handleRefresh} class="retry-button">
              Try Again
            </button>
            <button on:click={handleClose} class="back-button-alt">
              Back to Jobs
            </button>
          </div>
        </div>
      </div>
    {:else if job}
      <div class="job-detail-container">
        <div class="job-info-header">
          <div class="job-title-section">
            <h1>Job {job.job_id}</h1>
            <p class="job-name">{job.name}</p>
          </div>
          <span 
            class="state-badge" 
            style="background-color: {getStateColor(job.state)}"
          >
            {getStateLabel(job.state)}
          </span>
        </div>

        <div class="tabs">
          <button 
            class="tab" 
            class:active={activeTab === 'info'}
            on:click={() => activeTab = 'info'}
          >
            <svg class="tab-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M14,17H7V15H14M17,13H7V11H17M17,9H7V7H17M19,3H5C3.89,3 3,3.89 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5C21,3.89 20.1,3 19,3Z"/>
            </svg>
            Info
          </button>
          <button 
            class="tab" 
            class:active={activeTab === 'stdout'}
            on:click={() => activeTab = 'stdout'}
          >
            <svg class="tab-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
            </svg>
            Output
          </button>
          <button 
            class="tab" 
            class:active={activeTab === 'stderr'}
            on:click={() => activeTab = 'stderr'}
          >
            <svg class="tab-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M13,9H11V7H13M13,17H11V11H13M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z"/>
            </svg>
            Errors
          </button>
          <button 
            class="tab" 
            class:active={activeTab === 'script'}
            on:click={() => activeTab = 'script'}
          >
            <svg class="tab-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M14.6,16.6L19.2,12L14.6,7.4L16,6L22,12L16,18L14.6,16.6M9.4,16.6L4.8,12L9.4,7.4L8,6L2,12L8,18L9.4,16.6Z"/>
            </svg>
            Script
          </button>
        </div>

        <div class="tab-content">
          {#if activeTab === 'info'}
            <div class="info-grid">
              <div class="info-section">
                <h3>General</h3>
                <div class="info-row">
                  <span class="label">Job ID:</span>
                  <span class="value">{job.job_id}</span>
                </div>
                <div class="info-row">
                  <span class="label">Name:</span>
                  <span class="value">{job.name}</span>
                </div>
                <div class="info-row">
                  <span class="label">User:</span>
                  <span class="value">{job.user || 'N/A'}</span>
                </div>
                <div class="info-row">
                  <span class="label">Host:</span>
                  <span class="value">{job.hostname}</span>
                </div>
                <div class="info-row">
                  <span class="label">Partition:</span>
                  <span class="value">{job.partition || 'N/A'}</span>
                </div>
                {#if job.work_dir}
                <div class="info-row">
                  <span class="label">Work Dir:</span>
                  <span class="value work-dir" title={job.work_dir}>{job.work_dir}</span>
                </div>
                {/if}
                {#if job.reason}
                <div class="info-row">
                  <span class="label">Reason:</span>
                  <span class="value">{job.reason}</span>
                </div>
                {/if}
              </div>

              <div class="info-section">
                <h3>Resources</h3>
                <div class="info-row">
                  <span class="label">Nodes:</span>
                  <span class="value">{job.nodes || 'N/A'}</span>
                </div>
                <div class="info-row">
                  <span class="label">CPUs:</span>
                  <span class="value">{job.cpus || 'N/A'}</span>
                </div>
                <div class="info-row">
                  <span class="label">Memory:</span>
                  <span class="value">{job.memory || 'N/A'}</span>
                </div>
                <div class="info-row">
                  <span class="label">GPUs:</span>
                  <span class="value">{parseGPUs(job.alloc_tres || job.req_tres)}</span>
                </div>
                <div class="info-row">
                  <span class="label">Time Limit:</span>
                  <span class="value">{job.time_limit || 'N/A'}</span>
                </div>
                <div class="info-row">
                  <span class="label">Runtime:</span>
                  <span class="value">{job.runtime || 'N/A'}</span>
                </div>
              </div>

              <div class="info-section">
                <h3>Timing</h3>
                <div class="info-row">
                  <span class="label">Submitted:</span>
                  <span class="value">{job.submit_time ? new Date(job.submit_time).toLocaleString() : 'N/A'}</span>
                </div>
                <div class="info-row">
                  <span class="label">Started:</span>
                  <span class="value">{job.start_time ? new Date(job.start_time).toLocaleString() : 'N/A'}</span>
                </div>
                <div class="info-row">
                  <span class="label">Ended:</span>
                  <span class="value">{job.end_time ? new Date(job.end_time).toLocaleString() : 'N/A'}</span>
                </div>
              </div>

              {#if job.node_list}
              <div class="info-section">
                <h3>Allocation</h3>
                <div class="info-row">
                  <span class="label">Node List:</span>
                  <span class="value">{job.node_list}</span>
                </div>
                {#if job.alloc_tres}
                <div class="info-row">
                  <span class="label">Allocated TRES:</span>
                  <span class="value" title={job.alloc_tres}>{job.alloc_tres}</span>
                </div>
                {/if}
                {#if job.req_tres}
                <div class="info-row">
                  <span class="label">Requested TRES:</span>
                  <span class="value" title={job.req_tres}>{job.req_tres}</span>
                </div>
                {/if}
              </div>
              {/if}
            </div>
          {:else if activeTab === 'stdout'}
            <OutputViewer
              content={outputData?.stdout}
              loading={loadingOutput}
              error={outputError}
              emptyMessage="No output available"
              title="Standard Output"
              fileSize={outputData?.stdout_metadata?.size_bytes}
              modifiedDate={outputData?.stdout_metadata?.last_modified}
              fileName={`job_${params.id}_stdout.txt`}
              wrapLines={false}
              maxHeight="600px"
            />
          {:else if activeTab === 'stderr'}
            <OutputViewer
              content={outputData?.stderr}
              loading={loadingOutput}
              error={outputError}
              emptyMessage="No errors reported"
              title="Standard Error"
              fileSize={outputData?.stderr_metadata?.size_bytes}
              modifiedDate={outputData?.stderr_metadata?.last_modified}
              fileName={`job_${params.id}_stderr.txt`}
              wrapLines={false}
              maxHeight="600px"
            />
          {:else if activeTab === 'script'}
            <OutputViewer
              content={scriptData?.script_content}
              loading={loadingScript}
              error={scriptError}
              emptyMessage="No script available"
              title="Job Script"
              fileSize={scriptData?.content_length}
              modifiedDate={null}
              fileName={`job_${params.id}_script.sh`}
              syntaxHighlight="bash"
              wrapLines={false}
              maxHeight="600px"
            />
          {/if}
        </div>
      </div>
    {:else}
      <div class="loading-container">
        <div class="loading-spinner"></div>
        <p>Loading job details...</p>
      </div>
    {/if}
  </div>
</div>

<style>
  .job-page {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: #f9fafb;
  }

  .job-header {
    background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
    color: white;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    position: sticky;
    top: 0;
    z-index: 100;
  }

  .header-content {
    padding: 1rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    max-width: 1600px;
    margin: 0 auto;
    width: 100%;
    gap: 1rem;
  }

  .nav-section {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex: 1;
  }

  .breadcrumb-section {
    display: flex;
    align-items: center;
  }

  .back-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.2);
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 0.9rem;
    font-weight: 500;
  }

  .back-button:hover {
    background: rgba(255, 255, 255, 0.2);
    transform: translateX(-2px);
  }

  .back-button svg {
    width: 18px;
    height: 18px;
  }

  .breadcrumb {
    display: flex;
    align-items: center;
    font-size: 0.95rem;
    opacity: 0.95;
    font-weight: 400;
  }

  .separator {
    margin: 0 0.5rem;
    opacity: 0.5;
  }

  .current {
    font-weight: 500;
  }

  .refresh-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    border: none;
    color: white;
    padding: 0.6rem 1.2rem;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 0.9rem;
    font-weight: 500;
    box-shadow: 0 2px 4px rgba(16, 185, 129, 0.2);
    flex-shrink: 0;
  }

  .refresh-button:hover:not(:disabled) {
    background: linear-gradient(135deg, #059669 0%, #047857 100%);
    transform: translateY(-1px);
  }

  .refresh-button:disabled {
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    cursor: not-allowed;
  }

  .refresh-icon {
    width: 18px;
    height: 18px;
  }

  .spinning {
    animation: spin 1.5s linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .job-content {
    flex: 1;
    overflow: auto;
    padding: 2rem;
  }

  .job-detail-container {
    max-width: 1200px;
    margin: 0 auto;
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .job-info-header {
    padding: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }

  .job-title-section h1 {
    margin: 0;
    font-size: 1.5rem;
    color: #1f2937;
  }

  .job-name {
    margin: 0.25rem 0 0 0;
    color: #6b7280;
  }

  .state-badge {
    padding: 0.5rem 1rem;
    border-radius: 2rem;
    color: white;
    font-weight: 600;
    font-size: 0.875rem;
  }

  .tabs {
    display: flex;
    border-bottom: 1px solid #e5e7eb;
    background: #f9fafb;
  }

  .tab {
    padding: 1rem 1.5rem;
    background: none;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: #6b7280;
    font-size: 0.9rem;
    font-weight: 500;
    transition: all 0.2s;
    border-bottom: 3px solid transparent;
  }

  .tab:hover {
    color: #374151;
    background: rgba(0, 0, 0, 0.02);
  }

  .tab.active {
    color: #2563eb;
    border-bottom-color: #2563eb;
  }

  .tab-icon {
    width: 18px;
    height: 18px;
  }

  .tab-content {
    padding: 1.5rem;
    min-height: 400px;
  }

  .info-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
  }

  .info-section {
    background: #f9fafb;
    padding: 1.5rem;
    border-radius: 8px;
  }

  .info-section h3 {
    margin: 0 0 1rem 0;
    font-size: 1.1rem;
    color: #374151;
  }

  .info-row {
    display: flex;
    justify-content: space-between;
    padding: 0.5rem 0;
    border-bottom: 1px solid #e5e7eb;
  }

  .info-row:last-child {
    border-bottom: none;
  }

  .label {
    font-weight: 500;
    color: #6b7280;
  }

  .value {
    color: #111827;
    text-align: right;
    word-break: break-word;
  }

  .value.work-dir {
    font-size: 0.85rem;
    font-family: monospace;
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }


  .loading-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
  }

  .loading-spinner {
    border: 4px solid rgba(0, 0, 0, 0.1);
    border-left-color: #3498db;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }

  .error-container {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
  }

  .error-box {
    background: white;
    border-radius: 12px;
    padding: 3rem;
    text-align: center;
    max-width: 500px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  }

  .error-icon {
    width: 64px;
    height: 64px;
    color: #dc3545;
    margin-bottom: 1.5rem;
  }

  .error-box h2 {
    margin: 0 0 1rem 0;
    color: #1f2937;
  }

  .error-box p {
    color: #6b7280;
    margin-bottom: 2rem;
  }

  .error-actions {
    display: flex;
    gap: 1rem;
    justify-content: center;
  }

  .retry-button {
    background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 1rem;
    font-weight: 500;
  }

  .retry-button:hover {
    background: linear-gradient(135deg, #c82333 0%, #a71e2a 100%);
  }

  .back-button-alt {
    background: white;
    color: #6b7280;
    border: 2px solid #e5e7eb;
    padding: 0.75rem 1.5rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 1rem;
    font-weight: 500;
  }

  .back-button-alt:hover {
    background: #f3f4f6;
  }

  @media (max-width: 768px) {
    .header-content {
      padding: 1rem;
      flex-direction: column;
      gap: 1rem;
    }

    .nav-section {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.75rem;
    }

    .job-content {
      padding: 1rem;
    }

    .info-grid {
      grid-template-columns: 1fr;
    }

    .tabs {
      overflow-x: auto;
    }

    .tab {
      padding: 0.75rem 1rem;
      font-size: 0.85rem;
    }

    .tab-icon {
      width: 16px;
      height: 16px;
    }
  }
</style>