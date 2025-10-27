<script lang="ts">
  import { stopPropagation } from 'svelte/legacy';

  import { createEventDispatcher } from 'svelte';
  import { push, location } from 'svelte-spa-router';
  import { navigationActions } from '../stores/navigation';
  import type { Watcher } from '../types/watchers';
  import { pauseWatcher, resumeWatcher } from '../stores/watchers';
  import { api } from '../services/api';
  import WatcherDetailDialog from './WatcherDetailDialog.svelte';
  import { portal } from '../lib/actions/portal';
  
  interface Props {
    watcher: Watcher;
    jobInfo?: any;
    showJobLink?: boolean;
    lastEvent?: any; // Latest event for this watcher
  }

  let {
    watcher,
    jobInfo = null,
    showJobLink = true,
    lastEvent = null
  }: Props = $props();
  
  const dispatch = createEventDispatcher();
  
  // State management
  let isExpanded = $state(false);
  let isPausing = $state(false);
  let isTriggering = $state(false);
  let triggerMessage = $state('');
  let showDetailDialog = $state(false);
  
  // Real-time pulse animation for active watchers
  let isActive = $derived(watcher.state === 'active');
  let pulseClass = $derived(isActive ? 'pulse' : '');
  
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
      case 'static': return '▶';  // Play icon for static watchers
      case 'completed': return '✓';
      case 'failed': return '×';
      default: return '○';
    }
  }

  function getStateColor(state: string): string {
    switch (state) {
      case 'active': return '#10b981';
      case 'paused': return '#f59e0b';
      case 'static': return '#8b5cf6';  // Purple for static watchers
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

  function getActionTypeDisplay(action: any): string {
    if (!action.type) return 'Unknown';
    const type = action.type.toLowerCase();
    if (type.includes('metric')) return 'Metrics';
    if (type.includes('email')) return 'Email';
    if (type.includes('log')) return 'Log';
    if (type.includes('command')) return 'Command';
    if (type.includes('checkpoint')) return 'Checkpoint';
    return action.type;
  }

  function getActionDescription(action: any): string {
    if (!action.params) return '';
    const params = action.params;

    if (action.type.includes('email') && params.subject) {
      return `"${params.subject}"`;
    }
    if (action.type.includes('command') && params.command) {
      return `${params.command.substring(0, 40)}...`;
    }
    if (action.type.includes('log') && params.message) {
      return `"${params.message.substring(0, 40)}..."`;
    }
    if (action.type.includes('metric') && params.name) {
      return params.name;
    }
    return '';
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
    // Allow triggering for both ACTIVE and STATIC watchers
    if (isTriggering || (watcher.state !== 'active' && watcher.state !== 'static')) return;
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
    // Track where we're coming from for smart back navigation
    navigationActions.setPreviousRoute($location);
    // Navigate to the job details page with URL encoding
    const encodedJobId = encodeURIComponent(watcher.job_id);
    push(`/jobs/${encodedJobId}/${watcher.hostname}`);
  }
  
  function viewDetails() {
    // Navigate to watchers page with Events tab selected and filtered by this watcher
    push(`/watchers?tab=events&watcher=${watcher.id}`);
  }
  
  function copyWatcher() {
    // Create watcher config including job info
    const watcherConfig = {
      name: watcher.name,
      pattern: watcher.pattern,
      captures: watcher.captures || [],
      interval: watcher.interval_seconds,
      condition: watcher.condition,
      actions: watcher.actions || [],
      timer_mode_enabled: watcher.timer_mode_enabled || false,
      timer_interval_seconds: watcher.timer_interval_seconds || 30,
      // Include original job info for better copy experience
      job_id: watcher.job_id,
      hostname: watcher.hostname
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
  let activityPercentage = $derived(Math.min((watcher.trigger_count / 100) * 100, 100));
  
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

<div class="bg-white border border-gray-200 rounded-md p-2.5 mb-2 transition-all duration-300 relative overflow-hidden cursor-pointer hover:shadow-lg hover:-translate-y-0.5 w-full {pulseClass} {isExpanded ? 'expanded' : ''}" onclick={() => isExpanded = !isExpanded} role="button" tabindex="0" onkeydown={(e) => { if (e.key === 'Enter') isExpanded = !isExpanded; }}>
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
  <div class="flex justify-between items-start mb-1.5 gap-2">
    <div class="flex items-start gap-2 flex-1 min-w-0">
      <span class="text-xl leading-none mt-0.5 flex-shrink-0" style="color: {getStateColor(watcher.state)}">
        {getStateIcon(watcher.state)}
      </span>
      <div class="flex flex-col gap-0.5 min-w-0 flex-1">
        <div class="flex items-center gap-2 min-w-0 w-full">
          <h3 class="m-0 text-sm font-semibold text-gray-900 overflow-hidden text-ellipsis whitespace-nowrap flex-1 min-w-0">{watcher.name}</h3>
        </div>
{#if showJobLink && jobInfo}
          <button class="job-link" onclick={navigateToJob}>
            {#if watcher.job_name && watcher.job_name !== 'N/A'}
              Job #{watcher.job_id} - {watcher.job_name}
            {:else}
              Job #{watcher.job_id}
            {/if}
          </button>
        {:else if watcher.job_name && watcher.job_name !== 'N/A'}
          <span class="job-id" title="{watcher.job_name}">Job #{watcher.job_id} - {watcher.job_name}</span>
        {:else}
          <span class="job-id">Job #{watcher.job_id}</span>
        {/if}
      </div>
    </div>
    
    <div class="flex items-start gap-2 flex-shrink-0">
      {#if watcher.state === 'static'}
        <div class="static-indicator" title="Static watcher - runs on manual trigger only (for completed/canceled jobs)">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M9.5 6.5v11l8-5.5-8-5.5z"/>
          </svg>
          <span class="text-xs">Static</span>
        </div>
      {/if}
      {#if watcher.timer_mode_enabled}
        <div class="timer-indicator" class:active={watcher.timer_mode_active} title="Timer Mode {watcher.timer_mode_active ? 'Active' : 'Enabled'}">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M15,1H9V3H15M11,14H13V8H11M19.03,7.39L20.45,5.97C20,5.46 19.55,5 19.04,4.56L17.62,6C16.07,4.74 14.12,4 12,4A9,9 0 0,0 3,13A9,9 0 0,0 12,22C17,22 21,17.97 21,13C21,10.88 20.26,8.93 19.03,7.39Z"/>
          </svg>
        </div>
      {/if}
      
      
      <button
        id="copy-btn-{watcher.id}"
        class="copy-btn"
        onclick={stopPropagation(copyWatcher)}
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
          onclick={stopPropagation(togglePause)}
          disabled={isPausing}
          title={watcher.state === 'active' ? 'Pause watcher' : 'Resume watcher'}
        >
          {#if isPausing}
            <svg class="spinner-icon" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="31.4" stroke-dashoffset="10"/>
            </svg>
          {:else if watcher.state === 'active'}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <rect x="8" y="8" width="2.5" height="8" rx="0.5" />
              <rect x="13.5" y="8" width="2.5" height="8" rx="0.5" />
            </svg>
          {:else}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M9.5 6.5v11l8-5.5-8-5.5z"/>
            </svg>
          {/if}
        </button>
      {/if}
      
      {#if watcher.state === 'active' || watcher.state === 'static'}
        <button
          class="control-btn"
          class:triggering={isTriggering}
          onclick={stopPropagation(triggerManually)}
          disabled={isTriggering}
          title={watcher.state === 'static' ? 'Run watcher (static mode - runs on trigger only)' : 'Manually trigger watcher'}>
          {#if isTriggering}
            <svg class="spinner-icon" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="31.4" stroke-dashoffset="10"/>
            </svg>
          {:else}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M9.5 6.5v11l8-5.5-8-5.5z"/>
            </svg>
          {/if}
        </button>
      {/if}
      
      <button
        class="edit-btn"
        onclick={stopPropagation(openDetailDialog)}
        title="Edit watcher"
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
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
          <span class="section-label">Capture Groups</span>
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
          <span class="section-label">Condition</span>
          <code class="condition-code">{watcher.condition}</code>
        </div>
      {/if}
      
      <!-- Actions Preview -->
      {#if watcher.actions && watcher.actions.length > 0}
        <div class="actions-section">
          <span class="section-label">Actions ({watcher.actions.length})</span>
          <div class="actions-preview">
            {#each watcher.actions as action, i}
              <div class="action-item">
                <span class="action-icon">{getActionIcon(action.type)}</span>
                <div class="action-details">
                  <span class="action-type">{getActionTypeDisplay(action)}</span>
                  {#if getActionDescription(action)}
                    <span class="action-desc">{getActionDescription(action)}</span>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        </div>
      {/if}

      <!-- Last Trigger Result -->
      {#if lastEvent}
        <div class="last-trigger-section">
          <span class="section-label">Last Trigger</span>
          <div class="trigger-result">
            <div class="trigger-header">
              <span class="trigger-time">{formatTime(lastEvent.timestamp)}</span>
              <span class="trigger-status {lastEvent.success ? 'success' : 'failed'}">
                {lastEvent.success ? '✓ Success' : '✗ Failed'}
              </span>
            </div>
            {#if lastEvent.matched_text}
              <div class="matched-text">
                <span class="label">Match:</span>
                <code>{lastEvent.matched_text.length > 100 ? lastEvent.matched_text.substring(0, 100) + '...' : lastEvent.matched_text}</code>
              </div>
            {/if}
            {#if lastEvent.action_result}
              <div class="action-result">
                <span class="label">Result:</span>
                <code>{lastEvent.action_result.length > 150 ? lastEvent.action_result.substring(0, 150) + '...' : lastEvent.action_result}</code>
              </div>
            {/if}
            {#if lastEvent.captured_vars && Object.keys(lastEvent.captured_vars).length > 0}
              <div class="captured-vars">
                <span class="label">Variables:</span>
                <div class="vars-list">
                  {#each Object.entries(lastEvent.captured_vars) as [key, value]}
                    <span class="var-item">${key}: {value}</span>
                  {/each}
                </div>
              </div>
            {/if}
          </div>
        </div>
      {/if}

      <div class="details-actions">
        <button class="detail-btn" onclick={viewDetails}>
          View All Events
        </button>
        {#if showJobLink}
          <button class="detail-btn" onclick={navigateToJob}>
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
    background: var(--background);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.625rem;
    margin-bottom: 0.5rem;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
    cursor: pointer;
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
    align-items: flex-start;
    margin-bottom: 0.375rem;
    gap: 0.5rem;
  }
  
  .header-left {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    flex: 1;
    min-width: 0;
  }
  
  .state-indicator {
    font-size: 1.25rem;
    line-height: 1;
    margin-top: 0.125rem;
    flex-shrink: 0;
  }
  
  .watcher-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    min-width: 0;
    flex: 1;
  }
  
  .name-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  
  .watcher-name {
    margin: 0;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--foreground);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .static-indicator {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 12px;
    background: #f3e8ff;
    color: #8b5cf6;
    font-weight: 500;
    font-size: 0.75rem;
    flex-shrink: 0;
  }

  .static-indicator svg {
    width: 12px;
    height: 12px;
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
    flex-shrink: 0;
  }

  .timer-indicator.active {
    background: #dbeafe;
    color: #1d4ed8;
    animation: timer-pulse 2s infinite;
  }

  .timer-indicator svg {
    width: 16px;
    height: 16px;
  }

  @keyframes timer-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }
  
  .job-link {
    background: none;
    border: none;
    color: var(--accent);
    font-size: 0.75rem;
    cursor: pointer;
    padding: 0;
    text-align: left;
    text-decoration: underline;
    text-decoration-style: dotted;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }
  
  .job-link:hover {
    text-decoration-style: solid;
  }
  
  .job-id {
    color: var(--muted-foreground);
    font-size: 0.75rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .header-actions {
    display: flex;
    gap: 0.25rem;
    flex-shrink: 0;
    align-items: flex-start;
  }
  
  .control-btn,
  .expand-btn,
  .edit-btn,
  .detail-btn,
  .copy-btn {
    background: white;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0;
    width: 24px;
    height: 24px;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted-foreground);
    font-size: 0;
  }
  
  .detail-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    padding: 0;
  }
  
  .detail-btn:hover {
    background: #eff6ff;
    border-color: #3b82f6;
    color: #3b82f6;
  }
  
  .copy-btn span {
    display: none !important; /* Hide text in compact mode */
  }
  
  .control-btn svg,
  .expand-btn svg,
  .detail-btn svg {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  .copy-btn svg {
    width: 12px;
    height: 12px;
  }
  
  .control-btn:hover:not(:disabled) {
    background: var(--error-bg);
    border-color: var(--error);
    color: var(--error);
  }
  
  .control-btn.resume:hover:not(:disabled) {
    background: var(--success-bg);
    border-color: var(--success);
    color: var(--success);
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
  

  .edit-btn {
    background: white;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0;
    width: 24px;
    height: 24px;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted-foreground);
    font-size: 0;
  }

  .edit-btn svg {
    width: 13px;
    height: 13px;
    flex-shrink: 0;
  }

  .edit-btn:hover {
    background: #eff6ff;
    border-color: #3b82f6;
    color: #3b82f6;
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
    font-weight: 600;
    font-size: 0.875rem;
    color: var(--accent);
  }
  
  .info-label {
    font-size: 0.75rem;
    color: var(--muted-foreground);
  }
  
  .info-value {
    font-size: 0.75rem;
    color: var(--muted-foreground);
    font-weight: 500;
  }

  .job-name-truncated {
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-style: italic;
    color: var(--accent) !important;
  }
  
  .pattern-compact {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: var(--secondary);
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    margin-bottom: 0.5rem;
  }
  
  .pattern-text {
    font-family: monospace;
    font-size: 0.75rem;
    color: var(--foreground);
    flex: 1;
    word-break: break-all;
  }
  
  .actions-count {
    font-size: 0.625rem;
    color: var(--muted-foreground);
    white-space: nowrap;
    font-weight: 500;
  }
  
  .captures-section,
  .condition-section {
    margin-bottom: 1rem;
  }

  .captures-section .section-label,
  .condition-section .section-label {
    display: block;
    font-size: 0.75rem;
    color: var(--muted-foreground);
    margin-bottom: 0.5rem;
  }
  
  .condition-code {
    display: block;
    background: var(--secondary);
    padding: 0.75rem;
    border-radius: 8px;
    font-family: monospace;
    font-size: 0.875rem;
    word-break: break-all;
    border: 1px solid var(--border);
  }
  
  .expanded-content {
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
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
    background: var(--info-bg);
    color: var(--info);
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
    background: var(--accent);
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
    background: var(--accent);
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
      width: 22px;
      height: 22px;
    }

    .timer-indicator svg {
      width: 14px;
      height: 14px;
    }
    
    .job-link,
    .job-id {
      font-size: 0.75rem;
    }
    
    .header-actions {
      gap: 0.375rem;
    }
    
    .control-btn,
    .expand-btn,
    .edit-btn {
      width: 28px;
      height: 28px;
      min-width: 28px;
      min-height: 28px;
    }

    .edit-btn svg {
      width: 14px;
      height: 14px;
    }

    .copy-btn {
      padding: 0;
      width: 28px;
      height: 28px;
      min-width: 28px;
      min-height: 28px;
      font-size: 0.625rem;
    }

    .copy-btn span {
      display: none; /* Hide text on mobile, icon only */
    }

    .copy-btn svg {
      width: 12px;
      height: 12px;
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

    .captures-section .section-label,
    .condition-section .section-label {
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
    .edit-btn,
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

  /* Actions Preview Styles */
  .actions-section {
    margin: 1rem 0;
    padding-top: 1rem;
    border-top: 1px solid #e2e8f0;
  }

  .actions-section .section-label {
    display: block;
    font-size: 0.875rem;
    font-weight: 600;
    color: #374151;
    margin-bottom: 0.5rem;
  }

  .actions-preview {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .action-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 0.75rem;
    background: #f1f5f9;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
  }

  .action-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.5rem;
    height: 1.5rem;
    background: #3b82f6;
    color: white;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .action-details {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    flex: 1;
  }

  .action-type {
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
  }

  .action-desc {
    font-size: 0.75rem;
    color: #6b7280;
    font-family: 'SF Mono', 'Monaco', 'Cascadia Code', 'Roboto Mono', monospace;
  }

  /* Last Trigger Result Styles */
  .last-trigger-section {
    margin: 1rem 0;
    padding-top: 1rem;
    border-top: 1px solid #e2e8f0;
  }

  .last-trigger-section .section-label {
    display: block;
    font-size: 0.875rem;
    font-weight: 600;
    color: #374151;
    margin-bottom: 0.5rem;
  }

  .trigger-result {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 0.75rem;
  }

  .trigger-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .trigger-time {
    font-size: 0.75rem;
    color: #6b7280;
  }

  .trigger-status {
    font-size: 0.75rem;
    font-weight: 500;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
  }

  .trigger-status.success {
    color: #059669;
    background: #ecfdf5;
  }

  .trigger-status.failed {
    color: #dc2626;
    background: #fef2f2;
  }

  .matched-text, .action-result, .captured-vars {
    margin-bottom: 0.5rem;
  }

  .matched-text:last-child, .action-result:last-child, .captured-vars:last-child {
    margin-bottom: 0;
  }

  .label {
    font-size: 0.75rem;
    font-weight: 500;
    color: #374151;
    margin-right: 0.5rem;
  }

  .matched-text code, .action-result code {
    font-size: 0.75rem;
    background: #f1f5f9;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    border: 1px solid #e2e8f0;
    word-break: break-all;
    display: inline-block;
    max-width: 100%;
  }

  .vars-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    margin-top: 0.25rem;
  }

  .var-item {
    font-size: 0.75rem;
    background: #dbeafe;
    color: #1e40af;
    padding: 0.125rem 0.375rem;
    border-radius: 4px;
    font-family: 'SF Mono', 'Monaco', 'Cascadia Code', 'Roboto Mono', monospace;
  }
</style>