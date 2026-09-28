<script lang="ts">
  import { createEventDispatcher, tick } from 'svelte';
  import { push, location } from 'svelte-spa-router';
  import {
    Copy,
    ExternalLink,
    MoreHorizontal,
    Pause,
    Pencil,
    Play,
    Search,
    Trash2,
  } from 'lucide-svelte';
  import { navigationActions } from '../stores/navigation';
  import type { Watcher, WatcherEvent } from '../types/watchers';
  import { pauseWatcher, resumeWatcher, deleteWatcher as removeWatcher } from '../stores/watchers';
  import { api } from '../services/api';
  import WatcherDetailDialog from './WatcherDetailDialog.svelte';
  import { portal } from '../lib/actions/portal';

  interface Props {
    watcher: Watcher;
    lastEvent?: WatcherEvent | null;
    selected?: boolean;
  }

  let { watcher, lastEvent = null, selected = false }: Props = $props();

  const dispatch = createEventDispatcher();

  let isPausing = $state(false);
  let isTriggering = $state(false);
  let isDeleting = $state(false);
  let isDiscoveringTasks = $state(false);
  let statusMessage = $state('');
  let statusTone = $state<'success' | 'error' | 'neutral'>('neutral');
  let statusTimer: ReturnType<typeof setTimeout> | null = null;
  let showDetailDialog = $state(false);

  let menuOpen = $state(false);
  let menuPosition = $state({ top: 0, right: 0 });
  let menuButton: HTMLButtonElement | undefined = $state();
  let menuElement: HTMLDivElement | undefined = $state();

  const canToggle = $derived(watcher.state === 'active' || watcher.state === 'paused');
  const canRun = $derived(watcher.state === 'active' || watcher.state === 'static');
  const intervalSeconds = $derived(
    watcher.timer_mode_enabled
      ? watcher.timer_interval_seconds || watcher.interval_seconds
      : watcher.interval_seconds,
  );
  const lastActivity = $derived(lastEvent?.timestamp || watcher.last_check || null);
  const trigger = $derived(describeTrigger(watcher));
  const jobName = $derived(
    watcher.job_name && watcher.job_name !== 'N/A' ? watcher.job_name : '',
  );
  const actionSummary = $derived(
    (watcher.actions || []).map((action) => action.type.replace(/_/g, ' ')).join(', '),
  );

  function describeTrigger(item: Watcher): { label: string; mono: boolean; title: string } {
    const endStates = item.trigger_job_states?.length
      ? item.trigger_job_states.join(', ')
      : 'any end state';
    const jobEnd = item.trigger_on_job_end ? `Job ends: ${endStates}` : '';
    if (item.pattern) {
      return {
        label: item.pattern,
        mono: true,
        title: [`Pattern: ${item.pattern}`, jobEnd, item.timer_mode_enabled ? 'Timer mode' : '']
          .filter(Boolean)
          .join('\n'),
      };
    }
    if (jobEnd) return { label: jobEnd, mono: false, title: jobEnd };
    if (item.state === 'static') return { label: 'Manual run only', mono: false, title: '' };
    return { label: 'No pattern', mono: false, title: '' };
  }

  function formatInterval(seconds?: number | null): string {
    if (!seconds) return '—';
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    return `${Math.round((seconds / 3600) * 10) / 10}h`;
  }

  function formatRelative(timestamp?: string | null): string {
    if (!timestamp) return 'Never';
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return '—';
    const minutes = Math.floor((Date.now() - date.getTime()) / 60000);
    if (minutes < 1) return 'just now';
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  function formatAbsolute(timestamp?: string | null): string {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString();
  }

  function showStatus(message: string, tone: 'success' | 'error' | 'neutral', timeoutMs = 4000) {
    statusMessage = message;
    statusTone = tone;
    if (statusTimer) clearTimeout(statusTimer);
    statusTimer = setTimeout(() => {
      statusMessage = '';
      statusTimer = null;
    }, timeoutMs);
  }

  function errorDetail(error: any, fallback: string): string {
    return error?.response?.data?.detail || error?.message || fallback;
  }

  function inspect() {
    dispatch('inspect', { watcherId: watcher.id });
  }

  async function openMenu() {
    if (!menuButton) return;
    const rect = menuButton.getBoundingClientRect();
    menuPosition = {
      top: Math.round(rect.bottom + 4),
      right: Math.max(8, Math.round(window.innerWidth - rect.right)),
    };
    menuOpen = true;
    await tick();
    const menuRect = menuElement?.getBoundingClientRect();
    if (menuRect && menuRect.bottom > window.innerHeight - 8) {
      menuPosition = { ...menuPosition, top: Math.max(8, Math.round(rect.top - menuRect.height - 4)) };
    }
    menuElement?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
  }

  function closeMenu(restoreFocus = true) {
    if (!menuOpen) return;
    menuOpen = false;
    if (restoreFocus) menuButton?.focus();
  }

  function runFromMenu(action: () => void | Promise<void>) {
    closeMenu();
    void action();
  }

  function handleMenuKeydown(event: KeyboardEvent) {
    const items = Array.from(
      menuElement?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? [],
    );
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeMenu();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      items[(index + 1) % items.length]?.focus();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      items[(index - 1 + items.length) % items.length]?.focus();
    } else if (event.key === 'Tab') {
      closeMenu(false);
    }
  }

  function handleWindowPointer(event: PointerEvent) {
    if (!menuOpen) return;
    const target = event.target as Node;
    if (menuElement?.contains(target) || menuButton?.contains(target)) return;
    closeMenu(false);
  }

  async function togglePause() {
    if (isPausing || !canToggle) return;
    isPausing = true;
    try {
      if (watcher.state === 'active') {
        await pauseWatcher(watcher.id);
        showStatus('Watcher paused', 'success');
      } else {
        await resumeWatcher(watcher.id);
        showStatus('Watcher resumed', 'success');
      }
    } catch (error: any) {
      console.error('Failed to toggle watcher state:', error);
      showStatus(`Failed to change watcher state: ${errorDetail(error, 'Unknown error')}`, 'error', 5000);
    } finally {
      isPausing = false;
    }
  }

  async function triggerManually() {
    if (isTriggering || !canRun) return;
    isTriggering = true;
    try {
      const response = await api.post(`/api/watchers/${watcher.id}/trigger`, null);
      if (response.data.timer_mode) {
        showStatus(
          response.data.success
            ? `Timer actions executed: ${response.data.message || 'Success'}`
            : `Timer execution failed: ${response.data.message || 'Unknown error'}`,
          response.data.success ? 'success' : 'error',
          5000,
        );
      } else {
        showStatus(
          response.data.matches ? 'Pattern matched and actions executed' : 'No pattern matches found',
          response.data.matches ? 'success' : 'neutral',
        );
      }
      if (response.data.matches || response.data.timer_mode) {
        dispatch('refresh', { scope: 'events' });
      }
    } catch (error: any) {
      console.error('Failed to trigger watcher:', error);
      const fallback =
        error?.response?.status === 404
          ? 'Watcher not found'
          : error?.response?.status === 400
            ? 'Watcher not active'
            : 'Failed to trigger';
      showStatus(errorDetail(error, fallback), 'error', 5000);
    } finally {
      isTriggering = false;
    }
  }

  async function discoverArrayTasks() {
    if (isDiscoveringTasks) return;
    isDiscoveringTasks = true;
    try {
      const response = await api.post(`/api/watchers/${watcher.id}/discover-array-tasks`);
      if (response.data.success) {
        const newTasks = response.data.new_tasks_discovered || 0;
        const total = response.data.total_discovered || 0;
        const expected = response.data.expected_tasks || '?';
        showStatus(
          newTasks > 0
            ? `Discovered ${newTasks} new task(s) (${total}/${expected} total)`
            : `No new tasks found (${total}/${expected} discovered)`,
          newTasks > 0 ? 'success' : 'neutral',
          5000,
        );
        dispatch('refresh', { scope: 'all' });
      } else {
        showStatus(response.data.message || 'Not an array template', 'neutral', 5000);
      }
    } catch (error) {
      console.error('Failed to discover array tasks:', error);
      showStatus('Failed to discover tasks', 'error', 5000);
    } finally {
      isDiscoveringTasks = false;
    }
  }

  async function deleteWatcher() {
    if (isDeleting) return;
    if (!confirm(`Are you sure you want to delete the watcher "${watcher.name}"?`)) return;
    isDeleting = true;
    try {
      await removeWatcher(watcher.id);
      dispatch('refresh', { scope: 'all' });
    } catch (error: any) {
      console.error('Failed to delete watcher:', error);
      showStatus(errorDetail(error, 'Failed to delete watcher'), 'error', 5000);
    } finally {
      isDeleting = false;
    }
  }

  function copyWatcher() {
    const watcherConfig = {
      name: watcher.name,
      pattern: watcher.pattern,
      captures: watcher.captures || [],
      interval: watcher.interval_seconds,
      condition: watcher.condition,
      actions: watcher.actions || [],
      timer_mode_enabled: watcher.timer_mode_enabled || false,
      timer_interval_seconds: watcher.timer_interval_seconds || 30,
      job_id: watcher.job_id,
      hostname: watcher.hostname,
    };
    try {
      localStorage.setItem('copiedWatcher', JSON.stringify(watcherConfig));
    } catch {
      // Storage is only a convenience backup for the copy workflow.
    }
    dispatch('copy', watcherConfig);
  }

  function navigateToJob() {
    navigationActions.setPreviousRoute($location);
    push(`/jobs/${encodeURIComponent(watcher.job_id)}/${watcher.hostname}`);
  }

  function handleDetailChange() {
    dispatch('refresh', { scope: 'all' });
    showDetailDialog = false;
  }
