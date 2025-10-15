<script lang="ts">
  
  import { createEventDispatcher } from 'svelte';
  interface Props {
    title: string;
    message?: string;
    icon?: string;
    actionLabel?: string;
    actionHref?: string;
  }

  let {
    title,
    message = '',
    icon = 'empty',
    actionLabel = '',
    actionHref = ''
  }: Props = $props();
  const dispatch = createEventDispatcher<{
    action: void;
  }>();

  function handleAction() {
    if (actionHref) {
      window.location.href = actionHref;
    } else {
      dispatch('action');
    }
  }
</script>

<div class="flex flex-col items-center justify-center p-12 text-center text-gray-500">
  {#if icon === 'empty'}
    <svg class="w-12 h-12 mb-4 opacity-50" viewBox="0 0 24 24" fill="currentColor">
      <path d="M19,3H5C3.89,3 3,3.89 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5C21,3.89 20.1,3 19,3M19,5V19H5V5H19Z"/>
    </svg>
  {:else if icon === 'document'}
    <svg class="w-12 h-12 mb-4 opacity-50" viewBox="0 0 24 24" fill="currentColor">
      <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
    </svg>
  {:else if icon === 'clock'}
    <svg class="w-12 h-12 mb-4 opacity-50" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z"/>
    </svg>
  {:else if icon === 'terminal'}
    <svg class="w-12 h-12 mb-4 opacity-50" viewBox="0 0 24 24" fill="currentColor">
      <path d="M20,19V7H4V19H20M20,3A2,2 0 0,1 22,5V19A2,2 0 0,1 20,21H4A2,2 0 0,1 2,19V5C2,3.89 2.9,3 4,3H20M13,17V15H18V17H13M9.58,13L5.57,9H8.4L11.7,12.3C12.09,12.69 12.09,13.33 11.7,13.72L8.42,17H5.59L9.58,13Z"/>
    </svg>
  {:else if icon === 'code'}
    <svg class="w-12 h-12 mb-4 opacity-50" viewBox="0 0 24 24" fill="currentColor">
      <path d="M14.6,16.6L19.2,12L14.6,7.4L16,6L22,12L16,18L14.6,16.6M9.4,16.6L4.8,12L9.4,7.4L8,6L2,12L8,18L9.4,16.6Z"/>
    </svg>
  {/if}
  
  <h3 class="text-lg font-medium text-gray-900 mb-2">{title}</h3>
  
  {#if message}
    <p class="text-gray-500 mb-6 max-w-sm">{message}</p>
  {/if}
  
  {#if actionLabel}
    <button 
      class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
      onclick={handleAction}
    >
      {actionLabel}
    </button>
  {/if}
</div>