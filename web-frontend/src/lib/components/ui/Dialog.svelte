<script lang="ts">
  import { createBubbler, stopPropagation } from 'svelte/legacy';

  const bubble = createBubbler();
  import Overlay from './Overlay.svelte';
  import { fly } from 'svelte/transition';
  import { X } from 'lucide-svelte';
  import { createEventDispatcher } from 'svelte';

  const dispatch = createEventDispatcher<{ close: void }>();

  

  
  interface Props {
    // All Overlay props
    open?: boolean;
    closeOnBackdropClick?: boolean;
    closeOnEscape?: boolean;
    // Dialog-specific props
    title?: string;
    description?: string;
    size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
    showCloseButton?: boolean;
    headerClass?: string;
    contentClass?: string;
    footerClass?: string;
    header?: import('svelte').Snippet;
    children?: import('svelte').Snippet;
    footer?: import('svelte').Snippet;
  }

  let {
    open = $bindable(false),
    closeOnBackdropClick = true,
    closeOnEscape = true,
    title = '',
    description = '',
    size = 'md',
    showCloseButton = true,
    headerClass = '',
    contentClass = '',
    footerClass = '',
    header,
    children,
    footer
  }: Props = $props();

  // Size mapping
  const sizeClasses = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl',
    full: 'max-w-full mx-4',
  };

  function handleClose() {
    open = false;
    dispatch('close');
  }
</script>

<Overlay
  {open}
  {closeOnBackdropClick}
  {closeOnEscape}
  on:close={handleClose}
>
  <div
    class="dialog-container {sizeClasses[size]}"
    onclick={stopPropagation(bubble('click'))}
    onkeydown={() => {}}
    role="dialog"
    tabindex="-1"
    aria-modal="true"
    transition:fly={{ y: 20, duration: 200 }}
  >
    {#if header || title || showCloseButton}
      <div class="dialog-header {headerClass}">
        {#if header}
          {@render header?.()}
        {:else if title}
          <div class="dialog-title-wrapper">
            {#if title}
              <h2 class="dialog-title">{title}</h2>
            {/if}
            {#if description}
              <p class="dialog-description">{description}</p>
            {/if}
          </div>
        {/if}

        {#if showCloseButton}
          <button
            class="dialog-close-button"
            onclick={handleClose}
            aria-label="Close dialog"
            type="button"
          >
            <X class="w-5 h-5" />
          </button>
        {/if}
      </div>
    {/if}

    <div class="dialog-content {contentClass}">
      {@render children?.()}
    </div>

    {#if footer}
      <div class="dialog-footer {footerClass}">
        {@render footer?.()}
      </div>
    {/if}
  </div>
</Overlay>

<style>
  .dialog-container {
    position: relative;
    background: white;
    border-radius: 0.75rem;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1),
                0 10px 10px -5px rgba(0, 0, 0, 0.04);
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    width: 90%;
    margin: 1rem;
  }

  .dialog-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    gap: 1rem;
  }

  .dialog-title-wrapper {
    flex: 1;
    min-width: 0;
  }

  .dialog-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: #111827;
    margin: 0;
  }

  .dialog-description {
    font-size: 0.875rem;
    color: #6b7280;
    margin-top: 0.25rem;
    margin-bottom: 0;
  }

  .dialog-close-button {
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

  .dialog-close-button:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .dialog-close-button:focus {
    outline: 2px solid #3b82f6;
    outline-offset: 2px;
  }

  .dialog-content {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
    min-height: 0;
  }

  .dialog-footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.75rem;
    padding: 1.5rem;
    border-top: 1px solid #e5e7eb;
    flex-wrap: wrap;
  }

  /* Responsive */
  @media (max-width: 640px) {
    .dialog-container {
      width: 100vw;
      height: 100vh;
      max-height: 100vh;
      border-radius: 0;
      margin: 0;
    }

    .dialog-header,
    .dialog-content,
    .dialog-footer {
      padding: 1rem;
    }

    .dialog-footer {
      flex-direction: column-reverse;
    }

    .dialog-footer :global(button) {
      width: 100%;
    }
  }
</style>