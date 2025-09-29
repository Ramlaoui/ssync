<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { get } from "svelte/store";
  import { push, location } from "svelte-spa-router";
  import { navigationActions } from "../stores/navigation";
  import type { AxiosError } from "axios";
  import JobTable from "../components/JobTable.svelte";
  import ArrayJobCard from "../components/ArrayJobCard.svelte";
  import SyncStatus from "../components/SyncStatus.svelte";
  import { api } from "../services/api";
  import { jobStateManager } from "../lib/JobStateManager";
  import type { HostInfo, JobFilters, JobInfo, ArrayJobGroup } from "../types/api";
  import { RefreshCw, Clock, Search, X } from 'lucide-svelte';
  import Button from "../lib/components/ui/Button.svelte";
  import Badge from "../lib/components/ui/Badge.svelte";
  import Separator from "../lib/components/ui/Separator.svelte";
  import NavigationHeader from "../components/NavigationHeader.svelte";
  import WebSocketStatus from "../components/WebSocketStatus.svelte";

  let hosts: HostInfo[] = [];
  let loading = false;
  let hostsLoading = false;
  let error: string | null = null;
  let search = '';
  let filters: JobFilters = {
    host: "",
    user: "",
    since: "1d",
    limit: 50, // Default, will be overridden by preferences
    state: "",
    activeOnly: false,
    completedOnly: false,
  };
  
  // Mobile UI state
  let isMobile = typeof window !== 'undefined' && window.innerWidth < 768;
  let searchFocused = false;
  let searchExpanded = false;
  let searchInput: HTMLInputElement;

  // Auto-refresh state
  let autoRefreshEnabled = false;
  let autoRefreshInterval = 30; // seconds
  let autoRefreshTimer: number | null = null;
  
  // Get reactive stores from JobStateManager
  const allJobs = jobStateManager.getAllJobs();
  const connectionStatus = jobStateManager.getConnectionStatus();
  const managerState = jobStateManager.getState();
  const arrayJobGroups = jobStateManager.getArrayJobGroups();

  // Debug reactive jobs - only log when count changes
  $: if ($allJobs.length > 0) {
    console.log(`[JobsPage] Received ${$allJobs.length} jobs from store`);
  }
  $: if ($arrayJobGroups.length > 0) {
    console.log(`[JobsPage] Received ${$arrayJobGroups.length} array job groups`);
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
  
  // Filter jobs and exclude those that are part of array groups
  $: filteredJobs = (() => {
    try {
      let jobs = [...$allJobs];

      // Exclude jobs that are part of array groups
      if ($arrayJobGroups.length > 0) {
        const arrayJobIds = new Set(
          $arrayJobGroups.flatMap(group =>
            group.tasks.map(task => `${task.hostname}:${task.job_id}`)
          )
        );
        jobs = jobs.filter(j => !arrayJobIds.has(`${j.hostname}:${j.job_id}`));
      }

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

  // Filter array groups based on search and filters
  $: filteredArrayGroups = (() => {
    let groups = [...$arrayJobGroups];

    // Apply filters
    if (filters.host) {
      groups = groups.filter(g => g.hostname === filters.host);
    }
    if (filters.user) {
      groups = groups.filter(g => g.user?.toLowerCase().includes(filters.user.toLowerCase()));
    }
    if (filters.state) {
      // Filter groups that have tasks in the specified state
      groups = groups.filter(g => g.tasks.some(t => t.state === filters.state));
    }
    if (filters.activeOnly) {
      groups = groups.filter(g => g.running_count > 0 || g.pending_count > 0);
    }
    if (filters.completedOnly) {
      groups = groups.filter(g => g.completed_count > 0 || g.failed_count > 0 || g.cancelled_count > 0);
    }

    // Apply search
    if (search) {
      const term = search.toLowerCase();
      groups = groups.filter(g =>
        g.array_job_id.toLowerCase().includes(term) ||
        g.job_name.toLowerCase().includes(term) ||
        g.user?.toLowerCase().includes(term)
      );
    }

    return groups;
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
    const encodedJobId = encodeURIComponent(job.job_id);
    push(`/jobs/${encodedJobId}/${job.hostname}`);
  }

  function handleManualRefresh(): void {
    if (!loading) {
      loadJobs(true);
    }
  }

  function setupAutoRefresh(): void {
    // Clear existing timer
    if (autoRefreshTimer) {
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }

    // Set up new timer if enabled
    if (autoRefreshEnabled && autoRefreshInterval > 0) {
      autoRefreshTimer = setInterval(() => {
        if (!loading) {
          loadJobs(false); // Gentle refresh, no cache clear
        }
      }, autoRefreshInterval * 1000);
    }
  }

  function handleRefreshSettingsChanged(event: CustomEvent): void {
    const { autoRefreshEnabled: enabled, autoRefreshInterval: interval } = event.detail;
    autoRefreshEnabled = enabled;
    autoRefreshInterval = interval;
    setupAutoRefresh();

    // Save to localStorage
    const prefs = JSON.parse(localStorage.getItem('ssync_preferences') || '{}');
    prefs.autoRefresh = enabled;
    prefs.refreshInterval = interval;
    localStorage.setItem('ssync_preferences', JSON.stringify(prefs));
  }

  function handleJobsPerPageChanged(event: CustomEvent): void {
    const { jobsPerPage } = event.detail;
    filters.limit = jobsPerPage;
  }

  // React to auto-refresh settings changes
  $: if (typeof autoRefreshEnabled !== 'undefined') {
    setupAutoRefresh();
  }

  $: totalJobs = filteredJobs.length + filteredArrayGroups.reduce((sum, g) => sum + g.total_tasks, 0);
  

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

    // Load preferences from localStorage
    const savedPrefs = localStorage.getItem('ssync_preferences');
    if (savedPrefs) {
      try {
        const prefs = JSON.parse(savedPrefs);
        autoRefreshEnabled = prefs.autoRefresh || false;
        autoRefreshInterval = prefs.refreshInterval || 30;
        filters.limit = prefs.jobsPerPage || 50;
        setupAutoRefresh();
      } catch (e) {
        console.error('Failed to load preferences:', e);
      }
    }

    // Listen for settings changes
    window.addEventListener('jobsPerPageChanged', handleJobsPerPageChanged);
  });

  onDestroy(() => {
    if (filterChangeTimeout) clearTimeout(filterChangeTimeout);
    if (autoRefreshTimer) clearInterval(autoRefreshTimer);
    window.removeEventListener("resize", checkMobile);
    window.removeEventListener('jobsPerPageChanged', handleJobsPerPageChanged);
  });
</script>

<div class="h-full flex flex-col bg-gradient-to-br from-gray-50 to-slate-50">
  {#if !isMobile}
    <NavigationHeader
      showRefresh={true}
      refreshing={loading || progressiveLoading}
      {autoRefreshEnabled}
      {autoRefreshInterval}
      on:refresh={handleManualRefresh}
      on:refreshSettingsChanged={handleRefreshSettingsChanged}
    >
      <div slot="left" class="flex items-center gap-4">
        <div class="flex gap-4 flex-shrink-0 items-center">
          <div class="flex items-center gap-1 whitespace-nowrap">
            <span class="text-base font-semibold text-slate-900">{hosts.length}</span>
            <span class="text-xs text-slate-500">hosts</span>
          </div>
          <div class="flex items-center gap-1 whitespace-nowrap">
            <span class="text-base font-semibold text-slate-900">{totalJobs}</span>
            <span class="text-xs text-slate-500">jobs</span>
          </div>
          {#if dataFromCache}
            <div class="flex items-center gap-1 whitespace-nowrap pl-4 border-l border-gray-200 ml-4">
              <Clock class="h-4 w-4 text-muted-foreground" />
              <Badge variant="secondary">Cached</Badge>
            </div>
          {/if}
        </div>

        <!-- WebSocket Status -->
        <div class="ml-4">
          <WebSocketStatus compact={true} />
        </div>

        <!-- Search Bar -->
        <div class="flex-1 max-w-md">
          <div class="relative w-full">
            <div class="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 pointer-events-none flex items-center justify-center">
              <Search size={16} />
            </div>
            <input
              type="text"
              class="w-full pl-10 pr-10 py-2 border border-gray-300 rounded-lg text-sm transition-all bg-gray-50 focus:outline-none focus:border-blue-500 focus:bg-white focus:shadow-sm focus:ring-2 focus:ring-blue-100 placeholder-gray-400"
              placeholder="Search jobs..."
              bind:value={search}
              on:input={handleFilterChange}
            />
            {#if search}
              <button class="absolute right-2 top-1/2 transform -translate-y-1/2 p-1 bg-transparent border-0 text-gray-500 cursor-pointer rounded hover:bg-gray-100 hover:text-red-500 flex items-center justify-center transition-all" on:click={() => { search = ''; handleFilterChange(); }}>
                <X size={14} />
              </button>
            {/if}
          </div>
        </div>
      </div>
    </NavigationHeader>
  {:else}
    <!-- Mobile header -->
    <div class="flex justify-between items-center p-3 bg-gradient-to-b from-white to-slate-50/95 border-b border-black/8 relative z-50 shadow-sm">
      <div class="flex items-center min-h-[40px] whitespace-nowrap">
        <!-- Stats on the left -->
        <div class="flex gap-4 flex-shrink-0 items-center">
          <div class="flex items-center gap-1 whitespace-nowrap">
            <span class="text-base font-semibold text-slate-900">{hosts.length}</span>
            <span class="text-xs text-slate-500">hosts</span>
          </div>
          <div class="flex items-center gap-1 whitespace-nowrap">
            <span class="text-base font-semibold text-slate-900">{totalJobs}</span>
            <span class="text-xs text-slate-500">jobs</span>
          </div>
        </div>

        <!-- Flexible spacer to push search and refresh to the right -->
        <div class="flex-1 min-w-8"></div>

        <!-- Expandable search -->
        <div class="flex items-center justify-center transition-all duration-300 ease-out overflow-hidden flex-shrink-0 {searchExpanded ? 'w-[180px] max-w-[180px]' : 'w-8'}">
          {#if searchExpanded}
            <div class="relative w-full animate-in slide-in-from-right-2 duration-300">
              <div class="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 pointer-events-none flex items-center justify-center">
                <Search size={16} />
              </div>
              <input
                type="text"
                class="w-full pl-10 pr-10 py-2 border border-gray-300 rounded-lg text-sm transition-all bg-gray-50 focus:outline-none focus:border-blue-500 focus:bg-white focus:shadow-sm focus:ring-2 focus:ring-blue-100 placeholder-gray-400"
                placeholder="Search jobs..."
                bind:value={search}
                on:input={handleFilterChange}
                on:blur={() => { if (!search) searchExpanded = false; }}
                bind:this={searchInput}
              />
              {#if search}
                <button class="absolute right-2 top-1/2 transform -translate-y-1/2 p-1 bg-transparent border-0 text-gray-500 cursor-pointer rounded hover:bg-gray-100 hover:text-red-500 flex items-center justify-center transition-all" on:click={() => { search = ''; handleFilterChange(); }}>
                  <X size={14} />
                </button>
              {/if}
            </div>
          {:else}
            <button class="flex items-center justify-center w-8 h-8 border-0 rounded-md bg-transparent text-gray-500 cursor-pointer transition-all hover:bg-gray-100 hover:text-gray-700" on:click={() => { searchExpanded = true; setTimeout(() => searchInput?.focus(), 100); }}>
              <Search size={16} />
            </button>
          {/if}
        </div>

        <!-- Refresh button -->
        <button
          on:click={handleManualRefresh}
          disabled={loading}
          class="flex items-center justify-center w-8 h-8 bg-white border border-black/8 rounded-lg text-sm font-medium text-slate-600 cursor-pointer transition-all flex-shrink-0 hover:bg-slate-50 hover:border-black/12 disabled:opacity-50 disabled:cursor-not-allowed"
          title="{loading || progressiveLoading ? 'Loading from hosts...' : 'Refresh'}"
        >
          <RefreshCw class="w-4 h-4 {loading || progressiveLoading ? 'animate-spin' : ''}" />
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

  <div class="flex-1 overflow-auto px-4 py-4">
    {#if progressiveLoading && filteredJobs.length === 0 && filteredArrayGroups.length === 0}
      <div class="flex items-center justify-center h-full">
        <div class="text-center text-gray-500">Loading jobs...</div>
      </div>
    {:else}
      <!-- Array job groups -->
      {#if filteredArrayGroups.length > 0}
        <div class="space-y-2 mb-4">
          {#each filteredArrayGroups as group (group.array_job_id + group.hostname)}
            <ArrayJobCard {group} />
          {/each}
        </div>
      {/if}

      <!-- Regular jobs table -->
      {#if filteredJobs.length > 0}
        <JobTable
          jobs={filteredJobs}
          loading={false}
          on:jobSelect={(e) => handleJobSelect(e.detail)}
        />
      {:else if filteredArrayGroups.length === 0}
        <div class="flex items-center justify-center h-full">
          <div class="text-center text-gray-500">No jobs found</div>
        </div>
      {/if}
    {/if}
  </div>
</div>

<style>
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
</style>

