<script lang="ts">
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import { fly, slide, fade, scale } from 'svelte/transition';
  import { quintOut, backOut } from 'svelte/easing';
  import CodeMirrorEditor from './CodeMirrorEditor.svelte';
  import JobConfigForm from './JobConfigForm.svelte';
  import FileBrowser from './FileBrowser.svelte';
  import SyncSettings from './SyncSettings.svelte';
  import type { HostInfo } from '../types/api';
  
  const dispatch = createEventDispatcher<{
    launch: void;
    scriptChanged: { content: string };
    configChanged: any;
    pathSelected: any;
    syncSettingsChanged: any;
    openHistory: void;
  }>();

  // Props
  export let script = '';
  export let launching = false;
  export let hosts: HostInfo[] = [];
  export let selectedHost = '';
  export let loading = false;
  export let validationDetails: any = { isValid: false, missing: [], missingText: '' };
  export let config: any = {};
  export let jobParameters: any = {};

  // Layout state
  let sidebarOpen = true;
  let editorView: 'code' | 'visual' | 'split' = 'code';
  let sidebarSection: 'presets' | 'configuration' | 'directory' | 'sync' | 'templates' = 'configuration';
  
  // Editor state
  let codeMirrorEditor: CodeMirrorEditor;
  let vimMode = false;
  let editableScript = script;
  let hasUnsavedChanges = false;
  let searchQuery = '';
  let showAdvanced = false;
  
  // Quick presets
  const quickPresets = [
    { name: 'Quick Test', time: '00:10:00', mem: '2GB', cpus: 1, icon: '⚡' },
    { name: 'Standard', time: '01:00:00', mem: '4GB', cpus: 2, icon: '📊' },
    { name: 'Long Running', time: '24:00:00', mem: '8GB', cpus: 4, icon: '⏰' },
    { name: 'GPU Compute', time: '04:00:00', mem: '16GB', cpus: 4, gpus: 1, icon: '🎮' },
    { name: 'Big Memory', time: '12:00:00', mem: '64GB', cpus: 8, icon: '💾' },
    { name: 'Distributed', time: '08:00:00', mem: '32GB', cpus: 16, nodes: 4, icon: '🌐' }
  ];
  
  // Templates with categories
  const templateCategories = [
    {
      name: 'Getting Started',
      icon: '🚀',
      templates: [
        {
          name: 'Hello World',
          description: 'Simple test job',
          script: `#!/bin/bash
#SBATCH --job-name=hello-world
#SBATCH --time=00:05:00
#SBATCH --mem=1GB
#SBATCH --cpus-per-task=1

echo "Hello from $(hostname)"
echo "Job ID: $SLURM_JOB_ID"
date`
        },
        {
          name: 'Python Script',
          description: 'Run a Python script',
          script: `#!/bin/bash
#SBATCH --job-name=python-job
#SBATCH --time=01:00:00
#SBATCH --mem=4GB
#SBATCH --cpus-per-task=2

module load python/3.10
python --version
python my_script.py`
        }
      ]
    },
    {
      name: 'Machine Learning',
      icon: '🤖',
      templates: [
        {
          name: 'PyTorch Training',
          description: 'GPU training with PyTorch',
          script: `#!/bin/bash
#SBATCH --job-name=pytorch-train
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --time=04:00:00
#SBATCH --mem=32GB
#SBATCH --cpus-per-task=8

module load cuda/11.8 python/3.10
source ~/venv/bin/activate

python train.py \\
  --epochs 100 \\
  --batch-size 64 \\
  --learning-rate 0.001`
        }
      ]
    }
  ];
  
  // Navigation items
  const navItems = [
    { id: 'presets', icon: '⚡', label: 'Quick Presets' },
    { id: 'configuration', icon: '⚙️', label: 'Configuration' },
    { id: 'directory', icon: '📁', label: 'Directory' },
    { id: 'sync', icon: '🔄', label: 'Sync Settings' },
    { id: 'templates', icon: '📋', label: 'Templates' }
  ];
  
  // Reactive statements
  $: editableScript = script;
  $: canLaunch = validationDetails.isValid && !launching && selectedHost;
  $: filteredTemplates = templateCategories.map(cat => ({
    ...cat,
    templates: cat.templates.filter(t => 
      searchQuery === '' || 
      t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.description.toLowerCase().includes(searchQuery.toLowerCase())
    )
  })).filter(cat => cat.templates.length > 0);
  
  function handleScriptChange(event: CustomEvent<{ content: string }>) {
    editableScript = event.detail.content;
    hasUnsavedChanges = true;
    dispatch('scriptChanged', { content: editableScript });
  }
  
  function applyPreset(preset: typeof quickPresets[0]) {
    // Update config based on preset
    dispatch('configChanged', preset);
  }
  
  function applyTemplate(template: typeof templateCategories[0]['templates'][0]) {
    editableScript = template.script;
    codeMirrorEditor?.setContent(template.script);
    hasUnsavedChanges = true;
    dispatch('scriptChanged', { content: template.script });
  }
  
  function toggleSidebar() {
    sidebarOpen = !sidebarOpen;
  }
  
  function handleLaunch() {
    if (canLaunch) {
      dispatch('launch');
    }
  }
  
  function handleConfigChange(event: CustomEvent) {
    dispatch('configChanged', event.detail);
  }
  
  function handlePathSelected(event: CustomEvent) {
    dispatch('pathSelected', event.detail);
  }
  
  function handleSyncSettingsChange(event: CustomEvent) {
    dispatch('syncSettingsChanged', event.detail);
  }
  
  onMount(() => {
    // Initialize with a template if empty
    if (!editableScript.trim()) {
      const defaultTemplate = templateCategories[0].templates[0];
      applyTemplate(defaultTemplate);
    }
    
    // Keyboard shortcuts
    function handleKeydown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        if (canLaunch) handleLaunch();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === '\\') {
        e.preventDefault();
        toggleSidebar();
      }
    }
    
    document.addEventListener('keydown', handleKeydown);
    return () => document.removeEventListener('keydown', handleKeydown);
  });
