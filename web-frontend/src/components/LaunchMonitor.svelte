<script lang="ts">
  import { onMount } from 'svelte';
  import { push } from 'svelte-spa-router';
  import {
    AlertTriangle,
    CheckCircle2,
    ChevronDown,
    ChevronUp,
    ExternalLink,
    Loader2,
    Pencil,
    RotateCcw,
    Terminal,
    X,
    XCircle,
  } from 'lucide-svelte';
  import {
    launchMonitor,
    launchMonitorItems,
    type LaunchMonitorItem,
  } from '../stores/launchMonitor';

  let collapsed = $state(true);
  let expandedLogs = $state(new Set<string>());
  let relaunching = $state(new Set<string>());

  let visibleItems = $derived($launchMonitorItems.filter((item) => !item.dismissed));
  let activeCount = $derived(
    visibleItems.filter((item) => !item.terminal && item.status !== 'lost').length,
  );
  let terminalCount = $derived(
    visibleItems.filter((item) => item.terminal || item.status === 'lost').length,
  );
  let latestItem = $derived(visibleItems[0]);

  $effect(() => {
    if (activeCount > 0) {
      collapsed = false;
    }
  });

  onMount(() => {
    void launchMonitor.recoverActiveLaunches();
  });

  function titleFor(item: LaunchMonitorItem): string {
    return item.jobName || item.request.job_name || 'Launch';
  }

  function subtitleFor(item: LaunchMonitorItem): string {
    const parts = [item.host];
    if (item.sourceDir) {
      parts.push(item.sourceDir);
    }
    if (item.attempt > 1) {
      parts.push(`attempt ${item.attempt}`);
    }
    return parts.filter(Boolean).join(' · ');
  }

  function statusLabel(item: LaunchMonitorItem): string {
    if (item.status === 'queued') return 'Queued';
    if (item.status === 'launching') return item.stage || 'Launching';
    if (item.status === 'success') return 'Submitted';
    if (item.status === 'lost') return 'Disconnected';
    return 'Failed';
  }

  function toggleLogs(clientId: string): void {
    const next = new Set(expandedLogs);
    if (next.has(clientId)) {
      next.delete(clientId);
    } else {
      next.add(clientId);
    }
    expandedLogs = next;
  }

  async function relaunchItem(item: LaunchMonitorItem): Promise<void> {
    const next = new Set(relaunching);
    next.add(item.clientId);
    relaunching = next;
    try {
      await launchMonitor.relaunch(item.clientId);
    } finally {
      const done = new Set(relaunching);
      done.delete(item.clientId);
      relaunching = done;
    }
  }

  function viewJob(item: LaunchMonitorItem): void {
    if (!item.jobId) {
      return;
    }
    void push(`/jobs/${encodeURIComponent(item.jobId)}/${item.host}`);
  }

  function editItem(item: LaunchMonitorItem): void {
    if (launchMonitor.prepareEdit(item.clientId)) {
      void push('/launch');
    }
  }
</script>

