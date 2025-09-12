<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { fade, fly, scale } from 'svelte/transition';
  import ScriptViewer from './ScriptViewer.svelte';
  import ParameterEditor from './ParameterEditor.svelte';
  import ScriptHistory from './ScriptHistory.svelte';
  import TemplateLibrary from './TemplateLibrary.svelte';
  
  const dispatch = createEventDispatcher<{
    launch: { script: string; host: string };
  }>();
  
  export let script: string = '';
  export let launching: boolean = false;
  export let hosts: string[] = [];
  export let selectedHost: string = '';
  export let canLaunch: boolean = false;
  export let validationMessage: string = '';
  
  type ViewMode = 'view' | 'edit' | 'full';
  type TabMode = 'current' | 'history' | 'templates';
  
  let viewMode: ViewMode = 'view';
  let activeTab: TabMode = 'current';
  let showLaunchConfirm = false;
  let editedScript = script;
  
  $: editedScript = script;
  $: canLaunch = !!editedScript && !!selectedHost;
  
  function handleScriptUpdate(event: CustomEvent<{ script: string }>) {
    editedScript = event.detail.script;
    script = editedScript;
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
    viewMode = 'edit'; // Go to edit mode for templates
  }
  
  function confirmLaunch() {
    if (canLaunch) {
      showLaunchConfirm = true;
    }
  }
  
  function doLaunch() {
    if (canLaunch) {
      dispatch('launch', { script: editedScript, host: selectedHost });
      showLaunchConfirm = false;
    }
  }
  
  function getScriptSummary(): string {
    const lines = editedScript.split('\n');
    const jobName = lines.find(l => l.includes('--job-name'))?.split('=')[1] || 'Unnamed Job';
    const time = lines.find(l => l.includes('--time'))?.split('=')[1] || 'No time limit';
    const mem = lines.find(l => l.includes('--mem'))?.split('=')[1] || 'Default memory';
    return `${jobName} • ${time} • ${mem}`;
  }
  
  // Swipe gesture handling
  let touchStartX = 0;
  let touchEndX = 0;
  
  function handleTouchStart(e: TouchEvent) {
    touchStartX = e.touches[0].clientX;
  }
  
  function handleTouchEnd(e: TouchEvent) {
    touchEndX = e.changedTouches[0].clientX;
    handleSwipe();
  }
  
  function handleSwipe() {
    const swipeDistance = touchEndX - touchStartX;
    const minSwipeDistance = 75;
    
    if (Math.abs(swipeDistance) > minSwipeDistance) {
      if (swipeDistance > 0) {
        // Swipe right - go to previous tab
        const tabs: TabMode[] = ['current', 'history', 'templates'];
        const currentIndex = tabs.indexOf(activeTab);
        if (currentIndex > 0) {
          activeTab = tabs[currentIndex - 1];
        }
      } else {
        // Swipe left - go to next tab
        const tabs: TabMode[] = ['current', 'history', 'templates'];
        const currentIndex = tabs.indexOf(activeTab);
        if (currentIndex < tabs.length - 1) {
          activeTab = tabs[currentIndex + 1];
        }
      }
    }
  }
</script>

