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
    color: var(--popover-foreground);
    text-align: left;
    text-decoration: none;
    background: transparent;
    border: none;
    cursor: pointer;
    transition: all 0.15s;
    outline: none;
  }

  .dropdown-item:hover:not(.disabled) {
    background: var(--secondary);
    color: var(--foreground);
  }

  .dropdown-item:focus {
    background: var(--secondary);
    color: var(--foreground);
  }

  .dropdown-item.active {
    background: var(--info-bg);
    color: var(--accent);
  }

  .dropdown-item.danger {
    color: var(--destructive);
  }

  .dropdown-item.danger:hover:not(.disabled) {
    background: var(--error-bg);
    color: var(--destructive);
  }

  .dropdown-item.disabled {
    color: var(--muted-foreground);
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
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }
</style>