<script lang="ts">
  import {
    fetchJobWatchers,
    getWatcherJobKey,
    jobWatchersErrors,
    jobWatchersLoading,
    watcherEvents,
    watchers as watcherStore,
  } from "../stores/watchers";
  import type { Watcher, WatcherEvent } from "../types/watchers";
  import type { JobInfo } from "../types/api";
  import {
    Eye,
    ChevronDown,
    ChevronRight,
    Clock,
    Activity,
    CheckCircle,
    PauseCircle,
    AlertCircle,
    Play,
    Variable,
    Hash,
    Radio,
    RefreshCw,
    Zap
  } from "lucide-svelte";
  import LoadingSpinner from "./LoadingSpinner.svelte";

  interface Props {
    job: JobInfo;
  }

  let { job }: Props = $props();

  let expandedWatchers = $state(new Set<number>());
  let jobKey = $derived(getWatcherJobKey(job.job_id, job.hostname));
  let jobWatchers = $derived(
    $watcherStore.filter(
      (watcher) =>
        watcher.job_id === job.job_id && watcher.hostname === job.hostname
    )
  );
  let relatedEvents = $derived(
    $watcherEvents
      .filter((event) => event.job_id === job.job_id && event.hostname === job.hostname)
      .slice(0, 6)
  );
  let loading = $derived(Boolean($jobWatchersLoading[jobKey]) && jobWatchers.length === 0);
  let refreshing = $derived(Boolean($jobWatchersLoading[jobKey]) && jobWatchers.length > 0);
  let error = $derived($jobWatchersErrors[jobKey] || null);
  let activeCount = $derived(jobWatchers.filter((watcher) => watcher.state === 'active').length);
  let pausedCount = $derived(jobWatchers.filter((watcher) => watcher.state === 'paused').length);
  let totalTriggers = $derived(
    jobWatchers.reduce((count, watcher) => count + (watcher.trigger_count || 0), 0)
  );
  let nextCheck = $derived(
    jobWatchers
      .filter((watcher) => watcher.state === 'active')
      .map((watcher) => watcher.interval_seconds)
      .sort((left, right) => left - right)[0]
  );

  async function loadWatchers() {
    await fetchJobWatchers(job.job_id, job.hostname, { maxAgeMs: 0 });
  }

  function toggleWatcher(watcherId: number) {
    if (expandedWatchers.has(watcherId)) {
      expandedWatchers.delete(watcherId);
    } else {
      expandedWatchers.add(watcherId);
    }
    expandedWatchers = expandedWatchers;
  }

  function getStateIcon(state: string | undefined) {
    if (!state) return AlertCircle;

    switch (state) {
      case 'active':
        return Activity;
      case 'paused':
        return PauseCircle;
      case 'completed':
        return CheckCircle;
      case 'triggered':
        return Play;
      default:
        return AlertCircle;
    }
  }

  function getStateColor(state: string | undefined) {
    if (!state) return 'state-unknown';

    switch (state) {
      case 'active':
        return 'state-active';
      case 'paused':
        return 'state-paused';
      case 'completed':
        return 'state-completed';
      case 'triggered':
        return 'state-triggered';
      default:
        return 'state-unknown';
    }
  }

  function formatTime(timeStr: string | null | undefined): string {
    if (!timeStr) return 'Never';
    try {
      const date = new Date(timeStr);
      return date.toLocaleString();
    } catch {
      return 'Invalid date';
    }
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

  function eventSummary(event: WatcherEvent): string {
    if (event.matched_text) return event.matched_text;
    if (event.action_result) return event.action_result;
    return event.action_type.replace(/_/g, ' ');
  }

  function getActionDescription(action: any): string {
    const params = action.config || action.params || {};

    switch (action.type) {
      case 'log_event':
        return params.message ? `Log: "${params.message}"` : 'Log event';
      case 'store_metric':
        const metricName = params.metric_name || params.name;
        return metricName ? `Store metric: ${metricName}` : 'Store metric';
      case 'run_command':
        return params.command ? `Run: ${params.command.substring(0, 50)}${params.command.length > 50 ? '...' : ''}` : 'Run command';
      case 'cancel_job':
        return params.reason ? `Cancel job: ${params.reason}` : 'Cancel job';
      case 'resubmit':
        return params.delay ? `Resubmit with ${params.delay}s delay` : 'Resubmit job';
      case 'pause_watcher':
        return 'Pause this watcher';
      default:
        return action.type.replace(/_/g, ' ');
    }
  }

  $effect(() => {
    void fetchJobWatchers(job.job_id, job.hostname, { maxAgeMs: 15_000 }).catch(() => {});
  });
</script>

<div class="watchers-tab">
  {#if loading}
    <LoadingSpinner message="Preparing watchers..." />
  {:else if error}
    <div class="error-container">
      <AlertCircle class="w-5 h-5 text-red-500" />
      <span class="text-red-700">{error}</span>
      <button class="btn btn-sm" onclick={loadWatchers}>Retry</button>
    </div>
  {:else if jobWatchers.length === 0}
    <div class="empty-state">
      <Eye class="w-12 h-12 text-gray-400 mx-auto" />
      <h3 class="text-lg font-medium text-gray-900 mt-2">No watchers configured</h3>
      <p class="text-sm text-gray-500 mt-1">
        Watchers can be configured when launching a job or attached to running jobs.
      </p>
    </div>
  {:else}
    <div class="job-watchers-overview">
      <div class="overview-title">
        <div>
          <h3>Job Watchers</h3>
          <p>{job.hostname} · job #{job.job_id}</p>
        </div>
        <button class="refresh-button" onclick={loadWatchers} disabled={refreshing}>
          <RefreshCw class={`w-4 h-4${refreshing ? ' spin' : ''}`} />
          <span>{refreshing ? 'Refreshing' : 'Refresh'}</span>
        </button>
      </div>

      <div class="metric-strip">
        <div class="metric-tile active">
          <Activity class="w-4 h-4" />
          <span>Active</span>
          <strong>{activeCount}</strong>
        </div>
        <div class="metric-tile paused">
          <PauseCircle class="w-4 h-4" />
          <span>Paused</span>
          <strong>{pausedCount}</strong>
        </div>
        <div class="metric-tile">
          <Zap class="w-4 h-4" />
          <span>Triggers</span>
          <strong>{totalTriggers}</strong>
        </div>
        <div class="metric-tile">
          <Radio class="w-4 h-4" />
          <span>Fastest check</span>
          <strong>{nextCheck ? `${nextCheck}s` : 'manual'}</strong>
        </div>
      </div>

      {#if relatedEvents.length > 0}
        <div class="event-ribbon">
          {#each relatedEvents as event (event.id)}
            <div class="event-chip" class:failed={!event.success}>
              <span>{formatRelativeTime(event.timestamp)}</span>
              <strong>{event.action_type.replace(/_/g, ' ')}</strong>
              <em>{eventSummary(event)}</em>
            </div>
          {/each}
        </div>
      {/if}
    </div>

    <div class="watchers-list">
      <div class="header">
        <h3 class="text-lg font-semibold">Configured watchers ({jobWatchers.length})</h3>
      </div>

      {#each jobWatchers as watcher}
        {#if watcher}
        {@const SvelteComponent = getStateIcon(watcher.state)}
        <div class="watcher-card" class:expanded={expandedWatchers.has(watcher.id)}>
          <button
            class="watcher-header"
            onclick={() => toggleWatcher(watcher.id)}
          >
            <div class="header-left">
              <span class="expand-icon">
                {#if expandedWatchers.has(watcher.id)}
                  <ChevronDown class="w-4 h-4" />
                {:else}
                  <ChevronRight class="w-4 h-4" />
                {/if}
              </span>

              <div class="watcher-info">
                <span class="watcher-name">{watcher.name}</span>
                <div class="watcher-meta">
                  <span class="state-badge {getStateColor(watcher.state)}">
                    <SvelteComponent class="w-3 h-3" />
                    {watcher.state}
                  </span>
                  <span class="trigger-count">
                    <Hash class="w-3 h-3" />
                    {watcher.trigger_count} trigger{watcher.trigger_count !== 1 ? 's' : ''}
                  </span>
                  {#if watcher.timer_mode_active}
                    <span class="timer-mode">
                      <Clock class="w-3 h-3" />
                      Timer mode
                    </span>
                  {/if}
                </div>
              </div>
            </div>
          </button>

          {#if expandedWatchers.has(watcher.id)}
            <div class="watcher-details">
              <!-- Pattern Section -->
              <div class="detail-section">
                <h4>Pattern</h4>
                <code class="pattern-code">{watcher.pattern}</code>
              </div>

              <!-- Captures Section -->
              {#if watcher.captures && watcher.captures.length > 0}
                <div class="detail-section">
                  <h4>Capture Groups</h4>
                  <div class="captures-list">
                    {#each watcher.captures as capture}
                      <span class="capture-badge">{capture}</span>
                    {/each}
                  </div>
                </div>
              {/if}

              <!-- Captured Variables Section -->
              {#if watcher.variables && Object.keys(watcher.variables).length > 0}
                <div class="detail-section variables-section">
                  <h4>
                    <Variable class="w-4 h-4" />
                    Captured Variables
                  </h4>
                  <div class="variables-grid">
                    {#each Object.entries(watcher.variables) as [name, value]}
                      <div class="variable-item">
                        <span class="variable-name">{name}:</span>
                        <span class="variable-value">{value}</span>
                      </div>
                    {/each}
                  </div>
                </div>
              {:else if watcher.captures && watcher.captures.length > 0}
                <div class="detail-section">
                  <h4>
                    <Variable class="w-4 h-4" />
                    Captured Variables
                  </h4>
                  <p class="no-variables">No variables captured yet</p>
                </div>
              {/if}

              <!-- Condition Section -->
              {#if watcher.condition}
                <div class="detail-section">
                  <h4>Condition</h4>
                  <code class="condition-code">{watcher.condition}</code>
                </div>
              {/if}

              <!-- Actions Section -->
              {#if watcher.actions && watcher.actions.length > 0}
                <div class="detail-section">
                  <h4>Actions</h4>
                  <ul class="actions-list">
                    {#each watcher.actions as action}
                      <li class="action-item">
                        {getActionDescription(action)}
                        {#if action.condition}
                          <span class="action-condition">if {action.condition}</span>
                        {/if}
                      </li>
                    {/each}
                  </ul>
                </div>
              {/if}

              <!-- Timing Section -->
              <div class="detail-section">
                <h4>Timing</h4>
                <div class="timing-info">
                  <div class="timing-item">
                    <span class="timing-label">Check interval:</span>
                    <span>{watcher.interval_seconds}s</span>
                  </div>
                  <div class="timing-item">
                    <span class="timing-label">Last check:</span>
                    <span>{formatTime(watcher.last_check)}</span>
                  </div>
                  <div class="timing-item">
                    <span class="timing-label">Created:</span>
                    <span>{formatTime(watcher.created_at)}</span>
                  </div>
                  {#if watcher.timer_mode_enabled}
                    <div class="timing-item">
                      <span class="timing-label">Timer interval:</span>
                      <span>{watcher.timer_interval_seconds}s</span>
                    </div>
                  {/if}
                </div>
              </div>
            </div>
          {/if}
        </div>
        {/if}
      {/each}
    </div>
  {/if}
</div>

<style>
  .watchers-tab {
    height: 100%;
    overflow-y: auto;
    padding: 1rem;
    background: var(--secondary);
    color: var(--foreground);
  }

  .job-watchers-overview {
    max-width: 1200px;
    margin: 0 auto 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
  }

  .overview-title {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.9rem 1rem;
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    background: var(--card);
  }

  .overview-title h3 {
    margin: 0;
    color: var(--foreground);
    font-size: 1rem;
    font-weight: 700;
  }

  .overview-title p {
    margin: 0.25rem 0 0;
    color: var(--muted-foreground);
    font-size: 0.8rem;
  }

  .refresh-button {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    padding: 0.45rem 0.65rem;
    background: var(--background);
    color: var(--foreground);
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
  }

  .refresh-button:disabled {
    cursor: default;
    opacity: 0.7;
  }

  .spin {
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .metric-strip {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.7rem;
  }

  .metric-tile {
    display: grid;
    grid-template-columns: auto 1fr;
    align-items: center;
    gap: 0.25rem 0.5rem;
    min-width: 0;
    padding: 0.8rem;
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    background: var(--card);
    color: var(--muted-foreground);
  }

  .metric-tile strong {
    grid-column: 1 / -1;
    color: var(--foreground);
    font-size: 1.1rem;
  }

  .metric-tile span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.76rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .metric-tile.active {
    border-color: color-mix(in srgb, var(--success) 38%, var(--border));
  }

  .metric-tile.paused {
    border-color: color-mix(in srgb, var(--warning) 38%, var(--border));
  }

  .event-ribbon {
    display: flex;
    gap: 0.6rem;
    overflow-x: auto;
    padding-bottom: 0.15rem;
  }

  .event-chip {
    flex: 0 0 240px;
    min-width: 0;
    display: grid;
    gap: 0.18rem;
    padding: 0.65rem 0.75rem;
    border: 1px solid color-mix(in srgb, var(--success) 28%, var(--border));
    border-radius: 0.75rem;
    background: color-mix(in srgb, var(--success) 7%, var(--card));
  }

  .event-chip.failed {
    border-color: color-mix(in srgb, var(--destructive) 32%, var(--border));
    background: color-mix(in srgb, var(--destructive) 7%, var(--card));
  }

  .event-chip span,
  .event-chip em {
    color: var(--muted-foreground);
    font-size: 0.72rem;
    font-style: normal;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .event-chip strong {
    color: var(--foreground);
    font-size: 0.82rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .error-container {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem;
    background: color-mix(in srgb, var(--destructive) 10%, var(--card));
    border: 1px solid color-mix(in srgb, var(--destructive) 35%, var(--border));
    border-radius: 0.5rem;
    margin: 1rem;
    color: var(--destructive);
  }

  .empty-state {
    text-align: center;
    padding: 3rem 1rem;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    margin: 1rem;
  }

  .empty-state h3 {
    color: var(--foreground);
  }

  .empty-state p {
    color: var(--muted-foreground);
  }

  .watchers-list {
    max-width: 1200px;
    margin: 0 auto;
  }

  .header {
    margin-bottom: 1rem;
    padding: 0 0.5rem;
  }

  .header h3 {
    color: var(--foreground);
  }

  .watcher-card {
    background: var(--card);
    border-radius: 0.5rem;
    margin-bottom: 0.75rem;
    border: 1px solid var(--border);
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .watcher-card.expanded {
    border-color: color-mix(in srgb, var(--accent) 30%, var(--border));
    box-shadow: 0 1px 3px 0 color-mix(in srgb, var(--foreground) 10%, transparent);
  }

  .watcher-header {
    width: 100%;
    padding: 0.75rem 1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
  }

  .watcher-header:hover {
    background: var(--secondary);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 1;
  }

  .expand-icon {
    color: var(--muted-foreground);
  }

  .watcher-info {
    flex: 1;
    min-width: 0;
  }

  .watcher-name {
    font-weight: 600;
    color: var(--foreground);
    display: block;
    margin-bottom: 0.25rem;
  }

  .watcher-meta {
    display: flex;
    align-items: center;
    gap: 1rem;
    font-size: 0.875rem;
    color: var(--muted-foreground);
  }

  .state-badge {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-weight: 500;
  }

  .state-active {
    color: var(--success);
  }

  .state-paused {
    color: var(--warning);
  }

  .state-completed,
  .state-triggered {
    color: var(--accent);
  }

  .state-unknown {
    color: var(--muted-foreground);
  }

  .trigger-count {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    color: var(--muted-foreground);
  }

  .timer-mode {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    color: var(--accent);
  }

  .watcher-details {
    padding: 0 1rem 1rem 3rem;
    border-top: 1px solid var(--border);
  }

  .detail-section {
    margin-top: 1rem;
  }

  .detail-section h4 {
    font-weight: 600;
    font-size: 0.875rem;
    color: var(--muted-foreground);
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .pattern-code,
  .condition-code {
    display: block;
    padding: 0.5rem;
    background: var(--secondary);
    border-radius: 0.25rem;
    font-family: monospace;
    font-size: 0.875rem;
    color: var(--foreground);
    word-break: break-all;
  }

  .captures-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .capture-badge {
    padding: 0.25rem 0.5rem;
    background: color-mix(in srgb, var(--accent) 14%, var(--card));
    color: var(--accent);
    border-radius: 0.25rem;
    font-size: 0.875rem;
    font-family: monospace;
  }

  .variables-section {
    background: color-mix(in srgb, var(--success) 9%, var(--card));
    padding: 0.75rem;
    border-radius: 0.375rem;
    border: 1px solid color-mix(in srgb, var(--success) 30%, var(--border));
  }

  .variables-grid {
    display: grid;
    gap: 0.5rem;
  }

  .variable-item {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    font-size: 0.875rem;
  }

  .variable-name {
    font-weight: 600;
    color: var(--success);
    font-family: monospace;
    min-width: 100px;
  }

  .variable-value {
    color: var(--foreground);
    font-family: monospace;
    word-break: break-all;
    flex: 1;
  }

  .no-variables {
    color: var(--muted-foreground);
    font-size: 0.875rem;
    font-style: italic;
  }

  .actions-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .action-item {
    padding: 0.5rem;
    background: var(--secondary);
    border-radius: 0.25rem;
    margin-bottom: 0.5rem;
    font-size: 0.875rem;
    color: var(--foreground);
  }

  .action-condition {
    display: block;
    margin-top: 0.25rem;
    color: var(--muted-foreground);
    font-size: 0.75rem;
    font-style: italic;
  }

  .timing-info {
    display: grid;
    gap: 0.5rem;
  }

  .timing-item {
    display: flex;
    justify-content: space-between;
    font-size: 0.875rem;
  }

  .timing-label {
    color: var(--muted-foreground);
  }

  .btn {
    padding: 0.375rem 0.75rem;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 0.375rem;
    font-size: 0.875rem;
    cursor: pointer;
    transition: background 0.2s;
  }

  .btn:hover {
    background: var(--accent);
  }

  .btn-sm {
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
  }

  @media (max-width: 640px) {
    .watchers-tab {
      padding: 0.5rem;
    }

    .overview-title {
      flex-direction: column;
    }

    .metric-strip {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .watcher-details {
      padding: 0 0.5rem 0.5rem 2rem;
    }

    .watcher-meta {
      flex-wrap: wrap;
      gap: 0.5rem;
    }

    .variable-item {
      flex-direction: column;
      gap: 0.125rem;
    }

    .variable-name {
      min-width: unset;
    }
  }
</style>
