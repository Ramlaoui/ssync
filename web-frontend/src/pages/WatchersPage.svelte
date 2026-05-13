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
    watcherEvents,
    watchers,
    watchersLoading,
    watcherSocketConnected,
  } from '../stores/watchers';
  import { jobStateManager } from '../lib/JobStateManager';
  import { api } from '../services/api';
  import type { Watcher, WatcherEvent } from '../types/watchers';
  import WatcherCard from '../components/WatcherCard.svelte';
  import WatcherActivityFeed from '../components/WatcherActivityFeed.svelte';
  import WatcherCreator from '../components/WatcherCreator.svelte';
  import JobSelectionDialog from '../components/JobSelectionDialog.svelte';
  import NavigationHeader from '../components/NavigationHeader.svelte';
  import {
    BarChart3,
    Clock3,
    Eye,
    Filter,
    Layers,
    Plus,
    Radio,
    Search,
    Server,
    Zap,
  } from 'lucide-svelte';

  const allCurrentJobs = jobStateManager.getAllJobs();

  type FilterState = 'all' | 'active' | 'paused' | 'static' | 'completed';
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
  let filterState: FilterState = $state('all');
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

  function getStateLabel(state: FilterState): string {
    if (state === 'all') return 'All';
    return state.charAt(0).toUpperCase() + state.slice(1);
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
      await Promise.all([
        fetchAllWatchers({ silent, limit: 300 }),
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
    inspectWatcher(event.detail.watcherId, {
      scrollToActivity: event.detail.scrollToActivity,
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
    let nextWatchers = enhancedWatchers.filter((watcher) => {
      if (filterState === 'all') return true;
      return watcher.state === filterState;
    });

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

  let watcherCounts = $derived.by(() => {
    return {
      total: watcherItems.length,
      active: watcherItems.filter((watcher) => watcher.state === 'active').length,
      paused: watcherItems.filter((watcher) => watcher.state === 'paused').length,
      static: watcherItems.filter((watcher) => watcher.state === 'static').length,
      completed: watcherItems.filter((watcher) => watcher.state === 'completed').length,
    };
  });

  let hostCount = $derived.by(() => {
    return new Set(watcherItems.map((watcher) => watcher.hostname)).size;
  });
  let recentEventCount = $derived.by(() => watcherEventItems.length);
  let stateFilterChips = $derived.by(() =>
    (['all', 'active', 'paused', 'static', 'completed'] as FilterState[]).map((state) => ({
      state,
      label: getStateLabel(state),
      count: state === 'all' ? watcherCounts.total : watcherCounts[state],
    })),
  );
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

  $effect(() => {
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

    readSelectionFromUrl();
    connectWatcherWebSocket();
    await refreshData();
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

<div class="watchers-page">
  <NavigationHeader
    showRefresh={true}
    refreshing={pageRefreshing}
    on:refresh={() => refreshData()}
  >
    {#snippet left()}
      <div class="page-copy">
        <div class="page-title-row">
          <Eye class="w-4 h-4" />
          <span>Watchers</span>
        </div>
        <p>Monitor watcher state and related events in one unified workspace.</p>
      </div>
    {/snippet}

    {#snippet actions()}
      <button class="create-button" onclick={openAttachDialog}>
        <Plus class="w-4 h-4" />
        Create
      </button>
    {/snippet}

    {#snippet additional()}
      <div class="toolbar">
        <label class="toolbar-search">
          <Search class="w-4 h-4" />
          <input
            type="text"
            bind:value={searchQuery}
            placeholder="Search watchers, actions, jobs, or event text"
          />
        </label>

        <div class="toolbar-controls">
          <label class="toolbar-select">
            <Filter class="w-4 h-4" />
            <select bind:value={filterState}>
              <option value="all">All states</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="static">Static</option>
              <option value="completed">Completed</option>
            </select>
          </label>

          <label class="toolbar-select">
            <Clock3 class="w-4 h-4" />
            <select bind:value={sortMode}>
              <option value="activity">Sort by activity</option>
              <option value="recent">Sort by created</option>
              <option value="name">Sort by name</option>
            </select>
          </label>

          <div class:connected={$watcherSocketConnected} class="live-indicator">
            <span class="live-dot"></span>
            {$watcherSocketConnected ? 'Live updates' : 'Reconnecting'}
          </div>
        </div>
      </div>

      <div class="state-chips" aria-label="Watcher state filters">
        {#each stateFilterChips as chip}
          <button
            class:active={filterState === chip.state}
            class="state-chip"
            data-state={chip.state}
            onclick={() => {
              filterState = chip.state;
            }}
          >
            <span class="state-chip-dot"></span>
            <span>{chip.label}</span>
            <strong>{chip.count}</strong>
          </button>
        {/each}
      </div>
    {/snippet}
  </NavigationHeader>

  {#if error}
    <div class="error-banner">{error}</div>
  {/if}

  <main class="workspace">
    <section class="primary-column">
      <div class="summary-grid">
        <article class="summary-card">
          <span class="summary-label">Active</span>
          <strong>{watcherCounts.active}</strong>
          <small>{watcherCounts.total} total watchers</small>
        </article>
        <article class="summary-card">
          <span class="summary-label">Events</span>
          <strong>{recentEventCount}</strong>
          <small>recent watcher events</small>
        </article>
        <article class="summary-card">
          <span class="summary-label">Hosts</span>
          <strong>{hostCount}</strong>
          <small>clusters with watchers</small>
        </article>
        <article class="summary-card">
          <span class="summary-label">Static</span>
          <strong>{watcherCounts.static}</strong>
          <small>manual-only watchers</small>
        </article>
      </div>

      <div class="list-header">
        <div>
          <h2>{filteredWatchers.length} watcher{filteredWatchers.length === 1 ? '' : 's'}</h2>
          <p>Run watcher actions in place without leaving the board.</p>
        </div>
      </div>

      {#if $watchersLoading && $watchers.length === 0}
        <div class="panel-empty">Loading watchers…</div>
      {:else if filteredWatchers.length === 0}
        <div class="panel-empty">
          {#if searchQuery}
            No watchers match this search.
          {:else}
            No watchers yet. Create one from a running job.
          {/if}
        </div>
      {:else}
        <div class="watcher-grid">
          {#each filteredWatchers as watcher (watcher.id)}
            {@const latestEvent = eventSummaryByWatcher[watcher.id]?.latest}
            <article
              id={"watcher-card-" + watcher.id}
              class:selected={selectedWatcher?.id === watcher.id}
              class="watcher-shell"
            >
              <div class="watcher-shell-header">
                <div class="watcher-shell-copy">
                  <div class="watcher-shell-title">
                    <span class="item-state" data-state={watcher.state}></span>
                    <strong>{watcher.name}</strong>
                  </div>
                  <div class="watcher-shell-subtitle">
                    <span>
                      Job #{watcher.job_id}
                      {#if watcher.job_name}
                        • {watcher.job_name}
                      {/if}
                    </span>
                    <span>{watcher.hostname}</span>
                  </div>
                </div>
                <button
                  class="inspect-chip"
                  onclick={() => inspectWatcher(watcher.id, { scrollToActivity: true })}
                >
                  {eventSummaryByWatcher[watcher.id]?.count || 0} event{eventSummaryByWatcher[watcher.id]?.count === 1 ? '' : 's'}
                </button>
              </div>

              <div class="watcher-shell-meta">
                <span>{watcher.actions?.length || 0} action{watcher.actions?.length === 1 ? '' : 's'}</span>
                <span>{watcher.interval_seconds}s interval</span>
                <span>{formatRelativeTime(latestEvent?.timestamp || watcher.last_check)}</span>
              </div>

              <WatcherCard
                watcher={watcher}
                showJobLink={true}
                lastEvent={latestEvent}
                class={selectedWatcher?.id === watcher.id ? 'watcher-card-selected' : ''}
                on:copy={handleWatcherCopy}
                on:inspect={handleWatcherInspect}
                on:refresh={handleWatcherRefresh}
              />
            </article>
          {/each}
        </div>
      {/if}

      {#if selectedWatcher}
        <div id="watcher-activity-panel" class="activity-card selected-activity-card">
          <div class="detail-header">
            <div>
              <div class="page-title-row">
                <Zap class="w-4 h-4" />
                <span>Watcher Activity</span>
              </div>
              <p>
                {selectedWatcher.name} • Job #{selectedWatcher.job_id} on {selectedWatcher.hostname}
              </p>
            </div>
          </div>

          <div class="detail-pills">
            <span class="detail-pill">{selectedWatcher.state}</span>
            <span class="detail-pill">
              {eventSummaryByWatcher[selectedWatcher.id]?.count || 0} recent event(s)
            </span>
            <span class="detail-pill">
              created {formatRelativeTime(selectedWatcher.created_at)}
            </span>
            <span class="detail-pill">
              {selectedWatcher.trigger_on_job_end
                ? 'Terminal-state trigger'
                : selectedWatcher.timer_mode_enabled
                  ? 'Pattern + timer'
                  : 'Pattern monitor'}
            </span>
          </div>

          {#if sameJobWatchers.length > 0}
            <div class="peer-list">
              {#each sameJobWatchers as peer (peer.id)}
                <button
                  class="peer-chip"
                  onclick={() =>
                    inspectWatcher(peer.id, {
                      scrollToCard: true,
                      scrollToActivity: true,
                    })}
                >
                  <Server class="w-3.5 h-3.5" />
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
    </section>

    <aside class="activity-column" aria-label="Watcher activity overview">
      {#if $watchers.length > 0 || latestEvents.length > 0}
        <div class="board-panel host-panel">
          <div class="board-heading">
            <Layers class="w-4 h-4" />
            <span>Hosts</span>
          </div>

          {#if hostSummaries.length === 0}
            <p class="board-empty">No host activity yet.</p>
          {:else}
            <div class="host-lanes">
              {#each hostSummaries as host (host.host)}
                <button
                  class="host-lane"
                  onclick={() => {
                    searchQuery = host.host;
                  }}
                >
                  <div class="host-lane-title">
                    <Server class="w-3.5 h-3.5" />
                    <strong>{host.host}</strong>
                    <span>{host.total} watcher{host.total === 1 ? '' : 's'}</span>
                  </div>
                  <div class="host-lane-meter">
                    <span
                      class="host-lane-fill"
                      style={`width: ${host.total ? Math.max(8, Math.round((host.active / host.total) * 100)) : 0}%`}
                    ></span>
                  </div>
                  <div class="host-lane-meta">
                    <span>{host.active} active</span>
                    <span>{host.recentEvents} events</span>
                    <span>{formatRelativeTime(host.latest)}</span>
                  </div>
                </button>
              {/each}
            </div>
          {/if}
        </div>

        <div class="board-panel stream-panel">
          <div class="board-heading">
            <Radio class="w-4 h-4" />
            <span>Live stream</span>
            <span class:connected={$watcherSocketConnected} class="stream-status">
              {$watcherSocketConnected ? 'connected' : 'waiting'}
            </span>
          </div>

          {#if latestEvents.length === 0}
            <p class="board-empty">Events will appear here as watchers fire.</p>
          {:else}
            <div class="event-stream">
              {#each latestEvents as event (event.id)}
                <button
                  class:failed={!event.success}
                  class="event-stream-item"
                  onclick={() =>
                    inspectWatcher(event.watcher_id, {
                      scrollToCard: true,
                      scrollToActivity: true,
                    })}
                >
                  <span class="event-dot"></span>
                  <div>
                    <strong>{event.watcher_name || `Watcher #${event.watcher_id}`}</strong>
                    <p>{truncateInline(event.matched_text || event.action_result, event.action_type)}</p>
                  </div>
                  <time>{formatRelativeTime(event.timestamp)}</time>
                </button>
              {/each}
            </div>
          {/if}
        </div>

        <div class="board-panel pulse-panel">
          <div class="board-heading">
            <BarChart3 class="w-4 h-4" />
            <span>State mix</span>
          </div>
          <div class="state-bars">
            {#each stateFilterChips.filter((chip) => chip.state !== 'all') as chip}
              <button
                class="state-bar-row"
                data-state={chip.state}
                onclick={() => {
                  filterState = chip.state;
                }}
              >
                <span>{chip.label}</span>
                <div class="state-bar-track">
                  <span
                    class="state-bar-fill"
                    style={`width: ${watcherCounts.total ? Math.round((chip.count / watcherCounts.total) * 100) : 0}%`}
                  ></span>
                </div>
                <strong>{chip.count}</strong>
              </button>
            {/each}
          </div>
        </div>
      {/if}
    </aside>
  </main>
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
    height: 100%;
    min-height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--background);
    overflow: hidden;
  }

  .page-copy {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  .page-title-row {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    font-weight: 600;
    color: var(--foreground);
  }

  .page-copy p,
  .detail-header p {
    margin: 0;
    color: var(--muted-foreground);
    font-size: 0.84rem;
  }

  .create-button {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    border: none;
    border-radius: 0.75rem;
    padding: 0.72rem 1rem;
    background: var(--foreground);
    color: var(--background);
    font-weight: 600;
    cursor: pointer;
  }

  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0 0 1rem;
  }

  .state-chips {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    overflow-x: auto;
    padding-bottom: 0.25rem;
  }

  .state-chip {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0.42rem 0.65rem;
    background: var(--background);
    color: var(--muted-foreground);
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    transition: border-color 0.16s ease, color 0.16s ease, background 0.16s ease;
  }

  .state-chip:hover,
  .state-chip.active {
    border-color: color-mix(in srgb, var(--accent) 42%, var(--border));
    background: color-mix(in srgb, var(--accent) 8%, var(--background));
    color: var(--foreground);
  }

  .state-chip strong {
    color: var(--foreground);
    font-size: 0.76rem;
  }

  .state-chip-dot {
    width: 0.48rem;
    height: 0.48rem;
    border-radius: 999px;
    background: var(--muted-foreground);
  }

  .state-chip[data-state='active'] .state-chip-dot {
    background: var(--success);
  }

  .state-chip[data-state='paused'] .state-chip-dot {
    background: var(--warning);
  }

  .state-chip[data-state='static'] .state-chip-dot,
  .state-chip[data-state='completed'] .state-chip-dot {
    background: var(--accent);
  }

  .toolbar-search {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 0.65rem;
    min-width: 0;
    padding: 0.8rem 0.95rem;
    border: 1px solid var(--border);
    border-radius: 0.9rem;
    background: var(--background);
    color: var(--muted-foreground);
  }

  .toolbar-search input,
  .toolbar-select select {
    width: 100%;
    border: none;
    background: transparent;
    color: var(--foreground);
    font-size: 0.88rem;
  }

  .toolbar-search input:focus,
  .toolbar-select select:focus {
    outline: none;
  }

  .toolbar-controls {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .toolbar-select {
    display: inline-flex;
    align-items: center;
    gap: 0.55rem;
    min-width: 180px;
    padding: 0.75rem 0.9rem;
    border: 1px solid var(--border);
    border-radius: 0.9rem;
    background: var(--background);
    color: var(--muted-foreground);
  }

  .live-indicator {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.7rem 0.85rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--secondary) 85%, transparent);
    color: var(--muted-foreground);
    font-size: 0.82rem;
    font-weight: 600;
  }

  .live-indicator.connected {
    color: var(--foreground);
  }

  .live-dot {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 999px;
    background: var(--warning);
  }

  .live-indicator.connected .live-dot {
    background: var(--success);
    box-shadow: 0 0 0 0.24rem color-mix(in srgb, var(--success) 20%, transparent);
  }

  .error-banner {
    margin: 0 1.5rem;
    padding: 0.85rem 1rem;
    border-radius: 0.9rem;
    background: color-mix(in srgb, var(--destructive) 12%, transparent);
    color: var(--destructive);
    font-size: 0.9rem;
  }

  .workspace {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(260px, 320px);
    gap: 1rem;
    align-items: start;
    padding: 1.25rem 1.5rem 1.5rem;
    overflow: auto;
  }

  .primary-column,
  .activity-column {
    min-height: 0;
  }

  .primary-column {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.8rem;
  }

  .summary-card,
  .board-panel,
  .activity-card,
  .watcher-shell {
    min-width: 0;
    border: 1px solid var(--border);
    border-radius: 1.1rem;
    background: var(--card);
  }

  .summary-card {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0.9rem;
  }

  .summary-label {
    color: var(--muted-foreground);
    font-size: 0.76rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .summary-card strong {
    font-size: 1.15rem;
    color: var(--foreground);
  }

  .summary-card small {
    color: var(--muted-foreground);
    font-size: 0.76rem;
  }

  .list-header h2 {
    margin: 0;
    color: var(--foreground);
    font-size: 1.1rem;
  }

  .list-header p {
    margin: 0.3rem 0 0;
    color: var(--muted-foreground);
    font-size: 0.84rem;
  }

  .panel-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 220px;
    border: 1px dashed var(--border);
    border-radius: 1.2rem;
    background: var(--card);
    color: var(--muted-foreground);
    text-align: center;
    padding: 1.2rem;
  }

  .watcher-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 1rem;
  }

  .watcher-shell {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    padding: 1rem;
    transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
  }

  .watcher-shell:hover,
  .watcher-shell.selected {
    border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
    box-shadow: 0 12px 28px color-mix(in srgb, var(--foreground) 8%, transparent);
    transform: translateY(-1px);
  }

  .watcher-shell-header,
  .watcher-shell-title,
  .watcher-shell-subtitle,
  .watcher-shell-meta {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    min-width: 0;
  }

  .watcher-shell-header,
  .watcher-shell-meta {
    justify-content: space-between;
  }

  .watcher-shell-copy {
    min-width: 0;
    display: grid;
    gap: 0.25rem;
  }

  .watcher-shell-title strong {
    color: var(--foreground);
    font-size: 0.95rem;
    line-height: 1.3;
  }

  .watcher-shell-subtitle,
  .watcher-shell-meta {
    color: var(--muted-foreground);
    font-size: 0.78rem;
    flex-wrap: wrap;
  }

  .item-state {
    width: 0.7rem;
    height: 0.7rem;
    border-radius: 999px;
    flex-shrink: 0;
    background: var(--muted-foreground);
  }

  .item-state[data-state='active'] {
    background: var(--success);
  }

  .item-state[data-state='paused'] {
    background: var(--warning);
  }

  .item-state[data-state='static'],
  .item-state[data-state='completed'] {
    background: var(--accent);
  }

  .inspect-chip,
  .detail-pill,
  .peer-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    min-width: max-content;
    padding: 0.35rem 0.65rem;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: color-mix(in srgb, var(--secondary) 92%, transparent);
    color: var(--foreground);
    font-size: 0.76rem;
    font-weight: 600;
  }

  .activity-card {
    padding: 1rem;
  }

  .selected-activity-card {
    display: grid;
    gap: 1rem;
  }

  .detail-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }

  .detail-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.55rem;
  }

  .peer-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.55rem;
  }

  .activity-column {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    position: sticky;
    top: 0;
  }

  .board-panel {
    padding: 0.9rem;
  }

  .board-heading {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    margin-bottom: 0.75rem;
    color: var(--foreground);
    font-size: 0.86rem;
    font-weight: 700;
  }

  .stream-status {
    margin-left: auto;
    color: var(--muted-foreground);
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .stream-status.connected {
    color: var(--success);
  }

  .board-empty {
    margin: 0;
    color: var(--muted-foreground);
    font-size: 0.82rem;
  }

  .host-lanes,
  .event-stream,
  .state-bars {
    display: grid;
    gap: 0.55rem;
  }

  .host-lane,
  .event-stream-item,
  .state-bar-row {
    width: 100%;
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    background: var(--background);
    color: inherit;
    text-align: left;
    cursor: pointer;
  }

  .host-lane {
    display: grid;
    gap: 0.45rem;
    padding: 0.7rem;
  }

  .host-lane-title,
  .host-lane-meta {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    min-width: 0;
  }

  .host-lane-title strong {
    color: var(--foreground);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .host-lane-title span,
  .host-lane-meta {
    color: var(--muted-foreground);
    font-size: 0.74rem;
  }

  .host-lane-meta {
    justify-content: space-between;
    flex-wrap: wrap;
  }

  .host-lane-meter,
  .state-bar-track {
    width: 100%;
    height: 0.55rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--secondary) 88%, transparent);
    overflow: hidden;
  }

  .host-lane-fill,
  .state-bar-fill {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(
      90deg,
      color-mix(in srgb, var(--accent) 65%, white),
      var(--accent)
    );
  }

  .event-stream-item {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 0.6rem;
    align-items: start;
    padding: 0.75rem;
  }

  .event-stream-item strong {
    color: var(--foreground);
    font-size: 0.8rem;
  }

  .event-stream-item p,
  .event-stream-item time {
    margin: 0.2rem 0 0;
    color: var(--muted-foreground);
    font-size: 0.74rem;
    line-height: 1.4;
  }

  .event-stream-item.failed {
    border-color: color-mix(in srgb, var(--destructive) 30%, var(--border));
  }

  .event-dot {
    width: 0.55rem;
    height: 0.55rem;
    margin-top: 0.35rem;
    border-radius: 999px;
    background: var(--success);
  }

  .event-stream-item.failed .event-dot {
    background: var(--destructive);
  }

  .state-bar-row {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 0.75rem;
    padding: 0.72rem 0.8rem;
  }

  .state-bar-row span,
  .state-bar-row strong {
    font-size: 0.78rem;
  }

  .state-bar-row[data-state='active'] .state-bar-fill {
    background: var(--success);
  }

  .state-bar-row[data-state='paused'] .state-bar-fill {
    background: var(--warning);
  }

  .state-bar-row[data-state='static'] .state-bar-fill,
  .state-bar-row[data-state='completed'] .state-bar-fill {
    background: var(--accent);
  }

  :global(.watcher-card-selected) {
    border-color: color-mix(in srgb, var(--accent) 36%, var(--border));
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 18%, transparent);
  }

  @media (max-width: 1400px) {
    .workspace {
      grid-template-columns: 1fr;
    }

    .activity-column {
      position: static;
    }
  }

  @media (max-width: 900px) {
    .summary-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 720px) {
    .toolbar {
      flex-direction: column;
      align-items: stretch;
    }

    .toolbar-controls {
      width: 100%;
    }

    .toolbar-select {
      min-width: 0;
      flex: 1;
    }

    .workspace {
      grid-template-columns: 1fr;
      padding: 1rem;
    }

    .watcher-grid {
      grid-template-columns: 1fr;
    }

    .summary-grid {
      grid-template-columns: 1fr 1fr;
    }
  }
</style>