</script>

<div class="modern-editor">
  <!-- Top Bar -->
  <header class="top-bar">
    <div class="bar-section">
      <button class="logo-btn">
        <span class="logo-icon">⚡</span>
        <span class="logo-text">Job Editor</span>
      </button>
      
      <div class="host-selector">
        <select 
          bind:value={selectedHost} 
          class="modern-select"
          class:has-value={selectedHost}
        >
          <option value="">Select cluster...</option>
          {#each hosts as host}
            <option value={host.hostname}>{host.hostname}</option>
          {/each}
        </select>
        {#if selectedHost}
          <div class="host-status" transition:scale={{ duration: 200, easing: backOut }}>
            <span class="status-dot"></span>
            Connected
          </div>
        {/if}
      </div>
    </div>
    
    <div class="bar-section center">
      <div class="view-switcher">
        <button 
          class="view-btn"
          class:active={editorView === 'code'}
          on:click={() => editorView = 'code'}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/>
          </svg>
          Code
        </button>
        <button 
          class="view-btn"
          class:active={editorView === 'visual'}
          on:click={() => editorView = 'visual'}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
          </svg>
          Visual
        </button>
        <button 
          class="view-btn"
          class:active={editorView === 'split'}
          on:click={() => editorView = 'split'}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M18 6v12h-3V6h3m-3-2h3c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2h-3c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2zm-8 2v12H4V6h3m0-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h3c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2z"/>
          </svg>
          Split
        </button>
      </div>
    </div>
    
    <div class="bar-section right">
      {#if validationDetails.isValid}
        <div class="validation-badge valid" transition:scale={{ duration: 200 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/>
          </svg>
          Ready
        </div>
      {:else}
        <div class="validation-badge invalid" transition:scale={{ duration: 200 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
          </svg>
          {validationDetails.missingText || 'Invalid'}
        </div>
      {/if}
      
      <button 
        class="icon-btn"
        on:click={toggleSidebar}
        title="Toggle Settings (⌘\)"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z"/>
        </svg>
      </button>
      
      <button 
        class="icon-btn"
        on:click={() => dispatch('openHistory')}
        title="Script History"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z"/>
        </svg>
      </button>
    </div>
  </header>
  
  <!-- Main Content Area -->
  <div class="content-area">
    <!-- Editor Panel -->
    <div class="editor-panel" class:collapsed={!sidebarOpen}>
      {#if editorView === 'code' || editorView === 'split'}
        <div class="code-section">
          <CodeMirrorEditor
            bind:this={codeMirrorEditor}
            value={editableScript}
            vimMode={vimMode}
            on:change={handleScriptChange}
            placeholder="Start typing your SLURM script..."
          />
        </div>
      {/if}
      
      {#if editorView === 'visual' || editorView === 'split'}
        <div class="visual-section">
          <div class="visual-editor">
            <h3>Visual Job Builder</h3>
            <p>Drag and drop components to build your job script visually.</p>
          </div>
        </div>
      {/if}
      
      <!-- Floating Action Button -->
      <button 
        class="fab-launch"
        class:ready={canLaunch}
        on:click={handleLaunch}
        disabled={!canLaunch}
      >
        {#if launching}
          <div class="spinner"></div>
        {:else}
          <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z"/>
          </svg>
        {/if}
      </button>
    </div>
    
    <!-- Multi-Level Sidebar -->
    {#if sidebarOpen}
      <aside class="config-panel" transition:fly={{ x: 400, duration: 300, easing: quintOut }}>
        <div class="panel-header">
          <button class="close-panel" on:click={toggleSidebar}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
            </svg>
          </button>
        </div>
        
        <!-- Compact Icon Navigation Bar -->
        <div class="icon-nav">
          {#each navItems as item}
            <button 
              class="icon-nav-btn"
              class:active={sidebarSection === item.id}
              on:click={() => sidebarSection = item.id}
              title={item.label}
            >
              <span class="nav-icon">{item.icon}</span>
            </button>
          {/each}
        </div>
        
        <!-- Dynamic Content Area -->
        <div class="sidebar-content">
          {#if sidebarSection === 'presets'}
            <div class="section-content" transition:fade={{ duration: 200 }}>
              <div class="preset-grid">
                {#each quickPresets as preset}
                  <button 
                    class="preset-tile"
                    on:click={() => applyPreset(preset)}
                    transition:scale={{ duration: 200, delay: quickPresets.indexOf(preset) * 30 }}
                  >
                    <div class="preset-emoji">{preset.icon}</div>
                    <div class="preset-info">
                      <div class="preset-title">{preset.name}</div>
                      <div class="preset-details">
                        {preset.time} • {preset.mem} • {preset.cpus} CPU{preset.cpus > 1 ? 's' : ''}
                      </div>
                    </div>
                  </button>
                {/each}
              </div>
            </div>
            
          {:else if sidebarSection === 'configuration'}
            <div class="section-content" transition:fade={{ duration: 200 }}>
              <div class="modern-form">
                <!-- Job Name -->
                <div class="input-field">
                  <input 
                    id="job-name"
                    type="text" 
                    class="minimal-input"
                    value={config.jobName}
                    on:input={(e) => handleConfigChange({ detail: { jobName: e.target.value }})}
                    placeholder=" "
                  />
                  <label for="job-name" class="floating-label">Job Name</label>
                </div>
                
                <!-- Resources -->
                <div class="resource-grid">
                  <div class="input-field">
                    <select 
                      id="partition"
                      class="minimal-select"
                      value={config.partition}
                      on:change={(e) => handleConfigChange({ detail: { partition: e.target.value }})}
                    >
                      <option value="">Default</option>
                      <option value="cpu">CPU</option>
                      <option value="gpu">GPU</option>
                      <option value="bigmem">Big Memory</option>
                    </select>
                    <label for="partition" class="floating-label">Partition</label>
                  </div>
                  
                  <div class="input-field">
                    <input 
                      id="time-limit"
                      type="number" 
                      class="minimal-input"
                      value={config.timeLimit}
                      on:input={(e) => handleConfigChange({ detail: { timeLimit: parseInt(e.target.value) }})}
                      min="1"
                      max="10080"
                      placeholder=" "
                    />
                    <label for="time-limit" class="floating-label">Time (minutes)</label>
                  </div>
                  
                  <div class="input-field">
                    <input 
                      id="cpus"
                      type="number" 
                      class="minimal-input"
                      value={config.cpus}
                      on:input={(e) => handleConfigChange({ detail: { cpus: parseInt(e.target.value) }})}
                      min="1"
                      max="128"
                      placeholder=" "
                    />
                    <label for="cpus" class="floating-label">CPUs</label>
                  </div>
                  
                  <div class="input-field">
                    <input 
                      id="memory"
                      type="number" 
                      class="minimal-input"
                      value={config.memory}
                      on:input={(e) => handleConfigChange({ detail: { memory: parseInt(e.target.value) }})}
                      min="1"
                      max="512"
                      placeholder=" "
                    />
                    <label for="memory" class="floating-label">Memory (GB)</label>
                  </div>
                  
                  <div class="input-field">
                    <input 
                      id="nodes"
                      type="number" 
                      class="minimal-input"
                      value={config.nodes}
                      on:input={(e) => handleConfigChange({ detail: { nodes: parseInt(e.target.value) }})}
                      min="1"
                      max="100"
                      placeholder=" "
                    />
                    <label for="nodes" class="floating-label">Nodes</label>
                  </div>
                  
                  <div class="input-field">
                    <input 
                      id="gpus"
                      type="number" 
                      class="minimal-input"
                      value={config.gpusPerNode}
                      on:input={(e) => handleConfigChange({ detail: { gpusPerNode: parseInt(e.target.value) }})}
                      min="0"
                      max="8"
                      placeholder=" "
                    />
                    <label for="gpus" class="floating-label">GPUs</label>
                  </div>
                </div>
                
                <!-- Advanced Options -->
                <div class="divider"></div>
                
                <button 
                  class="advanced-toggle"
                  on:click={() => showAdvanced = !showAdvanced}
                >
                  <span class="toggle-text">Advanced Options</span>
                  <svg 
                    class="toggle-icon" 
                    class:rotated={showAdvanced}
                    width="16" 
                    height="16" 
                    viewBox="0 0 24 24" 
                    fill="currentColor"
                  >
                    <path d="M7 10l5 5 5-5z"/>
                  </svg>
                </button>
                
                {#if showAdvanced}
                  <div class="advanced-section" transition:slide={{ duration: 200 }}>
                    <div class="input-field">
                      <input 
                        id="account"
                        type="text" 
                        class="minimal-input"
                        value={config.account}
                        on:input={(e) => handleConfigChange({ detail: { account: e.target.value }})}
                        placeholder=" "
                      />
                      <label for="account" class="floating-label">Account</label>
                    </div>
                    
                    <div class="input-field">
                      <input 
                        id="output-file"
                        type="text" 
                        class="minimal-input"
                        value={config.outputFile}
                        on:input={(e) => handleConfigChange({ detail: { outputFile: e.target.value }})}
                        placeholder=" "
                      />
                      <label for="output-file" class="floating-label">Output File</label>
                    </div>
                    
                    <div class="input-field">
                      <input 
                        id="error-file"
                        type="text" 
                        class="minimal-input"
                        value={config.errorFile}
                        on:input={(e) => handleConfigChange({ detail: { errorFile: e.target.value }})}
                        placeholder=" "
                      />
                      <label for="error-file" class="floating-label">Error File</label>
                    </div>
                  </div>
                {/if}
              </div>
            </div>
            
          {:else if sidebarSection === 'directory'}
            <div class="section-content" transition:fade={{ duration: 200 }}>
              <!-- Current Path -->
              <div class="path-display">
                <div class="path-label">Current Directory</div>
                <div class="path-value">{config.sourceDir || '/home/user'}</div>
              </div>
              
              <!-- File Browser -->
              <div class="file-browser-wrapper">
                <FileBrowser
                  sourceDir={config.sourceDir}
                  initialPath="/home"
                  on:pathSelected={handlePathSelected}
                  on:change={(e) => dispatch('pathSelected', e.detail)}
                />
              </div>
            </div>
            
          {:else if sidebarSection === 'sync'}
            <div class="section-content" transition:fade={{ duration: 200 }}>
              <div class="sync-wrapper">
                <SyncSettings
                  excludePatterns={config.excludePatterns}
                  includePatterns={config.includePatterns}
                  noGitignore={config.noGitignore}
                  on:settingsChanged={handleSyncSettingsChange}
                />
              </div>
            </div>
            
          {:else if sidebarSection === 'templates'}
            <div class="section-content" transition:fade={{ duration: 200 }}>
              <!-- Search Bar -->
              <div class="input-field">
                <input 
                  type="text" 
                  bind:value={searchQuery}
                  class="minimal-input"
                  placeholder=" "
                  id="template-search"
                />
                <label for="template-search" class="floating-label">Search templates</label>
              </div>
              
              <div class="template-list">
                {#each filteredTemplates as category}
                  <div class="template-category">
                    <div class="category-header">
                      <span>{category.icon}</span>
                      <span class="category-title">{category.name}</span>
                    </div>
                    {#each category.templates as template}
                      <button 
                        class="template-item"
                        on:click={() => applyTemplate(template)}
                      >
                        <div class="template-main">{template.name}</div>
                        <div class="template-sub">{template.description}</div>
                      </button>
                    {/each}
                  </div>
                {/each}
              </div>
            </div>
          {/if}
        </div>
        
        <!-- Bottom Actions -->
        <div class="panel-footer">
          <button class="btn-secondary" on:click={() => vimMode = !vimMode}>
            {vimMode ? 'Disable' : 'Enable'} Vim
          </button>
          <button 
            class="btn-primary"
            class:launching
            on:click={handleLaunch}
            disabled={!canLaunch}
          >
            {#if launching}
              <div class="spinner"></div>
              Launching...
            {:else}
              Launch Job
            {/if}
          </button>
        </div>
      </aside>
    {/if}
  </div>
</div>

<style>
  .modern-editor {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    overflow: hidden;
  }
  
  .modern-editor::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: 
      radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.3) 0%, transparent 70%),
      radial-gradient(circle at 80% 20%, rgba(255, 119, 198, 0.3) 0%, transparent 70%),
      radial-gradient(circle at 40% 40%, rgba(120, 219, 255, 0.2) 0%, transparent 70%);
    pointer-events: none;
    z-index: 0;
  }
  
  /* Top Bar */
  .top-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1.5rem;
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid rgba(255, 255, 255, 0.2);
    box-shadow: 0 2px 20px rgba(0, 0, 0, 0.1);
    z-index: 10;
    position: relative;
    flex-shrink: 0;
    height: 64px;
  }
  
  .bar-section {
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  
  .bar-section.center {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
  }
  
  .bar-section.right {
    margin-left: auto;
  }
  
  .logo-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }
  
  .logo-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
  }
  
  .logo-icon {
    font-size: 1.2rem;
  }
  
  .host-selector {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  
  .modern-select {
    appearance: none;
    background: white;
    border: 2px solid rgba(102, 126, 234, 0.2);
    padding: 0.5rem 2.5rem 0.5rem 1rem;
    border-radius: 10px;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.3s;
    background-image: url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1.5L6 6.5L11 1.5' stroke='%23667eea' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 0.75rem center;
    background-size: 12px;
  }
  
  .modern-select:hover {
    border-color: rgba(102, 126, 234, 0.4);
  }
  
  .modern-select:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }
  
  .modern-select.has-value {
    color: #667eea;
    font-weight: 500;
  }
  
  .host-status {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.375rem 0.75rem;
    background: rgba(16, 185, 129, 0.1);
    color: #10b981;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 500;
  }
  
  .status-dot {
    width: 6px;
    height: 6px;
    background: #10b981;
    border-radius: 50%;
    animation: pulse 2s infinite;
  }
  
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  
  /* View Switcher */
  .view-switcher {
    display: flex;
    background: rgba(102, 126, 234, 0.1);
    border-radius: 12px;
    padding: 0.25rem;
  }
  
  .view-btn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 1rem;
    background: transparent;
    border: none;
    color: #64748b;
    font-size: 0.875rem;
    font-weight: 500;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .view-btn:hover {
    color: #667eea;
  }
  
  .view-btn.active {
    background: white;
    color: #667eea;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }
  
  /* Validation Badge */
  .validation-badge {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 0.875rem;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
  }
  
  .validation-badge.valid {
    background: rgba(16, 185, 129, 0.1);
    color: #10b981;
  }
  
  .validation-badge.invalid {
    background: rgba(239, 68, 68, 0.1);
    color: #ef4444;
  }
  
  .icon-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    background: white;
    border: 2px solid rgba(102, 126, 234, 0.2);
    border-radius: 10px;
    color: #667eea;
    cursor: pointer;
    transition: all 0.3s;
  }
  
  .icon-btn:hover {
    background: #667eea;
    border-color: #667eea;
    color: white;
    transform: rotate(90deg);
  }
  
  /* Content Area */
  .content-area {
    display: flex;
    flex: 1;
    position: relative;
    z-index: 1;
    min-height: 0; /* Important for Firefox */
    overflow: hidden;
  }
  
  .editor-panel {
    flex: 1;
    display: flex;
    transition: margin-right 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    background: rgba(255, 255, 255, 0.9);
    backdrop-filter: blur(20px);
    margin: 0.5rem;
    border-radius: 20px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
    overflow: hidden;
    min-height: 0; /* Important for proper scrolling */
  }
  
  .editor-panel.collapsed {
    margin-right: 0.5rem;
  }
  
  .code-section, .visual-section {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    overflow-x: hidden;
    min-height: 0;
  }
  
  /* Make sure CodeMirror takes full height and scrolls */
  .code-section :global(.CodeMirror) {
    height: 100% !important;
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
  }
  
  .code-section :global(.CodeMirror-scroll) {
    height: 100% !important;
  }
  
  .visual-editor {
    padding: 2rem;
  }
  
  .visual-editor h3 {
    margin: 0 0 1rem 0;
    color: #1e293b;
  }
  
  /* Floating Action Button */
  .fab-launch {
    position: absolute;
    bottom: 2rem;
    right: 2rem;
    width: 60px;
    height: 60px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
    border-radius: 50%;
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 8px 24px rgba(102, 126, 234, 0.4);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 10;
  }
  
  .fab-launch:hover:not(:disabled) {
    transform: scale(1.1);
    box-shadow: 0 12px 32px rgba(102, 126, 234, 0.5);
  }
  
  .fab-launch:disabled {
    background: #e2e8f0;
    cursor: not-allowed;
    box-shadow: none;
  }
  
  .fab-launch.ready {
    animation: breathe 2s infinite;
  }
  
  @keyframes breathe {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.05); }
  }
  
  /* Multi-Level Sidebar */
  .config-panel {
    width: 420px;
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(20px);
    margin: 0.5rem 0.5rem 0.5rem 0;
    border-radius: 20px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    height: calc(100vh - 1rem - 64px); /* Account for top bar and margins */
  }
  
  .panel-header {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(102, 126, 234, 0.1);
  }
  
  /* Icon Navigation Bar */
  .icon-nav {
    display: flex;
    gap: 0.25rem;
    padding: 0.5rem;
    background: rgba(102, 126, 234, 0.03);
    border-bottom: 1px solid rgba(102, 126, 234, 0.1);
  }
  
  .icon-nav-btn {
    position: relative;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 1.25rem;
  }
  
  .icon-nav-btn:hover {
    background: rgba(102, 126, 234, 0.08);
    border-color: rgba(102, 126, 234, 0.2);
  }
  
  .icon-nav-btn.active {
    background: linear-gradient(135deg, rgba(102, 126, 234, 0.15) 0%, rgba(118, 75, 162, 0.15) 100%);
    border-color: rgba(102, 126, 234, 0.3);
  }
  
  .icon-nav-btn.active::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 8px;
    right: 8px;
    height: 2px;
    background: linear-gradient(90deg, #667eea, #764ba2);
  }
  
  /* Tooltip */
  .icon-nav-btn::before {
    content: attr(title);
    position: absolute;
    top: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%) scale(0.9);
    background: #1e293b;
    color: white;
    padding: 0.375rem 0.625rem;
    border-radius: 6px;
    font-size: 0.75rem;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: all 0.2s;
    z-index: 1000;
  }
  
  .icon-nav-btn:hover::before {
    opacity: 0.95;
    transform: translateX(-50%) scale(1);
  }
  
  .nav-icon {
    display: block;
    line-height: 1;
  }
  
  .header-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  /* Removed dropdown menu styles - using icon nav instead */
  
  .panel-header h2 {
    margin: 0;
    font-size: 1.125rem;
    color: #1e293b;
    font-weight: 600;
  }
  
  .close-panel {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: transparent;
    border: none;
    color: #94a3b8;
    cursor: pointer;
    border-radius: 8px;
    transition: all 0.2s;
  }
  
  .close-panel:hover {
    background: rgba(102, 126, 234, 0.1);
    color: #667eea;
  }
  
  /* Compact Icon Navigation */
  .icon-nav {
    display: flex;
    justify-content: center;
    gap: 0.25rem;
    padding: 0.75rem;
    border-bottom: 1px solid rgba(102, 126, 234, 0.1);
  }
  
  .icon-nav-item {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: #64748b;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .icon-nav-item:hover {
    background: rgba(102, 126, 234, 0.05);
    border-color: rgba(102, 126, 234, 0.2);
    color: #667eea;
  }
  
  .icon-nav-item.active {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
  }
  
  .icon-nav-item .nav-icon {
    font-size: 1.25rem;
  }
  
  /* Tooltip */
  .icon-nav-item .tooltip {
    position: absolute;
    bottom: -28px;
    left: 50%;
    transform: translateX(-50%);
    background: #1e293b;
    color: white;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.7rem;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s;
    z-index: 10;
  }
  
  .icon-nav-item .tooltip::before {
    content: '';
    position: absolute;
    top: -4px;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 4px solid #1e293b;
  }
  
  .icon-nav-item:hover .tooltip {
    opacity: 1;
  }
  
  /* Sidebar Content */
  .sidebar-content {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 1.5rem;
    min-height: 0; /* Important for scrolling */
  }
  
  /* Custom scrollbar for sidebar */
  .sidebar-content::-webkit-scrollbar {
    width: 6px;
  }
  
  .sidebar-content::-webkit-scrollbar-track {
    background: rgba(102, 126, 234, 0.05);
    border-radius: 3px;
  }
  
  .sidebar-content::-webkit-scrollbar-thumb {
    background: rgba(102, 126, 234, 0.3);
    border-radius: 3px;
  }
  
  .sidebar-content::-webkit-scrollbar-thumb:hover {
    background: rgba(102, 126, 234, 0.5);
  }
  
  .section-content h3 {
    margin: 0 0 1rem 0;
    font-size: 1rem;
    color: #1e293b;
    font-weight: 600;
  }
  
  /* Compact Configuration Styles */
  .compact-config {
    display: flex;
    flex-direction: column;
    gap: 0.625rem;
  }
  
  .config-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.625rem;
  }
  
  .config-row:has(.config-field:only-child) {
    grid-template-columns: 1fr;
  }
  
  .config-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .config-field label {
    font-size: 0.75rem;
    font-weight: 500;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }
  
  .config-field input,
  .config-field select {
    padding: 0.375rem 0.5rem;
    background: white;
    border: 1px solid rgba(102, 126, 234, 0.2);
    border-radius: 6px;
    font-size: 0.8125rem;
    transition: all 0.2s;
  }
  
  .config-field input:focus,
  .config-field select:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
  }
  
  .config-field input[type="number"] {
    -moz-appearance: textfield;
  }
  
  .config-field input[type="number"]::-webkit-inner-spin-button,
  .config-field input[type="number"]::-webkit-outer-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }
  
  /* Advanced config section */
  .advanced-config {
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid rgba(102, 126, 234, 0.1);
  }
  
  .advanced-config summary {
    cursor: pointer;
    font-size: 0.8125rem;
    font-weight: 500;
    color: #667eea;
    margin-bottom: 0.75rem;
    user-select: none;
  }
  
  .advanced-config summary:hover {
    color: #764ba2;
  }
  
  .advanced-config[open] summary {
    margin-bottom: 0.625rem;
  }
  
  /* Current directory display */
  .current-directory {
    background: rgba(102, 126, 234, 0.05);
    border: 1px solid rgba(102, 126, 234, 0.1);
    border-radius: 8px;
    padding: 0.625rem;
    margin-bottom: 0.75rem;
  }
  
  .current-directory label {
    font-size: 0.75rem;
    font-weight: 500;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.025em;
    display: block;
    margin-bottom: 0.25rem;
  }
  
  .directory-path {
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
    font-size: 0.8125rem;
    color: #1e293b;
    word-break: break-all;
    padding: 0.25rem 0.5rem;
    background: white;
    border-radius: 4px;
  }
  
  /* Preset Grid */
  .preset-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.5rem;
  }
  
  .preset-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    padding: 0.625rem 0.375rem;
    background: white;
    border: 1px solid rgba(102, 126, 234, 0.1);
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .preset-card:hover {
    border-color: #667eea;
    background: rgba(102, 126, 234, 0.05);
    transform: translateY(-2px);
  }
  
  .preset-icon {
    font-size: 1.25rem;
  }
  
  .preset-name {
    font-size: 0.7rem;
    font-weight: 500;
    color: #64748b;
    text-align: center;
  }
  
  /* Container Styles */
  .browser-container,
  .sync-container {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1rem;
    max-height: calc(100vh - 350px);
    overflow-y: auto;
  }
  
  /* Make embedded form more compact */
  .embedded-component :global(.form-section),
  .embedded-component :global(.card-section) {
    background: white !important;
    border: 1px solid rgba(102, 126, 234, 0.1) !important;
    border-radius: 8px !important;
    padding: 0.75rem !important;
    margin-bottom: 0.75rem !important;
  }
  
  .embedded-component :global(.section-title) {
    font-size: 0.875rem !important;
    margin-bottom: 0.5rem !important;
    font-weight: 600 !important;
    color: #667eea !important;
  }
  
  .embedded-component :global(.section-subtitle) {
    display: none !important; /* Hide verbose descriptions */
  }
  
  .embedded-component::-webkit-scrollbar {
    width: 6px;
  }
  
  .embedded-component::-webkit-scrollbar-track {
    background: rgba(102, 126, 234, 0.05);
    border-radius: 3px;
  }
  
  .embedded-component::-webkit-scrollbar-thumb {
    background: rgba(102, 126, 234, 0.3);
    border-radius: 3px;
  }
  
  .embedded-component :global(.form-group) {
    margin-bottom: 0.625rem !important;
  }
  
  .embedded-component :global(.form-group label) {
    font-size: 0.8125rem !important;
    margin-bottom: 0.25rem !important;
    color: #64748b !important;
    font-weight: 500 !important;
  }
  
  .embedded-component :global(input),
  .embedded-component :global(select),
  .embedded-component :global(textarea) {
    width: 100% !important;
    padding: 0.5rem 0.625rem !important;
    border: 1px solid rgba(102, 126, 234, 0.2) !important;
    border-radius: 6px !important;
    font-size: 0.8125rem !important;
    transition: all 0.2s;
  }
  
  .embedded-component :global(input[type="number"]) {
    padding: 0.375rem 0.5rem !important;
  }
  
  .embedded-component :global(.info-text) {
    font-size: 0.75rem !important;
    margin-top: 0.25rem !important;
  }
  
  .embedded-component :global(input:focus),
  .embedded-component :global(select:focus),
  .embedded-component :global(textarea:focus) {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }
  
  /* Search Box */
  .search-box {
    position: relative;
    margin-bottom: 1rem;
  }
  
  .search-icon {
    position: absolute;
    left: 0.875rem;
    top: 50%;
    transform: translateY(-50%);
    color: #94a3b8;
    pointer-events: none;
  }
  
  .search-input {
    width: 100%;
    padding: 0.625rem 0.875rem 0.625rem 2.5rem;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    font-size: 0.875rem;
    color: #1e293b;
    transition: all 0.2s;
  }
  
  .search-input:hover {
    background: white;
    border-color: #cbd5e1;
  }
  
  .search-input:focus {
    outline: none;
    background: white;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }
  
  .search-input::placeholder {
    color: #94a3b8;
  }
  
  /* Template Styles */
  .template-list {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  .template-group {
    background: #f8fafc;
    border-radius: 12px;
    padding: 1rem;
    border: 1px solid #e2e8f0;
  }
  
  .group-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #e2e8f0;
  }
  
  .group-icon {
    font-size: 1.125rem;
  }
  
  .group-name {
    font-size: 0.875rem;
    font-weight: 600;
    color: #475569;
  }
  
  .template-grid {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .template-card {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.75rem;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    text-align: left;
  }
  
  .template-card:hover {
    background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%);
    border-color: #667eea;
    transform: translateX(4px);
  }
  
  .template-name {
    font-size: 0.875rem;
    font-weight: 500;
    color: #1e293b;
  }
  
  .template-desc {
    font-size: 0.75rem;
    color: #64748b;
  }
  
  /* Panel Footer */
  .panel-footer {
    display: flex;
    gap: 0.75rem;
    padding: 1.5rem;
    border-top: 1px solid rgba(102, 126, 234, 0.1);
  }
  
  .btn-secondary {
    flex: 1;
    padding: 0.75rem;
    background: white;
    border: 2px solid rgba(102, 126, 234, 0.2);
    color: #667eea;
    border-radius: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .btn-secondary:hover {
    background: rgba(102, 126, 234, 0.05);
    border-color: #667eea;
  }
  
  .btn-primary {
    flex: 1;
    padding: 0.75rem;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
    color: white;
    border-radius: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }
  
  .btn-primary:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
  }
  
  .btn-primary:disabled {
    background: #e2e8f0;
    cursor: not-allowed;
  }
  
  .btn-primary.launching {
    background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%);
  }
  
  /* Spinner */
  .spinner {
    width: 20px;
    height: 20px;
    border: 3px solid rgba(255, 255, 255, 0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  /* Responsive */
  /* Modern Minimal Form - Material Design Inspired */
  .modern-form {
    padding: 0;
  }
  
  .resource-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.25rem 1rem;
    margin-top: 1.5rem;
  }
  
  /* Floating Label Input Fields */
  .input-field {
    position: relative;
    margin-bottom: 1.75rem;
  }
  
  .minimal-input,
  .minimal-select {
    width: 100%;
    padding: 1.25rem 0 0.375rem 0;
    background: transparent;
    border: none;
    border-bottom: 2px solid #e0e0e0;
    font-size: 1rem;
    color: #212121;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    -webkit-appearance: none;
    -moz-appearance: none;
    appearance: none;
  }
  
  .minimal-input:focus,
  .minimal-select:focus {
    outline: none;
    border-bottom-color: #667eea;
  }
  
  .minimal-input:focus ~ .floating-label,
  .minimal-input:not(:placeholder-shown) ~ .floating-label,
  .minimal-select:focus ~ .floating-label,
  .minimal-select:not([value=""]) ~ .floating-label,
  .minimal-input:not([value=""]) ~ .floating-label {
    transform: translateY(-1.5rem) scale(0.75);
    color: #667eea;
  }
  
  .floating-label {
    position: absolute;
    left: 0;
    top: 1rem;
    font-size: 1rem;
    color: #757575;
    pointer-events: none;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    transform-origin: left top;
  }
  
  /* Number inputs */
  .minimal-input[type="number"]::-webkit-inner-spin-button,
  .minimal-input[type="number"]::-webkit-outer-spin-button {
    opacity: 0;
    margin: 0;
    -webkit-appearance: none;
  }
  
  .minimal-input[type="number"]:hover::-webkit-inner-spin-button,
  .minimal-input[type="number"]:hover::-webkit-outer-spin-button {
    opacity: 1;
  }
  
  /* Select dropdown arrow */
  .minimal-select {
    cursor: pointer;
    padding-right: 1.5rem;
    background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="%23757575"><path d="M7 10l5 5 5-5z"/></svg>');
    background-repeat: no-repeat;
    background-position: right 0 center;
  }
  
  .minimal-select:focus {
    background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="%23667eea"><path d="M7 10l5 5 5-5z"/></svg>');
  }
  
  /* Divider */
  .divider {
    height: 1px;
    background: #e0e0e0;
    margin: 2rem 0 1.5rem 0;
  }
  
  /* Advanced Toggle */
  .advanced-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 0.75rem 0;
    background: transparent;
    border: none;
    color: #757575;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: color 0.2s;
    text-align: left;
  }
  
  .advanced-toggle:hover {
    color: #667eea;
  }
  
  .toggle-text {
    flex: 1;
  }
  
  .toggle-icon {
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }
  
  .toggle-icon.rotated {
    transform: rotate(180deg);
  }
  
  .advanced-section {
    margin-top: 1rem;
  }
  
  /* Section Headers */
  .section-header {
    margin-bottom: 2rem;
  }
  
  .section-title {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 300;
    color: #212121;
    letter-spacing: -0.5px;
  }
  
  .section-subtitle {
    margin: 0.5rem 0 0 0;
    font-size: 0.875rem;
    color: #757575;
    font-weight: 400;
  }
  
  /* Modern Preset Tiles */
  .preset-tile {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: white;
    border: 2px solid #f5f5f5;
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    text-align: left;
    width: 100%;
  }
  
  .preset-tile:hover {
    border-color: #667eea;
    background: linear-gradient(135deg, rgba(102, 126, 234, 0.03) 0%, rgba(118, 75, 162, 0.03) 100%);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
  }
  
  .preset-emoji {
    font-size: 1.75rem;
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, #f5f5f5 0%, #fafafa 100%);
    border-radius: 10px;
  }
  
  .preset-info {
    flex: 1;
  }
  
  .preset-title {
    font-size: 0.9375rem;
    font-weight: 500;
    color: #212121;
    margin-bottom: 0.25rem;
  }
  
  .preset-details {
    font-size: 0.75rem;
    color: #757575;
  }
  
  /* Path Display */
  .path-display {
    background: linear-gradient(135deg, #f5f5f5 0%, #fafafa 100%);
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 1.5rem;
  }
  
  .path-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: #757575;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.5rem;
  }
  
  .path-value {
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
    font-size: 0.875rem;
    color: #212121;
    word-break: break-all;
  }
  
  /* File Browser & Sync Wrappers */
  .file-browser-wrapper,
  .sync-wrapper {
    background: white;
    border: 1px solid #f5f5f5;
    border-radius: 12px;
    padding: 1rem;
    max-height: calc(100vh - 350px);
    overflow-y: auto;
  }
  
  /* Template Styles */
  .template-category {
    margin-bottom: 2rem;
  }
  
  .category-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #f5f5f5;
    font-size: 0.875rem;
    font-weight: 500;
    color: #757575;
  }
  
  .category-title {
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  
  .template-item {
    display: block;
    width: 100%;
    padding: 0.875rem 1rem;
    margin-bottom: 0.5rem;
    background: white;
    border: 1px solid #f5f5f5;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    text-align: left;
  }
  
  .template-item:hover {
    background: #fafafa;
    border-color: #667eea;
    transform: translateX(4px);
  }
  
  .template-main {
    font-size: 0.875rem;
    font-weight: 500;
    color: #212121;
    margin-bottom: 0.25rem;
  }
  
  .template-sub {
    font-size: 0.75rem;
    color: #757575;
  }
  
  @media (max-width: 768px) {
    .bar-section.center {
      display: none;
    }
    
    .config-panel {
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      width: 100%;
      margin: 0;
      border-radius: 0;
      z-index: 50;
    }
    
    .editor-panel {
      margin: 0.5rem;
    }
    
    .preset-grid {
      grid-template-columns: 1fr;
    }
  }
</style>