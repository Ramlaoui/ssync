<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { navigationState, navigationActions } from '../stores/navigation';
  import { ArrowLeft, RefreshCw } from 'lucide-svelte';

  const dispatch = createEventDispatcher();

  // Props
  export let title: string = '';  // Made optional
  export let subtitle: string = '';
  export let count: number | undefined = undefined;
  export let countLabel: string = 'total';
  export let showRefresh: boolean = false;
  export let refreshing: boolean = false;
  export let showBackButton: boolean = true;
  export let customActions: boolean = false; // Slot for custom actions

  // Get back navigation info
  $: backLabel = customBackLabel || getBackLabel($navigationState);

  function getBackLabel(navState: typeof $navigationState): string {
    if (navState.context === 'job') {
      return 'Back to Job';
    }
    if (navState.context === 'watcher') {
      return 'Watchers';
    }
    if (navState.previousRoute?.includes('/job/')) {
      return 'Back to Job';
    }
    return 'Home';
  }

  // Check if parent component is listening for back events
  export let customBackHandler: boolean = false;
  export let customBackLabel: string = '';

  function handleBackClick() {
    if (customBackHandler) {
      // Parent component will handle the back navigation
      dispatch('back');
    } else {
      // Use default navigation
      navigationActions.goBack();
    }
  }

  function handleRefresh() {
    dispatch('refresh');
  }
</script>

<header class="bg-white border-b border-gray-200 sticky top-0 z-40">
  <div class="px-4 sm:px-6 lg:px-8">
    <div class="flex h-16 items-center justify-between">
      <!-- Left side -->
      <div class="flex items-center space-x-4">
        {#if showBackButton}
          <button
            class="flex items-center gap-2 px-3 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg font-medium transition-colors"
            on:click={handleBackClick}
          >
            <ArrowLeft class="w-4 h-4" />
            {backLabel}
          </button>

          <div class="w-px h-6 bg-gray-300"></div>
        {/if}

        {#if title}
          <h1 class="text-lg font-semibold text-gray-900">{title}</h1>
        {/if}

        {#if subtitle}
          <div class="text-sm text-gray-500">{subtitle}</div>
        {/if}

        {#if count !== undefined}
          <div class="flex items-center space-x-2">
            <span class="text-xl font-medium">{count}</span>
            <span class="text-sm text-gray-500">{countLabel}</span>
          </div>
        {/if}

        <!-- Slot for additional left content -->
        <slot name="left" />
      </div>

      <!-- Right side -->
      <div class="flex items-center space-x-3">
        <!-- Slot for custom actions -->
        <slot name="actions" />

        {#if showRefresh}
          <button
            on:click={handleRefresh}
            disabled={refreshing}
            class="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
            title="Refresh"
          >
            <RefreshCw class="w-4 h-4 {refreshing ? 'animate-spin' : ''}" />
          </button>
        {/if}
      </div>
    </div>

    <!-- Slot for additional header content (tabs, etc.) -->
    <slot name="additional" />
  </div>
</header>

<style>
  /* Component-specific styles can go here if needed */
</style>