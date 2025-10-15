<script lang="ts">
  import { run } from 'svelte/legacy';

  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import { fly, slide } from 'svelte/transition';
  import CodeMirrorEditor from './CodeMirrorEditor.svelte';
  import type { HostInfo } from '../types/api';
  
  const dispatch = createEventDispatcher<{
    launch: void;
    scriptChanged: { content: string };
    configChanged: any;
  }>();

  
  interface Props {
    // Props
    script?: string;
    launching?: boolean;
    hosts?: HostInfo[];
    selectedHost?: string;
    loading?: boolean;
    validationDetails?: any;
  }

  let {
    script = '',
    launching = false,
    hosts = [],
    selectedHost = $bindable(''),
    loading = false,
    validationDetails = { isValid: false, missing: [], missingText: '' }
  }: Props = $props();

  // Layout state
  let sidebarOpen = $state(true);
  let sidebarWidth = 380; // pixels
  let editorView: 'script' | 'split' | 'preview' = $state('script');
  let activeSection: 'resources' | 'output' | 'advanced' = $state('resources');
  
  // Editor state
  let codeMirrorEditor: CodeMirrorEditor = $state();
  let vimMode = $state(false);
  let editableScript = $state(script);
  let hasUnsavedChanges = false;
  
  // Configuration state
  let jobConfig = $state({
    jobName: '',
    partition: '',
    timeLimit: 60, // minutes
    memory: 4, // GB
    cpus: 1,
    nodes: 1,
    gpusPerNode: 0,
    account: '',
    outputFile: '',
    errorFile: ''
  });
  
  // Parsed SLURM parameters from script
  let parsedParams: Record<string, any> = $state({});
  let scriptValidation = $state({ errors: [], warnings: [] });

  
  
  
  function parseSlurmScript(content: string): Record<string, any> {
    const params: Record<string, any> = {};
    const lines = content.split('\n');
    
    for (const line of lines) {
      if (line.trim().startsWith('#SBATCH')) {
        const match = line.match(/#SBATCH\s+(--?\w+(?:-\w+)*)(?:=(.+)|$)/);
        if (match) {
          const [, flag, value] = match;
          const cleanFlag = flag.replace(/^--?/, '');
          params[cleanFlag] = value?.trim() || true;
        }
      }
    }
    
    return params;
  }
  
  function validateSlurmScript(content: string) {
    const errors = [];
    const warnings = [];
    
    if (!content.startsWith('#!/bin/bash') && !content.startsWith('#!/bin/sh')) {
      warnings.push('Script should start with a shebang (#!/bin/bash)');
    }
    
    if (!content.includes('#SBATCH')) {
      warnings.push('No SLURM directives found. Add #SBATCH parameters.');
    }
    
    const lines = content.split('\n');
    const jobNameLine = lines.find(l => l.includes('--job-name'));
    if (!jobNameLine) {
      warnings.push('Consider adding a job name with --job-name');
    }
    
    return { errors, warnings };
  }
  
  function syncParsedToConfig() {
    if (parsedParams['job-name']) jobConfig.jobName = parsedParams['job-name'];
    if (parsedParams['partition']) jobConfig.partition = parsedParams['partition'];
    if (parsedParams['time']) {
      const timeStr = parsedParams['time'];
      jobConfig.timeLimit = parseTimeToMinutes(timeStr);
    }
    if (parsedParams['mem']) {
      jobConfig.memory = parseMemoryToGB(parsedParams['mem']);
    }
    if (parsedParams['cpus-per-task']) jobConfig.cpus = parseInt(parsedParams['cpus-per-task']) || 1;
    if (parsedParams['nodes']) jobConfig.nodes = parseInt(parsedParams['nodes']) || 1;
  }
  
  function parseTimeToMinutes(timeStr: string): number {
    if (!timeStr) return 60;
    const parts = timeStr.split(':');
    if (parts.length >= 2) {
      return parseInt(parts[0]) * 60 + parseInt(parts[1]);
    }
    return parseInt(timeStr) || 60;
  }
  
  function parseMemoryToGB(memStr: string): number {
    if (!memStr) return 4;
    const match = memStr.match(/(\d+)([GMK]?)/i);
    if (match) {
      const value = parseInt(match[1]);
      const unit = match[2]?.toUpperCase();
      if (unit === 'G') return value;
      if (unit === 'M') return Math.ceil(value / 1024);
      if (unit === 'K') return Math.ceil(value / 1024 / 1024);
    }
    return parseInt(memStr) || 4;
  }
  
  function handleScriptChange(event: CustomEvent<{ content: string }>) {
    editableScript = event.detail.content;
    hasUnsavedChanges = true;
    dispatch('scriptChanged', { content: editableScript });
  }
  
  function handleConfigChange() {
    dispatch('configChanged', jobConfig);
    updateScriptFromConfig();
  }
  
  function updateScriptFromConfig() {
    // Update script with current config values
    let updatedScript = editableScript;
    
    // Update or add SBATCH directives
    if (jobConfig.jobName) {
      updatedScript = updateSlurmDirective(updatedScript, 'job-name', jobConfig.jobName);
    }
    if (jobConfig.partition) {
      updatedScript = updateSlurmDirective(updatedScript, 'partition', jobConfig.partition);
    }
    if (jobConfig.timeLimit) {
      const hours = Math.floor(jobConfig.timeLimit / 60);
      const minutes = jobConfig.timeLimit % 60;
      updatedScript = updateSlurmDirective(updatedScript, 'time', `${hours}:${minutes.toString().padStart(2, '0')}:00`);
    }
    
    if (updatedScript !== editableScript) {
      editableScript = updatedScript;
      codeMirrorEditor?.setContent(updatedScript);
    }
  }
  
  function updateSlurmDirective(script: string, directive: string, value: string): string {
    const lines = script.split('\n');
    const directiveRegex = new RegExp(`^#SBATCH\\s+--${directive}=.*`);
    
    let found = false;
    for (let i = 0; i < lines.length; i++) {
      if (directiveRegex.test(lines[i])) {
        lines[i] = `#SBATCH --${directive}=${value}`;
        found = true;
        break;
      }
    }
    
    if (!found) {
      // Add after shebang or at beginning
      const shebangIndex = lines.findIndex(line => line.startsWith('#!'));
      const insertIndex = shebangIndex >= 0 ? shebangIndex + 1 : 0;
      lines.splice(insertIndex, 0, `#SBATCH --${directive}=${value}`);
    }
    
    return lines.join('\n');
  }
  
  function toggleSidebar() {
    sidebarOpen = !sidebarOpen;
  }
  
  function handleLaunch() {
    dispatch('launch');
  }
  
  function insertTemplate(template: string) {
    const templates = {
      basic: `#!/bin/bash
#SBATCH --job-name=my-job
#SBATCH --time=1:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1

echo "Job started on $(hostname)"
echo "Hello from SLURM!"
`,
      gpu: `#!/bin/bash
#SBATCH --job-name=gpu-job
#SBATCH --time=4:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --partition=gpu

module load cuda/11.8
nvidia-smi

echo "Running GPU job on $(hostname)"
`,
      ml: `#!/bin/bash
#SBATCH --job-name=ml-training
#SBATCH --time=8:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --partition=gpu

module load python/3.10
source ~/venv/bin/activate

python train.py --epochs 100 --batch-size 32
`
    };
    
    const templateContent = templates[template] || templates.basic;
    editableScript = templateContent;
    codeMirrorEditor?.setContent(templateContent);
    hasUnsavedChanges = true;
  }

  onMount(() => {
    // Initialize with default script if empty
    if (!editableScript.trim()) {
      insertTemplate('basic');
    }
    
    // Add keyboard shortcuts
    function handleGlobalKeydown(event: KeyboardEvent) {
      // Ctrl/Cmd + S to save/validate
      if ((event.ctrlKey || event.metaKey) && event.key === 's') {
        event.preventDefault();
        // Trigger validation update
        scriptValidation = validateSlurmScript(editableScript);
      }
      
      // Ctrl/Cmd + Enter to launch job
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        if (validationDetails.isValid && !launching) {
          handleLaunch();
        }
      }
      
      // Ctrl/Cmd + \ to toggle sidebar
      if ((event.ctrlKey || event.metaKey) && event.key === '\\') {
        event.preventDefault();
        toggleSidebar();
      }
      
      // Escape to close sidebar on mobile
      if (event.key === 'Escape' && window.innerWidth <= 768 && sidebarOpen) {
        event.preventDefault();
        toggleSidebar();
      }
    }
    
    document.addEventListener('keydown', handleGlobalKeydown);
    
    return () => {
      document.removeEventListener('keydown', handleGlobalKeydown);
    };
  });
  run(() => {
    editableScript = script;
  });
  // Parse SLURM parameters from script
  run(() => {
    if (editableScript) {
      parsedParams = parseSlurmScript(editableScript);
      scriptValidation = validateSlurmScript(editableScript);
    }
  });
  // Auto-sync parsed params to config
  run(() => {
    if (Object.keys(parsedParams).length > 0) {
      syncParsedToConfig();
    }
  });
