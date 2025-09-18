<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { get } from "svelte/store";
  import { push, location } from "svelte-spa-router";
  import { navigationActions } from "../stores/navigation";
  import type { AxiosError } from "axios";
  import JobTable from "../components/JobTable.svelte";
  import SyncStatus from "../components/SyncStatus.svelte";
  import { api } from "../services/api";
  import { jobStateManager } from "../lib/JobStateManager";
  import type { HostInfo, JobFilters, JobInfo } from "../types/api";
  import { RefreshCw, Clock, Search, X } from 'lucide-svelte';
  import Button from "../lib/components/ui/Button.svelte";
  import Badge from "../lib/components/ui/Badge.svelte";
  import Separator from "../lib/components/ui/Separator.svelte";
  import NavigationHeader from "../components/NavigationHeader.svelte";

  let hosts: HostInfo[] = [];
  let loading = false;
  let hostsLoading = false;
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
  
  // Mobile UI state
  let isMobile = typeof window !== 'undefined' && window.innerWidth < 768;
  let searchFocused = false;
  let searchExpanded = false;
  let searchInput: HTMLInputElement;
  
  // Get reactive stores from JobStateManager
  const allJobs = jobStateManager.getAllJobs();
  const connectionStatus = jobStateManager.getConnectionStatus();
  const managerState = jobStateManager.getState();
  
  // Debug reactive jobs - only log when count changes
  $: if ($allJobs.length > 0) {
    console.log(`[JobsPage] Received ${$allJobs.length} jobs from store`);
  }
  
  // Search scoring function - returns relevance score (lower is better)
  function getSearchScore(job: any, searchTerm: string): number {
    if (!searchTerm) return 0;
    const term = searchTerm.toLowerCase();
    
    // Exact match scores
    if (job.job_id.toLowerCase() === term) return 0;
    if (job.name?.toLowerCase() === term) return 1;
    if (job.user?.toLowerCase() === term) return 2;
    
    // Starts with scores
    if (job.job_id.toLowerCase().startsWith(term)) return 10;
    if (job.name?.toLowerCase().startsWith(term)) return 11;
    if (job.user?.toLowerCase().startsWith(term)) return 12;
    
    // Contains scores
    if (job.job_id.toLowerCase().includes(term)) return 20;
    if (job.name?.toLowerCase().includes(term)) return 21;
    if (job.user?.toLowerCase().includes(term)) return 22;
    if (job.hostname?.toLowerCase().includes(term)) return 23;
    
    // No match
    return 999;
  }
  
  // Compute filtered jobs based on current filters with search ranking
  $: filteredJobs = (() => {
    try {
      let jobs = [...$allJobs];
      
      // Apply filters
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
      
      // Apply search with ranking
      if (search) {
        // Filter and score jobs
        const scoredJobs = jobs
          .map(job => ({ job, score: getSearchScore(job, search) }))
          .filter(item => item.score < 999)
          .sort((a, b) => a.score - b.score)
          .map(item => item.job);
        
        jobs = scoredJobs;
      }
      
      // Apply limit
      if (filters.limit > 0) {
        jobs = jobs.slice(0, filters.limit);
      }
      
      return jobs;
    } catch (error) {
      console.error('[JobsPage] Error in filteredJobs computation:', error);
      return [];
    }
  })();
  
  
  // Compute loading states from manager
  $: progressiveLoading = Array.from($managerState.hostStates.values()).some(h => h.status === 'loading');
  $: dataFromCache = $managerState.dataSource === 'cache';
  
  function checkMobile() {
    isMobile = window.innerWidth < 768;
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
        // Sync specific host
        await jobStateManager.syncHost(filters.host);
      } else {
        // Sync all hosts
        await jobStateManager.syncAllHosts();
      }
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      error = `Failed to load jobs: ${axiosError.message}`;
    } finally {
      loading = false;
    }
  }

  function handleFilterChange(): void {
    clearTimeout(filterChangeTimeout);
    filterChangeTimeout = setTimeout(() => {
      // Filters are applied reactively through the reactive statements
      // No need to check jobsByHost here as it's a reactive value
    }, 800);
  }

  let filterChangeTimeout: ReturnType<typeof setTimeout>;

  function handleJobSelect(job: JobInfo): void {
    // Track where we're coming from for smart back navigation
    navigationActions.setPreviousRoute($location);
    push(`/jobs/${job.job_id}/${job.hostname}`);
  }

  function handleManualRefresh(): void {
    if (!loading) {
      loadJobs(true);
    }
  }

  $: totalJobs = filteredJobs.length;
  

  onMount(async () => {
    // Load hosts first
    await loadHosts();

    // Only refresh jobs if we don't have any data
    const currentJobs = get(allJobs);
    if (currentJobs.length === 0) {
      await jobStateManager.forceRefresh();
    } else {
      // We have data, just do a gentle sync without clearing cache
      await jobStateManager.syncAllHosts();
    }
    checkMobile();
    window.addEventListener("resize", checkMobile);
  });

  onDestroy(() => {
    if (filterChangeTimeout) clearTimeout(filterChangeTimeout);
    window.removeEventListener("resize", checkMobile);
  });
</script>

