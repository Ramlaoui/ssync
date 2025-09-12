<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { dataSyncManager } from '../lib/DataSyncManager';
  import { batchedUpdates } from '../lib/BatchedUpdates';
  import { isWebSocketHealthy } from '../stores/jobWebSocket';
  
  export let compact = false;
  export let showDetails = false;
  
  let status = {
    webSocketConnected: false,
    webSocketReliable: false,
    isPolling: false,
    isTabActive: true,
    isPaused: false,
    connectionAttempts: 0,
    lastActivity: 0
  };
  
  let batchStatus = {
    queueSize: 0,
    isProcessing: false,
    hasTimer: false,
    callbackCount: 0
  };
  
  let updateInterval: ReturnType<typeof setInterval>;
  
  function updateStatus() {
    status = dataSyncManager.getStatus();
    batchStatus = batchedUpdates.getStatus();
  }
  
  function getStatusText(): string {
    if (status.isPaused) return 'Paused';
    if (status.webSocketConnected && status.webSocketReliable) return 'Real-time';
    if (status.webSocketConnected && !status.webSocketReliable) return 'Reconnecting';
    if (!status.webSocketConnected && status.isPolling) return 'Polling';
    if (!status.webSocketConnected && status.connectionAttempts === 0) return 'Initializing';
    return 'Connecting';
  }
  
  function getStatusColor(): string {
    if (status.isPaused) return '#6b7280'; // Gray
    if (status.webSocketConnected && status.webSocketReliable) return '#10b981'; // Green
    if (status.webSocketConnected && !status.webSocketReliable) return '#f97316'; // Orange
    if (!status.webSocketConnected && status.isPolling) return '#f59e0b'; // Amber
    if (!status.webSocketConnected && status.connectionAttempts === 0) return '#3b82f6'; // Blue
    return '#ef4444'; // Red
  }
  
  function formatLastActivity(): string {
    if (!status.lastActivity) return 'Never';
    const seconds = Math.floor((Date.now() - status.lastActivity) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  }
  
  onMount(() => {
    updateStatus();
    updateInterval = setInterval(updateStatus, 2000); // Update every 2 seconds
  });
  
  onDestroy(() => {
    if (updateInterval) clearInterval(updateInterval);
  });
</script>

<div class="sync-status" class:compact>
  <div class="status-indicator">
    <div 
      class="status-dot" 
      style="background-color: {getStatusColor()}"
      class:pulsing={!status.webSocketReliable && status.webSocketConnected}
    ></div>
    
    {#if !compact}
      <span class="status-text">{getStatusText()}</span>
    {/if}
  </div>
  
  {#if showDetails}
    <div class="status-details">
      <div class="detail-row">
        <span class="label">Connection:</span>
        <span class="value">
          {status.webSocketConnected ? 'Connected' : 'Disconnected'}
          {#if status.connectionAttempts > 0}
            (Attempt {status.connectionAttempts})
          {/if}
        </span>
      </div>
      
      <div class="detail-row">
        <span class="label">Mode:</span>
        <span class="value">
          {status.isPolling ? 'Polling' : 'WebSocket'}
        </span>
      </div>
      
      <div class="detail-row">
        <span class="label">Tab:</span>
        <span class="value">
          {status.isTabActive ? 'Active' : 'Background'}
        </span>
      </div>
      
      <div class="detail-row">
        <span class="label">Last Activity:</span>
        <span class="value">{formatLastActivity()}</span>
      </div>
      
      {#if batchStatus.queueSize > 0}
        <div class="detail-row">
          <span class="label">Queued Updates:</span>
          <span class="value">{batchStatus.queueSize}</span>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .sync-status {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-size: 0.875rem;
  }
  
  .sync-status.compact {
    gap: 0.5rem;
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
    transition: background-color 0.2s ease;
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
    font-weight: 500;
    color: #374151;
    user-select: none;
  }
  
  .status-details {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.5rem;
    background: #f9fafb;
    border-radius: 0.375rem;
    border: 1px solid #e5e7eb;
    font-size: 0.75rem;
  }
  
  .detail-row {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
  }
  
  .label {
    color: #6b7280;
    font-weight: 500;
  }
  
  .value {
    color: #374151;
    font-weight: 400;
  }
  
  @media (max-width: 768px) {
    .status-details {
      position: absolute;
      top: 100%;
      right: 0;
      z-index: 10;
      min-width: 200px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    
    .sync-status {
      position: relative;
    }
  }
</style>