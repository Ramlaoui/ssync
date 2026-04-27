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
    routeParams.delete('tab');

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

  async function refreshData() {
    error = null;
    try {
      await Promise.all([
        fetchAllWatchers(),
        fetchWatcherEvents(undefined, undefined, 300),
      ]);
      refreshJobNamesInBackground();
    } catch (err) {
      console.error('Failed to refresh watcher data:', err);
      error = 'Failed to refresh watcher data. Please try again.';
    }
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

  function selectWatcher(watcherId: number) {
    selectedWatcherId = watcherId;
    updateSelectionInUrl(watcherId);
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
    disconnectWatcherWebSocket();
  });
</script>

<div class="watchers-page">
  <NavigationHeader
    showRefresh={true}
    refreshing={$watchersLoading || $eventsLoading}
    on:refresh={refreshData}
  >
    {#snippet left()}
      <div class="page-copy">
        <div class="page-title-row">
          <Eye class="w-4 h-4" />
          <span>Watchers</span>
        </div>
        <p>Monitor watcher state and related events in the same workspace.</p>
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
    <aside class="list-panel">
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
          <p>Searchable list ordered by recent activity.</p>
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
        <div class="watcher-list">
          {#each filteredWatchers as watcher (watcher.id)}
            {@const latestEvent = eventSummaryByWatcher[watcher.id]?.latest}
            <button
              class:selected={selectedWatcher?.id === watcher.id}
              class="watcher-list-item"
              onclick={() => selectWatcher(watcher.id)}
            >
              <div class="item-row">
                <div class="item-title-group">
                  <div class="item-state" data-state={watcher.state}></div>
                  <div>
                    <div class="item-title">{watcher.name}</div>
                    <div class="item-subtitle">
                      Job #{watcher.job_id}
                      {#if watcher.job_name}
                        <span>• {watcher.job_name}</span>
                      {/if}
                    </div>
                  </div>
                </div>

                <span class="item-count">
                  {eventSummaryByWatcher[watcher.id]?.count || 0}
                </span>
              </div>

              <div class="item-body">
                <span>{watcher.hostname}</span>
                <span>
                  {watcher.trigger_on_job_end
                    ? `job end: ${(watcher.trigger_job_states || []).join(', ')}`
                    : watcher.pattern || 'manual trigger'}
                </span>
              </div>

              <div class="item-footer">
                <span>{watcher.actions?.length || 0} action{watcher.actions?.length === 1 ? '' : 's'}</span>
                <span>{watcher.interval_seconds}s interval</span>
                <span>{formatRelativeTime(latestEvent?.timestamp || watcher.last_check)}</span>
              </div>
            </button>
          {/each}
        </div>
      {/if}
    </aside>

    <section class="detail-panel">
      {#if !$watchersLoading && !selectedWatcher}
        <div class="detail-empty">
          <Zap class="w-8 h-8" />
          <h2>No watcher selected</h2>
          <p>Pick a watcher from the list to inspect its actions and related events.</p>
        </div>
      {:else if selectedWatcher}
        <div class="detail-header">
          <div>
            <h2>{selectedWatcher.name}</h2>
            <p>
              Job #{selectedWatcher.job_id} on {selectedWatcher.hostname}
              {#if selectedWatcher.job_name}
                • {selectedWatcher.job_name}
              {/if}
            </p>
          </div>

          <div class="detail-pills">
            <span class="detail-pill">{selectedWatcher.state}</span>
            <span class="detail-pill">
              {eventSummaryByWatcher[selectedWatcher.id]?.count || 0} recent event(s)
            </span>
            <span class="detail-pill">
              created {formatRelativeTime(selectedWatcher.created_at)}
            </span>
          </div>
        </div>

        <div class="detail-grid">
          <div class="detail-card">
            <WatcherCard
              watcher={selectedWatcher}
              showJobLink={true}
              lastEvent={eventSummaryByWatcher[selectedWatcher.id]?.latest}
              on:copy={handleWatcherCopy}
              on:refresh={refreshData}
            />
          </div>

          <div class="insights-card">
            <div class="insight-block">
              <span class="insight-label">Last activity</span>
              <strong>
                {formatRelativeTime(
                  eventSummaryByWatcher[selectedWatcher.id]?.latest?.timestamp ||
                    selectedWatcher.last_check,
                )}
              </strong>
            </div>
            <div class="insight-block">
              <span class="insight-label">Host</span>
              <strong>{selectedWatcher.hostname}</strong>
            </div>
            <div class="insight-block">
              <span class="insight-label">Mode</span>
              <strong>
                {selectedWatcher.trigger_on_job_end
                  ? 'Terminal-state trigger'
                  : selectedWatcher.timer_mode_enabled
                    ? 'Pattern + timer'
                    : 'Pattern monitor'}
              </strong>
            </div>
            <div class="insight-block">
              <span class="insight-label">Same job</span>
              <strong>{sameJobWatchers.length} peer watcher(s)</strong>
            </div>

            {#if sameJobWatchers.length > 0}
              <div class="peer-list">
                {#each sameJobWatchers as peer (peer.id)}
                  <button class="peer-chip" onclick={() => selectWatcher(peer.id)}>
                    <Server class="w-3.5 h-3.5" />
                    {peer.name}
                  </button>
                {/each}
              </div>
            {/if}
          </div>
        </div>

        <div class="activity-card">
          <WatcherActivityFeed
            watcher={selectedWatcher}
            events={selectedWatcherEvents}
            loading={$eventsLoading && $watcherEvents.length === 0}
          />
        </div>
      {/if}

      <div class="activity-column" aria-label="Watcher activity overview">
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
                  onclick={() => selectWatcher(event.watcher_id)}
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
      </div>
    </section>
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
    min-height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--background);
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

  .page-copy p {
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
    grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
    gap: 1rem;
    align-items: start;
    padding: 1.25rem 1.5rem 1.5rem;
  }

  .board-panel {
    min-width: 0;
    padding: 0.9rem;
    border: 1px solid var(--border);
    border-radius: 1rem;
    background: var(--card);
  }

  .activity-column {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 1rem;
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
    gap: 0.7rem;
  }

  .host-lane-meta span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .host-lane-meter,
  .state-bar-track {
    height: 0.4rem;
    border-radius: 999px;
    overflow: hidden;
    background: color-mix(in srgb, var(--secondary) 90%, transparent);
  }

  .host-lane-fill,
  .state-bar-fill {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: var(--success);
    transition: width 0.22s ease;
  }

  .event-stream-item {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 0.65rem;
    padding: 0.62rem 0.7rem;
  }

  .event-stream-item:hover,
  .host-lane:hover,
  .state-bar-row:hover {
    border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  }

  .event-dot {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 999px;
    background: var(--success);
    box-shadow: 0 0 0 0.2rem color-mix(in srgb, var(--success) 16%, transparent);
  }

  .event-stream-item.failed .event-dot {
    background: var(--destructive);
    box-shadow: 0 0 0 0.2rem color-mix(in srgb, var(--destructive) 16%, transparent);
  }

  .event-stream-item strong,
  .event-stream-item p,
  .event-stream-item time {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .event-stream-item strong {
    display: block;
    color: var(--foreground);
    font-size: 0.82rem;
  }

  .event-stream-item p,
  .event-stream-item time {
    margin: 0;
    color: var(--muted-foreground);
    font-size: 0.74rem;
  }

  .state-bar-row {
    display: grid;
    grid-template-columns: 74px minmax(0, 1fr) 2rem;
    align-items: center;
    gap: 0.6rem;
    padding: 0.55rem 0.65rem;
    color: var(--muted-foreground);
    font-size: 0.78rem;
    font-weight: 600;
  }

  .state-bar-row strong {
    color: var(--foreground);
    text-align: right;
  }

  .state-bar-row[data-state='paused'] .state-bar-fill {
    background: var(--warning);
  }

  .state-bar-row[data-state='static'] .state-bar-fill,
  .state-bar-row[data-state='completed'] .state-bar-fill {
    background: var(--accent);
  }

  .list-panel,
  .detail-panel,
  .activity-column {
    min-height: 0;
  }

  .list-panel {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: 1.2rem;
    background: var(--card);
    overflow: hidden;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.8rem;
  }

  .summary-card {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0.9rem;
    border: 1px solid var(--border);
    border-radius: 1rem;
    background: color-mix(in srgb, var(--background) 92%, transparent);
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

  .list-header h2,
  .detail-empty h2,
  .detail-header h2 {
    margin: 0;
    color: var(--foreground);
    font-size: 1.1rem;
  }

  .list-header p,
  .detail-empty p,
  .detail-header p {
    margin: 0.3rem 0 0;
    color: var(--muted-foreground);
    font-size: 0.84rem;
  }

  .watcher-list {
    flex: 1;
    min-height: 0;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding-right: 0.2rem;
  }

  .watcher-list-item {
    display: flex;
    flex-direction: column;
    gap: 0.7rem;
    padding: 0.95rem;
    border: 1px solid var(--border);
    border-radius: 1rem;
    background: var(--background);
    color: inherit;
    text-align: left;
    cursor: pointer;
    transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
  }

  .watcher-list-item:hover,
  .watcher-list-item.selected {
    border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
    box-shadow: 0 12px 28px color-mix(in srgb, var(--foreground) 8%, transparent);
    transform: translateY(-1px);
  }

  .item-row,
  .item-title-group,
  .item-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.8rem;
  }

  .item-title-group {
    justify-content: flex-start;
    min-width: 0;
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

  .item-title {
    font-weight: 600;
    color: var(--foreground);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .item-subtitle,
  .item-body,
  .item-footer {
    color: var(--muted-foreground);
    font-size: 0.78rem;
  }

  .item-body {
    display: grid;
    gap: 0.35rem;
    white-space: nowrap;
    overflow: hidden;
  }

  .item-body span,
  .item-footer span {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .item-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 1.9rem;
    padding: 0.2rem 0.45rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--secondary) 88%, transparent);
    color: var(--foreground);
    font-size: 0.76rem;
    font-weight: 700;
  }

  .detail-panel {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow: auto;
  }

  .detail-empty,
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

  .detail-empty {
    flex-direction: column;
    gap: 0.75rem;
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
    justify-content: flex-end;
    gap: 0.55rem;
  }

  .detail-pill,
  .peer-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.35rem 0.6rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--secondary) 88%, transparent);
    color: var(--foreground);
    font-size: 0.78rem;
    font-weight: 600;
    border: none;
  }

  .detail-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 1rem;
    align-items: start;
  }

  .detail-card,
  .insights-card,
  .activity-card {
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: 1.2rem;
    background: var(--card);
  }

  .insights-card {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.9rem;
  }

  .insight-block {
    display: flex;
    flex-direction: column;
    gap: 0.22rem;
  }

  .insight-label {
    color: var(--muted-foreground);
    font-size: 0.76rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .insight-block strong {
    color: var(--foreground);
    font-size: 0.94rem;
    line-height: 1.4;
  }

  .peer-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.55rem;
    grid-column: 1 / -1;
  }

  .peer-chip {
    cursor: pointer;
  }

  @media (max-width: 1400px) {
    .activity-column {
      display: flex;
    }

    .insights-card {
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

    .list-panel {
      order: 1;
    }

    .detail-panel {
      order: 2;
      overflow: visible;
    }

    .activity-column {
      order: 3;
      display: flex;
    }

    .summary-grid {
      grid-template-columns: 1fr 1fr;
    }

    .detail-header {
      flex-direction: column;
    }

    .detail-pills {
      justify-content: flex-start;
    }

    .insights-card {
      grid-template-columns: 1fr 1fr;
    }
  }
</style>
