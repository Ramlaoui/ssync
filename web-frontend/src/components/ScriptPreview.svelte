<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  
  const dispatch = createEventDispatcher<{
    launch: void;
    scriptChanged: { content: string };
  }>();

  export let generatedScript = '';
  export let selectedHost = '';
  export let sourceDir = '';
  export let launching = false;
  export let loading = false;

  let isEditing = false;
  let editableScript = '';

  // Sync editable script with generated script when it changes
  $: if (!isEditing && generatedScript !== editableScript) {
    editableScript = generatedScript;
  }

  function toggleEditMode(): void {
    if (isEditing) {
      // Save changes
      dispatch('scriptChanged', { content: editableScript });
      generatedScript = editableScript;
    } else {
      // Enter edit mode
      editableScript = generatedScript;
    }
    isEditing = !isEditing;
  }

  function handleScriptChange(event: Event): void {
    const target = event.target as HTMLTextAreaElement;
    editableScript = target.value;
  }

  function cancelEdit(): void {
    editableScript = generatedScript;
    isEditing = false;
  }

  function copyScript(): void {
    navigator.clipboard.writeText(generatedScript).then(() => {
      // Could add a toast notification here
      console.log('Script copied to clipboard');
    }).catch(err => {
      console.error('Failed to copy script:', err);
    });
  }

  function saveScript(): void {
    const blob = new Blob([generatedScript], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'slurm-job.sh';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function handleLaunch(): void {
    dispatch('launch');
  }

  function getScriptStats() {
    const lines = generatedScript.split('\n').length;
    const size = new Blob([generatedScript]).size;
    const hasConfig = selectedHost && sourceDir;
    
    return {
      lines,
      size,
      hasConfig,
      formattedSize: formatFileSize(size)
    };
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} bytes`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  $: stats = getScriptStats();
</script>

<div class="script-preview">
  <div class="preview-header">
    <div class="header-content">
      <h3>Generated Script Preview</h3>
      <div class="preview-stats">
        <span class="stat-item">
          <svg class="stat-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M14,17H7V15H14M17,13H7V11H17M17,9H7V7H17M19,3H5C3.89,3 3,3.89 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5C21,3.89 20.1,3 19,3Z"/>
          </svg>
          {stats.lines} lines
        </span>
        
        <span class="stat-item">
          <svg class="stat-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
          </svg>
          {stats.formattedSize}
        </span>
        
        {#if !stats.hasConfig}
          <span class="stat-item warning">
            <svg class="stat-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z"/>
            </svg>
            Missing config
          </span>
        {:else}
          <span class="stat-item success">
            <svg class="stat-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M17,9L12,14L7,9L8.41,7.59L12,11.17L15.59,7.59L17,9Z"/>
            </svg>
            Ready to launch
          </span>
        {/if}
      </div>
    </div>
  </div>
  
  <div class="preview-content">
    {#if generatedScript || editableScript}
      {#if isEditing}
        <div class="script-editor">
          <textarea
            class="script-editor-textarea"
            bind:value={editableScript}
            on:input={handleScriptChange}
            placeholder="Edit your SLURM script here..."
            disabled={launching}
          ></textarea>
        </div>
      {:else}
        <pre class="script-preview-code"><code>{generatedScript}</code></pre>
      {/if}
    {:else}
      <div class="empty-preview">
        <svg class="empty-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
        </svg>
        <div class="empty-text">
          <h4>Script preview will appear here</h4>
          <p>Fill in the configuration fields to generate a SLURM job script</p>
        </div>
      </div>
    {/if}
  </div>
  
  <div class="preview-actions">
    <button 
      type="button" 
      class="action-btn secondary" 
      on:click={copyScript}
      disabled={!generatedScript}
      title="Copy script to clipboard"
    >
      <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
        <path d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z"/>
      </svg>
      Copy
    </button>
    
    <button 
      type="button" 
      class="action-btn secondary" 
      on:click={saveScript}
      disabled={!generatedScript}
      title="Download script as file"
    >
      <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
        <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
      </svg>
      Save
    </button>
    
    <button 
      type="button" 
      class="action-btn {isEditing ? 'success' : 'secondary'}" 
      on:click={toggleEditMode}
      disabled={!generatedScript || launching}
      title={isEditing ? 'Save changes' : 'Edit script'}
    >
      {#if isEditing}
        <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M17,9L12,14L7,9L8.41,7.59L12,11.17L15.59,7.59L17,9Z"/>
        </svg>
        Save Edit
      {:else}
        <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z"/>
        </svg>
        Edit
      {/if}
    </button>
    
    {#if isEditing}
      <button 
        type="button" 
        class="action-btn danger" 
        on:click={cancelEdit}
        title="Cancel editing"
      >
        <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z"/>
        </svg>
        Cancel
      </button>
    {/if}
    
    <button 
      type="button" 
      class="action-btn primary launch-btn"
      on:click={handleLaunch}
      disabled={launching || loading || !stats.hasConfig}
      title={stats.hasConfig ? 'Launch the job' : 'Configure host and source directory first'}
    >
      {#if launching}
        <svg class="btn-icon loading-spinner" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,4V2A10,10 0 0,0 2,12H4A8,8 0 0,1 12,4Z"/>
        </svg>
        Launching...
      {:else}
        <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M8,5.14V19.14L19,12.14L8,5.14Z"/>
        </svg>
        Launch Job
      {/if}
    </button>
  </div>
</div>

<style>
  .script-preview {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: #1e1e2e;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
    min-height: 300px;
    max-height: 600px;
    position: relative;
  }

  .preview-header {
    background: linear-gradient(135deg, #2d3748 0%, #1a202c 100%);
    color: white;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    flex-shrink: 0;
  }

  .header-content {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
  }

  .preview-header h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: #f7fafc;
  }

  .preview-stats {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }

  .stat-item {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.8rem;
    color: rgba(255, 255, 255, 0.8);
    background: rgba(255, 255, 255, 0.1);
    padding: 0.375rem 0.75rem;
    border-radius: 6px;
    backdrop-filter: blur(10px);
    transition: all 0.2s ease;
  }

  .stat-item.warning {
    background: rgba(245, 158, 11, 0.2);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.3);
  }

  .stat-item.success {
    background: rgba(16, 185, 129, 0.2);
    color: #10b981;
    border: 1px solid rgba(16, 185, 129, 0.3);
  }

  .stat-icon {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  .preview-content {
    flex: 1;
    overflow: auto;
    background: #2d3748;
    min-height: 0;
    position: relative;
  }

  .preview-content::-webkit-scrollbar {
    width: 8px;
  }

  .preview-content::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.05);
  }

  .preview-content::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 4px;
  }

  .preview-content::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.3);
  }

  .script-preview-code {
    margin: 0;
    padding: 1.5rem;
    font-family: 'JetBrains Mono', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 0.9rem;
    line-height: 1.6;
    color: #e2e8f0;
    background: transparent;
    white-space: pre-wrap;
    word-wrap: break-word;
    min-height: 100%;
  }

  .script-preview-code code {
    color: #e2e8f0;
    background: transparent;
  }

  .script-editor {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .script-editor-textarea {
    flex: 1;
    margin: 0;
    padding: 1.5rem;
    font-family: 'JetBrains Mono', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 0.9rem;
    line-height: 1.6;
    color: #e2e8f0;
    background: #2d3748;
    border: none;
    outline: none;
    resize: none;
    white-space: pre;
    word-wrap: break-word;
    min-height: 200px;
  }

  .script-editor-textarea:focus {
    background: #374151;
  }

  .script-editor-textarea::placeholder {
    color: rgba(255, 255, 255, 0.5);
  }

  .empty-preview {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    padding: 2rem;
    color: rgba(255, 255, 255, 0.6);
    text-align: center;
  }

  .empty-icon {
    width: 4rem;
    height: 4rem;
    color: rgba(255, 255, 255, 0.3);
    margin-bottom: 1rem;
  }

  .empty-text h4 {
    margin: 0 0 0.5rem 0;
    font-size: 1.1rem;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.8);
  }

  .empty-text p {
    margin: 0;
    font-size: 0.9rem;
    line-height: 1.4;
    color: rgba(255, 255, 255, 0.6);
  }

  .preview-actions {
    padding: 1rem 1.5rem;
    background: #1a202c;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    display: flex;
    gap: 0.75rem;
    align-items: center;
    flex-shrink: 0;
  }

  .action-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 1rem;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    min-width: 0;
    white-space: nowrap;
  }

  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
  }

  .action-btn.secondary {
    background: rgba(255, 255, 255, 0.1);
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.2);
  }

  .action-btn.secondary:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.2);
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  }

  .action-btn.primary {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    color: white;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
  }

  .action-btn.primary:hover:not(:disabled) {
    background: linear-gradient(135deg, #059669 0%, #047857 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(16, 185, 129, 0.4);
  }

  .action-btn.success {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    color: white;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
  }

  .action-btn.success:hover:not(:disabled) {
    background: linear-gradient(135deg, #059669 0%, #047857 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(16, 185, 129, 0.4);
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

  .launch-btn {
    flex: 1;
    justify-content: center;
    font-weight: 600;
    min-height: 44px;
  }

  .btn-icon {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }

  .loading-spinner {
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* Mobile responsive */
  @media (max-width: 768px) {
    .script-preview {
      flex: none !important;
      max-height: none !important;
      min-height: auto !important;
      height: auto !important;
      border-radius: 8px;
      margin-bottom: 1rem;
      overflow: visible !important;
    }

    .preview-header {
      padding: 0.75rem 1rem;
    }

    .preview-content {
      flex: none !important;
      overflow: visible !important;
      max-height: 300px;
      min-height: 200px;
    }

    .header-content {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.75rem;
    }

    .preview-stats {
      flex-wrap: wrap;
      gap: 0.5rem;
      align-self: stretch;
    }

    .stat-item {
      font-size: 0.75rem;
      padding: 0.25rem 0.5rem;
      flex: 1;
      justify-content: center;
      min-width: 0;
    }

    .script-preview-code {
      padding: 1rem;
      font-size: 0.8rem;
      line-height: 1.5;
    }

    .empty-preview {
      padding: 1.5rem 1rem;
    }

    .empty-icon {
      width: 3rem;
      height: 3rem;
    }

    .empty-text h4 {
      font-size: 1rem;
    }

    .empty-text p {
      font-size: 0.85rem;
    }

    .preview-actions {
      padding: 0.75rem 1rem;
      gap: 0.5rem;
      flex-wrap: wrap;
      flex-shrink: 0 !important;
      position: relative;
      z-index: 10;
    }

    .action-btn {
      font-size: 0.8rem;
      padding: 0.5rem 0.75rem;
      min-height: 40px;
    }

    .action-btn.secondary {
      flex: 1;
    }

    .launch-btn {
      flex-basis: 100%;
      order: 1;
    }
  }

  @media (max-width: 480px) {
    .preview-actions {
      flex-direction: column;
    }

    .action-btn {
      width: 100%;
      justify-content: center;
    }
  }
</style>