<script lang="ts">
  import { run } from 'svelte/legacy';

  import { createEventDispatcher } from 'svelte';
  import Dialog from '../lib/components/ui/Dialog.svelte';

  const dispatch = createEventDispatcher();

  interface Props {
    isOpen?: boolean;
    script?: string;
    parameters?: any;
    selectedHost?: string;
  }

  let {
    isOpen = $bindable(false),
    script = '',
    parameters = {},
    selectedHost = ''
  }: Props = $props();

  let templateName = $state('');
  let templateDescription = $state('');

  function handleClose() {
    templateName = '';
    templateDescription = '';
    isOpen = false;
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
    handleClose();
  }

  // Reset form when dialog opens
  run(() => {
    if (isOpen) {
      templateName = '';
      templateDescription = '';
    }
  });

  // Handle Enter key in form
  function handleKeyPress(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey && templateName.trim()) {
      event.preventDefault();
      save();
    }
  }
</script>

<Dialog
  open={isOpen}
  onClose={handleClose}
  title="Save as Template"
  description="Save this script configuration for quick reuse"
  size="md"
>
  <div class="form-content">
    <div class="form-group">
      <label for="template-name">Template Name *</label>
      <input
        id="template-name"
        type="text"
        bind:value={templateName}
        placeholder="e.g., GPU Training Script"
        class="form-input"
        onkeypress={handleKeyPress}
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
></textarea>
    </div>

    <div class="form-group">
      <span class="section-label">Script Preview</span>
      <div class="script-preview">
        <pre>{script.split('\n').slice(0, 10).join('\n')}...</pre>
      </div>
    </div>

    <div class="form-group">
      <span class="section-label">Saved Parameters</span>
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

  {#snippet footer()}
    <div  class="dialog-footer">
      <button
        class="btn-secondary"
        onclick={handleClose}
      >
        Cancel
      </button>
      <button
        class="btn-primary"
        onclick={save}
        disabled={!templateName.trim()}
      >
        Save Template
      </button>
    </div>
  {/snippet}
</Dialog>

<style>
  .form-content {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .form-group {
    display: flex;
    flex-direction: column;
  }

  .form-group label,
  .form-group .section-label {
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