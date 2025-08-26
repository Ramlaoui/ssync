<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { push } from "svelte-spa-router";
  import type { AxiosError } from "axios";
  import FilterPanel from "../components/FilterPanel.svelte";
  import HostSelector from "../components/HostSelector.svelte";
  import JobList from "../components/JobList.svelte";
  import { api } from "../services/api";
  import { jobsStore } from "../stores/jobs";
  import type { HostInfo, JobFilters, JobInfo, JobStatusResponse } from "../types/api";

  let hosts: HostInfo[] = [];
  let jobsByHost = new Map<string, JobStatusResponse>();
  let loading = false;
  let hostsLoading = false;
  let error: string | null = null;
  let lastRequestId = 0;
  let search = '';
  let filters: JobFilters = {
    host: "",
    user: "",
    since: "1d",
    limit: 20,
    state: "",
    activeOnly: false,
    completedOnly: false,
  };

  // Mobile UI state
  let showMobileFilters = false;
  let isMobile = false;
  
  // Cache indicator (from backend)
  let dataFromCache = false;

  function checkMobile() {
    isMobile = window.innerWidth <= 768;
    if (!isMobile) {
      showMobileFilters = false;
    }
  }

  async function loadHosts(): Promise<void> {
    if (hostsLoading) return;

    hostsLoading = true;
    try {
      const response = await api.get<HostInfo[]>("/api/hosts");
      hosts = response.data;
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      error = `Failed to load hosts: ${axiosError.message}`;
    } finally {
      hostsLoading = false;
    }
  }

  async function loadJobs(forceRefresh = false): Promise<void> {
    const requestId = ++lastRequestId;
    loading = true;
    error = null;

    try {
      // Use the jobs store with caching
      const response = await jobsStore.fetchHostJobs(filters.host || undefined, {
        user: filters.user,
        since: filters.since,
        limit: filters.limit,
        state: filters.state,
        active_only: filters.activeOnly,
        completed_only: filters.completedOnly,
      });

      if (requestId === lastRequestId) {
        jobsByHost = new Map<string, JobStatusResponse>();
        
        // Check if data came from cache (backend sends this flag)
        dataFromCache = false;
        response.forEach((hostData: JobStatusResponse) => {
          jobsByHost.set(hostData.hostname, hostData);
          if (hostData.cached) {
            dataFromCache = true;
          }
        });
        
        jobsByHost = new Map(jobsByHost); // Trigger reactivity
      }
    } catch (err: unknown) {
      if (requestId === lastRequestId) {
        const axiosError = err as AxiosError;
        error = `Failed to load jobs: ${axiosError.message}`;
      }
    } finally {
      if (requestId === lastRequestId) {
        loading = false;
      }
    }
  }

  function handleFilterChange(): void {
    clearTimeout(filterChangeTimeout);
    filterChangeTimeout = setTimeout(() => {
      loadJobs();
    }, 300);
  }

  let filterChangeTimeout: ReturnType<typeof setTimeout>;
  let refreshInterval: ReturnType<typeof setInterval>;

  function handleJobSelect(job: JobInfo): void {
    // Find the host for this job
    let jobHost = "";
    for (let [hostname, hostData] of jobsByHost.entries()) {
      if (hostData.jobs.some(j => j.job_id === job.job_id)) {
        jobHost = hostname;
        break;
      }
    }
    
    if (jobHost) {
      // Cache the job data before navigation
      jobsStore.updateJob(jobHost, job);
      push(`/jobs/${job.job_id}/${jobHost}`);
    }
  }

  function handleManualRefresh(): void {
    if (!loading) {
      loadJobs();
    }
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

  $: totalJobs = (() => {
    let total = 0;
    for (let hostData of jobsByHost.values()) {
      total += hostData.jobs.length;
    }
    return total;
  })();
  
  $: jobCountMap = (() => {
    const counts = new Map<string, number>();
    for (let [hostname, hostData] of jobsByHost.entries()) {
      counts.set(hostname, hostData.jobs.length);
    }
    return counts;
  })();
  
  function handleHostSelect(event: CustomEvent<string>) {
    filters.host = event.detail;
    handleFilterChange();
  }

  onMount(() => {
    loadHosts();
    loadJobs();
    
    checkMobile();
    window.addEventListener("resize", checkMobile);

    // Auto-refresh every 2 minutes (120 seconds)
    refreshInterval = setInterval(loadJobs, 120000);
  });

  onDestroy(() => {
    if (refreshInterval) clearInterval(refreshInterval);
    window.removeEventListener("resize", checkMobile);
  });
</script>

<div class="jobs-page">
  <div class="page-header">
    <div class="stats">
      <div class="stat-item">
        <span class="stat-value">{hosts.length}</span>
        <span class="stat-label">Hosts</span>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <span class="stat-value">{totalJobs}</span>
        <span class="stat-label">Jobs</span>
      </div>
      {#if dataFromCache}
        <div class="stat-divider"></div>
        <div class="stat-item cache" title="Data served from backend cache">
          <svg class="stat-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M16.2,16.2L11,13V7H12.5V12.2L17,14.9L16.2,16.2Z" />
          </svg>
          <span class="stat-label">Cached</span>
        </div>
      {/if}
    </div>
    
    <button
      class="refresh-button"
      class:loading
      on:click={handleManualRefresh}
      disabled={loading}
      aria-label="Refresh data"
    >
      <svg
        class="refresh-icon"
        class:spinning={loading}
        viewBox="0 0 24 24"
        fill="currentColor"
      >
        <path d="M12,6V9L16,5L12,1V4A8,8 0 0,0 4,12C4,13.57 4.46,15.03 5.24,16.26L6.7,14.8C6.25,13.97 6,13 6,12A6,6 0 0,1 12,6M18.76,7.74L17.3,9.2C17.74,10.04 18,11 18,12A6,6 0 0,1 12,18V15L8,19L12,23V20A8,8 0 0,0 20,12C20,10.43 19.54,8.97 18.76,7.74Z" />
      </svg>
      {loading ? "Refreshing..." : "Refresh"}
    </button>

    {#if isMobile}
      <button
        class="mobile-filter-toggle"
        class:active={showMobileFilters}
        on:click={() => (showMobileFilters = !showMobileFilters)}
        aria-label="Toggle filters"
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M3,4A1,1 0 0,1 4,3H20A1,1 0 0,1 21,4V6A1,1 0 0,1 20,7H4A1,1 0 0,1 3,6V4M7,10A1,1 0 0,1 8,9H16A1,1 0 0,1 17,10V12A1,1 0 0,1 16,13H8A1,1 0 0,1 7,12V10M10,16A1,1 0 0,1 11,15H13A1,1 0 0,1 14,16V18A1,1 0 0,1 13,19H11A1,1 0 0,1 10,18V16Z" />
        </svg>
        Filters
      </button>
    {/if}
  </div>

  {#if error}
    <div class="error">
      <svg class="error-icon" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
      </svg>
      {error}
      <button on:click={loadJobs} disabled={loading} class="retry-button">
        {loading ? "Retrying..." : "Retry"}
      </button>
    </div>
  {/if}

  <div class="page-content">
    <!-- Mobile Filter Overlay -->
    {#if isMobile && showMobileFilters}
      <div class="mobile-filter-overlay" on:click={() => (showMobileFilters = false)}>
        <div class="mobile-filter-panel" on:click|stopPropagation>
          <div class="mobile-filter-header">
            <h3>Filters & Hosts</h3>
            <button class="close-filters" on:click={() => (showMobileFilters = false)}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z" />
              </svg>
            </button>
          </div>

          <FilterPanel bind:filters {hosts} bind:search={search} on:change={handleFilterChange} {loading} />
          
          <HostSelector 
            {hosts}
            selectedHost={filters.host}
            jobCounts={jobCountMap}
            on:select={(e) => {
              handleHostSelect(e);
              if (isMobile) showMobileFilters = false;
            }}
            {loading}
          />
        </div>
      </div>
    {/if}

    <!-- Desktop Sidebar -->
    <div class="sidebar" class:mobile-hidden={isMobile}>
      <FilterPanel bind:filters {hosts} bind:search={search} on:change={handleFilterChange} {loading} />
      
      <HostSelector 
        {hosts} 
        selectedHost={filters.host}
        jobCounts={jobCountMap}
        on:select={handleHostSelect}
        {loading}
      />
    </div>

    <div class="content">
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
    </div>
  </div>
</div>

<style>
  .jobs-page {
    height: 100%;
    width: 100%;
    display: flex;
    flex-direction: column;
  }

  .page-header {
    padding: 1rem 1.25rem;
    background: white;
    border-bottom: 1px solid #e2e8f0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
  }

  .stats {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  
  .stat-item {
    display: flex;
    align-items: center;
    gap: 0.375rem;
  }
  
  .stat-item.cache {
    color: #10b981;
  }
  
  .stat-value {
    font-size: 1.125rem;
    font-weight: 600;
    color: #1e293b;
  }
  
  .stat-label {
    font-size: 0.85rem;
    color: #64748b;
    font-weight: 500;
  }
  
  .stat-icon {
    width: 16px;
    height: 16px;
  }
  
  .stat-divider {
    width: 1px;
    height: 20px;
    background: #e2e8f0;
  }

  .refresh-button {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 1rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .refresh-button:hover:not(:disabled) {
    background: #2563eb;
    transform: translateY(-1px);
  }
  
  .refresh-button:active:not(:disabled) {
    transform: translateY(0);
  }

  .refresh-button:disabled {
    background: #cbd5e1;
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

  .error {
    background: #f8d7da;
    color: #721c24;
    padding: 1rem 2rem;
    border-bottom: 1px solid #f5c6cb;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .error-icon {
    width: 20px;
    height: 20px;
    margin-right: 0.5rem;
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

  .page-content {
    flex: 1;
    display: flex;
    min-height: 0;
    overflow: hidden;
  }

  .sidebar {
    width: 300px;
    min-width: 300px;
    background: #f8fafc;
    border-right: 1px solid #e2e8f0;
    padding: 1rem;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1rem;
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
    background: rgba(0, 0, 0, 0.03);
    border-radius: 0.25rem;
  }

  .mobile-filter-toggle {
    display: none;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 6px;
    color: #495057;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .mobile-filter-toggle svg {
    width: 16px;
    height: 16px;
  }

  .mobile-filter-toggle:hover {
    background: #e9ecef;
  }

  .mobile-filter-toggle.active {
    background: #007bff;
    color: white;
    border-color: #007bff;
  }

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
    border-radius: 16px;
    max-width: 480px;
    width: 100%;
    max-height: 85vh;
    overflow-y: auto;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
    margin-top: 1rem;
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .mobile-filter-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin: -1.25rem -1.25rem 0;
    padding: 1.25rem;
    border-bottom: 1px solid #e2e8f0;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border-radius: 16px 16px 0 0;
  }

  .mobile-filter-header h3 {
    margin: 0;
    font-size: 0.9rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.025em;
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
    .page-header {
      flex-direction: column;
      gap: 0.5rem;
      align-items: stretch;
    }

    .stats {
      justify-content: center;
    }

    .mobile-filter-toggle {
      display: flex;
      align-self: center;
    }

    .sidebar.mobile-hidden {
      display: none;
    }

    .content {
      padding: 1rem;
    }
  }
</style>