<!-- @migration-task Error while migrating Svelte code: can't migrate `$: hostState = $hostStates.get(hostname);` to `$derived` because there's a variable named derived.
     Rename the variable and try again or migrate by hand. -->
<script lang="ts">
  import { derived } from 'svelte/store';
  import { jobStateManager } from '../lib/JobStateManager';
  import { RefreshCw, CheckCircle, AlertCircle, Clock } from 'lucide-svelte';

  export let hostname: string;
  export let compact = false;

  // Get host states from JobStateManager
  const hostStates = jobStateManager.getHostStates();

  // Get the state for this specific host
  $: hostState = $hostStates.get(hostname);
  $: loading = hostState?.status === 'loading';
  $: isTimeout = hostState?.isTimeout || false;
  $: errorMessage = hostState?.lastError || 'Connection error';
  $: error = hostState?.status === 'error' ? errorMessage : undefined;
  $: lastFetch = hostState?.lastSync || 0;

  // Calculate time since last fetch
  function getTimeSinceLastFetch(timestamp: number): string {
    if (!timestamp) return 'Never';
    const now = Date.now();
    const diff = now - timestamp;
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) return `${hours}h ago`;
    if (minutes > 0) return `${minutes}m ago`;
    if (seconds > 30) return `${seconds}s ago`;
    return 'Just now';
  }

  $: timeSinceLastFetch = getTimeSinceLastFetch(lastFetch);
  $: isStale = lastFetch && (Date.now() - lastFetch) > 60000; // Stale after 1 minute
</script>

{#if compact}
  <!-- Compact indicator (icon only) -->
  <div class="inline-flex items-center" title="{loading ? 'Refreshing...' : error ? `${isTimeout ? 'Timeout' : 'Error'}: ${error}` : `Updated ${timeSinceLastFetch}`}">
    {#if loading}
      <RefreshCw class="h-4 w-4 text-blue-500 animate-spin" />
    {:else if error}
      <AlertCircle class="h-4 w-4 text-red-500" />
    {:else if isStale}
      <Clock class="h-4 w-4 text-yellow-500" />
    {:else}
      <CheckCircle class="h-4 w-4 text-green-500" />
    {/if}
  </div>
{:else}
  <!-- Full indicator with text -->
  <div class="flex items-center gap-2 text-sm">
    {#if loading}
      <RefreshCw class="h-4 w-4 text-blue-500 animate-spin" />
      <span class="text-blue-600">Refreshing...</span>
    {:else if error}
      <AlertCircle class="h-4 w-4 text-red-500" />
      <span class="text-red-600" title={error}>
        {isTimeout ? 'Connection timeout' : 'Connection error'}
      </span>
    {:else if isStale}
      <Clock class="h-4 w-4 text-yellow-500" />
      <span class="text-yellow-600">Updated {timeSinceLastFetch}</span>
    {:else}
      <CheckCircle class="h-4 w-4 text-green-500" />
      <span class="text-gray-600">Updated {timeSinceLastFetch}</span>
    {/if}
  </div>
{/if}