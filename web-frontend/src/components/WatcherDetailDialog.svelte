<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api } from '../services/api';
  import type { Watcher } from '../types/watchers';
  
  export let watcher: Watcher | null = null;
  export let jobId: string = '';
  export let hostname: string = '';
  
  const dispatch = createEventDispatcher();
  
  // UI state
  let activeTab: 'view' | 'edit' | 'code' = 'view';
  let isEditing = false;
  let isSaving = false;
  let error: string | null = null;
  let copySuccess = false;
  let codeFormat: 'inline' | 'file' = 'file'; // Default to block format
  
  // Editable fields
  let editName = '';
  let editPattern = '';
  let editInterval = 30;
  let editCaptures: string[] = [];
  let editCondition = '';
  let editActions: any[] = [];
  let editTimerMode = false;
  let editTimerInterval = 30;
  
  // Initialize edit fields when watcher changes
  $: if (watcher) {
    editName = watcher.name;
    editPattern = watcher.pattern;
    editInterval = watcher.interval_seconds;
    editCaptures = watcher.captures || [];
    editCondition = watcher.condition || '';
    editActions = watcher.actions || [];
    editTimerMode = watcher.timer_mode_enabled || false;
    editTimerInterval = watcher.timer_interval_seconds || 30;
  }
  
  function formatTime(timeStr: string | null): string {
    if (!timeStr) return 'Never';
    try {
      const date = new Date(timeStr);
      return date.toLocaleString();
    } catch {
      return 'Invalid date';
    }
  }
  
  function getActionDescription(action: any): string {
    switch (action.type) {
      case 'log_event':
        return 'Log event to output';
      case 'store_metric':
        return `Store metric: ${action.config?.metric_name || 'unnamed'}`;
      case 'run_command':
        return `Run: ${action.config?.command?.substring(0, 50) || 'command'}...`;
      case 'notify_email':
        return `Email to: ${action.config?.to || 'recipient'}`;
      case 'notify_slack':
        return 'Send Slack notification';
      case 'cancel_job':
        return `Cancel job${action.config?.reason ? ': ' + action.config.reason : ''}`;
      case 'resubmit':
        return `Resubmit job${action.config?.delay ? ' after ' + action.config.delay + 's' : ''}`;
      case 'pause_watcher':
        return 'Pause this watcher';
      default:
        return action.type;
    }
  }
  
  function generateWatcherCode(): string {
    if (!watcher) return '';
    
    // Always generate block format
    let code = '#WATCHER_BEGIN\n';
    code += `# name: ${watcher.name}\n`;
    code += `# pattern: "${watcher.pattern}"\n`;
    code += `# interval: ${watcher.interval_seconds}\n`;
    
    if (watcher.captures && watcher.captures.length > 0) {
      code += `# captures: [${watcher.captures.map(c => `"${c}"`).join(', ')}]\n`;
    }
    
    if (watcher.condition) {
      code += `# condition: ${watcher.condition}\n`;
    }
    
    if (watcher.timer_mode_enabled) {
      code += `# timer_mode: true\n`;
      code += `# timer_interval: ${watcher.timer_interval_seconds}\n`;
    }
    
    if (watcher.actions && watcher.actions.length > 0) {
      code += '# actions:\n';
      watcher.actions.forEach(action => {
        let actionStr = `#   - ${action.type}`;
        if (action.config && Object.keys(action.config).length > 0) {
          const params = Object.entries(action.config)
            .map(([k, v]) => `${k}="${v}"`)
            .join(', ');
          actionStr += `(${params})`;
        }
        code += actionStr + '\n';
      });
    }
    
    code += '#WATCHER_END';
    
    return code;
  }
  
  async function copyCode() {
    const code = generateWatcherCode();
    try {
      await navigator.clipboard.writeText(code);
      copySuccess = true;
      setTimeout(() => {
        copySuccess = false;
      }, 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
      error = 'Failed to copy to clipboard';
    }
  }
  
  async function saveChanges() {
    if (!watcher) return;
    
    isSaving = true;
    error = null;
    
    try {
      const updatedConfig = {
        name: editName,
        pattern: editPattern,
        interval_seconds: editInterval,
        capture_groups: editCaptures.length > 0 ? editCaptures : undefined,
        condition: editCondition || undefined,
        actions: editActions,
        timer_mode_enabled: editTimerMode,
        timer_interval_seconds: editTimerMode ? editTimerInterval : undefined
      };
      
      // API call to update watcher
      const response = await api.put(`/api/watchers/${watcher.id}`, updatedConfig);
      
      if (response.data) {
        dispatch('updated', response.data);
        isEditing = false;
        activeTab = 'view';
      }
    } catch (err: any) {
      error = err.response?.data?.detail || err.message || 'Failed to update watcher';
    } finally {
      isSaving = false;
    }
  }
  
  async function deleteWatcher() {
    if (!watcher) return;
    
    if (!confirm(`Are you sure you want to delete the watcher "${watcher.name}"?`)) {
      return;
    }
    
    try {
      await api.delete(`/api/watchers/${watcher.id}`);
      dispatch('deleted', watcher.id);
      handleClose();
    } catch (err: any) {
      error = err.response?.data?.detail || err.message || 'Failed to delete watcher';
    }
  }
  
  let isSelecting = false;
  
  function handleClose() {
    // Don't close if user is selecting text
    if (isSelecting) {
      isSelecting = false;
      return;
    }
    dispatch('close');
  }
  
  function handleMouseDown() {
    // Track when user starts selecting
    const selection = window.getSelection();
    if (selection && selection.toString().length === 0) {
      isSelecting = false;
    }
  }
  
  function handleMouseUp(event: MouseEvent) {
    // Check if user has selected text
    const selection = window.getSelection();
    if (selection && selection.toString().length > 0) {
      isSelecting = true;
      // Prevent the click event from firing
      event.stopPropagation();
      event.preventDefault();
    }
  }
  
  function addCapture() {
    editCaptures = [...editCaptures, ''];
  }
  
  function updateCapture(index: number, value: string) {
    editCaptures[index] = value;
    editCaptures = editCaptures;
  }
  
  function removeCapture(index: number) {
    editCaptures = editCaptures.filter((_, i) => i !== index);
  }
  
  function addAction() {
    editActions = [...editActions, { type: 'log_event', config: {} }];
  }
  
  function removeAction(index: number) {
    editActions = editActions.filter((_, i) => i !== index);
  }
</script>

{#if watcher}
<div 
  class="dialog-overlay" 
  on:click={handleClose}
  on:mousedown={handleMouseDown}
  on:mouseup={handleMouseUp}
>
  <div 
    class="dialog-container" 
    on:click|stopPropagation
    on:mousedown|stopPropagation
  >
    <div class="dialog-header">
      <div class="header-content">
        <h2>Watcher Details</h2>
        <p class="watcher-subtitle">{watcher.name}</p>
      </div>
      <button class="close-btn" on:click={handleClose}>
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
        </svg>
      </button>
    </div>
    
    <!-- Tab Navigation -->
    <div class="tabs">
      <button 
        class="tab" 
        class:active={activeTab === 'view'}
        on:click={() => { activeTab = 'view'; isEditing = false; }}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z"/>
        </svg>
        View
      </button>
      <button 
        class="tab" 
        class:active={activeTab === 'edit'}
        on:click={() => { activeTab = 'edit'; isEditing = true; }}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z"/>
        </svg>
        Edit
      </button>
      <button 
        class="tab" 
        class:active={activeTab === 'code'}
        on:click={() => activeTab = 'code'}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M14.6,16.6L19.2,12L14.6,7.4L16,6L22,12L16,18L14.6,16.6M9.4,16.6L4.8,12L9.4,7.4L8,6L2,12L8,18L9.4,16.6Z"/>
        </svg>
        Code
      </button>
    </div>
    
    <div class="dialog-body">
      {#if error}
        <div class="error-message">{error}</div>
      {/if}
      
      {#if activeTab === 'view'}
        <!-- View Mode -->
        <div class="detail-section">
          <h3>Configuration</h3>
          <div class="detail-grid">
            <div class="detail-item">
              <label>Status:</label>
              <span class="status-badge status-{watcher.state}">{watcher.state}</span>
            </div>
            <div class="detail-item">
              <label>Job ID:</label>
              <span>#{watcher.job_id}</span>
            </div>
            <div class="detail-item">
              <label>Host:</label>
              <span>{watcher.hostname}</span>
            </div>
            <div class="detail-item">
              <label>Check Interval:</label>
              <span>{watcher.interval_seconds}s</span>
            </div>
            {#if watcher.timer_mode_enabled}
              <div class="detail-item">
                <label>Timer Mode:</label>
                <span>Every {watcher.timer_interval_seconds}s</span>
              </div>
            {/if}
            <div class="detail-item">
              <label>Triggers:</label>
              <span>{watcher.trigger_count}</span>
            </div>
            <div class="detail-item">
              <label>Last Check:</label>
              <span>{formatTime(watcher.last_check)}</span>
            </div>
          </div>
        </div>
        
        <div class="detail-section">
          <h3>Pattern</h3>
          <div class="pattern-display">
            <code>{watcher.pattern}</code>
          </div>
          
          {#if watcher.captures && watcher.captures.length > 0}
            <div class="captures-display">
              <label>Capture Groups:</label>
              <div class="capture-tags">
                {#each watcher.captures as capture, i}
                  <span class="capture-tag">${i + 1}: {capture}</span>
                {/each}
              </div>
            </div>
          {/if}
          
          {#if watcher.condition}
            <div class="condition-display">
              <label>Condition:</label>
              <code>{watcher.condition}</code>
            </div>
          {/if}
        </div>
        
        <div class="detail-section">
          <h3>Actions ({watcher.actions?.length || 0})</h3>
          <div class="actions-list">
            {#each watcher.actions || [] as action, i}
              <div class="action-card">
                <span class="action-number">{i + 1}</span>
                <div class="action-content">
                  <div class="action-type">{action.type}</div>
                  <div class="action-desc">{getActionDescription(action)}</div>
                </div>
              </div>
            {/each}
          </div>
        </div>
      {:else if activeTab === 'edit'}
        <!-- Edit Mode -->
        <div class="edit-section">
          <div class="form-group">
            <label for="edit-name">Name</label>
            <input 
              id="edit-name"
              type="text" 
              bind:value={editName}
              placeholder="Watcher name"
            />
          </div>
          
          <div class="form-group">
            <label for="edit-pattern">Pattern</label>
            <input 
              id="edit-pattern"
              type="text" 
              bind:value={editPattern}
              placeholder="Regular expression pattern"
            />
          </div>
          
          <div class="form-group">
            <label for="edit-interval">Check Interval (seconds)</label>
            <input 
              id="edit-interval"
              type="number" 
              bind:value={editInterval}
              min="1"
              max="3600"
            />
          </div>
          
          <div class="form-group">
            <label>
              <input 
                type="checkbox" 
                bind:checked={editTimerMode}
              />
              Timer Mode
            </label>
            {#if editTimerMode}
              <input 
                type="number" 
                bind:value={editTimerInterval}
                min="1"
                max="3600"
                placeholder="Timer interval (seconds)"
              />
            {/if}
          </div>
          
          <div class="form-group">
            <label>Capture Groups</label>
            {#each editCaptures as capture, i}
              <div class="capture-edit">
                <input 
                  type="text" 
                  value={capture}
                  on:input={(e) => updateCapture(i, e.target.value)}
                  placeholder="Capture name"
                />
                <button on:click={() => removeCapture(i)}>Remove</button>
              </div>
            {/each}
            <button class="add-btn" on:click={addCapture}>Add Capture</button>
          </div>
          
          <div class="form-group">
            <label for="edit-condition">Condition (Optional)</label>
            <input 
              id="edit-condition"
              type="text" 
              bind:value={editCondition}
              placeholder="Python expression"
            />
          </div>
          
          <div class="edit-actions">
            <button 
              class="btn-primary"
              on:click={saveChanges}
              disabled={isSaving}
            >
              {isSaving ? 'Saving...' : 'Save Changes'}
            </button>
            <button 
              class="btn-secondary"
              on:click={() => { activeTab = 'view'; isEditing = false; }}
            >
              Cancel
            </button>
          </div>
        </div>
      {:else if activeTab === 'code'}
        <!-- Code Generation -->
        <div class="code-section">
          <div class="code-header">
            <h3>Submit Script Integration</h3>
          </div>
          
          <div class="code-instructions">
            <p>Add this block to your SLURM script (after #SBATCH directives):</p>
          </div>
          
          <div class="code-container">
            <pre><code>{generateWatcherCode()}</code></pre>
            <button 
              class="copy-code-btn"
              class:success={copySuccess}
              on:click={copyCode}
            >
              {#if copySuccess}
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z"/>
                </svg>
                Copied!
              {:else}
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z"/>
                </svg>
                Copy Code
              {/if}
            </button>
          </div>
          
          <div class="code-notes">
            <h4>Notes:</h4>
            <ul>
              <li>Place this #WATCHER_BEGIN...#WATCHER_END block after your #SBATCH directives</li>
              <li>The block format supports multiple actions and complex conditions</li>
              <li>Multiple watcher blocks can be added to monitor different conditions</li>
              <li>Watchers automatically stop when the job completes</li>
              <li>All parameters inside the block must start with # and be indented</li>
            </ul>
          </div>
        </div>
      {/if}
    </div>
    
    <div class="dialog-footer">
      {#if activeTab === 'view'}
        <button class="btn-danger" on:click={deleteWatcher}>
          Delete Watcher
        </button>
      {/if}
      <button class="btn-secondary" on:click={handleClose}>
        Close
      </button>
    </div>
  </div>
</div>
{/if}

<style>
  .dialog-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    backdrop-filter: blur(2px);
    animation: fadeIn 0.2s ease-out;
  }
  
  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }
  
  .dialog-container {
    background: white;
    border-radius: 12px;
    width: 90%;
    max-width: 800px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
    animation: slideIn 0.3s ease-out;
  }
  
  @keyframes slideIn {
    from {
      transform: translateY(-20px) scale(0.95);
      opacity: 0;
    }
    to {
      transform: translateY(0) scale(1);
      opacity: 1;
    }
  }
  
  .dialog-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .header-content h2 {
    margin: 0;
    font-size: 1.5rem;
    color: #111827;
  }
  
  .watcher-subtitle {
    margin: 0.25rem 0 0 0;
    color: #6b7280;
    font-size: 0.875rem;
  }
  
  .close-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.5rem;
    color: #6b7280;
    transition: color 0.2s;
    border-radius: 6px;
  }
  
  .close-btn:hover {
    background: #f3f4f6;
    color: #111827;
  }
  
  .close-btn svg {
    width: 20px;
    height: 20px;
  }
  
  /* Tabs */
  .tabs {
    display: flex;
    gap: 0.5rem;
    padding: 0 1.5rem;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .tab {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    cursor: pointer;
    color: #6b7280;
    font-size: 0.875rem;
    font-weight: 500;
    transition: all 0.2s;
  }
  
  .tab svg {
    width: 18px;
    height: 18px;
  }
  
  .tab:hover {
    color: #374151;
  }
  
  .tab.active {
    color: #3b82f6;
    border-bottom-color: #3b82f6;
  }
  
  .dialog-body {
    padding: 1.5rem;
    overflow-y: auto;
    flex: 1;
  }
  
  .error-message {
    background: #fee2e2;
    border: 1px solid #fecaca;
    color: #dc2626;
    padding: 0.75rem;
    border-radius: 6px;
    margin-bottom: 1rem;
  }
  
  /* View Mode */
  .detail-section {
    margin-bottom: 2rem;
  }
  
  .detail-section h3 {
    margin: 0 0 1rem 0;
    font-size: 1.1rem;
    color: #111827;
  }
  
  .detail-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
  }
  
  .detail-item {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .detail-item label {
    font-size: 0.75rem;
    font-weight: 500;
    color: #6b7280;
    text-transform: uppercase;
  }
  
  .detail-item span {
    font-size: 0.875rem;
    color: #111827;
  }
  
  .status-badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
  }
  
  .status-active {
    background: #d1fae5;
    color: #065f46;
  }
  
  .status-paused {
    background: #fed7aa;
    color: #92400e;
  }
  
  .status-completed {
    background: #dbeafe;
    color: #1e40af;
  }
  
  .status-failed {
    background: #fee2e2;
    color: #991b1b;
  }
  
  .pattern-display {
    background: #f9fafb;
    padding: 1rem;
    border-radius: 6px;
    margin-bottom: 1rem;
  }
  
  .pattern-display code {
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 0.875rem;
    color: #111827;
    word-break: break-all;
  }
  
  .captures-display,
  .condition-display {
    margin-top: 1rem;
  }
  
  .captures-display label,
  .condition-display label {
    display: block;
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
    margin-bottom: 0.5rem;
  }
  
  .capture-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  
  .capture-tag {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 6px;
    font-family: monospace;
    font-size: 0.75rem;
    color: #1e40af;
  }
  
  .condition-display code {
    display: block;
    padding: 0.5rem;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.875rem;
  }
  
  .actions-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .action-card {
    display: flex;
    align-items: flex-start;
    gap: 1rem;
    padding: 0.75rem;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
  }
  
  .action-number {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    background: #3b82f6;
    color: white;
    border-radius: 50%;
    font-size: 0.75rem;
    font-weight: 600;
    flex-shrink: 0;
  }
  
  .action-content {
    flex: 1;
  }
  
  .action-type {
    font-size: 0.875rem;
    font-weight: 600;
    color: #111827;
    margin-bottom: 0.25rem;
  }
  
  .action-desc {
    font-size: 0.75rem;
    color: #6b7280;
  }
  
  /* Edit Mode */
  .edit-section {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .form-group label {
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
  }
  
  .form-group input[type="text"],
  .form-group input[type="number"] {
    padding: 0.5rem 0.75rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.875rem;
  }
  
  .form-group input[type="checkbox"] {
    margin-right: 0.5rem;
  }
  
  .capture-edit {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }
  
  .capture-edit input {
    flex: 1;
  }
  
  .capture-edit button {
    padding: 0.5rem 1rem;
    background: #ef4444;
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 0.75rem;
    cursor: pointer;
  }
  
  .add-btn {
    padding: 0.5rem 1rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    cursor: pointer;
    align-self: flex-start;
  }
  
  .edit-actions {
    display: flex;
    gap: 1rem;
    margin-top: 1rem;
  }
  
  /* Code Section */
  .code-section {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .code-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .code-header h3 {
    margin: 0;
    font-size: 1.1rem;
    color: #111827;
  }
  
  .format-selector {
    display: flex;
    gap: 1rem;
  }
  
  .format-selector label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    color: #374151;
  }
  
  .code-instructions {
    padding: 0.75rem;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 6px;
  }
  
  .code-instructions p {
    margin: 0;
    font-size: 0.875rem;
    color: #1e40af;
  }
  
  .code-container {
    position: relative;
    background: #1f2937;
    border-radius: 8px;
    overflow: hidden;
  }
  
  .code-container pre {
    margin: 0;
    padding: 1rem;
    overflow-x: auto;
  }
  
  .code-container code {
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 0.875rem;
    color: #e5e7eb;
    line-height: 1.5;
  }
  
  .copy-code-btn {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .copy-code-btn:hover {
    background: #2563eb;
  }
  
  .copy-code-btn.success {
    background: #10b981;
  }
  
  .copy-code-btn svg {
    width: 16px;
    height: 16px;
  }
  
  .code-notes {
    background: #f9fafb;
    padding: 1rem;
    border-radius: 6px;
  }
  
  .code-notes h4 {
    margin: 0 0 0.5rem 0;
    font-size: 0.875rem;
    font-weight: 600;
    color: #374151;
  }
  
  .code-notes ul {
    margin: 0;
    padding-left: 1.5rem;
  }
  
  .code-notes li {
    font-size: 0.75rem;
    color: #6b7280;
    margin-bottom: 0.25rem;
  }
  
  /* Footer */
  .dialog-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-top: 1px solid #e5e7eb;
  }
  
  .btn-primary,
  .btn-secondary,
  .btn-danger {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .btn-primary {
    background: #3b82f6;
    color: white;
  }
  
  .btn-primary:hover:not(:disabled) {
    background: #2563eb;
  }
  
  .btn-secondary {
    background: white;
    color: #374151;
    border: 1px solid #d1d5db;
    margin-left: auto;
  }
  
  .btn-secondary:hover {
    background: #f3f4f6;
  }
  
  .btn-danger {
    background: #ef4444;
    color: white;
  }
  
  .btn-danger:hover {
    background: #dc2626;
  }
  
  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  @media (max-width: 640px) {
    .dialog-container {
      width: 100%;
      height: 100vh;
      max-width: none;
      max-height: 100vh;
      border-radius: 0;
      display: flex;
      flex-direction: column;
    }

    .dialog-body {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
    }

    .detail-grid {
      grid-template-columns: 1fr;
    }
  }
</style>