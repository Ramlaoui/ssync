<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../services/api';
  import type { WatcherAction } from '../types/watchers';
  
  export let jobId: string;
  export let hostname: string;
  export let copiedConfig: any = null;
  
  const dispatch = createEventDispatcher();
  
  // Form state
  let watcherName = '';
  let pattern = '';
  let interval = 30;
  let captures: string[] = [];
  let captureInput = '';
  let condition = '';
  let actions: WatcherAction[] = [];
  let timerModeEnabled = false;
  let timerIntervalSeconds = 30;
  
  // Action form
  let actionType = 'log_event';
  let actionConfig: Record<string, any> = {};
  let commandType = 'shell'; // 'shell' or 'python' for run_command
  
  // Loading state
  let isSubmitting = false;
  let error: string | null = null;
  
  // Available action types - must match backend ActionType enum
  const actionTypes = [
    { value: 'log_event', label: 'Log Event', description: 'Log the matched text as an event' },
    { value: 'store_metric', label: 'Store Metric', description: 'Store captured value as metric' },
    { value: 'notify_email', label: 'Send Email', description: 'Send email notification' },
    { value: 'notify_slack', label: 'Send Slack', description: 'Send Slack notification' },
    { value: 'run_command', label: 'Run Command', description: 'Execute a shell command' },
    { value: 'cancel_job', label: 'Cancel Job', description: 'Cancel the job on condition' },
    { value: 'resubmit', label: 'Resubmit Job', description: 'Resubmit the job' },
    { value: 'pause_watcher', label: 'Pause Watcher', description: 'Pause this watcher' },
  ];
  
  // Watcher templates
  const watcherTemplates = [
    {
      name: 'GPU Memory Monitor',
      description: 'Track GPU memory usage',
      config: {
        name: 'GPU Memory Monitor',
        pattern: 'GPU memory: (\\d+)/(\\d+) MB',
        captures: ['used', 'total'],
        interval: 30,
        actions: [{
          type: 'store_metric',
          config: { metric_name: 'gpu_memory_mb', value: '$used' }
        }]
      }
    },
    {
      name: 'Training Loss Tracker',
      description: 'Track ML training loss values',
      config: {
        name: 'Loss Tracker',
        pattern: 'Loss: ([\\d.]+)',
        captures: ['loss'],
        interval: 10,
        actions: [{
          type: 'store_metric',
          config: { metric_name: 'training_loss', value: 'float($loss)' }
        }]
      }
    },
    {
      name: 'Error Detection',
      description: 'Detect and alert on errors',
      config: {
        name: 'Error Detector',
        pattern: '(ERROR|CRITICAL|FATAL).*',
        captures: [],
        interval: 5,
        actions: [{
          type: 'log_event',
          config: {}
        }, {
          type: 'cancel_job',
          config: { reason: 'Critical error detected' }
        }]
      }
    },
    {
      name: 'Checkpoint Saver',
      description: 'Save checkpoint on epoch completion',
      config: {
        name: 'Checkpoint Saver',
        pattern: 'Epoch (\\d+) completed',
        captures: ['epoch'],
        interval: 60,
        actions: [{
          type: 'run_command',
          config: { command: 'cp -r ./checkpoint ./checkpoint_epoch_$1' }
        }]
      }
    },
    {
      name: 'Shell Command Runner',
      description: 'Run shell commands when pattern matches',
      config: {
        name: 'Command Runner',
        pattern: 'Iteration (\\d+)',
        captures: ['iteration'],
        interval: 30,
        actions: [{
          type: 'run_command',
          config: { 
            command: 'echo "Iteration $1 at $(date)" >> iterations.log'
          }
        }]
      }
    },
    {
      name: 'Python Script Runner',
      description: 'Execute Python code when pattern matches',
      config: {
        name: 'Python Runner',
        pattern: 'Loss: ([\\d.]+)',
        captures: ['loss'],
        interval: 30,
        actions: [{
          type: 'run_command',
          config: { 
            command: "python -c \"import sys; loss = float('$1'); print(f'Loss: {loss}'); sys.exit(0 if loss < 0.1 else 1)\""
          }
        }]
      }
    },
    {
      name: 'Custom Pattern',
      description: 'Start with a blank configuration',
      config: {
        name: '',
        pattern: '',
        captures: [],
        interval: 30,
        actions: []
      }
    }
  ];
  
  let selectedTemplate: typeof watcherTemplates[0] | null = null;
  let hasCopiedWatcher = false;
  
  // Check for copied watcher on mount
  onMount(() => {
    // If we have a copiedConfig prop, use it immediately
    if (copiedConfig) {
      watcherName = copiedConfig.name || '';
      pattern = copiedConfig.pattern || '';
      captures = copiedConfig.captures || [];
      interval = copiedConfig.interval || 30;
      condition = copiedConfig.condition || '';
      actions = copiedConfig.actions || [];
      timerModeEnabled = copiedConfig.timer_mode_enabled || false;
      timerIntervalSeconds = copiedConfig.timer_interval_seconds || 30;
      
      // Also add it as a template for reference
      watcherTemplates.unshift({
        name: 'Copied: ' + copiedConfig.name,
        description: 'Configuration copied from another watcher',
        config: copiedConfig
      });
      selectedTemplate = watcherTemplates[0];
    } else {
      // Otherwise check localStorage (legacy support)
      const copiedWatcher = localStorage.getItem('copiedWatcher');
      if (copiedWatcher) {
        hasCopiedWatcher = true;
        // Add copied watcher as a template option at the beginning
        try {
          const config = JSON.parse(copiedWatcher);
          watcherTemplates.unshift({
            name: 'Copied: ' + config.name,
            description: 'Previously copied watcher configuration',
            config: config
          });
        } catch (e) {
          console.error('Failed to parse copied watcher:', e);
        }
      }
    }
  });
  
  function addCapture() {
    if (captureInput.trim()) {
      captures = [...captures, captureInput.trim()];
      captureInput = '';
    }
  }
  
  function removeCapture(index: number) {
    captures = captures.filter((_, i) => i !== index);
  }
  
  function addAction() {
    const newAction: WatcherAction = {
      type: actionType,
      config: { ...actionConfig }
    };
    
    actions = [...actions, newAction];
    actionConfig = {};
    actionType = 'log_event'; // Reset to default
    commandType = 'shell'; // Reset command type
  }
  
  function applyTemplate(template: typeof watcherTemplates[0]) {
    try {
      selectedTemplate = template;
      watcherName = template.config.name || '';
      pattern = template.config.pattern || '';
      captures = Array.isArray(template.config.captures) ? [...template.config.captures] : [];
      interval = template.config.interval || 30;
      actions = Array.isArray(template.config.actions) ? [...template.config.actions] : [];
      condition = template.config.condition || '';
      timerModeEnabled = template.config.timer_mode_enabled || false;
      timerIntervalSeconds = template.config.timer_interval_seconds || 30;
      
      // Reset action form
      actionConfig = {};
      actionType = 'log_event';
      commandType = 'shell';
    } catch (error) {
      console.error('Error applying template:', error);
      alert('Failed to apply template. Please try again.');
    }
  }
  
  function clearForm() {
    selectedTemplate = null;
    watcherName = '';
    pattern = '';
    captures = [];
    captureInput = '';
    condition = '';
    actions = [];
    actionType = 'log_event';
    actionConfig = {};
    commandType = 'shell';
    timerModeEnabled = false;
    timerIntervalSeconds = 30;
  }
  
  function removeAction(index: number) {
    actions = actions.filter((_, i) => i !== index);
  }
  
  async function handleSubmit() {
    if (!watcherName || !pattern) {
      error = 'Watcher name and pattern are required';
      return;
    }
    
    if (actions.length === 0) {
      error = 'At least one action is required';
      return;
    }
    
    isSubmitting = true;
    error = null;
    
    try {
      const watcherConfig = {
        name: watcherName,
        pattern: pattern,
        interval_seconds: interval,
        capture_groups: captures.length > 0 ? captures : undefined,
        condition: condition || undefined,
        actions: actions,
        max_triggers: 10,
        output_type: 'stdout',
        timer_mode_enabled: timerModeEnabled,
        timer_interval_seconds: timerIntervalSeconds
      };
      
      const response = await api.post(`/api/jobs/${jobId}/watchers?host=${hostname}`, [watcherConfig]);
      
      if (response.data && response.data.watcher_ids) {
        dispatch('success', response.data);
      } else {
        throw new Error(response.data?.error || 'Failed to attach watchers');
      }
    } catch (err: any) {
      error = err.response?.data?.detail || err.message || 'Failed to attach watchers';
    } finally {
      isSubmitting = false;
    }
  }
  
  function handleClose() {
    dispatch('close');
  }
  
  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      handleClose();
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="dialog-overlay" on:click={handleClose}>
  <div class="dialog-container" on:click|stopPropagation>
    <div class="dialog-header">
      <h2>{copiedConfig ? 'Attach Copied Watcher to Job' : 'Attach Watchers to Job'}</h2>
      <button class="close-btn" on:click={handleClose}>
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
        </svg>
      </button>
    </div>
    
    <div class="dialog-body">
      {#if error}
        <div class="error-message">{error}</div>
      {/if}
      
      <!-- Template Selection -->
      <div class="template-section">
        <h3>Quick Start Templates</h3>
        <div class="template-grid">
          {#each watcherTemplates as template}
            <button
              type="button"
              class="template-card"
              class:selected={selectedTemplate === template}
              on:click={() => applyTemplate(template)}
              disabled={isSubmitting}
            >
              <div class="template-name">{template.name}</div>
              <div class="template-description">{template.description}</div>
            </button>
          {/each}
        </div>
      </div>
      
      <div class="form-section">
        <h3>Basic Configuration</h3>
        
        <div class="form-group">
          <label for="name">Watcher Name *</label>
          <input
            id="name"
            type="text"
            bind:value={watcherName}
            placeholder="e.g., GPU Memory Monitor"
            disabled={isSubmitting}
          />
        </div>
        
        <div class="form-group">
          <label for="pattern">Pattern to Match *</label>
          <input
            id="pattern"
            type="text"
            bind:value={pattern}
            placeholder="e.g., GPU memory: (\d+)MB"
            disabled={isSubmitting}
          />
          <small>Regular expression pattern to match in job output</small>
        </div>
        
        <div class="form-group">
          <label for="interval">Check Interval (seconds)</label>
          <input
            id="interval"
            type="number"
            bind:value={interval}
            min="5"
            max="3600"
            disabled={isSubmitting}
          />
          <small>How often to check for pattern matches</small>
        </div>
      </div>
      
      <div class="form-section">
        <h3>Capture Groups (Optional)</h3>
        
        <div class="form-group">
          <label>Named Capture Groups</label>
          <div class="capture-input">
            <input
              type="text"
              bind:value={captureInput}
              placeholder="e.g., gpu_memory"
              on:keydown={(e) => e.key === 'Enter' && addCapture()}
              disabled={isSubmitting}
            />
            <button 
              type="button" 
              on:click={addCapture}
              disabled={isSubmitting}
              class="add-btn"
            >
              Add
            </button>
          </div>
          
          {#if captures.length > 0}
            <div class="captures-list">
              {#each captures as capture, i}
                <div class="capture-item">
                  <span>${i + 1}: {capture}</span>
                  <button 
                    type="button"
                    on:click={() => removeCapture(i)}
                    disabled={isSubmitting}
                    class="remove-btn"
                  >
                    ×
                  </button>
                </div>
              {/each}
            </div>
          {/if}
        </div>
        
        <div class="form-group">
          <label for="condition">Condition (Optional)</label>
          <input
            id="condition"
            type="text"
            bind:value={condition}
            placeholder="e.g., $1 > 1000"
            disabled={isSubmitting}
          />
          <small>Python expression using captured variables</small>
        </div>
      </div>
      
      <div class="form-section">
        <h3>Actions *</h3>
        
        <div class="action-builder">
          <div class="form-group">
            <label for="action-type">Action Type</label>
            <select 
              id="action-type"
              bind:value={actionType}
              disabled={isSubmitting}
            >
              {#each actionTypes as type}
                <option value={type.value}>{type.label}</option>
              {/each}
            </select>
          </div>
          
          {#if actionType === 'store_metric'}
            <div class="form-group">
              <label for="metric-name">Metric Name</label>
              <input
                id="metric-name"
                type="text"
                bind:value={actionConfig.metric_name}
                placeholder="e.g., gpu_memory_usage"
                disabled={isSubmitting}
              />
            </div>
            <div class="form-group">
              <label for="value-expr">Value Expression</label>
              <input
                id="value-expr"
                type="text"
                bind:value={actionConfig.value}
                placeholder="e.g., $1 or float($gpu_memory)"
                disabled={isSubmitting}
              />
            </div>
          {:else if actionType === 'notify_email'}
            <div class="form-group">
              <label for="email-to">To</label>
              <input
                id="email-to"
                type="email"
                bind:value={actionConfig.to}
                placeholder="email@example.com"
                disabled={isSubmitting}
              />
            </div>
            <div class="form-group">
              <label for="email-subject">Subject</label>
              <input
                id="email-subject"
                type="text"
                bind:value={actionConfig.subject}
                placeholder="Alert: Pattern matched"
                disabled={isSubmitting}
              />
            </div>
          {:else if actionType === 'run_command'}
            <div class="form-group">
              <label for="command-type">Command Type</label>
              <select
                id="command-type"
                bind:value={commandType}
                disabled={isSubmitting}
              >
                <option value="shell">Shell Command</option>
                <option value="python">Python Code</option>
              </select>
            </div>
            
            {#if commandType === 'python'}
              <div class="form-group">
                <label for="python-code">Python Code</label>
                <textarea
                  id="python-code"
                  bind:value={actionConfig.pythonCode}
                  placeholder="# Access captured groups with $1, $2, etc.\n# Example:\nimport sys\nvalue = float('$1')\nprint(f'Processed value: {value}')\n\n# Write to files, use libraries, etc."
                  rows="8"
                  disabled={isSubmitting}
                  on:input={() => {
                    // Convert Python code to a shell command
                    if (actionConfig.pythonCode) {
                      actionConfig.command = `python -c "${actionConfig.pythonCode.replace(/"/g, '\\"').replace(/\n/g, '; ')}"`;
                    }
                  }}
                />
                <small>Captured groups are available as $1, $2, etc. The full match is $0.</small>
              </div>
            {:else}
              <div class="form-group">
                <label for="command">Shell Command</label>
                <input
                  id="command"
                  type="text"
                  bind:value={actionConfig.command}
                  placeholder="e.g., echo 'Match found: $0' >> log.txt"
                  disabled={isSubmitting}
                />
                <small>Use $0 for full match, $1, $2 for capture groups</small>
              </div>
            {/if}
          {:else if actionType === 'notify_slack'}
            <div class="form-group">
              <label for="webhook-url">Webhook URL</label>
              <input
                id="webhook-url"
                type="text"
                bind:value={actionConfig.webhook_url}
                placeholder="https://hooks.slack.com/services/..."
                disabled={isSubmitting}
              />
            </div>
            <div class="form-group">
              <label for="slack-message">Message</label>
              <input
                id="slack-message"
                type="text"
                bind:value={actionConfig.message}
                placeholder="Pattern matched: $0"
                disabled={isSubmitting}
              />
            </div>
          {:else if actionType === 'cancel_job'}
            <div class="form-group">
              <label for="cancel-reason">Reason (optional)</label>
              <input
                id="cancel-reason"
                type="text"
                bind:value={actionConfig.reason}
                placeholder="e.g., Error threshold exceeded"
                disabled={isSubmitting}
              />
            </div>
          {:else if actionType === 'resubmit'}
            <div class="form-group">
              <label for="resubmit-delay">Delay (seconds)</label>
              <input
                id="resubmit-delay"
                type="number"
                bind:value={actionConfig.delay}
                placeholder="0"
                min="0"
                disabled={isSubmitting}
              />
              <small>Delay before resubmitting the job</small>
            </div>
          {:else if actionType === 'pause_watcher'}
            <div class="form-group">
              <label for="checkpoint-name">Checkpoint Name</label>
              <input
                id="checkpoint-name"
                type="text"
                bind:value={actionConfig.name}
                placeholder="e.g., checkpoint_epoch_$1"
                disabled={isSubmitting}
              />
            </div>
          {/if}
          
          <button 
            type="button"
            on:click={addAction}
            disabled={isSubmitting}
            class="add-action-btn"
          >
            Add Action
          </button>
        </div>
        
        {#if actions.length > 0}
          <div class="actions-list">
            <h4>Configured Actions:</h4>
            {#each actions as action, i}
              <div class="action-item">
                <div class="action-info">
                  <strong>{actionTypes.find(t => t.value === action.type)?.label}</strong>
                  {#if action.config}
                    <small>{JSON.stringify(action.config)}</small>
                  {/if}
                </div>
                <button 
                  type="button"
                  on:click={() => removeAction(i)}
                  disabled={isSubmitting}
                  class="remove-btn"
                >
                  Remove
                </button>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </div>
    
    <div class="dialog-footer">
      <button 
        type="button"
        on:click={handleClose}
        disabled={isSubmitting}
        class="cancel-btn"
      >
        Cancel
      </button>
      <button 
        type="button"
        on:click={handleSubmit}
        disabled={isSubmitting || !watcherName || !pattern || actions.length === 0}
        class="submit-btn"
      >
        {isSubmitting ? 'Attaching...' : 'Attach Watcher'}
      </button>
    </div>
  </div>
</div>

<style>
  .dialog-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  
  .dialog-container {
    background: white;
    border-radius: 12px;
    width: 90%;
    max-width: 700px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
  }
  
  .dialog-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .dialog-header h2 {
    margin: 0;
    font-size: 1.5rem;
    color: #1f2937;
  }
  
  .close-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.5rem;
    color: #6b7280;
    transition: color 0.2s;
  }
  
  .close-btn:hover {
    color: #1f2937;
  }
  
  .close-btn svg {
    width: 24px;
    height: 24px;
  }
  
  .dialog-body {
    padding: 1.5rem;
    overflow-y: auto;
    flex: 1;
  }
  
  /* Template section */
  .template-section {
    margin-bottom: 2rem;
    padding: 1rem;
    background: #f0f9ff;
    border: 1px solid #bae6fd;
    border-radius: 8px;
  }
  
  .template-section h3 {
    margin: 0 0 1rem 0;
    font-size: 1rem;
    color: #0369a1;
    font-weight: 600;
  }
  
  .template-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.75rem;
  }
  
  .template-card {
    padding: 0.75rem;
    background: white;
    border: 1px solid #e0e7ff;
    border-radius: 6px;
    cursor: pointer;
    text-align: left;
    transition: all 0.2s;
  }
  
  .template-card:hover:not(:disabled) {
    border-color: #3b82f6;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  }
  
  .template-card.selected {
    background: #eff6ff;
    border-color: #3b82f6;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }
  
  .template-card:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .template-name {
    font-weight: 600;
    color: #1e293b;
    font-size: 0.875rem;
    margin-bottom: 0.25rem;
  }
  
  .template-description {
    font-size: 0.75rem;
    color: #64748b;
  }
  
  .error-message {
    background: #fee2e2;
    border: 1px solid #fca5a5;
    color: #dc2626;
    padding: 0.75rem;
    border-radius: 6px;
    margin-bottom: 1rem;
  }
  
  .form-section {
    margin-bottom: 2rem;
  }
  
  .form-section h3 {
    margin: 0 0 1rem 0;
    font-size: 1.1rem;
    color: #374151;
    font-weight: 600;
  }
  
  .form-group {
    margin-bottom: 1rem;
  }
  
  .form-group label {
    display: block;
    margin-bottom: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
  }
  
  .form-group input,
  .form-group select,
  .form-group textarea {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.875rem;
    transition: border-color 0.2s;
    font-family: inherit;
  }
  
  .form-group textarea {
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 0.8rem;
    resize: vertical;
  }
  
  .form-group input:focus,
  .form-group select:focus,
  .form-group textarea:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }
  
  .form-group input:disabled,
  .form-group select:disabled,
  .form-group textarea:disabled {
    background: #f3f4f6;
    color: #9ca3af;
  }
  
  .form-group small {
    display: block;
    margin-top: 0.25rem;
    font-size: 0.75rem;
    color: #6b7280;
  }
  
  .capture-input {
    display: flex;
    gap: 0.5rem;
  }
  
  .capture-input input {
    flex: 1;
  }
  
  .add-btn,
  .add-action-btn {
    padding: 0.5rem 1rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    cursor: pointer;
    transition: background 0.2s;
  }
  
  .add-btn:hover:not(:disabled),
  .add-action-btn:hover:not(:disabled) {
    background: #2563eb;
  }
  
  .add-btn:disabled,
  .add-action-btn:disabled {
    background: #9ca3af;
    cursor: not-allowed;
  }
  
  .captures-list,
  .actions-list {
    margin-top: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .capture-item,
  .action-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0.75rem;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
  }
  
  .capture-item span {
    font-family: monospace;
    font-size: 0.875rem;
    color: #374151;
  }
  
  .action-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .action-info small {
    font-size: 0.75rem;
    color: #6b7280;
    font-family: monospace;
  }
  
  .remove-btn {
    background: #ef4444;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-size: 0.875rem;
    cursor: pointer;
    transition: background 0.2s;
  }
  
  .remove-btn:hover:not(:disabled) {
    background: #dc2626;
  }
  
  .action-builder {
    padding: 1rem;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    margin-bottom: 1rem;
  }
  
  .actions-list h4 {
    margin: 0 0 0.5rem 0;
    font-size: 0.875rem;
    font-weight: 600;
    color: #374151;
  }
  
  .dialog-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    padding: 1.5rem;
    border-top: 1px solid #e5e7eb;
  }
  
  .cancel-btn,
  .submit-btn {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .cancel-btn {
    background: white;
    color: #374151;
    border: 1px solid #d1d5db;
  }
  
  .cancel-btn:hover:not(:disabled) {
    background: #f3f4f6;
  }
  
  .submit-btn {
    background: #3b82f6;
    color: white;
  }
  
  .submit-btn:hover:not(:disabled) {
    background: #2563eb;
  }
  
  .cancel-btn:disabled,
  .submit-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  @media (max-width: 640px) {
    .dialog-container {
      width: 100%;
      height: 100%;
      max-width: none;
      max-height: none;
      border-radius: 0;
    }
    
    .dialog-body {
      padding: 1rem;
    }
  }
</style>