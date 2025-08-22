<script>
  export let job;
  export let loadJobOutput;
  export let onClose;
  
  let outputData = null;
  let loadingOutput = false;
  let outputError = null;
  let activeTab = 'info';
  
  $: if (job && (activeTab === 'stdout' || activeTab === 'stderr') && !outputData) {
    loadOutput();
  }
  
  async function loadOutput() {
    if (!job) return;
    
    loadingOutput = true;
    outputError = null;
    
    try {
      outputData = await loadJobOutput(job.job_id, job.hostname);
      
      // Handle case where output is already loading from another request
      if (outputData && outputData.loading) {
        // Poll for output every second
        setTimeout(() => loadOutput(), 1000);
      }
    } catch (error) {
      console.error('Error loading job output:', error);
      outputError = error.message || 'Failed to load output';
    } finally {
      if (!(outputData && outputData.loading)) {
        loadingOutput = false;
      }
    }
  }
  
  function retryLoadOutput() {
    outputData = null;
    loadOutput();
  }
  
  function formatTime(timeStr) {
    if (!timeStr || timeStr === 'N/A') return 'N/A';
    try {
      return new Date(timeStr).toLocaleString();
    } catch {
      return timeStr;
    }
  }
  
  function getStateColor(state) {
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
  
  function getStateLabel(state) {
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
  
  function formatFileSize(bytes) {
    if (bytes === null || bytes === undefined) return 'Unknown';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  }
  
  function formatDate(dateStr) {
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
    <div class="title">
      <h2>Job {job.job_id}: {job.name}</h2>
      <span 
        class="state-badge" 
        style="background-color: {getStateColor(job.state)}"
      >
        {getStateLabel(job.state)}
      </span>
    </div>
    <button 
      class="close-btn" 
      on:click={onClose}
      aria-label="Close job details"
    >
      ×
    </button>
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
          <h3>Files & Directories</h3>
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
        </div>
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

  .header {
    padding: 1.5rem;
    border-bottom: 1px solid #dee2e6;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }

  .title {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .title h2 {
    margin: 0;
    color: #495057;
  }

  .state-badge {
    color: white;
    padding: 0.4rem 1rem;
    border-radius: 1rem;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
  }

  .close-btn {
    background: #6c757d;
    color: white;
    border: none;
    width: 2rem;
    height: 2rem;
    border-radius: 50%;
    font-size: 1.2rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .close-btn:hover {
    background: #5a6268;
  }
  
  .close-btn:focus {
    outline: 2px solid #007bff;
    outline-offset: 2px;
  }

  .tabs {
    display: flex;
    border-bottom: 1px solid #dee2e6;
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

  .info-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
  }

  .info-section {
    background: #f8f9fa;
    padding: 1.5rem;
    border-radius: 0.5rem;
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
  }

  .output-content.stderr {
    background: #fff5f5;
    color: #c53030;
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
