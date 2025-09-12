<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { push } from 'svelte-spa-router';
  import type { Watcher } from '../types/watchers';
  import { pauseWatcher, resumeWatcher } from '../stores/watchers';
  import { api } from '../services/api';
  import WatcherDetailDialog from './WatcherDetailDialog.svelte';
  import { portal } from '../lib/portal';
  
  export let watcher: Watcher;
  export let jobInfo: any = null;
  export let showJobLink = true;
  
  const dispatch = createEventDispatcher();
  
  // State management
  let isExpanded = false;
  let isPausing = false;
  let isTriggering = false;
  let triggerMessage = '';
  let showDetailDialog = false;
  
  // Real-time pulse animation for active watchers
  $: isActive = watcher.state === 'active';
  $: pulseClass = isActive ? 'pulse' : '';
  
  // Format time like JobList component
  function formatTime(timeStr: string | null): string {
    if (!timeStr) return 'Never';
    try {
      const date = new Date(timeStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMinutes = Math.floor(diffMs / (1000 * 60));
      const diffHours = Math.floor(diffMinutes / 60);
      
      if (diffMinutes < 1) return 'Just now';
      if (diffMinutes < 60) return `${diffMinutes}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      
      return date.toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return 'Invalid date';
    }
  }
  
  function getStateIcon(state: string): string {
    switch (state) {
      case 'active': return '●';
      case 'paused': return '||';
      case 'completed': return '✓';
      case 'failed': return '×';
      default: return '○';
    }
  }
  
  function getStateColor(state: string): string {
    switch (state) {
      case 'active': return '#10b981';
      case 'paused': return '#f59e0b';
      case 'completed': return '#3b82f6';
      case 'failed': return '#ef4444';
      default: return '#6b7280';
    }
  }
  
  function getActionIcon(actionType: string): string {
    if (actionType.includes('metric')) return 'M';
    if (actionType.includes('email')) return '@';
    if (actionType.includes('log')) return 'L';
    if (actionType.includes('command')) return '>';
    if (actionType.includes('checkpoint')) return '*';
    return '+';
  }
  
  async function togglePause() {
    if (isPausing) return;
    isPausing = true;
    
    try {
      if (watcher.state === 'active') {
        await pauseWatcher(watcher.id);
      } else if (watcher.state === 'paused') {
        await resumeWatcher(watcher.id);
      }
    } catch (error) {
      console.error('Failed to toggle watcher state:', error);
    } finally {
      isPausing = false;
    }
  }
  
  async function triggerManually() {
    if (isTriggering || watcher.state !== 'active') return;
    isTriggering = true;
    triggerMessage = '';
    
    try {
      const response = await api.post(`/api/watchers/${watcher.id}/trigger`, null);
      
      // Handle timer mode response
      if (response.data.timer_mode) {
        if (response.data.success) {
          triggerMessage = '⏱️ Timer actions executed: ' + (response.data.message || 'Success');
        } else {
          triggerMessage = '⏱️ Timer execution failed: ' + (response.data.message || 'Unknown error');
        }
      } else {
        // Regular pattern matching response
        if (response.data.matches) {
          triggerMessage = '✓ Pattern matched and actions executed';
        } else {
          triggerMessage = '○ No pattern matches found';
        }
      }
      
      // Clear message after 3 seconds (or 5 for longer messages)
      const clearDelay = response.data.message && response.data.message.length > 50 ? 5000 : 3000;
      setTimeout(() => {
        triggerMessage = '';
      }, clearDelay);
      
      // Refresh events if matches were found or timer actions executed
      if (response.data.matches || response.data.timer_mode) {
        dispatch('refresh');
      }
    } catch (error) {
      console.error('Failed to trigger watcher:', error);
      let errorMessage = '✗ Failed to trigger';
      
      // Extract more specific error information
      if (error.response?.data?.detail) {
        errorMessage = `✗ ${error.response.data.detail}`;
      } else if (error.response?.status === 404) {
        errorMessage = '✗ Watcher not found';
      } else if (error.response?.status === 400) {
        errorMessage = '✗ Watcher not active';
      } else if (error.message) {
        errorMessage = `✗ ${error.message}`;
      }
      
      triggerMessage = errorMessage;
      setTimeout(() => {
        triggerMessage = '';
      }, 5000); // Longer timeout for error messages
    } finally {
      isTriggering = false;
    }
  }
  
  function navigateToJob() {
    // Navigate to the job details page
    push(`/jobs/${watcher.job_id}/${watcher.hostname}`);
  }
  
  function viewDetails() {
    // Navigate to watchers page with Events tab selected and filtered by this watcher
    push(`/watchers?tab=events&watcher=${watcher.id}`);
  }
  
  function copyWatcher() {
    // Create watcher config
    const watcherConfig = {
      name: watcher.name,
      pattern: watcher.pattern,
      captures: watcher.captures || [],
      interval: watcher.interval_seconds,
      condition: watcher.condition,
      actions: watcher.actions || [],
      timer_mode_enabled: watcher.timer_mode_enabled || false,
      timer_interval_seconds: watcher.timer_interval_seconds || 30
    };
    
    // Store in localStorage as backup
    localStorage.setItem('copiedWatcher', JSON.stringify(watcherConfig));
    
    // Dispatch event to parent to trigger attach workflow
    dispatch('copy', watcherConfig);
    
    // Show confirmation
    const copyBtn = document.querySelector(`#copy-btn-${watcher.id} span`);
    if (copyBtn) {
      copyBtn.textContent = 'Opening...';
      setTimeout(() => {
        copyBtn.textContent = 'Copy';
      }, 1000);
    }
  }
  
  // Calculate activity percentage for visualization
  $: activityPercentage = Math.min((watcher.trigger_count / 100) * 100, 100);
  
  function openDetailDialog() {
    showDetailDialog = true;
  }
  
  function handleDetailClose() {
    showDetailDialog = false;
  }
  
  function handleDetailUpdate(event: CustomEvent) {
    // Update the watcher with new data
    dispatch('refresh');
    showDetailDialog = false;
  }
  
  function handleDetailDelete(event: CustomEvent) {
    dispatch('refresh');
    showDetailDialog = false;
  }
</script>

<div class="watcher-card {pulseClass}" class:expanded={isExpanded}>
  {#if triggerMessage}
    <div 
      class="trigger-message" 
      class:success={triggerMessage.includes('✓')}
      class:error={triggerMessage.includes('✗')}
    >
      {triggerMessage}
    </div>
  {/if}
  
  <!-- Header with state indicator -->
  <div class="card-header">
    <div class="header-left">
      <span class="state-indicator" style="color: {getStateColor(watcher.state)}">
        {getStateIcon(watcher.state)}
      </span>
      <div class="watcher-info">
        <div class="name-row">
          <h3 class="watcher-name">{watcher.name}</h3>
        </div>
        {#if showJobLink && jobInfo}
          <button class="job-link" on:click={navigateToJob}>
            Job #{watcher.job_id} - {jobInfo?.name || 'Unknown'}
          </button>
        {:else}
          <span class="job-id">Job #{watcher.job_id}</span>
        {/if}
      </div>
    </div>
    
    <div class="header-actions">
      {#if watcher.timer_mode_enabled}
        <div class="timer-indicator" class:active={watcher.timer_mode_active} title="Timer Mode {watcher.timer_mode_active ? 'Active' : 'Enabled'}">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M15,1H9V3H15M11,14H13V8H11M19.03,7.39L20.45,5.97C20,5.46 19.55,5 19.04,4.56L17.62,6C16.07,4.74 14.12,4 12,4A9,9 0 0,0 3,13A9,9 0 0,0 12,22C17,22 21,17.97 21,13C21,10.88 20.26,8.93 19.03,7.39Z"/>
          </svg>
        </div>
      {/if}
      
      <button
        class="detail-btn"
        on:click|stopPropagation={openDetailDialog}
        title="View details and get code snippet"
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z"/>
        </svg>
        <span>Details</span>
      </button>
      
      <button
        id="copy-btn-{watcher.id}"
        class="copy-btn"
        on:click|stopPropagation={copyWatcher}
        title="Copy this watcher configuration"
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z"/>
        </svg>
        <span>Copy</span>
      </button>
      
      {#if watcher.state === 'active' || watcher.state === 'paused'}
        <button 
          class="control-btn {watcher.state === 'paused' ? 'resume' : ''}"
          class:pausing={isPausing}
          on:click={togglePause}
          disabled={isPausing}
          title={watcher.state === 'active' ? 'Pause watcher' : 'Resume watcher'}
        >
          {#if isPausing}
            <svg class="spinner-icon" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="31.4" stroke-dashoffset="10"/>
            </svg>
          {:else if watcher.state === 'active'}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <rect x="7" y="6" width="3" height="12" />
              <rect x="14" y="6" width="3" height="12" />
            </svg>
          {:else}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5v14l11-7z"/>
            </svg>
          {/if}
        </button>
      {/if}
      
      {#if watcher.state === 'active'}
        <button 
          class="control-btn"
          class:triggering={isTriggering}
          on:click={triggerManually}
          disabled={isTriggering}
          title="Manually trigger watcher">
          {#if isTriggering}
            <svg class="spinner-icon" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="31.4" stroke-dashoffset="10"/>
            </svg>
          {:else}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M8,5.14V19.14L19,12.14L8,5.14Z"/>
            </svg>
          {/if}
        </button>
      {/if}
      
      <button 
        class="expand-btn"
        on:click={() => isExpanded = !isExpanded}
        title={isExpanded ? 'Collapse' : 'Expand'}
      >
        <svg 
          class="chevron"
          class:rotated={isExpanded}
          viewBox="0 0 24 24" 
          fill="currentColor"
        >
          <path d="M7 10l5 5 5-5z"/>
        </svg>
      </button>
    </div>
  </div>
  
  <!-- Compact info row -->
  <div class="compact-info">
    <div class="info-item">
      <span class="trigger-count">{watcher.trigger_count}</span>
      <span class="info-label">triggers</span>
    </div>
    <div class="info-item">
      <span class="info-value">{watcher.hostname}</span>
    </div>
    <div class="info-item">
      <span class="info-value">
        {#if watcher.timer_mode_enabled}
          {watcher.timer_interval_seconds || watcher.interval_seconds}s
        {:else}
          {watcher.interval_seconds}s
        {/if}
      </span>
    </div>
    <div class="info-item">
      <span class="info-value">{formatTime(watcher.last_check)}</span>
    </div>
  </div>
  
  <!-- Pattern (compact) -->
  <div class="pattern-compact">
    <code class="pattern-text">{watcher.pattern}</code>
    {#if watcher.actions && watcher.actions.length > 0}
      <span class="actions-count">→ {watcher.actions.length} action{watcher.actions.length > 1 ? 's' : ''}</span>
    {/if}
  </div>
  
  <!-- Expanded details -->
  {#if isExpanded}
    <div class="expanded-content">
      {#if watcher.captures && watcher.captures.length > 0}
        <div class="captures-section">
          <label>Capture Groups</label>
          <div class="captures-list">
            {#each watcher.captures as capture, i}
              <span class="capture-item">
                ${i + 1}: {capture || `group_${i + 1}`}
              </span>
            {/each}
          </div>
        </div>
      {/if}
      
      {#if watcher.condition}
        <div class="condition-section">
          <label>Condition</label>
          <code class="condition-code">{watcher.condition}</code>
        </div>
      {/if}
      
      <div class="details-actions">
        <button class="detail-btn" on:click={viewDetails}>
          View Details & Events
        </button>
        {#if showJobLink}
          <button class="detail-btn" on:click={navigateToJob}>
            View Job Output
          </button>
        {/if}
      </div>
    </div>
  {/if}
</div>

{#if showDetailDialog}
  <div use:portal>
    <WatcherDetailDialog
      {watcher}
      jobId={watcher.job_id}
      hostname={watcher.hostname}
      on:close={handleDetailClose}
      on:updated={handleDetailUpdate}
      on:deleted={handleDetailDelete}
    />
  </div>
{/if}

<style>
  .watcher-card {
    background: var(--color-bg-primary, white);
    border: 1px solid var(--color-border, #e5e7eb);
    border-radius: 8px;
    padding: 0.75rem;
    margin-bottom: 0.75rem;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
  }
  
  .watcher-card:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    transform: translateY(-2px);
  }
  
  .watcher-card.pulse::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(90deg, 
      transparent, 
      #10b981, 
      transparent
    );
    animation: pulse-slide 2s infinite;
  }
  
  @keyframes pulse-slide {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(100%); }
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }
  
  .header-left {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  
  .state-indicator {
    font-size: 1.5rem;
    line-height: 1;
  }
  
  .watcher-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .name-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  
  .watcher-name {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text-primary);
  }
  
  .timer-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: #f3f4f6;
    color: #6b7280;
    transition: all 0.2s;
  }
  
  .timer-indicator.active {
    background: #dbeafe;
    color: #1d4ed8;
    animation: timer-pulse 2s infinite;
  }
  
  .timer-indicator svg {
    width: 14px;
    height: 14px;
  }
  
  @keyframes timer-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }
  
  .job-link {
    background: none;
    border: none;
    color: var(--color-primary);
    font-size: 0.875rem;
    cursor: pointer;
    padding: 0;
    text-align: left;
    text-decoration: underline;
    text-decoration-style: dotted;
  }
  
  .job-link:hover {
    text-decoration-style: solid;
  }
  
  .job-id {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }
  
  .header-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .control-btn,
  .expand-btn,
  .detail-btn {
    background: white;
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 0;
    width: 32px;
    height: 32px;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--color-text-secondary);
  }
  
  .detail-btn {
    width: auto;
    padding: 0 0.5rem;
    gap: 0.25rem;
  }
  
  .detail-btn:hover {
    background: #eff6ff;
    border-color: #3b82f6;
    color: #3b82f6;
  }
  
  .detail-btn span {
    font-size: 0.75rem;
    font-weight: 500;
  }
  
  .control-btn svg,
  .expand-btn svg,
  .detail-btn svg {
    width: 16px;
    height: 16px;
  }
  
  .control-btn:hover:not(:disabled) {
    background: var(--color-error-bg);
    border-color: var(--color-error);
    color: var(--color-error);
  }
  
  .control-btn.resume:hover:not(:disabled) {
    background: var(--color-success-bg);
    border-color: var(--color-success);
    color: var(--color-success);
  }
  
  .control-btn.triggering {
    opacity: 0.6;
  }
  
  .trigger-message {
    position: fixed;
    top: 5rem;
    left: 50%;
    transform: translateX(-50%);
    background: white;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    font-size: 0.875rem;
    z-index: 1000;
    animation: slideInMessage 0.3s ease-out;
    color: #6b7280;
  }
  
  .trigger-message.success {
    color: #059669;
    background: #d1fae5;
  }

  .trigger-message.error {
    color: #dc2626;
    background: #fef2f2;
    border: 1px solid #fecaca;
  }
  
  @keyframes slideInMessage {
    from {
      opacity: 0;
      transform: translateX(-50%) translateY(-10px);
    }
    to {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }
  }
  
  .expand-btn:hover {
    background: var(--color-bg-secondary);
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
  
  .control-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .copy-btn {
    padding: 0.25rem 0.5rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    color: #6b7280;
    font-size: 0.75rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.25rem;
    transition: all 0.2s;
  }
  
  .copy-btn:hover {
    background: #f3f4f6;
    color: #1f2937;
    border-color: #9ca3af;
  }
  
  .copy-btn svg {
    width: 14px;
    height: 14px;
  }
  
  .spinner-icon {
    animation: spin 1s linear infinite;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  .chevron {
    width: 20px;
    height: 20px;
    transition: transform 0.3s;
  }
  
  .chevron.rotated {
    transform: rotate(180deg);
  }
  
  .compact-info {
    display: flex;
    gap: 1rem;
    margin-bottom: 0.5rem;
    flex-wrap: wrap;
    align-items: center;
  }
  
  .info-item {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  
  .trigger-count {
    font-weight: 700;
    font-size: 1rem;
    color: var(--color-primary);
  }
  
  .info-label {
    font-size: 0.75rem;
    color: var(--color-text-secondary);
  }
  
  .info-value {
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    font-weight: 500;
  }
  
  .pattern-compact {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: var(--color-bg-secondary);
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    margin-bottom: 0.5rem;
  }
  
  .pattern-text {
    font-family: monospace;
    font-size: 0.75rem;
    color: var(--color-text-primary);
    flex: 1;
    word-break: break-all;
  }
  
  .actions-count {
    font-size: 0.625rem;
    color: var(--color-text-secondary);
    white-space: nowrap;
    font-weight: 500;
  }
  
  .captures-section,
  .condition-section {
    margin-bottom: 1rem;
  }
  
  .captures-section label,
  .condition-section label {
    display: block;
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    margin-bottom: 0.5rem;
  }
  
  .condition-code {
    display: block;
    background: var(--color-bg-secondary);
    padding: 0.75rem;
    border-radius: 8px;
    font-family: monospace;
    font-size: 0.875rem;
    word-break: break-all;
    border: 1px solid var(--color-border);
  }
  
  .expanded-content {
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--color-border);
    animation: slideDown 0.3s ease;
  }
  
  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  
  .captures-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  
  .capture-item {
    background: var(--color-info-bg, #e0f2fe);
    color: var(--color-info, #0369a1);
    padding: 0.25rem 0.5rem;
    border-radius: 6px;
    font-size: 0.75rem;
    font-family: monospace;
  }
  
  .details-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
  }
  
  .detail-btn {
    flex: 1;
    background: var(--color-primary);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 0.75rem;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }
  
  .detail-btn:hover {
    background: var(--color-primary-dark);
    transform: translateY(-2px);
  }
  
  @media (max-width: 768px) {
    .watcher-card {
      padding: 0.625rem;
      border-radius: 6px;
      margin-bottom: 0.625rem;
    }
    
    .card-header {
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-bottom: 0.375rem;
    }
    
    .header-left {
      flex: 1;
      min-width: 0;
    }
    
    .watcher-name {
      font-size: 0.875rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    
    .name-row {
      flex-wrap: wrap;
      gap: 0.375rem;
    }
    
    .timer-indicator {
      width: 20px;
      height: 20px;
    }
    
    .timer-indicator svg {
      width: 12px;
      height: 12px;
    }
    
    .job-link,
    .job-id {
      font-size: 0.75rem;
    }
    
    .header-actions {
      gap: 0.375rem;
    }
    
    .control-btn,
    .expand-btn {
      width: 32px;
      height: 32px;
      min-width: 32px;
      min-height: 32px;
    }
    
    .copy-btn {
      padding: 0.25rem 0.5rem;
      font-size: 0.625rem;
    }
    
    .copy-btn svg {
      width: 12px;
      height: 12px;
    }
    
    .copy-btn span {
      display: none;
    }
    
    .compact-info {
      gap: 0.75rem;
      margin-bottom: 0.375rem;
    }
    
    .trigger-count {
      font-size: 0.875rem;
    }
    
    .info-label,
    .info-value {
      font-size: 0.625rem;
    }
    
    .pattern-compact {
      padding: 0.375rem 0.5rem;
      margin-bottom: 0.375rem;
    }
    
    .pattern-text {
      font-size: 0.625rem;
    }
    
    .actions-count {
      font-size: 0.5rem;
    }
    
    .captures-section,
    .condition-section {
      margin-bottom: 0.75rem;
    }
    
    .captures-section label,
    .condition-section label {
      font-size: 0.625rem;
      margin-bottom: 0.375rem;
    }
    
    .condition-code {
      padding: 0.5rem;
      font-size: 0.75rem;
      border-radius: 6px;
      word-break: break-word;
      overflow-wrap: break-word;
    }
    
    .expanded-content {
      margin-top: 0.75rem;
      padding-top: 0.75rem;
    }
    
    .captures-list {
      gap: 0.375rem;
    }
    
    .capture-item {
      padding: 0.1875rem 0.375rem;
      font-size: 0.625rem;
      border-radius: 4px;
    }
    
    .details-actions {
      flex-direction: row;
      gap: 0.5rem;
      margin-top: 0.75rem;
    }
    
    .detail-btn {
      padding: 0.625rem 0.75rem;
      font-size: 0.75rem;
      border-radius: 6px;
      gap: 0.375rem;
    }
    
    /* Touch optimization */
    .control-btn,
    .expand-btn,
    .copy-btn,
    .detail-btn {
      -webkit-tap-highlight-color: transparent;
      touch-action: manipulation;
    }
    
    /* Improve performance */
    .watcher-card {
      will-change: auto;
      transform: translateZ(0);
    }
    
    .watcher-card:hover {
      transform: none;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
    }
    
    .watcher-card.pulse::before {
      animation: none;
      display: none;
    }
    
    /* Trigger message positioning */
    .trigger-message {
      top: 4rem;
      font-size: 0.75rem;
      padding: 0.375rem 0.75rem;
      border-radius: 4px;
    }
  }
  
  @media (max-width: 480px) {
    .compact-info {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }
    
    .watcher-card {
      padding: 0.5rem;
    }
    
    .watcher-name {
      font-size: 0.75rem;
    }
    
    .pattern-compact {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }
    
    .details-actions {
      flex-direction: column;
    }
    
    .detail-btn {
      width: 100%;
      justify-content: center;
    }
  }
</style>