<script lang="ts">
  import { onMount } from 'svelte';
  import axios, { type AxiosError } from 'axios';
  import JobList from './components/JobList.svelte';
  import JobDetail from './components/JobDetail.svelte';
  import FilterPanel from './components/FilterPanel.svelte';
  import LaunchJob from './components/LaunchJob.svelte';
  import ErrorBoundary from './components/ErrorBoundary.svelte';
  import type { 
    HostInfo, 
    JobInfo, 
    JobStatusResponse, 
    JobOutputResponse, 
    JobFilters 
  } from './types/api';

  let hosts: HostInfo[] = [];
  let jobsByHost = new Map<string, JobStatusResponse>();
  let selectedJob: JobInfo | null = null;
  let loading = false;
  let hostsLoading = false;
  let error: string | null = null;
  let lastRequestId = 0;
  let activeRequests = new Set<string>();
  let filters: JobFilters = {
    host: '',
    user: '',
    since: '1d',
    limit: 20,
    state: '',
    activeOnly: false,
    completedOnly: false
  };

  // Tab state
  let activeTab: 'jobs' | 'launch' = 'jobs';
  
  // Mobile UI state
  let showMobileFilters = false;
  let isMobile = false;
  
  // Check if we're on mobile
  function checkMobile() {
    isMobile = window.innerWidth <= 768;
    if (!isMobile) {
      showMobileFilters = false; // Reset on desktop
    }
  }

  const API_BASE = '/api';

  onMount(() => {
    loadHosts();
    loadJobs();
    
    // Check mobile state
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    // Auto-refresh every 30 seconds
    const interval = setInterval(loadJobs, 30000);
    
    return () => {
      clearInterval(interval);
      window.removeEventListener('resize', checkMobile);
    };
  });

  async function loadHosts(): Promise<void> {
    if (hostsLoading) return; // Prevent concurrent requests
    
    hostsLoading = true;
    try {
      const response = await axios.get<HostInfo[]>(`${API_BASE}/hosts`);
      hosts = response.data;
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      error = `Failed to load hosts: ${axiosError.message}`;
    } finally {
      hostsLoading = false;
    }
  }

  async function loadJobs(): Promise<void> {
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

      const response = await axios.get<JobStatusResponse[]>(`${API_BASE}/status?${params}`);
      
      // Only update if this is still the latest request
      if (requestId === lastRequestId) {
        // Convert to Map for easier access
        jobsByHost = new Map<string, JobStatusResponse>();
        response.data.forEach((hostData: JobStatusResponse) => {
          jobsByHost.set(hostData.hostname, hostData);
        });
        
        jobsByHost = new Map(jobsByHost); // Trigger reactivity
      }
    } catch (err: unknown) {
      // Only show error if this is still the latest request
      if (requestId === lastRequestId) {
        const axiosError = err as AxiosError;
        error = `Failed to load jobs: ${axiosError.message}`;
      }
    } finally {
      activeRequests.delete(requestKey);
      if (requestId === lastRequestId) {
        loading = false;
      }
    }
  }

  async function loadJobOutput(jobId: string, hostname: string): Promise<JobOutputResponse | { loading: true }> {
    const requestKey = `output-${jobId}-${hostname}`;
    
    // Prevent duplicate requests for the same job output
    if (activeRequests.has(requestKey)) {
      return { loading: true };
    }
    
    activeRequests.add(requestKey);
    try {
      const response = await axios.get<JobOutputResponse>(`${API_BASE}/jobs/${jobId}/output?host=${hostname}`);
      
      const data = response.data;
      
      // Add additional info about file access for better debugging
      if (data.stdout === null && (data as any).output_files?.stdout_path) {
        data.stdout = `[No output file found at: ${(data as any).output_files.stdout_path}]`;
      }
      
      if (data.stderr === null && (data as any).output_files?.stderr_path) {
        data.stderr = `[No error file found at: ${(data as any).output_files.stderr_path}]`;
      }
      
      return data;
    } catch (err: unknown) {
      console.error('Failed to load job output:', err);
      throw err; // Let JobDetail component handle the error properly
    } finally {
      activeRequests.delete(requestKey);
    }
  }

  function handleFilterChange(): void {
    // Debounce rapid filter changes
    clearTimeout(filterChangeTimeout);
    filterChangeTimeout = setTimeout(() => {
      loadJobs();
    }, 300);
  }
  
  let filterChangeTimeout: ReturnType<typeof setTimeout>;

  function handleJobSelect(job: JobInfo): void {
    selectedJob = job;
  }
  
  // Manual refresh handler
  function handleManualRefresh(): void {
    if (!loading) {
      loadJobs();
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

  function getTotalJobs(): number {
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
      <div class="header-left">
        <button class="app-title" on:click={() => {selectedJob = null; activeTab = 'jobs';}}>
          ssync
        </button>

        <div class="nav-container">
          <nav class="tab-nav">
            <button 
              class="tab-button"
              class:active={activeTab === 'jobs'}
              on:click={() => {activeTab = 'jobs'; selectedJob = null;}}
            >
              Jobs
            </button>
            <button 
              class="tab-button"
              class:active={activeTab === 'launch'}
              on:click={() => {activeTab = 'launch'; selectedJob = null;}}
            >
              Launch Job
            </button>
          </nav>
          
          {#if activeTab === 'jobs' && isMobile}
            <button 
              class="mobile-filter-toggle"
              class:active={showMobileFilters}
              on:click={() => showMobileFilters = !showMobileFilters}
              aria-label="Toggle filters"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M3,4A1,1 0 0,1 4,3H20A1,1 0 0,1 21,4V6A1,1 0 0,1 20,7H4A1,1 0 0,1 3,6V4M7,10A1,1 0 0,1 8,9H16A1,1 0 0,1 17,10V12A1,1 0 0,1 16,13H8A1,1 0 0,1 7,12V10M10,16A1,1 0 0,1 11,15H13A1,1 0 0,1 14,16V18A1,1 0 0,1 13,19H11A1,1 0 0,1 10,18V16Z" />
              </svg>
              Filters
            </button>
          {/if}
        </div>
      </div>
      
      <div class="stats">
        <span class="stat">
          {hosts.length} Hosts
        </span>
        {#if activeTab === 'jobs'}
          <span class="stat">
            {getTotalJobs()} Jobs
          </span>
          <button 
            class="stat refresh-button" 
            class:loading 
            on:click={handleManualRefresh}
            disabled={loading}
            aria-label="Refresh data"
          >
            {loading ? 'Refreshing...' : 'Refresh'}
            <svg class="refresh-icon" class:spinning={loading} viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,6V9L16,5L12,1V4A8,8 0 0,0 4,12C4,13.57 4.46,15.03 5.24,16.26L6.7,14.8C6.25,13.97 6,13 6,12A6,6 0 0,1 12,6M18.76,7.74L17.3,9.2C17.74,10.04 18,11 18,12A6,6 0 0,1 12,18V15L8,19L12,23V20A8,8 0 0,0 20,12C20,10.43 19.54,8.97 18.76,7.74Z"/>
            </svg>
          </button>
        {/if}
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
    {#if activeTab === 'jobs'}
      <!-- Mobile Filter Overlay -->
      {#if isMobile && showMobileFilters}
        <div class="mobile-filter-overlay" on:click={() => showMobileFilters = false}>
          <div class="mobile-filter-panel" on:click|stopPropagation>
            <div class="mobile-filter-header">
              <h3>Filters & Hosts</h3>
              <button class="close-filters" on:click={() => showMobileFilters = false}>
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z" />
                </svg>
              </button>
            </div>
            
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
                        if (isMobile) showMobileFilters = false;
                      }}
                      disabled={loading}
                      aria-pressed={filters.host === host.hostname}
                    >
                      {host.hostname}
                      {#if jobsByHost.has(host.hostname)}
                        <span class="job-count">
                          {jobsByHost.get(host.hostname)?.jobs.length ?? 0}
                        </span>
                      {/if}
                    </button>
                  </div>
                {/each}
              {/if}
            </div>
          </div>
        </div>
      {/if}
      
      <!-- Desktop Sidebar -->
      <div class="sidebar" class:mobile-hidden={isMobile}>
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
                  aria-pressed={filters.host === host.hostname}
                >
                  {host.hostname}
                  {#if jobsByHost.has(host.hostname)}
                    <span class="job-count">
                      {jobsByHost.get(host.hostname)?.jobs.length ?? 0}
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
    {:else if activeTab === 'launch'}
      <div class="launch-content">
        <LaunchJob />
      </div>
    {/if}
  </div>
</div>
</ErrorBoundary>

<style>
  .app {
    min-height: 100vh;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .header {
    background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
    color: white;
    padding: 1rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    backdrop-filter: blur(10px);
    position: relative;
    z-index: 10;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 2rem;
  }

  .app-title {
    margin: 0;
    font-size: 1.5rem;
    cursor: pointer;
    transition: opacity 0.2s;
    background: none;
    border: none;
    color: inherit;
    font: inherit;
    font-weight: 600;
  }

  .app-title:hover {
    opacity: 0.8;
  }


  .error-icon {
    width: 20px;
    height: 20px;
    margin-right: 0.5rem;
  }

  .stats {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }

  @media (max-width: 768px) {
    .stats {
      gap: 0.5rem;
    }
  }

  .stat {
    background: rgba(255,255,255,0.1);
    padding: 0.25rem 0.75rem;
    border-radius: 1rem;
    font-size: 0.9rem;
    white-space: nowrap;
  }

  @media (max-width: 768px) {
    .stat {
      padding: 0.2rem 0.6rem;
      font-size: 0.8rem;
    }
  }

  .stat.refresh-button {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    cursor: pointer;
    user-select: none;
    transition: all 0.2s ease;
    border: none;
    box-shadow: 0 2px 4px rgba(16, 185, 129, 0.2);
    padding: 0.25rem 0.625rem;
    font-size: 0.85rem;
  }

  @media (max-width: 768px) {
    .stat.refresh-button {
      padding: 0.2rem 0.5rem;
      font-size: 0.8rem;
      gap: 0.25rem;
    }
  }

  .stat.refresh-button:hover:not(.loading) {
    background: linear-gradient(135deg, #059669 0%, #047857 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(16, 185, 129, 0.3);
  }

  .stat.refresh-button:focus {
    outline: 2px solid rgba(255, 255, 255, 0.5);
    outline-offset: 2px;
  }

  .stat.refresh-button.loading {
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    cursor: not-allowed;
    box-shadow: 0 2px 4px rgba(245, 158, 11, 0.2);
  }

  .refresh-icon {
    width: 14px;
    height: 14px;
  }

  @media (max-width: 768px) {
    .refresh-icon {
      width: 12px;
      height: 12px;
    }
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
    min-height: 0;
    overflow: hidden;
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
    overflow-x: hidden;
    background: #f9fafb;
    min-height: 0;
    height: 100%;
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
    min-height: min-content;
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

  .tab-nav {
    display: flex;
    gap: 0.5rem;
  }

  .tab-button {
    padding: 0.625rem 1.25rem;
    background: rgba(255,255,255,0.1);
    border: none;
    border-radius: 8px;
    color: rgba(255,255,255,0.8);
    cursor: pointer;
    transition: all 0.3s ease;
    font: inherit;
    font-size: 0.9rem;
    font-weight: 500;
    position: relative;
    overflow: hidden;
  }

  .tab-button::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
    transition: left 0.5s;
  }

  .tab-button:hover {
    background: rgba(255,255,255,0.2);
    color: white;
    transform: translateY(-1px);
  }

  .tab-button:hover::before {
    left: 100%;
  }

  .tab-button.active {
    background: rgba(255,255,255,0.95);
    color: #2c3e50;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    transform: translateY(-1px);
  }

  .tab-button.active::before {
    display: none;
  }


  .launch-content {
    flex: 1;
    overflow: hidden;
    background: #f9fafb;
    display: flex;
    flex-direction: column;
  }

  /* Mobile Navigation */
  .nav-container {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    gap: 1rem;
  }
  
  .mobile-filter-toggle {
    display: none;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 6px;
    color: white;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  
  .mobile-filter-toggle svg {
    width: 16px;
    height: 16px;
  }
  
  .mobile-filter-toggle:hover {
    background: rgba(255,255,255,0.25);
  }
  
  .mobile-filter-toggle.active {
    background: rgba(255,255,255,0.9);
    color: #2c3e50;
  }
  
  /* Mobile Filter Overlay */
  .mobile-filter-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 1000;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 1rem;
    backdrop-filter: blur(4px);
  }
  
  .mobile-filter-panel {
    background: white;
    border-radius: 12px;
    max-width: 400px;
    width: 100%;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    margin-top: 2rem;
  }
  
  .mobile-filter-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 1.25rem;
    border-bottom: 1px solid #e5e7eb;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border-radius: 12px 12px 0 0;
  }
  
  .mobile-filter-header h3 {
    margin: 0;
    color: #374151;
    font-size: 1.1rem;
  }
  
  .close-filters {
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 4px;
    transition: all 0.2s ease;
  }
  
  .close-filters:hover {
    background: rgba(239, 68, 68, 0.1);
    color: #dc2626;
  }
  
  .close-filters svg {
    width: 20px;
    height: 20px;
  }
  
  .mobile-hidden {
    display: none;
  }

  @media (max-width: 768px) {
    .header {
      padding: 1rem;
      flex-direction: column;
      gap: 1rem;
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(10px);
    }

    .header-left {
      gap: 1rem;
      width: 100%;
      justify-content: space-between;
    }

    .app-title {
      font-size: 1.25rem;
      font-weight: 700;
    }

    .stats {
      flex-wrap: wrap;
      gap: 0.5rem;
      justify-content: center;
    }

    .stat {
      font-size: 0.8rem;
      padding: 0.2rem 0.6rem;
    }

    .nav-container {
      width: 100%;
    }
    
    .tab-nav {
      gap: 0.25rem;
      flex: 1;
    }

    .tab-button {
      font-size: 0.8rem;
      padding: 0.5rem 0.75rem;
      flex: 1;
      justify-content: center;
      min-width: 0;
    }
    
    .mobile-filter-toggle {
      display: flex;
      flex-shrink: 0;
    }

    .main-content {
      flex-direction: column;
      padding: 0;
    }
    
    .content {
      padding: 1rem;
      min-height: calc(100vh - 200px);
    }
    
    /* Hide sidebar on mobile */
    .sidebar.mobile-hidden {
      display: none;
    }
  }
</style>
