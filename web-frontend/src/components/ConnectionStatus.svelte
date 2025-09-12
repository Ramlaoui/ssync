<script lang="ts">
  import { allJobsWebSocketStore } from '../stores/jobWebSocket';
  import { dataSyncManager } from '../lib/DataSyncManager';
  
  let showDetails = false;
  let syncStatus: any = {};
  
  // Update sync status periodically (reduced from 1s to 10s)
  setInterval(() => {
    syncStatus = dataSyncManager.getStatus();
  }, 10000);
  
  $: isConnected = $allJobsWebSocketStore.connected;
  $: connectionClass = isConnected ? 'connected' : 'disconnected';
  
  function handleReconnect() {
    dataSyncManager.requestImmediateRefresh();
  }
</script>

<div class="connection-status {connectionClass}" class:expanded={showDetails}>
  <button 
    class="status-indicator"
    on:click={() => showDetails = !showDetails}
    title={isConnected ? 'WebSocket connected' : 'WebSocket disconnected - using polling'}
  >
    <span class="status-dot"></span>
    <span class="status-text">
      {isConnected ? 'Live' : 'Reconnecting...'}
    </span>
  </button>
  
  {#if showDetails}
    <div class="status-details">
      <div class="detail-row">
        <span>WebSocket:</span>
        <span class:text-green={isConnected} class:text-red={!isConnected}>
          {isConnected ? 'Connected' : 'Disconnected'}
        </span>
      </div>
      <div class="detail-row">
        <span>Data sync:</span>
        <span>{syncStatus.isWebSocketReliable ? 'Real-time' : 'Polling'}</span>
      </div>
      {#if !isConnected}
        <div class="detail-row">
          <span>Next retry:</span>
          <span>{syncStatus.nextReconnectIn || 'Calculating...'}</span>
        </div>
        <button class="reconnect-btn" on:click={handleReconnect}>
          Force Refresh
        </button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .connection-status {
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    z-index: 1000;
    transition: all 0.3s;
  }
  
  .status-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: none;
    border: none;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
  }
  
  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    animation: pulse 2s infinite;
  }
  
  .connected .status-dot {
    background: #10b981;
  }
  
  .disconnected .status-dot {
    background: #f59e0b;
    animation: pulse 1s infinite;
  }
  
  .status-text {
    color: #374151;
  }
  
  .disconnected .status-text {
    color: #f59e0b;
  }
  
  .status-details {
    padding: 12px 16px;
    border-top: 1px solid #e5e7eb;
    font-size: 0.75rem;
  }
  
  .detail-row {
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
    color: #6b7280;
  }
  
  .text-green {
    color: #10b981;
  }
  
  .text-red {
    color: #ef4444;
  }
  
  .reconnect-btn {
    width: 100%;
    padding: 6px 12px;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    margin-top: 8px;
  }
  
  .reconnect-btn:hover {
    background: #2563eb;
  }
  
  @keyframes pulse {
    0% {
      box-shadow: 0 0 0 0 currentColor;
      opacity: 1;
    }
    70% {
      box-shadow: 0 0 0 8px currentColor;
      opacity: 0;
    }
    100% {
      opacity: 1;
    }
  }
  
  @media (max-width: 640px) {
    .connection-status {
      bottom: 10px;
      right: 10px;
    }
  }
</style>