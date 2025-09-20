<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { fade, fly } from 'svelte/transition';
  import { X, Download, Trash2, FileText } from 'lucide-svelte';

  const dispatch = createEventDispatcher();

  export let isOpen = false;
  export let scriptTemplates = [];

  function closeTemplates() {
    dispatch('close');
  }

  function selectTemplate(template) {
    dispatch('select', template);
  }

  function loadTemplate(template) {
    dispatch('load', template);
  }

  function deleteTemplate(templateId) {
    dispatch('delete', templateId);
  }
</script>

{#if isOpen}
  <div class="template-sidebar-backdrop" on:click={closeTemplates} transition:fade={{ duration: 200 }}>
    <div class="template-sidebar" on:click|stopPropagation transition:fly={{ x: 400, duration: 300, opacity: 0.8 }}>
      <div class="sidebar-header">
        <h3>Script Templates</h3>
        <button
          class="close-btn"
          on:click={closeTemplates}
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <div class="sidebar-content">
        {#if scriptTemplates.length === 0}
          <div class="empty-state">
            <FileText class="w-12 h-12 text-gray-400 mx-auto mb-3" />
            <p class="text-gray-600 mb-2">No templates saved yet</p>
            <p class="text-sm text-gray-500">Save your frequently used scripts as templates for quick reuse</p>
          </div>
        {:else}
          <div class="template-list">
            {#each scriptTemplates as template}
              <div class="template-list-item" on:click={() => selectTemplate(template)}>
                <div class="template-item-header">
                  <h4 class="template-item-name">{template.name}</h4>
                  <div class="template-item-actions" on:click|stopPropagation>
                    <button
                      class="template-action-btn"
                      on:click={() => loadTemplate(template)}
                      title="Load template"
                    >
                      <Download class="w-3.5 h-3.5" />
                    </button>
                    <button
                      class="template-action-btn delete"
                      on:click={() => deleteTemplate(template.id)}
                      title="Delete template"
                    >
                      <Trash2 class="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {#if template.description}
                  <p class="template-item-description">{template.description}</p>
                {/if}

                <div class="template-item-meta">
                  <span class="meta-chip">{template.parameters.time || '60'}m</span>
                  <span class="meta-chip">{template.parameters.memory || '4'}GB</span>
                  <span class="meta-chip">{template.parameters.cpus || '1'}CPU</span>
                  {#if template.parameters.gpus}
                    <span class="meta-chip">{template.parameters.gpus}GPU</span>
                  {/if}
                  <span class="meta-usage">Used {template.use_count} times</span>
                </div>

                <div class="template-item-preview">
                  <code>{template.script_content.split('\n')[0] || '#!/bin/bash'}...</code>
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  /* Template Sidebar */
  .template-sidebar-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.3);
    z-index: 9999;
  }

  .template-sidebar {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 400px;
    max-width: 90vw;
    background: white;
    box-shadow: -4px 0 15px rgba(0, 0, 0, 0.1);
    display: flex;
    flex-direction: column;
    z-index: 10000;
  }

  .sidebar-header {
    padding: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: white;
  }

  .sidebar-header h3 {
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

  .sidebar-content {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
  }

  .empty-state {
    text-align: center;
    padding: 3rem 1.5rem;
  }

  .template-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .template-list-item {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .template-list-item:hover {
    background: #f3f4f6;
    border-color: #d1d5db;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  }

  .template-item-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;
  }

  .template-item-name {
    font-size: 0.95rem;
    font-weight: 600;
    color: #111827;
    margin: 0;
  }

  .template-item-actions {
    display: flex;
    gap: 0.25rem;
  }

  .template-action-btn {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 0.375rem;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.2s;
  }

  .template-action-btn:hover {
    background: #f3f4f6;
    color: #111827;
    border-color: #d1d5db;
  }

  .template-action-btn.delete:hover {
    background: #fef2f2;
    color: #dc2626;
    border-color: #fecaca;
  }

  .template-item-description {
    font-size: 0.8rem;
    color: #6b7280;
    margin: 0 0 0.5rem 0;
    line-height: 1.4;
  }

  .template-item-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    margin-bottom: 0.5rem;
  }

  .meta-chip {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    padding: 0.125rem 0.375rem;
    font-size: 0.7rem;
    color: #6b7280;
  }

  .meta-usage {
    font-size: 0.7rem;
    color: #9ca3af;
    margin-left: auto;
  }

  .template-item-preview {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    padding: 0.5rem;
  }

  .template-item-preview code {
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 0.7rem;
    color: #4b5563;
  }
</style>