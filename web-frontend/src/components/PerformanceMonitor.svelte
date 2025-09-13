<script lang="ts">
  import { jobStateManager } from '../lib/JobStateManager';
  import { onMount, onDestroy } from 'svelte';
  
  export let showDetails = false;
  export let position: 'top-right' | 'bottom-right' | 'bottom-left' = 'bottom-left';
  
  const metrics = jobStateManager.getMetrics();
  const connectionStatus = jobStateManager.getConnectionStatus();
  const managerState = jobStateManager.getState();
  
  let refreshInterval: ReturnType<typeof setInterval>;
  
  // Calculate cache hit rate
  $: cacheHitRate = $metrics.cacheHits + $metrics.cacheMisses > 0
    ? (($metrics.cacheHits / ($metrics.cacheHits + $metrics.cacheMisses)) * 100).toFixed(1)
    : '0.0';
  
  // Format numbers
  function formatNumber(num: number): string {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  }
  
  // Format time
  function formatTime(ms: number): string {
    if (ms < 1) return '<1ms';
    if (ms < 1000) return `${ms.toFixed(0)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  }
  
  function resetMetrics() {
    jobStateManager.resetMetrics();
  }
  
  onMount(() => {
    // Refresh metrics display every 2 seconds
    refreshInterval = setInterval(() => {
      // Force component re-render to update times
      metrics.subscribe(() => {})();
    }, 2000);
  });
  
  onDestroy(() => {
    if (refreshInterval) clearInterval(refreshInterval);
  });
</script>

<div class="performance-monitor {position}" class:expanded={showDetails}>
  <button 
    class="monitor-toggle"
    on:click={() => showDetails = !showDetails}
    title="Performance Metrics"
  >
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M19,3H5C3.89,3 3,3.89 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5C21,3.89 20.1,3 19,3M9,17H7V10H9V17M13,17H11V7H13V17M17,17H15V13H17V17Z" />
    </svg>
    {#if !showDetails}
      <span class="brief-stats">
        {cacheHitRate}% cache · {formatNumber($metrics.totalUpdates)} updates
      </span>
    {/if}
  </button>
  
  {#if showDetails}
    <div class="monitor-details">
      <div class="details-header">
        <h3>Performance Metrics</h3>
        <button class="reset-btn" on:click={resetMetrics} title="Reset metrics">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,6V9L16,5L12,1V4A8,8 0 0,0 4,12C4,13.57 4.46,15.03 5.24,16.26L6.7,14.8C6.25,13.97 6,13 6,12A6,6 0 0,1 12,6M18.76,7.74L17.3,9.2C17.74,10.04 18,11 18,12A6,6 0 0,1 12,18V15L8,19L12,23V20A8,8 0 0,0 20,12C20,10.43 19.54,8.97 18.76,7.74Z" />
          </svg>
        </button>
      </div>
      
      <div class="metric-section">
        <h4>Cache Performance</h4>
        <div class="metric-row">
          <span class="metric-label">Hit Rate:</span>
          <span class="metric-value" class:good={parseFloat(cacheHitRate) > 80} class:warning={parseFloat(cacheHitRate) < 50}>
            {cacheHitRate}%
          </span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Hits:</span>
          <span class="metric-value">{formatNumber($metrics.cacheHits)}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Misses:</span>
          <span class="metric-value">{formatNumber($metrics.cacheMisses)}</span>
        </div>
      </div>
      
      <div class="metric-section">
        <h4>Data Sources</h4>
        <div class="metric-row">
          <span class="metric-label">Current:</span>
          <span class="metric-value" class:good={$connectionStatus.source === 'websocket'}>
            {$connectionStatus.source}
          </span>
        </div>
        <div class="metric-row">
          <span class="metric-label">API Calls:</span>
          <span class="metric-value">{formatNumber($metrics.apiCalls)}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">WS Messages:</span>
          <span class="metric-value">{formatNumber($metrics.wsMessages)}</span>
        </div>
      </div>
      
      <div class="metric-section">
        <h4>Update Performance</h4>
        <div class="metric-row">
          <span class="metric-label">Total Updates:</span>
          <span class="metric-value">{formatNumber($metrics.totalUpdates)}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Avg Time:</span>
          <span class="metric-value" class:good={$metrics.averageUpdateTime < 10} class:warning={$metrics.averageUpdateTime > 50}>
            {formatTime($metrics.averageUpdateTime)}
          </span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Last Time:</span>
          <span class="metric-value">{formatTime($metrics.lastUpdateTime)}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Queue Size:</span>
          <span class="metric-value" class:warning={$managerState.pendingUpdates.length > 50}>
            {$managerState.pendingUpdates.length}
          </span>
        </div>
      </div>
      
      <div class="metric-section">
        <h4>System State</h4>
        <div class="metric-row">
          <span class="metric-label">Jobs Cached:</span>
          <span class="metric-value">{$managerState.jobCache.size}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Hosts Tracked:</span>
          <span class="metric-value">{$managerState.hostStates.size}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Tab Active:</span>
          <span class="metric-value">{$managerState.isTabActive ? 'Yes' : 'No'}</span>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .performance-monitor {
    position: fixed;
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.15);
    z-index: 999;
    transition: all 0.3s;
    font-size: 0.875rem;
  }
  
  .performance-monitor.top-right {
    top: 20px;
    right: 20px;
  }
  
  .performance-monitor.bottom-right {
    bottom: 20px;
    right: 20px;
  }
  
  .performance-monitor.bottom-left {
    bottom: 20px;
    left: 20px;
  }
  
  .monitor-toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: none;
    border: none;
    cursor: pointer;
    width: 100%;
    text-align: left;
    font-size: 0.875rem;
  }
  
  .monitor-toggle svg {
    width: 20px;
    height: 20px;
    color: #6b7280;
  }
  
  .brief-stats {
    color: #374151;
    font-weight: 500;
  }
  
  .monitor-details {
    padding: 12px;
    border-top: 1px solid #e5e7eb;
    max-height: 500px;
    overflow-y: auto;
    min-width: 280px;
  }
  
  .details-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }
  
  .details-header h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: #111827;
  }
  
  .reset-btn {
    width: 24px;
    height: 24px;
    padding: 4px;
    background: none;
    border: none;
    cursor: pointer;
    color: #6b7280;
    border-radius: 4px;
    transition: all 0.2s;
  }
  
  .reset-btn:hover {
    background: #f3f4f6;
    color: #374151;
  }
  
  .reset-btn svg {
    width: 100%;
    height: 100%;
  }
  
  .metric-section {
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid #f3f4f6;
  }
  
  .metric-section:last-child {
    border-bottom: none;
    margin-bottom: 0;
    padding-bottom: 0;
  }
  
  .metric-section h4 {
    margin: 0 0 8px 0;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    color: #6b7280;
    letter-spacing: 0.05em;
  }
  
  .metric-row {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    font-size: 0.875rem;
  }
  
  .metric-label {
    color: #6b7280;
  }
  
  .metric-value {
    font-weight: 600;
    color: #374151;
    font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  }
  
  .metric-value.good {
    color: #10b981;
  }
  
  .metric-value.warning {
    color: #f59e0b;
  }
  
  .metric-value.error {
    color: #ef4444;
  }
  
  @media (max-width: 640px) {
    .performance-monitor {
      bottom: 10px !important;
      left: 10px !important;
      right: 10px !important;
      top: auto !important;
    }
    
    .monitor-details {
      max-height: 400px;
    }
  }
</style>