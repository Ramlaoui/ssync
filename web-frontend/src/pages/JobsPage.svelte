<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { push } from "svelte-spa-router";
  import type { AxiosError } from "axios";
  import FilterPanel from "../components/FilterPanel.svelte";
  import HostSelector from "../components/HostSelector.svelte";
  import JobList from "../components/JobList.svelte";
  import SyncStatus from "../components/SyncStatus.svelte";
  import { api } from "../services/api";
  import { jobStateManager } from "../lib/JobStateManager";
  import type { HostInfo, JobFilters, JobInfo } from "../types/api";
  import { RefreshCw, Filter, Wifi, Clock, Search } from 'lucide-svelte';
  import Button from "../lib/components/ui/Button.svelte";
  import Badge from "../lib/components/ui/Badge.svelte";
  import Separator from "../lib/components/ui/Separator.svelte";

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
  let showMobileFilters = false;
  let isMobile = false;
  
  // Get reactive stores from JobStateManager
  const allJobs = jobStateManager.getAllJobs();
  const connectionStatus = jobStateManager.getConnectionStatus();
  const managerState = jobStateManager.getState();
  
  // Debug reactive jobs - only log when count changes
  $: if ($allJobs.length > 0) {
    console.log(`[JobsPage] Received ${$allJobs.length} jobs from store`);
  }
  
  // Compute filtered jobs based on current filters
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
      if (search) {
        const searchLower = search.toLowerCase();
        jobs = jobs.filter(j => 
          j.job_id.toLowerCase().includes(searchLower) ||
          j.name?.toLowerCase().includes(searchLower) ||
          j.user?.toLowerCase().includes(searchLower)
        );
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
  
  // Group jobs by host for display
  $: jobsByHost = (() => {
    try {
      const map = new Map<string, JobInfo[]>();
      if (Array.isArray(filteredJobs)) {
        filteredJobs.forEach(job => {
          if (job && job.hostname) {
            if (!map.has(job.hostname)) {
              map.set(job.hostname, []);
            }
            map.get(job.hostname)!.push(job);
          }
        });
      }
      console.log(`[JobsPage] jobsByHost has ${map.size} hosts with jobs`);
      return map;
    } catch (error) {
      console.error('[JobsPage] Error in jobsByHost computation:', error);
      return new Map();
    }
  })();
  
  // Compute loading states from manager
  $: progressiveLoading = Array.from($managerState.hostStates.values()).some(h => h.status === 'loading');
  $: dataFromCache = $managerState.dataSource === 'cache';
  
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
    push(`/jobs/${job.job_id}/${job.hostname}`);
  }

  function handleManualRefresh(): void {
    if (!loading) {
      loadJobs(true);
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

  $: totalJobs = filteredJobs.length;
  
  $: jobCountMap = (() => {
    const counts = new Map<string, number>();
    jobsByHost.forEach((jobs, hostname) => {
      counts.set(hostname, jobs.length);
    });
    return counts;
  })();
  
  function handleHostSelect(event: CustomEvent<string>) {
    filters.host = event.detail;
    handleFilterChange();
  }

  onMount(async () => {
    loadHosts();
    // Force immediate job sync on page load
    await jobStateManager.forceRefresh();
    checkMobile();
    window.addEventListener("resize", checkMobile);
  });

  onDestroy(() => {
    if (filterChangeTimeout) clearTimeout(filterChangeTimeout);
    window.removeEventListener("resize", checkMobile);
  });
</script>

<div class="h-full flex flex-col bg-background">
  <div class="flex justify-between items-center p-4 sm:p-6 bg-card border-b">
    <div class="flex items-center space-x-4">
      <div class="flex items-center space-x-2">
        <span class="text-2xl font-semibold text-foreground">{hosts.length}</span>
        <span class="text-sm text-muted-foreground">Hosts</span>
      </div>
      <Separator orientation="vertical" class="h-6" />
      <div class="flex items-center space-x-2">
        <span class="text-2xl font-semibold text-foreground">{totalJobs}</span>
        <span class="text-sm text-muted-foreground">Jobs</span>
      </div>
      {#if progressiveLoading}
        <Separator orientation="vertical" class="h-6" />
        <div class="flex items-center space-x-2" title="Loading from hosts...">
          <RefreshCw class="h-4 w-4 text-muted-foreground animate-spin" />
          <span class="text-sm text-muted-foreground">Loading...</span>
        </div>
      {/if}
      {#if dataFromCache}
        <Separator orientation="vertical" class="h-6" />
        <div class="flex items-center space-x-2" title="Data served from cache">
          <Clock class="h-4 w-4 text-muted-foreground" />
          <Badge variant="secondary">Cached</Badge>
        </div>
      {/if}
      {#if $connectionStatus.connected}
        <Separator orientation="vertical" class="h-6" />
        <div class="flex items-center space-x-2" title="Data source: {$connectionStatus.source}">
          <Wifi class="h-4 w-4 text-green-500" />
          <Badge variant={$connectionStatus.source === 'websocket' ? 'success' : 'warning'}>
            {$connectionStatus.source === 'websocket' ? 'Live' : 'Polling'}
          </Badge>
        </div>
      {/if}
    </div>

    <div class="flex items-center space-x-3">
      <Button
        variant="outline"
        size="sm"
        on:click={handleManualRefresh}
        disabled={loading}
      >
        <RefreshCw class="h-4 w-4 mr-2 {loading ? 'animate-spin' : ''}" />
        {loading ? "Refreshing..." : "Refresh"}
      </Button>

      {#if isMobile}
        <Button
          variant={showMobileFilters ? "default" : "outline"}
          size="sm"
          on:click={() => (showMobileFilters = !showMobileFilters)}
        >
          <Filter class="h-4 w-4 mr-2" />
          Filters
        </Button>
      {/if}
    </div>
  </div>

  {#if error}
    <div class="bg-destructive/10 border-b border-destructive/20 p-3">
      <p class="text-sm font-medium text-destructive">{error}</p>
    </div>
  {/if}

  <div class="flex flex-1 overflow-hidden {isMobile ? 'flex-col' : ''}">
    {#if !isMobile || showMobileFilters}
      <div class="{isMobile ? 'w-full border-b' : 'w-64 border-r'} bg-card p-4 overflow-y-auto">
        <HostSelector {hosts} selectedHost={filters.host} on:select={handleHostSelect} />
        <FilterPanel bind:filters on:change={handleFilterChange} />
        <div class="mt-4">
          <div class="relative">
            <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search jobs..."
              bind:value={search}
              on:input={handleFilterChange}
              class="w-full pl-9 pr-3 py-2 text-sm border border-input rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
        </div>
      </div>
    {/if}
    
    <div class="flex-1 p-4 overflow-y-auto">
      {#if loading && jobsByHost.size === 0}
        <div class="flex flex-col items-center justify-center h-64 space-y-4">
          <RefreshCw class="h-8 w-8 text-muted-foreground animate-spin" />
          <span class="text-muted-foreground">Loading jobs...</span>
        </div>
      {:else if jobsByHost.size === 0}
        <div class="flex flex-col items-center justify-center h-64 space-y-4">
          <RefreshCw class="h-12 w-12 text-muted-foreground opacity-50" />
          <p class="text-muted-foreground">No jobs found</p>
          <Button variant="outline" on:click={handleManualRefresh}>
            <RefreshCw class="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      {:else}
        {#each Array.from(jobsByHost.entries()) as [hostname, jobs]}
          <div class="mb-8">
            <div class="flex justify-between items-center mb-4 pb-2 border-b">
              <h3 class="text-lg font-semibold text-foreground">{hostname}</h3>
              <Badge variant="outline">
                {jobs.length} job{jobs.length !== 1 ? 's' : ''}
              </Badge>
            </div>
            <JobList
              hostname={hostname}
              jobs={jobs}
              queryTime={new Date().toISOString()}
              getStateColor={getStateColor}
              on:jobSelect={(e) => handleJobSelect(e.detail)}
            />
          </div>
        {/each}
      {/if}
    </div>
  </div>
</div>

