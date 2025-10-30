<script lang="ts">
  import { run } from 'svelte/legacy';

  import { createEventDispatcher, onMount } from 'svelte';
  import { fade, fly, scale, slide } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { api } from '../services/api';
  import type { WatcherAction } from '../types/watchers';
  import type { JobOutputResponse } from '../types/api';
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
  
  // Mobile detection
  let isMobile = $state(false);
  
  // Wizard state - simplified for mobile
  type WizardStep = 'template' | 'pattern' | 'actions' | 'review';
  let currentStep: WizardStep = $state('template');
  let completedSteps: Set<WizardStep> = new Set();
  
  // Form state
  let watcherName = $state('');
  let pattern = $state('');
  let interval = $state(30);
  let captures: string[] = $state([]);
  let captureInput = $state('');
  let condition = '';
  let actions: WatcherAction[] = $state([]);
  let maxTriggers = 10;
  let watcherOutputType: 'stdout' | 'stderr' | 'both' = 'stdout';
  
  // Timer mode settings
  let timerModeEnabled = $state(false);
  let timerInterval = $state(30);
  
  // UI state
  let isSubmitting = $state(false);
  let error: string | null = $state(null);
  let selectedTemplate: any = $state(null);
  let showTemplateDetails = false;
  let testString = $state('');
  let testResult: any = $state(null);
  let patternValid = $state(false);
  let nameValid = $state(false);
  let actionsValid = $state(false);
  
  // Job output viewer state
  let showJobOutput = $state(false);
  let jobOutput: string = $state('');
  let loadingOutput = $state(false);
  let outputError: string | null = $state(null);
  let jobOutputType: 'stdout' | 'stderr' | 'both' = $state('stdout');
  let outputLines = $state(100);
  
  // Action builder state
  let actionType = $state('log_event');
  let actionConfig: Record<string, any> = $state({});
  let editingActionIndex: number | null = $state(null);
  
  // Animation state
  let isTransitioning = false;
  
  // Templates with categories
  const templateCategories = [
    {
      name: 'Monitoring',
      icon: '📊',
      templates: [
        {
          id: 'gpu-monitor',
          name: 'GPU Memory Monitor',
          description: 'Track GPU memory usage and alert on high usage',
          icon: '🎮',
          pattern: 'GPU memory: (\\d+)/(\\d+) MB',
          captures: ['used', 'total'],
          interval: 30,
          actions: [
            { type: 'store_metric', params: { metric_name: 'gpu_memory_mb', value: '$used' } }
          ]
        },
        {
          id: 'cpu-monitor',
          name: 'CPU Usage Monitor',
          description: 'Monitor CPU usage percentage',
          icon: '💻',
          pattern: 'CPU Usage: (\\d+)%',
          captures: ['cpu_percent'],
          interval: 60,
          actions: [
            { type: 'store_metric', params: { metric_name: 'cpu_usage', value: '$cpu_percent' } }
          ]
        }
      ]
    },
    {
      name: 'Machine Learning',
      icon: '🤖',
      templates: [
        {
          id: 'loss-tracker',
          name: 'Training Loss Tracker',
          description: 'Track and visualize training loss over time',
          icon: '📈',
          pattern: 'Loss: ([\\d.]+)',
          captures: ['loss'],
          interval: 10,
          actions: [
            { type: 'store_metric', params: { metric_name: 'training_loss', value: 'float($loss)' } }
          ]
        },
        {
          id: 'epoch-checkpoint',
          name: 'Epoch Checkpoint',
          description: 'Save checkpoints at epoch completion',
          icon: '💾',
          pattern: 'Epoch (\\d+)/(\\d+) completed',
          captures: ['current', 'total'],
          interval: 60,
          actions: [
            { type: 'run_command', params: { command: 'cp -r checkpoint checkpoint_epoch_$current' } }
          ]
        }
      ]
    },
    {
      name: 'Error Handling',
      icon: '🚨',
      templates: [
        {
          id: 'error-detector',
          name: 'Error Detector',
          description: 'Detect and respond to critical errors',
          icon: '❌',
          pattern: '(ERROR|CRITICAL|FATAL):\\s*(.+)',
          captures: ['level', 'message'],
          interval: 5,
          actions: [
            { type: 'log_event', params: {} },
            { type: 'notify_email', params: { subject: 'Critical Error Detected' } }
          ]
        },
        {
          id: 'warning-monitor',
          name: 'Warning Monitor',
          description: 'Track warnings and alert on threshold',
          icon: '⚠️',
          pattern: 'WARNING:\\s*(.+)',
          captures: ['message'],
          interval: 30,
          actions: [
            { type: 'log_event', params: {} }
          ]
        }
      ]
    },
    {
      name: 'Custom',
      icon: '✨',
      templates: [
        {
          id: 'blank',
          name: 'Blank Template',
          description: 'Start from scratch with a custom configuration',
          icon: '📝',
          pattern: '',
          captures: [],
          interval: 30,
          actions: []
        }
      ]
    }
  ];
  
  // Action types with better organization
  const actionCategories = [
    {
      name: 'Logging & Metrics',
      actions: [
        { value: 'log_event', label: 'Log Event', icon: '📝', description: 'Log the matched pattern' },
        { value: 'store_metric', label: 'Store Metric', icon: '📊', description: 'Store a metric value' }
      ]
    },
    {
      name: 'Notifications',
      actions: [
        { value: 'notify_email', label: 'Email Alert', icon: '📧', description: 'Send email notification' },
        { value: 'notify_slack', label: 'Slack Alert', icon: '💬', description: 'Send Slack message' }
      ]
    },
    {
      name: 'Job Control',
      actions: [
        { value: 'cancel_job', label: 'Cancel Job', icon: '🛑', description: 'Cancel the job' },
        { value: 'resubmit', label: 'Resubmit Job', icon: '🔄', description: 'Resubmit the job' },
        { value: 'pause_watcher', label: 'Pause Watcher', icon: '⏸️', description: 'Pause this watcher' }
      ]
    },
    {
      name: 'Commands',
      actions: [
        { value: 'run_command', label: 'Run Command', icon: '⚙️', description: 'Execute a shell command' }
      ]
    }
  ];
  
  // Get all action types flat
  const allActionTypes: any[] = actionCategories.reduce((acc: any[], cat: any) => [...acc, ...cat.actions], []);
  
  function getActionLabel(actionType: string) {
    const action = allActionTypes.find((a: any) => a.value === actionType);
    return action?.label || actionType;
  }
  
  // Check for copied watcher on mount
  onMount(() => {
    // Check if mobile
    isMobile = window.innerWidth <= 768;
    window.addEventListener('resize', () => {
      isMobile = window.innerWidth <= 768;
    });
    
    // Simplify for mobile
    if (isMobile) {
      // Default to simple watcher for mobile
      watcherName = `Watcher ${Date.now()}`;
      interval = 30;
      // Skip template step on mobile
      currentStep = 'pattern';
    }
    
    if (copiedConfig) {
      applyConfig(copiedConfig);
      currentStep = 'pattern';
    } else if (isMobile) {
      // On mobile, skip template selection
      watcherName = 'Quick Watcher';
      interval = 30;
      currentStep = 'pattern';
    }
  });
  
  
  
  function isValidRegex(str: string): boolean {
    try {
      new RegExp(str, 'm'); // Use multiline flag to match backend
      return true;
    } catch {
      return false;
    }
  }
  
  function selectTemplate(template: any) {
    selectedTemplate = template;
    applyConfig({
      name: template.name,
      pattern: template.pattern,
      captures: template.captures || [],
      interval: template.interval || 30,
      actions: template.actions || [],
      timerModeEnabled: template.timerModeEnabled || false,
      timerInterval: template.timerInterval || 30
    });
  }
  
  function applyConfig(config: any) {
    watcherName = config.name || '';
    pattern = config.pattern || '';
    captures = config.captures || [];
    interval = config.interval || 30;
    actions = config.actions || [];
    timerModeEnabled = config.timerModeEnabled || false;
    timerInterval = config.timerInterval || 30;
    condition = config.condition || '';
  }
  
  function goToStep(step: WizardStep) {
    if (isTransitioning) return;
    
    // Validate current step before moving
    const currentIndex = ['template', 'pattern', 'actions', 'review'].indexOf(currentStep);
    const targetIndex = ['template', 'pattern', 'actions', 'review'].indexOf(step);
    
    if (targetIndex > currentIndex && !canProceed[currentStep]) {
      showError('Please complete the current step before proceeding');
      return;
    }
    
    isTransitioning = true;
    setTimeout(() => {
      currentStep = step;
      if (canProceed[currentStep]) {
        completedSteps.add(currentStep);
      }
      isTransitioning = false;
    }, 300);
  }
  
  function nextStep() {
    const steps: WizardStep[] = ['template', 'pattern', 'actions', 'review'];
    const currentIndex = steps.indexOf(currentStep);
    if (currentIndex < steps.length - 1) {
      goToStep(steps[currentIndex + 1]);
    }
  }
  
  function prevStep() {
    const steps: WizardStep[] = ['template', 'pattern', 'actions', 'review'];
    const currentIndex = steps.indexOf(currentStep);
    if (currentIndex > 0) {
      goToStep(steps[currentIndex - 1]);
    }
  }
  
  function testPattern() {
    if (!pattern || !testString) return;
    
    try {
      const regex = new RegExp(pattern, 'gm'); // Use global and multiline flags
      const matches = Array.from(testString.matchAll(regex));
      
      if (matches.length > 0) {
        const firstMatch = matches[0];
        testResult = {
          success: true,
          fullMatch: firstMatch[0],
          groups: firstMatch.slice(1),
          capturedVars: captures.reduce((acc, name, i) => {
            acc[name] = firstMatch[i + 1] || null;
            return acc;
          }, {} as Record<string, string>),
          totalMatches: matches.length,
          allMatches: matches.map(m => m[0])
        };
      } else {
        testResult = { success: false, message: 'No match found' };
      }
    } catch (e: any) {
      testResult = { success: false, message: e.message };
    }
  }
  
  function addCapture() {
    if (captureInput.trim() && !captures.includes(captureInput.trim())) {
      captures = [...captures, captureInput.trim()];
      captureInput = '';
    }
  }
  
  function removeCapture(index: number) {
    captures = captures.filter((_, i) => i !== index);
  }
  
  function addAction() {
    const actionInfo = allActionTypes.find((a: any) => a.value === actionType);
    if (!actionInfo) return;
    
    const newAction: WatcherAction = {
      type: actionType,
      params: { ...actionConfig }
    };
    
    if (editingActionIndex !== null) {
      actions[editingActionIndex] = newAction;
      actions = [...actions]; // Force reactivity
      editingActionIndex = null;
    } else {
      actions = [...actions, newAction];
    }
    
    // Reset form state
    actionConfig = {};
    actionType = 'log_event';
    actionsValid = actions.length > 0;
  }
  
  function editAction(index: number) {
    const action = actions[index];
    actionType = action.type;
    actionConfig = { ...(action.params || {}) };
    editingActionIndex = index;
  }
  
  function removeAction(index: number) {
    actions = actions.filter((_, i) => i !== index);
  }
  
  function showError(message: string) {
    error = message;
    setTimeout(() => error = null, 5000);
  }
  
  async function handleSubmit() {
    if (!nameValid || !patternValid || !actionsValid) {
      showError('Please complete all required fields');
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
        max_triggers: maxTriggers,
        output_type: watcherOutputType,
        timer_mode_enabled: timerModeEnabled,
        timer_interval_seconds: timerInterval
      };
      
      const response = await api.post(`/api/jobs/${jobId}/watchers?host=${hostname}`, [watcherConfig]);
      
      if (response.data && response.data.watcher_ids) {
        dispatch('success', response.data);
      } else {
        throw new Error(response.data?.error || 'Failed to attach watchers');
      }
    } catch (err: any) {
      showError(err.response?.data?.detail || err.message || 'Failed to attach watchers');
    } finally {
      isSubmitting = false;
    }
  }

  function handleClose() {
    open = false;
    dispatch('close');
  }

  async function fetchJobOutput() {
    loadingOutput = true;
    outputError = null;
    
    try {
      const response = await api.get<JobOutputResponse>(
        `/api/jobs/${jobId}/output?host=${encodeURIComponent(hostname)}&lines=${outputLines}`
      );
      
      if (response.data) {
        if (jobOutputType === 'stdout') {
          jobOutput = response.data.stdout || 'No stdout output available';
        } else if (jobOutputType === 'stderr') {
          jobOutput = response.data.stderr || 'No stderr output available';
        } else {
          const stdout = response.data.stdout || '';
          const stderr = response.data.stderr || '';
          jobOutput = `=== STDOUT ===\n${stdout}\n\n=== STDERR ===\n${stderr}`;
        }
      }
    } catch (err) {
      outputError = 'Failed to fetch job output';
      console.error('Error fetching job output:', err);
    } finally {
      loadingOutput = false;
    }
  }
  
  function copyToTestInput(text: string) {
    testString = text;
    // Optionally auto-scroll to test section
    const testSection = document.querySelector('.pattern-tester');
    if (testSection) {
      testSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }
  
  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape' && !isSubmitting) {
      handleClose();
    }
  }
  // Validation
  run(() => {
    nameValid = watcherName.length > 0;
  });
  run(() => {
    patternValid = pattern.length > 0 && isValidRegex(pattern);
  });
  run(() => {
    actionsValid = actions.length > 0;
  });
  let canProceed = $derived({
    template: true,
    pattern: nameValid && patternValid,
    actions: actionsValid,
    review: nameValid && patternValid && actionsValid
  });
  // Step progress
  let stepProgress = $derived({
    template: 100,
    pattern: nameValid && patternValid ? 100 : (nameValid ? 50 : (patternValid ? 50 : 0)),
    actions: actionsValid ? 100 : (actions.length > 0 ? 50 : 0),
    review: 100
  });
