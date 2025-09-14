<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { fly, slide } from 'svelte/transition';
  import { api } from '../services/api';
  import type { WatcherAction } from '../types/watchers';
  import { Plus, X, Eye, Zap, Save, ChevronDown, ChevronRight } from 'lucide-svelte';

  export let jobId: string;
  export let hostname: string;
  export let isVisible = false;

  const dispatch = createEventDispatcher();

  // Smart defaults for immediate creation
  let watcherName = `Watcher for Job ${jobId}`;
  let pattern = '';
  let interval = 30;
  let watcherOutputType: 'stdout' | 'stderr' | 'both' = 'stdout';
  let actions: WatcherAction[] = [{
    type: 'log_event',
    params: { message: 'Pattern matched in job output' }
  }];

  // Progressive disclosure states
  let showAdvanced = false;
  let showPatternHelp = false;
  let showJobOutput = false;
  let showTemplates = false;

  // Advanced options
  let captures: string[] = [];
  let condition = '';
  let maxTriggers = 10;
  let timerModeEnabled = false;
  let timerInterval = 30;

  // UI state
  let isSubmitting = false;
  let error: string | null = null;
  let jobOutput = '';
  let loadingOutput = false;

  // Quick templates for common patterns
  const quickTemplates = [
    {
      name: 'Error Detection',
      pattern: '(error|ERROR|Error)',
      description: 'Catch any error messages'
    },
    {
      name: 'Progress Tracking',
      pattern: '(\\d+)% complete',
      description: 'Track percentage progress'
    },
    {
      name: 'GPU Memory',
      pattern: 'GPU memory: (\\d+)MB',
      description: 'Monitor GPU memory usage'
    },
    {
      name: 'Loss Tracking',
      pattern: 'loss: ([\\d\\.]+)',
      description: 'Track training loss values'
    }
  ];

  function applyTemplate(template: any) {
    pattern = template.pattern;
    watcherName = `${template.name} - Job ${jobId}`;
    showTemplates = false;
  }

  async function fetchJobOutput() {
    if (loadingOutput || !showJobOutput) return;

    loadingOutput = true;
    try {
      const response = await api.get(`/api/jobs/${jobId}/output`, {
        params: {
          host: hostname,
          type: watcherOutputType,
          lines: 50
        }
      });
      jobOutput = response.data.content || 'No output available';
    } catch (err) {
      jobOutput = 'Failed to load job output';
    } finally {
      loadingOutput = false;
    }
  }

  function addSimpleAction() {
    actions = [...actions, {
      type: 'log_event',
      params: { message: 'New action triggered' }
    }];
  }

  function removeAction(index: number) {
    actions = actions.filter((_, i) => i !== index);
  }

  async function createWatcher() {
    if (!pattern.trim()) {
      error = 'Pattern is required';
      return;
    }

    isSubmitting = true;
    error = null;

    try {
      const watcherData = {
        name: watcherName,
        job_id: jobId,
        hostname: hostname,
        pattern: pattern,
        interval_seconds: interval,
        captures: captures.filter(c => c.trim()),
        condition: condition.trim() || null,
        actions: actions,
        max_triggers: maxTriggers,
        output_type: watcherOutputType,
        timer_mode_enabled: timerModeEnabled,
        timer_interval_seconds: timerInterval
      };

      await api.post('/api/watchers', watcherData);
      dispatch('created');
      close();
    } catch (err: any) {
      error = err.response?.data?.detail || 'Failed to create watcher';
    } finally {
      isSubmitting = false;
    }
  }

  function close() {
    isVisible = false;
    dispatch('close');
  }

  // Auto-fetch job output when output viewer is opened
  $: if (showJobOutput && !jobOutput && !loadingOutput) {
    fetchJobOutput();
  }
</script>

