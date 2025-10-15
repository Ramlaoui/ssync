<script lang="ts">
  import { run } from 'svelte/legacy';

  import { fade, scale } from 'svelte/transition';
  import { portal, clickOutside, keyboardNav } from '../../actions';
  import { createEventDispatcher, tick, onMount } from 'svelte';

  const dispatch = createEventDispatcher<{ close: void; select: any }>();

  
  interface Props {
    // Props
    open?: boolean;
    placement?: 'bottom' | 'top' | 'left' | 'right' | 'auto';
    offset?: number;
    closeOnSelect?: boolean;
    triggerRef?: HTMLElement | null;
    width?: string; // 'auto', '200px', 'trigger' (match trigger width)
    maxHeight?: string;
    align?: 'start' | 'center' | 'end';
    children?: import('svelte').Snippet<[any]>;
  }

  let {
    open = $bindable(false),
    placement = 'auto',
    offset = 8,
    closeOnSelect = true,
    triggerRef = null,
    width = 'auto',
    maxHeight = '300px',
    align = 'start',
    children
  }: Props = $props();

  // State
  let dropdownElement: HTMLElement | undefined = $state();
  let dropdownPosition = $state({ top: 0, left: 0 });
  let computedPlacement: 'bottom' | 'top' | 'left' | 'right' = $state('bottom');
  let computedWidth: string = $state('auto');

  // Calculate position based on trigger element
  async function updatePosition() {
    if (!triggerRef || !dropdownElement) return;

    await tick();

    const triggerRect = triggerRef.getBoundingClientRect();
    const dropdownRect = dropdownElement.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let top = 0;
    let left = 0;
    let finalPlacement = placement;

    // Auto-detect best placement
    if (placement === 'auto') {
      const spaceBelow = viewportHeight - triggerRect.bottom;
      const spaceAbove = triggerRect.top;
      const spaceRight = viewportWidth - triggerRect.right;
      const spaceLeft = triggerRect.left;

      if (spaceBelow >= dropdownRect.height || spaceBelow >= spaceAbove) {
        finalPlacement = 'bottom';
      } else if (spaceAbove >= dropdownRect.height) {
        finalPlacement = 'top';
      } else if (spaceRight >= dropdownRect.width) {
        finalPlacement = 'right';
      } else if (spaceLeft >= dropdownRect.width) {
        finalPlacement = 'left';
      } else {
        finalPlacement = 'bottom'; // Default fallback
      }
    }

    computedPlacement = finalPlacement as 'bottom' | 'top' | 'left' | 'right';

    // Calculate position based on placement
    switch (finalPlacement) {
      case 'bottom':
        top = triggerRect.bottom + offset;
        left = calculateHorizontalPosition(triggerRect, dropdownRect);
        break;
      case 'top':
        top = triggerRect.top - dropdownRect.height - offset;
        left = calculateHorizontalPosition(triggerRect, dropdownRect);
        break;
      case 'right':
        top = triggerRect.top;
        left = triggerRect.right + offset;
        break;
      case 'left':
        top = triggerRect.top;
        left = triggerRect.left - dropdownRect.width - offset;
        break;
    }

    // Ensure dropdown stays within viewport
    top = Math.max(8, Math.min(top, viewportHeight - dropdownRect.height - 8));
    left = Math.max(8, Math.min(left, viewportWidth - dropdownRect.width - 8));

    dropdownPosition = { top, left };

    // Set width
    if (width === 'trigger') {
      computedWidth = `${triggerRect.width}px`;
    } else {
      computedWidth = width;
    }
  }

  function calculateHorizontalPosition(triggerRect: DOMRect, dropdownRect: DOMRect): number {
    const viewportWidth = window.innerWidth;
    let left = 0;

    switch (align) {
      case 'start':
        left = triggerRect.left;
        break;
      case 'center':
        left = triggerRect.left + (triggerRect.width - dropdownRect.width) / 2;
        break;
      case 'end':
        left = triggerRect.right - dropdownRect.width;
        break;
    }

    // Adjust if overflowing viewport
    if (left + dropdownRect.width > viewportWidth - 8) {
      left = viewportWidth - dropdownRect.width - 8;
    }
    if (left < 8) {
      left = 8;
    }

    return left;
  }

  function handleClose() {
    open = false;
    dispatch('close');
  }

  function handleSelect(value: any) {
    dispatch('select', value);
    if (closeOnSelect) {
      handleClose();
    }
  }

  // Update position when opened or trigger changes
  run(() => {
    if (open && triggerRef) {
      updatePosition();
    }
  });

  // Update position on window resize/scroll
  onMount(() => {
    if (open) {
      window.addEventListener('resize', updatePosition);
      window.addEventListener('scroll', updatePosition, true);

      return () => {
        window.removeEventListener('resize', updatePosition);
        window.removeEventListener('scroll', updatePosition, true);
      };
    }
  });

  // Keyboard navigation
  const keyHandlers = {
    onEscape: handleClose,
  };
</script>

{#if open}
  <div
    bind:this={dropdownElement}
    use:portal={{ target: 'body', zIndex: 9999, useWrapper: false }}
    use:clickOutside={{
      enabled: open,
      callback: handleClose,
      excludeSelector: triggerRef ? `[data-dropdown-trigger="${triggerRef.id}"]` : undefined
    }}
    use:keyboardNav={keyHandlers}
    class="dropdown-container"
    style="
      top: {dropdownPosition.top}px;
      left: {dropdownPosition.left}px;
      width: {computedWidth};
      max-height: {maxHeight};
    "
    role="menu"
    transition:scale={{ duration: 150, start: 0.95 }}
  >
    {@render children?.({ handleSelect, })}
  </div>
{/if}

<style>
  .dropdown-container {
    position: fixed;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1),
                0 4px 6px -2px rgba(0, 0, 0, 0.05);
    overflow-y: auto;
    overflow-x: hidden;
    padding: 0.5rem 0;
    z-index: 9999;
  }

  /* Scrollbar styling */
  .dropdown-container::-webkit-scrollbar {
    width: 6px;
  }

  .dropdown-container::-webkit-scrollbar-track {
    background: transparent;
  }

  .dropdown-container::-webkit-scrollbar-thumb {
    background: #d1d5db;
    border-radius: 3px;
  }

  .dropdown-container::-webkit-scrollbar-thumb:hover {
    background: #9ca3af;
  }
</style>