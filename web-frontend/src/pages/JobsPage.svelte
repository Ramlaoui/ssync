<script lang="ts">
  import { run } from "svelte/legacy";

  import type { AxiosError } from "axios";
  import { Clock, RefreshCw, Search, X } from "lucide-svelte";
  import { onDestroy, onMount } from "svelte";
  import { location, push } from "svelte-spa-router";
  import ArrayJobCard from "../components/ArrayJobCard.svelte";
  import JobTable from "../components/JobTable.svelte";
  import NavigationHeader from "../components/NavigationHeader.svelte";
  import Badge from "../lib/components/ui/Badge.svelte";
  import CollapsibleSection from "../lib/components/ui/CollapsibleSection.svelte";
  import { jobStateManager } from "../lib/JobStateManager";
  import { api } from "../services/api";
  import { navigationActions } from "../stores/navigation";
  import { preferences } from "../stores/preferences";
  import { fetchAllWatchers } from "../stores/watchers";
  import type { HostInfo, JobFilters, JobInfo, PartitionStatusResponse } from "../types/api";

  let hosts: HostInfo[] = $state([]);
  let loading = $state(false);
  let hostsLoading = false;
  let error: string | null = $state(null);
  let partitionStates: PartitionStatusResponse[] = $state([]);
  let partitionsLoading = $state(false);
  let partitionsError: string | null = $state(null);
  let search = $state("");
  let filters: JobFilters = $state({
    host: "",
    user: "",
    since: $preferences.defaultSince || "14d",
    limit: 50, // Default, will be overridden by preferences
    state: "",
    activeOnly: false,
    completedOnly: false,
  });

  // Mobile UI state
  let isMobile = $state(
    typeof window !== "undefined" && window.innerWidth < 768,
  );
  let searchFocused = false;
  let searchExpanded = $state(false);
  let searchInput: HTMLInputElement | null = $state(null);

  // Auto-refresh state
  let autoRefreshEnabled = $state(false);
  let autoRefreshInterval = $state(30); // seconds
  let autoRefreshTimer: ReturnType<typeof setInterval> | null = null;

  // Get reactive stores from JobStateManager
  const allJobs = jobStateManager.getAllJobs();
  const connectionStatus = jobStateManager.getConnectionStatus();
  const managerState = jobStateManager.getState();
  const arrayJobGroups = jobStateManager.getArrayJobGroups();
  const hostStates = jobStateManager.getHostStates();

  // Debug reactive jobs - check for duplicates
  run(() => {
    if ($allJobs.length > 0) {
      const uniqueKeys = new Set(
        $allJobs.map((j) => `${j.hostname}:${j.job_id}`),
      );
      const hasDuplicates = uniqueKeys.size !== $allJobs.length;
      console.log(
        `[JobsPage] Received ${$allJobs.length} jobs from store (${uniqueKeys.size} unique) ${hasDuplicates ? "⚠️ DUPLICATES DETECTED" : "✓"}`,
      );
      if (hasDuplicates) {
        // Find and log duplicates
        const jobKeys = $allJobs.map((j) => `${j.hostname}:${j.job_id}`);
        const duplicates = jobKeys.filter(
          (key, index) => jobKeys.indexOf(key) !== index,
        );
        console.log(`[JobsPage] Duplicate keys:`, [...new Set(duplicates)]);
      }
    }
  });
  run(() => {
    if ($arrayJobGroups.length > 0) {
      console.log(
        `[JobsPage] Received ${$arrayJobGroups.length} array job groups`,
      );
    }
  });

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
  let filteredJobs = $derived(
    (() => {
      try {
        let jobs = [...$allJobs];

        // Defensive deduplication: Ensure no duplicate job_id + hostname combinations
        const uniqueJobs = new Map();
        jobs.forEach((job) => {
          const key = `${job.hostname}:${job.job_id}`;
          uniqueJobs.set(key, job);
        });
        jobs = Array.from(uniqueJobs.values());

        // Exclude jobs that are part of array groups
        if ($arrayJobGroups.length > 0) {
          const arrayJobIds = new Set(
            $arrayJobGroups.flatMap((group) =>
              group.tasks.map((task) => `${task.hostname}:${task.job_id}`),
            ),
          );
          jobs = jobs.filter(
            (j) => !arrayJobIds.has(`${j.hostname}:${j.job_id}`),
          );
        }

        // Apply filters
        if (filters.host) {
          jobs = jobs.filter((j) => j.hostname === filters.host);
        }
        if (filters.user) {
          jobs = jobs.filter((j) =>
            j.user?.toLowerCase().includes(filters.user.toLowerCase()),
          );
        }
        if (filters.state) {
          jobs = jobs.filter((j) => j && j.state === filters.state);
        }
        if (filters.activeOnly) {
          jobs = jobs.filter(
            (j) => j && j.state && (j.state === "R" || j.state === "PD"),
          );
        }
        if (filters.completedOnly) {
          jobs = jobs.filter(
            (j) =>
              j &&
              j.state &&
              (j.state === "CD" ||
                j.state === "F" ||
                j.state === "CA" ||
                j.state === "TO"),
          );
        }

        // Apply search with ranking
        if (search) {
          // Filter and score jobs
          const scoredJobs = jobs
            .map((job) => ({ job, score: getSearchScore(job, search) }))
            .filter((item) => item.score < 999)
            .sort((a, b) => a.score - b.score)
            .map((item) => item.job);

          jobs = scoredJobs;
        }

        // Apply limit
        if (filters.limit > 0) {
          jobs = jobs.slice(0, filters.limit);
        }

        return jobs;
      } catch (error) {
        console.error("[JobsPage] Error in filteredJobs computation:", error);
        return [];
      }
    })(),
  );

  // Filter array groups based on search and filters
  let filteredArrayGroups = $derived(
    (() => {
      let groups = [...$arrayJobGroups];

      // Apply filters
      if (filters.host) {
        groups = groups.filter((g) => g.hostname === filters.host);
      }
      if (filters.user) {
        groups = groups.filter((g) =>
          g.user?.toLowerCase().includes(filters.user.toLowerCase()),
        );
      }
      if (filters.state) {
        // Filter groups that have tasks in the specified state
        groups = groups.filter((g) =>
          g.tasks.some((t) => t.state === filters.state),
        );
      }
      if (filters.activeOnly) {
        groups = groups.filter(
          (g) => g.running_count > 0 || g.pending_count > 0,
        );
      }
      if (filters.completedOnly) {
        groups = groups.filter(
          (g) =>
            g.completed_count > 0 ||
            g.failed_count > 0 ||
            g.cancelled_count > 0,
        );
      }

      // Apply search
      if (search) {
        const term = search.toLowerCase();
        groups = groups.filter(
          (g) =>
            g.array_job_id.toLowerCase().includes(term) ||
            g.job_name.toLowerCase().includes(term) ||
            g.user?.toLowerCase().includes(term),
        );
      }

      return groups;
    })(),
  );

  let totalPartitions = $derived(
    partitionStates.reduce((sum, host) => sum + host.partitions.length, 0),
  );

  let latestPartitionUpdate = $derived(
    (() => {
      const timestamps = partitionStates
        .map((h) => h.updated_at)
        .filter((t): t is string => Boolean(t))
        .map((t) => new Date(t).getTime());
      if (timestamps.length === 0) return null;
      return new Date(Math.max(...timestamps)).toISOString();
    })(),
  );

  let partitionsSectionExpanded = $derived(
    totalPartitions > 0 && totalPartitions <= 8,
  );

  let partitionsSubtitle = $derived(
    latestPartitionUpdate
      ? `Updated ${formatTimeAgo(latestPartitionUpdate)}`
      : "",
  );

  // Track active arrays for smart collapsible defaults
  let activeArrayCount = $derived(
    filteredArrayGroups.filter(
      (g) => g.running_count > 0 || g.pending_count > 0,
    ).length,
  );

  let hasActiveArrays = $derived(activeArrayCount > 0);

  // Smart default: collapse if all completed OR > 10 arrays
  let arraysSectionExpanded = $derived(
    hasActiveArrays && filteredArrayGroups.length <= 10,
  );

  // Compute loading states from manager
  let progressiveLoading = $derived(
    Array.from($managerState.hostStates.values()).some(
      (h) => h.status === "loading",
    ),
  );
  let dataFromCache = $derived($managerState.dataSource === "cache");

  // Track hosts with errors
  let hostsWithErrors = $derived(
    Array.from($hostStates.values()).filter((h) => h.status === "error"),
  );
  let hostsWithTimeouts = $derived(hostsWithErrors.filter((h) => h.isTimeout));

  function checkMobile() {
    isMobile = window.innerWidth < 768;
  }

  function formatTimeAgo(value: string | null | undefined): string {
    if (!value) return "";
    const ts = new Date(value).getTime();
    if (Number.isNaN(ts)) return "";
    const diff = Date.now() - ts;
    if (diff < 60000) return "just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return new Date(value).toLocaleDateString();
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

  async function loadPartitions(forceRefresh = false): Promise<void> {
    partitionsError = null;
    partitionsLoading = true;

    try {
      const params = new URLSearchParams();
      if (filters.host) params.append("host", filters.host);
      if (forceRefresh) params.append("force_refresh", "true");
      const url = params.toString()
        ? `/api/partitions?${params.toString()}`
        : "/api/partitions";
      const response = await api.get<PartitionStatusResponse[]>(url);
      partitionStates = response.data;
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      partitionsError = `Failed to load partition state: ${axiosError.message}`;
    } finally {
      partitionsLoading = false;
    }
  }

  async function refreshAll(forceRefresh = false): Promise<void> {
    await Promise.all([loadJobs(forceRefresh), loadPartitions(forceRefresh)]);
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
    if (!loading && !partitionsLoading) {
      refreshAll(true);
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
        if (!loading && !partitionsLoading) {
          refreshAll(false); // Gentle refresh, no cache clear
        }
      }, autoRefreshInterval * 1000);
    }
  }

  function handleRefreshSettingsChanged(
    event: CustomEvent<{ autoRefreshEnabled: boolean; autoRefreshInterval: number }>,
  ): void {
    const { autoRefreshEnabled: enabled, autoRefreshInterval: interval } =
      event.detail;
    autoRefreshEnabled = enabled;
    autoRefreshInterval = interval;
    setupAutoRefresh();

    // Save to localStorage
    const prefs = JSON.parse(localStorage.getItem("ssync_preferences") || "{}");
    prefs.autoRefresh = enabled;
    prefs.refreshInterval = interval;
    localStorage.setItem("ssync_preferences", JSON.stringify(prefs));
  }

  function handleJobsPerPageChanged(
    event: CustomEvent<{ jobsPerPage: number }>,
  ): void {
    const { jobsPerPage } = event.detail;
    filters.limit = jobsPerPage;
  }

  // React to auto-refresh settings changes
  run(() => {
    if (typeof autoRefreshEnabled !== "undefined") {
      setupAutoRefresh();
    }
  });

  let totalJobs = $derived(
    filteredJobs.length +
      filteredArrayGroups.reduce((sum, g) => sum + g.total_tasks, 0),
  );

  onMount(async () => {
    // Load hosts first
    await loadHosts();

    loadPartitions().catch((err) =>
      console.warn("Failed to load partition state:", err),
    );

    // Load watchers for eye icon display (non-blocking)
    fetchAllWatchers().catch((err) =>
      console.warn("Failed to load watchers:", err),
    );

    // ⚡ PERFORMANCE FIX: Don't force sync on mount - let WebSocket deliver initial data
    // The JobStateManager connects WebSocket on initialization and will receive initial
    // data automatically. Forcing a sync here causes a race condition with the WebSocket
    // initial fetch, resulting in 0 jobs being returned due to backend concurrency locks.
    // The user can always click the refresh button if they want to force a refresh.

    checkMobile();
    window.addEventListener("resize", checkMobile);

    // Load preferences from localStorage
    const savedPrefs = localStorage.getItem("ssync_preferences");
    if (savedPrefs) {
      try {
        const prefs = JSON.parse(savedPrefs);
        autoRefreshEnabled = prefs.autoRefresh || false;
        autoRefreshInterval = prefs.refreshInterval || 30;
        filters.limit = prefs.jobsPerPage || 50;
        setupAutoRefresh();
      } catch (e) {
        console.error("Failed to load preferences:", e);
      }
    }

    // Listen for settings changes
    window.addEventListener("jobsPerPageChanged", handleJobsPerPageChanged);
  });

  onDestroy(() => {
    if (filterChangeTimeout) clearTimeout(filterChangeTimeout);
    if (autoRefreshTimer) clearInterval(autoRefreshTimer);
    window.removeEventListener("resize", checkMobile);
    window.removeEventListener("jobsPerPageChanged", handleJobsPerPageChanged);
  });
