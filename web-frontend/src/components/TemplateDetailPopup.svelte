<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { fade, fly } from 'svelte/transition';
  import { X, Download, Trash2 } from 'lucide-svelte';

  const dispatch = createEventDispatcher();

  export let isOpen = false;
  export let template = null;

  function close() {
    dispatch('close');
  }

  function loadTemplate() {
    dispatch('load', template);
  }

  function deleteTemplate() {
    dispatch('delete', template.id);
  }
</script>

{#if isOpen && template}
  <div class="template-detail-backdrop" on:click={close} transition:fade={{ duration: 200 }}>
    <div class="template-detail-popup" on:click|stopPropagation transition:fly={{ y: 50, duration: 300, opacity: 0.8 }}>
      <div class="detail-popup-header">
        <h3>{template.name}</h3>
        <button
          class="close-btn"
          on:click={close}
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <div class="detail-popup-content">
        {#if template.description}
          <div class="detail-section">
            <h4>Description</h4>
            <p class="template-detail-description">{template.description}</p>
          </div>
        {/if}

        <div class="detail-section">
          <h4>Script Content</h4>
          <div class="script-content-preview">
            <pre><code>{template.script_content}</code></pre>
          </div>
        </div>

        <div class="detail-section">
          <h4>Parameters</h4>
          <div class="parameter-grid">
            <div class="param-item">
              <span class="param-label">Host</span>
              <span class="param-value">{template.parameters.selectedHost || 'Not set'}</span>
            </div>
            <div class="param-item">
              <span class="param-label">Directory</span>
              <span class="param-value">{template.parameters.sourceDir || 'Not set'}</span>
            </div>
            <div class="param-item">
              <span class="param-label">Time</span>
              <span class="param-value">{template.parameters.time || '60'} minutes</span>
            </div>
            <div class="param-item">
              <span class="param-label">Memory</span>
              <span class="param-value">{template.parameters.memory || '4'}GB</span>
            </div>
            <div class="param-item">
              <span class="param-label">CPUs</span>
              <span class="param-value">{template.parameters.cpus || '1'}</span>
            </div>
            {#if template.parameters.gpus}
              <div class="param-item">
                <span class="param-label">GPUs</span>
                <span class="param-value">{template.parameters.gpus}</span>
              </div>
            {/if}
            {#if template.parameters.partition}
              <div class="param-item">
                <span class="param-label">Partition</span>
                <span class="param-value">{template.parameters.partition}</span>
              </div>
            {/if}
            {#if template.parameters.account}
              <div class="param-item">
                <span class="param-label">Account</span>
                <span class="param-value">{template.parameters.account}</span>
              </div>
            {/if}
          </div>
        </div>

        <div class="detail-section">
          <h4>Usage Statistics</h4>
          <div class="stats-grid">
            <div class="stat-item">
              <span class="stat-label">Created</span>
              <span class="stat-value">{new Date(template.created_at).toLocaleDateString()}</span>
            </div>
            {#if template.last_used}
              <div class="stat-item">
                <span class="stat-label">Last Used</span>
                <span class="stat-value">{new Date(template.last_used).toLocaleDateString()}</span>
              </div>
            {/if}
            <div class="stat-item">
              <span class="stat-label">Times Used</span>
              <span class="stat-value">{template.use_count}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="detail-popup-footer">
        <button
          class="btn-secondary"
          on:click={close}
        >
          Close
        </button>
        <button
          class="btn-danger"
          on:click={deleteTemplate}
        >
          <Trash2 class="w-4 h-4" />
          Delete
        </button>
        <button
          class="btn-primary"
          on:click={loadTemplate}
        >
          <Download class="w-4 h-4" />
          Load Template
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  /* Template Detail Popup */
  .template-detail-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10001;
  }

  .template-detail-popup {
    background: white;
    border-radius: 12px;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
    max-width: 700px;
    width: 90%;
    max-height: 85vh;
    display: flex;
    flex-direction: column;
  }

  .detail-popup-header {
    padding: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .detail-popup-header h3 {
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

  .detail-popup-content {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
  }

  .detail-section {
    margin-bottom: 1.5rem;
  }

  .detail-section:last-child {
    margin-bottom: 0;
  }

  .detail-section h4 {
    font-size: 1rem;
    font-weight: 600;
    color: #111827;
    margin: 0 0 0.75rem 0;
  }

  .template-detail-description {
    color: #6b7280;
    line-height: 1.5;
    margin: 0;
  }

  .script-content-preview {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    overflow: hidden;
  }

  .script-content-preview pre {
    margin: 0;
    padding: 1rem;
    overflow-x: auto;
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 0.8rem;
    line-height: 1.4;
    color: #374151;
  }

  .parameter-grid,
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 0.75rem;
  }

  .param-item,
  .stat-item {
    background: #f9fafb;
    border-radius: 6px;
    padding: 0.75rem;
  }

  .param-label,
  .stat-label {
    display: block;
    font-size: 0.8rem;
    font-weight: 500;
    color: #6b7280;
    margin-bottom: 0.25rem;
  }

  .param-value,
  .stat-value {
    font-size: 0.9rem;
    color: #111827;
    font-weight: 500;
  }

  .detail-popup-footer {
    padding: 1.5rem;
    border-top: 1px solid #e5e7eb;
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
  }

  .btn-primary,
  .btn-secondary,
  .btn-danger {
    padding: 0.5rem 1rem;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .btn-primary {
    background: #3b82f6;
    color: white;
    border: none;
  }

  .btn-primary:hover {
    background: #2563eb;
  }

  .btn-secondary {
    background: white;
    color: #374151;
    border: 1px solid #d1d5db;
  }

  .btn-secondary:hover {
    background: #f9fafb;
  }

  .btn-danger {
    background: #dc2626;
    color: white;
    border: none;
  }

  .btn-danger:hover {
    background: #b91c1c;
  }
</style>