<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { jobStateManager } from '../lib/JobStateManager';
  
  interface Props {
    compact?: boolean;
    showDetails?: boolean;
  }

  let { compact = false, showDetails = false }: Props = $props();
  
  const connectionStatus = jobStateManager.getConnectionStatus();
  const managerState = jobStateManager.getState();
  
  function getStatusText(): string {
    if ($managerState.isPaused) return 'Paused';
    if ($connectionStatus.source === 'websocket' && $connectionStatus.healthy) return 'Real-time';
    if ($connectionStatus.source === 'websocket' && !$connectionStatus.healthy) return 'Reconnecting';
    if ($connectionStatus.source === 'api') return 'Polling';
    if ($connectionStatus.source === 'cache') return 'Cached';
    return 'Connecting';
  }
  
  function getStatusColor(): string {
    if ($managerState.isPaused) return '#6b7280'; // Gray
    if ($connectionStatus.source === 'websocket' && $connectionStatus.healthy) return '#10b981'; // Green
    if ($connectionStatus.source === 'websocket' && !$connectionStatus.healthy) return '#f97316'; // Orange
    if ($connectionStatus.source === 'api') return '#f59e0b'; // Amber
    if ($connectionStatus.source === 'cache') return '#3b82f6'; // Blue
    return '#ef4444'; // Red
  }
  
  function formatLastActivity(): string {
    if (!$managerState.lastActivity) return 'Never';
    const seconds = Math.floor((Date.now() - $managerState.lastActivity) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  }
  
  // Queue status
  let queueSize = $derived($managerState.pendingUpdates.length);
  let isProcessing = $derived($managerState.processingUpdates);
</script>

<div class="sync-status" class:compact>
  <div class="status-indicator">
    <div 
      class="status-dot" 
      style="background-color: {getStatusColor()}"
      class:pulsing={$connectionStatus.source === 'websocket' && !$connectionStatus.healthy}
    ></div>
    
    {#if !compact}
      <span class="status-text">{getStatusText()}</span>
    {/if}
  </div>
  
  {#if showDetails}
    <div class="status-details">
      <div class="detail-row">
        <span class="label">Source:</span>
        <span class="value">{$connectionStatus.source}</span>
      </div>
      
      <div class="detail-row">
        <span class="label">Status:</span>
        <span class="value">
          {$connectionStatus.connected ? 'Connected' : 'Disconnected'}
          {#if $connectionStatus.healthy}
            (Healthy)
          {:else}
            (Unhealthy)
          {/if}
        </span>
      </div>
      
      <div class="detail-row">
        <span class="label">Tab Active:</span>
        <span class="value">{$managerState.isTabActive ? 'Yes' : 'No'}</span>
      </div>
      
      <div class="detail-row">
        <span class="label">Last Activity:</span>
        <span class="value">{formatLastActivity()}</span>
      </div>
      
      {#if queueSize > 0}
        <div class="detail-row">
          <span class="label">Queue:</span>
          <span class="value">
            {queueSize} update{queueSize !== 1 ? 's' : ''}
            {#if isProcessing}
              (Processing)
            {/if}
          </span>
        </div>
      {/if}
      
      <div class="detail-row">
        <span class="label">Hosts:</span>
        <span class="value">{$managerState.hostStates.size} tracked</span>
      </div>
    </div>
  {/if}
</div>

<style>
  .sync-status {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .sync-status.compact {
    flex-direction: row;
    align-items: center;
  }
  
  .status-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    transition: background-color 0.3s ease;
  }
  
  .status-dot.pulsing {
    animation: pulse 2s infinite;
  }
  
  @keyframes pulse {
    0%, 100% {
      opacity: 1;
    }
    50% {
      opacity: 0.5;
    }
  }
  
  .status-text {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-primary);
  }
  
  .status-details {
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: 0.375rem;
    padding: 0.75rem;
    font-size: 0.75rem;
    min-width: 200px;
  }
  
  .detail-row {
    display: flex;
    justify-content: space-between;
    padding: 0.25rem 0;
  }
  
  .detail-row:not(:last-child) {
    border-bottom: 1px solid var(--border-color-light);
  }
  
  .label {
    color: var(--text-secondary);
    font-weight: 500;
  }
  
  .value {
    color: var(--text-primary);
  }
</style>