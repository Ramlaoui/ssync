<script lang="ts">
  import { run } from 'svelte/legacy';

  import { fade } from 'svelte/transition';
  import { portal, clickOutside, keyboardNav, focusTrap } from '../../actions';
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';

  const dispatch = createEventDispatcher<{ close: void }>();

  
  interface Props {
    // Props
    open?: boolean;
    closeOnBackdropClick?: boolean;
    closeOnEscape?: boolean;
    backdrop?: boolean;
    backdropClass?: string;
    zIndex?: number;
    lockScroll?: boolean;
    trapFocus?: boolean;
    children?: import('svelte').Snippet;
  }

  let {
    open = false,
    closeOnBackdropClick = true,
    closeOnEscape = true,
    backdrop = true,
    backdropClass = '',
    zIndex = 50,
    lockScroll = true,
    trapFocus = true,
    children
  }: Props = $props();

  // State
  let overlayElement: HTMLElement | undefined = $state();
  let previousActiveElement: Element | null = $state(null);

  // Handle close
  function handleClose() {
    dispatch('close');
  }

  // Lock body scroll when open
  run(() => {
    if (typeof document !== 'undefined' && lockScroll) {
      if (open) {
        document.body.style.overflow = 'hidden';
        previousActiveElement = document.activeElement;
      } else {
        document.body.style.overflow = '';
        if (previousActiveElement && previousActiveElement instanceof HTMLElement) {
          previousActiveElement.focus();
        }
      }
    }
  });

  // Cleanup on destroy
  onDestroy(() => {
    if (typeof document !== 'undefined' && lockScroll) {
      document.body.style.overflow = '';
    }
  });

  // Keyboard navigation handlers
  const keyHandlers = {
    onEscape: closeOnEscape ? handleClose : undefined,
  };
</script>

{#if open}
  <div
    bind:this={overlayElement}
    use:portal={{ target: 'body', zIndex }}
    use:keyboardNav={keyHandlers}
    use:focusTrap={{ enabled: trapFocus }}
    class="overlay-container"
    role="dialog"
    aria-modal="true"
    transition:fade={{ duration: 200 }}
  >
    {#if backdrop}
      <div
        class="overlay-backdrop {backdropClass}"
        onclick={closeOnBackdropClick ? handleClose : undefined}
        role="presentation"
        transition:fade={{ duration: 200 }}
      ></div>
    {/if}

    {@render children?.()}
  </div>
{/if}

<style>
  .overlay-container {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
  }

  .overlay-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(2px);
    pointer-events: auto;
  }

  /* Allow pointer events on children */
  .overlay-container :global(*) {
    pointer-events: auto;
  }
</style>