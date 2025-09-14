<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { watcherEvents, eventsLoading } from '../stores/watchers';
  import type { WatcherEvent } from '../types/watchers';
  import { Clock, Zap, Activity, Filter, ChevronRight, Search, X } from 'lucide-svelte';
  import { slide, fade, fly } from 'svelte/transition';

  // View modes for different event perspectives
  type ViewMode = 'latest' | 'by-watcher' | 'timeline';
  let viewMode: ViewMode = 'latest';

  // Filters and search
  let searchTerm = '';
  let showFilters = false;
  let timeFilter: 'all' | '1h' | '24h' | '7d' = '24h';
  let actionFilter = '';
  let successFilter: 'all' | 'success' | 'failed' = 'all';

  // Auto-refresh for latest events
  let autoRefresh = true;
  let refreshInterval: number | null = null;

  // Live event counter for dramatic effect
  let liveEventCount = 0;
  let lastEventTime: string | null = null;

  onMount(() => {
    if (autoRefresh) {
      refreshInterval = setInterval(() => {
        // Auto scroll to top when new events arrive
        updateLiveCounter();
      }, 5000);
    }
  });

  onDestroy(() => {
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
  });

  function updateLiveCounter() {
    const latestEvent = sortedEvents[0];
    if (latestEvent && lastEventTime !== latestEvent.timestamp) {
      lastEventTime = latestEvent.timestamp;
      liveEventCount++;
    }
  }

  // Smart time filtering
  function isWithinTimeFilter(timestamp: string): boolean {
    if (timeFilter === 'all') return true;

    const eventTime = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - eventTime.getTime();

    switch (timeFilter) {
      case '1h': return diffMs <= 3600000;
      case '24h': return diffMs <= 86400000;
      case '7d': return diffMs <= 604800000;
      default: return true;
    }
  }

  // Enhanced filtering and sorting
  $: filteredEvents = $watcherEvents.filter(event => {
    // Time filter
    if (!isWithinTimeFilter(event.timestamp)) return false;

    // Search filter
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      const matchText = [
        event.watcher_name,
        event.action_type,
        event.matched_text,
        event.action_result,
        event.job_id
      ].join(' ').toLowerCase();

      if (!matchText.includes(term)) return false;
    }

    // Action type filter
    if (actionFilter && !event.action_type.toLowerCase().includes(actionFilter.toLowerCase())) {
      return false;
    }

    // Success filter
    if (successFilter !== 'all') {
      const isSuccess = event.success !== false; // Assume success if not explicitly false
      if (successFilter === 'success' && !isSuccess) return false;
      if (successFilter === 'failed' && isSuccess) return false;
    }

    return true;
  });

  // Sort events by timestamp (newest first)
  $: sortedEvents = [...filteredEvents].sort((a, b) =>
    new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );

  // Group by time periods for "Latest" view
  $: eventsByTime = (() => {
    const now = new Date();
    const groups = {
      'Just now': [],
      'Last hour': [],
      'Today': [],
      'Yesterday': [],
      'This week': [],
      'Older': []
    };

    sortedEvents.forEach(event => {
      const eventTime = new Date(event.timestamp);
      const diffMs = now.getTime() - eventTime.getTime();
      const diffMinutes = diffMs / (1000 * 60);
      const diffHours = diffMinutes / 60;
      const diffDays = diffHours / 24;

      if (diffMinutes < 5) {
        groups['Just now'].push(event);
      } else if (diffHours < 1) {
        groups['Last hour'].push(event);
      } else if (diffDays < 1) {
        groups['Today'].push(event);
      } else if (diffDays < 2) {
        groups['Yesterday'].push(event);
      } else if (diffDays < 7) {
        groups['This week'].push(event);
      } else {
        groups['Older'].push(event);
      }
    });

    return groups;
  })();

  // Group by watcher for "By Watcher" view
  $: eventsByWatcher = (() => {
    const groups: Record<string, WatcherEvent[]> = {};
    sortedEvents.forEach(event => {
      const key = event.watcher_name || 'Unknown';
      if (!groups[key]) groups[key] = [];
      groups[key].push(event);
    });
    return groups;
  })();

  // Helper functions
  function formatRelativeTime(timestamp: string): string {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();

    if (diff < 60000) return 'just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`;

    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric'
    });
  }

  function getEventStatusColor(event: WatcherEvent): string {
    if (event.success === false) return '#ef4444';
    if (event.action_type.includes('error') || event.action_type.includes('fail')) return '#f59e0b';
    if (event.action_type.includes('metric')) return '#3b82f6';
    if (event.action_type.includes('checkpoint')) return '#10b981';
    return '#6b7280';
  }

  function getEventIcon(event: WatcherEvent): string {
    if (event.success === false) return '❌';
    if (event.action_type.includes('metric')) return '📊';
    if (event.action_type.includes('checkpoint')) return '💾';
    if (event.action_type.includes('email')) return '📧';
    if (event.action_type.includes('command')) return '⚡';
    if (event.action_type.includes('log')) return '📝';
    return '✅';
  }

  function clearSearch() {
    searchTerm = '';
  }

  function clearAllFilters() {
    searchTerm = '';
    timeFilter = '24h';
    actionFilter = '';
    successFilter = 'all';
    showFilters = false;
  }

  // Auto-scroll to latest events when view changes
  $: if (viewMode === 'latest') {
    setTimeout(() => {
      const container = document.querySelector('.events-content');
      if (container) {
        container.scrollTop = 0;
      }
    }, 100);
  }