<div class="mobile-launcher" on:touchstart={handleTouchStart} on:touchend={handleTouchEnd}>
  <!-- Header -->
  <header class="launcher-header">
    <div class="header-top">
      <h1>Job Launcher</h1>
      <select 
        bind:value={selectedHost}
        class="host-select"
        disabled={launching}
      >
        <option value="">Select Host</option>
        {#each hosts as host}
          <option value={host}>{host}</option>
        {/each}
      </select>
    </div>
    
    {#if !canLaunch && validationMessage}
      <div class="validation-bar warning">
        <svg viewBox="0 0 24 24" class="icon">
          <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z" />
        </svg>
        <span>{validationMessage}</span>
      </div>
    {:else if canLaunch}
      <div class="validation-bar success">
        <svg viewBox="0 0 24 24" class="icon">
          <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M17,9L12,14L7,9L8.41,7.59L12,11.17L15.59,7.59L17,9Z" />
        </svg>
        <span>Ready to launch</span>
      </div>
    {/if}
  </header>
  
  <!-- Tab Navigation -->
  <nav class="tab-nav">
    <button 
      class="tab"
      class:active={activeTab === 'current'}
      on:click={() => activeTab = 'current'}
    >
      <svg viewBox="0 0 24 24">
        <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
      </svg>
      Current
    </button>
    
    <button 
      class="tab"
      class:active={activeTab === 'history'}
      on:click={() => activeTab = 'history'}
    >
      <svg viewBox="0 0 24 24">
        <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M16.2,16.2L11,13V7H12.5V12.2L17,14.9L16.2,16.2Z" />
      </svg>
      History
    </button>
    
    <button 
      class="tab"
      class:active={activeTab === 'templates'}
      on:click={() => activeTab = 'templates'}
    >
      <svg viewBox="0 0 24 24">
        <path d="M19,19H5V5H19M19,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5A2,2 0 0,0 19,3M13.96,12.29L11.21,15.83L9.25,13.47L6.5,17H17.5L13.96,12.29Z" />
      </svg>
      Templates
    </button>
  </nav>
  
  <!-- Content Area -->
  <main class="content-area">
    {#if activeTab === 'current'}
      {#if script}
        <!-- View Mode Toggle -->
        <div class="mode-toggle">
          <button 
            class="mode-btn"
            class:active={viewMode === 'view'}
            on:click={() => viewMode = 'view'}
          >
            <svg viewBox="0 0 24 24">
              <path d="M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z" />
            </svg>
            View
          </button>
          
          <button 
            class="mode-btn"
            class:active={viewMode === 'edit'}
            on:click={() => viewMode = 'edit'}
          >
            <svg viewBox="0 0 24 24">
              <path d="M5,3C3.89,3 3,3.89 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V12H19V19H5V5H12V3H5Z" />
              <path d="M17.75,7L14.42,10.33L15.17,11.08L18.5,7.75L17.75,7M20.71,4.04C20.32,3.65 19.69,3.65 19.3,4.04L18.17,5.17L20.83,7.83L21.96,6.7C22.35,6.31 22.35,5.68 21.96,5.29L20.71,4.04M17.41,5.93L11,12.34V15H13.66L20.07,8.59L17.41,5.93Z" />
            </svg>
            Quick Edit
          </button>
          
          <button 
            class="mode-btn"
            class:active={viewMode === 'full'}
            on:click={() => viewMode = 'full'}
          >
            <svg viewBox="0 0 24 24">
              <path d="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z" />
            </svg>
            Full Edit
          </button>
        </div>
        
        <!-- Content based on mode -->
        {#if viewMode === 'view'}
          <div class="script-summary">
            <div class="summary-card">
              <h3>Script Summary</h3>
              <p>{getScriptSummary()}</p>
            </div>
          </div>
          
          <ScriptViewer 
            {script}
            collapsible={true}
            maxHeight="60vh"
          />
          
        {:else if viewMode === 'edit'}
          <ParameterEditor 
            bind:script={editedScript}
            on:update={handleScriptUpdate}
          />
          
          <div class="script-preview">
            <ScriptViewer 
              script={editedScript}
              collapsible={true}
              maxHeight="40vh"
            />
          </div>
          
        {:else if viewMode === 'full'}
          <div class="full-edit-warning">
            <svg viewBox="0 0 24 24" class="warning-icon">
              <path d="M13,14H11V10H13M13,18H11V16H13M1,21H23L12,2L1,21Z" />
            </svg>
            <h3>Full Edit Mode</h3>
            <p>For complex edits, we recommend using a desktop computer for the best experience.</p>
            <button class="continue-btn" on:click={() => alert('Full editor not implemented yet')}>
              Continue Anyway
            </button>
          </div>
        {/if}
        
      {:else}
        <div class="empty-state">
          <svg viewBox="0 0 24 24" class="empty-icon">
            <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
          </svg>
          <h3>No Script Selected</h3>
          <p>Choose a script from history or start with a template</p>
        </div>
      {/if}
      
    {:else if activeTab === 'history'}
      <ScriptHistory on:select={handleHistorySelect} />
      
    {:else if activeTab === 'templates'}
      <TemplateLibrary on:select={handleTemplateSelect} />
    {/if}
  </main>
  
  <!-- Launch Button -->
  <div class="launch-container">
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
        Launching...
      {:else}
        <svg viewBox="0 0 24 24">
          <path d="M8,5.14V19.14L19,12.14L8,5.14Z" />
        </svg>
        Launch Job
      {/if}
    </button>
  </div>
  
  <!-- Launch Confirmation -->
  {#if showLaunchConfirm}
    <div class="confirm-overlay" transition:fade={{ duration: 200 }}>
      <div class="confirm-dialog" transition:scale={{ duration: 200 }}>
        <h3>Confirm Launch</h3>
        <div class="confirm-details">
          <p><strong>Host:</strong> {selectedHost}</p>
          <p><strong>Script:</strong> {getScriptSummary()}</p>
        </div>
        <div class="confirm-actions">
          <button class="cancel-btn" on:click={() => showLaunchConfirm = false}>
            Cancel
          </button>
          <button class="confirm-btn" on:click={doLaunch}>
            Launch Now
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .mobile-launcher {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: #0a0e1a;
    color: #e4e8f1;
  }
  
  /* Header */
  .launcher-header {
    background: linear-gradient(135deg, #141925 0%, #1e2433 100%);
    border-bottom: 1px solid #2a3142;
    padding: 1rem;
    padding-top: calc(1rem + env(safe-area-inset-top));
  }
  
  .header-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }
  
  .launcher-header h1 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
  }
  
  .host-select {
    padding: 0.5rem 0.75rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 8px;
    color: #e4e8f1;
    font-size: 0.9rem;
    outline: none;
  }
  
  .validation-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    border-radius: 8px;
    font-size: 0.875rem;
  }
  
  .validation-bar.warning {
    background: rgba(239, 68, 68, 0.1);
    color: #ef4444;
    border: 1px solid rgba(239, 68, 68, 0.2);
  }
  
  .validation-bar.success {
    background: rgba(16, 185, 129, 0.1);
    color: #10b981;
    border: 1px solid rgba(16, 185, 129, 0.2);
  }
  
  .validation-bar .icon {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
  }
  
  /* Tab Navigation */
  .tab-nav {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    background: #141925;
    border-bottom: 1px solid #2a3142;
  }
  
  .tab {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    padding: 0.75rem;
    background: transparent;
    border: none;
    color: #6b7280;
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }
  
  .tab.active {
    color: #3b82f6;
    background: rgba(59, 130, 246, 0.1);
    border-bottom: 2px solid #3b82f6;
  }
  
  .tab svg {
    width: 24px;
    height: 24px;
  }
  
  /* Content Area */
  .content-area {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
    padding-bottom: 100px;
  }
  
  .mode-toggle {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.5rem;
    margin-bottom: 1rem;
  }
  
  .mode-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    padding: 0.75rem;
    background: #141925;
    border: 1px solid #2a3142;
    border-radius: 10px;
    color: #6b7280;
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }
  
  .mode-btn.active {
    background: #1e2433;
    border-color: #3b82f6;
    color: #3b82f6;
  }
  
  .mode-btn svg {
    width: 24px;
    height: 24px;
  }
  
  .script-summary {
    margin-bottom: 1rem;
  }
  
  .summary-card {
    background: #141925;
    border: 1px solid #2a3142;
    border-radius: 10px;
    padding: 1rem;
  }
  
  .summary-card h3 {
    margin: 0 0 0.5rem 0;
    color: #9ca3af;
    font-size: 0.875rem;
    font-weight: 500;
    text-transform: uppercase;
  }
  
  .summary-card p {
    margin: 0;
    color: #e4e8f1;
    font-size: 1rem;
  }
  
  .script-preview {
    margin-top: 1rem;
  }
  
  .full-edit-warning {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 2rem;
  }
  
  .warning-icon {
    width: 48px;
    height: 48px;
    color: #f59e0b;
    margin-bottom: 1rem;
  }
  
  .full-edit-warning h3 {
    margin: 0 0 0.5rem 0;
    color: #e4e8f1;
  }
  
  .full-edit-warning p {
    margin: 0 0 1.5rem 0;
    color: #9ca3af;
  }
  
  .continue-btn {
    padding: 0.75rem 1.5rem;
    background: #2a3142;
    border: none;
    border-radius: 8px;
    color: #e4e8f1;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
  }
  
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 3rem 1rem;
  }
  
  .empty-icon {
    width: 64px;
    height: 64px;
    color: #2a3142;
    margin-bottom: 1rem;
  }
  
  .empty-state h3 {
    margin: 0 0 0.5rem 0;
    color: #e4e8f1;
  }
  
  .empty-state p {
    margin: 0;
    color: #9ca3af;
  }
  
  /* Launch Button */
  .launch-container {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 1rem;
    padding-bottom: calc(1rem + env(safe-area-inset-bottom));
    background: linear-gradient(180deg, transparent 0%, #0a0e1a 20%);
  }
  
  .launch-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    width: 100%;
    padding: 1rem;
    background: #2a3142;
    border: none;
    border-radius: 12px;
    color: #6b7280;
    font-size: 1.1rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }
  
  .launch-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .launch-btn.ready:not(:disabled) {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
    box-shadow: 0 4px 20px rgba(59, 130, 246, 0.4);
  }
  
  .launch-btn.ready:active:not(:disabled) {
    transform: scale(0.98);
  }
  
  .launch-btn.launching {
    background: #f59e0b;
    color: white;
  }
  
  .launch-btn svg {
    width: 24px;
    height: 24px;
  }
  
  .spinner {
    animation: spin 1s linear infinite;
  }
  
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  
  /* Confirmation Dialog */
  .confirm-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    z-index: 1000;
  }
  
  .confirm-dialog {
    background: #1a1f2e;
    border-radius: 16px;
    padding: 1.5rem;
    max-width: 400px;
    width: 100%;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
  }
  
  .confirm-dialog h3 {
    margin: 0 0 1rem 0;
    color: #e4e8f1;
  }
  
  .confirm-details {
    background: #141925;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1.5rem;
  }
  
  .confirm-details p {
    margin: 0.5rem 0;
    color: #9ca3af;
  }
  
  .confirm-details strong {
    color: #e4e8f1;
  }
  
  .confirm-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
  }
  
  .cancel-btn,
  .confirm-btn {
    padding: 0.75rem;
    border: none;
    border-radius: 8px;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .cancel-btn {
    background: #2a3142;
    color: #9ca3af;
  }
  
  .confirm-btn {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
  }
</style>