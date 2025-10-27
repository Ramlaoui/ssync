<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Watcher } from '../types/watchers';
  import { pauseWatcher, resumeWatcher } from '../stores/watchers';
  
  interface Props {
    watchers?: Watcher[];
    loading?: boolean;
  }

  let { watchers = [], loading = false }: Props = $props();
  
  const dispatch = createEventDispatcher();
  
  // Group watchers by job
  let groupedWatchers = $derived(watchers.reduce((acc, watcher) => {
    if (!acc[watcher.job_id]) {
      acc[watcher.job_id] = [];
    }
    acc[watcher.job_id].push(watcher);
    return acc;
  }, {} as Record<string, Watcher[]>));
  
  async function handlePause(watcher: Watcher) {
    try {
      await pauseWatcher(watcher.id);
    } catch (error) {
      console.error('Failed to pause watcher:', error);
    }
  }
  
  async function handleResume(watcher: Watcher) {
    try {
      await resumeWatcher(watcher.id);
    } catch (error) {
      console.error('Failed to resume watcher:', error);
    }
  }
  
  function handleViewDetails(watcher: Watcher) {
    dispatch('viewDetails', watcher);
  }
  
  function getStateColor(state: string): string {
    switch (state) {
      case 'active': return 'var(--success)';
      case 'paused': return 'var(--warning)';
      case 'completed': return 'var(--info)';
      case 'failed': return 'var(--error)';
      default: return 'var(--muted-foreground)';
    }
  }
  
  function getStateIcon(state: string): string {
    switch (state) {
      case 'active': return '▶️';
      case 'paused': return '⏸️';
      case 'completed': return '✅';
      case 'failed': return '❌';
      default: return '⏳';
    }
  }
</script>

{#if loading}
  <div class="loading">
    <div class="spinner"></div>
    <p>Loading watchers...</p>
  </div>
{:else if watchers.length === 0}
  <div class="empty-state">
    <p>No watchers found</p>
    <small>Watchers will appear here when jobs with watcher directives are submitted</small>
  </div>
{:else}
  <div class="watcher-groups">
    {#each Object.entries(groupedWatchers) as [jobId, jobWatchers]}
      <div class="job-group">
        <div class="job-header">
          <h3>Job {jobId}</h3>
          <span class="watcher-count">{jobWatchers.length} watcher{jobWatchers.length !== 1 ? 's' : ''}</span>
        </div>
        
        <div class="watcher-cards">
          {#each jobWatchers as watcher}
            <div class="watcher-card">
              <div class="watcher-header">
                <div class="watcher-name">
                  <span class="state-icon" title={watcher.state}>
                    {getStateIcon(watcher.state)}
                  </span>
                  {watcher.name}
                </div>
                <div class="watcher-actions">
                  {#if watcher.state === 'active'}
                    <button 
                      class="action-btn pause"
                      onclick={() => handlePause(watcher)}
                      title="Pause watcher"
                    >
                      ⏸️
                    </button>
                  {:else if watcher.state === 'paused'}
                    <button 
                      class="action-btn resume"
                      onclick={() => handleResume(watcher)}
                      title="Resume watcher"
                    >
                      ▶️
                    </button>
                  {/if}
                  <button 
                    class="action-btn details"
                    onclick={() => handleViewDetails(watcher)}
                    title="View details"
                  >
                    📊
                  </button>
                </div>
              </div>
              
              <div class="watcher-body">
                <div class="pattern">
                  <label>Pattern:</label>
                  <code>{watcher.pattern}</code>
                </div>
                
                <div class="stats">
                  <div class="stat">
                    <label>Host:</label>
                    <span>{watcher.hostname}</span>
                  </div>
                  <div class="stat">
                    <label>Triggers:</label>
                    <span>{watcher.trigger_count}</span>
                  </div>
                  <div class="stat">
                    <label>Interval:</label>
                    <span>{watcher.interval_seconds}s</span>
                  </div>
                </div>
                
                {#if watcher.actions && watcher.actions.length > 0}
                  <div class="actions">
                    <label>Actions:</label>
                    <div class="action-list">
                      {#each watcher.actions as action}
                        <span class="action-badge">{action.type}</span>
                      {/each}
                    </div>
                  </div>
                {/if}
                
                {#if watcher.last_check}
                  <div class="last-check">
                    <label>Last checked:</label>
                    <span>{new Date(watcher.last_check).toLocaleString()}</span>
                  </div>
                {/if}
              </div>
              
              <div 
                class="state-indicator"
                style="background-color: {getStateColor(watcher.state)}"
              ></div>
            </div>
          {/each}
        </div>
      </div>
    {/each}
  </div>
{/if}

<style>
  .loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    color: var(--muted-foreground);
  }
  
  .spinner {
    width: 40px;
    height: 40px;
    border: 3px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  .empty-state {
    text-align: center;
    padding: 3rem;
    color: var(--muted-foreground);
  }
  
  .empty-state p {
    margin: 0 0 0.5rem 0;
    font-size: 1.1rem;
  }
  
  .empty-state small {
    font-size: 0.9rem;
  }
  
  .watcher-groups {
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }
  
  .job-group {
    background: var(--secondary);
    border-radius: 8px;
    padding: 1.5rem;
  }
  
  .job-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
  }
  
  .job-header h3 {
    margin: 0;
    color: var(--foreground);
    font-size: 1.1rem;
  }
  
  .watcher-count {
    background: var(--accent);
    color: white;
    padding: 0.25rem 0.75rem;
    border-radius: 12px;
    font-size: 0.85rem;
  }
  
  .watcher-cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
    gap: 1rem;
  }
  
  .watcher-card {
    background: var(--background);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s, box-shadow 0.2s;
  }
  
  .watcher-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }
  
  .state-indicator {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
  }
  
  .watcher-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .watcher-name {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 500;
    color: var(--foreground);
  }
  
  .state-icon {
    font-size: 1.2rem;
  }
  
  .watcher-actions {
    display: flex;
    gap: 0.25rem;
  }
  
  .action-btn {
    background: none;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    cursor: pointer;
    font-size: 1rem;
    transition: background 0.2s;
  }
  
  .action-btn:hover {
    background: var(--secondary);
  }
  
  .watcher-body {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .pattern {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .pattern label,
  .stats label,
  .actions label,
  .last-check label {
    color: var(--muted-foreground);
    font-size: 0.85rem;
  }
  
  .pattern code {
    background: var(--secondary);
    padding: 0.5rem;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.85rem;
    word-break: break-all;
  }
  
  .stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.5rem;
  }
  
  .stat {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .stat span {
    color: var(--foreground);
    font-size: 0.9rem;
  }
  
  .actions {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .action-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
  }
  
  .action-badge {
    background: var(--info);
    color: white;
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
  }
  
  .last-check {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    color: var(--muted-foreground);
    font-size: 0.85rem;
  }
  
  @media (max-width: 768px) {
    .watcher-cards {
      grid-template-columns: 1fr;
    }
    
    .stats {
      grid-template-columns: 1fr;
    }
  }
</style>