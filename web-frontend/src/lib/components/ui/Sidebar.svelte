<script lang="ts">
  import { createBubbler, stopPropagation } from 'svelte/legacy';

  const bubble = createBubbler();
  import Overlay from './Overlay.svelte';
  import { fly, slide } from 'svelte/transition';
  import { X } from 'lucide-svelte';
  import { createEventDispatcher } from 'svelte';

  const dispatch = createEventDispatcher<{ close: void }>();

  

  
  interface Props {
    // All Overlay props
    open?: boolean;
    closeOnBackdropClick?: boolean;
    closeOnEscape?: boolean;
    // Sidebar-specific props
    position?: 'left' | 'right' | 'top' | 'bottom';
    size?: string; // Can be '300px', '40%', 'full'
    showCloseButton?: boolean;
    headerClass?: string;
    contentClass?: string;
    title?: string;
    header?: import('svelte').Snippet;
    children?: import('svelte').Snippet;
  }

  let {
    open = $bindable(false),
    closeOnBackdropClick = true,
    closeOnEscape = true,
    position = 'right',
    size = '400px',
    showCloseButton = true,
    headerClass = '',
    contentClass = '',
    title = '',
    header,
    children
  }: Props = $props();

  // Position mapping for transitions and styles
  const positionConfig: Record<string, { x?: number; y?: number; axis: string }> = {
    left: { x: -100, axis: 'width' },
    right: { x: 100, axis: 'width' },
    top: { y: -100, axis: 'height' },
    bottom: { y: 100, axis: 'height' }
  };

  function handleClose() {
    open = false;
    dispatch('close');
  }

  // Compute sidebar position classes
  let positionClass = $derived(`sidebar-${position}`);
  let sizeStyle = $derived(position === 'left' || position === 'right'
    ? `width: ${size === 'full' ? '100vw' : size};`
    : `height: ${size === 'full' ? '100vh' : size};`);
</script>

<Overlay
  {open}
  {closeOnBackdropClick}
  {closeOnEscape}
  on:close={handleClose}
>
  <div
    class="sidebar-container {positionClass}"
    style={sizeStyle}
    onclick={stopPropagation(bubble('click'))}
    onkeydown={() => {}}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
    transition:fly={{
      x: positionConfig[position].x || 0,
      y: positionConfig[position].y || 0,
      duration: 250
    }}
  >
    {#if header || title || showCloseButton}
      <div class="sidebar-header {headerClass}">
        {#if header}
          {@render header?.()}
        {:else if title}
          <h3 class="sidebar-title">{title}</h3>
        {/if}

        {#if showCloseButton}
          <button
            class="sidebar-close-button"
            onclick={handleClose}
            aria-label="Close sidebar"
            type="button"
          >
            <X class="w-5 h-5" />
          </button>
        {/if}
      </div>
    {/if}

    <div class="sidebar-content {contentClass}">
      {@render children?.()}
    </div>
  </div>
</Overlay>

<style>
  .sidebar-container {
    position: fixed;
    background: white;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1),
                0 4px 6px -2px rgba(0, 0, 0, 0.05);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    max-height: 100vh;
  }

  .sidebar-left {
    top: 0;
    left: 0;
    bottom: 0;
    border-right: 1px solid #e5e7eb;
  }

  .sidebar-right {
    top: 0;
    right: 0;
    bottom: 0;
    border-left: 1px solid #e5e7eb;
  }

  .sidebar-top {
    top: 0;
    left: 0;
    right: 0;
    border-bottom: 1px solid #e5e7eb;
  }

  .sidebar-bottom {
    bottom: 0;
    left: 0;
    right: 0;
    border-top: 1px solid #e5e7eb;
  }

  .sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.25rem 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    gap: 1rem;
    flex-shrink: 0;
  }

  .sidebar-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: #111827;
    margin: 0;
  }

  .sidebar-close-button {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem;
    border: none;
    background: transparent;
    border-radius: 0.375rem;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.15s;
    flex-shrink: 0;
  }

  .sidebar-close-button:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .sidebar-close-button:focus {
    outline: 2px solid #3b82f6;
    outline-offset: 2px;
  }

  .sidebar-content {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 1.5rem;
    min-height: 0;
  }

  /* Responsive */
  @media (max-width: 768px) {
    .sidebar-left,
    .sidebar-right {
      width: 100vw !important;
      max-width: 100vw;
    }

    .sidebar-top,
    .sidebar-bottom {
      height: 100vh !important;
      max-height: 100vh;
    }

    .sidebar-header,
    .sidebar-content {
      padding: 1rem;
    }
  }
</style>