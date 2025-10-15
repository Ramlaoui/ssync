<script lang="ts">
  import { run } from 'svelte/legacy';

  import { onMount, createEventDispatcher, tick } from "svelte";
  import { fade, fly, scale } from 'svelte/transition';

  const dispatch = createEventDispatcher<{
    launch: void;
    change: { content: string };
    openHistory: void;
  }>();

  interface Props {
    script?: string;
    launching?: boolean;
    canLaunch?: boolean;
    validationMessage?: string;
  }

  let {
    script = $bindable(""),
    launching = false,
    canLaunch = false,
    validationMessage = ""
  }: Props = $props();

  let textarea: HTMLTextAreaElement = $state();
  let scrollContainer: HTMLDivElement = $state();
  let showActions = $state(false);
  let showQuickInsert = $state(false);
  let copied = $state(false);
  let saved = $state(false);
  let cursorPosition = 0;
  let selectedText = $state("");
  let lineCount = $state(1);
  let currentLine = $state(1);
  let fontSize = $state(16);
  let isDarkMode = $state(true);
  
  // Common SLURM snippets for quick insert
  const snippets = [
    { label: "Job Name", value: "#SBATCH --job-name=", icon: "📝" },
    { label: "Time Limit", value: "#SBATCH --time=", icon: "⏰" },
    { label: "Memory", value: "#SBATCH --mem=", icon: "💾" },
    { label: "CPUs", value: "#SBATCH --cpus-per-task=", icon: "🖥️" },
    { label: "GPU", value: "#SBATCH --gres=gpu:", icon: "🎮" },
    { label: "Partition", value: "#SBATCH --partition=", icon: "📊" },
    { label: "Module Load", value: "module load ", icon: "📦" },
    { label: "Conda Activate", value: "conda activate ", icon: "🐍" },
    { label: "Echo", value: 'echo "', icon: "💬" },
    { label: "Python Run", value: "python ", icon: "🐍" },
  ];

  run(() => {
    lineCount = (script.match(/\n/g) || []).length + 1;
  });

  onMount(() => {
    adjustTextareaHeight();
    updateCursorInfo();
  });

  function adjustTextareaHeight() {
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.max(textarea.scrollHeight, window.innerHeight * 0.5)}px`;
    }
  }

  function handleInput() {
    script = textarea.value;
    dispatch('change', { content: script });
    adjustTextareaHeight();
    updateCursorInfo();
    saved = false;
  }

  function updateCursorInfo() {
    if (!textarea) return;
    
    cursorPosition = textarea.selectionStart;
    const textBeforeCursor = script.substring(0, cursorPosition);
    currentLine = (textBeforeCursor.match(/\n/g) || []).length + 1;
    
    if (textarea.selectionStart !== textarea.selectionEnd) {
      selectedText = script.substring(textarea.selectionStart, textarea.selectionEnd);
    } else {
      selectedText = "";
    }
  }

  function insertSnippet(snippet: string) {
    if (!textarea) return;
    
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const before = script.substring(0, start);
    const after = script.substring(end);
    
    script = before + snippet + after;
    dispatch('change', { content: script });
    
    // Move cursor after inserted text
    tick().then(() => {
      textarea.selectionStart = textarea.selectionEnd = start + snippet.length;
      textarea.focus();
      adjustTextareaHeight();
      updateCursorInfo();
    });
    
    showQuickInsert = false;
  }

  async function copyScript() {
    try {
      await navigator.clipboard.writeText(script);
      copied = true;
      setTimeout(() => copied = false, 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  }

  function downloadScript() {
    const blob = new Blob([script], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'job-script.sh';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    saved = true;
  }

  function handleLaunch() {
    if (canLaunch && !launching) {
      dispatch('launch');
    }
  }

  function changeFontSize(delta: number) {
    fontSize = Math.max(12, Math.min(24, fontSize + delta));
  }

  function toggleTheme() {
    isDarkMode = !isDarkMode;
  }

  function handleKeyDown(e: KeyboardEvent) {
    // Tab key inserts spaces
    if (e.key === 'Tab') {
      e.preventDefault();
      insertSnippet('  ');
    }
    
    // Cmd/Ctrl + Enter to launch
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      handleLaunch();
    }
  }
</script>

<div class="mobile-editor" class:dark={isDarkMode} class:light={!isDarkMode}>
  <!-- Compact Header -->
  <header class="editor-header">
    <div class="header-left">
      <button class="icon-btn" onclick={() => dispatch('openHistory')} aria-label="Script History">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M16.2,16.2L11,13V7H12.5V12.2L17,14.9L16.2,16.2Z" />
        </svg>
      </button>
      <div class="editor-title">Script Editor</div>
    </div>
    
    <div class="header-right">
      <button class="icon-btn" onclick={() => showActions = !showActions} aria-label="More Actions">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,16A2,2 0 0,1 14,18A2,2 0 0,1 12,20A2,2 0 0,1 10,18A2,2 0 0,1 12,16M12,10A2,2 0 0,1 14,12A2,2 0 0,1 12,14A2,2 0 0,1 10,12A2,2 0 0,1 12,10M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8A2,2 0 0,1 10,6A2,2 0 0,1 12,4Z" />
        </svg>
      </button>
    </div>
  </header>

  <!-- Status Bar -->
  <div class="status-bar">
    <span class="status-item">Line {currentLine}/{lineCount}</span>
    {#if selectedText}
      <span class="status-item">{selectedText.length} selected</span>
    {/if}
    <span class="status-item flex-1"></span>
    {#if !canLaunch && validationMessage}
      <span class="status-warning">{validationMessage}</span>
    {:else if canLaunch}
      <span class="status-ready">Ready</span>
    {/if}
  </div>

  <!-- Main Editor Area -->
  <div class="editor-container" bind:this={scrollContainer}>
    <div class="line-numbers">
      {#each Array(lineCount) as _, i}
        <div class="line-number" class:active={i + 1 === currentLine}>
          {i + 1}
        </div>
      {/each}
    </div>
    
    <textarea
      bind:this={textarea}
      bind:value={script}
      oninput={handleInput}
      onselect={updateCursorInfo}
      onclick={updateCursorInfo}
      onkeydown={handleKeyDown}
      placeholder="#!/bin/bash&#10;#SBATCH --job-name=my-job&#10;#SBATCH --time=01:00:00&#10;#SBATCH --mem=4G&#10;&#10;# Your commands here..."
      spellcheck="false"
      autocomplete="off"
      autocorrect="off"
      autocapitalize="off"
      style="font-size: {fontSize}px;"
      disabled={launching}
></textarea>
  </div>

  <!-- Quick Insert Bar -->
  <div class="quick-insert-bar">
    <button 
      class="quick-btn"
      onclick={() => showQuickInsert = !showQuickInsert}
    >
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z" />
      </svg>
      Insert
    </button>
    
    <div class="quick-actions">
      <button class="quick-btn" onclick={() => changeFontSize(-2)} aria-label="Decrease Font">
        A-
      </button>
      <button class="quick-btn" onclick={() => changeFontSize(2)} aria-label="Increase Font">
        A+
      </button>
      <button class="quick-btn" onclick={toggleTheme} aria-label="Toggle Theme">
        {#if isDarkMode}
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6A6,6 0 0,1 18,12A6,6 0 0,1 12,18M20,15.31L23.31,12L20,8.69V4H15.31L12,0.69L8.69,4H4V8.69L0.69,12L4,15.31V20H8.69L12,23.31L15.31,20H20V15.31Z" />
          </svg>
        {:else}
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M17.75,4.09L15.22,6.03L16.13,9.09L13.5,7.28L10.87,9.09L11.78,6.03L9.25,4.09L12.44,4L13.5,1L14.56,4L17.75,4.09M21.25,11L19.61,12.25L20.2,14.23L18.5,13.06L16.8,14.23L17.39,12.25L15.75,11L17.81,10.95L18.5,9L19.19,10.95L21.25,11M18.97,15.95C19.8,15.87 20.69,17.05 20.16,17.8C19.84,18.25 19.5,18.67 19.08,19.07C15.17,23 8.84,23 4.94,19.07C1.03,15.17 1.03,8.83 4.94,4.93C5.34,4.53 5.76,4.17 6.21,3.85C6.96,3.32 8.14,4.21 8.06,5.04C7.79,7.9 8.75,10.87 10.95,13.06C13.14,15.26 16.1,16.22 18.97,15.95M17.33,17.97C14.5,17.81 11.7,16.64 9.53,14.5C7.36,12.31 6.2,9.5 6.04,6.68C3.23,9.82 3.34,14.64 6.35,17.66C9.37,20.67 14.19,20.78 17.33,17.97Z" />
          </svg>
        {/if}
      </button>
    </div>
  </div>

  <!-- Primary Action Button -->
  <button 
    class="launch-button"
    class:ready={canLaunch}
    class:launching={launching}
    onclick={handleLaunch}
    disabled={!canLaunch || launching}
  >
    {#if launching}
      <svg class="spinner" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12,4V2A10,10 0 0,0 2,12H4A8,8 0 0,1 12,4Z" />
      </svg>
      Launching...
    {:else}
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M8,5.14V19.14L19,12.14L8,5.14Z" />
      </svg>
      Launch Job
    {/if}
  </button>

  <!-- Quick Insert Panel -->
  {#if showQuickInsert}
    <div class="quick-insert-panel" transition:fly={{ y: 100, duration: 200 }}>
      <div class="panel-header">
        <h3>Quick Insert</h3>
        <button class="close-btn" onclick={() => showQuickInsert = false}>
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z" />
          </svg>
        </button>
      </div>
      <div class="snippet-grid">
        {#each snippets as snippet}
          <button 
            class="snippet-btn"
            onclick={() => insertSnippet(snippet.value)}
          >
            <span class="snippet-icon">{snippet.icon}</span>
            <span class="snippet-label">{snippet.label}</span>
          </button>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Actions Sheet -->
  {#if showActions}
    <div class="action-sheet" transition:fly={{ y: 100, duration: 200 }}>
      <button class="action-item" onclick={copyScript}>
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z" />
        </svg>
        {copied ? 'Copied!' : 'Copy Script'}
      </button>
      
      <button class="action-item" onclick={downloadScript}>
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z" />
        </svg>
        {saved ? 'Saved!' : 'Download'}
      </button>
      
      <button class="action-item cancel" onclick={() => showActions = false}>
        Cancel
      </button>
    </div>
    
    <div class="action-overlay" onclick={() => showActions = false}></div>
  {/if}
</div>

<style>
  .mobile-editor {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    position: relative;
  }

  /* Theme Variables */
  .dark {
    --bg-primary: #0a0e1a;
    --bg-secondary: #141925;
    --bg-tertiary: #1e2433;
    --text-primary: #e4e8f1;
    --text-secondary: #9ca3af;
    --text-muted: #6b7280;
    --border: #2a3142;
    --accent: #3b82f6;
    --accent-hover: #2563eb;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --line-active: #1e293b;
  }

  .light {
    --bg-primary: #ffffff;
    --bg-secondary: #f9fafb;
    --bg-tertiary: #f3f4f6;
    --text-primary: #111827;
    --text-secondary: #6b7280;
    --text-muted: #9ca3af;
    --border: #e5e7eb;
    --accent: #3b82f6;
    --accent-hover: #2563eb;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --line-active: #f3f4f6;
  }

  /* Header */
  .editor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 10;
    backdrop-filter: blur(10px);
  }

  .header-left, .header-right {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .editor-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .icon-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }

  .icon-btn:active {
    background: var(--bg-tertiary);
    transform: scale(0.95);
  }

  .icon-btn svg {
    width: 24px;
    height: 24px;
  }

  /* Status Bar */
  .status-bar {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.5rem 1rem;
    background: var(--bg-tertiary);
    border-bottom: 1px solid var(--border);
    font-size: 0.875rem;
  }

  .status-item {
    color: var(--text-muted);
  }

  .flex-1 {
    flex: 1;
  }

  .status-warning {
    color: var(--warning);
    font-weight: 500;
  }

  .status-ready {
    color: var(--success);
    font-weight: 500;
  }

  /* Editor Container */
  .editor-container {
    flex: 1;
    display: flex;
    overflow: auto;
    background: var(--bg-primary);
  }

  .line-numbers {
    display: flex;
    flex-direction: column;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border);
    padding: 1rem 0;
    user-select: none;
    flex-shrink: 0;
  }

  .line-number {
    padding: 0 0.75rem;
    min-width: 3rem;
    text-align: right;
    color: var(--text-muted);
    font-size: 0.875rem;
    line-height: 1.5rem;
    font-family: "SF Mono", Monaco, monospace;
  }

  .line-number.active {
    background: var(--line-active);
    color: var(--text-secondary);
    font-weight: 600;
  }

  textarea {
    flex: 1;
    padding: 1rem;
    background: transparent;
    border: none;
    color: var(--text-primary);
    font-family: "SF Mono", Monaco, "Courier New", monospace;
    line-height: 1.5rem;
    resize: none;
    outline: none;
    -webkit-text-size-adjust: none;
    min-height: 50vh;
  }

  textarea::placeholder {
    color: var(--text-muted);
    opacity: 0.5;
  }

  textarea:disabled {
    opacity: 0.7;
  }

  /* Quick Insert Bar */
  .quick-insert-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border);
  }

  .quick-btn {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.5rem 0.75rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-secondary);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }

  .quick-btn:active {
    background: var(--accent);
    color: white;
    transform: scale(0.95);
  }

  .quick-btn svg {
    width: 18px;
    height: 18px;
  }

  .quick-actions {
    display: flex;
    gap: 0.25rem;
    margin-left: auto;
  }

  /* Launch Button */
  .launch-button {
    position: sticky;
    bottom: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    width: 100%;
    padding: 1.125rem;
    background: var(--accent);
    color: white;
    border: none;
    font-size: 1.125rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }

  .launch-button:disabled {
    background: var(--bg-tertiary);
    color: var(--text-muted);
    cursor: not-allowed;
  }

  .launch-button.ready:not(:disabled) {
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%);
  }

  .launch-button.ready:active:not(:disabled) {
    transform: scale(0.98);
  }

  .launch-button.launching {
    background: var(--warning);
  }

  .launch-button svg {
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

  /* Quick Insert Panel */
  .quick-insert-panel {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border);
    border-radius: 20px 20px 0 0;
    padding: 1rem;
    padding-bottom: calc(1rem + env(safe-area-inset-bottom));
    z-index: 100;
    box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.2);
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }

  .panel-header h3 {
    margin: 0;
    font-size: 1.125rem;
    color: var(--text-primary);
  }

  .close-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: var(--bg-tertiary);
    border: none;
    border-radius: 50%;
    color: var(--text-secondary);
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }

  .close-btn:active {
    transform: scale(0.9);
  }

  .close-btn svg {
    width: 20px;
    height: 20px;
  }

  .snippet-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.5rem;
    max-height: 40vh;
    overflow-y: auto;
  }

  .snippet-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border);
    border-radius: 10px;
    color: var(--text-primary);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }

  .snippet-btn:active {
    background: var(--accent);
    color: white;
    transform: scale(0.95);
  }

  .snippet-icon {
    font-size: 1.25rem;
  }

  /* Action Sheet */
  .action-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 90;
  }

  .action-sheet {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--bg-secondary);
    border-radius: 20px 20px 0 0;
    padding: 1rem;
    padding-bottom: calc(1rem + env(safe-area-inset-bottom));
    z-index: 100;
    box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.2);
  }

  .action-item {
    display: flex;
    align-items: center;
    gap: 1rem;
    width: 100%;
    padding: 1rem;
    background: var(--bg-tertiary);
    border: none;
    border-radius: 12px;
    color: var(--text-primary);
    font-size: 1rem;
    font-weight: 500;
    margin-bottom: 0.5rem;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }

  .action-item:active {
    transform: scale(0.98);
    background: var(--accent);
    color: white;
  }

  .action-item.cancel {
    background: transparent;
    color: var(--text-secondary);
    margin-top: 0.5rem;
    margin-bottom: 0;
  }

  .action-item svg {
    width: 24px;
    height: 24px;
  }
</style>