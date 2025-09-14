<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { Plus, X, FolderX, FileCheck, GitBranch, HelpCircle, Trash2, RotateCcw } from 'lucide-svelte';
  import Button from '../lib/components/ui/Button.svelte';
  import Input from '../lib/components/ui/Input.svelte';
  import Card from '../lib/components/ui/Card.svelte';

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
  let showHelp = false;

  // Preset patterns for quick adding
  const presetExcludePatterns = [
    { pattern: 'node_modules/', description: 'Node.js dependencies', category: 'Build' },
    { pattern: '.git/', description: 'Git repository data', category: 'VCS' },
    { pattern: 'dist/', description: 'Distribution/build folder', category: 'Build' },
    { pattern: 'build/', description: 'Build output folder', category: 'Build' },
    { pattern: '__pycache__/', description: 'Python bytecode cache', category: 'Python' },
    { pattern: '.venv/', description: 'Python virtual environment', category: 'Python' },
    { pattern: '*.log', description: 'Log files', category: 'Logs' },
    { pattern: '*.tmp', description: 'Temporary files', category: 'Temp' },
    { pattern: '*.pyc', description: 'Python compiled files', category: 'Python' },
    { pattern: '.DS_Store', description: 'macOS system files', category: 'System' },
    { pattern: 'Thumbs.db', description: 'Windows thumbnail cache', category: 'System' },
    { pattern: '*.swp', description: 'Vim swap files', category: 'Editor' },
  ];

  const presetIncludePatterns = [
    { pattern: '*.py', description: 'Python files', category: 'Code' },
    { pattern: '*.js', description: 'JavaScript files', category: 'Code' },
    { pattern: '*.ts', description: 'TypeScript files', category: 'Code' },
    { pattern: '*.sh', description: 'Shell scripts', category: 'Scripts' },
    { pattern: '*.md', description: 'Markdown files', category: 'Docs' },
    { pattern: '*.yml', description: 'YAML configuration', category: 'Config' },
    { pattern: '*.yaml', description: 'YAML configuration', category: 'Config' },
    { pattern: '*.json', description: 'JSON files', category: 'Config' },
    { pattern: '*.toml', description: 'TOML configuration', category: 'Config' },
    { pattern: '*.txt', description: 'Text files', category: 'Docs' },
  ];

  function addExcludePattern(): void {
    if (currentExcludePattern.trim() && !excludePatterns.includes(currentExcludePattern.trim())) {
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
    if (currentIncludePattern.trim() && !includePatterns.includes(currentIncludePattern.trim())) {
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

  function addPresetPattern(pattern: string, type: 'exclude' | 'include'): void {
    if (type === 'exclude' && !excludePatterns.includes(pattern)) {
      excludePatterns = [...excludePatterns, pattern];
      dispatchChange();
    } else if (type === 'include' && !includePatterns.includes(pattern)) {
      includePatterns = [...includePatterns, pattern];
      dispatchChange();
    }
  }

  function clearAllPatterns(type: 'exclude' | 'include'): void {
    if (type === 'exclude') {
      excludePatterns = [];
    } else {
      includePatterns = [];
    }
    dispatchChange();
  }

  function resetToDefaults(): void {
    excludePatterns = ['*.log', '*.tmp', '__pycache__/'];
    includePatterns = [];
    noGitignore = false;
    dispatchChange();
  }

  // Group presets by category
  function groupPresetsByCategory(presets: typeof presetExcludePatterns) {
    const groups: Record<string, typeof presets> = {};
    presets.forEach(preset => {
      if (!groups[preset.category]) groups[preset.category] = [];
      groups[preset.category].push(preset);
    });
    return groups;
  }

  $: excludeGroups = groupPresetsByCategory(presetExcludePatterns);
  $: includeGroups = groupPresetsByCategory(presetIncludePatterns);
</script>

<div class="sync-settings">
  <!-- Action Buttons -->
  <div class="action-buttons">
    <Button
      variant="ghost"
      size="sm"
      on:click={() => showHelp = !showHelp}
      class="help-btn"
    >
      <HelpCircle class="w-4 h-4" />
      Help
    </Button>
    <Button
      variant="ghost"
      size="sm"
      on:click={resetToDefaults}
      class="reset-btn"
    >
      <RotateCcw class="w-4 h-4" />
      Reset
    </Button>
  </div>

  <!-- Gitignore Setting -->
  <Card class="gitignore-section">
    <div class="setting-header">
      <div class="setting-info">
        <GitBranch class="w-5 h-5 text-blue-600" />
        <div>
          <h4 class="setting-title">.gitignore Integration</h4>
          <p class="setting-description">Automatically respect .gitignore patterns</p>
        </div>
      </div>
      <label class="toggle-switch">
        <input
          type="checkbox"
          bind:checked={noGitignore}
          on:change={handleGitignoreChange}
        />
        <span class="toggle-slider"></span>
      </label>
    </div>
    <div class="setting-note">
      {#if noGitignore}
        <span class="note-text warning">⚠️ .gitignore patterns will be ignored</span>
      {:else}
        <span class="note-text success">✓ .gitignore patterns will be respected</span>
      {/if}
    </div>
  </Card>

  <!-- Exclude Patterns -->
  <Card class="patterns-section">
    <div class="section-header">
      <div class="section-info">
        <FolderX class="w-5 h-5 text-red-600" />
        <div>
          <h4 class="section-title">Exclude Patterns</h4>
          <p class="section-description">Files and directories to skip during sync</p>
        </div>
      </div>
      <div class="section-actions">
        {#if excludePatterns.length > 0}
          <Button
            variant="ghost"
            size="sm"
            on:click={() => clearAllPatterns('exclude')}
            class="clear-btn"
          >
            <Trash2 class="w-4 h-4" />
            Clear All
          </Button>
        {/if}
      </div>
    </div>

    <!-- Pattern Input -->
    <div class="pattern-input">
      <Input
        bind:value={currentExcludePattern}
        placeholder="e.g., *.log, node_modules/, __pycache__/"
        class="pattern-field"
        on:keypress={(e) => handleKeyPress(e, addExcludePattern)}
      />
      <Button
        on:click={addExcludePattern}
        disabled={!currentExcludePattern.trim()}
        size="sm"
        class="add-pattern-btn"
      >
        <Plus class="w-4 h-4" />
        Add
      </Button>
    </div>

    <!-- Pattern Tags -->
    <div class="patterns-display">
      {#if excludePatterns.length > 0}
        <div class="pattern-tags">
          {#each excludePatterns as pattern, index}
            <span class="pattern-tag exclude-tag">
              <FolderX class="w-3 h-3" />
              <span class="tag-text">{pattern}</span>
              <button
                type="button"
                class="remove-tag-btn"
                on:click={() => removeExcludePattern(index)}
                title="Remove pattern"
              >
                <X class="w-3 h-3" />
              </button>
            </span>
          {/each}
        </div>
      {:else}
        <div class="empty-state">
          <FolderX class="w-8 h-8 text-gray-400" />
          <p class="empty-text">No exclude patterns</p>
          <p class="empty-description">All files will be synced (except .gitignore patterns)</p>
        </div>
      {/if}
    </div>

    <!-- Preset Patterns -->
    <details class="preset-section">
      <summary class="preset-header">
        <span>Quick Add Common Patterns</span>
      </summary>
      <div class="preset-content">
        {#each Object.entries(excludeGroups) as [category, presets]}
          <div class="preset-category">
            <h5 class="category-title">{category}</h5>
            <div class="preset-buttons">
              {#each presets as preset}
                <button
                  type="button"
                  class="preset-btn"
                  class:added={excludePatterns.includes(preset.pattern)}
                  on:click={() => addPresetPattern(preset.pattern, 'exclude')}
                  disabled={excludePatterns.includes(preset.pattern)}
                  title={preset.description}
                >
                  <span class="preset-pattern">{preset.pattern}</span>
                  <span class="preset-desc">{preset.description}</span>
                </button>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    </details>
  </Card>

  <!-- Include Patterns -->
  <Card class="patterns-section">
    <div class="section-header">
      <div class="section-info">
        <FileCheck class="w-5 h-5 text-green-600" />
        <div>
          <h4 class="section-title">Include Patterns <span class="optional-badge">Optional</span></h4>
          <p class="section-description">Force include files even if excluded by .gitignore</p>
        </div>
      </div>
      <div class="section-actions">
        {#if includePatterns.length > 0}
          <Button
            variant="ghost"
            size="sm"
            on:click={() => clearAllPatterns('include')}
            class="clear-btn"
          >
            <Trash2 class="w-4 h-4" />
            Clear All
          </Button>
        {/if}
      </div>
    </div>

    <!-- Pattern Input -->
    <div class="pattern-input">
      <Input
        bind:value={currentIncludePattern}
        placeholder="e.g., *.py, *.js, *.md"
        class="pattern-field"
        on:keypress={(e) => handleKeyPress(e, addIncludePattern)}
      />
      <Button
        on:click={addIncludePattern}
        disabled={!currentIncludePattern.trim()}
        size="sm"
        class="add-pattern-btn"
      >
        <Plus class="w-4 h-4" />
        Add
      </Button>
    </div>

    <!-- Pattern Tags -->
    <div class="patterns-display">
      {#if includePatterns.length > 0}
        <div class="pattern-tags">
          {#each includePatterns as pattern, index}
            <span class="pattern-tag include-tag">
              <FileCheck class="w-3 h-3" />
              <span class="tag-text">{pattern}</span>
              <button
                type="button"
                class="remove-tag-btn"
                on:click={() => removeIncludePattern(index)}
                title="Remove pattern"
              >
                <X class="w-3 h-3" />
              </button>
            </span>
          {/each}
        </div>
      {:else}
        <div class="empty-state">
          <FileCheck class="w-8 h-8 text-gray-400" />
          <p class="empty-text">No include patterns</p>
          <p class="empty-description">Relying on .gitignore and exclude patterns</p>
        </div>
      {/if}
    </div>

    <!-- Preset Patterns -->
    <details class="preset-section">
      <summary class="preset-header">
        <span>Quick Add Common Patterns</span>
      </summary>
      <div class="preset-content">
        {#each Object.entries(includeGroups) as [category, presets]}
          <div class="preset-category">
            <h5 class="category-title">{category}</h5>
            <div class="preset-buttons">
              {#each presets as preset}
                <button
                  type="button"
                  class="preset-btn"
                  class:added={includePatterns.includes(preset.pattern)}
                  on:click={() => addPresetPattern(preset.pattern, 'include')}
                  disabled={includePatterns.includes(preset.pattern)}
                  title={preset.description}
                >
                  <span class="preset-pattern">{preset.pattern}</span>
                  <span class="preset-desc">{preset.description}</span>
                </button>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    </details>
  </Card>

  <!-- Help Section -->
  {#if showHelp}
    <Card class="help-section">
      <div class="help-header">
        <HelpCircle class="w-5 h-5 text-blue-600" />
        <h4 class="help-title">Pattern Help & Examples</h4>
      </div>

      <div class="help-content">
        <div class="help-row">
          <div class="help-column">
            <h5 class="help-subtitle">Wildcards</h5>
            <ul class="help-list">
              <li><code>*</code> - Matches any characters in filename</li>
              <li><code>**</code> - Matches directories recursively</li>
              <li><code>?</code> - Matches single character</li>
              <li><code>[abc]</code> - Matches any character in brackets</li>
            </ul>
          </div>
          <div class="help-column">
            <h5 class="help-subtitle">Examples</h5>
            <ul class="help-list">
              <li><code>*.log</code> - All log files</li>
              <li><code>data/*.csv</code> - CSV files in data directory</li>
              <li><code>**/temp</code> - All temp directories</li>
              <li><code>test_*.py</code> - Python test files</li>
            </ul>
          </div>
        </div>

        <div class="help-note">
          <p><strong>Tips:</strong></p>
          <ul>
            <li>Exclude patterns prevent files from being synced</li>
            <li>Include patterns override .gitignore exclusions</li>
            <li>Patterns are applied in order of precedence</li>
            <li>Use forward slashes (/) for directory separators</li>
          </ul>
        </div>
      </div>
    </Card>
  {/if}
</div>

<style>
  .sync-settings {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  /* Action Buttons */
  .action-buttons {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
    margin-bottom: 1rem;
  }

  /* Gitignore Section */
  .gitignore-section {
    padding: 1rem;
  }

  .setting-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .setting-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .setting-title {
    font-size: 1rem;
    font-weight: 600;
    color: #1f2937;
    margin: 0;
  }

  .setting-description {
    font-size: 0.875rem;
    color: #6b7280;
    margin: 0;
  }

  .toggle-switch {
    position: relative;
    width: 44px;
    height: 24px;
    cursor: pointer;
  }

  .toggle-switch input {
    opacity: 0;
    width: 0;
    height: 0;
  }

  .toggle-slider {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: #d1d5db;
    border-radius: 24px;
    transition: background 0.2s ease;
  }

  .toggle-slider::before {
    position: absolute;
    content: "";
    height: 20px;
    width: 20px;
    left: 2px;
    bottom: 2px;
    background: white;
    border-radius: 50%;
    transition: transform 0.2s ease;
  }

  .toggle-switch input:checked + .toggle-slider {
    background: #3b82f6;
  }

  .toggle-switch input:checked + .toggle-slider::before {
    transform: translateX(20px);
  }

  .setting-note {
    padding: 0.5rem 0.75rem;
    background: #f8fafc;
    border-radius: 6px;
    border-left: 4px solid transparent;
  }

  .note-text {
    font-size: 0.875rem;
    font-weight: 500;
  }

  .note-text.success {
    color: #059669;
    border-left-color: #059669;
  }

  .note-text.warning {
    color: #d97706;
    border-left-color: #d97706;
  }

  /* Patterns Sections */
  .patterns-section {
    padding: 1rem;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }

  .section-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .section-title {
    font-size: 1rem;
    font-weight: 600;
    color: #1f2937;
    margin: 0;
  }

  .optional-badge {
    font-size: 0.75rem;
    background: #e5e7eb;
    color: #6b7280;
    padding: 0.125rem 0.375rem;
    border-radius: 12px;
    font-weight: 500;
  }

  .section-description {
    font-size: 0.875rem;
    color: #6b7280;
    margin: 0;
  }

  .section-actions {
    display: flex;
    gap: 0.5rem;
  }

  /* Pattern Input */
  .pattern-input {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  :global(.pattern-field) {
    flex: 1;
  }

  /* Pattern Display */
  .patterns-display {
    margin-bottom: 1rem;
  }

  .pattern-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .pattern-tag {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 0.75rem;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    transition: all 0.2s ease;
  }

  .exclude-tag {
    background: #fef2f2;
    color: #dc2626;
    border: 1px solid #fecaca;
  }

  .include-tag {
    background: #f0fdf4;
    color: #16a34a;
    border: 1px solid #bbf7d0;
  }

  .tag-text {
    font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
    font-size: 0.8125rem;
  }

  .remove-tag-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: currentColor;
    opacity: 0.6;
    transition: opacity 0.2s ease;
    padding: 0.25rem;
    border-radius: 4px;
  }

  .remove-tag-btn:hover {
    opacity: 1;
    background: rgba(0, 0, 0, 0.1);
  }

  /* Empty State */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    text-align: center;
    border: 2px dashed #e5e7eb;
    border-radius: 12px;
    background: #f9fafb;
  }

  .empty-text {
    font-size: 1rem;
    font-weight: 500;
    color: #6b7280;
    margin: 0.5rem 0 0.25rem 0;
  }

  .empty-description {
    font-size: 0.875rem;
    color: #9ca3af;
    margin: 0;
  }

  /* Preset Section */
  .preset-section {
    border-top: 1px solid #e5e7eb;
    padding-top: 1rem;
  }

  .preset-header {
    cursor: pointer;
    font-weight: 500;
    color: #374151;
    padding: 0.5rem 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .preset-header::before {
    content: '▶';
    transition: transform 0.2s ease;
  }

  .preset-section[open] .preset-header::before {
    transform: rotate(90deg);
  }

  .preset-content {
    padding-top: 1rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .preset-category {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .category-title {
    font-size: 0.875rem;
    font-weight: 600;
    color: #4b5563;
    margin: 0;
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .preset-buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
  }

  .preset-btn {
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    cursor: pointer;
    transition: all 0.2s ease;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.125rem;
    min-width: 0;
  }

  .preset-btn:hover:not(:disabled) {
    border-color: #3b82f6;
    background: #eff6ff;
  }

  .preset-btn:disabled {
    background: #f3f4f6;
    color: #9ca3af;
    cursor: not-allowed;
  }

  .preset-btn.added {
    background: #eff6ff;
    border-color: #3b82f6;
    color: #1d4ed8;
  }

  .preset-pattern {
    font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
    font-size: 0.8125rem;
    font-weight: 600;
  }

  .preset-desc {
    font-size: 0.75rem;
    color: #6b7280;
    line-height: 1.2;
  }

  /* Help Section */
  .help-section {
    padding: 1rem;
  }

  .help-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  .help-title {
    font-size: 1rem;
    font-weight: 600;
    color: #1f2937;
    margin: 0;
  }

  .help-content {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .help-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2rem;
  }

  .help-column {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .help-subtitle {
    font-size: 0.875rem;
    font-weight: 600;
    color: #374151;
    margin: 0;
  }

  .help-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .help-list li {
    font-size: 0.875rem;
    color: #6b7280;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .help-list code {
    background: #f3f4f6;
    padding: 0.125rem 0.25rem;
    border-radius: 4px;
    font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
    font-size: 0.8125rem;
    color: #1f2937;
  }

  .help-note {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 8px;
    padding: 1rem;
  }

  .help-note p {
    margin: 0 0 0.5rem 0;
    font-weight: 600;
    color: #1e40af;
  }

  .help-note ul {
    margin: 0;
    padding-left: 1rem;
    color: #3730a3;
  }

  .help-note li {
    font-size: 0.875rem;
    margin-bottom: 0.25rem;
  }

  /* Mobile Responsive */
  @media (max-width: 768px) {
    .action-buttons {
      justify-content: center;
    }

    .section-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }

    .pattern-input {
      flex-direction: column;
    }

    .help-row {
      grid-template-columns: 1fr;
      gap: 1rem;
    }

    .preset-buttons {
      gap: 0.25rem;
    }

    .preset-btn {
      padding: 0.375rem 0.5rem;
    }
  }
</style>