</script>

<div class="h-full flex flex-col bg-background">
  {#if !isMobile}
    <NavigationHeader
      showRefresh={true}
      refreshing={loading || progressiveLoading}
      bind:autoRefreshEnabled
      bind:autoRefreshInterval
      on:refresh={handleManualRefresh}
      on:refreshSettingsChanged={handleRefreshSettingsChanged}
    >
      {#snippet left()}
        <div class="flex items-center gap-4">
          <div class="flex gap-4 flex-shrink-0 items-center">
            <div class="flex items-center gap-1 whitespace-nowrap">
              <span
                class="text-base font-semibold text-slate-900 dark:text-slate-100"
                >{hosts.length}</span
              >
              <span class="text-xs text-slate-500 dark:text-slate-400"
                >hosts</span
              >
            </div>
            <div class="flex items-center gap-1 whitespace-nowrap">
              <span
                class="text-base font-semibold text-slate-900 dark:text-slate-100"
                >{totalJobs}</span
              >
              <span class="text-xs text-slate-500 dark:text-slate-400"
                >jobs</span
              >
            </div>
            {#if dataFromCache}
              <div
                class="flex items-center gap-1 whitespace-nowrap pl-4 border-l border-border ml-4"
              >
                <Clock class="h-4 w-4 text-muted-foreground" />
                <Badge variant="secondary">Cached</Badge>
              </div>
            {/if}
          </div>

          <!-- Search Bar -->
          <div class="flex-1 max-w-md">
            <div class="relative w-full">
              <div
                class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground pointer-events-none flex items-center justify-center"
              >
                <Search size={16} />
              </div>
              <input
                type="text"
                class="w-full pl-10 pr-10 py-2 border border-border rounded-lg text-sm transition-all bg-input focus:outline-none focus:border-accent focus:bg-background focus:shadow-sm focus:ring-2 focus:ring-accent/20 placeholder-muted-foreground"
                placeholder="Search jobs..."
                bind:value={search}
                oninput={handleFilterChange}
              />
              {#if search}
                <button
                  class="absolute right-2 top-1/2 transform -translate-y-1/2 p-1 bg-transparent border-0 text-muted-foreground cursor-pointer rounded hover:bg-secondary hover:text-destructive flex items-center justify-center transition-all"
                  onclick={() => {
                    search = "";
                    handleFilterChange();
                  }}
                >
                  <X size={14} />
                </button>
              {/if}
            </div>
          </div>
        </div>
      {/snippet}
    </NavigationHeader>
  {:else}
    <!-- Mobile header -->
    <div
      class="flex justify-between items-center p-3 bg-secondary border-b border-border relative z-50 shadow-sm"
    >
      <div class="flex items-center min-h-[40px] whitespace-nowrap">
        <!-- Stats on the left -->
        <div class="flex gap-4 flex-shrink-0 items-center">
          <div class="flex items-center gap-1 whitespace-nowrap">
            <span
              class="text-base font-semibold text-slate-900 dark:text-slate-100"
              >{hosts.length}</span
            >
            <span class="text-xs text-slate-500 dark:text-slate-400">hosts</span
            >
          </div>
          <div class="flex items-center gap-1 whitespace-nowrap">
            <span
              class="text-base font-semibold text-slate-900 dark:text-slate-100"
              >{totalJobs}</span
            >
            <span class="text-xs text-slate-500 dark:text-slate-400">jobs</span>
          </div>
        </div>

        <!-- Flexible spacer to push search and refresh to the right -->
        <div class="flex-1 min-w-8"></div>

        <!-- Expandable search -->
        <div
          class="flex items-center justify-center transition-all duration-300 ease-out overflow-hidden flex-shrink-0 {searchExpanded
            ? 'w-[180px] max-w-[180px]'
            : 'w-8'}"
        >
          {#if searchExpanded}
            <div
              class="relative w-full animate-in slide-in-from-right-2 duration-300"
            >
              <div
                class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground pointer-events-none flex items-center justify-center"
              >
                <Search size={16} />
              </div>
              <input
                type="text"
                class="w-full pl-10 pr-10 py-2 border border-border rounded-lg text-sm transition-all bg-input focus:outline-none focus:border-accent focus:bg-background focus:shadow-sm focus:ring-2 focus:ring-accent/20 placeholder-muted-foreground"
                placeholder="Search jobs..."
                bind:value={search}
                oninput={handleFilterChange}
                onblur={() => {
                  if (!search) searchExpanded = false;
                }}
                bind:this={searchInput}
              />
              {#if search}
                <button
                  class="absolute right-2 top-1/2 transform -translate-y-1/2 p-1 bg-transparent border-0 text-muted-foreground cursor-pointer rounded hover:bg-secondary hover:text-destructive flex items-center justify-center transition-all"
                  onclick={() => {
                    search = "";
                    handleFilterChange();
                  }}
                >
                  <X size={14} />
                </button>
              {/if}
            </div>
          {:else}
            <button
              class="flex items-center justify-center w-8 h-8 border-0 rounded-md bg-transparent text-muted-foreground cursor-pointer transition-all hover:bg-secondary hover:text-foreground"
              onclick={() => {
                searchExpanded = true;
                setTimeout(() => searchInput?.focus(), 100);
              }}
            >
              <Search size={16} />
            </button>
          {/if}
        </div>

        <!-- Refresh button -->
        <button
          onclick={handleManualRefresh}
          disabled={loading}
          class="flex items-center justify-center w-8 h-8 bg-background border border-border rounded-lg text-sm font-medium text-muted cursor-pointer transition-all flex-shrink-0 hover:bg-secondary hover:border-border disabled:opacity-50 disabled:cursor-not-allowed"
          title={loading || progressiveLoading
            ? "Loading from hosts..."
            : "Refresh"}
        >
          <RefreshCw
            class="w-4 h-4 {loading || progressiveLoading
              ? 'animate-spin'
              : ''}"
          />
        </button>
      </div>
    </div>
  {/if}

  {#if error}
    <div class="bg-destructive/10 border-b border-destructive/20 p-3">
      <p class="text-sm font-medium text-destructive">{error}</p>
    </div>
  {/if}

  <!-- Host connection warnings -->
  {#if hostsWithTimeouts.length > 0}
    <div
      class="bg-yellow-50 dark:bg-yellow-900/20 border-b border-yellow-200 dark:border-yellow-800 p-3"
    >
      <div class="flex items-center gap-2">
        <svg
          class="h-5 w-5 text-yellow-600 dark:text-yellow-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <p class="text-sm font-medium text-yellow-800 dark:text-yellow-200">
          Connection timeout: {hostsWithTimeouts
            .map((h) => h.hostname)
            .join(", ")}
          {#if hostsWithTimeouts.length === 1}
            - Some jobs may not be visible
          {:else}
            - Some jobs may not be visible from these hosts
          {/if}
        </p>
      </div>
    </div>
  {:else if hostsWithErrors.length > 0}
    <div
      class="bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-800 p-3"
    >
      <div class="flex items-center gap-2">
        <svg
          class="h-5 w-5 text-red-600 dark:text-red-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <p class="text-sm font-medium text-red-800 dark:text-red-200">
          Connection error: {hostsWithErrors.map((h) => h.hostname).join(", ")}
        </p>
      </div>
    </div>
  {/if}

  <!-- Filters removed since search is now in header -->

  <div class="flex-1 overflow-auto px-4 py-4">
    {#if progressiveLoading && filteredJobs.length === 0 && filteredArrayGroups.length === 0}
      <div class="flex items-center justify-center h-full">
        <div class="text-center text-muted-foreground">Loading jobs...</div>
      </div>
    {:else}
      {#if totalPartitions > 0 || partitionsLoading || partitionsError}
        <div class="mb-4">
          <CollapsibleSection
            title="Partition Resources"
            badge="{totalPartitions} partitions"
            subtitle={partitionsSubtitle}
            defaultExpanded={partitionsSectionExpanded}
            storageKey="jobspage-partitions-expanded"
          >
            {#if partitionsLoading}
              <div class="text-sm text-muted-foreground">
                Loading partition resources...
              </div>
            {:else if partitionsError}
              <div class="text-sm text-destructive">{partitionsError}</div>
            {:else if totalPartitions === 0}
              <div class="text-sm text-muted-foreground">
                No partition data available
              </div>
            {:else}
              <div class="space-y-3">
                {#each partitionStates as hostState (hostState.hostname)}
                  <div class="rounded-lg border border-border bg-background p-3">
                    <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
                      <div class="flex items-center gap-2 flex-wrap">
                        <span class="text-sm font-semibold text-foreground"
                          >{hostState.hostname}</span
                        >
                        {#if hostState.cached}
                          <Badge variant="secondary">Cached</Badge>
                        {/if}
                        {#if hostState.stale}
                          <Badge variant="warning">Stale</Badge>
                        {/if}
                      </div>
                      {#if hostState.updated_at}
                        <span class="text-xs text-muted-foreground"
                          >Updated {formatTimeAgo(hostState.updated_at)}</span
                        >
                      {/if}
                    </div>

                    {#if hostState.error}
                      <div class="text-sm text-destructive">
                        {hostState.error}
                      </div>
                    {:else}
                      <div class="overflow-x-auto">
                        <table class="min-w-[720px] w-full text-sm">
                          <thead>
                            <tr class="text-xs text-muted-foreground uppercase tracking-wide">
                              <th class="text-left font-medium py-2 pr-4">Partition</th>
                              <th class="text-left font-medium py-2 pr-4">Avail</th>
                              <th class="text-left font-medium py-2 pr-4">CPUs a/i/t</th>
                              <th class="text-left font-medium py-2 pr-4">GPUs u/t</th>
                              <th class="text-left font-medium py-2 pr-4">Nodes</th>
                              <th class="text-left font-medium py-2">State</th>
                            </tr>
                          </thead>
                          <tbody>
                            {#each hostState.partitions as partition (partition.partition)}
                              <tr class="border-t border-border/60">
                                <td class="py-2 pr-4 font-medium text-foreground">
                                  {partition.partition}
                                </td>
                                <td class="py-2 pr-4 text-muted-foreground">
                                  {partition.availability || "-"}
                                </td>
                                <td class="py-2 pr-4">
                                  <span class="text-foreground font-medium">
                                    {partition.cpus_alloc}/{partition.cpus_idle}/{partition.cpus_total}
                                  </span>
                                </td>
                                <td class="py-2 pr-4">
                                  {#if partition.gpus_total === null}
                                    <span class="text-muted-foreground">-</span>
                                  {:else if partition.gpus_total === 0}
                                    <span class="text-muted-foreground">0</span>
                                  {:else if partition.gpus_used === null}
                                    <span class="text-muted-foreground"
                                      >?/{partition.gpus_total}</span
                                    >
                                  {:else}
                                    <span class="text-foreground font-medium"
                                      >{partition.gpus_used}/{partition.gpus_total}</span
                                    >
                                  {/if}
                                </td>
                                <td class="py-2 pr-4 text-muted-foreground">
                                  {partition.nodes_total}
                                </td>
                                <td class="py-2 text-muted-foreground">
                                  {(partition.states || []).join(", ") || "-"}
                                </td>
                              </tr>
                            {/each}
                          </tbody>
                        </table>
                      </div>
                    {/if}
                  </div>
                {/each}
              </div>
            {/if}
          </CollapsibleSection>
        </div>
      {/if}

      <!-- Array job groups - Collapsible Section -->
      {#if filteredArrayGroups.length > 0}
        <div class="mb-4">
          <CollapsibleSection
            title="Array Jobs"
            badge="{filteredArrayGroups.length} total"
            subtitle="{activeArrayCount} active"
            defaultExpanded={arraysSectionExpanded}
            storageKey="jobspage-arrays-expanded"
          >
            <div class="space-y-2">
              {#each filteredArrayGroups as group (group.array_job_id + group.hostname)}
                <ArrayJobCard {group} />
              {/each}
            </div>
          </CollapsibleSection>
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
          <div class="text-center text-muted-foreground">No jobs found</div>
        </div>
      {/if}
    {/if}
  </div>
</div>

<style>
  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
</style>
