<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import { push } from 'svelte-spa-router';
  import { navigationActions } from '../stores/navigation';
  import { fade, fly, slide } from 'svelte/transition';
  import {
    watchers,
    watcherEvents,
    watchersLoading,
    eventsLoading,
    fetchAllWatchers,
    fetchWatcherEvents,
    connectWatcherWebSocket,
    disconnectWatcherWebSocket
  } from '../stores/watchers';
  import { jobStateManager } from '../lib/JobStateManager';
  import { api } from '../services/api';
  import WatcherCard from '../components/WatcherCard.svelte';
  import WatcherEvents from '../components/WatcherEvents.svelte';
  import EventsView from '../components/EventsView.svelte';
  import AttachWatchersDialog from '../components/AttachWatchersDialog.svelte';
  import WatcherCreator from '../components/WatcherCreator.svelte';
  import JobSelectionDialog from '../components/JobSelectionDialog.svelte';
  import NavigationHeader from '../components/NavigationHeader.svelte';

  import {
    RefreshCw,
    Plus,
    Search,
    X,
    Eye,
    Activity,
    Clock,
    ArrowLeft,
    Filter,
    Grid3X3,
    List,
    ChevronDown
  } from 'lucide-svelte';

  // Get jobs store
  const allCurrentJobs = jobStateManager.getAllJobs();


  let activeTab: 'watchers' | 'events' = $state('watchers');
  let viewMode: 'grid' | 'grouped' = $state('grid');
  let searchQuery = $state('');
  let filterState: 'all' | 'active' | 'paused' | 'completed' = $state('all');
  let isMobile = $state(false);
  let showMobileFilters = false;
  let collapsedJobs: Set<string> = $state(new Set());
  let error: string | null = $state(null);

  // Dialog state
  let showAttachDialog = $state(false);
  let showStreamlinedCreator = $state(false);
  let showJobSelectionDialog = $state(false);
  let selectedJobId: string | null = $state(null);
  let selectedHostname: string | null = $state(null);
  let useStreamlinedInterface = true; // Toggle between old and new interface
  let useModernEvents = true; // Toggle between old and new events view
  let copiedWatcherConfig: any = $state(null);

  // Fuzzy search scoring function - returns relevance score (lower is better)
  function getWatcherSearchScore(watcher: any, searchTerm: string): number {
    if (!searchTerm) return 0;
    const term = searchTerm.toLowerCase();

    // Exact match scores
    if (watcher.job_id?.toString() === term) return 0;
    if (watcher.name?.toLowerCase() === term) return 1;
    if (watcher.hostname?.toLowerCase() === term) return 2;
    if (watcher.pattern?.toLowerCase() === term) return 3;

    // Starts with scores
    if (watcher.job_id?.toString().startsWith(term)) return 10;
    if (watcher.name?.toLowerCase().startsWith(term)) return 11;
    if (watcher.hostname?.toLowerCase().startsWith(term)) return 12;
    if (watcher.pattern?.toLowerCase().startsWith(term)) return 13;

    // Contains scores
    if (watcher.job_id?.toString().includes(term)) return 20;
    if (watcher.name?.toLowerCase().includes(term)) return 21;
    if (watcher.hostname?.toLowerCase().includes(term)) return 22;
    if (watcher.pattern?.toLowerCase().includes(term)) return 23;

    // No match
    return 999;
  }





  function checkMobile() {
    isMobile = window.innerWidth < 768;
    if (!isMobile) {
      showMobileFilters = false;
    }
  }

  async function refreshData() {
    error = null; // Clear any existing errors
    try {
      // Fetch jobs and watchers in parallel for better performance
      await Promise.all([
        jobStateManager.syncAllHosts(),
        fetchAllWatchers()
      ]);
      // Always fetch events to populate the latest events for each watcher
      await fetchWatcherEvents();
    } catch (err) {
      console.error('Failed to refresh watcher data:', err);
      error = 'Failed to refresh watcher data. Please try again.';
    }
  }

  async function openAttachDialog() {
    console.log('openAttachDialog called');
    error = null;

    // Get current cached jobs
    const allJobs = jobStateManager.getAllJobs();
    const cachedJobs = get(allJobs);
    const runningJobs = cachedJobs.filter(job =>
      job.state === 'R' || job.state === 'PD'
    );

    // If we have exactly one job, open the creator directly
    if (runningJobs.length === 1) {
      selectedJobId = runningJobs[0].job_id;
      selectedHostname = runningJobs[0].hostname;
      console.log('Single job - setting selectedJobId:', selectedJobId, 'hostname:', selectedHostname);

      if (useStreamlinedInterface) {
        console.log('Opening streamlined creator');
        showStreamlinedCreator = true;
      } else {
        showAttachDialog = true;
      }
    } else {
      // Show job selection dialog immediately with whatever jobs we have
      // The dialog will fetch fresh jobs in the background
      showJobSelectionDialog = true;
    }
  }

  // Store selected jobs for multi-job watcher creation
  let pendingMultiJobSelection: any[] = [];

  async function handleJobSelection(event: CustomEvent) {
    const selection = event.detail;
    showJobSelectionDialog = false;

    // Handle multi-select payload format: { jobs: [...], action: 'apply'/'edit' }
    let jobs: any[];
    let action: 'apply' | 'edit' = 'apply';

    if (selection.jobs && selection.action) {
      // Multi-select payload
      jobs = selection.jobs;
      action = selection.action;
    } else if (Array.isArray(selection)) {
      // Legacy array format
      jobs = selection;
    } else {
      // Single job
      jobs = [selection];
    }

    if (jobs.length === 1) {
      // Single job - open creator
      selectedJobId = jobs[0].job_id;
      selectedHostname = jobs[0].hostname;

      if (useStreamlinedInterface) {
        showStreamlinedCreator = true;
      } else {
        showAttachDialog = true;
      }
    } else if (jobs.length > 1) {
      // Store the selected jobs
      pendingMultiJobSelection = jobs;

      if (copiedWatcherConfig) {
        if (action === 'edit') {
          // Open creator for editing before applying to multiple jobs
          // Use the first job for the creator context
          selectedJobId = jobs[0].job_id;
          selectedHostname = jobs[0].hostname;
          showStreamlinedCreator = true;
        } else {
          // Apply directly without editing
          await applyWatcherToMultipleJobs(jobs, copiedWatcherConfig);
        }
      } else {
        // No config - prompt user to create watcher first for one job
        error = 'Please configure a watcher on one job first, then copy it to multiple jobs.';
        setTimeout(() => error = null, 5000);
        pendingMultiJobSelection = [];
      }
    }
  }

  async function applyWatcherToMultipleJobs(jobs: any[], config: any) {
    try {
      const promises = jobs.map(job =>
        api.post('/api/watchers', {
          job_id: job.job_id,
          hostname: job.hostname,
          name: config.name,
          pattern: config.pattern,
          captures: config.captures || [],
          interval_seconds: config.interval || 60,
          condition: config.condition,
          actions: config.actions || [],
          timer_mode_enabled: config.timer_mode_enabled || false,
          timer_interval_seconds: config.timer_interval_seconds || 30
        }).catch((err: any) => ({ error: err }))
      );

      const results = await Promise.all(promises);

      const successful = results.filter((r: any) => !r.error).length;
      const failed = results.filter((r: any) => r.error).length;

      if (successful > 0) {
        console.log(`Successfully created ${successful} watcher(s)`);
      }
      if (failed > 0) {
        console.error(`Failed to create ${failed} watcher(s)`);
        error = `Created ${successful} watcher(s), but ${failed} failed.`;
        setTimeout(() => error = null, 5000);
      }

      copiedWatcherConfig = null;
      pendingMultiJobSelection = [];
      await refreshData();
    } catch (err) {
      console.error('Failed to create watchers:', err);
      error = 'Failed to create watchers for selected jobs.';
      setTimeout(() => error = null, 5000);
      pendingMultiJobSelection = [];
    }
  }

  async function handleWatcherCopy(event: CustomEvent) {
    copiedWatcherConfig = event.detail;

    // Get current cached jobs immediately
    const allJobs = jobStateManager.getAllJobs();
    const cachedJobs = get(allJobs);
    const runningJobs = cachedJobs.filter(job =>
      job.state === 'R' || job.state === 'PD'
    );

    // Store the original job info for pre-selection if it's still running
    if (copiedWatcherConfig.job_id && copiedWatcherConfig.hostname) {
      const originalJob = runningJobs.find(job =>
        job.job_id === copiedWatcherConfig.job_id &&
        job.hostname === copiedWatcherConfig.hostname
      );

      // Pre-select the original job if it's still running (for the dialog)
      if (originalJob) {
        selectedJobId = originalJob.job_id;
        selectedHostname = originalJob.hostname;
      }
    }

    // Always show job selection dialog when copying
    // This allows users to choose whether to copy to the same job or a different one
    if (runningJobs.length === 0) {
      // No jobs running, need to inform user
      error = 'No running jobs available. Please start a job first.';
      setTimeout(() => error = null, 5000);
    } else {
      // Show job selection dialog with pre-selected job (if available)
      showJobSelectionDialog = true;
    }
  }

  async function handleAttachSuccess(event?: CustomEvent) {
    error = null; // Clear any existing errors
    showAttachDialog = false;
    showStreamlinedCreator = false;

    // If we have pending multi-job selections, apply the watcher to all of them
    if (pendingMultiJobSelection.length > 1 && copiedWatcherConfig) {
      // Get the updated config from the event if available
      const updatedConfig = event?.detail || copiedWatcherConfig;

      // Apply to all pending jobs except the first one (already created)
      const remainingJobs = pendingMultiJobSelection.slice(1);

      if (remainingJobs.length > 0) {
        await applyWatcherToMultipleJobs(remainingJobs, updatedConfig);
      }

      pendingMultiJobSelection = [];
    }

    selectedJobId = null;
    selectedHostname = null;
    copiedWatcherConfig = null;
    await refreshData();
  }

  function clearSearch() {
    searchQuery = '';
  }

  function toggleJobGroup(jobKey: string) {
    if (collapsedJobs.has(jobKey)) {
      collapsedJobs.delete(jobKey);
    } else {
      collapsedJobs.add(jobKey);
    }
    collapsedJobs = collapsedJobs;
  }

  function handleTabClick(tab: 'watchers' | 'events') {
    activeTab = tab;
    // Events are now fetched automatically during refreshData()
  }

  onMount(async () => {
    checkMobile();
    window.addEventListener('resize', checkMobile);

    // Set navigation context for proper back navigation
    navigationActions.setContext('watcher', {
      previousRoute: window.location.pathname
    });

    // Initial data load
    await refreshData();

    // Connect WebSocket
    connectWatcherWebSocket();
  });

  onDestroy(() => {
    window.removeEventListener('resize', checkMobile);
    disconnectWatcherWebSocket();
  });
  // Computed values with fuzzy search
  let sortedWatchers = $derived((() => {
    let filtered = $watchers.filter(w => {
      if (filterState === 'all') return true;
      return w.state === filterState;
    });

    // Apply search with ranking
    if (searchQuery) {
      const scoredWatchers = filtered
        .map(watcher => ({ watcher, score: getWatcherSearchScore(watcher, searchQuery) }))
        .filter(item => item.score < 999)
        .sort((a, b) => a.score - b.score)
        .map(item => item.watcher);

      filtered = scoredWatchers;
    } else {
      // Default sort by creation date when no search
      filtered = filtered.sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime());
    }

    return filtered;
  })());
  // Enhance watchers with job names from current jobs
  let enhancedWatchers = $derived(sortedWatchers.map(watcher => {
    const jobInfo = get(allCurrentJobs).find(job =>
      job.job_id === watcher.job_id && job.hostname === watcher.hostname
    );
    return {
      ...watcher,
      job_name: jobInfo?.name || watcher.job_name || null
    };
  }));
  let activeCount = $derived($watchers.filter(w => w && w.state === 'active').length);
  let pausedCount = $derived($watchers.filter(w => w && w.state === 'paused').length);
  let staticCount = $derived($watchers.filter(w => w && w.state === 'static').length);
  let completedCount = $derived($watchers.filter(w => w && w.state === 'completed').length);
  let totalCount = $derived($watchers.length);
  // Create a map of latest events by watcher_id for quick lookup
  let latestEventsByWatcher = $derived((() => {
    const eventMap: Record<number, any> = {};
    $watcherEvents.forEach(event => {
      if (!eventMap[event.watcher_id] || new Date(event.timestamp) > new Date(eventMap[event.watcher_id].timestamp)) {
        eventMap[event.watcher_id] = event;
      }
    });
    return eventMap;
  })());
  // Group watchers by job
  let watchersByJob = $derived((() => {
    const groups: Record<string, {
      job_id: string;
      job_name?: string | null;
      hostname: string;
      watchers: typeof sortedWatchers;
      stats: { active: number; paused: number; static: number; completed: number };
    }> = {};

    sortedWatchers.forEach(watcher => {
      const jobKey = `${watcher.job_id}-${watcher.hostname}`;

      if (!groups[jobKey]) {
        // Try to find job info from current jobs to get the job name
        const jobInfo = get(allCurrentJobs).find(job =>
          job.job_id === watcher.job_id && job.hostname === watcher.hostname
        );

        groups[jobKey] = {
          job_id: watcher.job_id || 'unknown',
          job_name: jobInfo?.name || watcher.job_name || null,
          hostname: watcher.hostname || 'unknown',
          watchers: [],
          stats: { active: 0, paused: 0, static: 0, completed: 0 }
        };
      }

      groups[jobKey].watchers.push(watcher);

      // Update stats (check for undefined state)
      if (watcher.state) {
        if (watcher.state === 'active') groups[jobKey].stats.active++;
        else if (watcher.state === 'paused') groups[jobKey].stats.paused++;
        else if (watcher.state === 'static') groups[jobKey].stats.static++;
        else if (watcher.state === 'completed') groups[jobKey].stats.completed++;
      }
    });

    return groups;
  })());
