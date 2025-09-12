<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  const dispatch = createEventDispatcher<{
    settingsChanged: {
      excludePatterns: string[];
      includePatterns: string[];
      noGitignore: boolean;
    };
  }>();

  export let excludePatterns: string[] = ['*.log', '*.tmp', '__pycache__/'];
  export let includePatterns: string[] = [];
  export let noGitignore = false;

  // UI state
  let currentExcludePattern = '';
  let currentIncludePattern = '';

  function addExcludePattern(): void {
    if (currentExcludePattern.trim() && excludePatterns.indexOf(currentExcludePattern.trim()) === -1) {
      excludePatterns = [...excludePatterns, currentExcludePattern.trim()];
      currentExcludePattern = '';
      dispatchChange();
    }
  }

  function removeExcludePattern(index: number): void {
    excludePatterns = excludePatterns.filter((_, i) => i !== index);
    dispatchChange();
  }

  function addIncludePattern(): void {
    if (currentIncludePattern.trim() && includePatterns.indexOf(currentIncludePattern.trim()) === -1) {
      includePatterns = [...includePatterns, currentIncludePattern.trim()];
      currentIncludePattern = '';
      dispatchChange();
    }
  }

  function removeIncludePattern(index: number): void {
    includePatterns = includePatterns.filter((_, i) => i !== index);
    dispatchChange();
  }

  function handleGitignoreChange(): void {
    dispatchChange();
  }

  function dispatchChange(): void {
    dispatch('settingsChanged', {
      excludePatterns,
      includePatterns,
      noGitignore
    });
  }

  function handleKeyPress(event: KeyboardEvent, action: () => void): void {
    if (event.key === 'Enter') {
      event.preventDefault();
      action();
    }
  }

  function addDefaultExcludePatterns(): void {
    const defaults = ['node_modules/', '.git/', 'dist/', 'build/', '*.log', '*.tmp'];
    const newPatterns = defaults.filter(pattern => excludePatterns.indexOf(pattern) === -1);
    if (newPatterns.length > 0) {
      excludePatterns = [...excludePatterns, ...newPatterns];
      dispatchChange();
    }
  }

  function addDefaultIncludePatterns(): void {
    const defaults = ['*.py', '*.js', '*.ts', '*.sh', '*.md'];
    const newPatterns = defaults.filter(pattern => includePatterns.indexOf(pattern) === -1);
    if (newPatterns.length > 0) {
      includePatterns = [...includePatterns, ...newPatterns];
      dispatchChange();
    }
  }

  function clearAllExcludePatterns(): void {
    excludePatterns = [];
    dispatchChange();
  }

  function clearAllIncludePatterns(): void {
    includePatterns = [];
    dispatchChange();
  }
</script>

