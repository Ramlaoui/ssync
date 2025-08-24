<script lang="ts">
  import type { JobInfo, JobOutputResponse, JobScriptResponse } from '../types/api';
  
  export let job: JobInfo;
  export let loadJobOutput: (jobId: string, hostname: string) => Promise<JobOutputResponse | { loading: true }>;
  export let onClose: () => void;
  
  let outputData: JobOutputResponse | null = null;
  let loadingOutput = false;
  let outputError: string | null = null;
  let scriptData: JobScriptResponse | null = null;
  let loadingScript = false;
  let scriptError: string | null = null;
  let activeTab: 'info' | 'stdout' | 'stderr' | 'script' = 'info';
  
  $: if (job && (activeTab === 'stdout' || activeTab === 'stderr') && !outputData) {
    loadOutput();
  }
  
  $: if (job && activeTab === 'script' && !scriptData) {
    loadScript();
  }
  
  async function loadOutput(): Promise<void> {
    if (!job) return;
    
    loadingOutput = true;
    outputError = null;
    
    try {
      const result = await loadJobOutput(job.job_id, job.hostname);
      
      // Handle case where output is already loading from another request
      if ('loading' in result && result.loading) {
        // Poll for output every second
        setTimeout(() => loadOutput(), 1000);
      } else {
        outputData = result as JobOutputResponse;
      }
    } catch (error: unknown) {
      console.error('Error loading job output:', error);
      outputError = (error as Error).message || 'Failed to load output';
    } finally {
      if (!(outputData && 'loading' in outputData)) {
        loadingOutput = false;
      }
    }
  }
  
  function retryLoadOutput(): void {
    outputData = null;
    loadOutput();
  }
  
  async function loadScript(): Promise<void> {
    if (!job) return;
    
    loadingScript = true;
    scriptError = null;
    
    try {
      const response = await fetch(`/api/jobs/${job.job_id}/script?host=${encodeURIComponent(job.hostname)}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      scriptData = await response.json() as JobScriptResponse;
    } catch (error: unknown) {
      console.error('Error loading job script:', error);
      scriptError = (error as Error).message || 'Failed to load script';
    } finally {
      loadingScript = false;
    }
  }
  
  function retryLoadScript(): void {
    scriptData = null;
    loadScript();
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
      case 'R': return '#28a745';
      case 'PD': return '#ffc107';
      case 'CD': return '#6f42c1';
      case 'F': return '#dc3545';
      case 'CA': return '#6c757d';
      case 'TO': return '#fd7e14';
      default: return '#17a2b8';
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
  
  function formatFileSize(bytes: number | null | undefined): string {
    if (bytes === null || bytes === undefined) return 'Unknown';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  }
  
  function formatDate(dateStr: string | null): string {
    if (!dateStr) return 'Unknown';
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  }
</script>

<div class="job-detail">
  <div class="header">
    <div class="title-row">
      <div class="job-info">
        <div class="job-header">
          <button 
            class="back-btn" 
            on:click={onClose}
            aria-label="Back to job list"
          >
            <svg class="back-arrow" viewBox="0 0 24 24" fill="currentColor">
              <path d="M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z"/>
            </svg>
          </button>
          <div class="job-details">
            <h2>Job {job.job_id}</h2>
            <div class="job-name">{job.name}</div>
          </div>
        </div>
      </div>
      <span 
        class="state-badge" 
        style="background-color: {getStateColor(job.state)}"
      >
        {getStateLabel(job.state)}
      </span>
    </div>
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
        <path d="M13,13H11V7H13M13,17H11V15H13M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z"/>
      </svg>
      Errors
    </button>
    <button 
      class="tab" 
      class:active={activeTab === 'script'}
      on:click={() => activeTab = 'script'}
    >
      <svg class="tab-icon" viewBox="0 0 24 24" fill="currentColor">
        <path d="M8,3A2,2 0 0,0 6,5V9A2,2 0 0,1 4,11H3V13H4A2,2 0 0,1 6,15V19A2,2 0 0,0 8,21H10V19H8V14A2,2 0 0,0 6,12A2,2 0 0,0 8,10V5H10V3M16,3A2,2 0 0,1 18,5V9A2,2 0 0,0 20,11H21V13H20A2,2 0 0,0 18,15V19A2,2 0 0,1 16,21H14V19H16V14A2,2 0 0,1 18,12A2,2 0 0,1 16,10V5H14V3H16Z"/>
      </svg>
      Script
    </button>
  </div>
  
  <div class="content">
    {#if activeTab === 'info'}
      <div class="info-grid">
        <div class="info-section">
          <h3>General</h3>
          <div class="info-item">
            <div class="item-label">Job ID:</div>
            <span>{job.job_id}</span>
          </div>
          <div class="info-item">
            <div class="item-label">Name:</div>
            <span>{job.name}</span>
          </div>
          <div class="info-item">
            <div class="item-label">User:</div>
            <span>{job.user || 'N/A'}</span>
          </div>
          <div class="info-item">
            <div class="item-label">Host:</div>
            <span>{job.hostname}</span>
          </div>
          <div class="info-item">
            <div class="item-label">Partition:</div>
            <span>{job.partition || 'N/A'}</span>
          </div>
        </div>
        
        <div class="info-section">
          <h3>Resources</h3>
          <div class="info-item">
            <div class="item-label">Nodes:</div>
            <span>{job.nodes || 'N/A'}</span>
          </div>
          <div class="info-item">
            <div class="item-label">CPUs:</div>
            <span>{job.cpus || 'N/A'}</span>
          </div>
          <div class="info-item">
            <div class="item-label">Memory:</div>
            <span>{job.memory || 'N/A'}</span>
          </div>
          <div class="info-item">
            <div class="item-label">Time Limit:</div>
            <span>{job.time_limit || 'N/A'}</span>
          </div>
          <div class="info-item">
            <div class="item-label">Runtime:</div>
            <span>{job.runtime || 'N/A'}</span>
          </div>
        </div>
        
        <div class="info-section">
          <h3>Timing</h3>
          <div class="info-item">
            <div class="item-label">Submitted:</div>
            <span>{formatTime(job.submit_time)}</span>
          </div>
          <div class="info-item">
            <div class="item-label">Started:</div>
            <span>{formatTime(job.start_time)}</span>
          </div>
          <div class="info-item">
            <div class="item-label">Ended:</div>
            <span>{formatTime(job.end_time)}</span>
          </div>
          {#if job.reason && job.reason !== 'N/A' && job.state === 'PD'}
            <div class="info-item">
              <div class="item-label">Reason:</div>
              <span>{job.reason}</span>
            </div>
          {/if}
        </div>
        
        <div class="info-section full-width">
          <h3>Command & Files</h3>
          {#if job.submit_line && job.submit_line !== 'N/A'}
            <div class="info-item">
              <div class="item-label">Submit Line:</div>
              <span class="monospace">{job.submit_line}</span>
            </div>
          {/if}
          <div class="info-item">
            <div class="item-label">Work Dir:</div>
            <span class="monospace">{job.work_dir || 'N/A'}</span>
          </div>
          <div class="info-item">
            <div class="item-label">Output File:</div>
            <span class="monospace">{job.stdout_file || 'N/A'}</span>
          </div>
          <div class="info-item">
            <div class="item-label">Error File:</div>
            <span class="monospace">{job.stderr_file || 'N/A'}</span>
          </div>
          {#if job.node_list && job.node_list !== 'N/A'}
            <div class="info-item">
              <div class="item-label">Node List:</div>
              <span class="monospace">{job.node_list}</span>
            </div>
          {/if}
        </div>
        
        {#if job.alloc_tres || job.req_tres}
          <div class="info-section">
            <h3>Resource Allocation</h3>
            {#if job.req_tres && job.req_tres !== 'N/A'}
              <div class="info-item">
                <div class="item-label">Requested:</div>
                <span class="monospace">{job.req_tres}</span>
              </div>
            {/if}
            {#if job.alloc_tres && job.alloc_tres !== 'N/A'}
              <div class="info-item">
                <div class="item-label">Allocated:</div>
                <span class="monospace">{job.alloc_tres}</span>
              </div>
            {/if}
          </div>
        {/if}
        
        {#if job.cpu_time || job.total_cpu || job.max_rss || job.consumed_energy}
          <div class="info-section">
            <h3>Performance Metrics</h3>
            {#if job.cpu_time && job.cpu_time !== 'N/A'}
              <div class="info-item">
                <div class="item-label">CPU Time:</div>
                <span>{job.cpu_time}</span>
              </div>
            {/if}
            {#if job.total_cpu && job.total_cpu !== 'N/A'}
              <div class="info-item">
                <div class="item-label">Total CPU:</div>
                <span>{job.total_cpu}</span>
              </div>
            {/if}
            {#if job.max_rss && job.max_rss !== 'N/A'}
              <div class="info-item">
                <div class="item-label">Max Memory:</div>
                <span>{job.max_rss}</span>
              </div>
            {/if}
            {#if job.consumed_energy && job.consumed_energy !== 'N/A'}
              <div class="info-item">
                <div class="item-label">Energy:</div>
                <span>{job.consumed_energy}</span>
              </div>
            {/if}
          </div>
        {/if}
      </div>
      
    {:else if activeTab === 'stdout'}
      <div class="output-section">
        {#if loadingOutput}
          <div class="loading">Loading output...</div>
        {:else if outputError}
          <div class="error">
            Failed to load output: {outputError}
            <button class="retry-output-btn" on:click={retryLoadOutput}>Retry</button>
          </div>
        {:else if outputData?.stdout}
          {#if outputData.stdout_metadata?.exists}
            <div class="output-controls">
              <div class="file-info">
                <span class="file-size">{formatFileSize(outputData.stdout_metadata.size_bytes)}</span>
                <span class="modified-date">Modified: {formatDate(outputData.stdout_metadata.last_modified)}</span>
              </div>
              <div class="actions">
                <a 
                  href={outputData.stdout_metadata.access_path} 
                  class="download-btn" 
                  target="_blank" 
                  rel="noopener noreferrer"
                >View Full</a>
                <a 
                  href={outputData.stdout_metadata.access_path + "&download=true"} 
                  class="download-btn download" 
                  download
                >Download</a>
              </div>
            </div>
          {/if}
          <pre class="output-content">{outputData.stdout}</pre>
        {:else}
          <div class="no-output">No output available</div>
        {/if}
      </div>
      
    {:else if activeTab === 'stderr'}
      <div class="output-section">
        {#if loadingOutput}
          <div class="loading">Loading errors...</div>
        {:else if outputError}
          <div class="error">
            Failed to load errors: {outputError}
            <button class="retry-output-btn" on:click={retryLoadOutput}>Retry</button>
          </div>
        {:else if outputData?.stderr}
          {#if outputData.stderr_metadata?.exists}
            <div class="output-controls">
              <div class="file-info">
                <span class="file-size">{formatFileSize(outputData.stderr_metadata.size_bytes)}</span>
                <span class="modified-date">Modified: {formatDate(outputData.stderr_metadata.last_modified)}</span>
              </div>
              <div class="actions">
                <a 
                  href={outputData.stderr_metadata.access_path} 
                  class="download-btn" 
                  target="_blank" 
                  rel="noopener noreferrer"
                >View Full</a>
                <a 
                  href={outputData.stderr_metadata.access_path + "&download=true"} 
                  class="download-btn download" 
                  download
                >Download</a>
              </div>
            </div>
          {/if}
          <pre class="output-content stderr">{outputData.stderr}</pre>
        {:else}
          <div class="no-output">No errors</div>
        {/if}
      </div>
      
    {:else if activeTab === 'script'}
      <div class="output-section">
        {#if loadingScript}
          <div class="loading">Loading batch script...</div>
        {:else if scriptError}
          <div class="error">
            Failed to load batch script: {scriptError}
            <button class="retry-output-btn" on:click={retryLoadScript}>Retry</button>
          </div>
        {:else if scriptData?.script_content}
          <div class="output-controls">
            <div class="file-info">
              <span class="file-size">{scriptData.content_length} characters</span>
              <span class="modified-date">Job {scriptData.job_id} batch script</span>
            </div>
            <div class="actions">
              <button 
                class="download-btn" 
                on:click={() => {
                  if (scriptData) {
                    const blob = new Blob([scriptData.script_content], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `job_${job.job_id}_script.sh`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                  }
                }}
              >Download</button>
            </div>
          </div>
          <pre class="output-content script">{scriptData.script_content}</pre>
        {:else}
          <div class="no-output">Batch script not available</div>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .job-detail {
    background: white;
    border-radius: 0.5rem;
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  @media (max-width: 768px) {
    .job-detail {
      border-radius: 0;
      box-shadow: none;
      height: 100vh;
    }
  }

  .header {
    padding: 1.5rem;
    border-bottom: 1px solid #dee2e6;
  }

  @media (max-width: 768px) {
    .header {
      padding: 1rem;
      position: sticky;
      top: 0;
      background: white;
      z-index: 10;
      border-bottom: 2px solid #dee2e6;
    }
  }

  .title-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
  }

  @media (max-width: 768px) {
    .title-row {
      flex-direction: column;
      gap: 0.75rem;
      align-items: flex-start;
    }
  }

  .job-info {
    flex: 1;
    min-width: 0;
  }

  .job-header {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
  }

  @media (max-width: 768px) {
    .job-header {
      width: 100%;
      align-items: center;
    }
  }

  .job-details {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .job-details h2 {
    margin: 0;
    color: #495057;
    font-size: 1.25rem;
    line-height: 1.2;
  }

  @media (max-width: 768px) {
    .job-details h2 {
      font-size: 1.1rem;
    }
  }

  .job-name {
    color: #6c757d;
    font-size: 0.9rem;
    word-wrap: break-word;
    line-height: 1.3;
    margin: 0;
  }

  @media (max-width: 768px) {
    .job-name {
      font-size: 0.85rem;
      max-width: 280px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }

  .state-badge {
    color: white;
    padding: 0.4rem 1rem;
    border-radius: 1rem;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    align-self: flex-start;
    margin-top: 0.2rem;
  }

  @media (max-width: 768px) {
    .state-badge {
      padding: 0.3rem 0.8rem;
      font-size: 0.75rem;
      align-self: flex-end;
      margin-top: -0.5rem;
    }
  }

  .back-btn {
    background: rgba(59, 130, 246, 0.1);
    color: #3b82f6;
    border: 1px solid rgba(59, 130, 246, 0.2);
    width: 2rem;
    height: 2rem;
    border-radius: 0.5rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    flex-shrink: 0;
    margin-right: 0.5rem;
  }

  .back-btn:hover {
    background: rgba(59, 130, 246, 0.15);
    border-color: rgba(59, 130, 246, 0.4);
    color: #2563eb;
  }

  .back-arrow {
    width: 1.25rem;
    height: 1.25rem;
  }
  
  .close-btn:focus {
    outline: 2px solid #007bff;
    outline-offset: 2px;
  }

  .tabs {
    display: flex;
    border-bottom: 1px solid #dee2e6;
    overflow-x: auto;
    scrollbar-width: none;
    -ms-overflow-style: none;
  }

  .tabs::-webkit-scrollbar {
    display: none;
  }

  @media (max-width: 768px) {
    .tabs {
      position: sticky;
      top: 73px;
      background: white;
      z-index: 9;
      border-bottom: 2px solid #dee2e6;
      padding: 0 1rem;
      margin: 0 -1rem;
    }
  }

  .tab {
    background: none;
    border: none;
    padding: 1rem 1.5rem;
    cursor: pointer;
    border-bottom: 3px solid transparent;
    transition: all 0.2s;
    color: #6c757d;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    white-space: nowrap;
    flex-shrink: 0;
  }

  @media (max-width: 768px) {
    .tab {
      padding: 0.75rem 1rem;
      font-size: 0.9rem;
    }
  }

  @media (max-width: 480px) {
    .tab {
      padding: 0.75rem 0.75rem;
      gap: 0.25rem;
    }

    .tab-icon {
      width: 14px;
      height: 14px;
    }
  }

  .tab-icon {
    width: 16px;
    height: 16px;
  }

  .tab:hover {
    background: #f8f9fa;
  }

  .tab.active {
    color: #007bff;
    border-bottom-color: #007bff;
  }

  .content {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
  }

  @media (max-width: 768px) {
    .content {
      padding: 1rem;
      -webkit-overflow-scrolling: touch;
    }
  }

  .info-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
  }

  @media (max-width: 768px) {
    .info-grid {
      grid-template-columns: 1fr;
      gap: 1rem;
    }
  }

  .info-section {
    background: #f8f9fa;
    padding: 1.5rem;
    border-radius: 0.5rem;
  }

  @media (max-width: 768px) {
    .info-section {
      padding: 1rem;
      border-radius: 0.375rem;
    }
  }

  .info-section.full-width {
    grid-column: 1 / -1;
  }

  .info-section h3 {
    margin: 0 0 1rem 0;
    color: #495057;
    font-size: 1.1rem;
  }

  .info-item {
    display: flex;
    margin-bottom: 0.75rem;
    align-items: flex-start;
  }

  .info-item .item-label {
    font-weight: 600;
    color: #495057;
    width: 120px;
    flex-shrink: 0;
    margin-right: 1rem;
  }

  @media (max-width: 768px) {
    .info-item {
      flex-direction: column;
      gap: 0.25rem;
      margin-bottom: 1rem;
    }

    .info-item .item-label {
      width: auto;
      margin-right: 0;
      font-size: 0.9rem;
    }

    .info-item span {
      padding-left: 0.5rem;
      font-size: 0.95rem;
    }
  }

  .info-item span {
    color: #6c757d;
    word-break: break-all;
  }

  .monospace {
    font-family: 'Courier New', monospace;
    background: rgba(0,0,0,0.05);
    padding: 0.2rem 0.4rem;
    border-radius: 0.2rem;
  }

  .output-section {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .output-content {
    flex: 1;
    background: #f8f9fa;
    padding: 1rem;
    border-radius: 0.5rem;
    overflow: auto;
    font-family: 'Courier New', monospace;
    font-size: 0.9rem;
    line-height: 1.4;
    white-space: pre-wrap;
    margin: 0;
    -webkit-overflow-scrolling: touch;
  }

  @media (max-width: 768px) {
    .output-content {
      font-size: 0.8rem;
      padding: 0.75rem;
      line-height: 1.3;
    }
  }

  .output-content.stderr {
    background: #fff5f5;
    color: #c53030;
  }

  .output-content.script {
    background: #f0f8ff;
    border-left: 4px solid #007bff;
  }

  .loading, .no-output {
    padding: 2rem;
    text-align: center;
    color: #6c757d;
  }
  
  .loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
  }
  
  .loading::before {
    content: "";
    display: block;
    width: 30px;
    height: 30px;
    border: 3px solid rgba(0,0,0,0.1);
    border-radius: 50%;
    border-top-color: #007bff;
    animation: spin 1s linear infinite;
  }
  
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .error {
    color: #721c24;
    background: #f8d7da;
    border-radius: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem;
  }
  
  .output-controls {
    background: #f8f9fa;
    border-radius: 0.5rem 0.5rem 0 0;
    padding: 0.75rem 1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #dee2e6;
    margin-bottom: -1px;
  }

  @media (max-width: 768px) {
    .output-controls {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.75rem;
      padding: 0.75rem;
    }

    .file-info {
      order: 1;
    }

    .actions {
      order: 2;
      align-self: flex-end;
    }
  }
  
  .file-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .file-size {
    font-weight: 600;
    color: #495057;
  }
  
  .modified-date {
    font-size: 0.8rem;
    color: #6c757d;
  }
  
  .actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .download-btn {
    padding: 0.35rem 0.75rem;
    border-radius: 0.25rem;
    text-decoration: none;
    font-size: 0.9rem;
    font-weight: 600;
    background: #e9ecef;
    color: #495057;
    transition: all 0.2s;
    border: none;
    cursor: pointer;
  }

  @media (max-width: 768px) {
    .download-btn {
      font-size: 0.85rem;
      padding: 0.4rem 0.75rem;
    }
  }
  
  .download-btn:hover {
    background: #dee2e6;
  }
  
  .download-btn.download {
    background: #007bff;
    color: white;
  }
  
  .download-btn.download:hover {
    background: #0069d9;
  }
  
  .retry-output-btn {
    background: #dc3545;
    color: white;
    border: none;
    padding: 0.25rem 0.75rem;
    border-radius: 0.25rem;
    cursor: pointer;
    margin-left: 1rem;
    transition: background-color 0.2s;
    font-size: 0.9rem;
  }
  
  .retry-output-btn:hover {
    background: #c82333;
  }
</style>
