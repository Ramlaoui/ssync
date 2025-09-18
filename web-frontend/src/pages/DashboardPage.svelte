<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { get } from "svelte/store";
  import { push, location } from "svelte-spa-router";
  import { navigationActions } from "../stores/navigation";
  import type { AxiosError } from "axios";
  import JobsSection from "../components/JobsSection.svelte";
  import WatchersSection from "../components/WatchersSection.svelte";
  import { api } from "../services/api";
  import { jobStateManager } from "../lib/JobStateManager";
  import { watchers as watchersStore, fetchAllWatchers, watchersByJob } from "../stores/watchers";
  import type { HostInfo, JobFilters, JobInfo } from "../types/api";
  import type { Watcher } from "../types/watchers";
  import { RefreshCw, Search, X } from 'lucide-svelte';
  
  let hosts: HostInfo[] = [];
  let loading = false;
  let hostsLoading = false;
  let initialLoading = true; // Track initial page load
  let error: string | null = null;
  let search = '';
  let filters: JobFilters = {
    host: "",
    user: "",
    since: "1d",
    limit: 100,
    state: "",
    activeOnly: false,
    completedOnly: false,
  };
  
  // Layout state
  let isMobile = typeof window !== 'undefined' && window.innerWidth < 1024;
  let selectedView: 'jobs' | 'watchers' | 'both' = 'both';
  
  // Get reactive stores
  const allJobs = jobStateManager.getAllJobs();
  const connectionStatus = jobStateManager.getConnectionStatus();
  const managerState = jobStateManager.getState();
  
  // Watchers state
  let watchers: Watcher[] = [];
  let watchersLoading = false;
  let activeWatchers: Watcher[] = [];
  let pausedWatchers: Watcher[] = [];
  let selectedJobId: string | null = null;
  
  // Subscribe to watchers store
  $: watchers = $watchersStore;
  $: activeWatchers = watchers.filter(w => w.state === 'active');
  $: pausedWatchers = watchers.filter(w => w.state === 'paused');
  
  // Get watchers for selected job
  $: selectedJobWatchers = selectedJobId && $watchersByJob[selectedJobId] ? $watchersByJob[selectedJobId] : [];
  
  // Get jobs with watchers
  $: jobsWithWatchers = new Set(Object.keys($watchersByJob));
  
  // Search scoring function
  function getSearchScore(job: any, searchTerm: string): number {
    if (!searchTerm) return 0;
    const term = searchTerm.toLowerCase();
    
    if (job.job_id.toLowerCase() === term) return 0;
    if (job.name?.toLowerCase() === term) return 1;
    if (job.user?.toLowerCase() === term) return 2;
    
    if (job.job_id.toLowerCase().startsWith(term)) return 10;
    if (job.name?.toLowerCase().startsWith(term)) return 11;
    if (job.user?.toLowerCase().startsWith(term)) return 12;
    
    if (job.job_id.toLowerCase().includes(term)) return 20;
    if (job.name?.toLowerCase().includes(term)) return 21;
    if (job.user?.toLowerCase().includes(term)) return 22;
    if (job.hostname?.toLowerCase().includes(term)) return 23;
    
    return 999;
  }
  
  // Compute filtered jobs
  $: filteredJobs = (() => {
    try {
      let jobs = [...$allJobs];
      
      if (filters.host) {
        jobs = jobs.filter(j => j.hostname === filters.host);
      }
      if (filters.user) {
        jobs = jobs.filter(j => j.user?.toLowerCase().includes(filters.user.toLowerCase()));
      }
      if (filters.state) {
        jobs = jobs.filter(j => j.state === filters.state);
      }
      if (filters.activeOnly) {
        jobs = jobs.filter(j => j.state === 'R' || j.state === 'PD');
      }
      if (filters.completedOnly) {
        jobs = jobs.filter(j => j.state === 'CD' || j.state === 'F' || j.state === 'CA' || j.state === 'TO');
      }
      
      if (search) {
        const scoredJobs = jobs
          .map(job => ({ job, score: getSearchScore(job, search) }))
          .filter(item => item.score < 999)
          .sort((a, b) => a.score - b.score)
          .map(item => item.job);
        
        jobs = scoredJobs;
      }
      
      if (filters.limit > 0) {
        jobs = jobs.slice(0, filters.limit);
      }
      
      return jobs;
    } catch (error) {
      console.error('[DashboardPage] Error in filteredJobs computation:', error);
      return [];
    }
  })();
  
  $: progressiveLoading = Array.from($managerState.hostStates.values()).some(h => h.status === 'loading');
  $: dataFromCache = $managerState.dataSource === 'cache';
  
  function checkMobile() {
    const newIsMobile = window.innerWidth < 1024;
    if (newIsMobile !== isMobile) {
      isMobile = newIsMobile;
      // On mobile, always use jobs view only
      if (isMobile) {
        selectedView = 'jobs';
      } else {
        selectedView = 'both';
      }
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
    error = null;
    loading = true;

    try {
      if (forceRefresh) {
        await jobStateManager.forceRefresh();
      } else if (filters.host) {
        await jobStateManager.syncHost(filters.host);
      } else {
        await jobStateManager.syncAllHosts();
      }
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      error = `Failed to load jobs: ${axiosError.message}`;
    } finally {
      loading = false;
    }
  }
  
  async function loadWatchersData(): Promise<void> {
    watchersLoading = true;
    try {
      await fetchAllWatchers();
    } catch (err) {
      console.error('Failed to load watchers:', err);
    } finally {
      watchersLoading = false;
    }
  }

  function handleFilterChange(): void {
    // Filters are applied reactively
  }

  function handleJobSelect(job: JobInfo): void {
    // Track where we're coming from for smart back navigation
    navigationActions.setPreviousRoute($location);
    push(`/jobs/${job.job_id}/${job.hostname}`);
  }
  
  function handleJobHover(job: JobInfo | null): void {
    selectedJobId = job ? job.job_id : null;
  }

  async function handleManualRefresh(): Promise<void> {
    if (!loading && !watchersLoading) {
      try {
        await Promise.all([
          loadJobs(true),
          loadWatchersData()
        ]);
      } catch (error) {
        console.error('Refresh failed:', error);
      }
    }
  }

  

  $: totalJobs = filteredJobs.length;
  
  // Ensure watchers are loaded when component is active
  $: if (typeof window !== 'undefined' && $watchersStore.length === 0 && !watchersLoading) {
    loadWatchersData();
  }
  
  onMount(async () => {
    await loadHosts();

    // Only refresh jobs if we don't have any data
    const currentJobs = get(allJobs);
    if (currentJobs.length === 0) {
      await jobStateManager.forceRefresh();
    } else {
      // We have data, just do a gentle sync without clearing cache
      await jobStateManager.syncAllHosts();
    }
    
    // Only load watchers if store is empty
    if ($watchersStore.length === 0) {
      await loadWatchersData();
    }
    
    // Mark initial loading as complete
    initialLoading = false;
    
    checkMobile();
    window.addEventListener("resize", checkMobile);
    
    // Refresh watchers periodically (only if we have watchers)
    const interval = setInterval(() => {
      if ($watchersStore.length > 0) {
        loadWatchersData();
      }
    }, 30000);
    
    return () => clearInterval(interval);
  });

  onDestroy(() => {
    window.removeEventListener("resize", checkMobile);
  });
</script>

<div class="dashboard-container">
  <div class="dashboard-header">
    <div class="header-left">
      <div class="header-stats">
        <div class="stat-item">
          <span class="stat-value">{hosts.length}</span>
          <span class="stat-label">hosts</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{totalJobs}</span>
          <span class="stat-label">jobs</span>
        </div>
      </div>
    </div>

    <!-- Search Bar -->
    <div class="header-search">
      <div class="search-bar">
        <div class="search-icon">
          <Search size={16} />
        </div>
        <input
          type="text"
          class="search-input"
          placeholder="Search jobs..."
          bind:value={search}
          on:input={handleFilterChange}
        />
        {#if search}
          <button class="clear-btn" on:click={() => { search = ''; handleFilterChange(); }}>
            <X size={14} />
          </button>
        {/if}
      </div>
    </div>

    <div class="header-actions">
      <button
        on:click={handleManualRefresh}
        disabled={loading || watchersLoading}
        class="refresh-btn"
        title="{loading || progressiveLoading || watchersLoading ? 'Loading...' : 'Refresh'}"
      >
        <RefreshCw class="icon {loading || progressiveLoading || watchersLoading ? 'animate-spin' : ''}" />
        {#if !isMobile}
          <span>{loading || progressiveLoading || watchersLoading ? "Refreshing" : "Refresh"}</span>
        {/if}
      </button>
    </div>
  </div>

  {#if error}
    <div class="error-banner">
      <p>{error}</p>
    </div>
  {/if}

  <!-- Filters removed since search is now in header -->
  
  <!-- Main Content Area -->
  <div class="dashboard-content">
    {#if isMobile}
      <!-- Mobile: Jobs only -->
      <div class="jobs-section mobile">
        <JobsSection
          jobs={filteredJobs}
          loading={initialLoading || (loading && filteredJobs.length === 0)}
          on:jobSelect={(e) => handleJobSelect(e.detail)}
        />
      </div>
    {:else}
      <!-- Desktop: Split view -->
      <div class="split-view">
        <!-- Jobs Section -->
        <JobsSection
          jobs={filteredJobs}
          loading={initialLoading || (loading && filteredJobs.length === 0)}
          on:jobSelect={(e) => handleJobSelect(e.detail)}
        />

        <div class="divider"></div>

        <!-- Watchers Section -->
        <WatchersSection
          {watchers}
          {selectedJobId}
          {selectedJobWatchers}
          on:refresh={loadWatchersData}
        />
      </div>
    {/if}
  </div>
</div>

<style>
  .dashboard-container {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: #fafafa;
  }
  
  .dashboard-header {
    display: flex;
    align-items: center;
    padding: 1rem 1.5rem;
    background: white;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
    gap: 2rem;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 0;
    flex-shrink: 0;
  }

  .home-label {
    color: #6b7280;
    font-size: 0.875rem;
    font-weight: 500;
    margin-right: 0.75rem;
  }

  .header-divider {
    width: 1px;
    height: 20px;
    background: #d1d5db;
    flex-shrink: 0;
    margin-right: 1rem;
  }
  
  .header-stats {
    display: flex;
    gap: 2rem;
  }
  
  .stat-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .stat-value {
    font-size: 1.25rem;
    font-weight: 600;
    color: #0f172a;
  }
  
  .stat-label {
    font-size: 0.875rem;
    color: #64748b;
  }
  
  .header-search {
    max-width: 400px;
    margin: 0;
  }

  .search-bar {
    position: relative;
    width: 100%;
  }

  .search-icon {
    position: absolute;
    left: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
    color: #9ca3af;
    pointer-events: none;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .search-input {
    width: 100%;
    padding: 0.5rem 2.5rem;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    transition: all 0.15s;
    background: #f9fafb;
  }

  .search-input:focus {
    outline: none;
    border-color: #3b82f6;
    background: white;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .search-input::placeholder {
    color: #9ca3af;
  }

  .clear-btn {
    position: absolute;
    right: 0.5rem;
    top: 50%;
    transform: translateY(-50%);
    padding: 0.25rem;
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    border-radius: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }

  .clear-btn:hover {
    background: #f3f4f6;
    color: #ef4444;
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-left: auto;
  }
  
  
  .refresh-btn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 0.875rem;
    background: white;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 0.5rem;
    font-size: 0.813rem;
    font-weight: 500;
    color: #475569;
    cursor: pointer;
    transition: all 0.15s;
  }
  
  .refresh-btn:hover:not(:disabled) {
    background: #f8fafc;
    border-color: rgba(0, 0, 0, 0.12);
  }
  
  .refresh-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .icon {
    width: 1rem;
    height: 1rem;
  }
  
  .icon-small {
    width: 0.875rem;
    height: 0.875rem;
  }
  
  .animate-spin {
    animation: spin 1s linear infinite;
  }
  
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  
  .error-banner {
    padding: 0.75rem 1.5rem;
    background: #fee2e2;
    border-bottom: 1px solid #fecaca;
  }
  
  .error-banner p {
    margin: 0;
    font-size: 0.875rem;
    font-weight: 500;
    color: #dc2626;
  }
  
  .dashboard-content {
    flex: 1;
    overflow: hidden;
  }

  /* Desktop split view */
  .split-view {
    display: flex;
    position: relative;
    gap: 0;
    min-height: 0; /* Enable flex shrinking */
    flex: 1; /* Take available space from parent */
  }

  .divider {
    width: 1px;
    background: rgba(0, 0, 0, 0.08);
    flex-shrink: 0;
  }
  
  /* Mobile styles */
  .jobs-section.mobile,
  .watchers-section.mobile {
    height: 100%;
    overflow: auto;
  }
  
  .watchers-grid {
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  /* Responsive behavior */
  @media (max-width: 1200px) {
    .watchers-section {
      flex: 0 0 320px; /* Smaller on medium screens */
    }
    .jobs-section {
      min-width: 400px;
    }
  }

  @media (max-width: 1024px) {
    .dashboard-header {
      padding: 0.75rem 1rem;
      flex-direction: column;
      gap: 1rem;
    }
    .header-left {
      width: 100%;
      justify-content: flex-start;
    }

    .header-search {
      max-width: none;
      margin: 0;
      width: 100%;
    }

    .header-stats {
      gap: 1rem;
    }

    .stat-value {
      font-size: 1rem;
    }

    .stat-label {
      font-size: 0.75rem;
    }

    /* Mobile switches to single view, no desktop split */
    .split-view {
      display: none;
    }
  }
</style>