</script>

<svelte:window
  onpointerdown={handleWindowPointer}
  onresize={() => closeMenu(false)}
/>

<div
  id={'watcher-card-' + watcher.id}
  class="watcher-row"
  class:selected
  data-state={watcher.state}
>
  <span class="w-dot" title={watcher.state} aria-hidden="true"></span>

  <div class="w-main">
    <button
      type="button"
      class="w-open"
      aria-pressed={selected}
      aria-label={`Show activity for ${watcher.name}, job ${watcher.job_id} on ${watcher.hostname}, ${watcher.state}`}
      title={watcher.name}
      onclick={inspect}
    >
      {watcher.name}
    </button>
    <span class="w-sub" title={[`#${watcher.job_id}`, watcher.hostname, jobName].filter(Boolean).join(' · ')}>
      <span class="mono">#{watcher.job_id}</span> · {watcher.hostname}{jobName ? ` · ${jobName}` : ''}
    </span>
  </div>

  <span class="w-job" title={[`#${watcher.job_id}`, jobName, watcher.hostname].filter(Boolean).join(' · ')}>
    <span class="mono">#{watcher.job_id}</span>
    <small>{watcher.hostname}{jobName ? ` · ${jobName}` : ''}</small>
  </span>

  <span
    class="w-trigger"
    class:mono={trigger.mono}
    title={[trigger.title, actionSummary ? `Actions: ${actionSummary}` : ''].filter(Boolean).join('\n')}
  >{trigger.label}</span>

  <span class="w-count" title={`${watcher.trigger_count} trigger${watcher.trigger_count === 1 ? '' : 's'}`}>
    {watcher.trigger_count.toLocaleString()}
  </span>

  <span class="w-interval" title={watcher.timer_mode_enabled ? 'Timer interval' : 'Check interval'}>
    {formatInterval(intervalSeconds)}
  </span>

  <time class="w-last" datetime={lastActivity || undefined} title={formatAbsolute(lastActivity)}>
    {formatRelative(lastActivity)}
  </time>

  <button
    bind:this={menuButton}
    type="button"
    class="relay-icon-button w-menu-button"
    aria-label={`Actions for ${watcher.name}`}
    title="Actions"
    aria-haspopup="menu"
    aria-expanded={menuOpen}
    onclick={() => (menuOpen ? closeMenu() : void openMenu())}
  >
    <MoreHorizontal size={16} />
  </button>

  {#if statusMessage}
    <div class="w-status" data-tone={statusTone} role="status">{statusMessage}</div>
  {/if}
</div>

{#if menuOpen}
  <div use:portal={{ zIndex: 60 }}>
    <div
      bind:this={menuElement}
      class="w-menu"
      role="menu"
      tabindex="-1"
      aria-label={`Actions for ${watcher.name}`}
      style={`top:${menuPosition.top}px;right:${menuPosition.right}px`}
      onkeydown={handleMenuKeydown}
    >
      {#if canRun}
        <button type="button" role="menuitem" disabled={isTriggering} onclick={() => runFromMenu(triggerManually)}>
          <Play size={14} />
          {isTriggering ? 'Running…' : 'Run now'}
        </button>
      {/if}
      {#if canToggle}
        <button type="button" role="menuitem" disabled={isPausing} onclick={() => runFromMenu(togglePause)}>
          {#if watcher.state === 'active'}
            <Pause size={14} />
            Pause
          {:else}
            <Play size={14} />
            Resume
          {/if}
        </button>
      {/if}
      <button type="button" role="menuitem" onclick={() => runFromMenu(() => { showDetailDialog = true; })}>
        <Pencil size={14} />
        Edit…
      </button>
      <button type="button" role="menuitem" onclick={() => runFromMenu(copyWatcher)}>
        <Copy size={14} />
        Copy to jobs…
      </button>
      {#if watcher.is_array_template}
        <button type="button" role="menuitem" disabled={isDiscoveringTasks} onclick={() => runFromMenu(discoverArrayTasks)}>
          <Search size={14} />
          Discover array tasks
        </button>
      {/if}
      <button type="button" role="menuitem" onclick={() => runFromMenu(navigateToJob)}>
        <ExternalLink size={14} />
        Open job
      </button>
      <div class="w-menu-separator" role="separator"></div>
      <button type="button" role="menuitem" class="danger" disabled={isDeleting} onclick={() => runFromMenu(deleteWatcher)}>
        <Trash2 size={14} />
        Delete…
      </button>
    </div>
  </div>
{/if}

{#if showDetailDialog}
  <div use:portal>
    <WatcherDetailDialog
      {watcher}
      jobId={watcher.job_id}
      hostname={watcher.hostname}
      on:close={() => (showDetailDialog = false)}
      on:updated={handleDetailChange}
      on:deleted={handleDetailChange}
    />
  </div>
{/if}

<style>
  /* Columns come from --watcher-cols, set by the list container per width.
     Cell visibility below mirrors the same container breakpoints (720px / 520px) in WatchersPage. */
  .watcher-row {
    display: grid;
    grid-template-columns: var(
      --watcher-cols,
      10px minmax(0, 2fr) minmax(0, 1.1fr) minmax(0, 1.3fr) 44px 44px 64px 30px
    );
    align-items: center;
    gap: 12px;
    min-height: 44px;
    padding: 4px 6px 4px 14px;
    border-bottom: 1px solid var(--border-soft);
    position: relative;
    font-size: 0.8125rem;
    transition: background var(--motion-state);
  }

  .watcher-row:last-child {
    border-bottom: 0;
  }

  .watcher-row:hover {
    background: var(--hover);
  }

  .watcher-row.selected {
    background: var(--accent-soft);
  }

  .watcher-row.selected::before {
    content: '';
    position: absolute;
    top: 8px;
    bottom: 8px;
    left: 0;
    width: 3px;
    border-radius: 0 4px 4px 0;
    background: var(--accent);
  }

  .w-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--muted-foreground);
  }

  [data-state='active'] .w-dot {
    background: var(--success);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--success) 18%, transparent);
  }

  [data-state='paused'] .w-dot {
    background: transparent;
    border: 2px solid var(--warning);
  }

  [data-state='static'] .w-dot {
    background: var(--accent);
  }

  [data-state='failed'] .w-dot {
    background: var(--error);
  }

  .w-main {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .w-open {
    display: block;
    padding: 0;
    border: 0;
    background: none;
    color: var(--foreground);
    font: inherit;
    font-weight: 550;
    text-align: left;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
  }

  /* Stretch the name button over the whole row so any cell selects it. */
  .w-open::after {
    content: '';
    position: absolute;
    inset: 0;
  }

  .w-open:focus-visible {
    outline: none;
  }

  .watcher-row:has(.w-open:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  .w-sub,
  .w-job small,
  .w-interval,
  .w-last {
    color: var(--muted-foreground);
    font-size: 0.75rem;
  }

  .w-sub {
    display: none;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .w-job {
    display: flex;
    flex-direction: column;
    min-width: 0;
    line-height: 1.25;
  }

  .w-job .mono {
    font-size: 0.75rem;
    color: var(--foreground);
  }

  .w-job small,
  .w-trigger {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .w-trigger {
    min-width: 0;
    color: var(--foreground);
  }

  .w-trigger.mono {
    font-size: 0.75rem;
  }

  .w-count,
  .w-interval,
  .w-last {
    text-align: right;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }

  .w-menu-button {
    position: relative;
    z-index: 1;
    width: 30px;
    height: 30px;
  }

  .w-status {
    grid-column: 2 / -1;
    padding: 2px 0 6px;
    font-size: 0.75rem;
    color: var(--muted-foreground);
    overflow-wrap: anywhere;
  }

  .w-status[data-tone='success'] {
    color: var(--success);
  }

  .w-status[data-tone='error'] {
    color: var(--error);
  }

  @container watcher-list (max-width: 720px) {
    .w-job,
    .w-interval {
      display: none;
    }
    .w-sub {
      display: block;
    }
  }

  @container watcher-list (max-width: 520px) {
    .w-trigger,
    .w-count {
      display: none;
    }
    .watcher-row {
      min-height: 52px;
    }
    /* Narrow rows have room for two lines of name rather than a hard cut. */
    .w-open {
      display: -webkit-box;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
      line-clamp: 2;
      white-space: normal;
      overflow-wrap: anywhere;
      line-height: 1.3;
    }
  }

  .w-menu {
    position: fixed;
    min-width: 188px;
    padding: 5px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--card);
    color: var(--foreground);
    box-shadow: 0 12px 32px color-mix(in srgb, var(--foreground) 16%, transparent);
  }

  .w-menu button {
    display: flex;
    align-items: center;
    gap: 9px;
    width: 100%;
    padding: 7px 9px;
    border: 0;
    border-radius: 7px;
    background: none;
    color: inherit;
    font-size: 0.8125rem;
    text-align: left;
    white-space: nowrap;
    cursor: pointer;
  }

  .w-menu button:hover:not(:disabled),
  .w-menu button:focus-visible {
    background: var(--hover);
    outline: none;
  }

  .w-menu button:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .w-menu button :global(svg) {
    color: var(--muted-foreground);
    flex-shrink: 0;
  }

  .w-menu button.danger,
  .w-menu button.danger :global(svg) {
    color: var(--error);
  }

  .w-menu button.danger:hover:not(:disabled),
  .w-menu button.danger:focus-visible {
    background: var(--error-bg);
  }

  .w-menu-separator {
    height: 1px;
    margin: 5px 4px;
    background: var(--border);
  }
</style>
