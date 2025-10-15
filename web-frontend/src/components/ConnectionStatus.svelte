<script lang="ts">
  import { jobStateManager } from '../lib/JobStateManager';
  
  let showDetails = $state(false);
  
  const connectionStatus = jobStateManager.getConnectionStatus();
  const managerState = jobStateManager.getState();
  
  let isConnected = $derived($connectionStatus.connected);
  let connectionClass = $derived($connectionStatus.source === 'websocket' ? 'connected' : 
                       $connectionStatus.source === 'api' ? 'polling' : 'disconnected');
  
  function handleReconnect() {
    jobStateManager.forceRefresh();
  }
  
  function getStatusText() {
    if ($connectionStatus.source === 'websocket') return 'Live';
    if ($connectionStatus.source === 'api') return 'Polling';
    if ($connectionStatus.source === 'cache') return 'Cached';
    return 'Reconnecting...';
  }
</script>

<div class="connection-status {connectionClass}" class:expanded={showDetails}>
  <button 
    class="status-indicator"
    onclick={() => showDetails = !showDetails}
    title="Connection status: {$connectionStatus.source}"
  >
    <span class="status-dot"></span>
    <span class="status-text">
      {getStatusText()}
    </span>
  </button>
  
  {#if showDetails}
    <div class="status-details">
      <div class="detail-row">
        <span>Source:</span>
        <span class:text-green={$connectionStatus.source === 'websocket'} 
              class:text-amber={$connectionStatus.source === 'api'}
              class:text-blue={$connectionStatus.source === 'cache'}>
          {$connectionStatus.source}
        </span>
      </div>
      <div class="detail-row">
        <span>Connected:</span>
        <span class:text-green={isConnected} class:text-red={!isConnected}>
          {isConnected ? 'Yes' : 'No'}
        </span>
      </div>
      <div class="detail-row">
        <span>Tab Active:</span>
        <span>{$managerState.isTabActive ? 'Yes' : 'No'}</span>
      </div>
      {#if $managerState.isPaused}
        <div class="detail-row">
          <span>Status:</span>
          <span class="text-amber">Paused (Inactive)</span>
        </div>
      {/if}
      <button class="reconnect-btn" onclick={handleReconnect}>
        Force Refresh
      </button>
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
  
  .polling .status-dot {
    background: #f59e0b;
    animation: pulse 1.5s infinite;
  }
  
  .disconnected .status-dot {
    background: #ef4444;
    animation: pulse 1s infinite;
  }
  
  .status-text {
    color: #374151;
  }
  
  .polling .status-text {
    color: #f59e0b;
  }
  
  .disconnected .status-text {
    color: #ef4444;
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
  
  .text-amber {
    color: #f59e0b;
  }
  
  .text-blue {
    color: #3b82f6;
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