{#if visibleItems.length > 0}
  <section class="launch-monitor" aria-label="Launch monitor">
    {#if collapsed}
      <button
        type="button"
        class="monitor-bar"
        onclick={() => (collapsed = false)}
        aria-label="Expand launch monitor"
      >
        <span class="bar-icon" class:active={activeCount > 0}>
          {#if activeCount > 0}
            <Loader2 size={16} class="launch-monitor-spin" />
          {:else if latestItem?.status === 'success'}
            <CheckCircle2 size={16} />
          {:else}
            <XCircle size={16} />
          {/if}
        </span>
        <span class="bar-copy">
          <span class="bar-title">
            {activeCount > 0 ? `${activeCount} launch${activeCount === 1 ? '' : 'es'} running` : 'Launches'}
          </span>
          <span class="bar-message">{latestItem?.message || statusLabel(latestItem)}</span>
        </span>
        <ChevronUp size={16} />
      </button>
    {:else}
      <div class="monitor-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">Launches</div>
            <div class="panel-subtitle">
              {activeCount} active · {terminalCount} finished
            </div>
          </div>
          <div class="header-actions">
            {#if activeCount === 0 && terminalCount > 0}
              <button
                type="button"
                class="icon-button"
                onclick={() => launchMonitor.clearTerminal()}
                title="Clear finished launches"
                aria-label="Clear finished launches"
              >
                <X size={16} />
              </button>
            {/if}
            <button
              type="button"
              class="icon-button"
              onclick={() => (collapsed = true)}
              title="Collapse launch monitor"
              aria-label="Collapse launch monitor"
            >
              <ChevronDown size={16} />
            </button>
          </div>
        </div>

        <div class="launch-list">
          {#each visibleItems as item (item.clientId)}
            <article class="launch-row" class:failed={item.status === 'error' || item.status === 'lost'}>
              <div class="status-icon" class:running={item.status === 'queued' || item.status === 'launching'} class:success={item.status === 'success'} class:failed={item.status === 'error' || item.status === 'lost'}>
                {#if item.status === 'queued' || item.status === 'launching'}
                  <Loader2 size={16} class="launch-monitor-spin" />
                {:else if item.status === 'success'}
                  <CheckCircle2 size={16} />
                {:else if item.status === 'lost'}
                  <AlertTriangle size={16} />
                {:else}
                  <XCircle size={16} />
                {/if}
              </div>

              <div class="launch-content">
                <div class="launch-topline">
                  <div class="launch-title" title={titleFor(item)}>{titleFor(item)}</div>
                  <span class="status-pill">{statusLabel(item)}</span>
                </div>
                <div class="launch-subtitle" title={subtitleFor(item)}>{subtitleFor(item)}</div>
                <div class="launch-message" title={item.message}>{item.message || 'Waiting for launch progress...'}</div>

                {#if expandedLogs.has(item.clientId) && item.logs.length > 0}
                  <pre class="launch-logs">{item.logs.join('\n')}</pre>
                {/if}
              </div>

              <div class="row-actions">
                {#if item.logs.length > 0}
                  <button
                    type="button"
                    class="icon-button"
                    onclick={() => toggleLogs(item.clientId)}
                    title="Toggle launch logs"
                    aria-label="Toggle launch logs"
                  >
                    <Terminal size={15} />
                  </button>
                {/if}
                {#if item.status === 'success' && item.jobId}
                  <button
                    type="button"
                    class="icon-button"
                    onclick={() => viewJob(item)}
                    title="Open launched job"
                    aria-label="Open launched job"
                  >
                    <ExternalLink size={15} />
                  </button>
                {/if}
                {#if item.status === 'error' || item.status === 'lost'}
                  <button
                    type="button"
                    class="icon-button"
                    onclick={() => editItem(item)}
                    title="Edit and relaunch"
                    aria-label="Edit and relaunch"
                  >
                    <Pencil size={15} />
                  </button>
                  <button
                    type="button"
                    class="icon-button"
                    disabled={relaunching.has(item.clientId)}
                    onclick={() => relaunchItem(item)}
                    title="Relaunch with the same request"
                    aria-label="Relaunch with the same request"
                  >
                    <RotateCcw
                      size={15}
                      class={relaunching.has(item.clientId) ? 'launch-monitor-spin' : ''}
                    />
                  </button>
                {/if}
                {#if item.terminal || item.status === 'lost'}
                  <button
                    type="button"
                    class="icon-button"
                    onclick={() => launchMonitor.dismiss(item.clientId)}
                    title="Dismiss launch"
                    aria-label="Dismiss launch"
                  >
                    <X size={15} />
                  </button>
                {/if}
              </div>
            </article>
          {/each}
        </div>
      </div>
    {/if}
  </section>
{/if}

<style>
  .launch-monitor {
    position: fixed;
    left: 50%;
    bottom: 1rem;
    transform: translateX(-50%);
    z-index: 80;
    width: min(760px, calc(100vw - 2rem));
    color: var(--foreground);
    --launch-monitor-icon-bg: var(--secondary);
    --launch-monitor-console-bg: #f8fafc;
    --launch-monitor-console-fg: #111827;
    --launch-monitor-running: #1d4ed8;
    --launch-monitor-running-bg: rgba(37, 99, 235, 0.14);
    --launch-monitor-success: #15803d;
    --launch-monitor-success-bg: rgba(22, 163, 74, 0.14);
    --launch-monitor-failed: #dc2626;
    --launch-monitor-failed-bg: rgba(220, 38, 38, 0.14);
  }

  :global(.dark) .launch-monitor {
    --launch-monitor-icon-bg: #171717;
    --launch-monitor-console-bg: #111827;
    --launch-monitor-console-fg: #e5e7eb;
    --launch-monitor-running: #60a5fa;
    --launch-monitor-running-bg: rgba(96, 165, 250, 0.18);
    --launch-monitor-success: #34d399;
    --launch-monitor-success-bg: rgba(52, 211, 153, 0.16);
    --launch-monitor-failed: #f87171;
    --launch-monitor-failed-bg: rgba(248, 113, 113, 0.18);
  }

  .monitor-bar,
  .monitor-panel {
    border: 1px solid var(--border);
    background: color-mix(in srgb, var(--background) 94%, transparent);
    box-shadow: 0 16px 38px rgba(15, 23, 42, 0.18);
    backdrop-filter: blur(14px);
  }

  .monitor-bar {
    width: 100%;
    min-height: 52px;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 0.75rem;
    padding: 0.65rem 0.8rem;
    border-radius: 8px;
    text-align: left;
  }

  .bar-icon,
  .status-icon {
    width: 28px;
    height: 28px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 999px;
    background: var(--launch-monitor-icon-bg);
    color: var(--muted-foreground);
    flex-shrink: 0;
  }

  .bar-icon.active,
  .status-icon.running {
    color: var(--launch-monitor-running);
    background: var(--launch-monitor-running-bg);
  }

  .status-icon.success {
    color: var(--launch-monitor-success);
    background: var(--launch-monitor-success-bg);
  }

  .status-icon.failed {
    color: var(--launch-monitor-failed);
    background: var(--launch-monitor-failed-bg);
  }

  .bar-copy {
    display: grid;
    min-width: 0;
    gap: 0.1rem;
  }

  .bar-title,
  .panel-title,
  .launch-title {
    font-weight: 600;
  }

  .bar-title {
    font-size: 0.9rem;
  }

  .bar-message,
  .panel-subtitle,
  .launch-subtitle,
  .launch-message {
    color: var(--muted-foreground);
  }

  .bar-message {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.76rem;
  }

  .monitor-panel {
    border-radius: 8px;
    overflow: hidden;
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem 0.85rem;
    border-bottom: 1px solid var(--border);
  }

  .panel-title {
    font-size: 0.94rem;
  }

  .panel-subtitle {
    font-size: 0.76rem;
  }

  .header-actions,
  .row-actions {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .launch-list {
    max-height: min(52vh, 520px);
    overflow-y: auto;
  }

  .launch-row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 0.65rem;
    padding: 0.75rem 0.85rem;
    border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  }

  .launch-row:last-child {
    border-bottom: 0;
  }

  .launch-content {
    min-width: 0;
    display: grid;
    gap: 0.22rem;
  }

  .launch-topline {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
  }

  .launch-title,
  .launch-subtitle,
  .launch-message {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .launch-title {
    min-width: 0;
    font-size: 0.86rem;
  }

  .launch-subtitle,
  .launch-message {
    font-size: 0.74rem;
  }

  .status-pill {
    flex-shrink: 0;
    max-width: 118px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0.08rem 0.42rem;
    font-size: 0.68rem;
    color: var(--muted-foreground);
  }

  .launch-logs {
    margin-top: 0.4rem;
    max-height: 132px;
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.5rem;
    background: var(--launch-monitor-console-bg);
    color: var(--launch-monitor-console-fg);
    font-size: 0.72rem;
    line-height: 1.35;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .icon-button {
    width: 30px;
    height: 30px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    color: var(--muted-foreground);
    transition:
      background-color 120ms ease,
      color 120ms ease;
  }

  .icon-button:hover:not(:disabled) {
    background: var(--secondary);
    color: var(--foreground);
  }

  .icon-button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  :global(.launch-monitor-spin) {
    animation: launch-monitor-spin 1s linear infinite;
  }

  @keyframes launch-monitor-spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (max-width: 640px) {
    .launch-monitor {
      bottom: 0.5rem;
      width: calc(100vw - 1rem);
    }

    .launch-row {
      grid-template-columns: auto minmax(0, 1fr);
    }

    .row-actions {
      grid-column: 2;
      justify-content: flex-start;
    }
  }
</style>
