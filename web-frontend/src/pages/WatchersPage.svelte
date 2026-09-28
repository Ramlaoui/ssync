<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { navigationActions } from '../stores/navigation';
  import {
    connectWatcherWebSocket,
    disconnectWatcherWebSocket,
    eventsLoading,
    fetchAllWatchers,
    fetchWatcherEvents,
    fetchWatcherStats,
    watcherEvents,
    watchers,
    watchersLoading,
    watcherSocketConnected,
    watcherStats,
  } from '../stores/watchers';
  import { jobStateManager } from '../lib/JobStateManager';
  import { api } from '../services/api';
  import type { Watcher, WatcherEvent } from '../types/watchers';
  import WatcherCard from '../components/WatcherCard.svelte';
  import WatcherActivityFeed from '../components/WatcherActivityFeed.svelte';
  import WatcherCreator from '../components/WatcherCreator.svelte';
  import JobSelectionDialog from '../components/JobSelectionDialog.svelte';
  import IconButton from '../components/workspace/IconButton.svelte';
  import {
    Layers,
    Plus,
    Radio,
    RefreshCw,
    Search,
    Server,
    TriangleAlert,
    X,
  } from 'lucide-svelte';

  const allCurrentJobs = jobStateManager.getAllJobs();
  // The list endpoint returns the most recent watchers up to this cap, without a total.
  const WATCHER_LIMIT = 300;

  type FilterState = 'live' | 'active' | 'paused' | 'completed' | 'static' | 'all';
  type SortMode = 'activity' | 'recent' | 'name';
  type BackgroundRefreshScope = 'events' | 'all';
  type EnhancedWatcher = Watcher & { job_name?: string | null };
  type HostSummary = {
    host: string;
    total: number;
    active: number;
    paused: number;
    recentEvents: number;
    latest?: string;
  };

  let searchQuery = $state('');
  let filterState: FilterState = $state('live');
  let sortMode: SortMode = $state('activity');
  let selectedWatcherId: number | null = $state(null);
  let error: string | null = $state(null);
  let watcherItems = $state<Watcher[]>([]);
  let watcherEventItems = $state<WatcherEvent[]>([]);
  let jobItems = $state<any[]>([]);

  let showStreamlinedCreator = $state(false);
  let showJobSelectionDialog = $state(false);
  let copiedWatcherConfig: any = $state(null);
  let selectedJobId: string | null = $state(null);
  let selectedHostname: string | null = $state(null);
  let pendingMultiJobSelection: any[] = [];
  let unsubscribePageStores: Array<() => void> = [];
  let pageRefreshing = $state(false);
  let backgroundRefreshTimer: ReturnType<typeof setTimeout> | null = null;
  let pendingBackgroundScope: BackgroundRefreshScope = 'events';
  let urlSelectionPending = false;
  let listFetchedComplete = $state(false);
  let narrowLayout = $state(false);

  function getWatcherSearchText(
    watcher: EnhancedWatcher,
    latestEvent: WatcherEvent | undefined,
  ): string {
    return [
      watcher.name,
      watcher.job_id,
      watcher.hostname,
      watcher.job_name,
      watcher.pattern,
      watcher.actions?.map((action) => action.type).join(' '),
      latestEvent?.action_type,
      latestEvent?.matched_text,
      latestEvent?.action_result,
      watcher.trigger_on_job_end ? 'job end terminal states' : '',
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
  }

  function formatRelativeTime(timestamp?: string | null): string {
    if (!timestamp) return 'No activity yet';
    const date = new Date(timestamp);
    const diffMinutes = Math.floor((Date.now() - date.getTime()) / 60000);

    if (diffMinutes < 1) return 'just now';
    if (diffMinutes < 60) return `${diffMinutes}m ago`;

    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours}h ago`;

    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  const filterLabels: Record<FilterState, string> = {
    live: 'Active & paused',
    active: 'Active',
    paused: 'Paused',
    completed: 'Completed',
    static: 'Static',
    all: 'All',
  };

  function matchesFilter(watcher: Watcher, state: FilterState): boolean {
    if (state === 'all') return true;
    if (state === 'live') return watcher.state === 'active' || watcher.state === 'paused';
    return watcher.state === state;
  }

  function truncateInline(value?: string | null, fallback = 'No event payload'): string {
    const text = value?.trim() || fallback;
    return text.length > 84 ? `${text.slice(0, 81)}...` : text;
  }

  function getWatcherRouteParams(): URLSearchParams {
    if (typeof window === 'undefined') return new URLSearchParams();
    const hashQueryIndex = window.location.hash.indexOf('?');
    if (hashQueryIndex >= 0) {
      return new URLSearchParams(window.location.hash.slice(hashQueryIndex + 1));
    }
    return new URLSearchParams(window.location.search);
  }

  function updateSelectionInUrl(watcherId: number | null) {
    if (typeof window === 'undefined') return;

    const url = new URL(window.location.href);
    const routeParams = getWatcherRouteParams();
    if (watcherId == null) {
      routeParams.delete('watcher');
    } else {
      routeParams.set('watcher', String(watcherId));
    }

    const nextQuery = routeParams.toString();
    const nextUrl = `${url.origin}/#/watchers${nextQuery ? `?${nextQuery}` : ''}`;
    window.history.replaceState({}, '', nextUrl);
  }

  function readSelectionFromUrl() {
    if (typeof window === 'undefined') return;
    const watcherParam = getWatcherRouteParams().get('watcher');
    if (!watcherParam) return;
    const parsed = Number(watcherParam);
    if (!Number.isNaN(parsed)) {
      selectedWatcherId = parsed;
      urlSelectionPending = true;
    }
  }

  function refreshJobNamesInBackground() {
    void jobStateManager.syncAllHosts(false, false, { limit: 50 }).catch((err) => {
      console.warn('Failed to refresh job names for watchers:', err);
    });
  }

  function scrollToElement(id: string) {
    if (typeof window === 'undefined') return;
    window.requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
    });
  }

  function inspectWatcher(
    watcherId: number,
    options: { scrollToCard?: boolean; scrollToActivity?: boolean } = {},
  ) {
    selectedWatcherId = watcherId;
    updateSelectionInUrl(watcherId);

    if (options.scrollToCard) {
      scrollToElement(`watcher-card-${watcherId}`);
    }
    if (options.scrollToActivity) {
      scrollToElement('watcher-activity-panel');
    }
  }

  async function refreshData(options: { silent?: boolean } = {}) {
    const silent = options.silent ?? false;
    if (!silent) {
      error = null;
      pageRefreshing = true;
    }

    try {
      if (!silent) {
        // Stats carry the real per-state totals; the query is heavy, so only user-driven loads fetch it.
        void fetchWatcherStats().catch(() => {});
      }
      await Promise.all([
        fetchAllWatchers({ silent, limit: WATCHER_LIMIT }).then(() => {
          listFetchedComplete = get(watchers).length < WATCHER_LIMIT;
        }),
        fetchWatcherEvents(undefined, undefined, 300, { silent }),
      ]);
      refreshJobNamesInBackground();
    } catch (err) {
      console.error('Failed to refresh watcher data:', err);
      error = silent
        ? 'Watcher activity could not be refreshed in the background.'
        : 'Failed to refresh watcher data. Please try again.';
    } finally {
      if (!silent) {
        pageRefreshing = false;
      }
    }
  }

  function scheduleBackgroundRefresh(scope: BackgroundRefreshScope = 'events') {
    if (scope === 'all') {
      pendingBackgroundScope = 'all';
    }
    if (backgroundRefreshTimer) {
      return;
    }

    backgroundRefreshTimer = setTimeout(async () => {
      const nextScope = pendingBackgroundScope;
      pendingBackgroundScope = 'events';
      backgroundRefreshTimer = null;

      try {
        if (nextScope === 'all') {
          await refreshData({ silent: true });
        } else {
          await fetchWatcherEvents(undefined, undefined, 300, { silent: true });
        }
      } catch (err) {
        console.error('Failed to refresh watcher activity in background:', err);
      }
    }, 250);
  }

  async function openAttachDialog() {
    error = null;

    const cachedJobs = get(allCurrentJobs);
    const runningJobs = cachedJobs.filter(
      (job) => job.state === 'R' || job.state === 'PD',
    );

    if (runningJobs.length === 1) {
      selectedJobId = runningJobs[0].job_id;
      selectedHostname = runningJobs[0].hostname;
      showStreamlinedCreator = true;
      return;
    }

    showJobSelectionDialog = true;
  }

  async function applyWatcherToMultipleJobs(jobs: any[], config: any) {
    try {
      const promises = jobs.map((job) =>
        api
          .post('/api/watchers', {
            job_id: job.job_id,
            hostname: job.hostname,
            name: config.name,
            pattern: config.pattern,
            captures: config.captures || [],
            interval_seconds: config.interval || 60,
            condition: config.condition,
            actions: config.actions || [],
            timer_mode_enabled: config.timer_mode_enabled || false,
            timer_interval_seconds: config.timer_interval_seconds || 30,
            trigger_on_job_end: config.trigger_on_job_end || false,
            trigger_job_states: config.trigger_job_states || [],
          })
          .catch((requestError: any) => ({ error: requestError })),
      );

      const results = await Promise.all(promises);
      const failed = results.filter((result: any) => result?.error).length;

      if (failed > 0) {
        error = `Created ${results.length - failed} watcher(s), but ${failed} failed.`;
        setTimeout(() => {
          error = null;
        }, 5000);
      }

      copiedWatcherConfig = null;
      pendingMultiJobSelection = [];
      await refreshData();
    } catch (err) {
      console.error('Failed to create watchers:', err);
      error = 'Failed to create watchers for selected jobs.';
      setTimeout(() => {
        error = null;
      }, 5000);
      pendingMultiJobSelection = [];
    }
  }

  async function handleJobSelection(event: CustomEvent) {
    const selection = event.detail;
    showJobSelectionDialog = false;

    let jobs: any[];
    let action: 'apply' | 'edit' = 'apply';

    if (selection.jobs && selection.action) {
      jobs = selection.jobs;
      action = selection.action;
    } else if (Array.isArray(selection)) {
      jobs = selection;
    } else {
      jobs = [selection];
    }

    if (jobs.length === 1) {
      selectedJobId = jobs[0].job_id;
      selectedHostname = jobs[0].hostname;
      showStreamlinedCreator = true;
      return;
    }

    pendingMultiJobSelection = jobs;

    if (!copiedWatcherConfig) {
      error = 'Please configure a watcher on one job first, then copy it to multiple jobs.';
      setTimeout(() => {
        error = null;
      }, 5000);
      pendingMultiJobSelection = [];
      return;
    }

    if (action === 'edit') {
      selectedJobId = jobs[0].job_id;
      selectedHostname = jobs[0].hostname;
      showStreamlinedCreator = true;
      return;
    }

    await applyWatcherToMultipleJobs(jobs, copiedWatcherConfig);
  }

  async function handleWatcherCopy(event: CustomEvent) {
    copiedWatcherConfig = event.detail;

    const cachedJobs = get(allCurrentJobs);
    const runningJobs = cachedJobs.filter(
      (job) => job.state === 'R' || job.state === 'PD',
    );

    if (copiedWatcherConfig.job_id && copiedWatcherConfig.hostname) {
      const originalJob = runningJobs.find(
        (job) =>
          job.job_id === copiedWatcherConfig.job_id &&
          job.hostname === copiedWatcherConfig.hostname,
      );
      if (originalJob) {
        selectedJobId = originalJob.job_id;
        selectedHostname = originalJob.hostname;
      }
    }

    if (runningJobs.length === 0) {
      error = 'No running jobs available. Please start a job first.';
      setTimeout(() => {
        error = null;
      }, 5000);
      return;
    }

    showJobSelectionDialog = true;
  }

  async function handleAttachSuccess(event?: CustomEvent) {
    showStreamlinedCreator = false;

    if (pendingMultiJobSelection.length > 1 && copiedWatcherConfig) {
      const updatedConfig = event?.detail || copiedWatcherConfig;
      const remainingJobs = pendingMultiJobSelection.slice(1);

      if (remainingJobs.length > 0) {
        await applyWatcherToMultipleJobs(remainingJobs, updatedConfig);
      }
    }

    selectedJobId = null;
    selectedHostname = null;
    copiedWatcherConfig = null;
    pendingMultiJobSelection = [];
    await refreshData();
  }

  function handleWatcherInspect(
    event: CustomEvent<{ watcherId: number; scrollToActivity?: boolean }>,
  ) {
    // In the stacked layout the activity panel sits below the list, so bring it into view.
    inspectWatcher(event.detail.watcherId, {
      scrollToActivity: event.detail.scrollToActivity ?? narrowLayout,
    });
  }

  function handleWatcherRefresh(
    event?: CustomEvent<{ scope?: BackgroundRefreshScope }>,
  ) {
    scheduleBackgroundRefresh(event?.detail?.scope || 'events');
  }

  let eventSummaryByWatcher = $derived.by(() => {
    const summary: Record<number, { count: number; latest?: WatcherEvent }> = {};
    for (const event of watcherEventItems) {
      const existing = summary[event.watcher_id];
      if (!existing) {
        summary[event.watcher_id] = { count: 1, latest: event };
        continue;
      }

      existing.count += 1;
      if (
        !existing.latest ||
        new Date(event.timestamp).getTime() >
          new Date(existing.latest.timestamp).getTime()
      ) {
        existing.latest = event;
      }
    }

    return summary;
  });

  let enhancedWatchers = $derived.by(() => {
    return watcherItems.map((watcher) => {
      const job = jobItems.find(
        (candidate) =>
          candidate.job_id === watcher.job_id &&
          candidate.hostname === watcher.hostname,
      );

      return {
        ...watcher,
        job_name: job?.name || watcher.job_name || null,
      } as EnhancedWatcher;
    });
  });

  let filteredWatchers = $derived.by(() => {
    let nextWatchers = enhancedWatchers.filter((watcher) =>
      matchesFilter(watcher, filterState),
    );

    if (searchQuery.trim()) {
      const term = searchQuery.trim().toLowerCase();
      nextWatchers = nextWatchers.filter((watcher) =>
        getWatcherSearchText(
          watcher,
          eventSummaryByWatcher[watcher.id]?.latest,
        ).includes(term),
      );
    }

    return [...nextWatchers].sort((left, right) => {
      if (sortMode === 'name') {
        return left.name.localeCompare(right.name);
      }

      if (sortMode === 'recent') {
        return (
          new Date(right.created_at || 0).getTime() -
          new Date(left.created_at || 0).getTime()
        );
      }

      const leftActivity =
        eventSummaryByWatcher[left.id]?.latest?.timestamp ||
        left.last_check ||
        left.created_at ||
        '';
      const rightActivity =
        eventSummaryByWatcher[right.id]?.latest?.timestamp ||
        right.last_check ||
        right.created_at ||
        '';

      return (
        new Date(rightActivity || 0).getTime() -
        new Date(leftActivity || 0).getTime()
      );
    });
  });

  let selectedWatcher = $derived.by(() =>
    filteredWatchers.find((watcher) => watcher.id === selectedWatcherId) || null,
  );

  let selectedWatcherEvents = $derived.by(() =>
    selectedWatcher
      ? watcherEventItems
          .filter((event) => event.watcher_id === selectedWatcher.id)
          .slice(0, 60)
      : [],
  );

  let sameJobWatchers = $derived.by(() =>
    selectedWatcher
      ? filteredWatchers.filter(
          (watcher) =>
            watcher.id !== selectedWatcher.id &&
            watcher.job_id === selectedWatcher.job_id &&
            watcher.hostname === selectedWatcher.hostname,
        )
      : [],
  );

  // The list is capped, so loaded counts are lower bounds; stats (when loaded) give real totals.
  // The websocket's initial snapshot is capped too, so the list is only known to be complete
  // once a list fetch returned fewer rows than it asked for.
  let listCapped = $derived(!listFetchedComplete || watcherItems.length >= WATCHER_LIMIT);

  function loadedCount(state: FilterState): number {
    return watcherItems.filter((watcher) => matchesFilter(watcher, state)).length;
  }

  function totalCount(state: FilterState): number | null {
    const stats = $watcherStats;
    if (!stats) return listCapped ? null : loadedCount(state);
    const byState = (stats.watchers_by_state || {}) as Record<string, number>;
    if (state === 'all') return stats.total_watchers;
    if (state === 'live') return (byState.active || 0) + (byState.paused || 0);
    return byState[state] || 0;
  }

  function formatCount(state: FilterState): string {
    const total = totalCount(state);
    return total === null ? `${loadedCount(state).toLocaleString()}+` : total.toLocaleString();
  }

  let stateTabs = $derived.by(() =>
    (['live', 'active', 'paused', 'completed', 'static', 'all'] as FilterState[])
      .filter((state) => state !== 'static' || filterState === 'static' || (totalCount(state) ?? loadedCount(state)) > 0)
      .map((state) => ({ state, label: filterLabels[state], count: formatCount(state) })),
  );

  let headingSummary = $derived(
    `${formatCount('active')} active · ${formatCount('paused')} paused`,
  );

  // How many watchers of the current tab exist beyond the loaded, most-recent slice.
  let hiddenByCap = $derived.by(() => {
    const total = totalCount(filterState);
    const loaded = loadedCount(filterState);
    if (total === null) return listCapped ? -1 : 0;
    return Math.max(0, total - loaded);
  });
  let latestEvents = $derived.by(() => watcherEventItems.slice(0, 8));
  let hostSummaries = $derived.by(() => {
    const summaries: Record<string, HostSummary> = {};

    for (const watcher of watcherItems) {
      const host = watcher.hostname || 'unknown';
      summaries[host] ||= {
        host,
        total: 0,
        active: 0,
        paused: 0,
        recentEvents: 0,
      };
      summaries[host].total += 1;
      if (watcher.state === 'active') summaries[host].active += 1;
      if (watcher.state === 'paused') summaries[host].paused += 1;
      const latest = eventSummaryByWatcher[watcher.id]?.latest?.timestamp || watcher.last_check;
      if (
        latest &&
        (!summaries[host].latest ||
          new Date(latest).getTime() > new Date(summaries[host].latest || 0).getTime())
      ) {
        summaries[host].latest = latest;
      }
    }

    for (const event of watcherEventItems) {
      const host = event.hostname || 'unknown';
      summaries[host] ||= {
        host,
        total: 0,
        active: 0,
        paused: 0,
        recentEvents: 0,
      };
      summaries[host].recentEvents += 1;
      if (
        !summaries[host].latest ||
        new Date(event.timestamp).getTime() > new Date(summaries[host].latest || 0).getTime()
      ) {
        summaries[host].latest = event.timestamp;
      }
    }

    return Object.values(summaries)
      .sort(
        (left, right) =>
          right.active - left.active ||
          right.recentEvents - left.recentEvents ||
          right.total - left.total ||
          left.host.localeCompare(right.host),
      )
      .slice(0, 6);
  });

  // A deep-linked watcher outside the default tab (e.g. completed) switches to "All" once.
  $effect(() => {
    if (!urlSelectionPending || selectedWatcherId === null) return;
    const target = watcherItems.find((watcher) => watcher.id === selectedWatcherId);
    if (!target) return;
    urlSelectionPending = false;
    if (!matchesFilter(target, filterState)) {
      filterState = 'all';
    }
  });

  $effect(() => {
    if (urlSelectionPending && selectedWatcherId !== null && $watchersLoading) {
      return;
    }
    if (filteredWatchers.length === 0) {
      if ($watchersLoading || $eventsLoading) {
        return;
      }
      if (selectedWatcherId !== null) {
        selectedWatcherId = null;
        updateSelectionInUrl(null);
      }
      return;
    }

    if (
      selectedWatcherId !== null &&
      filteredWatchers.some((watcher) => watcher.id === selectedWatcherId)
    ) {
      return;
    }

    selectedWatcherId = filteredWatchers[0].id;
    updateSelectionInUrl(selectedWatcherId);
  });

  onMount(async () => {
    const unsubscribeWatchers = watchers.subscribe((value) => {
      watcherItems = value ?? [];
    });
    const unsubscribeEvents = watcherEvents.subscribe((value) => {
      watcherEventItems = value ?? [];
    });
    const unsubscribeJobs = allCurrentJobs.subscribe((value) => {
      jobItems = value ?? [];
    });

    unsubscribePageStores = [unsubscribeWatchers, unsubscribeEvents, unsubscribeJobs];

    navigationActions.setContext('watcher', {
      previousRoute: window.location.pathname,
    });

    const media = window.matchMedia?.('(max-width: 1100px)');
    const syncLayout = () => {
      narrowLayout = media?.matches ?? false;
    };
    syncLayout();
    media?.addEventListener?.('change', syncLayout);
    unsubscribePageStores.push(() => media?.removeEventListener?.('change', syncLayout));

    readSelectionFromUrl();
    connectWatcherWebSocket();
    await refreshData();
    urlSelectionPending = false;
  });

  onDestroy(() => {
    unsubscribePageStores.forEach((unsubscribe) => unsubscribe());
    unsubscribePageStores = [];
    if (backgroundRefreshTimer) {
      clearTimeout(backgroundRefreshTimer);
      backgroundRefreshTimer = null;
    }
    disconnectWatcherWebSocket();
  });
