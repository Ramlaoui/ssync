<script lang="ts">
  import Dialog from './Dialog.svelte';
  import { createEventDispatcher } from 'svelte';
  import type { Snippet } from 'svelte';

  const dispatch = createEventDispatcher<{
    submit: any;
    cancel: void;
  }>();

  interface Props {
    // All Dialog props
    open?: boolean;
    title?: string;
    description?: string;
    size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
    closeOnBackdropClick?: boolean;
    closeOnEscape?: boolean;
    // Form-specific props
    submitText?: string;
    cancelText?: string;
    loading?: boolean;
    disabled?: boolean;
    submitButtonClass?: string;
    children?: Snippet;
  }

  let {
    open = $bindable(false),
    title = '',
    description = '',
    size = 'md',
    closeOnBackdropClick = false,
    closeOnEscape = true,
    submitText = 'Submit',
    cancelText = 'Cancel',
    loading = false,
    disabled = false,
    submitButtonClass = 'primary',
    children
  }: Props = $props();

  function handleClose() {
    if (!loading) {
      open = false;
      dispatch('cancel');
    }
  }

  function handleSubmit(event: Event) {
    event.preventDefault();
    if (!loading && !disabled) {
      dispatch('submit');
    }
  }
</script>

{#snippet formFooter()}
  <div class="form-actions">
    <button
      type="button"
      class="action-btn secondary"
      onclick={handleClose}
      disabled={loading}
    >
      {cancelText}
    </button>
    <button
      type="submit"
      class="action-btn {submitButtonClass}"
      disabled={loading || disabled}
    >
      {#if loading}
        <svg class="spinner" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path
            class="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
        <span>Processing...</span>
      {:else}
        {submitText}
      {/if}
    </button>
  </div>
{/snippet}

<Dialog
  bind:open
  {title}
  {description}
  {size}
  {closeOnBackdropClick}
  {closeOnEscape}
  on:close={handleClose}
  footer={formFooter}
>
  <form onsubmit={handleSubmit}>
    {@render children?.()}
  </form>
</Dialog>

<style>
  form {
    display: contents;
  }

  .form-actions {
    display: flex;
    gap: 0.75rem;
    justify-content: flex-end;
  }

  .action-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 1.25rem;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    min-width: 80px;
    justify-content: center;
  }

  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .action-btn.secondary {
    background: #f3f4f6;
    color: #374151;
    border: 1px solid #d1d5db;
  }

  .action-btn.secondary:hover:not(:disabled) {
    background: #e5e7eb;
    transform: translateY(-1px);
  }

  .action-btn.primary {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
  }

  .action-btn.primary:hover:not(:disabled) {
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(59, 130, 246, 0.4);
  }

  .action-btn.danger {
    background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
    color: white;
    box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
  }

  .action-btn.danger:hover:not(:disabled) {
    background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(239, 68, 68, 0.4);
  }

  .spinner {
    width: 16px;
    height: 16px;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }

  /* Mobile responsive */
  @media (max-width: 640px) {
    .form-actions {
      flex-direction: column;
    }

    .action-btn {
      width: 100%;
    }
  }
</style>