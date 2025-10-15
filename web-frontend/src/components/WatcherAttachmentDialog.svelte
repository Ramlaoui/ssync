<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../services/api';
  import type { WatcherAction } from '../types/watchers';
  import Dialog from '../lib/components/ui/Dialog.svelte';
  
  interface Props {
    jobId: string;
    hostname: string;
    copiedConfig?: any;
    open?: boolean;
  }

  let {
    jobId,
    hostname,
    copiedConfig = null,
    open = $bindable(true)
  }: Props = $props();

  const dispatch = createEventDispatcher();
  
  // Form state
  let watcherName = $state('');
  let pattern = $state('');
  let interval = $state(30);
  let captures: string[] = $state([]);
  let captureInput = $state('');
  let condition = $state('');
  let actions: WatcherAction[] = $state([]);
  let watchMode: 'pattern' | 'timer' = $state('pattern');
  let timerInterval = $state(30);
  
  // Action form
  let actionType = $state('log_event');
  let actionConfig: Record<string, any> = $state({});
  let commandType = $state('shell');
  
  // UI state
  let isSubmitting = $state(false);
  let error: string | null = $state(null);
  let showTemplates = $state(false);
  let showAdvanced = $state(false);
  let activeTab: 'config' | 'actions' = $state('config');
  
  // Action types with better descriptions
  const actionTypes = [
    { 
      value: 'log_event', 
      label: 'Log Event', 
      icon: '📝',
      description: 'Record matched text in event log',
      fields: []
    },
    { 
      value: 'store_metric', 
      label: 'Store Metric', 
      icon: '📊',
      description: 'Track numerical values over time',
      fields: ['metric_name', 'value']
    },
    { 
      value: 'run_command', 
      label: 'Run Command', 
      icon: '⚡',
      description: 'Execute shell or Python code',
      fields: ['command']
    },
    { 
      value: 'notify_email', 
      label: 'Send Email', 
      icon: '✉️',
      description: 'Email notifications on match',
      fields: ['to', 'subject']
    },
    { 
      value: 'notify_slack', 
      label: 'Send to Slack', 
      icon: '💬',
      description: 'Post to Slack channel',
      fields: ['webhook_url', 'message']
    },
    { 
      value: 'cancel_job', 
      label: 'Cancel Job', 
      icon: '🛑',
      description: 'Stop job execution',
      fields: ['reason']
    },
    { 
      value: 'resubmit', 
      label: 'Resubmit Job', 
      icon: '🔄',
      description: 'Restart the job',
      fields: ['delay']
    },
    { 
      value: 'pause_watcher', 
      label: 'Pause Watcher', 
      icon: '⏸️',
      description: 'Stop watching temporarily',
      fields: ['name']
    },
  ];
  
  // Compact template data
  const templates = [
    {
      id: 'gpu',
      name: 'GPU Monitor',
      icon: '🎮',
      pattern: 'GPU memory: (\\d+)/(\\d+) MB',
      captures: ['used', 'total'],
      interval: 30,
      actions: [{
        type: 'store_metric',
        config: { metric_name: 'gpu_memory_mb', value: '$used' }
      }]
    },
    {
      id: 'loss',
      name: 'Training Loss',
      icon: '📉',
      pattern: 'Loss: ([\\d.]+)',
      captures: ['loss'],
      interval: 10,
      actions: [{
        type: 'store_metric',
        config: { metric_name: 'training_loss', value: 'float($loss)' }
      }]
    },
    {
      id: 'error',
      name: 'Error Detector',
      icon: '⚠️',
      pattern: '(ERROR|CRITICAL|FATAL).*',
      captures: [],
      interval: 5,
      actions: [{
        type: 'log_event',
        config: {}
      }]
    },
    {
      id: 'checkpoint',
      name: 'Checkpoint',
      icon: '💾',
      pattern: 'Epoch (\\d+) completed',
      captures: ['epoch'],
      interval: 60,
      actions: [{
        type: 'run_command',
        config: { command: 'cp -r checkpoint checkpoint_epoch_$1' }
      }]
    },
    {
      id: 'timer',
      name: 'Time-based',
      icon: '⏰',
      isTimer: true,
      pattern: '',
      interval: 300,
      actions: [{
        type: 'run_command',
        config: { command: 'echo "Timer triggered at $(date)"' }
      }]
    },
    {
      id: 'custom',
      name: 'Custom',
      icon: '✨',
      pattern: '',
      captures: [],
      interval: 30,
      actions: []
    }
  ];
  
  let selectedTemplateId: string | null = $state(null);
  
  onMount(() => {
    if (copiedConfig) {
      applyConfig(copiedConfig);
    }
  });
  
  function applyConfig(config: any) {
    watcherName = config.name || '';
    pattern = config.pattern || '';
    captures = config.captures || [];
    interval = config.interval || 30;
    condition = config.condition || '';
    actions = config.actions || [];
    
    if (config.timer_mode_enabled) {
      watchMode = 'timer';
      timerInterval = config.timer_interval_seconds || 30;
    }
  }
  
  function selectTemplate(template: typeof templates[0]) {
    selectedTemplateId = template.id;
    
    if (template.isTimer) {
      watchMode = 'timer';
      timerInterval = template.interval;
      watcherName = template.name;
      actions = template.actions || [];
    } else {
      watchMode = 'pattern';
      watcherName = template.name;
      pattern = template.pattern;
      captures = template.captures || [];
      interval = template.interval;
      actions = template.actions || [];
    }
    
    // Reset action form
    actionConfig = {};
    actionType = 'log_event';
    showTemplates = false;
  }
  
  function addCapture() {
    if (captureInput.trim()) {
      captures = [...captures, captureInput.trim()];
      captureInput = '';
    }
  }
  
  function removeCapture(index: number) {
    captures = captures.filter((_, i) => i !== index);
  }
  
  function getActionTypeInfo(type: string) {
    return actionTypes.find(t => t.value === type);
  }
  
  function addAction() {
    const newAction: WatcherAction = {
      type: actionType,
      config: { ...actionConfig }
    };
    
    actions = [...actions, newAction];
    actionConfig = {};
    actionType = 'log_event';
    commandType = 'shell';
  }
  
  function removeAction(index: number) {
    actions = actions.filter((_, i) => i !== index);
  }
  
  function getActionSummary(action: WatcherAction): string {
    switch (action.type) {
      case 'store_metric':
        return `${action.config.metric_name}: ${action.config.value}`;
      case 'run_command':
        const cmd = action.config.command || '';
        return cmd.length > 50 ? cmd.substring(0, 50) + '...' : cmd;
      case 'notify_email':
        return `To: ${action.config.to}`;
      case 'notify_slack':
        return action.config.message || 'Slack notification';
      case 'cancel_job':
        return action.config.reason || 'Cancel job';
      case 'resubmit':
        return `Delay: ${action.config.delay || 0}s`;
      case 'pause_watcher':
        return action.config.name || 'Pause';
      default:
        return 'Log event';
    }
  }
  
  function formatInterval(seconds: number): string {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    return `${Math.floor(seconds / 3600)}h`;
  }
  
  async function handleSubmit() {
    if (!watcherName) {
      error = 'Please provide a watcher name';
      return;
    }
    
    if (watchMode === 'pattern' && !pattern) {
      error = 'Please provide a pattern to match';
      return;
    }
    
    if (actions.length === 0) {
      error = 'Please add at least one action';
      return;
    }
    
    isSubmitting = true;
    error = null;
    
    try {
      const watcherConfig = {
        name: watcherName,
        pattern: watchMode === 'timer' ? '.*' : pattern,
        interval_seconds: watchMode === 'timer' ? timerInterval : interval,
        capture_groups: captures.length > 0 ? captures : undefined,
        condition: condition || undefined,
        actions: actions,
        max_triggers: 10,
        output_type: 'stdout',
        timer_mode_enabled: watchMode === 'timer',
        timer_interval_seconds: watchMode === 'timer' ? timerInterval : undefined
      };
      
      const response = await api.post(`/api/jobs/${jobId}/watchers?host=${hostname}`, [watcherConfig]);
      
      if (response.data && response.data.watcher_ids) {
        dispatch('success', response.data);
      } else {
        throw new Error(response.data?.error || 'Failed to attach watcher');
      }
    } catch (err: any) {
      error = err.response?.data?.detail || err.message || 'Failed to attach watcher';
    } finally {
      isSubmitting = false;
    }
  }
  
  function handleClose() {
    open = false;
    dispatch('close');
  }
