<script lang="ts">
  import { run } from 'svelte/legacy';

  import { onMount, tick } from 'svelte';
  import type { WatcherEvent } from '../types/watchers';
  
  interface Props {
    events?: WatcherEvent[];
    loading?: boolean;
  }

  let { events = [], loading = false }: Props = $props();
  
  // Performance: limit initial render
  const EVENTS_PER_PAGE = 20;
  let displayedEvents = $state(EVENTS_PER_PAGE);
  let searchTerm = $state('');
  
  // Group events by watcher for better organization
  let groupedEvents = $derived(events.reduce((acc, event) => {
    const key = event.watcher_name || 'Unknown';
    if (!acc[key]) acc[key] = [];
    acc[key].push(event);
    return acc;
  }, {} as Record<string, WatcherEvent[]>));
  
  let watcherNames = $derived(Object.keys(groupedEvents));
  
  let selectedWatcher: string | null = $state(null);
  let expandedEvents: Set<string> = $state(new Set());
  
  // Initialize selected watcher after mount to prevent SSR issues
  onMount(() => {
    selectedWatcher = watcherNames[0] || null;
  });
  
  // Filter events based on search
  let filteredEvents = $derived(selectedWatcher && groupedEvents[selectedWatcher] 
    ? groupedEvents[selectedWatcher].filter(event => {
        if (!searchTerm) return true;
        const term = searchTerm.toLowerCase();
        return (
          event.action_type?.toLowerCase().includes(term) ||
          event.matched_text?.toLowerCase().includes(term) ||
          event.action_result?.toLowerCase().includes(term) ||
          event.job_id?.toLowerCase().includes(term)
        );
      })
    : []);
  
  // Paginated events for performance
  let visibleEvents = $derived(filteredEvents.slice(0, displayedEvents));
  let hasMore = $derived(displayedEvents < filteredEvents.length);
  
  function loadMore() {
    displayedEvents += EVENTS_PER_PAGE;
  }
  
  // Reset pagination when switching watchers or searching
  run(() => {
    if (selectedWatcher || searchTerm) {
      displayedEvents = EVENTS_PER_PAGE;
      expandedEvents = new Set(); // Force reactivity with new Set
    }
  });
  
  function getActionIcon(actionType: string): string {
    if (actionType.includes('metric')) return '📊';
    if (actionType.includes('checkpoint')) return '💾';
    if (actionType.includes('command')) return '⚡';
    if (actionType.includes('log')) return '📝';
    if (actionType.includes('email')) return '✉️';
    if (actionType.includes('cancel')) return '🛑';
    if (actionType.includes('resubmit')) return '🔄';
    return '•';
  }
  
  function getActionColor(actionType: string): string {
    if (actionType.includes('metric')) return '#3b82f6';
    if (actionType.includes('checkpoint')) return '#10b981';
    if (actionType.includes('command')) return '#f59e0b';
    if (actionType.includes('cancel')) return '#ef4444';
    if (actionType.includes('resubmit')) return '#8b5cf6';
    return '#6b7280';
  }
  
  function formatTimestamp(timestamp: string): string {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    
    if (diff < 60000) return 'now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h`;
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}d`;
    
    return date.toLocaleDateString('en-US', { 
      month: 'short', 
      day: 'numeric'
    });
  }
  
  function formatFullTime(timestamp: string): string {
    return new Date(timestamp).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  }
  
  function toggleEventExpansion(eventId: string) {
    if (expandedEvents.has(eventId)) {
      expandedEvents.delete(eventId);
    } else {
      expandedEvents.add(eventId);
    }
    expandedEvents = new Set(expandedEvents); // Force reactivity
  }
  
  function getEventId(event: WatcherEvent): string {
    return `${event.watcher_id}_${event.timestamp}`;
  }
</script>

{#if loading}
  <div class="loading">
    <div class="spinner"></div>
    <p>Loading events...</p>
  </div>
{:else if events.length === 0}
  <div class="empty-state">
    <div class="empty-icon">📭</div>
    <h3>No events yet</h3>
    <p>Watcher events will appear here when triggered</p>
  </div>
{:else}
  <div class="events-container">
    <!-- Header with search -->
    <div class="events-header">
      <div class="header-title">
        <h3>Events</h3>
        <span class="event-count">{events.length} total</span>
      </div>
      <input
        type="text"
        placeholder="Search events..."
        bind:value={searchTerm}
        class="search-input"
      />
    </div>
    
    <!-- Watcher tabs -->
    {#if watcherNames.length > 1}
      <div class="watcher-tabs">
        {#each watcherNames as watcherName}
          <button 
            class="watcher-tab"
            class:active={selectedWatcher === watcherName}
            onclick={() => selectedWatcher = watcherName}
          >
            {watcherName}
            <span class="tab-count">{groupedEvents[watcherName].length}</span>
          </button>
        {/each}
      </div>
    {/if}
    
    <!-- Events timeline -->
    <div class="events-timeline">
      {#if selectedWatcher && visibleEvents.length > 0}
        {#each visibleEvents as event, index}
          {@const eventId = getEventId(event)}
          {@const isExpanded = expandedEvents.has(eventId)}
          
          <div class="timeline-item">
            <div class="timeline-marker" style="background: {getActionColor(event.action_type)}">
              <span class="action-icon">{getActionIcon(event.action_type)}</span>
            </div>
            
            <div class="timeline-content">
              <button 
                class="event-card"
                class:expanded={isExpanded}
                onclick={() => toggleEventExpansion(eventId)}
              >
                <div class="event-header">
                  <div class="event-main">
                    <span class="action-type" style="color: {getActionColor(event.action_type)}">
                      {event.action_type}
                    </span>
                    <span class="job-badge">Job #{event.job_id}</span>
                    <span class="time-badge" title={formatFullTime(event.timestamp)}>
                      {formatTimestamp(event.timestamp)}
                    </span>
                  </div>
                  
                  <svg 
                    class="expand-icon"
                    class:rotated={isExpanded}
                    viewBox="0 0 24 24" 
                    fill="currentColor"
                  >
                    <path d="M7 10l5 5 5-5z"/>
                  </svg>
                </div>
                
                {#if event.matched_text && !isExpanded}
                  <div class="event-preview">
                    <code>{event.matched_text.slice(0, 100)}{event.matched_text.length > 100 ? '...' : ''}</code>
                  </div>
                {/if}
              </button>
              
              {#if isExpanded}
                <div class="event-details">
                  {#if event.matched_text}
                    <div class="detail-section">
                      <h4>Pattern Match</h4>
                      <code class="code-block">{event.matched_text}</code>
                    </div>
                  {/if}
                  
                  {#if event.captured_vars && Object.keys(event.captured_vars).length > 0}
                    <div class="detail-section">
                      <h4>Captured Variables</h4>
                      <div class="var-grid">
                        {#each Object.entries(event.captured_vars) as [key, value]}
                          <div class="var-entry">
                            <span class="var-key">{key}</span>
                            <span class="var-value">{value}</span>
                          </div>
                        {/each}
                      </div>
                    </div>
                  {/if}
                  
                  {#if event.action_result}
                    <div class="detail-section">
                      <h4>Action Result</h4>
                      <pre class="result-text">{event.action_result}</pre>
                    </div>
                  {/if}
                  
                  <div class="detail-footer">
                    <span class="timestamp">{formatFullTime(event.timestamp)}</span>
                    <span class="hostname">{event.hostname}</span>
                  </div>
                </div>
              {/if}
            </div>
          </div>
        {/each}
        
        {#if hasMore}
          <div class="load-more-container">
            <button class="load-more-btn" onclick={loadMore}>
              Load More ({filteredEvents.length - displayedEvents} remaining)
            </button>
          </div>
        {/if}
      {:else if selectedWatcher}
        <div class="no-results">
          <p>No events found {searchTerm ? `matching "${searchTerm}"` : ''}</p>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 4rem;
    color: var(--color-text-secondary);
  }
  
  .spinner {
    width: 40px;
    height: 40px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  .empty-state {
    text-align: center;
    padding: 4rem 2rem;
    color: var(--color-text-secondary);
  }
  
  .empty-icon {
    font-size: 3rem;
    margin-bottom: 1rem;
    opacity: 0.5;
  }
  
  .empty-state h3 {
    margin: 0 0 0.5rem 0;
    font-size: 1.25rem;
    color: var(--color-text-primary);
  }
  
  .empty-state p {
    margin: 0;
    font-size: 0.875rem;
  }
  
  .events-container {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  
  .events-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    background: var(--color-bg-secondary);
    border-bottom: 1px solid var(--color-border);
  }
  
  .header-title {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  
  .header-title h3 {
    margin: 0;
    font-size: 1.125rem;
    color: var(--color-text-primary);
  }
  
  .event-count {
    background: var(--color-primary);
    color: white;
    padding: 0.25rem 0.5rem;
    border-radius: 12px;
    font-size: 0.75rem;
  }
  
  .search-input {
    padding: 0.5rem 1rem;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    font-size: 0.875rem;
    width: 250px;
    background: var(--color-bg-primary);
  }
  
  .search-input:focus {
    outline: none;
    border-color: var(--color-primary);
  }
  
  .watcher-tabs {
    display: flex;
    gap: 0.5rem;
    padding: 0.5rem;
    background: var(--color-bg-secondary);
    border-radius: 8px 8px 0 0;
    border-bottom: 1px solid var(--color-border);
    overflow-x: auto;
  }
  
  .watcher-tab {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: var(--color-text-secondary);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
  }
  
  .watcher-tab:hover {
    background: var(--color-bg-primary);
    border-color: var(--color-border);
  }
  
  .watcher-tab.active {
    background: var(--color-bg-primary);
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
  
  .tab-count {
    background: var(--color-bg-secondary);
    padding: 0.125rem 0.375rem;
    border-radius: 10px;
    font-size: 0.75rem;
  }
  
  .watcher-tab.active .tab-count {
    background: var(--color-primary);
    color: white;
  }
  
  .events-timeline {
    flex: 1;
    padding: 1.5rem;
    overflow-y: auto;
    background: var(--color-bg-primary);
  }
  
  .timeline-item {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.5rem;
    position: relative;
  }
  
  /* Removed timeline connector for performance */
  
  .timeline-marker {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    position: relative;
    z-index: 1;
  }
  
  .action-icon {
    font-size: 1.25rem;
  }
  
  .timeline-content {
    flex: 1;
    min-width: 0;
  }
  
  .event-card {
    width: 100%;
    background: var(--color-bg-secondary);
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    text-align: left;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .event-card:hover {
    border-color: var(--color-primary);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }
  
  .event-card.expanded {
    border-color: var(--color-primary);
  }
  
  .event-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
  }
  
  .event-main {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }
  
  .action-type {
    font-weight: 600;
    font-size: 0.875rem;
  }
  
  .job-badge {
    background: var(--color-bg-primary);
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    color: var(--color-text-secondary);
  }
  
  .time-badge {
    color: var(--color-text-secondary);
    font-size: 0.75rem;
  }
  
  .expand-icon {
    width: 20px;
    height: 20px;
    color: var(--color-text-secondary);
    transition: transform 0.2s;
  }
  
  .expand-icon.rotated {
    transform: rotate(180deg);
  }
  
  .event-preview {
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--color-border);
  }
  
  .event-preview code {
    font-family: monospace;
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    word-break: break-all;
  }
  
  .event-details {
    margin-top: 1rem;
    padding: 1rem;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
  }
  
  .detail-section {
    margin-bottom: 1.25rem;
  }
  
  .detail-section:last-of-type {
    margin-bottom: 0.75rem;
  }
  
  .detail-section h4 {
    margin: 0 0 0.5rem 0;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #6b7280;
  }
  
  .code-block {
    display: block;
    background: #f1f5f9;
    padding: 0.75rem;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.8125rem;
    word-break: break-all;
    border: 1px solid #e2e8f0;
  }
  
  .var-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.5rem;
  }
  
  .var-entry {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--color-bg-secondary);
    padding: 0.375rem 0.625rem;
    border-radius: 4px;
    font-size: 0.8125rem;
  }
  
  .var-key {
    font-weight: 600;
    color: var(--color-primary);
  }
  
  .var-value {
    color: var(--color-text-primary);
    font-family: monospace;
  }
  
  .result-text {
    margin: 0;
    padding: 0.75rem;
    background: var(--color-bg-secondary);
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.8125rem;
    white-space: pre-wrap;
    word-break: break-all;
    border: 1px solid #e2e8f0;
    color: var(--color-text-primary);
  }
  
  .detail-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 0.75rem;
    border-top: 1px solid var(--color-border);
    font-size: 0.75rem;
    color: var(--color-text-secondary);
  }
  
  .load-more-container {
    display: flex;
    justify-content: center;
    padding: 2rem;
  }
  
  .load-more-btn {
    padding: 0.75rem 1.5rem;
    background: var(--color-primary);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
  }
  
  .load-more-btn:hover {
    background: var(--color-primary-dark);
  }
  
  .no-results {
    text-align: center;
    padding: 3rem;
    color: var(--color-text-secondary);
  }
  
  .no-results p {
    margin: 0;
    font-size: 0.875rem;
  }
  
  @media (max-width: 768px) {
    .events-timeline {
      padding: 1rem;
    }
    
    .timeline-item {
      gap: 0.75rem;
    }
    
    .timeline-marker {
      width: 32px;
      height: 32px;
    }
    
    .action-icon {
      font-size: 1rem;
    }
    
    .watcher-tabs {
      padding: 0.375rem;
    }
    
    .watcher-tab {
      padding: 0.375rem 0.75rem;
      font-size: 0.8125rem;
    }
    
    .var-grid {
      grid-template-columns: 1fr;
    }
    
    .detail-footer {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.25rem;
    }
  }
</style>