</script>

<div class="relay-page watchers-page">
  <div class="relay-heading">
    <div>
      <h1>Watchers</h1>
      <p>
        {headingSummary}
        <span
          class="watchers-live"
          class:online={$watcherSocketConnected}
          title={$watcherSocketConnected ? 'Receiving live watcher updates' : 'Live watcher updates are reconnecting'}
        >
          <span class="relay-dot" class:connected={$watcherSocketConnected}></span>
          {$watcherSocketConnected ? 'Live' : 'Reconnecting…'}
        </span>
      </p>
    </div>
    <div class="relay-heading-actions">
      <IconButton label="Refresh watchers" disabled={pageRefreshing} onclick={() => void refreshData()}>
        <RefreshCw size={17} class={pageRefreshing ? 'animate-spin' : ''} />
      </IconButton>
      <button type="button" class="relay-button primary" onclick={openAttachDialog}>
        <Plus size={17} />
        New watcher
      </button>
    </div>
  </div>

  {#if error}
    <div class="relay-banner error watchers-banner" role="alert">
      <TriangleAlert size={17} />
      <span>{error}</span>
      <button class="relay-text-button" onclick={() => void refreshData()}>Retry</button>
    </div>
  {/if}

  <div class="watchers-workspace">
    <section class="watchers-list" aria-label="Watchers">
      <div class="relay-tabs" role="group" aria-label="Filter by state">
        {#each stateTabs as tab (tab.state)}
          <button
            class:active={filterState === tab.state}
            aria-pressed={filterState === tab.state}
            onclick={() => {
              filterState = tab.state;
            }}
          >
            {tab.label}
            <span>{tab.count}</span>
          </button>
        {/each}
      </div>

      <div class="watchers-filters">
        <label class="relay-search">
          <Search size={16} />
          <input
            type="text"
            bind:value={searchQuery}
            placeholder="Search name, job, host, pattern…"
            aria-label="Search watchers"
          />
          {#if searchQuery}
            <IconButton label="Clear search" onclick={() => (searchQuery = '')}>
              <X size={14} />
            </IconButton>
          {/if}
        </label>
        <select class="relay-select" aria-label="Sort watchers" bind:value={sortMode}>
          <option value="activity">Last activity</option>
          <option value="recent">Newest</option>
          <option value="name">Name</option>
        </select>
      </div>

      {#if $watchersLoading && $watchers.length === 0}
        <div class="relay-empty-message">Loading watchers…</div>
      {:else if filteredWatchers.length === 0}
        <div class="relay-empty watchers-empty">
          {#if searchQuery}
            <p>No {filterLabels[filterState].toLowerCase()} watchers match “{searchQuery}”.</p>
          {:else if filterState === 'live' && watcherItems.length > 0}
            <p>No active or paused watchers. Completed watchers are under “Completed”.</p>
          {:else}
            <p>No watchers yet. Create one from a running job.</p>
          {/if}
        </div>
      {:else}
        <div class="watcher-table">
          <div class="watcher-rows" role="list">
            <div class="watcher-head" aria-hidden="true">
              <span></span>
              <span>Watcher</span>
              <span class="h-job">Job</span>
              <span class="h-trigger">Trigger</span>
              <span class="h-num h-count">Fired</span>
              <span class="h-num h-interval">Every</span>
              <span class="h-num">Last</span>
              <span></span>
            </div>
            {#each filteredWatchers as watcher (watcher.id)}
              <div role="listitem">
                <WatcherCard
                  {watcher}
                  lastEvent={eventSummaryByWatcher[watcher.id]?.latest}
                  selected={selectedWatcher?.id === watcher.id}
                  on:copy={handleWatcherCopy}
                  on:inspect={handleWatcherInspect}
                  on:refresh={handleWatcherRefresh}
                />
              </div>
            {/each}
          </div>
        </div>
      {/if}

      {#if hiddenByCap !== 0 && !searchQuery}
        <p class="watchers-cap-note">
          {#if hiddenByCap > 0}
            Showing the {filteredWatchers.length.toLocaleString()} loaded of {(filteredWatchers.length + hiddenByCap).toLocaleString()}
            {filterLabels[filterState].toLowerCase()} watchers — only the {WATCHER_LIMIT} most recent watchers are loaded.
          {:else}
            Only the {WATCHER_LIMIT} most recent watchers are loaded; older ones are not shown.
          {/if}
        </p>
      {/if}
    </section>

    <aside class="watchers-side" aria-label="Watcher activity">
      {#if selectedWatcher}
        <div id="watcher-activity-panel" class="side-panel activity-panel">
          <div class="activity-heading">
            <span class="activity-state" data-state={selectedWatcher.state}>{selectedWatcher.state}</span>
            <h2>{selectedWatcher.name}</h2>
            <p>
              Job <span class="mono">#{selectedWatcher.job_id}</span>{selectedWatcher.job_name ? ` · ${selectedWatcher.job_name}` : ''} on {selectedWatcher.hostname}
            </p>
          </div>

          <dl class="activity-facts">
            <div>
              <dt>Recent events</dt>
              <dd>{eventSummaryByWatcher[selectedWatcher.id]?.count || 0}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{formatRelativeTime(selectedWatcher.created_at)}</dd>
            </div>
            <div>
              <dt>Mode</dt>
              <dd>
                {selectedWatcher.trigger_on_job_end && !selectedWatcher.pattern
                  ? 'Job end'
                  : selectedWatcher.timer_mode_enabled
                    ? 'Pattern + timer'
                    : 'Pattern'}
              </dd>
            </div>
          </dl>

          {#if sameJobWatchers.length > 0}
            <div class="peer-list">
              <span class="peer-label">Same job</span>
              {#each sameJobWatchers as peer (peer.id)}
                <button
                  class="peer-chip"
                  onclick={() =>
                    inspectWatcher(peer.id, {
                      scrollToCard: true,
                    })}
                >
                  {peer.name}
                </button>
              {/each}
            </div>
          {/if}

          <WatcherActivityFeed
            watcher={selectedWatcher}
            events={selectedWatcherEvents}
            loading={$eventsLoading && $watcherEvents.length === 0}
          />
        </div>
      {/if}

      {#if latestEvents.length > 0}
        <div class="side-panel">
          <div class="side-heading">
            <Radio size={15} />
            <span>Latest events</span>
          </div>
          <div class="event-stream">
            {#each latestEvents as event (event.id)}
              <button
                class:failed={!event.success}
                class="event-stream-item"
                onclick={() =>
                  inspectWatcher(event.watcher_id, {
                    scrollToCard: true,
                  })}
              >
                <span class="event-dot"></span>
                <span class="event-body">
                  <strong>{event.watcher_name || `Watcher #${event.watcher_id}`}</strong>
                  <small>{truncateInline(event.matched_text || event.action_result, event.action_type)}</small>
                </span>
                <time>{formatRelativeTime(event.timestamp)}</time>
              </button>
            {/each}
          </div>
        </div>
      {/if}

      {#if hostSummaries.length > 0}
        <div class="side-panel">
          <div class="side-heading">
            <Layers size={15} />
            <span>Hosts</span>
          </div>
          <div class="host-lanes">
            {#each hostSummaries as host (host.host)}
              <button
                class="host-lane"
                title={`Search watchers on ${host.host}`}
                onclick={() => {
                  searchQuery = host.host;
                }}
              >
                <Server size={14} />
                <strong>{host.host}</strong>
                <span>{host.active} active · {host.paused} paused</span>
                <time>{formatRelativeTime(host.latest)}</time>
              </button>
            {/each}
          </div>
        </div>
      {/if}
    </aside>
  </div>
</div>

{#if showJobSelectionDialog}
  <JobSelectionDialog
    title={copiedWatcherConfig ? 'Select Job(s) for Copied Watcher' : 'Select Job(s)'}
    description={copiedWatcherConfig
      ? 'Choose which job(s) to attach the copied watcher to.'
      : 'Choose job(s) to attach watchers to.'}
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
      pendingMultiJobSelection = [];
    }}
  />
{/if}

<style>
  .watchers-page {
    display: flex;
    flex-direction: column;
  }

  .watchers-live {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-left: 10px;
    white-space: nowrap;
  }

  .watchers-live.online .relay-dot {
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--success) 20%, transparent);
  }

  .watchers-banner {
    margin-bottom: 16px;
    border-radius: 10px;
  }

  .watchers-workspace {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
    gap: 24px;
    align-items: start;
  }

  .watchers-list {
    min-width: 0;
  }

  .watchers-filters {
    display: flex;
    gap: 8px;
    padding: 12px 0;
    align-items: center;
  }

  .watchers-filters .relay-search {
    flex: 1;
  }

  .watchers-filters > .relay-select {
    max-width: 160px;
  }

  .watchers-empty {
    min-height: 200px;
  }

  .watcher-table {
    container: watcher-list / inline-size;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }

  /* Column tracks shared by the header and every WatcherCard row. */
  .watcher-rows {
    --watcher-cols: 10px minmax(0, 2fr) minmax(0, 1.1fr) minmax(0, 1.3fr) 44px 44px 64px 30px;
  }

  .watcher-head {
    display: grid;
    grid-template-columns: var(--watcher-cols);
    gap: 12px;
    padding: 8px 6px 8px 14px;
    border-bottom: 1px solid var(--border);
    background: var(--secondary);
    color: var(--muted-foreground);
    font-size: 0.6875rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .watcher-head .h-num {
    text-align: right;
  }

  .watchers-cap-note {
    margin: 10px 2px 0;
    color: var(--muted-foreground);
    font-size: 0.75rem;
  }

  @container watcher-list (max-width: 720px) {
    .watcher-rows {
      --watcher-cols: 10px minmax(0, 1.6fr) minmax(0, 1fr) 44px 64px 30px;
    }
    .h-job,
    .h-interval {
      display: none;
    }
  }

  @container watcher-list (max-width: 520px) {
    .watcher-rows {
      --watcher-cols: 10px minmax(0, 1fr) 64px 30px;
    }
    .watcher-head {
      display: none;
    }
  }

  .watchers-side {
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-width: 0;
    position: sticky;
    top: 0;
  }

  .side-panel {
    min-width: 0;
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius-card);
    background: var(--card);
    overflow-wrap: anywhere;
  }

  .activity-panel {
    display: grid;
    gap: 14px;
  }

  .activity-heading h2 {
    margin: 6px 0 4px;
    color: var(--foreground);
    font-size: 1rem;
    font-weight: 600;
    line-height: 1.3;
  }

  .activity-heading p {
    margin: 0;
    color: var(--muted-foreground);
    font-size: 0.8125rem;
  }

  .activity-state {
    display: inline-flex;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--secondary);
    color: var(--muted-foreground);
    font-size: 0.6875rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .activity-state[data-state='active'] {
    background: var(--success-bg);
    color: var(--success);
  }

  .activity-state[data-state='paused'] {
    background: var(--warning-bg);
    color: var(--warning);
  }

  .activity-facts {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
    margin: 0;
  }

  .activity-facts div {
    min-width: 0;
    padding: 8px 10px;
    border-radius: 8px;
    background: var(--secondary);
  }

  .activity-facts dt {
    color: var(--muted-foreground);
    font-size: 0.6875rem;
  }

  .activity-facts dd {
    margin: 2px 0 0;
    color: var(--foreground);
    font-size: 0.8125rem;
    font-weight: 550;
  }

  .peer-list {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }

  .peer-label {
    color: var(--muted-foreground);
    font-size: 0.75rem;
  }

  .peer-chip {
    max-width: 100%;
    padding: 3px 9px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--card);
    color: var(--foreground);
    font-size: 0.75rem;
    text-align: left;
  }

  .peer-chip:hover {
    background: var(--hover);
  }

  /* Keep long paths, commands and captured values inside the panel. */
  .activity-panel :global(.activity-header) {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .activity-panel :global(.activity-search) {
    min-width: 0;
    border-radius: 10px;
    background: var(--card);
  }

  .activity-panel :global(.activity-item) {
    grid-template-columns: 1.5rem minmax(0, 1fr);
    gap: 10px;
    padding: 12px;
    border-radius: 10px;
  }

  .activity-panel :global(.activity-row) {
    flex-wrap: wrap;
    gap: 4px 10px;
  }

  .activity-panel :global(.activity-snippet),
  .activity-panel :global(.activity-result),
  .activity-panel :global(.activity-var),
  .activity-panel :global(.activity-meta span) {
    max-width: 100%;
    overflow-wrap: anywhere;
    word-break: normal;
  }

  .activity-panel :global(.activity-snippet) {
    max-height: 240px;
    overflow: auto;
  }

  .side-heading {
    display: flex;
    align-items: center;
    gap: 7px;
    margin-bottom: 10px;
    color: var(--foreground);
    font-size: 0.8125rem;
    font-weight: 600;
  }

  .event-stream,
  .host-lanes {
    display: grid;
  }

  .event-stream-item,
  .host-lane {
    display: grid;
    align-items: center;
    gap: 8px;
    width: 100%;
    min-width: 0;
    padding: 8px 4px;
    border: 0;
    border-bottom: 1px solid var(--border-soft);
    background: none;
    color: inherit;
    text-align: left;
  }

  .event-stream-item:last-child,
  .host-lane:last-child {
    border-bottom: 0;
  }

  .event-stream-item:hover,
  .host-lane:hover {
    background: var(--hover);
  }

  .event-stream-item {
    grid-template-columns: 8px minmax(0, 1fr) auto;
  }

  .event-body {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .event-body strong,
  .event-body small,
  .host-lane strong,
  .host-lane span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .event-body strong {
    color: var(--foreground);
    font-size: 0.8125rem;
    font-weight: 550;
  }

  .event-body small,
  .event-stream-item time,
  .host-lane span,
  .host-lane time {
    color: var(--muted-foreground);
    font-size: 0.75rem;
  }

  .event-stream-item time,
  .host-lane time {
    white-space: nowrap;
  }

  .event-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--success);
  }

  .event-stream-item.failed .event-dot {
    background: var(--error);
  }

  .host-lane {
    grid-template-columns: 14px minmax(0, 1fr) auto auto;
    color: var(--muted-foreground);
  }

  .host-lane strong {
    color: var(--foreground);
    font-size: 0.8125rem;
    font-weight: 550;
  }

  @media (max-width: 1100px) {
    .watchers-workspace {
      grid-template-columns: minmax(0, 1fr);
    }
    .watchers-side {
      position: static;
    }
  }

  @media (max-width: 760px) {
    .relay-heading {
      flex-wrap: wrap;
    }
    .watchers-filters {
      flex-wrap: wrap;
    }
    .watchers-filters .relay-search {
      flex-basis: 100%;
    }
    .watchers-filters > .relay-select {
      max-width: none;
      flex: 1;
    }
    .host-lane {
      grid-template-columns: 14px minmax(0, 1fr) auto;
    }
    .host-lane time {
      display: none;
    }
  }
</style>