</script>

<div class="integrated-editor">
  <!-- Toolbar -->
  <div class="toolbar">
    <div class="toolbar-left">
      <div class="host-selector">
        <select bind:value={selectedHost} class="host-select">
          <option value="">Select Host</option>
          {#each hosts as host}
            <option value={host.hostname}>{host.hostname}</option>
          {/each}
        </select>
        {#if selectedHost}
          <div class="host-info">
            Connected to {selectedHost}
          </div>
        {/if}
      </div>
    </div>
    
    <div class="toolbar-center">
      <div class="validation-status" class:valid={validationDetails.isValid} class:invalid={!validationDetails.isValid}>
        <svg class="status-icon" viewBox="0 0 24 24">
          {#if validationDetails.isValid}
            <path d="M9,16.17L4.83,12L3.41,13.41L9,19L21,7L19.59,5.59L9,16.17Z" />
          {:else}
            <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z" />
          {/if}
        </svg>
        <span class="status-text">{validationDetails.missingText}</span>
      </div>
    </div>
    
    <div class="toolbar-right">
      <div class="view-controls">
        <button 
          class="view-btn"
          class:active={editorView === 'script'}
          onclick={() => editorView = 'script'}
          title="Script Only"
        >
          <svg viewBox="0 0 24 24">
            <path d="M14.6,16.6L19.2,12L14.6,7.4L16,6L22,12L16,18L14.6,16.6M9.4,16.6L4.8,12L9.4,7.4L8,6L2,12L8,18L9.4,16.6Z"/>
          </svg>
        </button>
        <button 
          class="view-btn"
          class:active={editorView === 'split'}
          onclick={() => editorView = 'split'}
          title="Split View"
        >
          <svg viewBox="0 0 24 24">
            <path d="M19,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5A2,2 0 0,0 19,3M19,5V10H5V5H19M5,12H11V19H5V12M13,12H19V19H13V12Z"/>
          </svg>
        </button>
      </div>
      
      <div class="action-buttons">
        <div class="template-dropdown">
          <button class="dropdown-btn">
            <svg viewBox="0 0 24 24">
              <path d="M19,19H5V5H19M19,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5A2,2 0 0,0 19,3M13.96,12.29L11.21,15.83L9.25,13.47L6.5,17H17.5L13.96,12.29Z"/>
            </svg>
            Templates
          </button>
          <div class="dropdown-menu">
            <button onclick={() => insertTemplate('basic')}>Basic Job</button>
            <button onclick={() => insertTemplate('gpu')}>GPU Job</button>
            <button onclick={() => insertTemplate('ml')}>ML Training</button>
          </div>
        </div>
        
        <button class="icon-btn" onclick={toggleSidebar} title="Toggle Config Panel">
          <svg viewBox="0 0 24 24">
            <path d="M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z"/>
          </svg>
        </button>
      </div>
    </div>
  </div>

  <!-- Main Content -->
  <div class="main-content" style="--sidebar-width: {sidebarWidth}px">
    <!-- Editor Area -->
    <div class="editor-area" class:sidebar-open={sidebarOpen}>
      {#if editorView === 'script'}
        <div class="code-editor">
          <CodeMirrorEditor
            bind:this={codeMirrorEditor}
            value={editableScript}
            vimMode={vimMode}
            on:change={handleScriptChange}
            placeholder="Enter your SLURM script here..."
          />
        </div>
        
      {:else if editorView === 'split'}
        <div class="split-view">
          <div class="editor-pane">
            <CodeMirrorEditor
              bind:this={codeMirrorEditor}
              value={editableScript}
              vimMode={vimMode}
              on:change={handleScriptChange}
            />
          </div>
          <div class="preview-pane">
            <div class="preview-header">
              <h3>Generated Script</h3>
            </div>
            <div class="preview-content">
              <pre>{editableScript}</pre>
            </div>
          </div>
        </div>
      {/if}
      
      <!-- Script Status Overlay -->
      {#if scriptValidation.errors.length > 0 || scriptValidation.warnings.length > 0}
        <div class="script-status" transition:slide>
          {#each scriptValidation.errors as error}
            <div class="status-item error">
              <svg viewBox="0 0 24 24">
                <path d="M13,14H11V10H13M13,18H11V16H13M1,21H23L12,2L1,21Z"/>
              </svg>
              {error}
            </div>
          {/each}
          {#each scriptValidation.warnings as warning}
            <div class="status-item warning">
              <svg viewBox="0 0 24 24">
                <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z"/>
              </svg>
              {warning}
            </div>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Configuration Sidebar -->
    {#if sidebarOpen}
      <aside class="config-sidebar" transition:fly={{ x: sidebarWidth, duration: 300 }}>
        <div class="sidebar-header">
          <h2>Job Configuration</h2>
          <button class="close-btn" onclick={toggleSidebar}>
            <svg viewBox="0 0 24 24">
              <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
            </svg>
          </button>
        </div>
        
        <div class="sidebar-content">
          <!-- Section Tabs -->
          <div class="section-tabs">
            <button 
              class="section-tab"
              class:active={activeSection === 'resources'}
              onclick={() => activeSection = 'resources'}
            >
              Resources
            </button>
            <button 
              class="section-tab"
              class:active={activeSection === 'output'}
              onclick={() => activeSection = 'output'}
            >
              Output
            </button>
            <button 
              class="section-tab"
              class:active={activeSection === 'advanced'}
              onclick={() => activeSection = 'advanced'}
            >
              Advanced
            </button>
          </div>
          
          <!-- Configuration Sections -->
          <div class="config-sections">
            {#if activeSection === 'resources'}
              <div class="config-section">
                <div class="config-group">
                  <label>Job Name</label>
                  <input 
                    type="text" 
                    bind:value={jobConfig.jobName}
                    onchange={handleConfigChange}
                    placeholder="my-job"
                  />
                </div>
                
                <div class="config-group">
                  <label>Partition</label>
                  <select bind:value={jobConfig.partition} onchange={handleConfigChange}>
                    <option value="">Default</option>
                    <option value="cpu">CPU</option>
                    <option value="gpu">GPU</option>
                    <option value="bigmem">Big Memory</option>
                  </select>
                </div>
                
                <div class="config-row">
                  <div class="config-group">
                    <label>Time (hours)</label>
                    <input 
                      type="number" 
                      bind:value={jobConfig.timeLimit}
                      onchange={handleConfigChange}
                      min="1" 
                      max="168"
                    />
                  </div>
                  <div class="config-group">
                    <label>Memory (GB)</label>
                    <input 
                      type="number" 
                      bind:value={jobConfig.memory}
                      onchange={handleConfigChange}
                      min="1" 
                      max="512"
                    />
                  </div>
                </div>
                
                <div class="config-row">
                  <div class="config-group">
                    <label>CPUs</label>
                    <input 
                      type="number" 
                      bind:value={jobConfig.cpus}
                      onchange={handleConfigChange}
                      min="1" 
                      max="128"
                    />
                  </div>
                  <div class="config-group">
                    <label>GPUs</label>
                    <input 
                      type="number" 
                      bind:value={jobConfig.gpusPerNode}
                      onchange={handleConfigChange}
                      min="0" 
                      max="8"
                    />
                  </div>
                </div>
              </div>
              
            {:else if activeSection === 'output'}
              <div class="config-section">
                <div class="config-group">
                  <label>Output File</label>
                  <input 
                    type="text" 
                    bind:value={jobConfig.outputFile}
                    onchange={handleConfigChange}
                    placeholder="job-%j.out"
                  />
                </div>
                <div class="config-group">
                  <label>Error File</label>
                  <input 
                    type="text" 
                    bind:value={jobConfig.errorFile}
                    onchange={handleConfigChange}
                    placeholder="job-%j.err"
                  />
                </div>
              </div>
              
            {:else if activeSection === 'advanced'}
              <div class="config-section">
                <div class="config-group">
                  <label>Account</label>
                  <input 
                    type="text" 
                    bind:value={jobConfig.account}
                    onchange={handleConfigChange}
                    placeholder="project-account"
                  />
                </div>
                <div class="config-group">
                  <label>Nodes</label>
                  <input 
                    type="number" 
                    bind:value={jobConfig.nodes}
                    onchange={handleConfigChange}
                    min="1" 
                    max="100"
                  />
                </div>
              </div>
            {/if}
          </div>
          
          <!-- Quick Actions -->
          <div class="quick-actions">
            <button class="action-btn secondary" onclick={() => vimMode = !vimMode}>
              <svg viewBox="0 0 24 24">
                <path d="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z"/>
              </svg>
              {vimMode ? 'Disable' : 'Enable'} Vim
            </button>
            <button class="action-btn secondary" onclick={() => navigator.clipboard.writeText(editableScript)}>
              <svg viewBox="0 0 24 24">
                <path d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z"/>
              </svg>
              Copy Script
            </button>
          </div>
        </div>
        
        <!-- Launch Button -->
        <div class="sidebar-footer">
          <button 
            class="launch-btn" 
            class:ready={validationDetails.isValid}
            class:launching={launching}
            onclick={handleLaunch}
            disabled={!validationDetails.isValid || launching}
          >
            {#if launching}
              <div class="spinner"></div>
              Launching...
            {:else if validationDetails.isValid}
              <svg viewBox="0 0 24 24">
                <path d="M8,5.14V19.14L19,12.14L8,5.14Z"/>
              </svg>
              Launch Job
            {:else}
              <svg viewBox="0 0 24 24">
                <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z"/>
              </svg>
              {validationDetails.missingText}
            {/if}
          </button>
        </div>
      </aside>
    {/if}
  </div>
</div>

<style>
  .integrated-editor {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: #1e1e1e;
    color: #d4d4d4;
    font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }

  /* Toolbar */
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    background: #252526;
    border-bottom: 1px solid #3c3c3c;
    height: 48px;
    flex-shrink: 0;
  }

  .toolbar-left, .toolbar-center, .toolbar-right {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .host-selector {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .host-select {
    background: #3c3c3c;
    border: 1px solid #555;
    color: #d4d4d4;
    padding: 0.5rem 0.75rem;
    border-radius: 4px;
    font-size: 0.875rem;
  }

  .host-info {
    font-size: 0.8125rem;
    color: #858585;
  }

  .validation-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem 0.75rem;
    border-radius: 4px;
    font-size: 0.8125rem;
  }

  .validation-status.valid {
    background: rgba(16, 185, 129, 0.1);
    color: #10b981;
  }

  .validation-status.invalid {
    background: rgba(239, 68, 68, 0.1);
    color: #ef4444;
  }

  .status-icon {
    width: 16px;
    height: 16px;
    fill: currentColor;
  }

  .view-controls {
    display: flex;
    border: 1px solid #555;
    border-radius: 4px;
    overflow: hidden;
  }

  .view-btn {
    background: #3c3c3c;
    border: none;
    padding: 0.375rem 0.5rem;
    color: #d4d4d4;
    cursor: pointer;
    display: flex;
    align-items: center;
    border-right: 1px solid #555;
  }

  .view-btn:last-child {
    border-right: none;
  }

  .view-btn.active {
    background: #007acc;
    color: white;
  }

  .view-btn svg {
    width: 16px;
    height: 16px;
    fill: currentColor;
  }

  .action-buttons {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .template-dropdown {
    position: relative;
  }

  .dropdown-btn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    background: #0e639c;
    color: white;
    border: none;
    padding: 0.5rem 0.75rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8125rem;
  }

  .dropdown-btn svg {
    width: 14px;
    height: 14px;
    fill: currentColor;
  }

  .dropdown-menu {
    position: absolute;
    top: 100%;
    right: 0;
    background: #252526;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 0.25rem 0;
    display: none;
    min-width: 150px;
    z-index: 100;
  }

  .template-dropdown:hover .dropdown-menu {
    display: block;
  }

  .dropdown-menu button {
    width: 100%;
    background: none;
    border: none;
    color: #d4d4d4;
    padding: 0.5rem 0.75rem;
    text-align: left;
    cursor: pointer;
    font-size: 0.8125rem;
  }

  .dropdown-menu button:hover {
    background: #3c3c3c;
  }

  .icon-btn {
    background: #3c3c3c;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 0.5rem;
    color: #d4d4d4;
    cursor: pointer;
    display: flex;
    align-items: center;
  }

  .icon-btn svg {
    width: 16px;
    height: 16px;
    fill: currentColor;
  }

  /* Main Content */
  .main-content {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  .editor-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: #1e1e1e;
    transition: margin-right 0.3s ease;
    position: relative;
  }

  .editor-area.sidebar-open {
    margin-right: var(--sidebar-width);
  }

  .code-editor {
    flex: 1;
    overflow: hidden;
  }

  .split-view {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  .editor-pane {
    flex: 1;
    overflow: hidden;
  }

  .preview-pane {
    width: 400px;
    border-left: 1px solid #3c3c3c;
    background: #252526;
    display: flex;
    flex-direction: column;
  }

  .preview-header {
    padding: 0.75rem 1rem;
    background: #2d2d30;
    border-bottom: 1px solid #3c3c3c;
  }

  .preview-header h3 {
    margin: 0;
    font-size: 0.875rem;
    color: #d4d4d4;
  }

  .preview-content {
    flex: 1;
    overflow: auto;
    padding: 1rem;
  }

  .preview-content pre {
    margin: 0;
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
    font-size: 0.8125rem;
    line-height: 1.5;
    color: #d4d4d4;
    white-space: pre-wrap;
  }

  /* Script Status */
  .script-status {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    background: #252526;
    border-top: 1px solid #3c3c3c;
    padding: 0.5rem 1rem;
    max-height: 200px;
    overflow-y: auto;
  }

  .status-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem 0;
    font-size: 0.8125rem;
  }

  .status-item.error {
    color: #f48771;
  }

  .status-item.warning {
    color: #ffcc02;
  }

  .status-item svg {
    width: 16px;
    height: 16px;
    fill: currentColor;
    flex-shrink: 0;
  }

  /* Configuration Sidebar */
  .config-sidebar {
    position: fixed;
    top: 48px;
    right: 0;
    width: var(--sidebar-width);
    height: calc(100vh - 48px);
    background: #252526;
    border-left: 1px solid #3c3c3c;
    display: flex;
    flex-direction: column;
    z-index: 50;
  }

  .sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    background: #2d2d30;
    border-bottom: 1px solid #3c3c3c;
  }

  .sidebar-header h2 {
    margin: 0;
    font-size: 0.9375rem;
    font-weight: 600;
    color: #d4d4d4;
  }

  .close-btn {
    background: none;
    border: none;
    color: #858585;
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 4px;
  }

  .close-btn:hover {
    background: #3c3c3c;
    color: #d4d4d4;
  }

  .close-btn svg {
    width: 16px;
    height: 16px;
    fill: currentColor;
  }

  .sidebar-content {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
  }

  .section-tabs {
    display: flex;
    margin-bottom: 1rem;
    border-bottom: 1px solid #3c3c3c;
  }

  .section-tab {
    background: none;
    border: none;
    color: #858585;
    padding: 0.5rem 0.75rem;
    cursor: pointer;
    font-size: 0.8125rem;
    border-bottom: 2px solid transparent;
  }

  .section-tab.active {
    color: #007acc;
    border-bottom-color: #007acc;
  }

  .config-section {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .config-group {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .config-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
  }

  .config-group label {
    font-size: 0.8125rem;
    color: #d4d4d4;
    font-weight: 500;
  }

  .config-group input,
  .config-group select {
    background: #3c3c3c;
    border: 1px solid #555;
    color: #d4d4d4;
    padding: 0.5rem 0.75rem;
    border-radius: 4px;
    font-size: 0.8125rem;
  }

  .config-group input:focus,
  .config-group select:focus {
    outline: none;
    border-color: #007acc;
  }

  .quick-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid #3c3c3c;
  }

  .action-btn {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.375rem;
    background: #3c3c3c;
    border: 1px solid #555;
    color: #d4d4d4;
    padding: 0.5rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.75rem;
  }

  .action-btn svg {
    width: 14px;
    height: 14px;
    fill: currentColor;
  }

  .action-btn.secondary:hover {
    background: #484848;
  }

  .sidebar-footer {
    padding: 1rem;
    border-top: 1px solid #3c3c3c;
  }

  .launch-btn {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    background: #555;
    border: none;
    color: #858585;
    padding: 0.75rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
    transition: all 0.2s;
  }

  .launch-btn:disabled {
    cursor: not-allowed;
  }

  .launch-btn.ready:not(:disabled) {
    background: #0e639c;
    color: white;
  }

  .launch-btn.ready:hover:not(:disabled) {
    background: #1177bb;
  }

  .launch-btn.launching {
    background: #f0ad4e;
    color: white;
  }

  .launch-btn svg {
    width: 18px;
    height: 18px;
    fill: currentColor;
  }

  .spinner {
    width: 18px;
    height: 18px;
    border: 2px solid currentColor;
    border-top: 2px solid transparent;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Responsive */
  @media (max-width: 768px) {
    .config-sidebar {
      width: 100%;
      --sidebar-width: 100%;
    }
    
    .editor-area.sidebar-open {
      display: none;
    }
    
    .toolbar-center {
      display: none;
    }
    
    .config-row {
      grid-template-columns: 1fr;
    }
  }
</style>