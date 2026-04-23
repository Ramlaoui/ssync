<script lang="ts">
  import { Search, Clock3, CircleAlert, CheckCircle2, XCircle } from 'lucide-svelte';
  import type { Watcher, WatcherEvent } from '../types/watchers';

  interface Props {
    watcher: Watcher | null;
    events?: WatcherEvent[];
    loading?: boolean;
  }

  let { watcher, events = [], loading = false }: Props = $props();

  let searchTerm = $state('');

  function formatRelativeTime(timestamp: string): string {
    const date = new Date(timestamp);
    const diffMs = Date.now() - date.getTime();
    const diffMinutes = Math.floor(diffMs / 60000);

    if (diffMinutes < 1) return 'just now';
    if (diffMinutes < 60) return `${diffMinutes}m ago`;

    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours}h ago`;

    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  }

  function formatAbsoluteTime(timestamp: string): string {
    return new Date(timestamp).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }

  function getStatusColor(event: WatcherEvent): string {
    return event.success === false ? 'var(--destructive)' : 'var(--success)';
  }

  function getStatusLabel(event: WatcherEvent): string {
    return event.success === false ? 'failed' : 'ok';
  }

  let filteredEvents = $derived(
    events.filter((event) => {
      if (!searchTerm) return true;
      const term = searchTerm.toLowerCase();
      return [
        event.action_type,
        event.matched_text,
        event.action_result,
        event.job_id,
        event.hostname,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(term);
    }),
  );
</script>

<section class="activity-feed">
  <div class="activity-header">
    <div>
      <h3>Related Activity</h3>
      <p>
        {#if watcher}
          Recent events for {watcher.name}
        {:else}
          Recent watcher events
        {/if}
      </p>
    </div>

    <div class="activity-search">
      <Search class="w-4 h-4" />
      <input
        type="text"
        bind:value={searchTerm}
        placeholder="Search events"
      />
    </div>
  </div>

  {#if loading}
    <div class="activity-empty">
      <Clock3 class="w-5 h-5" />
      <span>Loading events…</span>
    </div>
  {:else if filteredEvents.length === 0}
    <div class="activity-empty">
      <CircleAlert class="w-5 h-5" />
      <span>
        {searchTerm ? 'No matching events yet.' : 'No related events yet.'}
      </span>
    </div>
  {:else}
    <div class="activity-list">
      {#each filteredEvents as event (event.id)}
        <article class="activity-item">
          <div class="activity-marker" style={`--marker-color: ${getStatusColor(event)}`}>
            {#if event.success === false}
              <XCircle class="w-4 h-4" />
            {:else}
              <CheckCircle2 class="w-4 h-4" />
            {/if}
          </div>

          <div class="activity-body">
            <div class="activity-row">
              <div class="activity-title">
                <span class="activity-action">{event.action_type.replace(/_/g, ' ')}</span>
                <span class="activity-status">{getStatusLabel(event)}</span>
              </div>
              <time title={formatAbsoluteTime(event.timestamp)}>
                {formatRelativeTime(event.timestamp)}
              </time>
            </div>

            <div class="activity-meta">
              <span>Job #{event.job_id}</span>
              <span>{event.hostname}</span>
            </div>

            {#if event.matched_text}
              <pre class="activity-snippet">{event.matched_text}</pre>
            {/if}

            {#if event.captured_vars && Object.keys(event.captured_vars).length > 0}
              <div class="activity-vars">
                {#each Object.entries(event.captured_vars) as [key, value]}
                  <span class="activity-var">{key}={String(value)}</span>
                {/each}
              </div>
            {/if}

            {#if event.action_result}
              <div class="activity-result">{event.action_result}</div>
            {/if}
          </div>
        </article>
      {/each}
    </div>
  {/if}
</section>

<style>
  .activity-feed {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    min-height: 0;
  }

  .activity-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }

  .activity-header h3 {
    margin: 0;
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--foreground);
  }

  .activity-header p {
    margin: 0.25rem 0 0;
    color: var(--muted-foreground);
    font-size: 0.8rem;
  }

  .activity-search {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 220px;
    padding: 0.65rem 0.8rem;
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    background: var(--background);
    color: var(--muted-foreground);
  }

  .activity-search input {
    width: 100%;
    border: none;
    background: transparent;
    color: var(--foreground);
    font-size: 0.85rem;
  }

  .activity-search input:focus {
    outline: none;
  }

  .activity-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.65rem;
    min-height: 140px;
    border: 1px dashed var(--border);
    border-radius: 1rem;
    color: var(--muted-foreground);
    background: color-mix(in srgb, var(--card) 90%, transparent);
  }

  .activity-list {
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
  }

  .activity-item {
    display: grid;
    grid-template-columns: 2rem minmax(0, 1fr);
    gap: 0.9rem;
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: 1rem;
    background: var(--card);
  }

  .activity-marker {
    display: flex;
    align-items: flex-start;
    justify-content: center;
    color: var(--marker-color);
    position: relative;
  }

  .activity-marker::before {
    content: '';
    position: absolute;
    inset: 0.1rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--marker-color) 12%, transparent);
    z-index: 0;
  }

  .activity-marker :global(svg) {
    position: relative;
    z-index: 1;
  }

  .activity-body {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
  }

  .activity-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .activity-title {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    min-width: 0;
  }

  .activity-action {
    color: var(--foreground);
    font-size: 0.9rem;
    font-weight: 600;
    text-transform: capitalize;
  }

  .activity-status {
    display: inline-flex;
    align-items: center;
    padding: 0.15rem 0.45rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    background: var(--secondary);
    color: var(--muted-foreground);
  }

  .activity-row time {
    color: var(--muted-foreground);
    font-size: 0.78rem;
    flex-shrink: 0;
  }

  .activity-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    color: var(--muted-foreground);
    font-size: 0.78rem;
  }

  .activity-meta span {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.18rem 0.45rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--secondary) 85%, transparent);
  }

  .activity-snippet {
    margin: 0;
    padding: 0.8rem;
    border-radius: 0.8rem;
    background: color-mix(in srgb, var(--secondary) 92%, transparent);
    color: var(--foreground);
    font-size: 0.78rem;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .activity-vars {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
  }

  .activity-var {
    display: inline-flex;
    align-items: center;
    padding: 0.22rem 0.55rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--foreground);
    font-size: 0.75rem;
  }

  .activity-result {
    color: var(--muted-foreground);
    font-size: 0.8rem;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
  }

  @media (max-width: 720px) {
    .activity-header {
      flex-direction: column;
    }

    .activity-search {
      min-width: 0;
      width: 100%;
    }
  }
</style>
