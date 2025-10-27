<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { navigationState, navigationActions } from '../stores/navigation';
  import { ArrowLeft, RefreshCw } from 'lucide-svelte';
  import RefreshControl from './RefreshControl.svelte';

  const dispatch = createEventDispatcher();



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

  interface Props {
    title?: string;
    subtitle?: string;
    count?: number | undefined;
    countLabel?: string;
    showRefresh?: boolean;
    refreshing?: boolean;
    showBackButton?: boolean;
    customActions?: boolean; // Slot for custom actions
    autoRefreshEnabled?: boolean;
    autoRefreshInterval?: number;
    customBackHandler?: boolean;
    customBackLabel?: string;
    left?: import('svelte').Snippet;
    actions?: import('svelte').Snippet;
    additional?: import('svelte').Snippet;
  }

  let {
    title = '',
    subtitle = '',
    count = undefined,
    countLabel = 'total',
    showRefresh = false,
    refreshing = false,
    showBackButton = true,
    customActions = false,
    autoRefreshEnabled = $bindable(false),
    autoRefreshInterval = $bindable(30),
    customBackHandler = false,
    customBackLabel = '',
    left,
    actions,
    additional
  }: Props = $props();

  function handleBackClick() {
    if (customBackHandler) {
      dispatch('back');
    } else {
      navigationActions.goBack();
    }
  }

  function handleRefresh() {
    dispatch('refresh');
  }

  function handleRefreshSettingsChanged(event: CustomEvent) {
    dispatch('refreshSettingsChanged', event.detail);
  }
  let backLabel = $derived(customBackLabel || getBackLabel($navigationState));
</script>

<header class="bg-background border-b border-border sticky top-0 z-40">
  <div class="px-4 sm:px-6 lg:px-8">
    <div class="flex h-16 items-center justify-between">
      <!-- Left side -->
      <div class="flex items-center space-x-4">
        {#if showBackButton}
          <button
            class="flex items-center gap-2 px-3 py-2 text-muted-foreground hover:text-foreground hover:bg-secondary rounded-lg font-medium transition-colors"
            onclick={handleBackClick}
          >
            <ArrowLeft class="w-4 h-4" />
            {backLabel}
          </button>

          <div class="w-px h-6 bg-border"></div>
        {/if}

        {#if title}
          <h1 class="text-lg font-semibold text-foreground">{title}</h1>
        {/if}

        {#if subtitle}
          <div class="text-sm text-muted-foreground">{subtitle}</div>
        {/if}

        {#if count !== undefined}
          <div class="flex items-center space-x-2">
            <span class="text-xl font-medium text-foreground">{count}</span>
            <span class="text-sm text-muted-foreground">{countLabel}</span>
          </div>
        {/if}

        <!-- Slot for additional left content -->
        {@render left?.()}
      </div>

      <!-- Right side -->
      <div class="flex items-center space-x-3">
        <!-- Slot for custom actions -->
        {@render actions?.()}

        {#if showRefresh}
          <RefreshControl
            {refreshing}
            bind:autoRefreshEnabled
            bind:autoRefreshInterval
            on:refresh={handleRefresh}
            on:settingsChanged={handleRefreshSettingsChanged}
          />
        {/if}
      </div>
    </div>

    <!-- Slot for additional header content (tabs, etc.) -->
    {@render additional?.()}
  </div>
</header>

