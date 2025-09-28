<script lang="ts">
  import { createEventDispatcher, onDestroy } from 'svelte';
  import { RefreshCw, Settings2, Clock } from 'lucide-svelte';
  import { clickOutside } from '../lib/clickOutside';

  const dispatch = createEventDispatcher();

  export let refreshing = false;
  export let autoRefreshEnabled = false;
  export let autoRefreshInterval = 30; // seconds

  let showMenu = false;
  let autoRefreshTimer: number | null = null;
  let secondsUntilRefresh = autoRefreshInterval;

  // Common auto-refresh intervals
  const intervals = [
    { label: 'Off', value: 0 },
    { label: '10s', value: 10 },
    { label: '30s', value: 30 },
    { label: '1m', value: 60 },
    { label: '2m', value: 120 },
    { label: '5m', value: 300 },
  ];

  function handleManualRefresh() {
    dispatch('refresh');
    // Reset countdown if auto-refresh is enabled
    if (autoRefreshEnabled) {
      secondsUntilRefresh = autoRefreshInterval;
    }
  }

  function toggleAutoRefresh() {
    autoRefreshEnabled = !autoRefreshEnabled;
    if (autoRefreshEnabled) {
      startAutoRefresh();
    } else {
      stopAutoRefresh();
    }
    savePreferences();
  }

  function setInterval(value: number) {
    if (value === 0) {
      autoRefreshEnabled = false;
      stopAutoRefresh();
    } else {
      autoRefreshInterval = value;
      autoRefreshEnabled = true;
      startAutoRefresh();
    }
    showMenu = false;
    savePreferences();
  }

  function startAutoRefresh() {
    stopAutoRefresh(); // Clear any existing timer
    if (autoRefreshEnabled && autoRefreshInterval > 0) {
      secondsUntilRefresh = autoRefreshInterval;
      autoRefreshTimer = setInterval(() => {
        secondsUntilRefresh--;
        if (secondsUntilRefresh <= 0) {
          dispatch('refresh');
          secondsUntilRefresh = autoRefreshInterval;
        }
      }, 1000);
    }
  }

  function stopAutoRefresh() {
    if (autoRefreshTimer) {
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }
  }

  function savePreferences() {
    const prefs = JSON.parse(localStorage.getItem('ssync_preferences') || '{}');
    prefs.autoRefresh = autoRefreshEnabled;
    prefs.refreshInterval = autoRefreshInterval;
    localStorage.setItem('ssync_preferences', JSON.stringify(prefs));

    // Dispatch event for other components to pick up
    dispatch('settingsChanged', {
      autoRefreshEnabled,
      autoRefreshInterval
    });
  }

  function formatCountdown(seconds: number): string {
    if (seconds >= 60) {
      const mins = Math.floor(seconds / 60);
      const secs = seconds % 60;
      return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
    }
    return `${seconds}s`;
  }

  // Start auto-refresh if enabled on mount
  $: if (autoRefreshEnabled) {
    startAutoRefresh();
  }

  onDestroy(() => {
    stopAutoRefresh();
  });
</script>

<div class="relative flex items-center gap-1">
  <!-- Main refresh button -->
  <button
    on:click={handleManualRefresh}
    disabled={refreshing}
    class="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors flex items-center gap-2"
    title="{autoRefreshEnabled ? `Auto-refresh in ${formatCountdown(secondsUntilRefresh)}` : 'Refresh'}"
  >
    <RefreshCw class="w-4 h-4 {refreshing ? 'animate-spin' : ''}" />
    {#if autoRefreshEnabled && !refreshing}
      <span class="text-xs font-medium text-gray-500 min-w-[3rem] text-right">
        {formatCountdown(secondsUntilRefresh)}
      </span>
    {/if}
  </button>

  <!-- Settings dropdown button -->
  <button
    on:click={() => showMenu = !showMenu}
    class="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
    title="Refresh settings"
  >
    <Settings2 class="w-4 h-4" />
  </button>

  <!-- Dropdown menu -->
  {#if showMenu}
    <div
      class="absolute right-0 top-full mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-50"
      use:clickOutside
      on:click_outside={() => showMenu = false}
    >
      <div class="px-3 py-2 border-b border-gray-100">
        <div class="text-xs font-semibold text-gray-600 uppercase tracking-wider">
          Auto-refresh
        </div>
      </div>

      {#each intervals as interval}
        <button
          class="w-full text-left px-3 py-2 hover:bg-gray-50 flex items-center justify-between text-sm"
          class:bg-blue-50={autoRefreshEnabled && autoRefreshInterval === interval.value && interval.value > 0}
          class:text-blue-700={autoRefreshEnabled && autoRefreshInterval === interval.value && interval.value > 0}
          on:click={() => setInterval(interval.value)}
        >
          <span>{interval.label}</span>
          {#if autoRefreshEnabled && autoRefreshInterval === interval.value && interval.value > 0}
            <Clock class="w-3 h-3" />
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  /* Ensure the dropdown doesn't get cut off */
  :global(.relative) {
    position: relative;
  }
</style>