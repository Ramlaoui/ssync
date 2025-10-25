<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "../services/api";
  import type { Watcher, WatchersResponse } from "../types/watchers";
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
    Hash
  } from "lucide-svelte";
  import LoadingSpinner from "./LoadingSpinner.svelte";

  interface Props {
    job: JobInfo;
  }

  let { job }: Props = $props();

  let watchers: Watcher[] = $state([]);
  let loading = $state(true);
  let error: string | null = $state(null);
  let expandedWatchers = $state(new Set<number>());

  async function loadWatchers() {
    try {
      loading = true;
      error = null;

      const response = await api.get<WatchersResponse>(
        `/api/jobs/${job.job_id}/watchers?host=${job.hostname}`
      );

      // Filter out any null/undefined watchers and ensure required properties exist
      watchers = (response.data.watchers || []).filter(w => w != null && w.state != null && w.id != null);
    } catch (err: any) {
      error = err.response?.data?.detail || err.message || "Failed to load watchers";
    } finally {
      loading = false;
    }
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
    if (!state) return 'text-gray-600';

    switch (state) {
      case 'active':
        return 'text-green-600';
      case 'paused':
        return 'text-yellow-600';
      case 'completed':
        return 'text-blue-600';
      case 'triggered':
        return 'text-purple-600';
      default:
        return 'text-gray-600';
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

  onMount(() => {
    loadWatchers();
  });
</script>

<div class="watchers-tab">
  {#if loading}
    <LoadingSpinner message="Loading watchers..." />
  {:else if error}
    <div class="error-container">
      <AlertCircle class="w-5 h-5 text-red-500" />
      <span class="text-red-700">{error}</span>
      <button class="btn btn-sm" onclick={loadWatchers}>Retry</button>
    </div>
  {:else if watchers.length === 0}
    <div class="empty-state">
      <Eye class="w-12 h-12 text-gray-400 mx-auto" />
      <h3 class="text-lg font-medium text-gray-900 mt-2">No watchers configured</h3>
      <p class="text-sm text-gray-500 mt-1">
        Watchers can be configured when launching a job or attached to running jobs.
      </p>
    </div>
  {:else}
    <div class="watchers-list">
      <div class="header">
        <h3 class="text-lg font-semibold">Job Watchers ({watchers.length})</h3>
      </div>

      {#each watchers as watcher}
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
    background: #f9fafb;
  }

  .error-container {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem;
    background: white;
    border: 1px solid #fecaca;
    border-radius: 0.5rem;
    margin: 1rem;
  }

  .empty-state {
    text-align: center;
    padding: 3rem 1rem;
    background: white;
    border-radius: 0.5rem;
    margin: 1rem;
  }

  .watchers-list {
    max-width: 1200px;
    margin: 0 auto;
  }

  .header {
    margin-bottom: 1rem;
    padding: 0 0.5rem;
  }

  .watcher-card {
    background: white;
    border-radius: 0.5rem;
    margin-bottom: 0.75rem;
    border: 1px solid #e5e7eb;
    transition: box-shadow 0.2s;
  }

  .watcher-card.expanded {
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
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
    background: #f9fafb;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 1;
  }

  .expand-icon {
    color: #6b7280;
  }

  .watcher-info {
    flex: 1;
  }

  .watcher-name {
    font-weight: 600;
    color: #1f2937;
    display: block;
    margin-bottom: 0.25rem;
  }

  .watcher-meta {
    display: flex;
    align-items: center;
    gap: 1rem;
    font-size: 0.875rem;
  }

  .state-badge {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-weight: 500;
  }

  .trigger-count {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    color: #6b7280;
  }

  .timer-mode {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    color: #8b5cf6;
  }

  .watcher-details {
    padding: 0 1rem 1rem 3rem;
    border-top: 1px solid #e5e7eb;
  }

  .detail-section {
    margin-top: 1rem;
  }

  .detail-section h4 {
    font-weight: 600;
    font-size: 0.875rem;
    color: #4b5563;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .pattern-code,
  .condition-code {
    display: block;
    padding: 0.5rem;
    background: #f3f4f6;
    border-radius: 0.25rem;
    font-family: monospace;
    font-size: 0.875rem;
    color: #1f2937;
    word-break: break-all;
  }

  .captures-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .capture-badge {
    padding: 0.25rem 0.5rem;
    background: #dbeafe;
    color: #1e40af;
    border-radius: 0.25rem;
    font-size: 0.875rem;
    font-family: monospace;
  }

  .variables-section {
    background: #f0fdf4;
    padding: 0.75rem;
    border-radius: 0.375rem;
    border: 1px solid #bbf7d0;
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
    color: #15803d;
    font-family: monospace;
    min-width: 100px;
  }

  .variable-value {
    color: #166534;
    font-family: monospace;
    word-break: break-all;
    flex: 1;
  }

  .no-variables {
    color: #6b7280;
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
    background: #f9fafb;
    border-radius: 0.25rem;
    margin-bottom: 0.5rem;
    font-size: 0.875rem;
    color: #1f2937;
  }

  .action-condition {
    display: block;
    margin-top: 0.25rem;
    color: #6b7280;
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
    color: #6b7280;
  }

  .btn {
    padding: 0.375rem 0.75rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 0.375rem;
    font-size: 0.875rem;
    cursor: pointer;
    transition: background 0.2s;
  }

  .btn:hover {
    background: #2563eb;
  }

  .btn-sm {
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
  }

  @media (max-width: 640px) {
    .watchers-tab {
      padding: 0.5rem;
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