</script>

<div class="modern-events-view">
  <!-- Header with live stats and controls -->
  <div class="events-header">
    <div class="header-main">
      <div class="live-indicator">
        <div class="pulse-dot"></div>
        <span class="live-text">Live Events</span>
        {#if liveEventCount > 0}
          <span class="live-count" transition:fly={{ y: -10, duration: 200 }}>
            +{liveEventCount}
          </span>
        {/if}
      </div>

      <div class="event-stats">
        <span class="stat">
          <Activity class="w-4 h-4" />
          {filteredEvents.length} events
        </span>
        <span class="stat">
          <Clock class="w-4 h-4" />
          {timeFilter === 'all' ? 'All time' : timeFilter}
        </span>
      </div>
    </div>

    <!-- View Mode Toggle -->
    <div class="view-controls">
      <div class="view-mode-toggle">
        <button
          class="mode-btn {viewMode === 'latest' ? 'mode-btn-active' : ''}"
          on:click={() => viewMode = 'latest'}
        >
          <Zap class="w-4 h-4" />
          Latest
        </button>
        <button
          class="mode-btn {viewMode === 'by-watcher' ? 'mode-btn-active' : ''}"
          on:click={() => viewMode = 'by-watcher'}
        >
          <Activity class="w-4 h-4" />
          By Watcher
        </button>
        <button
          class="mode-btn {viewMode === 'timeline' ? 'mode-btn-active' : ''}"
          on:click={() => viewMode = 'timeline'}
        >
          <Clock class="w-4 h-4" />
          Timeline
        </button>
      </div>

      <button
        class="filter-btn {showFilters ? 'filter-btn-active' : ''}"
        on:click={() => showFilters = !showFilters}
      >
        <Filter class="w-4 h-4" />
        Filters
      </button>
    </div>
  </div>

  <!-- Expandable Filters -->
  {#if showFilters}
    <div class="filters-panel" transition:slide={{ duration: 200 }}>
      <div class="filter-row">
        <div class="search-box">
          <Search class="w-4 h-4 search-icon" />
          <input
            type="text"
            placeholder="Search events..."
            bind:value={searchTerm}
            class="search-input"
          />
          {#if searchTerm}
            <button class="clear-search" on:click={clearSearch}>
              <X class="w-4 h-4" />
            </button>
          {/if}
        </div>

        <select bind:value={timeFilter} class="filter-select">
          <option value="all">All time</option>
          <option value="1h">Last hour</option>
          <option value="24h">Last 24 hours</option>
          <option value="7d">Last 7 days</option>
        </select>

        <select bind:value={successFilter} class="filter-select">
          <option value="all">All results</option>
          <option value="success">Success only</option>
          <option value="failed">Failed only</option>
        </select>

        <button class="clear-filters" on:click={clearAllFilters}>
          Clear all
        </button>
      </div>
    </div>
  {/if}

  <!-- Events Content -->
  <div class="events-content">
    {#if $eventsLoading}
      <div class="loading-state">
        <div class="spinner"></div>
        <p>Loading events...</p>
      </div>
    {:else if sortedEvents.length === 0}
      <div class="empty-state">
        <div class="empty-icon">
          <Search class="w-12 h-12 text-gray-400" />
        </div>
        <h3>No events found</h3>
        <p>Try adjusting your filters or check back later</p>
        {#if searchTerm || timeFilter !== '24h' || actionFilter || successFilter !== 'all'}
          <button class="reset-filters" on:click={clearAllFilters}>
            Reset filters
          </button>
        {/if}
      </div>
    {:else}
      <!-- Latest Events View (Default) -->
      {#if viewMode === 'latest'}
        <div class="latest-view">
          {#each Object.entries(eventsByTime) as [timeGroup, events]}
            {#if events.length > 0}
              <div class="time-group" transition:fade={{ duration: 200 }}>
                <h4 class="time-group-header">
                  {timeGroup}
                  <span class="group-count">({events.length})</span>
                </h4>

                <div class="events-grid">
                  {#each events as event}
                    <div
                      class="event-card-modern"
                      style="--accent-color: {getEventStatusColor(event)}"
                      transition:fly={{ y: 20, duration: 200 }}
                    >
                      <div class="event-card-header">
                        <div class="event-meta">
                          <span class="event-icon">{getEventIcon(event)}</span>
                          <span class="watcher-name">{event.watcher_name}</span>
                          <span class="job-badge">#{event.job_id}</span>
                        </div>
                        <span class="event-time">{formatRelativeTime(event.timestamp)}</span>
                      </div>

                      <div class="event-action">
                        <span class="action-type" style="color: {getEventStatusColor(event)}">
                          {event.action_type}
                        </span>
                      </div>

                      {#if event.matched_text}
                        <div class="event-match">
                          <code>{event.matched_text.slice(0, 80)}{event.matched_text.length > 80 ? '...' : ''}</code>
                        </div>
                      {/if}

                      {#if event.action_result}
                        <div class="event-result">
                          <span class="result-label">Result:</span>
                          <span class="result-text">
                            {event.action_result.slice(0, 100)}{event.action_result.length > 100 ? '...' : ''}
                          </span>
                        </div>
                      {/if}
                    </div>
                  {/each}
                </div>
              </div>
            {/if}
          {/each}
        </div>

      <!-- By Watcher View -->
      {:else if viewMode === 'by-watcher'}
        <div class="watcher-view">
          {#each Object.entries(eventsByWatcher) as [watcherName, events]}
            <div class="watcher-group">
              <h4 class="watcher-group-header">
                <Activity class="w-4 h-4" />
                {watcherName}
                <span class="group-count">({events.length} events)</span>
              </h4>

              <div class="watcher-events">
                {#each events.slice(0, 5) as event}
                  <div class="timeline-event">
                    <div class="timeline-marker" style="background: {getEventStatusColor(event)}"></div>
                    <div class="timeline-content">
                      <div class="timeline-header">
                        <span class="action-type">{event.action_type}</span>
                        <span class="event-time">{formatRelativeTime(event.timestamp)}</span>
                      </div>
                      {#if event.matched_text}
                        <code class="timeline-match">{event.matched_text.slice(0, 60)}...</code>
                      {/if}
                    </div>
                  </div>
                {/each}
                {#if events.length > 5}
                  <div class="more-events">
                    <span>+{events.length - 5} more events</span>
                  </div>
                {/if}
              </div>
            </div>
          {/each}
        </div>

      <!-- Timeline View -->
      {:else}
        <div class="timeline-view">
          {#each sortedEvents as event}
            <div class="timeline-item-modern">
              <div class="timeline-marker" style="background: {getEventStatusColor(event)}">
                <span class="marker-icon">{getEventIcon(event)}</span>
              </div>
              <div class="timeline-card">
                <div class="timeline-header">
                  <div class="timeline-meta">
                    <span class="watcher-name">{event.watcher_name}</span>
                    <span class="job-badge">#{event.job_id}</span>
                    <span class="action-type" style="color: {getEventStatusColor(event)}">{event.action_type}</span>
                  </div>
                  <span class="timeline-time">{formatRelativeTime(event.timestamp)}</span>
                </div>
                {#if event.matched_text}
                  <div class="timeline-match">
                    <code>{event.matched_text}</code>
                  </div>
                {/if}
                {#if event.action_result}
                  <div class="timeline-result">
                    <strong>Result:</strong> {event.action_result}
                  </div>
                {/if}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    {/if}
  </div>
</div>

<style>
  .modern-events-view {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: white;
  }

  .events-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    background: #fafafa;
    position: sticky;
    top: 0;
    z-index: 10;
  }

  .header-main {
    display: flex;
    align-items: center;
    gap: 2rem;
  }

  .live-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 600;
    color: #059669;
  }

  .pulse-dot {
    width: 8px;
    height: 8px;
    background: #10b981;
    border-radius: 50%;
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  .live-count {
    background: #10b981;
    color: white;
    border-radius: 12px;
    padding: 0.125rem 0.5rem;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .event-stats {
    display: flex;
    gap: 1rem;
  }

  .stat {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.875rem;
    color: #6b7280;
  }

  .view-controls {
    display: flex;
    gap: 1rem;
    align-items: center;
  }

  .view-mode-toggle {
    display: flex;
    background: #f3f4f6;
    border-radius: 8px;
    padding: 0.25rem;
  }

  .mode-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: none;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.2s;
  }

  .mode-btn:hover {
    color: #374151;
    background: #e5e7eb;
  }

  .mode-btn-active {
    color: #3b82f6;
    background: white;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  .filter-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.875rem;
    color: #374151;
    cursor: pointer;
    transition: all 0.2s;
  }

  .filter-btn:hover {
    border-color: #9ca3af;
  }

  .filter-btn-active {
    background: #3b82f6;
    color: white;
    border-color: #3b82f6;
  }

  .filters-panel {
    padding: 1rem 1.5rem;
    background: #f8fafc;
    border-bottom: 1px solid #e5e7eb;
  }

  .filter-row {
    display: flex;
    gap: 1rem;
    align-items: center;
    flex-wrap: wrap;
  }

  .search-box {
    position: relative;
    flex: 1;
    min-width: 200px;
  }

  .search-icon {
    position: absolute;
    left: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
    color: #9ca3af;
  }

  .search-input {
    width: 100%;
    padding: 0.5rem 0.75rem 0.5rem 2.25rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.875rem;
  }

  .search-input:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .clear-search {
    position: absolute;
    right: 0.5rem;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    color: #9ca3af;
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 4px;
  }

  .clear-search:hover {
    color: #6b7280;
    background: #f3f4f6;
  }

  .filter-select {
    padding: 0.5rem 0.75rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.875rem;
    background: white;
    cursor: pointer;
  }

  .filter-select:focus {
    outline: none;
    border-color: #3b82f6;
  }

  .clear-filters {
    padding: 0.5rem 0.75rem;
    background: #ef4444;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    cursor: pointer;
    transition: background 0.2s;
  }

  .clear-filters:hover {
    background: #dc2626;
  }

  .events-content {
    flex: 1;
    overflow-y: auto;
    padding: 1rem 1.5rem;
  }

  .loading-state,
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 200px;
    color: #6b7280;
  }

  .spinner {
    width: 24px;
    height: 24px;
    border: 2px solid #e5e7eb;
    border-left-color: #3b82f6;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .empty-icon {
    margin-bottom: 1rem;
    display: flex;
    justify-content: center;
  }

  .reset-filters {
    margin-top: 1rem;
    padding: 0.5rem 1rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
  }

  /* Latest View Styles */
  .latest-view {
    space-y: 2rem;
  }

  .time-group {
    margin-bottom: 2rem;
  }

  .time-group-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1rem;
    font-size: 1.125rem;
    font-weight: 600;
    color: #111827;
  }

  .group-count {
    font-size: 0.875rem;
    color: #6b7280;
    font-weight: 400;
  }

  .events-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 1rem;
  }

  .event-card-modern {
    background: white;
    border: 1px solid #e5e7eb;
    border-left: 4px solid var(--accent-color);
    border-radius: 8px;
    padding: 1rem;
    transition: all 0.2s;
  }

  .event-card-modern:hover {
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    transform: translateY(-1px);
  }

  .event-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .event-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .event-icon {
    font-size: 1rem;
  }

  .watcher-name {
    font-weight: 500;
    color: #111827;
  }

  .job-badge {
    background: #f3f4f6;
    color: #6b7280;
    padding: 0.125rem 0.5rem;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
  }

  .event-time {
    font-size: 0.75rem;
    color: #9ca3af;
  }

  .event-action {
    margin-bottom: 0.5rem;
  }

  .action-type {
    font-weight: 500;
    font-size: 0.875rem;
  }

  .event-match {
    background: #f8fafc;
    padding: 0.5rem;
    border-radius: 6px;
    margin-bottom: 0.5rem;
  }

  .event-match code {
    font-size: 0.75rem;
    color: #374151;
  }

  .event-result {
    font-size: 0.75rem;
    color: #6b7280;
  }

  .result-label {
    font-weight: 500;
  }

  /* Watcher View Styles */
  .watcher-view {
    space-y: 1.5rem;
  }

  .watcher-group {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    overflow: hidden;
  }

  .watcher-group-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: #f8fafc;
    padding: 1rem;
    margin: 0;
    font-weight: 600;
    color: #111827;
  }

  .watcher-events {
    padding: 1rem;
  }

  .timeline-event {
    display: flex;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .timeline-marker {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    margin-top: 0.25rem;
    flex-shrink: 0;
  }

  .timeline-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.25rem;
  }

  .timeline-match {
    font-size: 0.75rem;
    color: #6b7280;
    background: #f8fafc;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    margin-top: 0.25rem;
  }

  .more-events {
    text-align: center;
    padding: 0.5rem;
    color: #6b7280;
    font-size: 0.875rem;
    border-top: 1px solid #f3f4f6;
    margin-top: 1rem;
  }

  /* Timeline View Styles */
  .timeline-view {
    max-width: 800px;
    margin: 0 auto;
  }

  .timeline-item-modern {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .timeline-item-modern .timeline-marker {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 0.5rem;
    flex-shrink: 0;
  }

  .marker-icon {
    font-size: 0.875rem;
  }

  .timeline-card {
    flex: 1;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1rem;
  }

  .timeline-meta {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }

  .timeline-time {
    font-size: 0.75rem;
    color: #9ca3af;
  }

  .timeline-result {
    margin-top: 0.5rem;
    font-size: 0.875rem;
    color: #6b7280;
  }

  /* Mobile responsiveness */
  @media (max-width: 768px) {
    .events-header {
      flex-direction: column;
      gap: 1rem;
      align-items: stretch;
    }

    .header-main {
      flex-direction: column;
      gap: 1rem;
    }

    .view-controls {
      justify-content: center;
    }

    .filter-row {
      flex-direction: column;
      align-items: stretch;
    }

    .search-box {
      min-width: auto;
    }

    .events-grid {
      grid-template-columns: 1fr;
    }

    .timeline-item-modern {
      gap: 0.5rem;
    }

    .timeline-meta {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.25rem;
    }
  }
</style>