</script>

<Dialog
  bind:open
  on:close={handleClose}
  title="Create New Watcher"
  description="Monitor job output and trigger actions"
  size="xl"
  contentClass="watcher-attachment-content"
>
      {#if error}
        <div class="error-banner">
          <svg class="error-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
          </svg>
          <span>{error}</span>
        </div>
      {/if}
      
      <!-- Template Selection -->
      <div class="template-selector">
        <button 
          class="template-toggle"
          onclick={() => showTemplates = !showTemplates}
          type="button"
        >
          <svg class="toggle-icon" viewBox="0 0 20 20" fill="currentColor">
            <path d="M10 3.5a1.5 1.5 0 013 0V4a1 1 0 001 1h3.5a1.5 1.5 0 010 3H14a1 1 0 00-1 1v3.5a1.5 1.5 0 01-3 0V9a1 1 0 00-1-1H5.5a1.5 1.5 0 010-3H9a1 1 0 001-1v-.5z"/>
          </svg>
          <span>Quick Templates</span>
          <svg class="chevron" class:rotated={showTemplates} viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
          </svg>
        </button>
        
        {#if showTemplates}
          <div class="templates-grid">
            {#each templates as template}
              <button
                type="button"
                class="template-tile"
                class:selected={selectedTemplateId === template.id}
                onclick={() => selectTemplate(template)}
                disabled={isSubmitting}
              >
                <span class="template-icon">{template.icon}</span>
                <span class="template-name">{template.name}</span>
              </button>
            {/each}
          </div>
        {/if}
      </div>
      
      <!-- Main Configuration Tabs -->
      <div class="tabs">
        <button 
          type="button"
          class="tab"
          class:active={activeTab === 'config'}
          onclick={() => activeTab = 'config'}
        >
          Configuration
        </button>
        <button 
          type="button"
          class="tab"
          class:active={activeTab === 'actions'}
          onclick={() => activeTab = 'actions'}
        >
          Actions {#if actions.length > 0}<span class="badge">{actions.length}</span>{/if}
        </button>
      </div>
      
      {#if activeTab === 'config'}
        <div class="config-section">
          <!-- Watcher Name -->
          <div class="form-group">
            <label for="name">
              Watcher Name
              <span class="required">*</span>
            </label>
            <input
              id="name"
              type="text"
              bind:value={watcherName}
              placeholder="e.g., GPU Memory Monitor"
              disabled={isSubmitting}
            />
          </div>
          
          <!-- Watch Mode Toggle -->
          <div class="mode-selector">
            <span class="mode-label">Watch Mode</span>
            <div class="mode-buttons">
              <button
                type="button"
                class="mode-btn"
                class:active={watchMode === 'pattern'}
                onclick={() => watchMode = 'pattern'}
                disabled={isSubmitting}
              >
                <svg viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z"/>
                  <path d="M4 5a2 2 0 012-2 1 1 0 000 2H6a2 2 0 00-2 2v6a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-1a1 1 0 100-2h1a4 4 0 014 4v6a4 4 0 01-4 4H6a4 4 0 01-4-4V7a4 4 0 014-4z"/>
                </svg>
                Pattern Match
              </button>
              <button
                type="button"
                class="mode-btn"
                class:active={watchMode === 'timer'}
                onclick={() => watchMode = 'timer'}
                disabled={isSubmitting}
              >
                <svg viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"/>
                </svg>
                Time-based
              </button>
            </div>
            <p class="mode-description">
              {#if watchMode === 'pattern'}
                Trigger actions when specific patterns appear in job output
              {:else}
                Trigger actions at regular time intervals
              {/if}
            </p>
          </div>
          
          {#if watchMode === 'pattern'}
            <!-- Pattern Configuration -->
            <div class="form-group">
              <label for="pattern">
                Match Pattern
                <span class="required">*</span>
                <button 
                  type="button"
                  class="help-btn"
                  title="Regular expression pattern to match in job output"
                >
                  ?
                </button>
              </label>
              <input
                id="pattern"
                type="text"
                bind:value={pattern}
                placeholder="e.g., Loss: ([\d.]+)"
                disabled={isSubmitting}
              />
              <small>Regular expression. Use () to capture groups</small>
            </div>
            
            <!-- Check Interval Slider -->
            <div class="form-group">
              <label for="interval">
                Check Interval: <strong>{formatInterval(interval)}</strong>
              </label>
              <div class="slider-container">
                <input
                  id="interval"
                  type="range"
                  bind:value={interval}
                  min="5"
                  max="300"
                  step="5"
                  disabled={isSubmitting}
                />
                <div class="slider-labels">
                  <span>5s</span>
                  <span>2.5m</span>
                  <span>5m</span>
                </div>
              </div>
              <small>How often to scan output for matches</small>
            </div>
            
            <!-- Advanced Options -->
            <button
              type="button"
              class="advanced-toggle"
              onclick={() => showAdvanced = !showAdvanced}
            >
              <svg class="chevron" class:rotated={showAdvanced} viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
              </svg>
              Advanced Options
            </button>
            
            {#if showAdvanced}
              <div class="advanced-options">
                <!-- Capture Groups -->
                <div class="form-group">
                  <span class="section-label">Capture Groups</span>
                  <div class="capture-input">
                    <input
                      type="text"
                      bind:value={captureInput}
                      placeholder="e.g., loss_value"
                      onkeydown={(e) => e.key === 'Enter' && addCapture()}
                      disabled={isSubmitting}
                    />
                    <button 
                      type="button" 
                      onclick={addCapture}
                      disabled={isSubmitting}
                      class="add-btn"
                    >
                      Add
                    </button>
                  </div>
                  
                  {#if captures.length > 0}
                    <div class="captures-list">
                      {#each captures as capture, i}
                        <span class="capture-tag">
                          ${i + 1}: {capture}
                          <button 
                            type="button"
                            onclick={() => removeCapture(i)}
                            disabled={isSubmitting}
                            class="tag-remove"
                          >
                            ×
                          </button>
                        </span>
                      {/each}
                    </div>
                  {/if}
                  <small>Name your regex capture groups for use in actions</small>
                </div>
                
                <!-- Condition -->
                <div class="form-group">
                  <label for="condition">Trigger Condition</label>
                  <input
                    id="condition"
                    type="text"
                    bind:value={condition}
                    placeholder="e.g., float($1) > 0.5"
                    disabled={isSubmitting}
                  />
                  <small>Python expression. Only trigger if true</small>
                </div>
              </div>
            {/if}
          {:else}
            <!-- Timer Configuration -->
            <div class="form-group">
              <label for="timer-interval">
                Timer Interval: <strong>{formatInterval(timerInterval)}</strong>
              </label>
              <div class="slider-container">
                <input
                  id="timer-interval"
                  type="range"
                  bind:value={timerInterval}
                  min="10"
                  max="3600"
                  step="10"
                  disabled={isSubmitting}
                />
                <div class="slider-labels">
                  <span>10s</span>
                  <span>30m</span>
                  <span>1h</span>
                </div>
              </div>
              <small>Trigger actions at this interval</small>
            </div>
          {/if}
        </div>
      {:else}
        <!-- Actions Tab -->
        <div class="actions-section">
          <!-- Action Builder -->
          <div class="action-builder">
            <h3>Add New Action</h3>
            
            <div class="action-type-selector">
              {#each actionTypes as type}
                <button
                  type="button"
                  class="action-type-btn"
                  class:selected={actionType === type.value}
                  onclick={() => { actionType = type.value; actionConfig = {}; }}
                  disabled={isSubmitting}
                >
                  <span class="action-icon">{type.icon}</span>
                  <div class="action-info">
                    <span class="action-label">{type.label}</span>
                    <span class="action-desc">{type.description}</span>
                  </div>
                </button>
              {/each}
            </div>
            
            <!-- Dynamic fields based on action type -->
            <div class="action-fields">
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
                    placeholder="e.g., $1 or float($loss)"
                    disabled={isSubmitting}
                  />
                  <small>Use $1, $2 for capture groups</small>
                </div>
              {:else if actionType === 'run_command'}
                <div class="form-group">
                  <span class="section-label">Command Type</span>
                  <div class="command-type-toggle">
                    <button
                      type="button"
                      class:active={commandType === 'shell'}
                      onclick={() => commandType = 'shell'}
                    >
                      Shell
                    </button>
                    <button
                      type="button"
                      class:active={commandType === 'python'}
                      onclick={() => commandType = 'python'}
                    >
                      Python
                    </button>
                  </div>
                </div>
                
                {#if commandType === 'python'}
                  <div class="form-group">
                    <label for="python-code">Python Code</label>
                    <textarea
                      id="python-code"
                      bind:value={actionConfig.pythonCode}
                      placeholder={'# Use $1, $2 for captures\nprint(f"Value: {float(\'$1\')}")'}
                      rows="4"
                      disabled={isSubmitting}
                      oninput={() => {
                        if (actionConfig.pythonCode) {
                          actionConfig.command = `python -c "${actionConfig.pythonCode.replace(/"/g, '\\"').replace(/\n/g, '; ')}"`;
                        }
                      }}
></textarea>
                  </div>
                {:else}
                  <div class="form-group">
                    <label for="command">Shell Command</label>
                    <input
                      id="command"
                      type="text"
                      bind:value={actionConfig.command}
                      placeholder="e.g., echo 'Match: $0' >> log.txt"
                      disabled={isSubmitting}
                    />
                    <small>Use $0 for full match, $1, $2 for captures</small>
                  </div>
                {/if}
              {:else if actionType === 'notify_email'}
                <div class="form-group">
                  <label for="email-to">Email To</label>
                  <input
                    id="email-to"
                    type="email"
                    bind:value={actionConfig.to}
                    placeholder="user@example.com"
                    disabled={isSubmitting}
                  />
                </div>
                <div class="form-group">
                  <label for="email-subject">Subject</label>
                  <input
                    id="email-subject"
                    type="text"
                    bind:value={actionConfig.subject}
                    placeholder="Job Alert"
                    disabled={isSubmitting}
                  />
                </div>
              {:else if actionType === 'notify_slack'}
                <div class="form-group">
                  <label for="webhook-url">Webhook URL</label>
                  <input
                    id="webhook-url"
                    type="url"
                    bind:value={actionConfig.webhook_url}
                    placeholder="https://hooks.slack.com/..."
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
                  <label for="cancel-reason">Cancellation Reason</label>
                  <input
                    id="cancel-reason"
                    type="text"
                    bind:value={actionConfig.reason}
                    placeholder="e.g., Critical error detected"
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
                </div>
              {:else if actionType === 'pause_watcher'}
                <div class="form-group">
                  <label for="pause-name">Checkpoint Name</label>
                  <input
                    id="pause-name"
                    type="text"
                    bind:value={actionConfig.name}
                    placeholder="Optional checkpoint name"
                    disabled={isSubmitting}
                  />
                </div>
              {/if}
              
              <button 
                type="button"
                onclick={addAction}
                disabled={isSubmitting || (actionType === 'store_metric' && !actionConfig.metric_name)}
                class="add-action-btn"
              >
                Add Action
              </button>
            </div>
          </div>
          
          <!-- Actions List -->
          {#if actions.length > 0}
            <div class="actions-list">
              <h3>Configured Actions</h3>
              {#each actions as action, i}
                <div class="action-card">
                  <div class="action-header">
                    <span class="action-icon">{getActionTypeInfo(action.type)?.icon}</span>
                    <span class="action-title">{getActionTypeInfo(action.type)?.label}</span>
                  </div>
                  <div class="action-summary">{getActionSummary(action)}</div>
                  <button 
                    type="button"
                    onclick={() => removeAction(i)}
                    disabled={isSubmitting}
                    class="action-remove"
                    aria-label="Remove action"
                  >
                    <svg viewBox="0 0 20 20" fill="currentColor">
                      <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
                    </svg>
                  </button>
                </div>
              {/each}
            </div>
          {:else}
            <div class="empty-state">
              <svg viewBox="0 0 20 20" fill="currentColor">
                <path d="M10 12a2 2 0 100-4 2 2 0 000 4z"/>
                <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd"/>
              </svg>
              <p>No actions configured yet</p>
              <small>Add an action above to get started</small>
            </div>
          {/if}
        </div>
      {/if}

  {#snippet footer()}
    <div  class="attachment-footer">
      <button
        type="button"
        onclick={handleClose}
        disabled={isSubmitting}
        class="btn-secondary"
      >
        Cancel
      </button>
      <button
        type="button"
        onclick={handleSubmit}
        disabled={isSubmitting || !watcherName || (watchMode === 'pattern' && !pattern) || actions.length === 0}
        class="btn-primary"
      >
        {isSubmitting ? 'Creating...' : 'Create Watcher'}
      </button>
    </div>
  {/snippet}
</Dialog>

<style>
  :global(.watcher-attachment-content) {
    padding: 1.5rem !important;
  }
  
  .error-banner {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: #fef2f2;
    border: 1px solid #fecaca;
    color: #dc2626;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    margin-bottom: 1rem;
    font-size: 0.875rem;
  }
  
  .error-icon {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }
  
  /* Template Selector */
  .template-selector {
    margin-bottom: 1.5rem;
  }
  
  .template-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.75rem 1rem;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
  }
  
  .template-toggle:hover {
    background: #f3f4f6;
    border-color: #d1d5db;
  }
  
  .toggle-icon {
    width: 18px;
    height: 18px;
    color: #6b7280;
  }
  
  .chevron {
    width: 18px;
    height: 18px;
    margin-left: auto;
    transition: transform 0.2s;
  }
  
  .chevron.rotated {
    transform: rotate(180deg);
  }
  
  .templates-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 0.5rem;
    margin-top: 0.75rem;
    padding: 0.75rem;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    border-top-left-radius: 0;
    border-top-right-radius: 0;
    border-top: none;
  }
  
  .template-tile {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    padding: 0.75rem 0.5rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .template-tile:hover:not(:disabled) {
    border-color: #3b82f6;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  }
  
  .template-tile.selected {
    background: #eff6ff;
    border-color: #3b82f6;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
  }
  
  .template-tile:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .template-icon {
    font-size: 1.5rem;
  }
  
  .template-name {
    font-size: 0.75rem;
    font-weight: 500;
    color: #374151;
    text-align: center;
  }
  
  /* Tabs */
  .tabs {
    display: flex;
    gap: 0.25rem;
    margin-bottom: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .tab {
    position: relative;
    padding: 0.75rem 1rem;
    background: none;
    border: none;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
    color: #6b7280;
    transition: all 0.2s;
  }
  
  .tab:hover {
    color: #374151;
  }
  
  .tab.active {
    color: #3b82f6;
  }
  
  .tab.active::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 0;
    right: 0;
    height: 2px;
    background: #3b82f6;
  }
  
  .badge {
    display: inline-block;
    margin-left: 0.25rem;
    padding: 0.125rem 0.375rem;
    background: #3b82f6;
    color: white;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
  }
  
  /* Mode Selector */
  .mode-selector {
    margin-bottom: 1.5rem;
  }
  
  .mode-label {
    display: block;
    margin-bottom: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
  }
  
  .mode-buttons {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }
  
  .mode-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background: white;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 0.875rem;
    font-weight: 500;
    color: #6b7280;
  }
  
  .mode-btn:hover:not(:disabled) {
    border-color: #d1d5db;
    background: #f9fafb;
  }
  
  .mode-btn.active {
    background: #eff6ff;
    border-color: #3b82f6;
    color: #3b82f6;
  }
  
  .mode-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .mode-btn svg {
    width: 18px;
    height: 18px;
  }
  
  .mode-description {
    margin-top: 0.5rem;
    font-size: 0.75rem;
    color: #6b7280;
    font-style: italic;
  }
  
  /* Form Groups */
  .form-group {
    margin-bottom: 1.25rem;
  }

  .form-group label {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    margin-bottom: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
  }

  .section-label {
    display: block;
    margin-bottom: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
  }
  
  .required {
    color: #ef4444;
  }
  
  .help-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    background: #e5e7eb;
    border: none;
    border-radius: 50%;
    cursor: help;
    font-size: 0.7rem;
    color: #6b7280;
  }
  
  .form-group input,
  .form-group textarea {
    width: 100%;
    padding: 0.625rem 0.875rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.875rem;
    transition: all 0.2s;
  }
  
  .form-group input:focus,
  .form-group textarea:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }
  
  .form-group input:disabled,
  .form-group textarea:disabled {
    background: #f9fafb;
    color: #9ca3af;
  }
  
  .form-group textarea {
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 0.8rem;
    resize: vertical;
  }
  
  .form-group small {
    display: block;
    margin-top: 0.375rem;
    font-size: 0.75rem;
    color: #6b7280;
  }
  
  /* Slider */
  .slider-container {
    position: relative;
    padding: 0.5rem 0;
  }
  
  .slider-container input[type="range"] {
    width: 100%;
    height: 6px;
    background: #e5e7eb;
    border-radius: 3px;
    outline: none;
    -webkit-appearance: none;
  }
  
  .slider-container input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 18px;
    height: 18px;
    background: #3b82f6;
    border-radius: 50%;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .slider-container input[type="range"]::-webkit-slider-thumb:hover {
    transform: scale(1.1);
    box-shadow: 0 0 0 8px rgba(59, 130, 246, 0.1);
  }
  
  .slider-labels {
    display: flex;
    justify-content: space-between;
    margin-top: 0.5rem;
    font-size: 0.7rem;
    color: #9ca3af;
  }
  
  /* Advanced Options */
  .advanced-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.5rem 0;
    background: none;
    border: none;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
    color: #6b7280;
    transition: color 0.2s;
  }
  
  .advanced-toggle:hover {
    color: #374151;
  }
  
  .advanced-options {
    margin-top: 1rem;
    padding: 1rem;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
  }
  
  /* Capture Input */
  .capture-input {
    display: flex;
    gap: 0.5rem;
  }
  
  .capture-input input {
    flex: 1;
  }
  
  .add-btn {
    padding: 0.625rem 1rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
  }
  
  .add-btn:hover:not(:disabled) {
    background: #2563eb;
  }
  
  .add-btn:disabled {
    background: #9ca3af;
    cursor: not-allowed;
  }
  
  .captures-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.75rem;
  }
  
  .capture-tag {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.375rem 0.625rem;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 6px;
    font-family: monospace;
    font-size: 0.8rem;
    color: #1e40af;
  }
  
  .tag-remove {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 50%;
    cursor: pointer;
    font-size: 0.875rem;
    line-height: 1;
  }
  
  .tag-remove:hover {
    background: #2563eb;
  }
  
  /* Action Builder */
  .action-builder {
    padding: 1.25rem;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    margin-bottom: 1.5rem;
  }
  
  .action-builder h3 {
    margin: 0 0 1rem 0;
    font-size: 1rem;
    font-weight: 600;
    color: #111827;
  }
  
  .action-type-selector {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.5rem;
    margin-bottom: 1rem;
  }
  
  .action-type-btn {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    text-align: left;
  }
  
  .action-type-btn:hover:not(:disabled) {
    border-color: #d1d5db;
    background: #f9fafb;
  }
  
  .action-type-btn.selected {
    background: #eff6ff;
    border-color: #3b82f6;
  }
  
  .action-type-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .action-icon {
    font-size: 1.25rem;
  }
  
  .action-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }
  
  .action-label {
    font-size: 0.875rem;
    font-weight: 500;
    color: #111827;
  }
  
  .action-desc {
    font-size: 0.7rem;
    color: #6b7280;
  }
  
  .action-fields {
    margin-top: 1rem;
  }
  
  .command-type-toggle {
    display: flex;
    gap: 0.25rem;
    padding: 0.25rem;
    background: #f3f4f6;
    border-radius: 6px;
  }
  
  .command-type-toggle button {
    flex: 1;
    padding: 0.5rem;
    background: none;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
    color: #6b7280;
    transition: all 0.2s;
  }
  
  .command-type-toggle button.active {
    background: white;
    color: #111827;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  }
  
  .add-action-btn {
    width: 100%;
    padding: 0.75rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
  }
  
  .add-action-btn:hover:not(:disabled) {
    background: #2563eb;
  }
  
  .add-action-btn:disabled {
    background: #9ca3af;
    cursor: not-allowed;
  }
  
  /* Actions List */
  .actions-list h3 {
    margin: 0 0 1rem 0;
    font-size: 1rem;
    font-weight: 600;
    color: #111827;
  }
  
  .action-card {
    position: relative;
    padding: 1rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    margin-bottom: 0.75rem;
  }
  
  .action-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }
  
  .action-title {
    font-size: 0.875rem;
    font-weight: 500;
    color: #111827;
  }
  
  .action-summary {
    font-family: monospace;
    font-size: 0.75rem;
    color: #6b7280;
  }
  
  .action-remove {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #fef2f2;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    color: #ef4444;
    transition: all 0.2s;
  }
  
  .action-remove:hover:not(:disabled) {
    background: #fee2e2;
  }
  
  .action-remove svg {
    width: 16px;
    height: 16px;
  }
  
  /* Empty State */
  .empty-state {
    text-align: center;
    padding: 2rem;
    color: #9ca3af;
  }
  
  .empty-state svg {
    width: 48px;
    height: 48px;
    margin: 0 auto 1rem;
  }
  
  .empty-state p {
    margin: 0 0 0.5rem 0;
    font-size: 0.875rem;
    font-weight: 500;
    color: #6b7280;
  }
  
  .empty-state small {
    font-size: 0.75rem;
  }
  
  /* Footer */
  .attachment-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    width: 100%;
  }
  
  .btn-secondary,
  .btn-primary {
    padding: 0.625rem 1.25rem;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .btn-secondary {
    background: white;
    color: #374151;
    border: 1px solid #d1d5db;
  }
  
  .btn-secondary:hover:not(:disabled) {
    background: #f9fafb;
  }
  
  .btn-primary {
    background: #3b82f6;
    color: white;
  }
  
  .btn-primary:hover:not(:disabled) {
    background: #2563eb;
  }
  
  .btn-secondary:disabled,
  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  /* Responsive */
  @media (max-width: 640px) {
    :global(.watcher-attachment-content) {
      padding: 1rem !important;
    }

    .templates-grid {
      grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
    }

    .mode-buttons {
      grid-template-columns: 1fr;
    }

    .action-type-selector {
      grid-template-columns: 1fr;
    }
  }
</style>