<div class="h-full flex flex-col bg-gradient-to-br from-gray-50 to-slate-50">
  {#if !isMobile}
    <NavigationHeader
      showRefresh={true}
      refreshing={loading || progressiveLoading}
      on:refresh={handleManualRefresh}
    >
      <div slot="left" class="flex items-center gap-4">
        <div class="header-stats">
          <div class="stat-item">
            <span class="stat-value">{hosts.length}</span>
            <span class="stat-label">hosts</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{totalJobs}</span>
            <span class="stat-label">jobs</span>
          </div>
          {#if dataFromCache}
            <div class="stat-item cache-indicator">
              <Clock class="h-4 w-4 text-muted-foreground" />
              <Badge variant="secondary">Cached</Badge>
            </div>
          {/if}
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
      </div>
    </NavigationHeader>
  {:else}
    <!-- Mobile header -->
    <div class="header mobile-header">
      <div class="mobile-header-row">
        <!-- Stats on the left -->
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

        <!-- Flexible spacer to push search and refresh to the right -->
        <div style="flex: 1; min-width: 2rem;"></div>

        <!-- Expandable search -->
        <div class="mobile-search-container {searchExpanded ? 'expanded' : ''}">
          {#if searchExpanded}
            <div class="search-bar expanded">
              <div class="search-icon">
                <Search size={16} />
              </div>
              <input
                type="text"
                class="search-input"
                placeholder="Search jobs..."
                bind:value={search}
                on:input={handleFilterChange}
                on:blur={() => { if (!search) searchExpanded = false; }}
                bind:this={searchInput}
              />
              {#if search}
                <button class="clear-btn" on:click={() => { search = ''; handleFilterChange(); }}>
                  <X size={14} />
                </button>
              {/if}
            </div>
          {:else}
            <button class="search-toggle-btn" on:click={() => { searchExpanded = true; setTimeout(() => searchInput?.focus(), 100); }}>
              <Search size={16} />
            </button>
          {/if}
        </div>

        <!-- Refresh button -->
        <button
          on:click={handleManualRefresh}
          disabled={loading}
          class="refresh-btn"
          style="flex-shrink: 0;"
          title="{loading || progressiveLoading ? 'Loading from hosts...' : 'Refresh'}"
        >
          <RefreshCw class="icon {loading || progressiveLoading ? 'animate-spin' : ''}" />
        </button>
      </div>
    </div>
  {/if}

  {#if error}
    <div class="bg-destructive/10 border-b border-destructive/20 p-3">
      <p class="text-sm font-medium text-destructive">{error}</p>
    </div>
  {/if}

  <!-- Filters removed since search is now in header -->
  
  <div class="flex-1 overflow-hidden">
    <JobTable
      jobs={filteredJobs}
      loading={progressiveLoading && filteredJobs.length === 0}
      on:jobSelect={(e) => handleJobSelect(e.detail)}
    />
  </div>
</div>

<style>
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 1.5rem;
    background: linear-gradient(to bottom, white, rgba(248, 250, 252, 0.95));
    border-bottom: 1px solid rgba(0, 0, 0, 0.08);
    gap: 2rem;
    position: relative;
    z-index: 60;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.03);
  }

  .mobile-header {
    padding: 0.75rem 1rem;
  }

  .mobile-header-row {
    display: flex;
    align-items: center;
    min-height: 40px;
    white-space: nowrap;
  }

  .header-stats {
    display: flex;
    gap: 1rem;
    flex-shrink: 0;
    align-items: center;
  }

  .stat-item {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    white-space: nowrap;
  }

  .stat-value {
    font-size: 1rem;
    font-weight: 600;
    color: #0f172a;
  }

  .stat-label {
    font-size: 0.75rem;
    color: #64748b;
  }

  .cache-indicator {
    padding-left: 1rem;
    border-left: 1px solid #e5e7eb;
    margin-left: 1rem;
  }

  .header-search {
    flex: 1;
    max-width: 400px;
  }

  .mobile-search-container {
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
    flex-shrink: 0;
  }

  .mobile-search-container:not(.expanded) {
    width: 32px;
    flex-shrink: 0;
  }

  .mobile-search-container.expanded {
    width: 180px;
    max-width: 180px;
    flex-shrink: 0;
  }

  .search-toggle-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.2s;
  }

  .search-toggle-btn:hover {
    background: #f3f4f6;
    color: #374151;
  }

  .search-bar {
    position: relative;
    width: 100%;
  }

  .search-bar.expanded {
    width: 100%;
    animation: searchExpand 0.4s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  }

  @keyframes searchExpand {
    from {
      width: 32px;
      opacity: 0;
    }
    to {
      width: 100%;
      opacity: 1;
    }
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
    flex-shrink: 0;
  }

  .refresh-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.375rem;
    padding: 0.5rem;
    width: 32px;
    height: 32px;
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

  .animate-spin {
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* Mobile responsive */
  @media (max-width: 768px) {
    .header-search {
      max-width: none;
      margin: 0;
      width: 100%;
    }

    .header-stats {
      gap: 1rem;
      justify-content: center;
    }

    .stat-value {
      font-size: 1rem;
    }

    .stat-label {
      font-size: 0.75rem;
    }

    .refresh-btn {
      padding: 0.5rem;
    }

    .refresh-btn span {
      display: none;
    }
  }
</style>

