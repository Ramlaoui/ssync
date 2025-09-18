<script lang="ts">
  import { Activity, Eye } from 'lucide-svelte';
  import { createEventDispatcher } from 'svelte';
  import WatcherCard from './WatcherCard.svelte';
  import type { Watcher } from '../types/watchers';

  export let watchers: Watcher[] = [];
  export let selectedJobId: string | null = null;
  export let selectedJobWatchers: Watcher[] = [];

  const dispatch = createEventDispatcher();

  $: activeWatchers = watchers.filter(w => w.state === 'active');
  $: pausedWatchers = watchers.filter(w => w.state === 'paused');

  function handleRefresh() {
    dispatch('refresh');
  }
</script>

<div class="watchers-section">
  <div class="watchers-header">
    <div class="header-content">
      <div class="header-left">
        <h3 class="watchers-title">
          <Activity class="header-icon" />
          Watchers
        </h3>
      </div>
      <div class="header-actions">
        <div class="status-indicators">
          {#if activeWatchers.length > 0}
            <span class="status-indicator active">
              <span class="status-dot active"></span>
              {activeWatchers.length} active
            </span>
          {/if}
          {#if pausedWatchers.length > 0}
            <span class="status-indicator paused">
              <span class="status-dot paused"></span>
              {pausedWatchers.length} paused
            </span>
          {/if}
        </div>
      </div>
    </div>
  </div>

  <div class="watchers-content">
    {#if selectedJobId && selectedJobWatchers.length > 0}
      <div class="selected-job-watchers">
        <div class="watcher-group">
          <h4 class="group-title highlighted">Watchers for Job #{selectedJobId}</h4>
          <div class="watchers-list">
            {#each selectedJobWatchers as watcher (watcher.id)}
              <WatcherCard {watcher} showJobLink={false} on:refresh={handleRefresh} />
            {/each}
          </div>
        </div>
        <div class="divider-line"></div>
      </div>
    {/if}

    {#if activeWatchers.length > 0}
      <div class="watcher-group">
        <h4 class="group-title">Active ({activeWatchers.length})</h4>
        <div class="watchers-list">
          {#each activeWatchers as watcher (watcher.id)}
            <WatcherCard
              {watcher}
              showJobLink={true}
              class={selectedJobId && watcher.job_id === selectedJobId ? 'highlighted' : ''}
              on:refresh={handleRefresh}
            />
          {/each}
        </div>
      </div>
    {/if}

    {#if pausedWatchers.length > 0}
      <div class="watcher-group">
        <h4 class="group-title">Paused ({pausedWatchers.length})</h4>
        <div class="watchers-list">
          {#each pausedWatchers as watcher (watcher.id)}
            <WatcherCard
              {watcher}
              showJobLink={true}
              class={selectedJobId && watcher.job_id === selectedJobId ? 'highlighted' : ''}
              on:refresh={handleRefresh}
            />
          {/each}
        </div>
      </div>
    {/if}

    {#if watchers.length === 0}
      <div class="empty-state">
        <Eye class="empty-icon" />
        <p>No watchers configured</p>
        <span class="empty-hint">Watchers monitor your jobs and trigger actions</span>
      </div>
    {/if}
  </div>
</div>

<style>
  .watchers-section {
    flex: 0 0 380px;
    display: flex;
    flex-direction: column;
    background: white;
    position: relative;
    height: calc(100vh - 140px); /* Fixed height: full viewport minus header/margins */
  }

  .watchers-header {
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
    flex-shrink: 0;
    background: white;
  }

  .header-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.25rem;
    gap: 1rem;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    flex: 1;
  }

  .watchers-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: #0f172a;
    letter-spacing: -0.025em;
  }

  .header-icon {
    width: 1.125rem;
    height: 1.125rem;
    color: #6366f1;
  }

  .header-stats {
    display: flex;
    align-items: baseline;
    gap: 0.375rem;
  }

  .stat-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #0f172a;
    line-height: 1;
  }

  .stat-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .status-indicators {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .status-indicator {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.75rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .status-indicator.active {
    color: #059669;
  }

  .status-indicator.paused {
    color: #d97706;
  }

  .status-dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .status-dot.active {
    background: #10b981;
    box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
  }

  .status-dot.paused {
    background: #f59e0b;
    box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2);
  }

  /* Mobile Responsive Design */
  @media (max-width: 768px) {
    .header-content {
      padding: 0.75rem 1rem;
      flex-direction: column;
      align-items: flex-start;
      gap: 0.75rem;
    }

    .header-left {
      width: 100%;
      justify-content: space-between;
      gap: 1rem;
    }

    .watchers-title {
      font-size: 0.875rem;
    }

    .header-icon {
      width: 1rem;
      height: 1rem;
    }

    .stat-value {
      font-size: 1.25rem;
    }

    .stat-label {
      font-size: 0.6875rem;
    }

    .header-actions {
      width: 100%;
      justify-content: flex-start;
    }

    .status-indicators {
      gap: 0.75rem;
    }

    .status-indicator {
      font-size: 0.6875rem;
    }

    .status-dot {
      width: 0.375rem;
      height: 0.375rem;
    }
  }

  @media (max-width: 480px) {
    .header-left {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }

    .header-stats {
      gap: 0.25rem;
    }

    .status-indicators {
      gap: 0.5rem;
      flex-wrap: wrap;
    }
  }

  .watchers-content {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 1rem;
    overscroll-behavior: contain;
    touch-action: pan-y;
    scroll-behavior: smooth;
  }


  .watcher-group {
    margin-bottom: 1.5rem;
  }

  .watcher-group:last-child {
    margin-bottom: 0;
  }

  .group-title {
    margin: 0 0 0.75rem 0;
    font-size: 0.75rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .group-title.highlighted {
    color: #3b82f6;
    background: rgba(59, 130, 246, 0.05);
    padding: 0.375rem 0.75rem;
    border-radius: 0.375rem;
    margin: 0 0 0.75rem 0;
  }

  .watchers-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .selected-job-watchers {
    margin-bottom: 1rem;
  }

  .divider-line {
    height: 1px;
    background: linear-gradient(90deg,
      transparent 0%,
      rgba(59, 130, 246, 0.2) 50%,
      transparent 100%);
    margin: 1rem 0;
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem 1rem;
    text-align: center;
  }

  .empty-icon {
    width: 3rem;
    height: 3rem;
    margin-bottom: 1rem;
    color: #cbd5e1;
  }

  .empty-state p {
    margin: 0;
    font-size: 0.875rem;
    font-weight: 500;
    color: #64748b;
  }

  .empty-hint {
    margin-top: 0.5rem;
    font-size: 0.75rem;
    color: #94a3b8;
  }

  :global(.watcher-card.highlighted) {
    border-color: #3b82f6 !important;
    background: rgba(59, 130, 246, 0.02) !important;
  }
</style>