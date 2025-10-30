<script lang="ts">
  import { run, createBubbler, stopPropagation } from 'svelte/legacy';

  const bubble = createBubbler();
  import { createEventDispatcher } from 'svelte';
  import { fly, slide } from 'svelte/transition';
  import { api } from '../services/api';
  import type { WatcherAction } from '../types/watchers';
  import { Plus, X, Eye, Zap, Save, ChevronDown, ChevronRight } from 'lucide-svelte';

  interface Props {
    jobId: string;
    hostname: string;
    isVisible?: boolean;
    copiedWatcherConfig?: any;
  }

  let {
    jobId,
    hostname,
    isVisible = false,
    copiedWatcherConfig = null
  }: Props = $props();

  const dispatch = createEventDispatcher();

  // Debug logging
  run(() => {
    console.log('WatcherCreator props:', { jobId, hostname, isVisible, copiedWatcherConfig });
  });

  // Smart defaults for immediate creation
  let watcherName = $state('');
  let pattern = $state('');
  let interval = $state(30);
  let watcherOutputType: 'stdout' | 'stderr' | 'both' = $state('stdout');

  // Initialize actions based on whether we're copying or creating new
  let actions: WatcherAction[] = $state([]);

  // Track whether we've already initialized from copy to prevent overwriting user edits
  let hasInitializedFromCopy = $state(false);

  // Advanced options - declare before run() blocks that use them
  let captures: string[] = $state([]);
  let condition = $state('');
  let maxTriggers = $state(10);
  let timerModeEnabled = $state(false);
  let useSeparateTimerInterval = $state(false);
  let timerInterval = $state(30);

  // Initialize from copied configuration if provided
  run(() => {
    if (copiedWatcherConfig && isVisible && !hasInitializedFromCopy) {
      console.log('Initializing from copied config:', copiedWatcherConfig);
      watcherName = `Copy of ${copiedWatcherConfig.name}`;
      pattern = copiedWatcherConfig.pattern || '';
      captures = copiedWatcherConfig.captures || [];
      interval = copiedWatcherConfig.interval_seconds || copiedWatcherConfig.interval || 30;
      watcherOutputType = copiedWatcherConfig.output_type || 'stdout';
      maxTriggers = copiedWatcherConfig.max_triggers || 10;
      timerModeEnabled = copiedWatcherConfig.timer_mode_enabled || false;
      timerInterval = copiedWatcherConfig.timer_interval_seconds || 30;
      if (copiedWatcherConfig.condition) {
        condition = copiedWatcherConfig.condition;
      }
      // Copy actions with all their properties
      if (copiedWatcherConfig.actions && copiedWatcherConfig.actions.length > 0) {
        console.log('Copying actions:', copiedWatcherConfig.actions);
        actions = copiedWatcherConfig.actions.map(action => ({
          type: action.type,
          params: { ...action.params }
        }));
      } else {
        // Only set default action if no actions to copy
        actions = [{
          type: 'log_event',
          params: { message: 'Pattern matched in job output' }
        }];
      }
      hasInitializedFromCopy = true;
    } else if (!copiedWatcherConfig && actions.length === 0) {
      // Only set default action for new watchers (not copies)
      actions = [{
        type: 'log_event',
        params: { message: 'Pattern matched in job output' }
      }];
    }
  });

  // Reset initialization flag when component is closed or config changes
  run(() => {
    if (!isVisible || !copiedWatcherConfig) {
      hasInitializedFromCopy = false;
    }
  });

  // Update watcher name reactively when jobId changes (only for new watchers)
  run(() => {
    if (jobId && !copiedWatcherConfig && !watcherName) {
      watcherName = `Watcher for Job ${jobId}`;
    }
  });

  // Ensure all actions have params initialized (defensive programming)
  run(() => {
    actions = actions.map(action => ({
      ...action,
      params: action.params || {}
    }))
  });

  // Progressive disclosure states
  let showAdvanced = $state(false);
  let showPatternHelp = false;
  let showJobOutput = $state(false);
  let showTemplates = $state(false);

  // UI state
  let isSubmitting = $state(false);
  let error: string | null = $state(null);
  let success: string | null = $state(null);
  let jobOutput = $state('');
  let loadingOutput = $state(false);

  // Regex testing state
  interface PatternMatch {
    matched_text: string;
    captures: string[];
    position: number;
  }
  let patternMatches: PatternMatch[] = $state([]);
  let patternError: string | null = $state(null);
  let showPatternTest = $state(false);

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
          lines: 50
        }
      });
      // Get the appropriate output based on the selected type
      let output = '';
      if (watcherOutputType === 'stdout') {
        output = response.data.stdout || '';
      } else if (watcherOutputType === 'stderr') {
        output = response.data.stderr || '';
      } else {
        // 'both' - combine stdout and stderr
        output = (response.data.stdout || '') + '\n' + (response.data.stderr || '');
      }
      jobOutput = output || 'No output available';
    } catch (err) {
      console.error('Failed to fetch job output:', err);
      jobOutput = 'Failed to load job output';
    } finally {
      loadingOutput = false;
    }
  }

  function testPattern() {
    patternMatches = [];
    patternError = null;

    if (!pattern.trim()) {
      patternError = 'Please enter a pattern to test';
      return;
    }

    if (!jobOutput || jobOutput === 'No output available' || jobOutput === 'Failed to load job output') {
      patternError = 'Please load job output first';
      return;
    }

    try {
      // Create regex with multiline flag (same as backend)
      const regex = new RegExp(pattern, 'gm');
      const matches: PatternMatch[] = [];

      let match;
      while ((match = regex.exec(jobOutput)) !== null) {
        matches.push({
          matched_text: match[0],
          captures: match.slice(1), // All captured groups
          position: match.index
        });

        // Prevent infinite loop for zero-width matches
        if (match.index === regex.lastIndex) {
          regex.lastIndex++;
        }
      }

      patternMatches = matches;
      showPatternTest = true;
    } catch (err: any) {
      patternError = `Invalid regex pattern: ${err.message}`;
      patternMatches = [];
    }
  }

  // Auto-test pattern when it changes (debounced)
  let testPatternTimeout: number | null = null;
  run(() => {
    // Only auto-test if output is loaded and pattern is not empty
    if (pattern && jobOutput && jobOutput !== 'No output available' && jobOutput !== 'Failed to load job output') {
      if (testPatternTimeout) {
        clearTimeout(testPatternTimeout);
      }
      testPatternTimeout = window.setTimeout(() => {
        testPattern();
      }, 500);
    }
  });

  function addSimpleAction() {
    actions = [...actions, {
      type: 'log_event',
      params: { message: '' }
    }];
  }

  // Initialize params when action type changes
  function updateActionType(index: number, newType: string) {
    const action = actions[index];
    action.type = newType;

    // Initialize params based on type
    switch(newType) {
      case 'log_event':
        action.params = { message: '' };
        break;
      case 'store_metric':
        action.params = { metric_name: '', value: '' };
        break;
      case 'run_command':
        action.params = { command: '' };
        break;
      case 'notify_email':
        action.params = { to: '', subject: '', message: '' };
        break;
      case 'notify_slack':
        action.params = { webhook: '', message: '' };
        break;
      case 'cancel_job':
        action.params = { reason: '' };
        break;
      case 'resubmit':
        action.params = { delay: 0 };
        break;
      case 'pause_watcher':
        action.params = {};
        break;
      default:
        action.params = {};
    }

    actions = actions; // Trigger reactivity
  }

  function removeAction(index: number) {
    actions = actions.filter((_, i) => i !== index);
  }

  async function createWatcher() {
    console.log('createWatcher called');

    // Validate required fields
    if (!watcherName.trim()) {
      error = 'Watcher name is required';
      return;
    }

    if (!pattern.trim()) {
      error = 'Pattern is required';
      console.log('Pattern validation failed');
      return;
    }

    if (interval < 1 || interval > 3600) {
      error = 'Check interval must be between 1 and 3600 seconds';
      return;
    }

    if (maxTriggers < 1 || maxTriggers > 1000) {
      error = 'Max triggers must be between 1 and 1000';
      return;
    }

    if (timerModeEnabled && useSeparateTimerInterval && (timerInterval < 1 || timerInterval > 3600)) {
      error = 'Timer interval must be between 1 and 3600 seconds';
      return;
    }

    // Validate actions
    for (let i = 0; i < actions.length; i++) {
      const action = actions[i];
      const params = action.params || {};

      switch (action.type) {
        case 'store_metric':
          if (!params.metric_name || !params.metric_name.trim()) {
            error = `Action ${i + 1}: Metric name is required`;
            return;
          }
          if (!params.value || !params.value.trim()) {
            error = `Action ${i + 1}: Value expression is required`;
            return;
          }
          break;
        case 'notify_email':
          if (!params.to || !params.to.trim()) {
            error = `Action ${i + 1}: Email address is required`;
            return;
          }
          const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
          if (!emailRegex.test(params.to)) {
            error = `Action ${i + 1}: Invalid email address`;
            return;
          }
          if (!params.subject || !params.subject.trim()) {
            error = `Action ${i + 1}: Email subject is required`;
            return;
          }
          break;
        case 'notify_slack':
          if (!params.webhook || !params.webhook.trim()) {
            error = `Action ${i + 1}: Slack webhook URL is required`;
            return;
          }
          try {
            const url = new URL(params.webhook);
            if (!params.webhook.startsWith('https://hooks.slack.com/services/')) {
              error = `Action ${i + 1}: Invalid Slack webhook URL format`;
              return;
            }
          } catch {
            error = `Action ${i + 1}: Invalid URL`;
            return;
          }
          break;
        case 'resubmit':
          if (params.delay !== undefined && params.delay !== null) {
            const delay = Number(params.delay);
            if (isNaN(delay) || delay < 0 || delay > 86400) {
              error = `Action ${i + 1}: Delay must be between 0 and 86400 seconds`;
              return;
            }
          }
          break;
      }
    }

    isSubmitting = true;
    error = null;
    success = null;

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
        // Send timer_interval_seconds when timer mode is enabled
        ...(timerModeEnabled ? {
          timer_interval_seconds: useSeparateTimerInterval ? timerInterval : interval
        } : {})
      };

      console.log('Sending watcher data:', watcherData);
      const response = await api.post('/api/watchers', watcherData);
      console.log('Watcher created successfully:', response.data);

      // Show success message
      success = 'Watcher created successfully!';
      isSubmitting = false;

      // Wait a bit for user to see the success message
      setTimeout(() => {
        dispatch('created');
        close();
      }, 1500);
    } catch (err: any) {
      console.error('Failed to create watcher:', err);
      error = err.response?.data?.detail || 'Failed to create watcher';
      isSubmitting = false;
    }
  }

  let overlayElement: HTMLElement = $state();
  let mouseDownInsideDialog = false;

  function close() {
    dispatch('close');
  }

  function handleOverlayMouseDown(event: MouseEvent) {
    // Check if mousedown started on the overlay itself
    mouseDownInsideDialog = event.target !== overlayElement;
  }

  function handleOverlayClick(event: MouseEvent) {
    // Don't close if:
    // 1. Click started inside the dialog
    // 2. Text is selected
    // 3. Click target is not the overlay

    const selection = window.getSelection();
    const hasSelection = selection && selection.toString().length > 0;

    if (mouseDownInsideDialog || hasSelection || event.target !== overlayElement) {
      return;
    }

    close();
  }

  function handleDialogMouseDown(event: MouseEvent) {
    mouseDownInsideDialog = true;
    event.stopPropagation();
  }

  // Auto-fetch job output when output viewer is opened
  run(() => {
    if (showJobOutput && !jobOutput && !loadingOutput) {
      fetchJobOutput();
    }
  });
