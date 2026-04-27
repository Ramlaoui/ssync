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
  <div class="header-shell px-4 sm:px-6 lg:px-8">
    <div class="header-row flex h-16 items-center justify-between">
      <!-- Left side -->
      <div class="header-left flex items-center space-x-4">
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
      <div class="header-actions flex items-center space-x-3">
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

<style>
  .header-left {
    min-width: 0;
    flex: 1 1 auto;
  }

  .header-actions {
    flex: 0 0 auto;
  }

  .header-left :global(h1),
  .header-left :global(.page-copy),
  .header-left :global(.page-title-row),
  .header-left :global(.page-copy p) {
    min-width: 0;
  }

  .header-left :global(.page-title-row),
  .header-left :global(.page-copy p) {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  @media (max-width: 720px) {
    .header-shell {
      padding-left: 0.875rem;
      padding-right: 0.875rem;
    }

    .header-row {
      min-height: 4rem;
      height: auto;
      align-items: flex-start;
      gap: 0.75rem;
      padding: 0.65rem 0;
    }

    .header-left {
      flex-wrap: wrap;
      align-items: center;
      row-gap: 0.35rem;
      column-gap: 0.55rem;
    }

    .header-left :global(button) {
      padding-left: 0.35rem;
      padding-right: 0.35rem;
    }

    .header-left :global(.w-px) {
      display: none;
    }

    .header-left :global(.page-copy) {
      flex: 1 1 100%;
      max-width: 100%;
    }

    .header-left :global(.page-copy p) {
      white-space: normal;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      line-clamp: 2;
      -webkit-box-orient: vertical;
    }

    .header-actions {
      padding-top: 0;
    }
  }

  @media (max-width: 420px) {
    .header-row {
      flex-wrap: wrap;
    }

    .header-left {
      flex: 1 1 100%;
    }

    .header-actions {
      width: 100%;
      justify-content: space-between;
    }
  }
</style>
