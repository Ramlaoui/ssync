<script lang="ts">
  import { jobStateManager } from '../lib/JobStateManager';
  import { Wifi, WifiOff, RefreshCw, AlertTriangle } from 'lucide-svelte';

  interface Props {
    compact?: boolean;
  }

  let { compact = false }: Props = $props();

  // Use JobStateManager's connection status
  const connectionStatus = jobStateManager.getConnectionStatus();

  // Reactive connection status
  let connected = $derived($connectionStatus.connected);
  let isLoading = $derived($connectionStatus.isLoading);

  let reconnecting = $state(false);

  async function handleReconnect() {
    reconnecting = true;

    // Disconnect and reconnect WebSocket
    jobStateManager.destroy();
    await new Promise(resolve => setTimeout(resolve, 500));
    jobStateManager.connectWebSocket();

    // Also refresh data
    await jobStateManager.refresh();

    reconnecting = false;
  }
</script>

{#if compact}
  <!-- Compact status indicator -->
  <button
    class="flex items-center gap-2 px-2 py-1 rounded-lg transition-colors {connected ? 'hover:bg-green-50' : 'hover:bg-red-50'}"
    onclick={handleReconnect}
    disabled={reconnecting || isLoading}
    title="{connected ? 'WebSocket connected - Click to reconnect' : 'WebSocket disconnected - Click to connect'}"
  >
    {#if reconnecting || isLoading}
      <RefreshCw class="h-4 w-4 text-blue-500 animate-spin" />
    {:else if connected}
      <Wifi class="h-4 w-4 text-green-500" />
    {:else}
      <WifiOff class="h-4 w-4 text-red-500" />
    {/if}
  </button>
{:else}
  <!-- Full status display -->
  <div class="flex items-center gap-3 px-3 py-2 bg-white rounded-lg shadow-sm border border-gray-200">
    <div class="flex items-center gap-2">
      {#if reconnecting || isLoading}
        <RefreshCw class="h-5 w-5 text-blue-500 animate-spin" />
        <span class="text-sm text-blue-600">{reconnecting ? 'Reconnecting...' : 'Loading...'}</span>
      {:else if connected}
        <Wifi class="h-5 w-5 text-green-500" />
        <span class="text-sm text-green-600">Live updates active</span>
      {:else}
        <WifiOff class="h-5 w-5 text-gray-500" />
        <span class="text-sm text-gray-600">Not connected</span>
      {/if}
    </div>

    <button
      class="ml-2 px-3 py-1 text-xs font-medium rounded-md transition-colors
        {connected ? 'bg-gray-100 hover:bg-gray-200 text-gray-700' : 'bg-blue-100 hover:bg-blue-200 text-blue-700'}"
      onclick={handleReconnect}
      disabled={reconnecting || isLoading}
    >
      {connected ? 'Reconnect' : 'Connect'}
    </button>
  </div>
{/if}
