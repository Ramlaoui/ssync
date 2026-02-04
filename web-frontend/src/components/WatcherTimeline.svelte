<script lang="ts">
  import { run } from 'svelte/legacy';

  import { onMount, onDestroy } from 'svelte';
  import type { WatcherEvent } from '../types/watchers';
  
  interface Props {
    events?: WatcherEvent[];
    maxEvents?: number;
    autoScroll?: boolean;
  }

  let { events = [], maxEvents = 50, autoScroll = $bindable(true) }: Props = $props();
  
  // Timeline state
  let timelineElement: HTMLDivElement | null = $state(null);
  let hoveredEvent: WatcherEvent | null = $state(null);
  let selectedTimeRange = $state('1h'); // 1h, 6h, 24h, all
  let tooltipX = $state(0);
  let tooltipY = $state(0);
  
  // Real-time updates
  let animationFrame: number;
  let timeNow = new Date();
  
  
  
  function filterEventsByTime(events: WatcherEvent[], range: string): WatcherEvent[] {
    const now = new Date();
    let cutoffTime: Date;
    
    switch (range) {
      case '1h':
        cutoffTime = new Date(now.getTime() - 60 * 60 * 1000);
        break;
      case '6h':
        cutoffTime = new Date(now.getTime() - 6 * 60 * 60 * 1000);
        break;
      case '24h':
        cutoffTime = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        break;
      default:
        return events.slice(0, maxEvents);
    }
    
    return events
      .filter(e => new Date(e.timestamp) >= cutoffTime)
      .slice(0, maxEvents);
  }
  
  function groupEventsByTime(events: WatcherEvent[]): Map<string, WatcherEvent[]> {
    const groups = new Map<string, WatcherEvent[]>();
    
    events.forEach(event => {
      const date = new Date(event.timestamp);
      const hours = date.getHours().toString().padStart(2, '0');
      const minutes = (Math.floor(date.getMinutes() / 5) * 5).toString().padStart(2, '0');
      const key = `${hours}:${minutes}`;
      
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key)!.push(event);
    });
    
    return groups;
  }
  
  function getEventColor(event: WatcherEvent): string {
    if (!event.success) return 'var(--destructive)';
    if (event.action_type.includes('metric')) return 'var(--accent)';
    if (event.action_type.includes('warning')) return 'var(--warning)';
    if (event.action_type.includes('checkpoint')) return 'var(--success)';
    return 'var(--muted-foreground)';
  }
  
  function getEventIcon(event: WatcherEvent): string {
    if (!event.success) return '×';
    if (event.action_type.includes('metric')) return 'M';
    if (event.action_type.includes('warning')) return '!';
    if (event.action_type.includes('checkpoint')) return '✓';
    if (event.action_type.includes('email')) return '@';
    return '•';
  }
  
  function formatTimestamp(timestamp: string): string {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  }
  
  function getRelativeTime(timestamp: string): string {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSeconds = Math.floor(diffMs / 1000);
    const diffMinutes = Math.floor(diffSeconds / 60);
    const diffHours = Math.floor(diffMinutes / 60);
    
    if (diffSeconds < 60) return `${diffSeconds}s ago`;
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${Math.floor(diffHours / 24)}d ago`;
  }
  
  // Update time periodically
  function updateTime() {
    timeNow = new Date();
  }
  
  // Auto-scroll to latest events
  function scrollToLatest() {
    if (timelineElement && autoScroll) {
      timelineElement.scrollTo({
        left: timelineElement.scrollWidth,
        behavior: 'smooth'
      });
    }
  }
  
  // Handle mouse move for tooltip positioning
  function handleMouseEnter(event: MouseEvent, eventData: WatcherEvent) {
    hoveredEvent = eventData;
    updateTooltipPosition(event);
  }
  
  function updateTooltipPosition(event: MouseEvent) {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    tooltipX = rect.left + rect.width / 2;
    tooltipY = rect.top - 10;
    
    // Adjust for viewport boundaries
    const tooltipWidth = 300;
    const tooltipHeight = 200;
    
    if (tooltipX + tooltipWidth / 2 > window.innerWidth) {
      tooltipX = window.innerWidth - tooltipWidth / 2 - 10;
    }
    if (tooltipX - tooltipWidth / 2 < 0) {
      tooltipX = tooltipWidth / 2 + 10;
    }
    if (tooltipY - tooltipHeight < 0) {
      tooltipY = rect.bottom + 10;
    }
  }
  
  onMount(() => {
    updateTime();
    scrollToLatest();
    const interval = setInterval(updateTime, 5000);
    
    return () => clearInterval(interval);
  });
  
  // Filter events by time range
  let filteredEvents = $derived(filterEventsByTime(events, selectedTimeRange));
  // Group events by minute for visualization
  let eventGroups = $derived(groupEventsByTime(filteredEvents));
  // Scroll when new events arrive
  run(() => {
    if (events.length && autoScroll) {
      scrollToLatest();
    }
  });
</script>

<div class="timeline-container">
  <div class="timeline-header">
    <h3>Activity Timeline</h3>
    <div class="timeline-controls">
      <div class="time-range-selector">
        {#each ['1h', '6h', '24h', 'all'] as range}
          <button 
            class="range-btn"
            class:active={selectedTimeRange === range}
            onclick={() => selectedTimeRange = range}
          >
            {range === 'all' ? 'All' : `Last ${range}`}
          </button>
        {/each}
      </div>
      <label class="auto-scroll">
        <input 
          type="checkbox" 
          bind:checked={autoScroll}
        />
        Auto-scroll
      </label>
    </div>
  </div>
  
  <div class="timeline-wrapper">
    <div class="timeline" bind:this={timelineElement}>
      <!-- Event track with bubbles -->
      <div class="event-track">
        {#each filteredEvents as event, i}
          <div 
            class="event-bubble"
            class:failed={!event.success}
            style="
              background: {getEventColor(event)};
              left: {(i / Math.max(filteredEvents.length - 1, 1)) * 90}%;
            "
            onmouseenter={(e) => handleMouseEnter(e, event)}
            onmouseleave={() => hoveredEvent = null}
            role="presentation"
            aria-hidden="true"
          >
            <span class="event-icon">{getEventIcon(event)}</span>
          </div>
        {/each}
        
        <!-- Live pulse indicator -->
        <div class="live-indicator">
          <span class="live-dot"></span>
        </div>
      </div>
      
      <!-- Time axis below events -->
      <div class="time-axis">
        {#if filteredEvents.length > 0}
          <div class="time-marker start">
            {formatTimestamp(filteredEvents[0].timestamp)}
          </div>
          {#if filteredEvents.length > 1}
            <div class="time-marker middle">
              {formatTimestamp(filteredEvents[Math.floor(filteredEvents.length / 2)].timestamp)}
            </div>
          {/if}
          <div class="time-marker end">Now</div>
        {:else}
          <div class="time-marker">No events</div>
        {/if}
      </div>
    </div>
  </div>
  
  <!-- Tooltip rendered outside timeline -->
  {#if hoveredEvent}
    <div 
      class="event-tooltip"
      style="
        left: {tooltipX}px;
        top: {tooltipY}px;
        transform: translate(-50%, -100%);
      "
    >
      <div class="tooltip-header">
        <strong>{hoveredEvent.watcher_name}</strong>
        <span class="tooltip-time">{getRelativeTime(hoveredEvent.timestamp)}</span>
      </div>
      <div class="tooltip-body">
        <div class="tooltip-row">
          <span class="label">Job:</span>
          <span>#{hoveredEvent.job_id}</span>
        </div>
        <div class="tooltip-row">
          <span class="label">Action:</span>
          <span>{hoveredEvent.action_type}</span>
        </div>
        {#if hoveredEvent.matched_text}
          <div class="tooltip-row">
            <span class="label">Matched:</span>
            <code>{hoveredEvent.matched_text.substring(0, 50)}{hoveredEvent.matched_text.length > 50 ? '...' : ''}</code>
          </div>
        {/if}
        {#if hoveredEvent.captured_vars && Object.keys(hoveredEvent.captured_vars).length > 0}
          <div class="tooltip-row">
            <span class="label">Captured:</span>
            <span>{Object.keys(hoveredEvent.captured_vars).join(', ')}</span>
          </div>
        {/if}
        <div class="tooltip-status" class:success={hoveredEvent.success}>
          {hoveredEvent.success ? '✓ Success' : '× Failed'}
        </div>
      </div>
    </div>
  {/if}
  
  <!-- Event summary stats -->
  <div class="timeline-stats">
    <div class="stat-item">
      <span class="stat-value">{filteredEvents.length}</span>
      <span class="stat-label">Events</span>
    </div>
    <div class="stat-item">
      <span class="stat-value success">
        {filteredEvents.filter(e => e.success).length}
      </span>
      <span class="stat-label">Success</span>
    </div>
    <div class="stat-item">
      <span class="stat-value failed">
        {filteredEvents.filter(e => !e.success).length}
      </span>
      <span class="stat-label">Failed</span>
    </div>
    <div class="stat-item">
      <span class="stat-value">
        {new Set(filteredEvents.map(e => e.watcher_id)).size}
      </span>
      <span class="stat-label">Watchers</span>
    </div>
  </div>
</div>

<style>
  .timeline-container {
    background: var(--background);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }
  
  .timeline-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
  }
  
  .timeline-header h3 {
    margin: 0;
    font-size: 1.25rem;
    color: var(--foreground);
  }
  
  .timeline-controls {
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  
  .time-range-selector {
    display: flex;
    gap: 0.25rem;
    background: var(--secondary);
    padding: 0.25rem;
    border-radius: 8px;
  }
  
  .range-btn {
    background: none;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
    color: var(--muted-foreground);
  }
  
  .range-btn:hover {
    background: white;
  }
  
  .range-btn.active {
    background: var(--accent);
    color: white;
  }
  
  .auto-scroll {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    color: var(--muted-foreground);
  }
  
  .timeline-wrapper {
    position: relative;
    margin-bottom: 1.5rem;
  }
  
  .timeline {
    position: relative;
    height: 100px;
    overflow-x: auto;
    overflow-y: hidden;
    background: var(--secondary);
    border-radius: 8px;
    padding: 1rem 1rem 2rem 1rem;
  }
  
  .time-axis {
    position: absolute;
    bottom: 0;
    left: 1rem;
    right: 1rem;
    height: 25px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid var(--border);
    padding-top: 0.25rem;
  }
  
  .time-marker {
    font-size: 0.7rem;
    color: var(--muted-foreground);
    white-space: nowrap;
  }
  
  .time-marker.start {
    text-align: left;
  }
  
  .time-marker.middle {
    text-align: center;
  }
  
  .time-marker.end {
    text-align: right;
    color: var(--accent);
    font-weight: 600;
  }
  
  .event-track {
    position: relative;
    height: 50px;
    margin-bottom: 0.5rem;
  }
  
  .event-bubble {
    position: absolute;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.3s;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }
  
  
  .event-bubble:hover {
    transform: scale(1.2);
    z-index: 10;
  }
  
  .event-bubble.failed {
    border: 2px solid var(--destructive);
  }
  
  .event-icon {
    font-size: 1rem;
  }
  
  .event-tooltip {
    position: fixed;
    background: white;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.75rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    min-width: 250px;
    max-width: 350px;
    pointer-events: none;
  }
  
  .event-tooltip::after {
    content: '';
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border-width: 6px;
    border-style: solid;
    border-color: white transparent transparent transparent;
  }
  
  .tooltip-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.5rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
  }
  
  .tooltip-time {
    font-size: 0.75rem;
    color: var(--muted-foreground);
  }
  
  .tooltip-row {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.25rem;
    font-size: 0.875rem;
  }
  
  .tooltip-row .label {
    color: var(--muted-foreground);
    min-width: 60px;
  }
  
  .tooltip-row code {
    background: var(--secondary);
    padding: 0.125rem 0.25rem;
    border-radius: 4px;
    font-size: 0.75rem;
  }
  
  .tooltip-status {
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border);
    text-align: center;
    font-weight: 500;
    color: var(--error);
  }
  
  .tooltip-status.success {
    color: var(--success);
  }
  
  .live-indicator {
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
  }
  
  .live-dot {
    display: inline-block;
    width: 12px;
    height: 12px;
    background: var(--success);
    border-radius: 50%;
    animation: pulse 2s infinite;
  }
  
  @keyframes pulse {
    0% {
      box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
    }
    70% {
      box-shadow: 0 0 0 10px rgba(16, 185, 129, 0);
    }
    100% {
      box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
    }
  }
  
  .timeline-stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    padding: 1rem;
    background: var(--secondary);
    border-radius: 8px;
  }
  
  .stat-item {
    text-align: center;
  }
  
  .stat-value {
    display: block;
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--foreground);
  }
  
  .stat-value.success {
    color: var(--success);
  }
  
  .stat-value.failed {
    color: var(--error);
  }
  
  .stat-label {
    display: block;
    font-size: 0.875rem;
    color: var(--muted-foreground);
    margin-top: 0.25rem;
  }
  
  @media (max-width: 768px) {
    .timeline-header {
      flex-direction: column;
      gap: 1rem;
      align-items: flex-start;
    }
    
    .timeline-controls {
      width: 100%;
      flex-direction: column;
      gap: 0.5rem;
    }
    
    .time-range-selector {
      width: 100%;
    }
    
    .timeline-stats {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
