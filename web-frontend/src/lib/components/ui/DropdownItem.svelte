<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  const dispatch = createEventDispatcher<{ click: MouseEvent }>();

  
  interface Props {
    // Props
    disabled?: boolean;
    danger?: boolean;
    active?: boolean;
    href?: string | undefined;
    children?: import('svelte').Snippet;
  }

  let {
    disabled = false,
    danger = false,
    active = false,
    href = undefined,
    children
  }: Props = $props();

  function handleClick(event: MouseEvent) {
    if (disabled) {
      event.preventDefault();
      return;
    }
    dispatch('click', event);
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (disabled) return;

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      dispatch('click', event as any);
    }
  }

  // Determine element type
  const element = href && !disabled ? 'a' : 'button';
</script>

<svelte:element
  this={element}
  class="dropdown-item"
  class:disabled
  class:danger
  class:active
  {href}
  role="menuitem"
  tabindex={disabled ? -1 : 0}
  aria-disabled={disabled}
  onclick={handleClick}
  onkeydown={handleKeyDown}
  type={element === 'button' ? 'button' : undefined}
>
  {@render children?.()}
</svelte:element>

<style>
  .dropdown-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
    padding: 0.625rem 1rem;
    font-size: 0.875rem;
    color: #374151;
    text-align: left;
    text-decoration: none;
    background: transparent;
    border: none;
    cursor: pointer;
    transition: all 0.15s;
    outline: none;
  }

  .dropdown-item:hover:not(.disabled) {
    background: #f3f4f6;
    color: #111827;
  }

  .dropdown-item:focus {
    background: #f3f4f6;
    color: #111827;
  }

  .dropdown-item.active {
    background: #eff6ff;
    color: #1d4ed8;
  }

  .dropdown-item.danger {
    color: #dc2626;
  }

  .dropdown-item.danger:hover:not(.disabled) {
    background: #fef2f2;
    color: #991b1b;
  }

  .dropdown-item.disabled {
    color: #9ca3af;
    cursor: not-allowed;
    opacity: 0.5;
  }

  /* Icon spacing */
  .dropdown-item :global(svg) {
    width: 1rem;
    height: 1rem;
    flex-shrink: 0;
  }

  /* Keyboard indicator */
  .dropdown-item:focus-visible {
    outline: 2px solid #3b82f6;
    outline-offset: -2px;
  }
</style>