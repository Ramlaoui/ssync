<script lang="ts">
  import { run } from 'svelte/legacy';

  import { createEventDispatcher } from 'svelte';
  import CodeMirrorEditor from '../CodeMirrorEditor.svelte';
  
  const dispatch = createEventDispatcher<{
    launch: void;
    scriptChanged: { content: string };
    openHistory: void;
  }>();
  
  interface Props {
    script?: string;
    launching?: boolean;
    canLaunch?: boolean;
    validationMessage?: string;
  }

  let {
    script = '',
    launching = false,
    canLaunch = false,
    validationMessage = ''
  }: Props = $props();
  
  let editableScript = $state(script);
  let vimMode = $state(true);
  let codeMirrorEditor: CodeMirrorEditor = $state();
  
  run(() => {
    editableScript = script;
  });
  
  function handleScriptChange(event: CustomEvent<{ content: string }>) {
    editableScript = event.detail.content;
    dispatch('scriptChanged', { content: editableScript });
  }
  
  function handleEscape() {
    // Send ESC key to CodeMirror editor
    if (codeMirrorEditor) {
      const cm = (codeMirrorEditor as any).getEditor?.();
      if (cm) {
        cm.triggerOnKeyDown({ type: 'keydown', keyCode: 27 });
      }
    }
  }
  
  function toggleVimMode() {
    vimMode = !vimMode;
  }
  
  function handleLaunch() {
    if (canLaunch && !launching) {
      dispatch('launch');
    }
  }
  
  function handleHistory() {
    dispatch('openHistory');
  }
</script>

<div class="mobile-editor">
  <div class="editor-header">
    <h3>Launch Script</h3>
    <div class="header-buttons">
      <button 
        class="vim-toggle"
        class:active={vimMode}
        onclick={toggleVimMode}
        title="Toggle Vim Mode"
      >
        VIM
      </button>
      <button class="history-button" onclick={handleHistory}>
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M13 3C8.03 3 4 7.03 4 12H1L5 16L9 12H6C6 8.13 9.13 5 13 5C16.87 5 20 8.13 20 12C20 15.87 16.87 19 13 19C11.07 19 9.32 18.21 8.06 16.94L6.64 18.36C8.27 20 10.5 21 13 21C17.97 21 22 16.97 22 12C22 7.03 17.97 3 13 3M12 8V13L16.28 15.54L17 14.33L13.5 12.25V8H12Z" />
        </svg>
        History
      </button>
    </div>
  </div>
  
  <!-- Validation Message -->
  {#if !canLaunch && validationMessage}
    <div class="validation-message">
      {validationMessage}
    </div>
  {/if}
  
  <!-- Script Content -->
  <div class="script-container">
    <CodeMirrorEditor
      bind:this={codeMirrorEditor}
      value={script}
      on:change={handleScriptChange}
      vimMode={vimMode}
      disabled={false}
    />
  </div>
  
  <!-- Vim Mode Helper -->
  {#if vimMode}
    <div class="vim-helper">
      <button class="esc-button" onclick={handleEscape}>
        ESC
      </button>
      <span class="vim-hint">Vim mode active • Tap ESC button for escape key</span>
    </div>
  {/if}
  
  <!-- Action Buttons -->
  <div class="action-buttons">
    <button 
      class="launch-button" 
      onclick={handleLaunch}
      disabled={!canLaunch || launching}
    >
      {#if launching}
        <span class="spinner"></span>
        Launching...
      {:else}
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M2,21L23,12L2,3V10L17,12L2,14V21Z" />
        </svg>
        Launch Job
      {/if}
    </button>
  </div>
</div>

<style>
  .mobile-editor {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: white;
  }
  
  /* Header */
  .editor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    background: white;
    border-bottom: 1px solid var(--border);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  }
  
  .editor-header h3 {
    margin: 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--foreground);
  }
  
  .header-buttons {
    display: flex;
    gap: 0.5rem;
  }
  
  .vim-toggle,
  .history-button {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 0.875rem;
    background: white;
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--foreground);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .vim-toggle.active {
    background: var(--accent);
    border-color: var(--accent);
    color: white;
  }
  
  .history-button:active,
  .vim-toggle:active:not(.active) {
    background: var(--secondary);
    transform: scale(0.98);
  }
  
  .history-button svg {
    width: 18px;
    height: 18px;
  }
  
  /* Validation Message */
  .validation-message {
    margin: 0.75rem;
    padding: 0.75rem;
    background: var(--error-bg);
    border-left: 3px solid var(--error);
    border-radius: 4px;
    color: var(--error);
    font-size: 0.875rem;
  }
  
  /* Script Container */
  .script-container {
    flex: 1;
    overflow: hidden;
    position: relative;
    background: white;
  }
  
  /* Override CodeMirror styles for mobile */
  .script-container :global(.CodeMirror) {
    font-size: 0.9rem !important;
    line-height: 1.5 !important;
    height: 100% !important;
    background: white !important;
  }
  
  .script-container :global(.CodeMirror-gutters) {
    background: var(--secondary) !important;
    border-right: 1px solid var(--border) !important;
  }
  
  .script-container :global(.CodeMirror-linenumber) {
    color: var(--muted-foreground) !important;
    padding: 0 8px !important;
  }
  
  .script-container :global(.CodeMirror-lines) {
    padding: 8px !important;
  }
  
  .script-container :global(.CodeMirror pre.CodeMirror-line) {
    padding: 0 8px !important;
  }
  
  /* Vim Helper */
  .vim-helper {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 0.75rem;
    background: var(--secondary);
    border-top: 1px solid var(--border);
  }
  
  .esc-button {
    padding: 0.5rem 1rem;
    background: var(--accent);
    border: none;
    border-radius: 4px;
    color: white;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }
  
  .esc-button:active {
    opacity: 0.9;
    transform: scale(0.98);
  }
  
  .vim-hint {
    color: var(--muted-foreground);
    font-size: 0.75rem;
  }
  
  /* Action Buttons */
  .action-buttons {
    display: flex;
    gap: 0.75rem;
    padding: 0.875rem;
    background: var(--secondary);
    border-top: 1px solid var(--border);
  }
  
  .launch-button {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.875rem;
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent) 100%);
    border: none;
    border-radius: 6px;
    color: white;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }
  
  .launch-button:active:not(:disabled) {
    opacity: 0.9;
    transform: scale(0.98);
  }
  
  .launch-button:disabled {
    background: var(--border);
    color: var(--muted-foreground);
    cursor: not-allowed;
  }
  
  .launch-button svg {
    width: 18px;
    height: 18px;
  }
  
  /* Spinner */
  .spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  /* Responsive adjustments */
  @media (max-width: 480px) {
    .editor-header {
      padding: 0.875rem;
    }
    
    .editor-header h3 {
      font-size: 1rem;
    }
    
    .vim-toggle,
    .history-button {
      padding: 0.375rem 0.75rem;
      font-size: 0.8rem;
    }
    
    .script-container :global(.CodeMirror) {
      font-size: 0.875rem !important;
    }
    
    .action-buttons {
      padding: 0.75rem;
      gap: 0.5rem;
    }
    
    .launch-button {
      padding: 0.75rem;
      font-size: 0.875rem;
    }
    
    .esc-button {
      padding: 0.375rem 0.75rem;
      font-size: 0.8rem;
    }
  }
</style>