<div class="sync-settings" data-testid="sync-settings">
    <!-- Gitignore Option -->
    <div class="setting-section">
      <div class="setting-row">
        <label class="checkbox-label">
          <input 
            type="checkbox" 
            bind:checked={noGitignore} 
            on:change={handleGitignoreChange}
          />
          <span class="checkbox-text">Disable .gitignore</span>
        </label>
        <div class="setting-help">
          <svg class="info-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11,9H13V7H11M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M11,17H13V11H11V17Z"/>
          </svg>
          By default, patterns from .gitignore are excluded from sync
        </div>
      </div>
    </div>

    <!-- Exclude Patterns -->
    <div class="setting-section">
      <div class="section-header">
        <h4>Exclude Patterns</h4>
        <div class="section-actions">
          <button type="button" class="action-btn small" on:click={addDefaultExcludePatterns}>
            <svg class="action-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/>
            </svg>
            Add Defaults
          </button>
          {#if excludePatterns.length > 0}
            <button type="button" class="action-btn small danger" on:click={clearAllExcludePatterns}>
              <svg class="action-icon" viewBox="0 0 24 24" fill="currentColor">
                <path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z"/>
              </svg>
              Clear All
            </button>
          {/if}
        </div>
      </div>
      
      <div class="pattern-input-row">
        <input
          type="text"
          bind:value={currentExcludePattern}
          placeholder="*.log, node_modules/, __pycache__/"
          class="pattern-input"
          on:keypress={(e) => handleKeyPress(e, addExcludePattern)}
        />
        <button 
          type="button" 
          class="add-btn" 
          on:click={addExcludePattern}
          disabled={!currentExcludePattern.trim()}
        >
          <svg class="add-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/>
          </svg>
          Add
        </button>
      </div>
      
      <div class="pattern-list">
        {#each excludePatterns as pattern, index}
          <span class="pattern-tag exclude">
            <svg class="pattern-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z"/>
            </svg>
            <span class="pattern-text">{pattern}</span>
            <button
              type="button"
              class="remove-pattern"
              on:click={() => removeExcludePattern(index)}
              title="Remove pattern"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
              </svg>
            </button>
          </span>
        {/each}
        
        {#if excludePatterns.length === 0}
          <div class="empty-patterns">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z"/>
            </svg>
            No exclude patterns - all files will be synced
          </div>
        {/if}
      </div>
    </div>

    <!-- Include Patterns -->
    <div class="setting-section">
      <div class="section-header">
        <h4>Include Patterns <span class="optional">(override .gitignore)</span></h4>
        <div class="section-actions">
          <button type="button" class="action-btn small" on:click={addDefaultIncludePatterns}>
            <svg class="action-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/>
            </svg>
            Add Common
          </button>
          {#if includePatterns.length > 0}
            <button type="button" class="action-btn small danger" on:click={clearAllIncludePatterns}>
              <svg class="action-icon" viewBox="0 0 24 24" fill="currentColor">
                <path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z"/>
              </svg>
              Clear All
            </button>
          {/if}
        </div>
      </div>
      
      <div class="pattern-input-row">
        <input
          type="text"
          bind:value={currentIncludePattern}
          placeholder="data/*.csv, models/*.pkl, config.yaml"
          class="pattern-input"
          on:keypress={(e) => handleKeyPress(e, addIncludePattern)}
        />
        <button 
          type="button" 
          class="add-btn" 
          on:click={addIncludePattern}
          disabled={!currentIncludePattern.trim()}
        >
          <svg class="add-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/>
          </svg>
          Add
        </button>
      </div>
      
      <div class="pattern-list">
        {#each includePatterns as pattern, index}
          <span class="pattern-tag include">
            <svg class="pattern-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M17,9L12,14L7,9L8.41,7.59L12,11.17L15.59,7.59L17,9Z"/>
            </svg>
            <span class="pattern-text">{pattern}</span>
            <button
              type="button"
              class="remove-pattern"
              on:click={() => removeIncludePattern(index)}
              title="Remove pattern"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
              </svg>
            </button>
          </span>
        {/each}
        
        {#if includePatterns.length === 0}
          <div class="empty-patterns">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M17,9L12,14L7,9L8.41,7.59L12,11.17L15.59,7.59L17,9Z"/>
            </svg>
            No include patterns - rely on .gitignore and exclude patterns
          </div>
        {/if}
      </div>
    </div>

    <!-- Pattern Help -->
    <div class="pattern-help">
      <details class="help-details">
        <summary class="help-summary">
          <svg class="help-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11,18H13V16H11V18M12,6A4,4 0 0,0 8,10H10A2,2 0 0,1 12,8A2,2 0 0,1 14,10C14,12 11,11.75 11,15H13C13,12.75 16,12.5 16,10A4,4 0 0,0 12,6M5,3H19A2,2 0 0,1 21,5V19A2,2 0 0,1 19,21H5A2,2 0 0,1 3,19V5A2,2 0 0,1 5,3Z"/>
          </svg>
          Pattern Examples & Tips
        </summary>
        <div class="help-content">
          <div class="help-section">
            <h5>Common Patterns:</h5>
            <ul>
              <li><code>*.log</code> - All log files</li>
              <li><code>node_modules/</code> - Node.js dependencies</li>
              <li><code>**/*.tmp</code> - All temp files recursively</li>
              <li><code>data/*.csv</code> - CSV files in data directory</li>
            </ul>
          </div>
          <div class="help-section">
            <h5>Wildcards:</h5>
            <ul>
              <li><code>*</code> - Matches any characters in filename</li>
              <li><code>**</code> - Matches directories recursively</li>
              <li><code>?</code> - Matches single character</li>
              <li><code>[abc]</code> - Matches any character in brackets</li>
            </ul>
          </div>
        </div>
      </details>
    </div>
</div>

<style>
  .sync-settings {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    padding: 0;
  }



  .setting-section {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    padding: 1.5rem;
    background: var(--color-surface, #ffffff);
    border: 1px solid var(--color-border, #e5e7eb);
    border-radius: 12px;
    transition: all 0.2s ease;
  }

  .setting-section:hover {
    border-color: rgba(52, 152, 219, 0.3);
    box-shadow: 0 2px 8px rgba(52, 152, 219, 0.08);
  }

  .setting-row {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    color: var(--color-text-primary, #212529);
    padding: 0.75rem;
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .checkbox-label:hover {
    background: var(--color-surface-hover, #f8f9fa);
  }

  .checkbox-label input[type="checkbox"] {
    margin: 0;
    cursor: pointer;
    width: 18px;
    height: 18px;
    accent-color: var(--color-accent, #3498db);
  }

  .checkbox-text {
    flex: 1;
  }

  .setting-help {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    font-size: 0.85rem;
    color: var(--color-text-secondary, #6c757d);
    line-height: 1.5;
    margin-left: 2.25rem;
    padding: 0.75rem 1rem;
    background: rgba(52, 152, 219, 0.05);
    border-radius: 8px;
    border-left: 3px solid var(--color-accent, #3498db);
  }

  .info-icon {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
    margin-top: 0.1rem;
    color: var(--color-accent, #3498db);
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
  }

  .section-header h4 {
    margin: 0;
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--color-text-primary, #212529);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .section-header h4::before {
    content: '';
    width: 6px;
    height: 6px;
    background: var(--color-accent, #3498db);
    border-radius: 50%;
  }

  .optional {
    font-size: 0.85rem;
    font-weight: 400;
    color: var(--color-text-secondary, #6c757d);
    background: rgba(108, 117, 125, 0.1);
    padding: 0.25rem 0.5rem;
    border-radius: 12px;
    margin-left: 0.5rem;
  }

  .section-actions {
    display: flex;
    gap: 0.5rem;
  }

  .action-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    font-size: 0.85rem;
    font-weight: 600;
    border: 1.5px solid var(--color-border, #e5e7eb);
    border-radius: 8px;
    background: var(--color-surface, #ffffff);
    color: var(--color-text-primary, #212529);
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
  }

  .action-btn::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.4), transparent);
    transition: left 0.5s;
  }

  .action-btn:hover::before {
    left: 100%;
  }

  .action-btn:hover {
    border-color: var(--color-accent, #3498db);
    background: var(--color-accent-alpha, rgba(52, 152, 219, 0.05));
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(52, 152, 219, 0.2);
  }

  .action-btn.danger {
    color: var(--color-error, #dc3545);
    border-color: rgba(220, 53, 69, 0.3);
  }

  .action-btn.danger:hover {
    background: rgba(220, 53, 69, 0.05);
    border-color: var(--color-error, #dc3545);
    box-shadow: 0 4px 12px rgba(220, 53, 69, 0.2);
  }

  .action-icon {
    width: 14px;
    height: 14px;
  }

  .pattern-input-row {
    display: flex;
    gap: 0.5rem;
    align-items: stretch;
  }

  .pattern-input {
    flex: 1;
    padding: 1rem;
    border: 2px solid var(--color-border, #e5e7eb);
    border-radius: 12px;
    background: var(--color-surface, #ffffff);
    color: var(--color-text-primary, #212529);
    font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', 'Consolas', 'Courier New', monospace;
    font-size: 0.9rem;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    position: relative;
  }

  .pattern-input:focus {
    outline: none;
    border-color: var(--color-accent, #3498db);
    box-shadow: 0 0 0 4px rgba(52, 152, 219, 0.15), 0 4px 12px rgba(52, 152, 219, 0.1);
    transform: translateY(-1px);
  }

  .pattern-input::placeholder {
    color: var(--color-text-secondary, #6c757d);
    opacity: 0.7;
  }

  .add-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 1rem 1.25rem;
    background: linear-gradient(135deg, var(--color-accent, #3498db) 0%, #667eea 100%);
    color: white;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 600;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    white-space: nowrap;
    position: relative;
    overflow: hidden;
  }

  .add-btn::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(135deg, transparent 30%, rgba(255, 255, 255, 0.2) 50%, transparent 70%);
    transform: translateX(-100%);
    transition: transform 0.6s;
  }

  .add-btn:hover::before {
    transform: translateX(100%);
  }

  .add-btn:hover:not(:disabled) {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 0 6px 20px rgba(52, 152, 219, 0.4);
  }

  .add-btn:active {
    transform: translateY(0) scale(0.98);
    transition: transform 0.1s;
  }

  .add-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none;
    background: #9ca3af;
  }

  .add-btn:disabled::before {
    display: none;
  }

  .add-icon {
    width: 16px;
    height: 16px;
  }

  .pattern-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    min-height: 2.5rem;
    align-items: flex-start;
    align-content: flex-start;
  }

  .pattern-tag {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    border-radius: 16px;
    font-size: 0.85rem;
    font-weight: 600;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    border: 2px solid;
    position: relative;
    overflow: hidden;
    cursor: default;
  }

  .pattern-tag::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(45deg, transparent 30%, rgba(255, 255, 255, 0.3) 50%, transparent 70%);
    opacity: 0;
    transition: opacity 0.3s;
  }

  .pattern-tag:hover::before {
    opacity: 1;
  }

  .pattern-tag:hover {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  .pattern-tag.exclude {
    background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
    border-color: #fca5a5;
    color: #dc2626;
  }

  .pattern-tag.exclude:hover {
    box-shadow: 0 4px 12px rgba(220, 38, 38, 0.25);
  }

  .pattern-tag.include {
    background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
    border-color: #86efac;
    color: #16a34a;
  }

  .pattern-tag.include:hover {
    box-shadow: 0 4px 12px rgba(22, 163, 74, 0.25);
  }

  .pattern-icon {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  .pattern-text {
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 0.8rem;
  }

  .remove-pattern {
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid currentColor;
    color: inherit;
    cursor: pointer;
    padding: 0;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    opacity: 0.8;
    position: relative;
    z-index: 1;
  }

  .remove-pattern:hover {
    opacity: 1;
    background: currentColor;
    color: white;
    transform: scale(1.2) rotate(90deg);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  }

  .remove-pattern:active {
    transform: scale(1.1) rotate(90deg);
  }

  .remove-pattern svg {
    width: 12px;
    height: 12px;
    transition: transform 0.2s;
  }

  .remove-pattern:hover svg {
    transform: rotate(0deg);
  }

  .empty-patterns {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1.5rem;
    background: linear-gradient(135deg, var(--color-surface-hover, #f8f9fa) 0%, #f1f3f4 100%);
    border: 2px dashed var(--color-border, #e5e7eb);
    border-radius: 12px;
    color: var(--color-text-secondary, #6c757d);
    font-size: 0.9rem;
    font-style: italic;
    justify-content: center;
    text-align: center;
    transition: all 0.3s ease;
  }

  .empty-patterns:hover {
    border-color: rgba(52, 152, 219, 0.3);
    background: linear-gradient(135deg, rgba(52, 152, 219, 0.02) 0%, rgba(52, 152, 219, 0.05) 100%);
  }

  .empty-icon {
    width: 16px;
    height: 16px;
    opacity: 0.5;
  }

  .pattern-help {
    border-top: 2px solid var(--color-border, #e5e7eb);
    padding-top: 1.5rem;
    margin-top: 0.5rem;
  }

  .help-details {
    border: 1.5px solid var(--color-border, #e5e7eb);
    border-radius: 12px;
    overflow: hidden;
    transition: all 0.3s ease;
    background: var(--color-surface, #ffffff);
  }

  .help-details[open] {
    border-color: var(--color-accent, #3498db);
    box-shadow: 0 4px 12px rgba(52, 152, 219, 0.1);
  }

  .help-summary {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem 1.25rem;
    background: linear-gradient(135deg, var(--color-surface-hover, #f8f9fa) 0%, #f1f3f4 100%);
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--color-text-primary, #212529);
    list-style: none;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
  }

  .help-summary::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(52, 152, 219, 0.1), transparent);
    transition: left 0.5s;
  }

  .help-summary:hover::before {
    left: 100%;
  }

  .help-summary:hover {
    background: linear-gradient(135deg, rgba(52, 152, 219, 0.05) 0%, rgba(52, 152, 219, 0.08) 100%);
    transform: translateY(-1px);
  }

  .help-summary::-webkit-details-marker {
    display: none;
  }

  .help-icon {
    width: 16px;
    height: 16px;
    color: #6b7280;
  }

  .help-content {
    padding: 1.25rem;
    background: var(--color-surface, #ffffff);
    border-top: 1px solid var(--color-border, #e5e7eb);
    font-size: 0.9rem;
    color: var(--color-text-primary, #212529);
    line-height: 1.6;
  }

  .help-section {
    margin-bottom: 1rem;
  }

  .help-section:last-child {
    margin-bottom: 0;
  }

  .help-section h5 {
    margin: 0 0 0.5rem 0;
    font-size: 0.9rem;
    font-weight: 600;
    color: #374151;
  }

  .help-section ul {
    margin: 0;
    padding-left: 1.25rem;
    list-style-type: disc;
  }

  .help-section li {
    margin-bottom: 0.25rem;
  }

  .help-section code {
    background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
    padding: 0.25rem 0.5rem;
    border-radius: 6px;
    border: 1px solid rgba(30, 64, 175, 0.1);
    font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', 'Consolas', 'Courier New', monospace;
    font-size: 0.85rem;
    color: var(--color-accent, #3498db);
    font-weight: 600;
  }

  /* Mobile responsive */
  @media (max-width: 768px) {
    .sync-settings {
      overflow: visible;
      height: auto;
      min-height: auto;
      max-height: none;
      margin-bottom: 1rem;
      background: white;
      border-radius: 12px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }

    .setting-section {
      padding: 1.25rem;
    }

    .section-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.75rem;
    }

    .section-actions {
      align-self: stretch;
      justify-content: space-between;
    }

    .pattern-input-row {
      flex-direction: column;
      gap: 0.75rem;
    }

    .add-btn {
      align-self: stretch;
      justify-content: center;
    }

    .pattern-tag {
      font-size: 0.8rem;
      padding: 0.375rem 0.625rem;
    }

    .help-content {
      padding: 0.75rem;
    }

    .setting-help {
      margin-left: 1.125rem;
    }
  }

</style>