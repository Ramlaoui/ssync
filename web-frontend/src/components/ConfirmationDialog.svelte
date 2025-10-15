<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Dialog from '../lib/components/ui/Dialog.svelte';

  const dispatch = createEventDispatcher<{
    confirm: void;
    cancel: void;
  }>();

  interface Props {
    show?: boolean;
    title?: string;
    message?: string;
    confirmText?: string;
    cancelText?: string;
    confirmButtonClass?: string;
    stats?: { file_count: number; size_mb: number; dangerous_path: boolean; gitignore_applied?: boolean } | null;
  }

  let {
    show = $bindable(false),
    title = 'Confirm Action',
    message = 'Are you sure you want to proceed?',
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    confirmButtonClass = 'primary',
    stats = null
  }: Props = $props();

  function handleConfirm() {
    dispatch('confirm');
    show = false;
  }

  function handleCancel() {
    dispatch('cancel');
    show = false;
  }

  function handleClose() {
    handleCancel();
  }
</script>

<Dialog
  open={show}
  {title}
  size="md"
  onClose={handleClose}
>
  <div class="dialog-message">
    {message}
  </div>

  {#if stats}
    <div class="directory-stats">
      <h3>Directory Information</h3>
      <div class="stats-grid">
        <div class="stat-item">
          <div class="stat-label">Files:</div>
          <div class="stat-value">{stats.file_count.toLocaleString()}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Size:</div>
          <div class="stat-value">{stats.size_mb.toFixed(2)} MB</div>
        </div>
        {#if stats.dangerous_path}
          <div class="stat-item warning">
            <div class="stat-label">⚠️ System Directory:</div>
            <div class="stat-value">Yes</div>
          </div>
        {/if}
        {#if stats.gitignore_applied}
          <div class="stat-item info">
            <div class="stat-label">📋 .gitignore Applied:</div>
            <div class="stat-value">Yes</div>
          </div>
        {/if}
      </div>
    </div>
  {/if}

  <div class="dialog-notice">
    <svg class="notice-icon" viewBox="0 0 24 24" fill="currentColor">
      <path d="M11,9H13V7H11M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M11,17H13V11H11V17Z"/>
    </svg>
    <p>
      This action cannot be undone. Large directories may take considerable time to sync and could impact server performance.
    </p>
  </div>

  {#snippet footer()}
    <div  class="dialog-actions">
      <button
        class="action-btn secondary"
        onclick={handleCancel}
      >
        {cancelText}
      </button>
      <button
        class="action-btn {confirmButtonClass}"
        onclick={handleConfirm}
      >
        {confirmText}
      </button>
    </div>
  {/snippet}
</Dialog>

<style>
  .dialog-message {
    color: #374151;
    line-height: 1.6;
    margin-bottom: 1rem;
  }

  .directory-stats {
    background: #f8fafc;
    border: 1px solid #e1e5e9;
    border-radius: 8px;
    padding: 1rem;
    margin: 1rem 0;
  }

  .directory-stats h3 {
    margin: 0 0 0.75rem 0;
    color: #374151;
    font-size: 0.95rem;
    font-weight: 600;
  }

  .stats-grid {
    display: grid;
    gap: 0.5rem;
    grid-template-columns: 1fr;
  }

  .stat-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.25rem 0;
  }

  .stat-item.warning {
    color: #d97706;
    font-weight: 500;
  }

  .stat-item.info {
    color: #2563eb;
    font-weight: 500;
  }

  .stat-label {
    font-size: 0.9rem;
    color: #6b7280;
  }

  .stat-value {
    font-size: 0.9rem;
    font-weight: 500;
    color: #374151;
  }

  .stat-item.warning .stat-value {
    color: #d97706;
  }

  .stat-item.info .stat-value {
    color: #2563eb;
  }

  .dialog-notice {
    display: flex;
    gap: 0.75rem;
    background: #fef3c7;
    border: 1px solid #fbbf24;
    border-radius: 8px;
    padding: 1rem;
    margin-top: 1rem;
  }

  .notice-icon {
    width: 20px;
    height: 20px;
    color: #d97706;
    flex-shrink: 0;
    margin-top: 0.1rem;
  }

  .dialog-notice p {
    margin: 0;
    font-size: 0.9rem;
    color: #92400e;
    line-height: 1.5;
  }

  .dialog-actions {
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

  .action-btn.secondary {
    background: #f3f4f6;
    color: #374151;
    border: 1px solid #d1d5db;
  }

  .action-btn.secondary:hover {
    background: #e5e7eb;
    transform: translateY(-1px);
  }

  .action-btn.primary {
    background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
    color: white;
    box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
  }

  .action-btn.primary:hover {
    background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(239, 68, 68, 0.4);
  }

  /* Mobile responsive */
  @media (max-width: 640px) {
    .dialog-actions {
      flex-direction: column;
    }

    .action-btn {
      width: 100%;
    }

    .stats-grid {
      gap: 0.25rem;
    }
  }
</style>