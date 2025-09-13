<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { fade, fly, scale } from 'svelte/transition';
  import ScriptViewer from './ScriptViewer.svelte';
  import ScriptEditor from './ScriptEditor.svelte';
  import ScriptHistory from './ScriptHistory.svelte';
  import TemplateLibrary from './TemplateLibrary.svelte';
  
  const dispatch = createEventDispatcher<{
    launch: void;
    scriptUpdate: { script: string };
    hostChange: { host: string };
  }>();
  
  export let script: string = '';
  export let launching: boolean = false;
  export let hosts: string[] = [];
  export let selectedHost: string = '';
  export let canLaunch: boolean = false;
  export let validationMessage: string = '';
  
  type ViewMode = 'view' | 'edit';
  type TabMode = 'current' | 'history' | 'templates';
  
  let viewMode: ViewMode = 'view';
  let activeTab: TabMode = 'current';
  let showLaunchConfirm = false;
  let editedScript = script;
  let scriptExpanded = false;
  let showEditor = false;
  let editorMode: 'normal' | 'vim' = 'normal';
  
  $: editedScript = script;
  $: canLaunch = !!editedScript && !!selectedHost;
  
  function handleScriptUpdate(event: CustomEvent<{ script: string }>) {
    editedScript = event.detail.script;
    script = editedScript;
    dispatch('scriptUpdate', { script: editedScript });
  }
  
  function handleHistorySelect(event: CustomEvent<{ script: string }>) {
    script = event.detail.script;
    editedScript = script;
    activeTab = 'current';
    viewMode = 'view';
  }
  
  function handleTemplateSelect(event: CustomEvent<{ script: string }>) {
    script = event.detail.script;
    editedScript = script;
    activeTab = 'current';
    viewMode = 'edit';
  }
  
  function confirmLaunch() {
    if (canLaunch) {
      showLaunchConfirm = true;
    }
  }
  
  function doLaunch() {
    if (canLaunch) {
      dispatch('launch');
      showLaunchConfirm = false;
    }
  }
  
  function getScriptSummary(): { name: string; time: string; memory: string; cpus: string } {
    const lines = editedScript.split('\n');
    return {
      name: lines.find(l => l.includes('--job-name'))?.split('=')[1]?.trim() || 'Unnamed',
      time: lines.find(l => l.includes('--time'))?.split('=')[1]?.trim() || '00:00',
      memory: lines.find(l => l.includes('--mem'))?.split('=')[1]?.trim() || '0GB',
      cpus: lines.find(l => l.includes('--cpus-per-task'))?.split('=')[1]?.trim() || '1'
    };
  }
  
  function getScriptPreview(): string[] {
    if (!editedScript) return [];
    const lines = editedScript.split('\n').filter(line => line.trim());
    return lines.slice(0, 3);
  }
</script>

