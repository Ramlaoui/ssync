<script lang="ts">
  import { run } from 'svelte/legacy';

  import { createEventDispatcher, onMount, tick } from "svelte";
  import CodeMirrorEditor from "./CodeMirrorEditor.svelte";
  import SimpleMobileEditor from "./mobile/SimpleMobileEditor.svelte";

  const dispatch = createEventDispatcher<{
    launch: void;
    scriptChanged: { content: string };
    openHistory: void;
  }>();

  interface Props {
    generatedScript?: string;
    launching?: boolean;
    loading?: boolean;
    validationDetails?: { isValid: boolean; missing: string[]; missingText: string };
  }

  let {
    generatedScript = "",
    launching = false,
    loading = false,
    validationDetails = { isValid: false, missing: [], missingText: 'Missing configuration' }
  }: Props = $props();
  
  // Editor preferences
  let vimModeEnabled = $state(true);

  let editableScript = $state("");
  let codeMirrorEditor: CodeMirrorEditor = $state();
  let hasUnsavedChanges = $state(false);
  let autoSaveTimeout: number | null = null;
  let lastSavedScript = $state("");
  let userHasEdited = $state(false);
  let showMobileMenu = $state(false);
  let isMobile = $state(false);

  // Initialize editable script when component mounts or generated script changes
  // Only update if user hasn't made manual edits (avoid overwriting user's edits)
  // Reset userHasEdited flag when script is programmatically changed
  run(() => {
    if (generatedScript !== lastSavedScript) {
      if (!userHasEdited || generatedScript === '') {
        editableScript = generatedScript;
        lastSavedScript = generatedScript;
        hasUnsavedChanges = false;
        userHasEdited = false; // Reset flag when script is externally updated
      }
    }
  });
  
  // Calculate line count for stats display
  let currentText = $derived(editableScript || generatedScript || "");
  let lineCount = $derived(Math.max(1, currentText.split("\n").length));

  function handleScriptChange(event: CustomEvent<{ content: string }>): void {
    const newContent = event.detail.content;
    // Only update if actually changed to prevent loops
    if (newContent !== editableScript) {
      editableScript = newContent;
      userHasEdited = true;
      hasUnsavedChanges = editableScript !== generatedScript;

      // Auto-save after 1 second of no changes
      if (autoSaveTimeout) {
        clearTimeout(autoSaveTimeout);
      }

      autoSaveTimeout = setTimeout(() => {
        saveChanges();
      }, 1000);
    }
  }

  function saveChanges(): void {
    if (editableScript !== generatedScript) {
      // Send the full script content, including #SBATCH directives
      // The parent component will handle the sync
      dispatch("scriptChanged", { content: editableScript });
      // Mark saved locally; parent will update the derived generatedScript
      lastSavedScript = editableScript;
      hasUnsavedChanges = false;
      userHasEdited = false;
    }

    if (autoSaveTimeout) {
      clearTimeout(autoSaveTimeout);
      autoSaveTimeout = null;
    }
  }

  function handleKeyDown(event: KeyboardEvent): void {
    // Ctrl+S or Cmd+S to save manually
    if ((event.ctrlKey || event.metaKey) && event.key === "s") {
      event.preventDefault();
      saveChanges();
    }

    // Cmd+Enter to launch job
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      if (!launching && !loading && validationDetails.isValid) {
        handleLaunch();
      }
    }
  }

  function resetScript(): void {
    editableScript = generatedScript;
    if (codeMirrorEditor) {
      codeMirrorEditor.setContent(generatedScript);
    }
    userHasEdited = false;
    hasUnsavedChanges = false;
    lastSavedScript = generatedScript;
    if (autoSaveTimeout) {
      clearTimeout(autoSaveTimeout);
      autoSaveTimeout = null;
    }
  }

  // Global keyboard shortcut handler
  function handleGlobalKeyDown(event: KeyboardEvent): void {
    // Cmd+Enter to launch job (global shortcut)
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      if (!launching && !loading && validationDetails.isValid) {
        handleLaunch();
      }
    }
  }

  // Clean up timeout on destroy
  onMount(() => {
    // Detect mobile device
    isMobile = window.matchMedia('(max-width: 768px)').matches ||
               /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) ||
               ('ontouchstart' in window);
    
    // Add global keyboard listener
    document.addEventListener('keydown', handleGlobalKeyDown);
    
    return () => {
      // Clean up all timers
      if (autoSaveTimeout) {
        clearTimeout(autoSaveTimeout);
        autoSaveTimeout = null;
      }
      
      // Remove event listener
      document.removeEventListener('keydown', handleGlobalKeyDown);
      
      // Clean up CodeMirror instance if it exists
      if (codeMirrorEditor) {
        // Save any pending changes before cleanup
        if (hasUnsavedChanges) {
          saveChanges();
        }
        // Note: CodeMirror component should handle its own cleanup
      }
    };
  });

  function copyScript(): void {
    navigator.clipboard
      .writeText(generatedScript)
      .then(() => {
        // Could add a toast notification here
      })
      .catch((err) => {
        // Failed to copy script
      });
  }

  function saveScript(): void {
    const blob = new Blob([generatedScript], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "slurm-job.sh";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function handleLaunch(): void {
    dispatch("launch");
  }

  function getScriptStats() {
    const lines = generatedScript.split("\n").length;
    const size = new Blob([generatedScript]).size;

    return {
      lines,
      size,
      formattedSize: formatFileSize(size),
    };
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} bytes`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  let stats = $derived(getScriptStats());

</script>

{#if isMobile}
  <SimpleMobileEditor
    script={editableScript}
    launching={launching}
    canLaunch={validationDetails.isValid}
    validationMessage={validationDetails.missingText}
    on:launch={handleLaunch}
    on:scriptChanged={handleScriptChange}
    on:openHistory={() => dispatch('openHistory')}
  />
{:else}
  <div class="script-preview">
  <div class="preview-header">
    <div class="header-content">
      <div class="header-title">
        <h3>Script Editor & Preview</h3>
        <div class="editor-status">
          {#if hasUnsavedChanges}
            <span class="status-indicator unsaved">
              <svg class="status-icon" viewBox="0 0 24 24" fill="currentColor">
                <path
                  d="M17,3H5C3.89,3 3,3.89 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V7L17,3M19,19H5V5H16V8H19V19Z"
                />
              </svg>
              Auto-saving...
            </span>
          {:else if lastSavedScript}
            <span class="status-indicator saved">
              <svg class="status-icon" viewBox="0 0 24 24" fill="currentColor">
                <path
                  d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M17,9L12,14L7,9L8.41,7.59L12,11.17L15.59,7.59L17,9Z"
                />
              </svg>
              Saved
            </span>
          {/if}
        </div>
      </div>

      <div class="preview-stats">
        <span class="stat-item">
          <svg class="stat-icon" viewBox="0 0 24 24" fill="currentColor">
            <path
              d="M14,17H7V15H14M17,13H7V11H17M17,9H7V7H17M19,3H5C3.89,3 3,3.89 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5C21,3.89 20.1,3 19,3Z"
            />
          </svg>
          {stats.lines} lines
        </span>

        <span class="stat-item">
          <svg class="stat-icon" viewBox="0 0 24 24" fill="currentColor">
            <path
              d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"
            />
          </svg>
          {stats.formattedSize}
        </span>

        {#if !validationDetails.isValid}
          <span class="stat-item warning" title={validationDetails.missingText}>
            <svg class="stat-icon" viewBox="0 0 24 24" fill="currentColor">
              <path
                d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z"
              />
            </svg>
            Missing config
          </span>
        {:else}
          <span class="stat-item success" title="All required configuration is complete">
            <svg class="stat-icon" viewBox="0 0 24 24" fill="currentColor">
              <path
                d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M17,9L12,14L7,9L8.41,7.59L12,11.17L15.59,7.59L17,9Z"
              />
            </svg>
            Ready to launch
          </span>
        {/if}
      </div>
    </div>
  </div>

  <div class="preview-content">
    {#if generatedScript || editableScript}
      <div class="script-editor-container">
        <CodeMirrorEditor
          bind:this={codeMirrorEditor}
          bind:value={editableScript}
          vimMode={vimModeEnabled}
          on:change={handleScriptChange}
          on:toggleVim={() => vimModeEnabled = !vimModeEnabled}
          placeholder="#!/bin/bash&#10;#SBATCH --job-name=my-job&#10;#SBATCH --ntasks=1&#10;#SBATCH --mem=4G&#10;&#10;#LOGIN_SETUP_BEGIN&#10;conda activate ml-env&#10;pip install torch transformers&#10;#LOGIN_SETUP_END&#10;&#10;echo 'Starting training on compute node...'&#10;python train_model.py"
          disabled={launching}
        />
      </div>
    {:else}
      <div class="empty-preview">
        <svg class="empty-icon" viewBox="0 0 24 24" fill="currentColor">
          <path
            d="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z"
          />
        </svg>
        <div class="empty-text">
          <h4>Script editor ready</h4>
          <p>
            Configure your job settings to generate a SLURM script, or start
            typing to create your own
          </p>
        </div>
      </div>
    {/if}
  </div>

  {#if isMobile}
    <!-- Mobile Floating Action Button -->
    <div class="mobile-fab-container">
      {#if showMobileMenu}
        <div class="fab-menu">
          <button
            class="fab-item"
            onclick={() => { dispatch('openHistory'); showMobileMenu = false; }}
            title="Script History"
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M16.2,16.2L11,13V7H12.5V12.2L17,14.9L16.2,16.2Z" />
            </svg>
            <span>History</span>
          </button>
          
          <button
            class="fab-item"
            onclick={() => { copyScript(); showMobileMenu = false; }}
            disabled={!editableScript && !generatedScript}
            title="Copy Script"
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z" />
            </svg>
            <span>Copy</span>
          </button>
          
          <button
            class="fab-item"
            onclick={() => { saveScript(); showMobileMenu = false; }}
            disabled={!editableScript && !generatedScript}
            title="Download Script"
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z" />
            </svg>
            <span>Download</span>
          </button>
        </div>
        
        <button
          class="fab-toggle fab-close"
          onclick={() => showMobileMenu = false}
          aria-label="Close menu"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z" />
          </svg>
        </button>
      {:else}
        <button
          class="fab-toggle"
          onclick={() => showMobileMenu = true}
          aria-label="More options"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,16A2,2 0 0,1 14,18A2,2 0 0,1 12,20A2,2 0 0,1 10,18A2,2 0 0,1 12,16M12,10A2,2 0 0,1 14,12A2,2 0 0,1 12,14A2,2 0 0,1 10,12A2,2 0 0,1 12,10M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8A2,2 0 0,1 10,6A2,2 0 0,1 12,4Z" />
          </svg>
        </button>
      {/if}
    </div>
  {/if}

  <div class="preview-actions">
    <button
      type="button"
      class="action-btn secondary"
      onclick={() => dispatch('openHistory')}
      title="Browse script history and reuse previous scripts"
    >
      <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M16.2,16.2L11,13V7H12.5V12.2L17,14.9L16.2,16.2Z" />
      </svg>
      History
    </button>

    <button
      type="button"
      class="action-btn secondary"
      onclick={copyScript}
      disabled={!editableScript && !generatedScript}
      title="Copy script to clipboard"
    >
      <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
        <path
          d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z"
        />
      </svg>
      Copy
    </button>

    <button
      type="button"
      class="action-btn secondary"
      onclick={saveScript}
      disabled={!editableScript && !generatedScript}
      title="Download script as file"
    >
      <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
        <path
          d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"
        />
      </svg>
      Download
    </button>

    {#if hasUnsavedChanges}
      <button
        type="button"
        class="action-btn warning"
        onclick={saveChanges}
        title="Save changes manually"
      >
        <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
          <path
            d="M15,9H5V5H15M12,19A3,3 0 0,1 9,16A3,3 0 0,1 12,13A3,3 0 0,1 15,16A3,3 0 0,1 12,19M17,3H5C3.89,3 3,3.9 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V7L17,3Z"
          />
        </svg>
        Save Now
      </button>

      <button
        type="button"
        class="action-btn secondary"
        onclick={resetScript}
        title="Reset to original script"
      >
        <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
          <path
            d="M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z"
          />
        </svg>
        Reset
      </button>
    {/if}

    <button
      type="button"
      class="action-btn primary launch-btn"
      onclick={handleLaunch}
      disabled={launching || loading || !validationDetails.isValid}
      title={validationDetails.isValid
        ? "Launch the job"
        : validationDetails.missingText}
    >
      {#if launching}
        <svg
          class="btn-icon loading-spinner"
          viewBox="0 0 24 24"
          fill="currentColor"
        >
          <path d="M12,4V2A10,10 0 0,0 2,12H4A8,8 0 0,1 12,4Z" />
        </svg>
        Launching...
      {:else}
        <svg class="btn-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M8,5.14V19.14L19,12.14L8,5.14Z" />
        </svg>
        Launch Job
      {/if}
    </button>
  </div>
</div>
{/if}

<style>
  .script-preview {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: #1e1e2e;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
    height: 100%;
    position: relative;
  }

  .preview-header {
    background: linear-gradient(135deg, #2d3748 0%, #1a202c 100%);
    color: white;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    flex-shrink: 0;
  }

  .header-content {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
  }

  .header-title {
    display: flex;
    align-items: center;
    gap: 1rem;
    user-select: none;
    -webkit-user-select: none;
    -moz-user-select: none;
    -ms-user-select: none;
  }

  .preview-header h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: #f7fafc;
    user-select: none;
    -webkit-user-select: none;
    -moz-user-select: none;
    -ms-user-select: none;
  }

  .editor-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .status-indicator {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 500;
    animation: fadeIn 0.3s ease;
  }

  .status-indicator.saved {
    background: rgba(16, 185, 129, 0.15);
    color: #10b981;
    border: 1px solid rgba(16, 185, 129, 0.3);
  }

  .status-indicator.unsaved {
    background: rgba(245, 158, 11, 0.15);
    color: #f59e0b;
    border: 1px solid rgba(245, 158, 11, 0.3);
  }

  .status-icon {
    width: 12px;
    height: 12px;
    flex-shrink: 0;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(-4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .preview-stats {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }

  .stat-item {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.8rem;
    color: rgba(255, 255, 255, 0.8);
    background: rgba(255, 255, 255, 0.1);
    padding: 0.375rem 0.75rem;
    border-radius: 6px;
    backdrop-filter: blur(10px);
    transition: all 0.2s ease;
  }

  .stat-item.warning {
    background: rgba(245, 158, 11, 0.2);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.3);
  }

  .stat-item.success {
    background: rgba(16, 185, 129, 0.2);
    color: #10b981;
    border: 1px solid rgba(16, 185, 129, 0.3);
  }

  .stat-icon {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  .preview-content {
    flex: 1;
    overflow: hidden;
    background: #2d3748;
    min-height: 0;
    position: relative;
    display: flex;
    flex-direction: column;
  }

  .preview-content::-webkit-scrollbar {
    width: 8px;
  }

  .preview-content::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.05);
  }

  .preview-content::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 4px;
  }

  .preview-content::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.3);
  }

  /* CodeMirror Editor Styles */

  .script-editor-container {
    position: relative;
    display: flex;
    flex: 1;
    height: 100%;
    background: #2d3748;
  }

  .empty-preview {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    padding: 2rem;
    color: rgba(255, 255, 255, 0.6);
    text-align: center;
  }

  .empty-icon {
    width: 4rem;
    height: 4rem;
    color: rgba(255, 255, 255, 0.3);
    margin-bottom: 1rem;
  }

  .empty-text h4 {
    margin: 0 0 0.5rem 0;
    font-size: 1.1rem;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.8);
  }

  .empty-text p {
    margin: 0;
    font-size: 0.9rem;
    line-height: 1.4;
    color: rgba(255, 255, 255, 0.6);
  }

  .preview-actions {
    padding: 1rem 1.5rem;
    background: #1a202c;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    display: flex;
    gap: 0.75rem;
    align-items: center;
    flex-shrink: 0;
  }

  .action-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 1rem;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    min-width: 0;
    white-space: nowrap;
  }

  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
  }

  .action-btn.secondary {
    background: rgba(255, 255, 255, 0.1);
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.2);
  }

  .action-btn.secondary:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.2);
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  }

  .action-btn.primary {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    color: white;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
  }

  .action-btn.primary:hover:not(:disabled) {
    background: linear-gradient(135deg, #059669 0%, #047857 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(16, 185, 129, 0.4);
  }

  .action-btn.warning {
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    color: white;
    box-shadow: 0 2px 8px rgba(245, 158, 11, 0.3);
  }

  .action-btn.warning:hover:not(:disabled) {
    background: linear-gradient(135deg, #d97706 0%, #b45309 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(245, 158, 11, 0.4);
  }

  .launch-btn {
    flex: 1;
    justify-content: center;
    font-weight: 600;
    min-height: 44px;
    max-width: 200px;
  }

  .btn-icon {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }

  .loading-spinner {
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }

  /* Mobile responsive */
  @media (max-width: 768px) {
    .script-preview {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100%;
      border-radius: 0;
      margin: 0;
      background: #1a1f2e;
    }

    .preview-header {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      z-index: 15;
      padding: 1rem;
      padding-top: calc(1rem + env(safe-area-inset-top));
      background: linear-gradient(135deg, rgba(45, 52, 65, 0.98) 0%, rgba(26, 31, 46, 0.98) 100%);
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      backdrop-filter: blur(10px);
      box-shadow: 0 2px 15px rgba(0, 0, 0, 0.3);
    }

    .header-content {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.5rem;
    }

    .header-title {
      flex: 1;
    }

    .preview-header h3 {
      font-size: 1.1rem;
      font-weight: 700;
      margin: 0;
      letter-spacing: 0.5px;
    }

    .editor-status {
      display: none;
    }

    .preview-stats {
      display: flex;
      gap: 0.5rem;
      flex-shrink: 0;
    }

    .stat-item {
      font-size: 0.75rem;
      padding: 0.4rem 0.7rem;
      min-width: auto;
      border-radius: 20px;
      font-weight: 600;
      backdrop-filter: blur(10px);
    }

    .stat-item.warning,
    .stat-item.success {
      display: flex;
      animation: pulse 2s ease-in-out infinite;
    }
    
    @keyframes pulse {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.02); }
    }

    .stat-item:not(.warning):not(.success) {
      display: none;
    }

    .preview-content {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      min-height: 0;
      background: #1a1f2e;
      margin-top: 80px;
      padding-bottom: 80px;
    }

    .script-editor-container {
      flex: 1;
      display: flex;
      height: 100%;
      position: relative;
      background: transparent;
    }

    .empty-preview {
      padding: 2rem 1rem;
      text-align: center;
    }

    .empty-icon {
      width: 3rem;
      height: 3rem;
      margin-bottom: 0.75rem;
    }

    .empty-text h4 {
      font-size: 0.95rem;
      margin-bottom: 0.5rem;
    }

    .empty-text p {
      font-size: 0.8rem;
      line-height: 1.4;
    }

    .preview-actions {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      padding: 1rem;
      padding-bottom: calc(1rem + env(safe-area-inset-bottom));
      background: linear-gradient(180deg, rgba(26, 31, 46, 0.98) 0%, rgba(20, 25, 38, 1) 100%);
      border-top: 1px solid rgba(255, 255, 255, 0.15);
      display: flex;
      gap: 0.75rem;
      z-index: 20;
      backdrop-filter: blur(15px);
      box-shadow: 0 -4px 30px rgba(0, 0, 0, 0.4);
    }

    .action-btn {
      font-size: 0.95rem;
      padding: 0.875rem 1.25rem;
      min-height: 48px;
      flex: 1;
      border-radius: 12px;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      transition: all 0.2s ease;
    }

    .action-btn.secondary {
      display: none;
    }

    .action-btn.warning {
      flex: 0 0 auto;
      min-width: 80px;
      background: linear-gradient(135deg, rgba(245, 158, 11, 0.9) 0%, rgba(217, 119, 6, 0.9) 100%);
      border: 1px solid rgba(251, 191, 36, 0.3);
    }

    .launch-btn {
      flex: 1;
      font-weight: 700;
      font-size: 1rem;
      padding: 1rem 1.5rem;
      min-height: 52px;
      background: linear-gradient(135deg, #10b981 0%, #059669 100%);
      border: 2px solid rgba(16, 185, 129, 0.4);
      box-shadow: 0 3px 15px rgba(16, 185, 129, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.15);
      text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
      letter-spacing: 0.5px;
    }
    
    .launch-btn:active:not(:disabled) {
      transform: scale(0.98);
      box-shadow: 0 1px 5px rgba(16, 185, 129, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1);
    }

    .btn-icon {
      width: 14px;
      height: 14px;
    }
  }

  /* Mobile FAB Styles */
  .mobile-fab-container {
    position: fixed;
    bottom: 110px;
    right: 1rem;
    z-index: 30;
    display: flex;
    flex-direction: column-reverse;
    align-items: flex-end;
    gap: 0.75rem;
  }

  .fab-toggle {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    border: none;
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4), 0 2px 6px rgba(0, 0, 0, 0.2);
    cursor: pointer;
    transition: all 0.3s ease;
    -webkit-tap-highlight-color: transparent;
  }

  .fab-toggle:active {
    transform: scale(0.95);
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.4), 0 1px 4px rgba(0, 0, 0, 0.2);
  }

  .fab-toggle.fab-close {
    background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
    animation: rotateIn 0.3s ease;
  }

  .fab-toggle svg {
    width: 24px;
    height: 24px;
  }

  @keyframes rotateIn {
    from { transform: rotate(0deg); }
    to { transform: rotate(90deg); }
  }

  .fab-menu {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    animation: slideUp 0.3s ease;
  }

  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .fab-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: linear-gradient(135deg, rgba(26, 31, 46, 0.95) 0%, rgba(35, 41, 55, 0.95) 100%);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 28px;
    color: white;
    font-size: 0.875rem;
    font-weight: 600;
    white-space: nowrap;
    cursor: pointer;
    transition: all 0.2s ease;
    backdrop-filter: blur(10px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    min-width: 140px;
    justify-content: flex-start;
    -webkit-tap-highlight-color: transparent;
  }

  .fab-item:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .fab-item:not(:disabled):active {
    transform: scale(0.98);
    background: linear-gradient(135deg, rgba(35, 41, 55, 0.95) 0%, rgba(45, 52, 65, 0.95) 100%);
  }

  .fab-item svg {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }

  .fab-item span {
    flex: 1;
  }

  /* Small mobile adjustments */
  @media (max-width: 480px) {
    .preview-header {
      padding: 0.75rem;
    }

    .preview-header h3 {
      font-size: 0.85rem;
    }

    .stat-item {
      font-size: 0.65rem;
      padding: 0.2rem 0.4rem;
    }

    /* Small mobile specific styles handled by CodeMirror component */

    .preview-actions {
      padding: 0.625rem;
    }

    .launch-btn {
      font-size: 0.8rem;
      padding: 0.625rem 0.875rem;
      min-height: 40px;
    }
  }

</style>