{#if isVisible}
  <div class="watcher-creator" transition:slide={{ duration: 300 }}>
    <div class="creator-header">
      <div class="header-info">
        <h3>Create Watcher</h3>
        <span class="job-info">Job #{jobId} on {hostname}</span>
      </div>
      <button class="close-btn" on:click={close}>
        <X class="w-4 h-4" />
      </button>
    </div>

    {#if error}
      <div class="error-message" transition:slide={{ duration: 200 }}>
        {error}
      </div>
    {/if}

    <div class="creator-content">
      <!-- Quick Start Form -->
      <div class="quick-form">
        <div class="form-row">
          <div class="form-group flex-1">
            <label for="watcher-name">Watcher Name</label>
            <input
              id="watcher-name"
              type="text"
              bind:value={watcherName}
              placeholder="Enter watcher name"
              class="form-input"
            />
          </div>
        </div>

        <div class="form-row">
          <div class="form-group flex-1">
            <label for="pattern">
              Pattern to Watch For
              <button
                class="help-toggle"
                on:click={() => showTemplates = !showTemplates}
              >
                <Zap class="w-3 h-3" />
                Templates
              </button>
            </label>
            <input
              id="pattern"
              type="text"
              bind:value={pattern}
              placeholder="Enter regex pattern (e.g., error|ERROR)"
              class="form-input"
              class:error={error && !pattern.trim()}
            />
            {#if showTemplates}
              <div class="template-suggestions" transition:slide={{ duration: 200 }}>
                {#each quickTemplates as template}
                  <button
                    class="template-suggestion"
                    on:click={() => applyTemplate(template)}
                  >
                    <strong>{template.name}</strong>
                    <span>{template.description}</span>
                    <code>{template.pattern}</code>
                  </button>
                {/each}
              </div>
            {/if}
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="interval">Check Interval</label>
            <select id="interval" bind:value={interval} class="form-select">
              <option value={10}>10 seconds</option>
              <option value={30}>30 seconds</option>
              <option value={60}>1 minute</option>
              <option value={300}>5 minutes</option>
            </select>
          </div>
          <div class="form-group">
            <label for="output-type">Watch</label>
            <select id="output-type" bind:value={watcherOutputType} class="form-select">
              <option value="stdout">stdout</option>
              <option value="stderr">stderr</option>
              <option value="both">both</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Helper Tools -->
      <div class="helper-tools">
        <button
          class="tool-toggle"
          on:click={() => { showJobOutput = !showJobOutput; }}
        >
          <Eye class="w-4 h-4" />
          <span>Preview Job Output</span>
          <ChevronRight class="w-3 h-3 chevron {showJobOutput ? 'rotated' : ''}" />
        </button>

        {#if showJobOutput}
          <div class="job-output-preview" transition:slide={{ duration: 200 }}>
            <div class="output-controls">
              <button
                class="refresh-btn"
                on:click={fetchJobOutput}
                disabled={loadingOutput}
              >
                {loadingOutput ? 'Loading...' : 'Refresh'}
              </button>
            </div>
            <pre class="output-content">{jobOutput}</pre>
          </div>
        {/if}
      </div>

      <!-- Advanced Options (Collapsed by default) -->
      <div class="advanced-section">
        <button
          class="section-toggle"
          on:click={() => showAdvanced = !showAdvanced}
        >
          <ChevronRight class="w-4 h-4 chevron {showAdvanced ? 'rotated' : ''}" />
          <span>Advanced Options</span>
        </button>

        {#if showAdvanced}
          <div class="advanced-content" transition:slide={{ duration: 300 }}>
            <div class="form-row">
              <div class="form-group flex-1">
                <label for="condition">Condition (optional)</label>
                <input
                  id="condition"
                  type="text"
                  bind:value={condition}
                  placeholder="e.g., int($1) > 90"
                  class="form-input"
                />
              </div>
            </div>

            <div class="form-row">
              <div class="form-group">
                <label for="max-triggers">Max Triggers</label>
                <input
                  id="max-triggers"
                  type="number"
                  bind:value={maxTriggers}
                  min="1"
                  max="1000"
                  class="form-input"
                />
              </div>
              <div class="form-group">
                <label>
                  <input type="checkbox" bind:checked={timerModeEnabled} />
                  Timer Mode
                </label>
                {#if timerModeEnabled}
                  <input
                    type="number"
                    bind:value={timerInterval}
                    placeholder="Timer interval (seconds)"
                    class="form-input mt-2"
                  />
                {/if}
              </div>
            </div>

            <!-- Simple Actions List -->
            <div class="actions-section">
              <div class="section-header">
                <label>Actions</label>
                <button class="add-action-btn" on:click={addSimpleAction}>
                  <Plus class="w-3 h-3" />
                  Add
                </button>
              </div>

              {#each actions as action, i}
                <div class="action-item">
                  <select bind:value={action.type} class="action-type-select">
                    <option value="log_event">Log Event</option>
                    <option value="store_metric">Store Metric</option>
                    <option value="notify_email">Send Email</option>
                  </select>

                  {#if action.type === 'log_event'}
                    <input
                      type="text"
                      bind:value={action.params.message}
                      placeholder="Log message"
                      class="action-input"
                    />
                  {:else if action.type === 'store_metric'}
                    <input
                      type="text"
                      bind:value={action.params.metric_name}
                      placeholder="Metric name"
                      class="action-input"
                    />
                    <input
                      type="text"
                      bind:value={action.params.value}
                      placeholder="Value expression"
                      class="action-input"
                    />
                  {:else if action.type === 'notify_email'}
                    <input
                      type="email"
                      bind:value={action.params.to}
                      placeholder="Email address"
                      class="action-input"
                    />
                    <input
                      type="text"
                      bind:value={action.params.subject}
                      placeholder="Subject"
                      class="action-input"
                    />
                  {/if}

                  <button
                    class="remove-action-btn"
                    on:click={() => removeAction(i)}
                  >
                    <X class="w-3 h-3" />
                  </button>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </div>

      <!-- Action Buttons -->
      <div class="action-buttons">
        <button class="cancel-btn" on:click={close} disabled={isSubmitting}>
          Cancel
        </button>
        <button
          class="create-btn"
          on:click={createWatcher}
          disabled={isSubmitting || !pattern.trim()}
        >
          {#if isSubmitting}
            Creating...
          {:else}
            <Save class="w-4 h-4" />
            Create Watcher
          {/if}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .watcher-creator {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    margin-bottom: 1rem;
    overflow: hidden;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  }

  .creator-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    background: #f8fafc;
    border-bottom: 1px solid #e5e7eb;
  }

  .header-info h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: #111827;
  }

  .job-info {
    font-size: 0.875rem;
    color: #6b7280;
  }

  .close-btn {
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 4px;
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: #f3f4f6;
    color: #374151;
  }

  .creator-content {
    padding: 1rem;
  }

  .error-message {
    background: #fef2f2;
    color: #dc2626;
    padding: 0.75rem;
    margin: 0 1rem;
    border-radius: 6px;
    font-size: 0.875rem;
    border: 1px solid #fecaca;
  }

  .quick-form {
    margin-bottom: 1rem;
  }

  .form-row {
    display: flex;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .form-row:last-child {
    margin-bottom: 0;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .form-group.flex-1 {
    flex: 1;
  }

  .form-group label {
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .help-toggle {
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.25rem;
    transition: all 0.2s;
  }

  .help-toggle:hover {
    background: #2563eb;
  }

  .form-input,
  .form-select {
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    font-size: 0.875rem;
    transition: border-color 0.2s;
  }

  .form-input:focus,
  .form-select:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .form-input.error {
    border-color: #dc2626;
  }

  .template-suggestions {
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    background: white;
    overflow: hidden;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    margin-top: 0.5rem;
  }

  .template-suggestion {
    display: block;
    width: 100%;
    padding: 0.75rem;
    border: none;
    background: none;
    text-align: left;
    cursor: pointer;
    transition: background 0.2s;
    border-bottom: 1px solid #f3f4f6;
  }

  .template-suggestion:hover {
    background: #f8fafc;
  }

  .template-suggestion:last-child {
    border-bottom: none;
  }

  .template-suggestion strong {
    display: block;
    color: #111827;
    font-size: 0.875rem;
    margin-bottom: 0.25rem;
  }

  .template-suggestion span {
    display: block;
    color: #6b7280;
    font-size: 0.75rem;
    margin-bottom: 0.5rem;
  }

  .template-suggestion code {
    display: block;
    background: #f3f4f6;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.75rem;
    color: #374151;
  }

  .helper-tools {
    margin-bottom: 1rem;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    overflow: hidden;
  }

  .tool-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.75rem;
    background: #f8fafc;
    border: none;
    cursor: pointer;
    font-size: 0.875rem;
    color: #374151;
    transition: background 0.2s;
  }

  .tool-toggle:hover {
    background: #f1f5f9;
  }

  .chevron {
    margin-left: auto;
    transition: transform 0.2s;
  }

  .chevron.rotated {
    transform: rotate(90deg);
  }

  .job-output-preview {
    border-top: 1px solid #e5e7eb;
  }

  .output-controls {
    padding: 0.5rem 0.75rem;
    background: #f8fafc;
    border-bottom: 1px solid #e5e7eb;
  }

  .refresh-btn {
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 0.25rem 0.75rem;
    font-size: 0.75rem;
    cursor: pointer;
    transition: background 0.2s;
  }

  .refresh-btn:hover:not(:disabled) {
    background: #2563eb;
  }

  .refresh-btn:disabled {
    opacity: 0.5;
  }

  .output-content {
    padding: 0.75rem;
    background: #1f2937;
    color: #f9fafb;
    font-family: monospace;
    font-size: 0.75rem;
    max-height: 200px;
    overflow-y: auto;
    margin: 0;
    white-space: pre-wrap;
  }

  .advanced-section {
    margin-bottom: 1rem;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    overflow: hidden;
  }

  .section-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.75rem;
    background: #f8fafc;
    border: none;
    cursor: pointer;
    font-size: 0.875rem;
    color: #374151;
    font-weight: 500;
    transition: background 0.2s;
  }

  .section-toggle:hover {
    background: #f1f5f9;
  }

  .advanced-content {
    padding: 1rem;
    border-top: 1px solid #e5e7eb;
  }

  .actions-section {
    margin-top: 1rem;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .section-header label {
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
  }

  .add-action-btn {
    background: #10b981;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.25rem;
    transition: background 0.2s;
  }

  .add-action-btn:hover {
    background: #059669;
  }

  .action-item {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 0.5rem;
    padding: 0.5rem;
    background: #f8fafc;
    border-radius: 6px;
  }

  .action-type-select {
    min-width: 120px;
  }

  .action-input {
    flex: 1;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
  }

  .remove-action-btn {
    background: #dc2626;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 0.25rem;
    cursor: pointer;
    transition: background 0.2s;
    display: flex;
    align-items: center;
  }

  .remove-action-btn:hover {
    background: #b91c1c;
  }

  .action-buttons {
    display: flex;
    gap: 0.75rem;
    justify-content: flex-end;
    padding-top: 1rem;
    border-top: 1px solid #e5e7eb;
  }

  .cancel-btn {
    background: white;
    border: 1px solid #d1d5db;
    color: #374151;
    border-radius: 6px;
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .cancel-btn:hover:not(:disabled) {
    background: #f9fafb;
    border-color: #9ca3af;
  }

  .create-btn {
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .create-btn:hover:not(:disabled) {
    background: #2563eb;
  }

  .create-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* Mobile responsiveness */
  @media (max-width: 768px) {
    .form-row {
      flex-direction: column;
      gap: 0.75rem;
    }

    .creator-content {
      padding: 0.75rem;
    }

    .action-item {
      flex-direction: column;
      align-items: stretch;
    }

    .action-buttons {
      flex-direction: column;
    }

    .output-content {
      font-size: 0.6875rem;
      max-height: 150px;
    }
  }
</style>