</script>

<div class="h-full flex flex-col bg-[var(--background)]">
  {#if !isMobile}
    <NavigationHeader
      showRefresh={true}
      refreshing={$watchersLoading || $eventsLoading}
      on:refresh={refreshData}
    >
      {#snippet left()}
            <div  class="flex items-center space-x-4">
          <!-- Tab Navigation -->
          <div class="flex items-center bg-[var(--secondary)] rounded-lg p-1">
              <button
                class="header-tab {activeTab === 'watchers' ? 'header-tab-active' : ''}"
                onclick={() => handleTabClick('watchers')}
              >
                <Eye class="w-4 h-4" />
                Watchers
              </button>
              <button
                class="header-tab {activeTab === 'events' ? 'header-tab-active' : ''}"
                onclick={() => handleTabClick('events')}
              >
                <Activity class="w-4 h-4" />
                Events
              </button>
            </div>

          <!-- Search Bar -->
          {#if activeTab === 'watchers'}
            <div class="header-search">
              <div class="search-bar">
                <div class="search-icon">
                  <Search size={16} />
                </div>
                <input
                  type="text"
                  class="search-input"
                  placeholder="Search watchers..."
                  bind:value={searchQuery}
                />
                {#if searchQuery}
                  <button class="clear-btn" onclick={clearSearch}>
                    <X size={14} />
                  </button>
                {/if}
              </div>
            </div>
          {/if}
        </div>
          {/snippet}

      {#snippet actions()}
            <div >
          <button
            onclick={openAttachDialog}
            class="inline-flex items-center gap-2 px-3 py-2 bg-black text-white text-sm rounded-lg hover:bg-gray-800 transition-colors"
          >
            <Plus class="w-4 h-4" />
            Create
          </button>
        </div>
          {/snippet}

      <!-- Filters in additional slot -->
      {#snippet additional()}
            <div  class="bg-[var(--secondary)] border-t border-[var(--border)] py-3" class:hidden={activeTab !== 'watchers'}>
          <div class="flex justify-between items-center">
            <!-- Filter Tabs -->
            <div class="flex gap-2">
              <button
                class="filter-tab-modern {filterState === 'all' ? 'filter-tab-active' : ''}"
                onclick={() => filterState = 'all'}
              >
                <div class="w-2 h-2 bg-[var(--muted)] rounded-full"></div>
                All
                <span class="filter-count">{totalCount}</span>
              </button>
              <button
                class="filter-tab-modern {filterState === 'active' ? 'filter-tab-active' : ''}"
                onclick={() => filterState = 'active'}
              >
                <div class="w-2 h-2 bg-[var(--success)] rounded-full"></div>
                Active
                <span class="filter-count">{activeCount}</span>
              </button>
              <button
                class="filter-tab-modern {filterState === 'paused' ? 'filter-tab-active' : ''}"
                onclick={() => filterState = 'paused'}
              >
                <div class="w-2 h-2 bg-[var(--warning)] rounded-full"></div>
                Paused
                <span class="filter-count">{pausedCount}</span>
              </button>
              <button
                class="filter-tab-modern {filterState === 'completed' ? 'filter-tab-active' : ''}"
                onclick={() => filterState = 'completed'}
              >
                <div class="w-2 h-2 bg-[var(--accent)] rounded-full"></div>
                Completed
                <span class="filter-count">{completedCount}</span>
              </button>
            </div>

            <!-- View Toggle -->
            <div class="flex gap-1 bg-[var(--secondary)] rounded-lg p-1">
              <button
                class="view-toggle {viewMode === 'grid' ? 'view-toggle-active' : ''}"
                onclick={() => viewMode = 'grid'}
                title="Grid view"
              >
                <Grid3X3 class="w-4 h-4" />
                <span class="view-toggle-label">Grid</span>
              </button>
              <button
                class="view-toggle {viewMode === 'grouped' ? 'view-toggle-active' : ''}"
                onclick={() => viewMode = 'grouped'}
                title="Grouped by job"
              >
                <List class="w-4 h-4" />
                <span class="view-toggle-label">By Job</span>
              </button>
            </div>
          </div>
        </div>
          {/snippet}
    </NavigationHeader>
  {:else}
    <!-- Mobile header -->
    <div class="header mobile-header">
      <div class="flex items-center justify-between">
        <!-- Tab Navigation -->
        <div class="flex items-center bg-[var(--secondary)] rounded-lg p-1">
          <button
            class="header-tab {activeTab === 'watchers' ? 'header-tab-active' : ''}"
            onclick={() => handleTabClick('watchers')}
          >
            <Eye class="w-4 h-4" />
            Watchers
          </button>
          <button
            class="header-tab {activeTab === 'events' ? 'header-tab-active' : ''}"
            onclick={() => handleTabClick('events')}
          >
            <Activity class="w-4 h-4" />
            Events
          </button>
        </div>

        <!-- Actions -->
        <div class="flex items-center space-x-2">
          <button
            onclick={refreshData}
            disabled={$watchersLoading || $eventsLoading}
            class="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
            title="Refresh"
          >
            <RefreshCw class="w-4 h-4 {$watchersLoading || $eventsLoading ? 'animate-spin' : ''}" />
          </button>

          <button
            onclick={openAttachDialog}
            class="inline-flex items-center gap-2 px-3 py-2 bg-black text-white text-sm rounded-lg hover:bg-gray-800 transition-colors"
          >
            <Plus class="w-4 h-4" />
            Create
          </button>
        </div>
      </div>
    </div>
  {/if}
  <!-- Main Content -->
  <main class="flex-1 flex flex-col overflow-hidden">
    {#if activeTab === 'watchers'}
      <!-- Error Banner -->
      {#if error}
        <div class="bg-[var(--error-bg)] border-b border-[var(--destructive)] flex-shrink-0">
          <div class="px-4 sm:px-6 lg:px-8 py-3">
            <div class="flex items-center justify-between">
              <div class="flex items-center space-x-3">
                <svg class="h-5 w-5 text-[var(--destructive)]" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                </svg>
                <p class="text-sm font-medium text-[var(--destructive)]">{error}</p>
              </div>
              <button
                onclick={() => error = null}
                class="inline-flex items-center text-sm font-medium text-[var(--destructive)] hover:opacity-80"
                aria-label="Dismiss error"
              >
                <svg class="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      {/if}

      <!-- Scrollable Watchers Container -->
      <div class="flex-1 overflow-y-auto">
        <div class="p-4 sm:p-6 lg:p-8">
        <!-- Watchers Content -->
        {#if $watchersLoading}
          <div class="flex items-center justify-center py-16">
            <div class="text-center">
              <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--foreground)] mx-auto mb-4"></div>
              <p class="text-[var(--muted-foreground)]">Loading watchers...</p>
            </div>
          </div>
        {:else if sortedWatchers.length === 0}
          <div class="flex items-center justify-center py-16" in:fade>
            <div class="text-center">
              <Eye class="mx-auto h-12 w-12 text-[var(--muted-foreground)] mb-4" />
              <h3 class="text-lg font-medium text-[var(--foreground)] mb-2">
                {#if searchQuery}
                  No watchers found
                {:else if filterState !== 'all'}
                  No {filterState} watchers
                {:else}
                  No watchers yet
                {/if}
              </h3>
              <p class="text-[var(--muted-foreground)] mb-6">
                {#if searchQuery}
                  Try adjusting your search criteria
                {:else if filterState !== 'all'}
                  No watchers match this status
                {:else}
                  Create your first watcher to start monitoring jobs
                {/if}
              </p>
              {#if !searchQuery && filterState === 'all'}
                <button
                  onclick={openAttachDialog}
                  class="inline-flex items-center gap-2 px-4 py-2 bg-[var(--foreground)] text-[var(--background)] text-sm rounded-lg hover:opacity-90 transition-colors"
                >
                  <Plus class="w-4 h-4" />
                  Create Watcher
                </button>
              {/if}
            </div>
          </div>
        {:else if viewMode === 'grid'}
          <!-- Grid View (Flat) -->
          <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-6">
            {#each enhancedWatchers as watcher, i}
              <div
                class="transition-all duration-200 hover:scale-[1.02] min-w-0"
                in:fly={{ y: 20, duration: 300, delay: i * 50 }}
              >
                <WatcherCard
                  {watcher}
                  showJobLink={true}
                  lastEvent={latestEventsByWatcher[watcher.id]}
                  on:copy={handleWatcherCopy}
                />
              </div>
            {/each}
          </div>
        {:else if viewMode === 'grouped'}
          <!-- Grouped View (By Job) -->
          <div class="space-y-6">
            {#each Object.entries(watchersByJob) as [jobKey, jobGroup], i}
              <div
                class="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-all duration-200"
                in:fly={{ y: 20, duration: 300, delay: i * 100 }}
              >
                <!-- Job Header -->
                <button
                  class="w-full p-4 bg-[var(--secondary)] hover:bg-[var(--muted)] transition-colors text-left flex justify-between items-center border-b border-[var(--border)]"
                  onclick={() => toggleJobGroup(jobKey)}
                >
                  <div class="space-y-1">
                    <h3 class="text-lg font-semibold flex items-center gap-2 text-[var(--foreground)]">
                      Job #{jobGroup.job_id}
                      {#if jobGroup.job_name && jobGroup.job_name !== 'N/A'}
                        <span class="text-[var(--muted-foreground)] font-normal">• {jobGroup.job_name}</span>
                      {/if}
                    </h3>
                    <p class="text-sm text-[var(--muted-foreground)]">{jobGroup.hostname}</p>
                  </div>

                  <div class="flex items-center gap-6">
                    <div class="text-center">
                      <div class="text-lg font-semibold text-[var(--foreground)]">{jobGroup.watchers.length}</div>
                      <div class="text-xs text-[var(--muted-foreground)]">watchers</div>
                    </div>
                    {#if jobGroup.stats.active > 0}
                      <div class="text-center">
                        <div class="text-lg font-semibold text-[var(--success)]">{jobGroup.stats.active}</div>
                        <div class="text-xs text-[var(--success)]">active</div>
                      </div>
                    {/if}
                    {#if jobGroup.stats.paused > 0}
                      <div class="text-center">
                        <div class="text-lg font-semibold text-[var(--warning)]">{jobGroup.stats.paused}</div>
                        <div class="text-xs text-[var(--warning)]">paused</div>
                      </div>
                    {/if}
                    <ChevronDown
                      class="h-5 w-5 text-[var(--muted-foreground)] transition-transform duration-300 {!collapsedJobs.has(jobKey) ? 'rotate-180' : ''}"
                    />
                  </div>
                </button>

                <!-- Watchers Grid -->
                {#if !collapsedJobs.has(jobKey)}
                  <div class="p-6 grid grid-cols-1 xl:grid-cols-2 2xl:grid-cols-3 gap-4" transition:slide={{ duration: 250 }}>
                    {#each jobGroup.watchers as watcher, j}
                      <div
                        class="transition-all duration-200 hover:scale-[1.02] min-w-0"
                        in:fly={{ x: -20, duration: 200, delay: j * 50 }}
                      >
                        <WatcherCard
                          {watcher}
                          showJobLink={false}
                          lastEvent={latestEventsByWatcher[watcher.id]}
                          on:copy={handleWatcherCopy}
                        />
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
        </div>
      </div>

    {:else if activeTab === 'events'}
      <!-- Scrollable Events Container -->
      <div class="flex-1 overflow-y-auto">
        <div class="p-4 sm:p-6 lg:p-8">
          {#if useModernEvents}
            <EventsView />
          {:else if $eventsLoading}
            <div class="flex items-center justify-center py-16">
              <div class="text-center">
                <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto mb-4"></div>
                <p class="text-gray-500">Loading events...</p>
              </div>
            </div>
          {:else}
            <WatcherEvents />
          {/if}
        </div>
      </div>
    {/if}

    <!-- Streamlined Watcher Creator -->
    {#if showStreamlinedCreator && selectedJobId && selectedHostname}
      <WatcherCreator
        jobId={selectedJobId}
        hostname={selectedHostname}
        {copiedWatcherConfig}
        isVisible={true}
        on:created={handleAttachSuccess}
        on:close={() => {
          showStreamlinedCreator = false;
          selectedJobId = null;
          selectedHostname = null;
          copiedWatcherConfig = null;
        }}
      />
    {/if}
  </main>
</div>

<!-- Dialogs -->
{#if showJobSelectionDialog}
  <JobSelectionDialog
    title={copiedWatcherConfig ? "Select Job(s) for Copied Watcher" : "Select Job(s)"}
    description={copiedWatcherConfig ? "Choose which job(s) to attach the copied watcher to (including completed jobs for static watchers)" : "Choose job(s) to attach watchers to (including completed jobs for static watchers)"}
    preSelectedJobId={selectedJobId}
    preSelectedHostname={selectedHostname}
    allowMultiSelect={true}
    includeCompletedJobs={true}
    on:select={handleJobSelection}
    on:close={() => {
      showJobSelectionDialog = false;
      copiedWatcherConfig = null;
      selectedJobId = null;
      selectedHostname = null;
    }}
  />
{/if}

{#if showAttachDialog && selectedJobId && selectedHostname}
  <AttachWatchersDialog
    jobId={selectedJobId}
    hostname={selectedHostname}
    copiedConfig={copiedWatcherConfig}
    on:close={() => showAttachDialog = false}
    on:success={handleAttachSuccess}
  />
{/if}

<style>
  /* Header tab styles */
  .header-tab {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--muted-foreground);
    border-radius: 0.375rem;
    transition: all 0.15s;
    border: none;
    background: transparent;
    cursor: pointer;
  }

  .header-tab:hover {
    color: var(--foreground);
    background: color-mix(in srgb, var(--background) 50%, transparent);
  }

  .header-tab-active {
    background: var(--background);
    color: var(--foreground);
    box-shadow: 0 1px 2px 0 color-mix(in srgb, var(--foreground) 10%, transparent);
  }

  /* Search bar styles */
  .search-bar {
    position: relative;
    width: 300px;
  }

  .search-icon {
    position: absolute;
    left: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
    color: var(--muted-foreground);
    pointer-events: none;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .search-input {
    width: 100%;
    padding: 0.5rem 2.5rem 0.5rem 2.5rem;
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    font-size: 0.875rem;
    transition: all 0.15s;
    background: var(--secondary);
  }

  .search-input:focus {
    outline: none;
    border-color: var(--accent);
    background: var(--background);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 10%, transparent);
  }

  .search-input::placeholder {
    color: var(--muted-foreground);
  }

  .clear-btn {
    position: absolute;
    right: 0.5rem;
    top: 50%;
    transform: translateY(-50%);
    padding: 0.25rem;
    background: none;
    border: none;
    color: var(--muted-foreground);
    cursor: pointer;
    border-radius: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }

  .clear-btn:hover {
    background: var(--secondary);
    color: var(--destructive);
  }

  /* Modern filter tab styles */
  .filter-tab-modern {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--muted-foreground);
    background: transparent;
    border: none;
    border-radius: 0.5rem;
    transition: all 0.15s;
    cursor: pointer;
  }

  .filter-tab-modern:hover {
    background: var(--secondary);
    color: var(--foreground);
  }

  .filter-tab-modern.filter-tab-active {
    background: var(--foreground);
    color: white;
  }

  .filter-tab-modern.filter-tab-active:hover {
    background: var(--foreground);
  }

  .filter-count {
    background: rgba(0, 0, 0, 0.1);
    color: inherit;
    padding: 0.125rem 0.5rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    min-width: 1.5rem;
    text-align: center;
  }

  .filter-tab-active .filter-count {
    background: rgba(255, 255, 255, 0.2);
  }

  .view-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.375rem;
    padding: 0.5rem 0.75rem;
    border-radius: 0.375rem;
    color: var(--muted-foreground);
    transition: all 0.2s;
    font-size: 0.875rem;
    font-weight: 500;
    border: none;
    background: transparent;
    cursor: pointer;
  }

  .view-toggle:hover {
    color: var(--foreground);
    background: color-mix(in srgb, var(--background) 50%, transparent);
  }

  .view-toggle-active {
    background: var(--background);
    color: var(--foreground);
    box-shadow: 0 1px 2px 0 color-mix(in srgb, var(--foreground) 5%, transparent);
  }

  .view-toggle-active:hover {
    color: var(--foreground);
  }

  .view-toggle-label {
    white-space: nowrap;
  }

  /* Header search styling similar to JobsPage */
  .header-search {
    flex: 1;
    max-width: 400px;
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
    color: var(--muted-foreground);
    pointer-events: none;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .search-input {
    width: 100%;
    padding: 0.5rem 2.5rem;
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    font-size: 0.875rem;
    transition: all 0.15s;
    background: var(--secondary);
  }

  .search-input:focus {
    outline: none;
    border-color: var(--accent);
    background: var(--background);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 10%, transparent);
  }

  .search-input::placeholder {
    color: var(--muted-foreground);
  }

  .clear-btn {
    position: absolute;
    right: 0.5rem;
    top: 50%;
    transform: translateY(-50%);
    padding: 0.25rem;
    background: none;
    border: none;
    color: var(--muted-foreground);
    cursor: pointer;
    border-radius: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }

  .clear-btn:hover {
    background: var(--secondary);
    color: var(--destructive);
  }

  .header.mobile-header {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  }
</style>