<div class="mobile-launcher">
  <!-- Simplified Header -->
  <header class="header">
    <h1>Job Launcher</h1>
    
    <!-- Host Selector -->
    <select 
      bind:value={selectedHost}
      class="host-select"
      class:has-value={selectedHost}
      disabled={launching}
    >
      <option value="">Select Host</option>
      {#each hosts as host}
        <option value={host}>{host}</option>
      {/each}
    </select>
  </header>
  
  <!-- Status Bar -->
  {#if selectedHost && script}
    <div class="status-bar" class:ready={canLaunch}>
      <div class="status-icon">
        {#if canLaunch}
          <svg viewBox="0 0 24 24">
            <path d="M9,16.17L4.83,12L3.41,13.41L9,19L21,7L19.59,5.59L9,16.17Z" />
          </svg>
        {:else}
          <svg viewBox="0 0 24 24">
            <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M12,20C16.42,20 20,16.42 20,12C20,7.58 16.42,4 12,4C7.58,4 4,7.58 4,12C4,16.42 7.58,20 12,20M12,11H16V13H12V11M8,11H10V13H8V11Z" />
          </svg>
        {/if}
      </div>
      <span class="status-text">
        {canLaunch ? 'Ready to launch' : validationMessage || 'Configure job'}
      </span>
    </div>
  {/if}
  
  <!-- Main Content Area -->
  <main class="content">
    <!-- Tab Bar -->
    <nav class="tabs">
      <button 
        class="tab"
        class:active={activeTab === 'current'}
        on:click={() => activeTab = 'current'}
      >
        Current
      </button>
      <button 
        class="tab"
        class:active={activeTab === 'history'}
        on:click={() => activeTab = 'history'}
      >
        History
      </button>
      <button 
        class="tab"
        class:active={activeTab === 'templates'}
        on:click={() => activeTab = 'templates'}
      >
        Templates
      </button>
    </nav>
    
    <!-- Tab Content -->
    <div class="tab-content">
      {#if activeTab === 'current'}
        {#if script}
          <!-- Job Summary Card -->
          {@const summary = getScriptSummary()}
          <div class="job-card">
            <div class="job-header">
              <h2>{summary.name}</h2>
              <button 
                class="edit-btn"
                on:click={() => showEditor = true}
                title="Edit script"
              >
                <svg viewBox="0 0 24 24">
                  <path d="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z" />
                </svg>
              </button>
            </div>
            
            <div class="job-details">
              <div class="detail">
                <svg viewBox="0 0 24 24">
                  <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z" />
                </svg>
                <span>{summary.time}</span>
              </div>
              <div class="detail">
                <svg viewBox="0 0 24 24">
                  <path d="M17,17H7V7H17M21,11V9H19V7C19,5.89 18.1,5 17,5H15V3H13V5H11V3H9V5H7C5.89,5 5,5.89 5,7V9H3V11H5V13H3V15H5V17A2,2 0 0,0 7,19H9V21H11V19H13V21H15V19H17A2,2 0 0,0 19,17V15H21V13H19V11M13,13V11H11V13H13M15,15V13H13V15H15Z" />
                </svg>
                <span>{summary.memory}</span>
              </div>
              <div class="detail">
                <svg viewBox="0 0 24 24">
                  <path d="M17,17H7V7H17M21,11V9H19V7C19,5.89 18.1,5 17,5H15V3H13V5H11V3H9V5H7C5.89,5 5,5.89 5,7V9H3V11H5V13H3V15H5V17A2,2 0 0,0 7,19H9V21H11V19H13V21H15V19H17A2,2 0 0,0 19,17V15H21V13H19V11M13,13V11H11V13H13M15,15V13H13V15H15Z" />
                </svg>
                <span>{summary.cpus} CPUs</span>
              </div>
            </div>
          </div>
          
          <!-- Quick Actions Bar -->
          <div class="quick-actions-bar">
            <button 
              class="quick-btn"
              on:click={() => showEditor = true}
            >
              <svg viewBox="0 0 24 24">
                <path d="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z" />
              </svg>
              <span>Edit Script</span>
            </button>
            
            <button 
              class="quick-btn"
              on:click={() => activeTab = 'templates'}
            >
              <svg viewBox="0 0 24 24">
                <path d="M19,19H5V5H19M19,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5A2,2 0 0,0 19,3M13.96,12.29L11.21,15.83L9.25,13.47L6.5,17H17.5L13.96,12.29Z" />
              </svg>
              <span>Use Template</span>
            </button>
            
            <button 
              class="quick-btn"
              on:click={() => activeTab = 'history'}
            >
              <svg viewBox="0 0 24 24">
                <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M16.2,16.2L11,13V7H12.5V12.2L17,14.9L16.2,16.2Z" />
              </svg>
              <span>From History</span>
            </button>
          </div>
          
          <!-- Script Preview -->
          <div class="script-section">
            <button 
              class="script-toggle"
              on:click={() => scriptExpanded = !scriptExpanded}
            >
              <svg class="chevron" class:expanded={scriptExpanded} viewBox="0 0 24 24">
                <path d="M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z" />
              </svg>
              <span>Script ({editedScript.split('\n').length} lines)</span>
              <div class="script-actions">
                <button class="icon-btn" on:click|stopPropagation={() => navigator.clipboard.writeText(editedScript)}>
                  <svg viewBox="0 0 24 24">
                    <path d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z" />
                  </svg>
                </button>
              </div>
            </button>
            
            {#if scriptExpanded}
              <div class="script-content" transition:fade={{ duration: 200 }}>
                <ScriptViewer 
                  script={editedScript}
                  collapsible={false}
                  showLineNumbers={true}
                  maxHeight="60vh"
                />
              </div>
            {:else if getScriptPreview().length > 0}
              <div class="script-preview" transition:fade={{ duration: 200 }}>
                {#each getScriptPreview() as line}
                  <code>{line}</code>
                {/each}
              </div>
            {/if}
          </div>
          
        {:else}
          <!-- Empty State -->
          <div class="empty-state">
            <svg viewBox="0 0 24 24">
              <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
            </svg>
            <h3>No Script Selected</h3>
            <p>Start with a template or select from history</p>
            <div class="quick-actions">
              <button class="action-btn" on:click={() => activeTab = 'templates'}>
                Browse Templates
              </button>
              <button class="action-btn secondary" on:click={() => activeTab = 'history'}>
                View History
              </button>
            </div>
          </div>
        {/if}
        
      {:else if activeTab === 'history'}
        <ScriptHistory on:select={handleHistorySelect} />
        
      {:else if activeTab === 'templates'}
        <TemplateLibrary on:select={handleTemplateSelect} />
      {/if}
    </div>
  </main>
  
  <!-- Launch Button -->
  <footer class="footer">
    <button 
      class="launch-btn"
      class:ready={canLaunch}
      class:launching={launching}
      on:click={confirmLaunch}
      disabled={!canLaunch || launching}
    >
      {#if launching}
        <svg class="spinner" viewBox="0 0 24 24">
          <path d="M12,4V2A10,10 0 0,0 2,12H4A8,8 0 0,1 12,4Z" />
        </svg>
        <span>Launching...</span>
      {:else}
        <svg viewBox="0 0 24 24">
          <path d="M8,5.14V19.14L19,12.14L8,5.14Z" />
        </svg>
        <span>Launch Job</span>
      {/if}
    </button>
  </footer>
  
  <!-- Script Editor Overlay -->
  {#if showEditor}
    <div class="editor-overlay" transition:fade={{ duration: 200 }}>
      <div class="editor-modal" transition:fly={{ y: 100, duration: 300 }}>
        <ScriptEditor 
          bind:script={editedScript}
          mode={editorMode}
          on:update={handleScriptUpdate}
          on:close={() => showEditor = false}
        />
      </div>
    </div>
  {/if}
  
  <!-- Launch Confirmation -->
  {#if showLaunchConfirm}
    {@const summary = getScriptSummary()}
    <div class="overlay" transition:fade={{ duration: 200 }} on:click={() => showLaunchConfirm = false}>
      <div class="dialog" transition:scale={{ duration: 200 }} on:click|stopPropagation>
        <h3>Confirm Launch</h3>
        <p>Launch job on <strong>{selectedHost}</strong>?</p>
        <div class="dialog-details">
          <div class="detail-row">
            <span>Job:</span>
            <strong>{summary.name}</strong>
          </div>
          <div class="detail-row">
            <span>Time:</span>
            <strong>{summary.time}</strong>
          </div>
          <div class="detail-row">
            <span>Memory:</span>
            <strong>{summary.memory}</strong>
          </div>
        </div>
        <div class="dialog-actions">
          <button class="btn-secondary" on:click={() => showLaunchConfirm = false}>
            Cancel
          </button>
          <button class="btn-primary" on:click={doLaunch}>
            Launch
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  /* Base Layout */
  .mobile-launcher {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: #f8fafc;
    color: #334155;
  }
  
  /* Header */
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    padding-top: calc(1rem + env(safe-area-inset-top));
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
  }
  
  .header h1 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: #1e293b;
  }
  
  .host-select {
    padding: 0.625rem 2.5rem 0.625rem 0.875rem;
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    color: #64748b;
    font-size: 0.875rem;
    font-weight: 500;
    outline: none;
    appearance: none;
    background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%2364748b'%3e%3cpath d='M7,10L12,15L17,10H7Z'/%3e%3c/svg%3e");
    background-repeat: no-repeat;
    background-position: right 0.5rem center;
    background-size: 20px;
    cursor: pointer;
  }
  
  .host-select.has-value {
    color: #3b82f6;
    border-color: #3b82f6;
    background-color: #f0f9ff;
  }
  
  /* Status Bar */
  .status-bar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: #fef7cd;
    border-bottom: 1px solid #fbbf24;
  }
  
  .status-bar.ready {
    background: #d1fae5;
    border-color: #22c55e;
  }
  
  .status-icon {
    width: 20px;
    height: 20px;
  }
  
  .status-icon svg {
    width: 100%;
    height: 100%;
    fill: #eab308;
  }
  
  .status-bar.ready .status-icon svg {
    fill: #16a34a;
  }
  
  .status-text {
    font-size: 0.875rem;
    font-weight: 500;
    color: #a16207;
  }
  
  .status-bar.ready .status-text {
    color: #15803d;
  }
  
  /* Content Area */
  .content {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: #f1f5f9;
  }
  
  /* Tabs */
  .tabs {
    display: flex;
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 0 1rem;
  }
  
  .tab {
    flex: 1;
    padding: 1rem 0;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: #64748b;
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .tab.active {
    color: #3b82f6;
    border-bottom-color: #3b82f6;
  }
  
  /* Tab Content */
  .tab-content {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
  }
  
  /* Job Card */
  .job-card {
    background: #ffffff;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }
  
  .job-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .job-header h2 {
    margin: 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: #1e293b;
  }
  
  .edit-btn {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f1f5f9;
    border: none;
    border-radius: 8px;
    color: #64748b;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .edit-btn:active {
    background: #e2e8f0;
    transform: scale(0.95);
  }
  
  .edit-btn svg {
    width: 20px;
    height: 20px;
  }
  
  .job-details {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
  }
  
  .detail {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    color: #64748b;
    font-size: 0.875rem;
  }
  
  .detail svg {
    width: 16px;
    height: 16px;
    fill: #94a3b8;
  }
  
  /* Quick Actions Bar */
  .quick-actions-bar {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    padding-bottom: 0.25rem;
  }
  
  .quick-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 0.875rem;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    color: #475569;
    font-size: 0.875rem;
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
    transition: all 0.2s;
    flex-shrink: 0;
  }
  
  .quick-btn:active {
    background: #f1f5f9;
    border-color: #3b82f6;
    transform: scale(0.98);
  }
  
  .quick-btn svg {
    width: 16px;
    height: 16px;
    fill: #64748b;
  }
  
  /* Script Section */
  .script-section {
    background: #ffffff;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }
  
  .script-toggle {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 1rem;
    background: none;
    border: none;
    color: #475569;
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
    text-align: left;
  }
  
  .chevron {
    width: 20px;
    height: 20px;
    transition: transform 0.2s;
    fill: #64748b;
  }
  
  .chevron.expanded {
    transform: rotate(180deg);
  }
  
  .script-toggle span {
    flex: 1;
  }
  
  .script-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .icon-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f1f5f9;
    border: none;
    border-radius: 6px;
    color: #64748b;
    cursor: pointer;
  }
  
  .icon-btn svg {
    width: 18px;
    height: 18px;
  }
  
  .script-content {
    border-top: 1px solid #e2e8f0;
  }
  
  .script-preview {
    padding: 0 1rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .script-preview code {
    padding: 0.375rem 0.625rem;
    background: #f1f5f9;
    border-radius: 6px;
    font-family: 'SF Mono', Monaco, monospace;
    font-size: 0.8125rem;
    color: #64748b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  
  /* Empty State */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 3rem 1rem;
  }
  
  .empty-state svg {
    width: 64px;
    height: 64px;
    fill: #cbd5e1;
    margin-bottom: 1rem;
  }
  
  .empty-state h3 {
    margin: 0 0 0.5rem 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: #1e293b;
  }
  
  .empty-state p {
    margin: 0 0 1.5rem 0;
    color: #64748b;
    font-size: 0.9375rem;
  }
  
  .quick-actions {
    display: flex;
    gap: 0.75rem;
  }
  
  .action-btn {
    padding: 0.75rem 1.25rem;
    background: #3b82f6;
    border: none;
    border-radius: 8px;
    color: white;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .action-btn.secondary {
    background: #ffffff;
    color: #475569;
    border: 1px solid #cbd5e1;
  }
  
  .action-btn:active {
    transform: scale(0.95);
  }
  
  /* Footer */
  .footer {
    padding: 1rem;
    padding-bottom: calc(1rem + env(safe-area-inset-bottom));
    background: #ffffff;
    border-top: 1px solid #e2e8f0;
  }
  
  .launch-btn {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    padding: 1rem;
    background: #e2e8f0;
    border: none;
    border-radius: 12px;
    color: #94a3b8;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .launch-btn:disabled {
    cursor: not-allowed;
  }
  
  .launch-btn.ready:not(:disabled) {
    background: #3b82f6;
    color: white;
  }
  
  .launch-btn.ready:active:not(:disabled) {
    transform: scale(0.98);
    background: #2563eb;
  }
  
  .launch-btn.launching {
    background: #eab308;
    color: white;
  }
  
  .launch-btn svg {
    width: 20px;
    height: 20px;
  }
  
  .spinner {
    animation: spin 1s linear infinite;
  }
  
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  
  /* Dialog Overlay */
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    z-index: 1000;
  }
  
  .dialog {
    background: white;
    border-radius: 16px;
    padding: 1.5rem;
    max-width: 320px;
    width: 100%;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
  }
  
  .dialog h3 {
    margin: 0 0 0.5rem 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: #1e293b;
  }
  
  .dialog p {
    margin: 0 0 1rem 0;
    color: #64748b;
    font-size: 0.9375rem;
  }
  
  .dialog-details {
    background: #f8fafc;
    border-radius: 8px;
    padding: 0.75rem;
    margin-bottom: 1.5rem;
  }
  
  .detail-row {
    display: flex;
    justify-content: space-between;
    padding: 0.25rem 0;
    font-size: 0.875rem;
  }
  
  .detail-row span {
    color: #64748b;
  }
  
  .detail-row strong {
    color: #1e293b;
    font-weight: 500;
  }
  
  .dialog-actions {
    display: flex;
    gap: 0.75rem;
  }
  
  .btn-primary,
  .btn-secondary {
    flex: 1;
    padding: 0.75rem;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .btn-primary {
    background: #3b82f6;
    border: none;
    color: white;
  }
  
  .btn-secondary {
    background: white;
    border: 1px solid #cbd5e1;
    color: #475569;
  }
  
  .btn-primary:active,
  .btn-secondary:active {
    transform: scale(0.95);
  }
  
  /* Editor Overlay */
  .editor-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: flex-end;
    z-index: 1000;
  }
  
  .editor-modal {
    width: 100%;
    height: 85vh;
    background: #ffffff;
    border-radius: 16px 16px 0 0;
    overflow: hidden;
    box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.15);
  }
  
  @media (min-width: 768px) {
    .editor-overlay {
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }
    
    .editor-modal {
      max-width: 800px;
      height: 80vh;
      border-radius: 16px;
    }
  }
</style>