</script>

{#if isVisible}
  <div class="watcher-creator-overlay" bind:this={overlayElement} onmousedown={handleOverlayMouseDown} onclick={handleOverlayClick} role="presentation">
    <div class="watcher-creator" onmousedown={handleDialogMouseDown} onclick={stopPropagation(bubble('click'))} onkeydown={() => {}} role="dialog" aria-modal="true" tabindex="-1" transition:slide={{ duration: 300 }}>
    <div class="creator-header">
      <div class="header-info">
        <h3>{copiedWatcherConfig ? 'Copy Watcher' : 'Create Watcher'}</h3>
        <span class="job-info">
          {#if jobId && hostname}
            Job #{jobId} on {hostname}
          {:else}
            Selecting job...
          {/if}
        </span>
      </div>
      <button class="close-btn" onclick={close}>
        <X class="w-4 h-4" />
      </button>
    </div>

    {#if error}
      <div class="error-message" transition:slide={{ duration: 200 }}>
        {error}
      </div>
    {/if}

    {#if success}
      <div class="success-message" transition:slide={{ duration: 200 }}>
        {success}
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
                onclick={() => showTemplates = !showTemplates}
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
                    onclick={() => applyTemplate(template)}
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
            <label for="interval">
              Check Interval
              <span class="label-hint">{timerModeEnabled ? '(for initial pattern search)' : ''}</span>
            </label>
            <select id="interval" bind:value={interval} class="form-select">
              <option value={10}>10 seconds</option>
              <option value={30}>30 seconds</option>
              <option value={60}>1 minute</option>
              <option value={300}>5 minutes</option>
              <option value={600}>10 minutes</option>
              <option value={1800}>30 minutes</option>
              <option value={3600}>1 hour</option>
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
          onclick={() => { showJobOutput = !showJobOutput; }}
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
                onclick={fetchJobOutput}
                disabled={loadingOutput}
              >
                {loadingOutput ? 'Loading...' : 'Refresh'}
              </button>
              <button
                class="test-pattern-btn"
                onclick={testPattern}
                disabled={!pattern.trim() || !jobOutput || jobOutput === 'No output available'}
              >
                Test Pattern
              </button>
            </div>

            {#if patternError}
              <div class="pattern-error" transition:slide={{ duration: 200 }}>
                {patternError}
              </div>
            {/if}

            {#if showPatternTest && !patternError}
              <div class="pattern-test-results" transition:slide={{ duration: 200 }}>
                <div class="results-header">
                  <strong>{patternMatches.length}</strong> match{patternMatches.length !== 1 ? 'es' : ''} found
                </div>
                {#if patternMatches.length > 0}
                  <div class="matches-list">
                    {#each patternMatches.slice(0, 5) as match, i}
                      <div class="match-item">
                        <div class="match-header">Match {i + 1}</div>
                        <div class="match-text">
                          <code>{match.matched_text}</code>
                        </div>
                        {#if match.captures.length > 0 && match.captures.some(c => c !== undefined)}
                          <div class="captures-list">
                            <span class="captures-label">Captured groups:</span>
                            {#each match.captures as capture, capIdx}
                              {#if capture !== undefined}
                                <div class="capture-item">
                                  <span class="capture-index">${capIdx + 1}:</span>
                                  <code>{capture}</code>
                                </div>
                              {/if}
                            {/each}
                          </div>
                        {/if}
                      </div>
                    {/each}
                    {#if patternMatches.length > 5}
                      <div class="more-matches">
                        ... and {patternMatches.length - 5} more match{patternMatches.length - 5 !== 1 ? 'es' : ''}
                      </div>
                    {/if}
                  </div>
                {/if}
              </div>
            {/if}

            <pre class="output-content">{jobOutput}</pre>
          </div>
        {/if}
      </div>

      <!-- Advanced Options (Collapsed by default) -->
      <div class="advanced-section">
        <button
          class="section-toggle"
          onclick={() => showAdvanced = !showAdvanced}
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
                  oninput={(e) => {
                    const value = Number(e.target.value);
                    if (!isNaN(value)) {
                      maxTriggers = Math.max(1, Math.min(1000, value));
                    }
                  }}
                />
              </div>
              <div class="form-group">
                <label title="After first pattern match, switch to periodic execution mode">
                  <input type="checkbox" bind:checked={timerModeEnabled} />
                  Timer Mode
                </label>
                {#if timerModeEnabled}
                  <div class="timer-mode-explanation">
                    <p class="explanation-text">
                      <strong>How Timer Mode Works:</strong><br/>
                      1. Watcher searches for pattern every {interval}s<br/>
                      2. When pattern is found, switches to timer mode<br/>
                      3. Executes actions periodically without pattern matching
                    </p>
                    <label class="checkbox-label">
                      <input
                        type="checkbox"
                        bind:checked={useSeparateTimerInterval}
                      />
                      Use different interval for timer execution
                    </label>
                    {#if useSeparateTimerInterval}
                      <label for="timer-interval" class="timer-interval-label">
                        Timer Execution Interval (seconds)
                      </label>
                      <input
                        id="timer-interval"
                        type="number"
                        bind:value={timerInterval}
                        placeholder="Timer interval (seconds)"
                        class="form-input mt-2"
                        min="1"
                        max="3600"
                        oninput={(e) => {
                          const value = Number(e.target.value);
                          if (!isNaN(value)) {
                            timerInterval = Math.max(1, Math.min(3600, value));
                          }
                        }}
                      />
                      <span class="form-hint">After pattern match, actions execute every {timerInterval}s</span>
                    {:else}
                      <span class="form-hint">After pattern match, actions execute every {interval}s (same as check interval)</span>
                    {/if}
                  </div>
                {:else}
                  <span class="form-hint">Watcher will continuously search for pattern every {interval}s</span>
                {/if}
              </div>
            </div>

            <!-- Simple Actions List -->
            <div class="actions-section">
              <div class="section-header">
                <span class="section-label">Actions</span>
                <button class="add-action-btn" onclick={addSimpleAction}>
                  <Plus class="w-3 h-3" />
                  Add
                </button>
              </div>

              {#each actions as action, i}
                <div class="action-item">
                  <select
                    value={action.type}
                    onchange={(e) => updateActionType(i, e.target.value)}
                    class="action-type-select">
                    <option value="log_event">Log Event</option>
                    <option value="store_metric">Store Metric</option>
                    <option value="run_command">Run Command</option>
                    <option value="notify_email">Send Email</option>
                    <option value="notify_slack">Send Slack</option>
                    <option value="cancel_job">Cancel Job</option>
                    <option value="resubmit">Resubmit Job</option>
                    <option value="pause_watcher">Pause Watcher</option>
                  </select>

                  {#if action.type === 'log_event'}
                    <input
                      type="text"
                      bind:value={action.params.message}
                      placeholder="Log message (can use $1, $2 for captures)"
                      class="action-input"
                    />
                  {:else if action.type === 'store_metric'}
                    <input
                      type="text"
                      bind:value={action.params.metric_name}
                      placeholder="Metric name (e.g., gpu_usage)"
                      class="action-input"
                      pattern="^[a-zA-Z_][a-zA-Z0-9_]*$"
                      title="Must start with letter or underscore, followed by letters, numbers, or underscores"
                      class:invalid={action.params.metric_name && !/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(action.params.metric_name)}
                    />
                    <input
                      type="text"
                      bind:value={action.params.value}
                      placeholder="Value (e.g., $1 or float($1))"
                      class="action-input"
                    />
                  {:else if action.type === 'run_command'}
                    <input
                      type="text"
                      bind:value={action.params.command}
                      placeholder="Command (e.g., wandb sync, python script.py)"
                      class="action-input wide"
                    />
                  {:else if action.type === 'notify_email'}
                    <input
                      type="email"
                      bind:value={action.params.to}
                      placeholder="Email address"
                      class="action-input"
                      pattern="^[^\s@]+@[^\s@]+\.[^\s@]+$"
                      class:invalid={action.params.to && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(action.params.to)}
                    />
                    <input
                      type="text"
                      bind:value={action.params.subject}
                      placeholder="Subject"
                      class="action-input"
                    />
                  {:else if action.type === 'notify_slack'}
                    <input
                      type="url"
                      bind:value={action.params.webhook}
                      placeholder="Slack webhook URL"
                      class="action-input wide"
                      pattern="^https://hooks\.slack\.com/services/.+"
                      class:invalid={action.params.webhook && !action.params.webhook.startsWith('https://hooks.slack.com/services/')}
                    />
                    <input
                      type="text"
                      bind:value={action.params.message}
                      placeholder="Message"
                      class="action-input"
                    />
                  {:else if action.type === 'cancel_job'}
                    <input
                      type="text"
                      bind:value={action.params.reason}
                      placeholder="Cancellation reason (optional)"
                      class="action-input wide"
                    />
                  {:else if action.type === 'resubmit'}
                    <input
                      type="number"
                      bind:value={action.params.delay}
                      placeholder="Delay in seconds"
                      class="action-input"
                      min="0"
                      max="86400"
                      oninput={(e) => {
                        const value = Number(e.target.value);
                        if (!isNaN(value)) {
                          action.params.delay = Math.max(0, Math.min(86400, value));
                        }
                      }}
                    />
                  {:else if action.type === 'pause_watcher'}
                    <span class="action-desc">This watcher will pause after triggering</span>
                  {/if}

                  <button
                    class="remove-action-btn"
                    onclick={() => removeAction(i)}
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
        <button class="cancel-btn" onclick={close} disabled={isSubmitting}>
          Cancel
        </button>
        <button
          class="create-btn"
          onclick={createWatcher}
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
  </div>
{/if}

<style>
  .watcher-creator-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: color-mix(in srgb, var(--foreground) 50%, transparent);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }
  .watcher-creator {
    background: var(--background);
    border: 1px solid var(--border);
    border-radius: 8px;
    max-width: 600px;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 10px 25px color-mix(in srgb, var(--foreground) 20%, transparent);
  }

  .creator-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    background: var(--secondary);
    border-bottom: 1px solid var(--border);
  }

  .header-info h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--foreground);
  }

  .job-info {
    font-size: 0.875rem;
    color: var(--muted-foreground);
  }

  .close-btn {
    background: none;
    border: none;
    color: var(--muted-foreground);
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 4px;
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: var(--secondary);
    color: var(--foreground);
  }

  .creator-content {
    padding: 1rem;
  }

  .error-message {
    background: var(--error-bg);
    color: var(--destructive);
    padding: 0.75rem;
    margin: 0 1rem;
    border-radius: 6px;
    font-size: 0.875rem;
    border: 1px solid var(--error-bg);
  }

  .success-message {
    background: var(--success-bg);
    color: var(--success);
    padding: 0.75rem;
    margin: 0 1rem;
    border-radius: 6px;
    font-size: 0.875rem;
    border: 1px solid var(--success-bg);
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
    color: var(--foreground);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .help-toggle {
    background: var(--accent);
    color: var(--accent-foreground);
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
    background: var(--accent);
  }

  .form-input,
  .form-select {
    border: 1px solid var(--muted);
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    font-size: 0.875rem;
    transition: border-color 0.2s;
    background: var(--background);
    color: var(--foreground);
  }

  .form-input:focus,
  .form-select:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 10%, transparent);
  }

  .form-input.error {
    border-color: var(--destructive);
  }

  .template-suggestions {
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--background);
    overflow: hidden;
    box-shadow: 0 4px 6px -1px color-mix(in srgb, var(--foreground) 10%, transparent);
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
    border-bottom: 1px solid var(--secondary);
  }

  .template-suggestion:hover {
    background: var(--secondary);
  }

  .template-suggestion:last-child {
    border-bottom: none;
  }

  .template-suggestion strong {
    display: block;
    color: var(--foreground);
    font-size: 0.875rem;
    margin-bottom: 0.25rem;
  }

  .template-suggestion span {
    display: block;
    color: var(--muted-foreground);
    font-size: 0.75rem;
    margin-bottom: 0.5rem;
  }

  .template-suggestion code {
    display: block;
    background: var(--secondary);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.75rem;
    color: var(--foreground);
  }

  .helper-tools {
    margin-bottom: 1rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
  }

  .tool-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.75rem;
    background: var(--secondary);
    border: none;
    cursor: pointer;
    font-size: 0.875rem;
    color: var(--foreground);
    transition: background 0.2s;
  }

  .tool-toggle:hover {
    background: var(--secondary);
  }

  .job-output-preview {
    border-top: 1px solid var(--border);
  }

  .output-controls {
    padding: 0.5rem 0.75rem;
    background: var(--secondary);
    border-bottom: 1px solid var(--border);
  }

  .refresh-btn,
  .test-pattern-btn {
    background: var(--accent);
    color: var(--accent-foreground);
    border: none;
    border-radius: 4px;
    padding: 0.25rem 0.75rem;
    font-size: 0.75rem;
    cursor: pointer;
    transition: background 0.2s;
    margin-right: 0.5rem;
  }

  .refresh-btn:hover:not(:disabled),
  .test-pattern-btn:hover:not(:disabled) {
    background: var(--accent);
  }

  .refresh-btn:disabled,
  .test-pattern-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .test-pattern-btn {
    background: var(--success);
  }

  .test-pattern-btn:hover:not(:disabled) {
    background: var(--success);
  }

  .pattern-error {
    background: var(--error-bg);
    color: var(--destructive);
    padding: 0.5rem 0.75rem;
    font-size: 0.75rem;
    border-bottom: 1px solid var(--error-bg);
  }

  .pattern-test-results {
    background: var(--success-bg);
    border-bottom: 1px solid var(--success-bg);
    padding: 0.75rem;
  }

  .results-header {
    font-size: 0.875rem;
    color: var(--success);
    margin-bottom: 0.75rem;
  }

  .results-header strong {
    font-size: 1rem;
    color: var(--success);
  }

  .matches-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .match-item {
    background: var(--background);
    border: 1px solid var(--success-bg);
    border-radius: 6px;
    padding: 0.625rem;
  }

  .match-header {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--success);
    margin-bottom: 0.375rem;
  }

  .match-text {
    margin-bottom: 0.5rem;
  }

  .match-text code {
    display: inline-block;
    background: var(--secondary);
    border: 1px solid var(--border);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.75rem;
    color: var(--foreground);
    max-width: 100%;
    overflow-x: auto;
  }

  .captures-list {
    padding-top: 0.5rem;
    border-top: 1px solid var(--secondary);
  }

  .captures-label {
    display: block;
    font-size: 0.6875rem;
    color: var(--muted-foreground);
    margin-bottom: 0.375rem;
    font-weight: 500;
  }

  .capture-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.25rem;
    font-size: 0.75rem;
  }

  .capture-index {
    color: var(--accent);
    font-weight: 600;
    font-family: monospace;
    min-width: 2rem;
  }

  .capture-item code {
    background: var(--secondary);
    border: 1px solid var(--border);
    padding: 0.125rem 0.375rem;
    border-radius: 3px;
    font-family: monospace;
    font-size: 0.6875rem;
    color: var(--foreground);
  }

  .more-matches {
    font-size: 0.75rem;
    color: var(--muted-foreground);
    font-style: italic;
    text-align: center;
    padding: 0.5rem;
  }

  .output-content {
    padding: 0.75rem;
    background: var(--foreground);
    color: var(--secondary);
    font-family: monospace;
    font-size: 0.75rem;
    max-height: 200px;
    overflow-y: auto;
    margin: 0;
    white-space: pre-wrap;
  }

  .advanced-section {
    margin-bottom: 1rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
  }

  .section-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.75rem;
    background: var(--secondary);
    border: none;
    cursor: pointer;
    font-size: 0.875rem;
    color: var(--foreground);
    font-weight: 500;
    transition: background 0.2s;
  }

  .section-toggle:hover {
    background: var(--secondary);
  }

  .advanced-content {
    padding: 1rem;
    border-top: 1px solid var(--border);
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

  .section-header .section-label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--foreground);
  }

  .add-action-btn {
    background: var(--success);
    color: var(--accent-foreground);
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
    background: var(--success);
  }

  .action-item {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 0.5rem;
    padding: 0.5rem;
    background: var(--secondary);
    border-radius: 6px;
  }

  .action-type-select {
    min-width: 120px;
    background: var(--background);
    color: var(--foreground);
  }

  .action-input {
    flex: 1;
    border: 1px solid var(--muted);
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
    background: var(--background);
    color: var(--foreground);
  }

  .action-input.wide {
    min-width: 250px;
  }

  .action-desc {
    flex: 1;
    font-size: 0.75rem;
    color: var(--muted-foreground);
    font-style: italic;
    padding: 0.25rem 0.5rem;
  }

  .remove-action-btn {
    background: var(--destructive);
    color: var(--accent-foreground);
    border: none;
    border-radius: 4px;
    padding: 0.25rem;
    cursor: pointer;
    transition: background 0.2s;
    display: flex;
    align-items: center;
  }

  .remove-action-btn:hover {
    background: var(--destructive);
  }

  .action-buttons {
    display: flex;
    gap: 0.75rem;
    justify-content: flex-end;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
  }

  .cancel-btn {
    background: var(--background);
    border: 1px solid var(--muted);
    color: var(--foreground);
    border-radius: 6px;
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .cancel-btn:hover:not(:disabled) {
    background: var(--secondary);
    border-color: var(--muted-foreground);
  }

  .create-btn {
    background: var(--accent);
    color: var(--accent-foreground);
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
    background: var(--accent);
  }

  .create-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* Timer mode styles */
  .timer-mode-explanation {
    margin-top: 0.5rem;
    padding-left: 1.5rem;
  }

  .explanation-text {
    background: var(--info-bg);
    border: 1px solid var(--info-bg);
    border-radius: 6px;
    padding: 0.75rem;
    margin-bottom: 0.75rem;
    font-size: 0.8125rem;
    line-height: 1.5;
    color: var(--accent);
  }

  .explanation-text strong {
    color: var(--accent);
  }

  .timer-interval-label {
    display: block;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--foreground);
    margin-top: 0.5rem;
    margin-bottom: 0.25rem;
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    color: var(--muted-foreground);
    margin-bottom: 0.5rem;
  }

  .form-hint {
    display: block;
    font-size: 0.75rem;
    color: var(--muted-foreground);
    margin-top: 0.25rem;
    font-style: italic;
  }

  .label-hint {
    font-size: 0.75rem;
    color: var(--muted-foreground);
    font-weight: normal;
    font-style: italic;
    margin-left: 0.25rem;
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

  /* Validation styles */
  .action-input.invalid {
    border-color: var(--destructive);
  }

  .action-input:invalid {
    border-color: var(--destructive);
  }

  .form-input:invalid {
    border-color: var(--destructive);
  }
</style>