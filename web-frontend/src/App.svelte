<script>
  import { onMount } from 'svelte';
  import axios from 'axios';
  import JobList from './components/JobList.svelte';
  import JobDetail from './components/JobDetail.svelte';
  import FilterPanel from './components/FilterPanel.svelte';
  import ErrorBoundary from './components/ErrorBoundary.svelte';

  let hosts = [];
  let jobsByHost = new Map();
  let selectedJob = null;
  let loading = false;
  let hostsLoading = false;
  let error = null;
  let lastRequestId = 0;
  let activeRequests = new Set();
  let filters = {
    host: '',
    user: '',
    since: '1d',
    limit: 20,
    state: '',
    activeOnly: false,
    completedOnly: false
  };

  const API_BASE = '/api';

  onMount(async () => {
    await loadHosts();
    await loadJobs();
    
    // Auto-refresh every 30 seconds
    const interval = setInterval(loadJobs, 30000);
    return () => clearInterval(interval);
  });

  async function loadHosts() {
    if (hostsLoading) return; // Prevent concurrent requests
    
    hostsLoading = true;
    try {
      const response = await axios.get(`${API_BASE}/hosts`);
      hosts = response.data;
    } catch (err) {
      error = `Failed to load hosts: ${err.message}`;
    } finally {
      hostsLoading = false;
    }
  }

  async function loadJobs() {
    const requestId = ++lastRequestId;
    const requestKey = 'loadJobs';
    
    // Cancel if there's already a request in progress
    if (activeRequests.has(requestKey)) {
      return;
    }
    
    activeRequests.add(requestKey);
    loading = true;
    error = null;
    
    try {
      const params = new URLSearchParams();
      if (filters.host) params.append('host', filters.host);
      if (filters.user) params.append('user', filters.user);
      if (filters.since) params.append('since', filters.since);
      if (filters.limit) params.append('limit', filters.limit.toString());
      if (filters.state) params.append('state', filters.state);
      if (filters.activeOnly) params.append('active_only', 'true');
      if (filters.completedOnly) params.append('completed_only', 'true');

      const response = await axios.get(`${API_BASE}/status?${params}`);
      
      // Only update if this is still the latest request
      if (requestId === lastRequestId) {
        // Convert to Map for easier access
        jobsByHost = new Map();
        response.data.forEach(hostData => {
          jobsByHost.set(hostData.hostname, hostData);
        });
        
        jobsByHost = new Map(jobsByHost); // Trigger reactivity
      }
    } catch (err) {
      // Only show error if this is still the latest request
      if (requestId === lastRequestId) {
        error = `Failed to load jobs: ${err.message}`;
      }
    } finally {
      activeRequests.delete(requestKey);
      if (requestId === lastRequestId) {
        loading = false;
      }
    }
  }

  async function loadJobOutput(jobId, hostname) {
    const requestKey = `output-${jobId}-${hostname}`;
    
    // Prevent duplicate requests for the same job output
    if (activeRequests.has(requestKey)) {
      return { loading: true };
    }
    
    activeRequests.add(requestKey);
    try {
      const response = await axios.get(`${API_BASE}/jobs/${jobId}/output?host=${hostname}`);
      
      const data = response.data;
      
      // Add additional info about file access for better debugging
      if (data.stdout === null && data.output_files?.stdout_path) {
        data.stdout = `[No output file found at: ${data.output_files.stdout_path}]`;
      }
      
      if (data.stderr === null && data.output_files?.stderr_path) {
        data.stderr = `[No error file found at: ${data.output_files.stderr_path}]`;
      }
      
      return data;
    } catch (err) {
      console.error('Failed to load job output:', err);
      throw err; // Let JobDetail component handle the error properly
    } finally {
      activeRequests.delete(requestKey);
    }
  }

  function handleFilterChange() {
    // Debounce rapid filter changes
    clearTimeout(filterChangeTimeout);
    filterChangeTimeout = setTimeout(() => {
      loadJobs();
    }, 300);
  }
  
  let filterChangeTimeout;

  function handleJobSelect(job) {
    selectedJob = job;
  }
  
  // Manual refresh handler
  function handleManualRefresh() {
    if (!loading) {
      loadJobs();
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

  function getTotalJobs() {
    let total = 0;
    for (let hostData of jobsByHost.values()) {
      total += hostData.jobs.length;
    }
    return total;
  }
</script>

<ErrorBoundary resetError={() => {
  error = null;
  loading = false;
  loadJobs();
}}>
  <div class="app">
    <header class="header">
      <h1 class="app-title" on:click={() => selectedJob = null}>
        <svg class="logo-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L2 7v10c0 5.55 3.84 10 9 11 1.04-.02 2-.02 3 0 5.16-1 9-5.45 9-11V7l-10-5z"/>
          <path d="M12 8v8m-4-4h8"/>
        </svg>
        SLURM Manager
      </h1>
      <div class="stats">
        <span class="stat">
          {hosts.length} Hosts
        </span>
        <span class="stat">
          {getTotalJobs()} Jobs
        </span>
        <span 
          class="stat refresh-button" 
          class:loading 
          on:click={handleManualRefresh}
          role="button"
          tabindex="0"
          aria-label="Refresh data"
        >
          {loading ? 'Refreshing...' : 'Refresh'}
          <svg class="refresh-icon" class:spinning={loading} viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,6V9L16,5L12,1V4A8,8 0 0,0 4,12C4,13.57 4.46,15.03 5.24,16.26L6.7,14.8C6.25,13.97 6,13 6,12A6,6 0 0,1 12,6M18.76,7.74L17.3,9.2C17.74,10.04 18,11 18,12A6,6 0 0,1 12,18V15L8,19L12,23V20A8,8 0 0,0 20,12C20,10.43 19.54,8.97 18.76,7.74Z"/>
          </svg>
        </span>
      </div>
    </header>

  {#if error}
    <div class="error">
      <svg class="error-icon" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
      </svg>
      {error}
      <button 
        on:click={loadJobs} 
        disabled={loading}
        class="retry-button"
      >
        {loading ? 'Retrying...' : 'Retry'}
      </button>
    </div>
  {/if}

  <div class="main-content">
    <div class="sidebar">
      <FilterPanel 
        bind:filters 
        {hosts}
        on:change={handleFilterChange}
      />
      
      <div class="hosts-section">
        <h3>Hosts</h3>
        {#if hostsLoading && hosts.length === 0}
          <div class="loading-placeholder">Loading hosts...</div>
        {:else}
          {#each hosts as host}
            <div class="host-item" class:active={filters.host === host.hostname}>
              <button 
                class="host-name"
                on:click={() => {
                  filters.host = filters.host === host.hostname ? '' : host.hostname;
                  handleFilterChange();
                }}
                disabled={loading}
                aria-selected={filters.host === host.hostname}
              >
                {host.hostname}
                {#if jobsByHost.has(host.hostname)}
                  <span class="job-count">
                    {jobsByHost.get(host.hostname).jobs.length}
                  </span>
                {/if}
              </button>
            </div>
          {/each}
        {/if}
      </div>
    </div>

    <div class="content">
      {#if selectedJob}
        <JobDetail 
          job={selectedJob} 
          {loadJobOutput}
          onClose={() => selectedJob = null}
        />
      {:else}
        {#if loading && jobsByHost.size === 0}
          <div class="loading-container">
            <div class="loading-spinner"></div>
            <p>Loading jobs...</p>
          </div>
        {:else}
          <div class="job-lists">
            {#each [...jobsByHost.entries()] as [hostname, hostData]}
              <JobList 
                {hostname}
                jobs={hostData.jobs}
                queryTime={hostData.query_time}
                {getStateColor}
                on:jobSelect={(event) => handleJobSelect(event.detail)}
                {loading}
              />
            {/each}
          </div>
        {/if}
      {/if}
    </div>
  </div>
</div>
</ErrorBoundary>

<style>
  .app {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  .header {
    background: #2c3e50;
    color: white;
    padding: 1rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  }

  .app-title {
    margin: 0;
    font-size: 1.5rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    cursor: pointer;
    transition: opacity 0.2s;
  }

  .app-title:hover {
    opacity: 0.8;
  }

  .logo-icon {
    width: 28px;
    height: 28px;
  }

  .error-icon {
    width: 20px;
    height: 20px;
    margin-right: 0.5rem;
  }

  .stats {
    display: flex;
    gap: 1rem;
  }

  .stat {
    background: rgba(255,255,255,0.1);
    padding: 0.25rem 0.75rem;
    border-radius: 1rem;
    font-size: 0.9rem;
  }

  .stat.refresh-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: #3498db;
    cursor: pointer;
    user-select: none;
    transition: background-color 0.2s;
  }

  .stat.refresh-button:hover:not(.loading) {
    background: #2980b9;
  }

  .stat.refresh-button:focus {
    outline: 2px solid white;
    outline-offset: 2px;
  }

  .stat.refresh-button.loading {
    background: #f39c12;
    cursor: not-allowed;
  }

  .refresh-icon {
    width: 16px;
    height: 16px;
  }

  .spinning {
    animation: spin 1.5s linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }

  .error {
    background: #f8d7da;
    color: #721c24;
    padding: 1rem 2rem;
    border-bottom: 1px solid #f5c6cb;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .retry-button {
    background: #dc3545;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 0.25rem;
    cursor: pointer;
    transition: background-color 0.2s;
  }

  .retry-button:hover:not(:disabled) {
    background: #c82333;
  }

  .retry-button:disabled {
    background: #e9a3ab;
    cursor: not-allowed;
  }

  .main-content {
    flex: 1;
    display: flex;
  }

  .sidebar {
    width: 300px;
    min-width: 300px;
    background: white;
    border-right: 1px solid #dee2e6;
    padding: 1rem;
    overflow-y: auto;
  }

  .content {
    flex: 1;
    padding: 1rem;
    overflow-y: auto;
    background: #f9fafb;
  }

  .hosts-section h3 {
    margin: 1.5rem 0 0.5rem 0;
    color: #495057;
  }

  .host-item {
    margin-bottom: 0.25rem;
  }

  .host-name {
    width: 100%;
    padding: 0.5rem;
    border-radius: 0.25rem;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: background-color 0.2s;
    background: none;
    border: none;
    text-align: left;
    color: inherit;
    font: inherit;
  }

  .host-name:hover:not(:disabled) {
    background: #f8f9fa;
  }

  .host-name:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .host-item.active .host-name {
    background: #e3f2fd;
    color: #1976d2;
  }

  .job-count {
    background: #6c757d;
    color: white;
    padding: 0.125rem 0.5rem;
    border-radius: 1rem;
    font-size: 0.75rem;
  }

  .job-lists {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .loading-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    color: #6c757d;
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

  .loading-placeholder {
    padding: 1rem;
    text-align: center;
    color: #6c757d;
    font-style: italic;
    background: rgba(0,0,0,0.03);
    border-radius: 0.25rem;
  }
</style>