</script>

<Dialog
  bind:open
  on:close={handleClose}
  size="full"
  contentClass="attach-watchers-content"
  headerClass="attach-watchers-header"
  footerClass="attach-watchers-footer"
>
  {#snippet header()}
    <div  class="header-wrapper">
      <h2>{isMobile ? `Watcher: Job #${jobId}` : `Create Watcher for Job #${jobId}`}</h2>
      {#if !isMobile}<p class="header-subtitle">Configure a watcher to monitor your job output</p>{/if}
    </div>
  {/snippet}
    
    <!-- Progress Steps -->
    {#if !isMobile}
    <div class="wizard-progress">
      <div class="progress-track">
        {#each ['template', 'pattern', 'actions', 'review'] as step, i}
          {@const isActive = step === currentStep}
          {@const isCompleted = completedSteps.has(step)}
          {@const stepLabels = {
            template: 'Choose Template',
            pattern: 'Define Pattern',
            actions: 'Configure Actions',
            review: 'Review & Submit'
          }}
          
          <button
            class="progress-step"
            class:active={isActive}
            class:completed={isCompleted}
            onclick={() => goToStep(step)}
            disabled={i > 0 && !completedSteps.has(['template', 'pattern', 'actions', 'review'][i - 1])}
          >
            <div class="step-number">
              {#if isCompleted}
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z"/>
                </svg>
              {:else}
                {i + 1}
              {/if}
            </div>
            <div class="step-label">{stepLabels[step]}</div>
            <div class="step-progress">
              <div class="progress-fill" style="width: {stepProgress[step]}%"></div>
            </div>
          </button>
          
          {#if i < 3}
            <div class="progress-connector" class:filled={isCompleted}></div>
          {/if}
        {/each}
      </div>
    </div>
    {:else}
    <!-- Mobile Progress Bar -->
    <div class="mobile-progress">
      <div class="mobile-progress-bar">
        <div class="mobile-progress-fill" style="width: {currentStep === 'pattern' ? '33%' : currentStep === 'actions' ? '66%' : currentStep === 'review' ? '100%' : '0%'}"></div>
      </div>
      <div class="mobile-step-label">
        {currentStep === 'pattern' ? 'Pattern' : currentStep === 'actions' ? 'Actions' : currentStep === 'review' ? 'Review' : 'Template'}
      </div>
    </div>
    {/if}
    
    <!-- Error Message -->
    {#if error}
      <div class="error-banner" transition:slide={{ duration: 300 }}>
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,2L1,21H23M12,6L19.53,19H4.47M11,10V14H13V10M11,16V18H13V16"/>
        </svg>
        {error}
      </div>
    {/if}
    
    <!-- Dialog Body -->
    <div class="dialog-body" class:mobile={isMobile}>
      {#if currentStep === 'template' && !isMobile}
        <div class="step-content" in:fly={{ x: 20, duration: 300 }} out:fly={{ x: -20, duration: 300 }}>
          <div class="step-header">
            <h3>Start with a Template</h3>
            <p>Choose a pre-configured template or start from scratch</p>
          </div>
          
          <div class="template-categories">
            {#each templateCategories as category}
              <div class="template-category">
                <div class="category-header">
                  <span class="category-icon">{category.icon}</span>
                  <h4>{category.name}</h4>
                  <span class="category-count">{category.templates.length}</span>
                </div>
                
                <div class="template-grid">
                  {#each category.templates as template}
                    <button
                      class="template-card"
                      class:selected={selectedTemplate?.id === template.id}
                      onclick={() => selectTemplate(template)}
                    >
                      <div class="template-icon">{template.icon}</div>
                      <div class="template-info">
                        <h5>{template.name}</h5>
                        <p>{template.description}</p>
                      </div>
                      {#if selectedTemplate?.id === template.id}
                        <div class="selected-badge" transition:scale={{ duration: 200 }}>
                          <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z"/>
                          </svg>
                        </div>
                      {/if}
                    </button>
                  {/each}
                </div>
              </div>
            {/each}
          </div>
        </div>
        
      {:else if currentStep === 'pattern'}
        <div class="step-content" in:fly={{ x: 20, duration: 300 }} out:fly={{ x: -20, duration: 300 }}>
          <div class="step-header">
            <h3>{isMobile ? 'Pattern' : 'Define Your Pattern'}</h3>
            <p>{isMobile ? 'What to watch for' : 'Configure what to watch for in your job output'}</p>
          </div>
          
          <!-- Job Output Viewer -->
          <div class="output-viewer-section">
            <button 
              class="output-toggle"
              onclick={() => {
                showJobOutput = !showJobOutput;
                if (showJobOutput && !jobOutput) fetchJobOutput();
              }}
            >
              <svg 
                class="toggle-icon" 
                class:rotated={showJobOutput}
                viewBox="0 0 24 24" 
                fill="currentColor"
              >
                <path d="M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z"/>
              </svg>
              <span>View Job Output</span>
              <span class="badge">Helps design patterns</span>
            </button>
            
            {#if showJobOutput}
              <div class="output-viewer" transition:slide={{ duration: 300 }}>
                <div class="output-controls">
                  <div class="output-type-selector">
                    <button 
                      class="type-btn" 
                      class:active={jobOutputType === 'stdout'}
                      onclick={() => { jobOutputType = 'stdout'; fetchJobOutput(); }}
                    >
                      stdout
                    </button>
                    <button 
                      class="type-btn" 
                      class:active={jobOutputType === 'stderr'}
                      onclick={() => { jobOutputType = 'stderr'; fetchJobOutput(); }}
                    >
                      stderr
                    </button>
                    <button 
                      class="type-btn" 
                      class:active={jobOutputType === 'both'}
                      onclick={() => { jobOutputType = 'both'; fetchJobOutput(); }}
                    >
                      both
                    </button>
                  </div>
                  
                  <div class="lines-control">
                    <span class="lines-label">Lines:</span>
                    <select bind:value={outputLines} onchange={fetchJobOutput}>
                      <option value={50}>50</option>
                      <option value={100}>100</option>
                      <option value={200}>200</option>
                      <option value={500}>500</option>
                    </select>
                  </div>
                  
                  <button 
                    class="refresh-btn" 
                    onclick={fetchJobOutput}
                    disabled={loadingOutput}
                  >
                    {#if loadingOutput}
                      <svg class="spin" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12,4V2A10,10 0 0,0 2,12H4A8,8 0 0,1 12,4Z"/>
                      </svg>
                    {:else}
                      <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z"/>
                      </svg>
                    {/if}
                    Refresh
                  </button>
                </div>
                
                {#if outputError}
                  <div class="output-error">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12,2L1,21H23M12,6L19.53,19H4.47M11,10V14H13V10M11,16V18H13V16"/>
                    </svg>
                    {outputError}
                  </div>
                {:else if jobOutput}
                  <div class="output-content">
                    <pre>{jobOutput}</pre>
                    <button 
                      class="copy-to-test-btn"
                      onclick={() => copyToTestInput(jobOutput)}
                      title="Copy to test input"
                    >
                      <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z"/>
                      </svg>
                      Use in Pattern Tester
                    </button>
                  </div>
                {:else}
                  <div class="output-placeholder">
                    Click refresh to load job output
                  </div>
                {/if}
              </div>
            {/if}
          </div>
          
          <!-- Mobile Quick Templates -->
          {#if isMobile}
            <div class="mobile-quick-templates">
              <div class="quick-template-label">Quick Templates:</div>
              <div class="quick-template-buttons">
                <button 
                  class="quick-template-btn"
                  onclick={() => {
                    pattern = 'Error|ERROR|error';
                    watcherName = 'Error Monitor';
                  }}
                >
                  🚨 Errors
                </button>
                <button 
                  class="quick-template-btn"
                  onclick={() => {
                    pattern = 'GPU memory: (\\d+)/(\\d+)';
                    watcherName = 'GPU Monitor';
                    captures = ['used', 'total'];
                  }}
                >
                  🎮 GPU
                </button>
                <button 
                  class="quick-template-btn"
                  onclick={() => {
                    pattern = 'epoch (\\d+).*loss: ([\\d.]+)';
                    watcherName = 'Training Monitor';
                    captures = ['epoch', 'loss'];
                  }}
                >
                  📊 Training
                </button>
                <button 
                  class="quick-template-btn"
                  onclick={() => {
                    pattern = 'DONE|Complete|Finished';
                    watcherName = 'Completion Monitor';
                  }}
                >
                  ✅ Done
                </button>
              </div>
            </div>
          {/if}
          
          <div class="pattern-form">
            <div class="form-row" class:mobile={isMobile}>
              <div class="form-group">
                <label for="watcher-name">
                  Watcher Name
                  <span class="required">*</span>
                  {#if nameValid}
                    <span class="valid-indicator" transition:scale={{ duration: 200 }}>✓</span>
                  {/if}
                </label>
                <input
                  id="watcher-name"
                  type="text"
                  bind:value={watcherName}
                  placeholder={isMobile ? "Name" : "e.g., GPU Memory Monitor"}
                  class:valid={nameValid}
                  class:invalid={watcherName && !nameValid}
                  autocomplete="off"
                  autocorrect="off"
                />
                {#if !isMobile}<small>A descriptive name for your watcher</small>{/if}
              </div>
              
              <div class="form-group">
                <label for="interval">Check Interval (seconds)</label>
                <div class="interval-input">
                  <input
                    id="interval"
                    type="range"
                    bind:value={interval}
                    min="5"
                    max="300"
                    step="5"
                  />
                  <div class="interval-display">{interval}s</div>
                </div>
                <small>How often to check for pattern matches</small>
              </div>
            </div>
            
            <!-- Timer Mode Settings -->
            <div class="timer-mode-section">
              <div class="timer-mode-toggle">
                <label class="toggle-label">
                  <input
                    type="checkbox"
                    bind:checked={timerModeEnabled}
                    class="toggle-checkbox"
                  />
                  <span class="toggle-slider"></span>
                  <span class="toggle-text">Enable Timer Mode</span>
                </label>
                <small>Switch to timer mode after first pattern match</small>
              </div>
              
              {#if timerModeEnabled}
                <div class="timer-interval-group" transition:slide={{ duration: 300 }}>
                  <label for="timer-interval">Timer Interval (seconds)</label>
                  <div class="interval-input">
                    <input
                      id="timer-interval"
                      type="range"
                      bind:value={timerInterval}
                      min="5"
                      max="300"
                      step="5"
                    />
                    <div class="interval-display">{timerInterval}s</div>
                  </div>
                  <small>How often to execute actions in timer mode</small>
                </div>
              {/if}
            </div>
            
            <div class="form-group">
              <label for="pattern">
                {isMobile ? 'Pattern' : 'Regular Expression Pattern'}
                <span class="required">*</span>
                {#if patternValid}
                  <span class="valid-indicator" transition:scale={{ duration: 200 }}>✓</span>
                {/if}
              </label>
              <div class="pattern-input-group">
                <input
                  id="pattern"
                  type="text"
                  bind:value={pattern}
                  placeholder={isMobile ? "e.g., Error: (.*)" : "e.g., GPU memory: (\d+)/(\d+) MB or Error: (.*)"}
                  class:valid={patternValid}
                  class:invalid={pattern && !patternValid}
                  oninput={() => testResult = null}
                  autocomplete="off"
                  autocorrect="off"
                  autocapitalize="off"
                />
                {#if !isMobile}
                <button 
                  class="help-btn"
                  title="Pattern help"
                  onclick={() => window.open('https://regex101.com', '_blank')}
                >
                  <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M11,18H13V16H11V18M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,6A4,4 0 0,0 8,10H10A2,2 0 0,1 12,8A2,2 0 0,1 14,10C14,12 11,11.75 11,15H13C13,12.75 16,12.5 16,10A4,4 0 0,0 12,6Z"/>
                  </svg>
                </button>
                {/if}
              </div>
              {#if pattern && !patternValid}
                <div class="error-text">Invalid regex</div>
              {/if}
            </div>
            
            <!-- Pattern Tester -->
            <div class="pattern-tester">
              <h4>Test Your Pattern</h4>
              <div class="test-input-group">
                <textarea
                  bind:value={testString}
                  placeholder="Paste sample output from your job to test the pattern..."
                  rows="3"
></textarea>
                <button 
                  class="test-btn"
                  onclick={testPattern}
                  disabled={!pattern || !testString}
                >
                  Test Pattern
                </button>
              </div>
              
              {#if testResult}
                <div class="test-result" class:success={testResult.success} transition:slide={{ duration: 300 }}>
                  {#if testResult.success}
                    <div class="result-header">
                      <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z"/>
                      </svg>
                      Pattern matched{testResult.totalMatches > 1 ? ` (${testResult.totalMatches} times)` : ''}!
                    </div>
                    <div class="match-details">
                      <div class="match-item">
                        <strong>Full Match:</strong>
                        <code>{testResult.fullMatch}</code>
                      </div>
                      {#if testResult.groups.length > 0}
                        <div class="match-item">
                          <strong>Capture Groups:</strong>
                          <div class="capture-results">
                            {#each testResult.groups as group, i}
                              <div class="capture-result">
                                <span class="capture-index">${i + 1}:</span>
                                <code>{group || '(empty)'}</code>
                              </div>
                            {/each}
                          </div>
                        </div>
                      {/if}
                      {#if testResult.totalMatches > 1}
                        <div class="match-item">
                          <strong>All Matches:</strong>
                          <div class="all-matches">
                            {#each testResult.allMatches.slice(0, 5) as match}
                              <code class="match-preview">{match}</code>
                            {/each}
                            {#if testResult.allMatches.length > 5}
                              <small>...and {testResult.allMatches.length - 5} more</small>
                            {/if}
                          </div>
                        </div>
                      {/if}
                    </div>
                  {:else}
                    <div class="result-header">
                      <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
                      </svg>
                      {testResult.message || 'No match found'}
                    </div>
                  {/if}
                </div>
              {/if}
            </div>
            
            <!-- Capture Groups -->
            <div class="capture-groups">
              <h4>Capture Groups (Optional)</h4>
              <p class="help-text">Name your capture groups to reference them in actions</p>
              
              <div class="capture-input-group">
                <input
                  type="text"
                  bind:value={captureInput}
                  placeholder="e.g., gpu_memory"
                  onkeydown={(e) => e.key === 'Enter' && addCapture()}
                />
                <button class="add-btn" onclick={addCapture}>
                  <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/>
                  </svg>
                  Add
                </button>
              </div>
              
              {#if captures.length > 0}
                <div class="capture-list">
                  {#each captures as capture, i}
                    <div class="capture-chip" transition:scale={{ duration: 200 }}>
                      <span class="capture-name">${i + 1}: {capture}</span>
                      <button class="remove-btn" onclick={() => removeCapture(i)} aria-label="Remove capture group">
                        <svg viewBox="0 0 24 24" fill="currentColor">
                          <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
                        </svg>
                      </button>
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          </div>
        </div>
        
      {:else if currentStep === 'actions'}
        <div class="step-content" in:fly={{ x: 20, duration: 300 }} out:fly={{ x: -20, duration: 300 }}>
          <div class="step-header">
            <h3>Configure Actions</h3>
            <p>Define what happens when your pattern matches</p>
          </div>
          
          <div class="actions-builder">
            <!-- Action Type Selector -->
            <div class="action-selector">
              {#each actionCategories as category}
                <div class="action-category">
                  <h5>{category.name}</h5>
                  <div class="action-types">
                    {#each category.actions as action}
                      <button
                        class="action-type-btn"
                        class:selected={actionType === action.value}
                        onclick={() => actionType = action.value}
                      >
                        <span class="action-icon">{action.icon}</span>
                        <div class="action-info">
                          <strong>{action.label}</strong>
                          <small>{action.description}</small>
                        </div>
                      </button>
                    {/each}
                  </div>
                </div>
              {/each}
            </div>
            
            <!-- Action Configuration -->
            <div class="action-config">
              <h5>Configure {getActionLabel(actionType)}</h5>
              
              {#if actionType === 'store_metric'}
                <div class="config-form">
                  <div class="form-group">
                    <label for="metric-name">Metric Name</label>
                    <input
                      id="metric-name"
                      type="text"
                      bind:value={actionConfig.metric_name}
                      placeholder="e.g., gpu_memory_usage"
                    />
                  </div>
                  <div class="form-group">
                    <label for="value-expr">Value Expression</label>
                    <input
                      id="value-expr"
                      type="text"
                      bind:value={actionConfig.value}
                      placeholder="e.g., $1 or float($gpu_memory)"
                    />
                    <small>Use $1, $2 for capture groups or named variables</small>
                  </div>
                </div>
                
              {:else if actionType === 'notify_email'}
                <div class="config-form">
                  <div class="form-group">
                    <label for="email-to">To</label>
                    <input
                      id="email-to"
                      type="email"
                      bind:value={actionConfig.to}
                      placeholder="email@example.com"
                    />
                  </div>
                  <div class="form-group">
                    <label for="email-subject">Subject</label>
                    <input
                      id="email-subject"
                      type="text"
                      bind:value={actionConfig.subject}
                      placeholder="Alert: Pattern matched in job #{jobId}"
                    />
                  </div>
                </div>
                
              {:else if actionType === 'notify_slack'}
                <div class="config-form">
                  <div class="form-group">
                    <label for="webhook-url">Webhook URL</label>
                    <input
                      id="webhook-url"
                      type="text"
                      bind:value={actionConfig.webhook_url}
                      placeholder="https://hooks.slack.com/services/..."
                    />
                  </div>
                  <div class="form-group">
                    <label for="slack-message">Message</label>
                    <textarea
                      id="slack-message"
                      bind:value={actionConfig.message}
                      placeholder="Pattern matched: $0"
                      rows="2"
></textarea>
                  </div>
                </div>
                
              {:else if actionType === 'run_command'}
                <div class="config-form">
                  <div class="form-group">
                    <label for="command">Command</label>
                    <textarea
                      id="command"
                      bind:value={actionConfig.command}
                      placeholder="cd /path/to/dir && echo 'Match found: $0' >> log.txt"
                      rows="3"
                      style="font-family: monospace;"
></textarea>
                    <small>Use $0 for full match, $1, $2 for capture groups. Commands like 'cd' are allowed.</small>
                  </div>
                </div>
                
              {:else if actionType === 'cancel_job'}
                <div class="config-form">
                  <div class="form-group">
                    <label for="cancel-reason">Reason (optional)</label>
                    <input
                      id="cancel-reason"
                      type="text"
                      bind:value={actionConfig.reason}
                      placeholder="e.g., Critical error detected"
                    />
                  </div>
                </div>
                
              {:else if actionType === 'resubmit'}
                <div class="config-form">
                  <div class="form-group">
                    <label for="resubmit-delay">Delay (seconds)</label>
                    <input
                      id="resubmit-delay"
                      type="number"
                      bind:value={actionConfig.delay}
                      placeholder="0"
                      min="0"
                    />
                  </div>
                </div>
                
              {:else if actionType === 'log_event' || actionType === 'pause_watcher'}
                <div class="config-form">
                  <p class="info-text">No additional configuration needed</p>
                </div>
              {/if}
              
              <div class="action-buttons">
                <button 
                  class="btn secondary"
                  onclick={() => {
                    actionConfig = {};
                    editingActionIndex = null;
                  }}
                >
                  Clear
                </button>
                <button 
                  class="btn primary"
                  onclick={addAction}
                >
                  {editingActionIndex !== null ? 'Update Action' : 'Add Action'}
                </button>
              </div>
            </div>
            
            <!-- Actions List -->
            {#if actions.length > 0}
              <div class="actions-list">
                <h5>Configured Actions</h5>
                <div class="action-items">
                  {#each actions as action, i}
                    {@const actionInfo = allActionTypes.find(a => a.value === action.type)}
                    <div class="action-item" transition:slide={{ duration: 300 }}>
                      <div class="action-icon">{actionInfo?.icon}</div>
                      <div class="action-details">
                        <strong>{actionInfo?.label}</strong>
                        {#if action.params && Object.keys(action.params).length > 0}
                          <small>{JSON.stringify(action.params)}</small>
                        {/if}
                      </div>
                      <div class="action-controls">
                        <button class="icon-btn" onclick={() => editAction(i)} title="Edit">
                          <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M3,17.25V21H6.75L17.81,9.94L14.06,6.19L3,17.25M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.13,5.12L18.88,8.87L20.71,7.04Z"/>
                          </svg>
                        </button>
                        <button class="icon-btn" onclick={() => removeAction(i)} title="Remove">
                          <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z"/>
                          </svg>
                        </button>
                      </div>
                    </div>
                  {/each}
                </div>
              </div>
            {:else}
              <div class="empty-actions">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/>
                </svg>
                <p>No actions configured yet</p>
                <small>Select an action type above to get started</small>
              </div>
            {/if}
          </div>
        </div>
        
      {:else if currentStep === 'review'}
        <div class="step-content" in:fly={{ x: 20, duration: 300 }} out:fly={{ x: -20, duration: 300 }}>
          <div class="step-header">
            <h3>Review Your Watcher</h3>
            <p>Check your configuration before creating the watcher</p>
          </div>
          
          <div class="review-content">
            <div class="review-section">
              <h4>Basic Information</h4>
              <div class="review-items">
                <div class="review-item">
                  <span class="review-label">Name:</span>
                  <span class="review-value">{watcherName || '(not set)'}</span>
                </div>
                <div class="review-item">
                  <span class="review-label">Job:</span>
                  <span class="review-value">#{jobId} on {hostname}</span>
                </div>
                <div class="review-item">
                  <span class="review-label">Check Interval:</span>
                  <span class="review-value">Every {interval} seconds</span>
                </div>
                
                {#if timerModeEnabled}
                  <div class="review-item">
                    <span class="review-label">Timer Mode:</span>
                    <span class="review-value">Enabled (every {timerInterval}s after match)</span>
                  </div>
                {/if}
              </div>
            </div>
            
            <div class="review-section">
              <h4>Pattern Configuration</h4>
              <div class="review-items">
                <div class="review-item">
                  <span class="review-label">Pattern:</span>
                  <code class="review-code">{pattern || '(not set)'}</code>
                </div>
                {#if captures.length > 0}
                  <div class="review-item">
                    <span class="review-label">Capture Groups:</span>
                    <div class="review-captures">
                      {#each captures as capture, i}
                        <span class="capture-badge">${i + 1}: {capture}</span>
                      {/each}
                    </div>
                  </div>
                {/if}
              </div>
            </div>
            
            <div class="review-section">
              <h4>Actions ({actions.length})</h4>
              <div class="review-actions">
                {#each actions as action}
                  {@const actionInfo = allActionTypes.find(a => a.value === action.type)}
                  <div class="review-action">
                    <span class="action-icon">{actionInfo?.icon}</span>
                    <div>
                      <strong>{actionInfo?.label}</strong>
                      {#if action.params && Object.keys(action.params).length > 0}
                        <small>{JSON.stringify(action.params)}</small>
                      {/if}
                    </div>
                  </div>
                {/each}
              </div>
            </div>
            
            <div class="review-summary">
              <div class="summary-icon">✨</div>
              <p>Your watcher is ready to be created!</p>
              <small>It will start monitoring immediately after creation</small>
            </div>
          </div>
        </div>
      {/if}
    </div>
    

  {#snippet footer()}
    <div  class="wizard-footer-content">
      <div class="footer-left">
        {#if currentStep !== 'template'}
          <button
            class="btn secondary"
            onclick={prevStep}
            disabled={isSubmitting}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M15.41,16.58L10.83,12L15.41,7.41L14,6L8,12L14,18L15.41,16.58Z"/>
            </svg>
            Previous
          </button>
        {/if}
      </div>

      <div class="footer-actions">
        <button
          class="btn secondary"
          onclick={handleClose}
          disabled={isSubmitting}
        >
          Cancel
        </button>

        {#if currentStep === 'review'}
          <button
            class="btn primary"
            onclick={handleSubmit}
            disabled={isSubmitting || !canProceed.review}
          >
            {#if isSubmitting}
              <span class="spinner"></span>
              Creating...
            {:else}
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z"/>
              </svg>
              Create Watcher
            {/if}
          </button>
        {:else}
          <button
            class="btn primary"
            onclick={nextStep}
            disabled={!canProceed[currentStep]}
          >
            Next
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"/>
            </svg>
          </button>
        {/if}
      </div>
    </div>
  {/snippet}
</Dialog>

<style>
  /* Custom Dialog Styles */
  :global(.attach-watchers-content) {
    padding: 0 !important;
  }

  :global(.attach-watchers-header) {
    border-bottom: none !important;
  }

  :global(.attach-watchers-footer) {
    border-top: 1px solid var(--border);
  }

  /* Header */
  .header-wrapper {
    width: 100%;
  }

  .header-wrapper h2 {
    margin: 0;
    font-size: 1.5rem;
    color: var(--foreground);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .header-subtitle {
    margin: 0.25rem 0 0 0;
    font-size: 0.875rem;
    color: var(--muted-foreground);
  }
  
  /* Progress Steps */
  .wizard-progress {
    padding: 1.5rem;
    background: var(--secondary);
    border-bottom: 1px solid var(--border);
  }
  
  /* Mobile Progress Bar */
  .mobile-progress {
    padding: 1rem;
    background: var(--secondary);
    border-bottom: 1px solid var(--border);
  }
  
  .mobile-progress-bar {
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
    margin-bottom: 0.5rem;
  }
  
  .mobile-progress-fill {
    height: 100%;
    background: var(--accent);
    transition: width 0.3s ease;
  }
  
  .mobile-step-label {
    text-align: center;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--muted-foreground);
  }
  
  .progress-track {
    display: flex;
    align-items: center;
    justify-content: space-between;
    max-width: 600px;
    margin: 0 auto;
  }
  
  .progress-step {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    position: relative;
    transition: all 0.3s;
  }
  
  .progress-step:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }
  
  .step-number {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: var(--background);
    border: 2px solid var(--muted);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    color: var(--muted-foreground);
    transition: all 0.3s;
    position: relative;
    z-index: 2;
  }
  
  .progress-step.active .step-number {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-foreground);
    transform: scale(1.1);
  }
  
  .progress-step.completed .step-number {
    background: var(--success);
    border-color: var(--success);
    color: var(--accent-foreground);
  }
  
  .step-number svg {
    width: 20px;
    height: 20px;
  }
  
  .step-label {
    font-size: 0.75rem;
    color: var(--muted-foreground);
    font-weight: 500;
  }
  
  .progress-step.active .step-label {
    color: var(--accent);
    font-weight: 600;
  }
  
  .progress-step.completed .step-label {
    color: var(--success);
  }
  
  .step-progress {
    width: 100%;
    height: 2px;
    background: var(--border);
    border-radius: 1px;
    overflow: hidden;
    margin-top: 0.25rem;
  }
  
  .progress-fill {
    height: 100%;
    background: var(--accent);
    transition: width 0.3s ease;
  }
  
  .progress-connector {
    position: absolute;
    top: 20px;
    left: 50%;
    width: 100%;
    height: 2px;
    background: var(--border);
    z-index: 1;
  }
  
  .progress-connector.filled {
    background: var(--success);
  }
  
  /* Error Banner */
  .error-banner {
    background: #fee2e2;
    color: #dc2626;
    padding: 0.75rem 1.5rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
  }
  
  .error-banner svg {
    width: 20px;
    height: 20px;
  }
  
  /* Dialog Body */
  .dialog-body {
    flex: 1;
    overflow-y: auto;
    padding: 2rem;
    min-height: 400px;
  }
  
  .dialog-body.mobile {
    padding: 1rem;
    min-height: unset;
  }
  
  .step-content {
    animation: fadeIn 0.3s ease;
  }
  
  .step-header {
    margin-bottom: 2rem;
  }
  
  .step-header h3 {
    margin: 0;
    font-size: 1.25rem;
    color: var(--foreground);
  }
  
  .step-header p {
    margin: 0.5rem 0 0 0;
    color: var(--muted-foreground);
    font-size: 0.875rem;
  }
  
  /* Template Selection */
  .template-categories {
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }
  
  .template-category {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  .category-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .category-icon {
    font-size: 1.25rem;
  }
  
  .category-header h4 {
    margin: 0;
    flex: 1;
    font-size: 1rem;
    color: #374151;
  }
  
  .category-count {
    background: var(--secondary);
    padding: 0.25rem 0.5rem;
    border-radius: 12px;
    font-size: 0.75rem;
    color: var(--muted-foreground);
  }
  
  .template-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 1rem;
  }
  
  .template-card {
    background: var(--background);
    border: 2px solid var(--border);
    border-radius: 12px;
    padding: 1rem;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    gap: 1rem;
    align-items: flex-start;
    text-align: left;
    position: relative;
  }
  
  .template-card:hover {
    border-color: var(--accent);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
    transform: translateY(-2px);
  }
  
  .template-card.selected {
    border-color: var(--accent);
    background: #f0f4ff;
  }
  
  .template-icon {
    font-size: 1.5rem;
    flex-shrink: 0;
  }
  
  .template-info h5 {
    margin: 0;
    font-size: 0.95rem;
    color: var(--foreground);
    font-weight: 600;
  }
  
  .template-info p {
    margin: 0.25rem 0 0 0;
    font-size: 0.8rem;
    color: var(--muted-foreground);
  }
  
  .selected-badge {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    width: 24px;
    height: 24px;
    background: var(--accent);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--accent-foreground);
  }
  
  .selected-badge svg {
    width: 16px;
    height: 16px;
  }
  
  /* Pattern Form */
  .pattern-form {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
  }
  
  /* Mobile Quick Templates */
  .mobile-quick-templates {
    margin-bottom: 1.5rem;
    padding: 1rem;
    background: var(--secondary);
    border-radius: 12px;
    border: 1px solid var(--border);
  }
  
  .quick-template-label {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--muted-foreground);
    margin-bottom: 0.75rem;
  }
  
  .quick-template-buttons {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.5rem;
  }
  
  .quick-template-btn {
    padding: 0.75rem;
    background: var(--background);
    border: 2px solid var(--border);
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--foreground);
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }
  
  .quick-template-btn:hover {
    background: var(--secondary);
    border-color: var(--accent);
    transform: translateY(-1px);
  }
  
  .quick-template-btn:active {
    transform: translateY(0);
  }
  
  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .form-row.mobile {
    flex-direction: column;
  }
  
  .form-row.mobile .form-group {
    width: 100%;
  }
  
  .form-group label {
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .required {
    color: #ef4444;
  }
  
  .valid-indicator {
    color: var(--success);
    margin-left: auto;
  }
  
  .form-group input,
  .form-group textarea {
    padding: 0.75rem;
    border: 2px solid var(--border);
    border-radius: 8px;
    font-size: 0.875rem;
    transition: all 0.2s;
    background: var(--background);
    color: var(--foreground);
  }

  .form-group input:focus,
  .form-group textarea:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 10%, transparent);
  }
  
  .form-group input.valid {
    border-color: var(--success);
  }
  
  .form-group input.invalid {
    border-color: #ef4444;
  }
  
  .form-group small {
    font-size: 0.75rem;
    color: var(--muted-foreground);
  }
  
  .error-text {
    font-size: 0.75rem;
    color: #ef4444;
  }
  
  .interval-input {
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  
  .interval-input input[type="range"] {
    flex: 1;
    padding: 0;
  }
  
  .interval-display {
    min-width: 50px;
    text-align: center;
    font-weight: 600;
    color: var(--accent);
  }
  
  /* Timer Mode Styling */
  .timer-mode-section {
    background: #f8fafc;
    border-radius: 8px;
    padding: 1rem;
    border: 1px solid #e2e8f0;
    margin: 1rem 0;
  }
  
  .timer-mode-toggle {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .toggle-label {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    cursor: pointer;
    font-weight: 500;
    color: #374151;
  }
  
  .toggle-checkbox {
    display: none;
  }
  
  .toggle-slider {
    position: relative;
    width: 44px;
    height: 24px;
    background: #cbd5e1;
    border-radius: 12px;
    transition: all 0.2s;
  }
  
  .toggle-slider::after {
    content: '';
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    background: var(--background);
    border-radius: 50%;
    transition: all 0.2s;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
  
  .toggle-checkbox:checked + .toggle-slider {
    background: var(--accent);
  }
  
  .toggle-checkbox:checked + .toggle-slider::after {
    transform: translateX(20px);
  }
  
  .timer-interval-group {
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid #e2e8f0;
  }
  
  .timer-interval-group label {
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
    margin-bottom: 0.5rem;
    display: block;
  }
  
  .pattern-input-group {
    display: flex;
    gap: 0.5rem;
  }
  
  .pattern-input-group input {
    flex: 1;
  }
  
  .help-btn {
    padding: 0.75rem;
    background: var(--secondary);
    border: 2px solid var(--border);
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .help-btn:hover {
    background: var(--border);
  }
  
  .help-btn svg {
    width: 20px;
    height: 20px;
    color: var(--muted-foreground);
  }
  
  /* Job Output Viewer */
  .output-viewer-section {
    margin-bottom: 1.5rem;
  }
  
  .output-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.75rem 1rem;
    background: linear-gradient(135deg, var(--accent) 0%, #764ba2 100%);
    color: var(--accent-foreground);
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .output-toggle:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  }
  
  .toggle-icon {
    width: 20px;
    height: 20px;
    transition: transform 0.3s;
  }
  
  .toggle-icon.rotated {
    transform: rotate(180deg);
  }
  
  .output-toggle .badge {
    margin-left: auto;
    background: rgba(255, 255, 255, 0.2);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
  }
  
  .output-viewer {
    margin-top: 1rem;
    background: var(--secondary);
    border: 2px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }
  
  .output-controls {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem 1rem;
    background: var(--background);
    border-bottom: 1px solid var(--border);
  }
  
  .output-type-selector {
    display: flex;
    gap: 0.25rem;
    background: var(--secondary);
    padding: 0.25rem;
    border-radius: 6px;
  }
  
  .type-btn {
    padding: 0.375rem 0.75rem;
    background: transparent;
    border: none;
    border-radius: 4px;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--muted-foreground);
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .type-btn:hover {
    color: #374151;
  }
  
  .type-btn.active {
    background: var(--background);
    color: var(--accent);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }
  
  .lines-control {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-left: auto;
  }

  .lines-control .lines-label {
    font-size: 0.8125rem;
    color: var(--muted-foreground);
  }
  
  .lines-control select {
    padding: 0.375rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 0.8125rem;
    background: var(--background);
  }
  
  .refresh-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem 0.75rem;
    background: var(--background);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 0.8125rem;
    font-weight: 500;
    color: #374151;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .refresh-btn:hover:not(:disabled) {
    background: var(--secondary);
  }
  
  .refresh-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .refresh-btn svg {
    width: 16px;
    height: 16px;
  }
  
  .refresh-btn svg.spin {
    animation: spin 1s linear infinite;
  }
  
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  
  .output-error {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 1rem;
    background: #fef2f2;
    color: #dc2626;
    font-size: 0.875rem;
  }
  
  .output-error svg {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }
  
  .output-content {
    position: relative;
    max-height: 300px;
    overflow: auto;
  }
  
  .output-content pre {
    margin: 0;
    padding: 1rem;
    font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
    font-size: 0.8125rem;
    line-height: 1.5;
    color: var(--foreground);
    white-space: pre-wrap;
    word-break: break-all;
  }
  
  .copy-to-test-btn {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.375rem 0.75rem;
    background: var(--background);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 500;
    color: #374151;
    cursor: pointer;
    transition: all 0.2s;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }
  
  .copy-to-test-btn:hover {
    background: var(--accent);
    color: var(--accent-foreground);
    border-color: var(--accent);
  }
  
  .copy-to-test-btn svg {
    width: 14px;
    height: 14px;
  }
  
  .output-placeholder {
    padding: 2rem;
    text-align: center;
    color: #9ca3af;
    font-size: 0.875rem;
  }
  
  /* Pattern Tester */
  .pattern-tester {
    background: var(--secondary);
    border-radius: 12px;
    padding: 1.5rem;
  }
  
  .pattern-tester h4 {
    margin: 0 0 1rem 0;
    font-size: 1rem;
    color: #374151;
  }
  
  .test-input-group {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .test-input-group textarea {
    padding: 0.75rem;
    border: 2px solid var(--border);
    border-radius: 8px;
    font-size: 0.875rem;
    font-family: monospace;
    resize: vertical;
  }
  
  .test-btn {
    padding: 0.75rem 1.5rem;
    background: var(--accent);
    color: var(--accent-foreground);
    border: none;
    border-radius: 8px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    align-self: flex-start;
  }
  
  .test-btn:hover:not(:disabled) {
    background: #5a67d8;
  }
  
  .test-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .test-result {
    margin-top: 1rem;
    padding: 1rem;
    border-radius: 8px;
    border: 2px solid;
  }
  
  .test-result.success {
    background: #d1fae5;
    border-color: var(--success);
    color: #065f46;
  }
  
  .test-result:not(.success) {
    background: #fee2e2;
    border-color: #ef4444;
    color: #991b1b;
  }
  
  .result-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 600;
    margin-bottom: 0.75rem;
  }
  
  .result-header svg {
    width: 20px;
    height: 20px;
  }
  
  .match-details {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .match-item strong {
    display: inline-block;
    min-width: 100px;
  }
  
  .match-item code {
    background: var(--background);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.875rem;
  }
  
  .capture-results {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  
  .all-matches {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    margin-top: 0.5rem;
  }
  
  .match-preview {
    background: rgba(99, 102, 241, 0.1);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8125rem;
    display: inline-block;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .capture-result {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--background);
    padding: 0.25rem 0.5rem;
    border-radius: 6px;
  }
  
  .capture-index {
    font-weight: 600;
    color: var(--accent);
  }
  
  /* Capture Groups */
  .capture-groups {
    background: var(--secondary);
    border-radius: 12px;
    padding: 1.5rem;
  }
  
  .capture-groups h4 {
    margin: 0 0 0.5rem 0;
    font-size: 1rem;
    color: #374151;
  }
  
  .help-text {
    margin: 0 0 1rem 0;
    font-size: 0.875rem;
    color: var(--muted-foreground);
  }
  
  .capture-input-group {
    display: flex;
    gap: 0.5rem;
  }
  
  .capture-input-group input {
    flex: 1;
    padding: 0.75rem;
    border: 2px solid var(--border);
    border-radius: 8px;
    font-size: 0.875rem;
  }
  
  .add-btn {
    padding: 0.75rem 1rem;
    background: var(--accent);
    color: var(--accent-foreground);
    border: none;
    border-radius: 8px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .add-btn:hover {
    background: #5a67d8;
  }
  
  .add-btn svg {
    width: 18px;
    height: 18px;
  }
  
  .capture-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 1rem;
  }
  
  .capture-chip {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--background);
    border: 2px solid var(--border);
    border-radius: 20px;
    padding: 0.5rem 0.75rem;
  }
  
  .capture-name {
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
  }
  
  .remove-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    color: var(--muted-foreground);
    transition: color 0.2s;
  }
  
  .remove-btn:hover {
    color: #ef4444;
  }
  
  .remove-btn svg {
    width: 16px;
    height: 16px;
  }
  
  /* Actions Builder */
  .actions-builder {
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }
  
  .action-selector {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .action-category h5 {
    margin: 0 0 0.75rem 0;
    font-size: 0.875rem;
    color: var(--muted-foreground);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  
  .action-types {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.75rem;
  }
  
  .action-type-btn {
    background: var(--background);
    border: 2px solid var(--border);
    border-radius: 8px;
    padding: 0.75rem;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    gap: 0.75rem;
    align-items: center;
    text-align: left;
  }
  
  .action-type-btn:hover {
    border-color: var(--accent);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  }
  
  .action-type-btn.selected {
    border-color: var(--accent);
    background: #f0f4ff;
  }
  
  .action-icon {
    font-size: 1.25rem;
    flex-shrink: 0;
  }
  
  .action-info strong {
    display: block;
    font-size: 0.875rem;
    color: var(--foreground);
    font-weight: 600;
  }
  
  .action-info small {
    display: block;
    font-size: 0.75rem;
    color: var(--muted-foreground);
    margin-top: 0.25rem;
  }
  
  /* Action Configuration */
  .action-config {
    background: var(--secondary);
    border-radius: 12px;
    padding: 1.5rem;
  }
  
  .action-config h5 {
    margin: 0 0 1rem 0;
    font-size: 1rem;
    color: #374151;
  }
  
  .config-form {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  .info-text {
    color: var(--muted-foreground);
    font-size: 0.875rem;
    text-align: center;
    padding: 2rem;
  }
  
  .action-buttons {
    display: flex;
    gap: 0.75rem;
    margin-top: 1rem;
  }
  
  /* Actions List */
  .actions-list {
    background: var(--background);
    border: 2px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
  }
  
  .actions-list h5 {
    margin: 0 0 1rem 0;
    font-size: 1rem;
    color: #374151;
  }
  
  .action-items {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .action-item {
    display: flex;
    align-items: center;
    gap: 1rem;
    background: var(--secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem;
  }
  
  .action-item .action-icon {
    font-size: 1.25rem;
    flex-shrink: 0;
  }
  
  .action-details {
    flex: 1;
  }
  
  .action-details strong {
    display: block;
    font-size: 0.875rem;
    color: var(--foreground);
    margin-bottom: 0.25rem;
  }
  
  .action-details small {
    font-size: 0.75rem;
    color: var(--muted-foreground);
    font-family: monospace;
  }
  
  .action-controls {
    display: flex;
    gap: 0.5rem;
  }
  
  .icon-btn {
    padding: 0.5rem;
    background: var(--background);
    border: 1px solid var(--border);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .icon-btn:hover {
    background: var(--secondary);
    border-color: var(--muted);
  }
  
  .icon-btn svg {
    width: 16px;
    height: 16px;
    color: var(--muted-foreground);
  }
  
  .empty-actions {
    text-align: center;
    padding: 3rem;
    color: #9ca3af;
  }
  
  .empty-actions svg {
    width: 48px;
    height: 48px;
    margin-bottom: 1rem;
    opacity: 0.5;
  }
  
  .empty-actions p {
    margin: 0;
    font-weight: 500;
    color: var(--muted-foreground);
  }
  
  .empty-actions small {
    display: block;
    margin-top: 0.5rem;
    font-size: 0.875rem;
  }
  
  /* Review Section */
  .review-content {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .review-section {
    background: var(--secondary);
    border-radius: 12px;
    padding: 1.5rem;
  }
  
  .review-section h4 {
    margin: 0 0 1rem 0;
    font-size: 1rem;
    color: #374151;
    font-weight: 600;
  }
  
  .review-items {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .review-item {
    display: flex;
    gap: 1rem;
    align-items: flex-start;
  }
  
  .review-label {
    min-width: 120px;
    font-size: 0.875rem;
    color: var(--muted-foreground);
  }
  
  .review-value {
    flex: 1;
    font-size: 0.875rem;
    color: var(--foreground);
    font-weight: 500;
  }
  
  .review-code {
    background: var(--background);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.8rem;
    word-break: break-all;
  }
  
  .review-captures {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  
  .capture-badge {
    background: var(--background);
    border: 1px solid var(--border);
    padding: 0.25rem 0.5rem;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--accent);
  }
  
  .review-actions {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .review-action {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: var(--background);
    padding: 0.75rem;
    border-radius: 8px;
  }
  
  .review-action .action-icon {
    font-size: 1.25rem;
  }
  
  .review-action strong {
    display: block;
    font-size: 0.875rem;
    color: var(--foreground);
  }
  
  .review-action small {
    display: block;
    font-size: 0.75rem;
    color: var(--muted-foreground);
    margin-top: 0.25rem;
    font-family: monospace;
  }
  
  .review-summary {
    background: linear-gradient(135deg, #f0f4ff 0%, #e0e7ff 100%);
    border: 2px solid var(--accent);
    border-radius: 12px;
    padding: 2rem;
    text-align: center;
  }
  
  .summary-icon {
    font-size: 3rem;
    margin-bottom: 1rem;
  }
  
  .review-summary p {
    margin: 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--foreground);
  }
  
  .review-summary small {
    display: block;
    margin-top: 0.5rem;
    font-size: 0.875rem;
    color: var(--muted-foreground);
  }
  
  /* Dialog Footer */
  .wizard-footer-content {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    background: var(--secondary);
  }

  .footer-left {
    display: flex;
    gap: 0.75rem;
  }

  .footer-actions {
    display: flex;
    gap: 0.75rem;
  }
  
  /* Buttons */
  .btn {
    padding: 0.75rem 1.25rem;
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .btn.primary {
    background: var(--accent);
    color: var(--accent-foreground);
  }
  
  .btn.primary:hover:not(:disabled) {
    background: #5a67d8;
    transform: translateY(-1px);
    box-shadow: 0 4px 6px rgba(102, 126, 234, 0.2);
  }
  
  .btn.secondary {
    background: var(--background);
    color: #374151;
    border: 2px solid var(--border);
  }
  
  .btn.secondary:hover:not(:disabled) {
    background: var(--secondary);
    border-color: var(--muted);
  }
  
  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .btn svg {
    width: 18px;
    height: 18px;
  }
  
  .spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid #ffffff30;
    border-top-color: var(--accent-foreground);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  /* Responsive */
  /* Mobile Styles */
  @media (max-width: 768px) {
    .wizard-progress {
      padding: 0.75rem 1rem;
      gap: 0.5rem;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }
    
    .progress-step {
      min-width: 80px;
      gap: 0.375rem;
    }

    .step-label {
      font-size: 0.625rem;
    }
    
    .dialog-body {
      padding: 1rem;
      flex: 1;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
    }
    
    .step-content {
      padding: 0;
    }
    
    .step-header {
      padding: 0 0 0.75rem 0;
    }

    .form-row {
      grid-template-columns: 1fr;
      gap: 1rem;
    }
    
    .form-group label {
      font-size: 0.8125rem;
    }
    
    .form-group input,
    .form-group textarea {
      padding: 0.75rem;
      font-size: 16px; /* Prevent zoom on iOS */
      min-height: 44px;
    }
    
    .form-group textarea {
      min-height: 100px;
    }
    
    .template-grid {
      grid-template-columns: 1fr;
      gap: 0.75rem;
    }
    
    .template-card {
      padding: 0.875rem;
    }
    
    .template-icon {
      width: 32px;
      height: 32px;
    }

    .output-viewer {
      margin-top: 1rem;
    }

    .output-content {
      padding: 0.75rem;
      font-size: 0.75rem;
      max-height: 250px;
    }
    
    .lines-control {
      gap: 0.375rem;
    }

    .lines-control .lines-label {
      font-size: 0.75rem;
    }
    
    .lines-control select {
      padding: 0.375rem 0.5rem;
      font-size: 0.75rem;
    }
    
    .timer-mode-toggle {
      padding: 0.875rem;
      margin-bottom: 1rem;
    }

    .toggle-label {
      gap: 0.375rem;
    }

    .action-item {
      padding: 0.875rem;
      gap: 0.75rem;
    }

    .action-types {
      grid-template-columns: 1fr;
      gap: 0.5rem;
    }
    
    .action-type-btn {
      padding: 0.75rem;
      font-size: 0.75rem;
      gap: 0.5rem;
    }

    .review-section {
      padding: 0.875rem;
      margin-bottom: 0.75rem;
    }

    .review-item {
      padding: 0.625rem;
      font-size: 0.75rem;
      gap: 0.375rem;
    }
    
    .review-label {
      font-size: 0.6875rem;
    }
    
    .review-value {
      font-size: 0.75rem;
    }

    .wizard-footer-content {
      padding: 1rem;
      gap: 0.75rem;
    }

    .footer-actions {
      gap: 0.5rem;
    }
    
    .btn {
      padding: 0.75rem 1rem;
      font-size: 0.875rem;
      min-height: 44px;
    }
    
    .btn svg {
      width: 16px;
      height: 16px;
    }
    
    /* Fix input zoom on iOS */
    input[type="text"],
    input[type="number"],
    textarea,
    select {
      font-size: 16px !important;
    }
    
    /* Optimize animations */
    * {
      animation-duration: 0.2s !important;
    }
    
    /* Hide scrollbars on mobile */
    .wizard-progress::-webkit-scrollbar,
    .dialog-body::-webkit-scrollbar {
      display: none;
    }
    
    .wizard-progress,
    .dialog-body {
      -ms-overflow-style: none;
      scrollbar-width: none;
    }
    
    .progress-step .step-label {
      display: none;
    }
  }
</style>