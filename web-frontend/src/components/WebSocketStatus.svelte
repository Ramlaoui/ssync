<script lang="ts">
  import { allJobsWebSocketStore, connectAllJobsWebSocket, disconnectAllJobsWebSocket, getConnectionQuality } from '../stores/jobWebSocket';
  import { Wifi, WifiOff, RefreshCw, AlertTriangle } from 'lucide-svelte';

  export let compact = false;

  // Reactive connection status
  $: connected = $allJobsWebSocketStore.connected;
  $: error = $allJobsWebSocketStore.error;

  let reconnecting = false;
  let showDetails = false;

  async function handleReconnect() {
    reconnecting = true;
    disconnectAllJobsWebSocket();

    // Wait a bit before reconnecting
    await new Promise(resolve => setTimeout(resolve, 500));

    connectAllJobsWebSocket();
    reconnecting = false;
  }

  function getConnectionQualityInfo() {
    const quality = getConnectionQuality();
    return quality.allJobs;
  }
</script>

{#if compact}
  <!-- Compact status indicator -->
  <button
    class="flex items-center gap-2 px-2 py-1 rounded-lg transition-colors {connected ? 'hover:bg-green-50' : 'hover:bg-red-50'}"
    on:click={handleReconnect}
    disabled={reconnecting}
    title="{connected ? 'WebSocket connected - Click to reconnect' : 'WebSocket disconnected - Click to connect'}"
  >
    {#if reconnecting}
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
      {#if reconnecting}
        <RefreshCw class="h-5 w-5 text-blue-500 animate-spin" />
        <span class="text-sm text-blue-600">Reconnecting...</span>
      {:else if connected}
        <Wifi class="h-5 w-5 text-green-500" />
        <span class="text-sm text-green-600">Live updates active</span>
      {:else if error}
        <AlertTriangle class="h-5 w-5 text-red-500" />
        <span class="text-sm text-red-600">Connection error</span>
      {:else}
        <WifiOff class="h-5 w-5 text-gray-500" />
        <span class="text-sm text-gray-600">Not connected</span>
      {/if}
    </div>

    <button
      class="ml-2 px-3 py-1 text-xs font-medium rounded-md transition-colors
        {connected ? 'bg-gray-100 hover:bg-gray-200 text-gray-700' : 'bg-blue-100 hover:bg-blue-200 text-blue-700'}"
      on:click={handleReconnect}
      disabled={reconnecting}
    >
      {connected ? 'Reconnect' : 'Connect'}
    </button>

    {#if !compact}
      <button
        class="ml-auto text-xs text-gray-500 hover:text-gray-700"
        on:click={() => showDetails = !showDetails}
      >
        {showDetails ? 'Hide' : 'Show'} details
      </button>
    {/if}
  </div>

  {#if showDetails && !compact}
    <div class="mt-2 px-3 py-2 bg-gray-50 rounded-lg text-xs text-gray-600">
      {#each Object.entries(getConnectionQualityInfo()) as [key, value]}
        <div class="flex justify-between">
          <span class="font-medium">{key}:</span>
          <span>{value}</span>
        </div>
      {/each}
    </div>
  {/if}
{/if}