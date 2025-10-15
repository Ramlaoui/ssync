<script lang="ts">
  import type { WatcherStats } from '../types/watchers';
  
  interface Props {
    stats?: WatcherStats | null;
    loading?: boolean;
  }

  let { stats = null, loading = false }: Props = $props();
  
  function getStateColor(state: string): string {
    switch (state) {
      case 'active': return 'var(--color-success)';
      case 'paused': return 'var(--color-warning)';
      case 'completed': return 'var(--color-info)';
      case 'failed': return 'var(--color-error)';
      case 'pending': return 'var(--color-text-secondary)';
      default: return 'var(--color-text-secondary)';
    }
  }
  
  function calculateSuccessRate(action: { total: number; success: number }): number {
    if (action.total === 0) return 0;
    return Math.round((action.success / action.total) * 100);
  }
</script>

{#if loading}
  <div class="loading">
    <div class="spinner"></div>
    <p>Loading statistics...</p>
  </div>
{:else if !stats}
  <div class="empty-state">
    <p>No statistics available</p>
  </div>
{:else}
  <div class="stats-container">
    <!-- Overview Cards -->
    <div class="stats-overview">
      <div class="stat-card">
        <div class="stat-value">{stats.total_watchers}</div>
        <div class="stat-label">Total Watchers</div>
      </div>
      
      <div class="stat-card">
        <div class="stat-value">{stats.total_events}</div>
        <div class="stat-label">Total Events</div>
      </div>
      
      <div class="stat-card">
        <div class="stat-value">{stats.events_last_hour}</div>
        <div class="stat-label">Events (Last Hour)</div>
      </div>
      
      <div class="stat-card">
        <div class="stat-value">
          {stats.watchers_by_state.active || 0}
        </div>
        <div class="stat-label">Active Watchers</div>
      </div>
    </div>
    
    <!-- Watchers by State -->
    <div class="stats-section">
      <h3>Watchers by State</h3>
      <div class="state-distribution">
        {#each Object.entries(stats.watchers_by_state) as [state, count]}
          <div class="state-item">
            <div class="state-bar-container">
              <div 
                class="state-bar"
                style="width: {(count / stats.total_watchers) * 100}%; background-color: {getStateColor(state)}"
              ></div>
            </div>
            <div class="state-info">
              <span class="state-name">{state}</span>
              <span class="state-count">{count}</span>
            </div>
          </div>
        {/each}
      </div>
    </div>
    
    <!-- Events by Action Type -->
    {#if Object.keys(stats.events_by_action).length > 0}
      <div class="stats-section">
        <h3>Events by Action Type</h3>
        <div class="action-stats">
          {#each Object.entries(stats.events_by_action) as [actionType, actionStats]}
            <div class="action-card">
              <div class="action-header">
                <span class="action-type">{actionType}</span>
                <span class="action-total">{actionStats.total} events</span>
              </div>
              
              <div class="action-metrics">
                <div class="metric">
                  <span class="metric-label">Success:</span>
                  <span class="metric-value success">{actionStats.success}</span>
                </div>
                <div class="metric">
                  <span class="metric-label">Failed:</span>
                  <span class="metric-value error">{actionStats.failed}</span>
                </div>
                <div class="metric">
                  <span class="metric-label">Rate:</span>
                  <span class="metric-value">{calculateSuccessRate(actionStats)}%</span>
                </div>
              </div>
              
              <div class="success-bar">
                <div 
                  class="success-fill"
                  style="width: {calculateSuccessRate(actionStats)}%"
                ></div>
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/if}
    
    <!-- Top Triggered Watchers -->
    {#if stats.top_watchers.length > 0}
      <div class="stats-section">
        <h3>Most Active Watchers</h3>
        <div class="top-watchers">
          {#each stats.top_watchers as watcher, index}
            <div class="top-watcher-item">
              <div class="rank">#{index + 1}</div>
              <div class="watcher-info">
                <div class="watcher-name">{watcher.name}</div>
                <div class="watcher-job">Job {watcher.job_id}</div>
              </div>
              <div class="event-count">
                <span class="count">{watcher.event_count}</span>
                <span class="label">events</span>
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </div>
{/if}

<style>
  .loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    color: var(--color-text-secondary);
  }
  
  .spinner {
    width: 40px;
    height: 40px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
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
    color: var(--color-text-secondary);
  }
  
  .stats-container {
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }
  
  /* Overview Cards */
  .stats-overview {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
  }
  
  .stat-card {
    background: var(--color-bg-secondary);
    border-radius: 8px;
    padding: 1.5rem;
    text-align: center;
  }
  
  .stat-value {
    font-size: 2rem;
    font-weight: 600;
    color: var(--color-primary);
    margin-bottom: 0.5rem;
  }
  
  .stat-label {
    color: var(--color-text-secondary);
    font-size: 0.9rem;
  }
  
  /* Stats Sections */
  .stats-section {
    background: var(--color-bg-secondary);
    border-radius: 8px;
    padding: 1.5rem;
  }
  
  .stats-section h3 {
    margin: 0 0 1rem 0;
    color: var(--color-text-primary);
    font-size: 1.1rem;
  }
  
  /* State Distribution */
  .state-distribution {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .state-item {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .state-bar-container {
    height: 24px;
    background: var(--color-bg-primary);
    border-radius: 4px;
    overflow: hidden;
  }
  
  .state-bar {
    height: 100%;
    transition: width 0.3s ease;
  }
  
  .state-info {
    display: flex;
    justify-content: space-between;
    font-size: 0.85rem;
  }
  
  .state-name {
    color: var(--color-text-secondary);
    text-transform: capitalize;
  }
  
  .state-count {
    color: var(--color-text-primary);
    font-weight: 500;
  }
  
  /* Action Stats */
  .action-stats {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 1rem;
  }
  
  .action-card {
    background: var(--color-bg-primary);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 1rem;
  }
  
  .action-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }
  
  .action-type {
    font-weight: 500;
    color: var(--color-text-primary);
  }
  
  .action-total {
    color: var(--color-text-secondary);
    font-size: 0.85rem;
  }
  
  .action-metrics {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.75rem;
  }
  
  .metric {
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  
  .metric-label {
    color: var(--color-text-secondary);
    font-size: 0.75rem;
    margin-bottom: 0.25rem;
  }
  
  .metric-value {
    font-weight: 600;
    font-size: 0.95rem;
  }
  
  .metric-value.success {
    color: var(--color-success);
  }
  
  .metric-value.error {
    color: var(--color-error);
  }
  
  .success-bar {
    height: 4px;
    background: var(--color-bg-secondary);
    border-radius: 2px;
    overflow: hidden;
  }
  
  .success-fill {
    height: 100%;
    background: var(--color-success);
    transition: width 0.3s ease;
  }
  
  /* Top Watchers */
  .top-watchers {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .top-watcher-item {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem;
    background: var(--color-bg-primary);
    border: 1px solid var(--color-border);
    border-radius: 8px;
  }
  
  .rank {
    font-size: 1.2rem;
    font-weight: 600;
    color: var(--color-primary);
    width: 40px;
    text-align: center;
  }
  
  .watcher-info {
    flex: 1;
  }
  
  .watcher-name {
    font-weight: 500;
    color: var(--color-text-primary);
  }
  
  .watcher-job {
    color: var(--color-text-secondary);
    font-size: 0.85rem;
  }
  
  .event-count {
    text-align: center;
  }
  
  .event-count .count {
    display: block;
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--color-primary);
  }
  
  .event-count .label {
    color: var(--color-text-secondary);
    font-size: 0.75rem;
  }
  
  @media (max-width: 768px) {
    .stats-overview {
      grid-template-columns: 1fr;
    }
    
    .action-stats {
      grid-template-columns: 1fr;
    }
  }
</style>