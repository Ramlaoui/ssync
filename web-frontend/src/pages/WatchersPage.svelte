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
    Clock3,
    Eye,
    Filter,
    Plus,
    Search,
    Server,
    Zap,
  } from 'lucide-svelte';

  const allCurrentJobs = jobStateManager.getAllJobs();

  type FilterState = 'all' | 'active' | 'paused' | 'static' | 'completed';
  type SortMode = 'activity' | 'recent' | 'name';
  type EnhancedWatcher = Watcher & { job_name?: string | null };

  let searchQuery = $state('');
  let filterState: FilterState = $state('all');
  let sortMode: SortMode = $state('activity');
  let selectedWatcherId: number | null = $state(null);
  let error: string | null = $state(null);

  let showStreamlinedCreator = $state(false);
  let showJobSelectionDialog = $state(false);
  let copiedWatcherConfig: any = $state(null);
  let selectedJobId: string | null = $state(null);
  let selectedHostname: string | null = $state(null);
  let pendingMultiJobSelection: any[] = [];

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

  function updateSelectionInUrl(watcherId: number | null) {
    if (typeof window === 'undefined') return;

    const url = new URL(window.location.href);
    if (watcherId == null) {
      url.searchParams.delete('watcher');
    } else {
      url.searchParams.set('watcher', String(watcherId));
    }
    url.searchParams.delete('tab');

    const nextQuery = url.searchParams.toString();
    const nextUrl = `${url.pathname}${nextQuery ? `?${nextQuery}` : ''}`;
    window.history.replaceState({}, '', nextUrl);
  }

  function readSelectionFromUrl() {
    if (typeof window === 'undefined') return;
    const watcherParam = new URLSearchParams(window.location.search).get('watcher');
    if (!watcherParam) return;
    const parsed = Number(watcherParam);
    if (!Number.isNaN(parsed)) {
      selectedWatcherId = parsed;
    }
  }

  async function refreshData() {
    error = null;
    try {
      await Promise.all([
        jobStateManager.syncAllHosts(),
        fetchAllWatchers(),
        fetchWatcherEvents(undefined, undefined, 300),
      ]);
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

  let eventSummaryByWatcher = $derived(
    (() => {
      const summary: Record<number, { count: number; latest?: WatcherEvent }> = {};

      for (const event of $watcherEvents) {
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
    })(),
  );

  let enhancedWatchers = $derived(
    (() => {
      const jobs = get(allCurrentJobs);
      return $watchers.map((watcher) => {
        const job = jobs.find(
          (candidate) =>
            candidate.job_id === watcher.job_id &&
            candidate.hostname === watcher.hostname,
        );

        return {
          ...watcher,
          job_name: job?.name || watcher.job_name || null,
        } as EnhancedWatcher;
      });
    })(),
  );

  let filteredWatchers = $derived(
    (() => {
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
    })(),
  );

  let selectedWatcher = $derived(
    filteredWatchers.find((watcher) => watcher.id === selectedWatcherId) || null,
  );

  let selectedWatcherEvents = $derived(
    selectedWatcher
      ? $watcherEvents
          .filter((event) => event.watcher_id === selectedWatcher.id)
          .slice(0, 60)
      : [],
  );

  let sameJobWatchers = $derived(
    selectedWatcher
      ? filteredWatchers.filter(
          (watcher) =>
            watcher.id !== selectedWatcher.id &&
            watcher.job_id === selectedWatcher.job_id &&
            watcher.hostname === selectedWatcher.hostname,
        )
      : [],
  );

  let watcherCounts = $derived({
    total: $watchers.length,
    active: $watchers.filter((watcher) => watcher.state === 'active').length,
    paused: $watchers.filter((watcher) => watcher.state === 'paused').length,
    static: $watchers.filter((watcher) => watcher.state === 'static').length,
    completed: $watchers.filter((watcher) => watcher.state === 'completed').length,
  });

  let hostCount = $derived(new Set($watchers.map((watcher) => watcher.hostname)).size);
  let recentEventCount = $derived($watcherEvents.length);

  $effect(() => {
    if (filteredWatchers.length === 0) {
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
    navigationActions.setContext('watcher', {
      previousRoute: window.location.pathname,
    });

    readSelectionFromUrl();
    await refreshData();
    connectWatcherWebSocket();
  });

  onDestroy(() => {
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
    grid-template-columns: minmax(320px, 390px) minmax(0, 1fr);
    gap: 1.25rem;
    padding: 1.25rem 1.5rem 1.5rem;
  }

  .list-panel,
  .detail-panel {
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .list-panel {
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
    grid-template-columns: minmax(0, 1fr) minmax(240px, 300px);
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
    display: flex;
    flex-direction: column;
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
  }

  .peer-chip {
    cursor: pointer;
  }

  @media (max-width: 1100px) {
    .workspace {
      grid-template-columns: 1fr;
    }

    .detail-grid {
      grid-template-columns: 1fr;
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
      padding: 1rem;
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
  }
</style>
