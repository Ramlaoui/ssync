<script lang="ts">
  import { run } from 'svelte/legacy';

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
  
  let hosts: HostInfo[] = $state([]);
  let loading = $state(false);
  let hostsLoading = false;
  let initialLoading = $state(true); // Track initial page load
  let error: string | null = $state(null);
  let search = $state('');
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
  let isMobile = $state(typeof window !== 'undefined' && window.innerWidth < 1024);
  let selectedView: 'jobs' | 'watchers' | 'both' = 'both';
  
  // Get reactive stores
  const allJobs = jobStateManager.getAllJobs();
  const connectionStatus = jobStateManager.getConnectionStatus();
  const managerState = jobStateManager.getState();
  
  // Watchers state
  let watchers: Watcher[] = $state([]);
  let watchersLoading = $state(false);
  let activeWatchers: Watcher[] = $state([]);
  let pausedWatchers: Watcher[] = $state([]);
  let selectedJobId: string | null = $state(null);
  
  // Subscribe to watchers store
  run(() => {
    watchers = $watchersStore;
  });
  run(() => {
    activeWatchers = watchers.filter(w => w && w.state === 'active');
  });
  run(() => {
    pausedWatchers = watchers.filter(w => w && w.state === 'paused');
  });
  
  // Get watchers for selected job
  let selectedJobWatchers = $derived(selectedJobId && $watchersByJob[selectedJobId] ? $watchersByJob[selectedJobId] : []);
  
  // Get jobs with watchers
  let jobsWithWatchers = $derived(new Set(Object.keys($watchersByJob)));
  
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
  let filteredJobs = $derived((() => {
    try {
      let jobs = [...$allJobs];
      
      if (filters.host) {
        jobs = jobs.filter(j => j.hostname === filters.host);
      }
      if (filters.user) {
        jobs = jobs.filter(j => j.user?.toLowerCase().includes(filters.user.toLowerCase()));
      }
      if (filters.state) {
        jobs = jobs.filter(j => j && j.state === filters.state);
      }
      if (filters.activeOnly) {
        jobs = jobs.filter(j => j && j.state && (j.state === 'R' || j.state === 'PD'));
      }
      if (filters.completedOnly) {
        jobs = jobs.filter(j => j && j.state && (j.state === 'CD' || j.state === 'F' || j.state === 'CA' || j.state === 'TO'));
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
  })());
  
  let progressiveLoading = $derived(Array.from($managerState.hostStates.values()).some(h => h.status === 'loading'));
  let dataFromCache = $derived($managerState.dataSource === 'cache');
  
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
    const encodedJobId = encodeURIComponent(job.job_id);
    push(`/jobs/${encodedJobId}/${job.hostname}`);
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

  

  let totalJobs = $derived(filteredJobs.length);
  
  // Ensure watchers are loaded when component is active
  run(() => {
    if (typeof window !== 'undefined' && $watchersStore.length === 0 && !watchersLoading) {
      loadWatchersData();
    }
  });
  
  onMount(async () => {
    await loadHosts();

    // ⚡ PERFORMANCE FIX: Don't force sync on mount - let WebSocket deliver initial data
    // The JobStateManager connects WebSocket on initialization and will receive initial
    // data automatically. Forcing a sync here causes a race condition with the WebSocket
    // initial fetch, resulting in 0 jobs being returned due to backend concurrency locks.

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

<div class="flex flex-col h-screen bg-gray-50">
  <div class="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200">
    <div class="flex items-center">
      <div class="flex items-center gap-6">
        <div class="flex items-baseline gap-2">
          <span class="text-2xl font-bold text-gray-900">{hosts.length}</span>
          <span class="text-xs font-medium text-gray-500 uppercase tracking-wider">hosts</span>
        </div>
        <div class="flex items-baseline gap-2">
          <span class="text-2xl font-bold text-gray-900">{totalJobs}</span>
          <span class="text-xs font-medium text-gray-500 uppercase tracking-wider">jobs</span>
        </div>
      </div>
    </div>

    <!-- Search Bar -->
    <div class="flex-1 max-w-md mx-8">
      <div class="relative">
        <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <Search class="w-4 h-4 text-gray-400" />
        </div>
        <input
          type="text"
          class="block w-full pl-10 pr-8 py-2 border border-gray-300 rounded-md leading-5 bg-white placeholder-gray-500 focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
          placeholder="Search jobs..."
          bind:value={search}
          oninput={handleFilterChange}
        />
        {#if search}
          <button class="absolute inset-y-0 right-0 pr-3 flex items-center" onclick={() => { search = ''; handleFilterChange(); }}>
            <X class="w-3.5 h-3.5 text-gray-400 hover:text-gray-600" />
          </button>
        {/if}
      </div>
    </div>

    <div class="flex items-center gap-3">
      <button
        onclick={handleManualRefresh}
        disabled={loading || watchersLoading}
        class="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        title="{loading || progressiveLoading || watchersLoading ? 'Loading...' : 'Refresh'}"
      >
        <RefreshCw class="w-4 h-4 {loading || progressiveLoading || watchersLoading ? 'animate-spin' : ''}" />
        {#if !isMobile}
          <span class="ml-2">{loading || progressiveLoading || watchersLoading ? "Refreshing" : "Refresh"}</span>
        {/if}
      </button>
    </div>
  </div>

  {#if error}
    <div class="bg-red-50 border-l-4 border-red-400 p-4">
      <p class="text-red-700">{error}</p>
    </div>
  {/if}

  <!-- Filters removed since search is now in header -->
  
  <!-- Main Content Area -->
  <div class="flex-1 flex overflow-hidden">
    {#if isMobile}
      <!-- Mobile: Jobs only -->
      <div class="flex-1 overflow-auto">
        <JobsSection
          jobs={filteredJobs}
          loading={initialLoading || (loading && filteredJobs.length === 0)}
          on:jobSelect={(e) => handleJobSelect(e.detail)}
        />
      </div>
    {:else}
      <!-- Desktop: Split view -->
      <div class="flex flex-1 overflow-hidden">
        <!-- Jobs Section -->
        <JobsSection
          jobs={filteredJobs}
          loading={initialLoading || (loading && filteredJobs.length === 0)}
          on:jobSelect={(e) => handleJobSelect(e.detail)}
        />

        <div class="w-px bg-gray-200 flex-shrink-0"></div>

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
</style>