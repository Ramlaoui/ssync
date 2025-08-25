<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  const dispatch = createEventDispatcher<{
    confirm: void;
    cancel: void;
  }>();

  export let show = false;
  export let title = 'Confirm Action';
  export let message = 'Are you sure you want to proceed?';
  export let confirmText = 'Confirm';
  export let cancelText = 'Cancel';
  export let confirmButtonClass = 'primary';
  export let stats: { file_count: number; size_mb: number; dangerous_path: boolean; gitignore_applied?: boolean } | null = null;

  function handleConfirm() {
    dispatch('confirm');
    show = false;
  }

  function handleCancel() {
    dispatch('cancel');
    show = false;
  }

  function handleBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      handleCancel();
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      handleCancel();
    } else if (event.key === 'Enter' && event.ctrlKey) {
      handleConfirm();
    }
  }
</script>

{#if show}
  <div 
    class="dialog-overlay" 
    on:click={handleBackdropClick} 
    on:keydown={handleKeydown}
    role="dialog" 
    aria-modal="true"
    aria-labelledby="dialog-title"
    aria-describedby="dialog-message"
  >
    <div class="dialog-container">
      <div class="dialog-header">
        <h2 id="dialog-title">{title}</h2>
        <button 
          class="dialog-close" 
          on:click={handleCancel}
          aria-label="Close dialog"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z" />
          </svg>
        </button>
      </div>

      <div class="dialog-content">
        <div id="dialog-message" class="dialog-message">
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
      </div>

      <div class="dialog-actions">
        <button 
          class="action-btn secondary" 
          on:click={handleCancel}
        >
          {cancelText}
        </button>
        <button 
          class="action-btn {confirmButtonClass}" 
          on:click={handleConfirm}
        >
          {confirmText}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .dialog-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fadeIn 0.2s ease;
  }

  .dialog-container {
    background: white;
    border-radius: 12px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
    max-width: 500px;
    width: 90vw;
    max-height: 90vh;
    overflow: hidden;
    animation: slideUp 0.2s ease;
    display: flex;
    flex-direction: column;
  }

  .dialog-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    flex-shrink: 0;
  }

  .dialog-header h2 {
    margin: 0;
    color: #374151;
    font-size: 1.25rem;
    font-weight: 600;
  }

  .dialog-close {
    background: none;
    border: none;
    padding: 0.5rem;
    border-radius: 6px;
    cursor: pointer;
    color: #6b7280;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }

  .dialog-close:hover {
    background: #f3f4f6;
    color: #374151;
  }

  .dialog-close svg {
    width: 20px;
    height: 20px;
  }

  .dialog-content {
    padding: 1.5rem;
    flex: 1;
    overflow-y: auto;
  }

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
    padding: 1.5rem;
    border-top: 1px solid #e5e7eb;
    justify-content: flex-end;
    flex-shrink: 0;
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

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes slideUp {
    from { 
      opacity: 0;
      transform: translateY(20px);
    }
    to { 
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* Mobile responsive */
  @media (max-width: 640px) {
    .dialog-container {
      width: 95vw;
      margin: 0.5rem;
    }

    .dialog-header,
    .dialog-content,
    .dialog-actions {
      padding: 1rem;
    }

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