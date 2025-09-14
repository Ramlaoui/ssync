<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export let error: string;
  export let title: string = 'Error';
  export let icon: string = 'error';
  export let showRetry: boolean = true;
  export let retryLabel: string = 'Retry';
  export let variant: 'page' | 'inline' | 'card' = 'inline';
  
  const dispatch = createEventDispatcher<{
    retry: void;
  }>();

  function handleRetry() {
    dispatch('retry');
  }

  $: containerClass = {
    page: 'flex-1 flex flex-col items-center justify-center p-8 text-center',
    inline: 'flex flex-col items-center justify-center p-6 text-center',
    card: 'bg-red-50 border border-red-200 rounded-lg p-4'
  }[variant];

  $: iconSize = variant === 'page' ? 'w-12 h-12' : 'w-8 h-8';
</script>

<div class="{containerClass}">
  {#if icon === 'error'}
    <svg class="{iconSize} text-red-500 mb-4" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
    </svg>
  {:else if icon === 'network'}
    <svg class="{iconSize} text-red-500 mb-4" viewBox="0 0 24 24" fill="currentColor">
      <path d="M19,21H5A2,2 0 0,1 3,19V5A2,2 0 0,1 5,3H19A2,2 0 0,1 21,5V19A2,2 0 0,1 19,21M5,5V19H19V5H5M8.5,13.5L11,16.5L14.5,12L19,18H5L8.5,13.5Z"/>
    </svg>
  {:else if icon === 'file'}
    <svg class="{iconSize} text-red-500 mb-4" viewBox="0 0 24 24" fill="currentColor">
      <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
    </svg>
  {/if}
  
  <h2 class="text-lg font-semibold text-gray-900 mb-2">{title}</h2>
  <p class="text-gray-600 mb-4 max-w-md">{error}</p>
  
  {#if showRetry}
    <button 
      class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
      on:click={handleRetry}
    >
      {retryLabel}
    </button>
  {/if}
</div>