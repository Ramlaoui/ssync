<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { X } from 'lucide-svelte';

  const dispatch = createEventDispatcher();

  export let isOpen = false;
  export let script = '';
  export let parameters = {};
  export let selectedHost = '';

  let templateName = '';
  let templateDescription = '';

  function close() {
    templateName = '';
    templateDescription = '';
    dispatch('close');
  }

  function save() {
    if (!templateName.trim()) {
      alert('Please enter a template name');
      return;
    }

    const template = {
      name: templateName.trim(),
      description: templateDescription.trim(),
      script_content: script,
      parameters: {
        ...parameters,
        selectedHost,
        sourceDir: parameters.sourceDir
      }
    };

    dispatch('save', template);
    close();
  }

  // Reset form when dialog opens
  $: if (isOpen) {
    templateName = '';
    templateDescription = '';
  }
</script>

{#if isOpen}
  <div class="modal-backdrop" on:click={close}>
    <div class="save-template-dialog" on:click|stopPropagation>
      <div class="dialog-header">
        <h3>Save as Template</h3>
        <button
          class="close-btn"
          on:click={close}
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <div class="dialog-content">
        <div class="form-group">
          <label for="template-name">Template Name *</label>
          <input
            id="template-name"
            type="text"
            bind:value={templateName}
            placeholder="e.g., GPU Training Script"
            class="form-input"
          />
        </div>

        <div class="form-group">
          <label for="template-description">Description (optional)</label>
          <textarea
            id="template-description"
            bind:value={templateDescription}
            placeholder="Describe what this script does..."
            class="form-textarea"
            rows="3"
          />
        </div>

        <div class="form-group">
          <label>Script Preview</label>
          <div class="script-preview">
            <pre>{script.split('\n').slice(0, 10).join('\n')}...</pre>
          </div>
        </div>

        <div class="form-group">
          <label>Saved Parameters</label>
          <div class="saved-params">
            <div class="param-row">
              <span class="param-label">Host:</span>
              <span class="param-value">{selectedHost || 'Not selected'}</span>
            </div>
            <div class="param-row">
              <span class="param-label">Directory:</span>
              <span class="param-value">{parameters.sourceDir || 'Not selected'}</span>
            </div>
            <div class="param-row">
              <span class="param-label">Time:</span>
              <span class="param-value">{parameters.time || '60'} minutes</span>
            </div>
            <div class="param-row">
              <span class="param-label">Memory:</span>
              <span class="param-value">{parameters.memory || '4'}GB</span>
            </div>
            <div class="param-row">
              <span class="param-label">CPUs:</span>
              <span class="param-value">{parameters.cpus || '1'}</span>
            </div>
            {#if parameters.gpus}
              <div class="param-row">
                <span class="param-label">GPUs:</span>
                <span class="param-value">{parameters.gpus}</span>
              </div>
            {/if}
          </div>
        </div>
      </div>

      <div class="dialog-footer">
        <button
          class="btn-secondary"
          on:click={close}
        >
          Cancel
        </button>
        <button
          class="btn-primary"
          on:click={save}
          disabled={!templateName.trim()}
        >
          Save Template
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
  }

  .save-template-dialog {
    background: white;
    border-radius: 12px;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
    max-width: 500px;
    width: 90%;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
  }

  .dialog-header {
    padding: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .dialog-header h3 {
    font-size: 1.25rem;
    font-weight: 600;
    color: #111827;
    margin: 0;
  }

  .close-btn {
    background: none;
    border: none;
    padding: 0.5rem;
    border-radius: 6px;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .dialog-content {
    padding: 1.5rem;
    overflow-y: auto;
    flex: 1;
  }

  .form-group {
    margin-bottom: 1.25rem;
  }

  .form-group label {
    display: block;
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
    margin-bottom: 0.5rem;
  }

  .form-input,
  .form-textarea {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.875rem;
    transition: all 0.2s;
  }

  .form-input:focus,
  .form-textarea:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .form-textarea {
    resize: vertical;
    font-family: inherit;
  }

  .script-preview {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 1rem;
    max-height: 200px;
    overflow-y: auto;
  }

  .script-preview pre {
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 0.8rem;
    color: #4b5563;
    margin: 0;
  }

  .saved-params {
    background: #f9fafb;
    border-radius: 6px;
    padding: 1rem;
  }

  .param-row {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.5rem;
    font-size: 0.85rem;
  }

  .param-row:last-child {
    margin-bottom: 0;
  }

  .param-label {
    font-weight: 500;
    color: #374151;
  }

  .param-value {
    color: #6b7280;
  }

  .dialog-footer {
    padding: 1.5rem;
    border-top: 1px solid #e5e7eb;
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
  }

  .btn-primary,
  .btn-secondary {
    padding: 0.5rem 1rem;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn-primary {
    background: #3b82f6;
    color: white;
    border: none;
  }

  .btn-primary:hover:not(:disabled) {
    background: #2563eb;
  }

  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-secondary {
    background: white;
    color: #374151;
    border: 1px solid #d1d5db;
  }

  .btn-secondary:hover {
    background: #f9fafb;
  }
</style>