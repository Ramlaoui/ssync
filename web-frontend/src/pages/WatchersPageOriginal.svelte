<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { querystring, push } from 'svelte-spa-router';
  import {
    watchers,
    watcherEvents,
    watcherStats,
    watchersLoading,
    eventsLoading,
    statsLoading,
    fetchAllWatchers,
    fetchWatcherEvents,
    fetchWatcherStats,
    connectWatcherWebSocket,
    disconnectWatcherWebSocket,
    clearWatcherData
  } from '../stores/watchers';
  import { allCurrentJobs, jobsStore } from '../stores/jobs';
  import WatcherCard from '../components/WatcherCard.svelte';
  import WatcherEvents from '../components/WatcherEvents.svelte';
  import WatcherTimeline from '../components/WatcherTimeline.svelte';
  import WatcherMetrics from '../components/WatcherMetrics.svelte';
  import AttachWatchersDialog from '../components/AttachWatchersDialog.svelte';
  import JobSelectionDialog from '../components/JobSelectionDialog.svelte';
  
  // Tab state - simplified to just 3 tabs
  let activeTab: 'watchers' | 'events' | 'metrics' = 'watchers';
  
  // Filter state
  let filterState: 'all' | 'active' | 'paused' | 'completed' = 'all';
  let filterWatcherId: number | null = null;
  
  // Collapsed state for job groups
  let collapsedJobs: Set<string> = new Set();
  
  // Refresh interval
  let refreshInterval: number | null = null;
  
  // Dialog states
  let showJobSelectionDialog = false;
  let showAttachDialog = false;
  let selectedJobId: string | null = null;
  let selectedHostname: string | null = null;
  let copiedWatcherConfig: any = null;
  
  // Parse query parameters and fetch data when they change
  $: {
    const params = new URLSearchParams($querystring);
    const tab = params.get('tab');
    const watcherId = params.get('watcher');
    
    let tabChanged = false;
    let watcherIdChanged = false;
    
    if (tab === 'events' || tab === 'metrics' || tab === 'watchers') {
      if (activeTab !== tab) {
        tabChanged = true;
        activeTab = tab;
      }
    }
    
    if (watcherId) {
      const newWatcherId = parseInt(watcherId, 10);
      if (filterWatcherId !== newWatcherId) {
        watcherIdChanged = true;
        filterWatcherId = newWatcherId;
      }
      // If we have a watcher filter, default to events tab
      if (!tab) {
        activeTab = 'events';
        tabChanged = true;
      }
    } else if (filterWatcherId !== null) {
      filterWatcherId = null;
      watcherIdChanged = true;
    }
    
    // Fetch data when tab or watcher filter changes
    if (tabChanged || watcherIdChanged) {
      // Use setTimeout to ensure this runs after the reactive statements complete
      // Force event refresh when watcher filter changes
      setTimeout(() => refreshData(watcherIdChanged), 0);
    }
  }
  
  onMount(async () => {
    // Initial data fetch
    await refreshData();
    
    // Ensure hosts are loaded first
    await jobsStore.fetchAvailableHosts();
    
    // Fetch jobs to get job names and for the attach dialog
    await jobsStore.fetchAllJobs(true); // Force refresh on page load
    
    // Connect WebSocket for real-time updates
    connectWatcherWebSocket();
    
    // Set up refresh interval (every 30 seconds)
    startRefreshInterval();
  });
  
  onDestroy(() => {
    // Clean up
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
    disconnectWatcherWebSocket();
    clearWatcherData();
  });
  
  function startRefreshInterval() {
    if (!refreshInterval) {
      refreshInterval = setInterval(refreshData, 30000);
    }
  }
  
  function stopRefreshInterval() {
    if (refreshInterval) {
      clearInterval(refreshInterval);
      refreshInterval = null;
    }
  }
  
  async function refreshData(forceEventRefresh = false) {
    // Don't refresh if any dialog is open to preserve user's work
    if (showJobSelectionDialog || showAttachDialog) {
      console.log('Skipping refresh - dialog is open');
      return;
    }
    
    try {
      // Fetch jobs to get updated job names
      await jobsStore.fetchAllJobs();
      
      // Always fetch watchers for the count badges
      await fetchAllWatchers();
      
      // Fetch additional data based on active tab or if forced
      if (forceEventRefresh || activeTab === 'events') {
        await fetchWatcherEvents();
      }
      
      if (activeTab === 'metrics') {
        await fetchWatcherEvents();
        await fetchWatcherStats();
      }
    } catch (error) {
      console.error('Failed to refresh watcher data:', error);
    }
  }
  
  // Watch for dialog state changes to manage refresh interval
  $: {
    if (showJobSelectionDialog || showAttachDialog) {
      // Stop refresh when dialogs are open
      stopRefreshInterval();
    } else {
      // Resume refresh when dialogs are closed
      startRefreshInterval();
    }
  }
  
  async function handleTabChange(tab: typeof activeTab) {
    activeTab = tab;
    await refreshData();
  }
  
  // Filtered watchers based on filter state
  $: filteredWatchers = filterState === 'all' 
    ? $watchers
    : $watchers.filter(w => w.state === filterState);
  
  // Group watchers by job and try to find job names
  $: watchersByJob = filteredWatchers.reduce((acc, watcher) => {
    const key = `${watcher.job_id}_${watcher.hostname}`;
    if (!acc[key]) {
      // Try to find the job in allCurrentJobs to get the name
      const jobInfo = $allCurrentJobs.find(
        j => j.job_id === watcher.job_id && j.hostname === watcher.hostname
      );
      
      acc[key] = {
        job_id: watcher.job_id,
        hostname: watcher.hostname,
        job_name: jobInfo?.name || null,
        job_state: jobInfo?.state || null,
        watchers: []
      };
    }
    acc[key].watchers.push(watcher);
    return acc;
  }, {} as Record<string, { job_id: string; hostname: string; job_name: string | null; job_state: string | null; watchers: typeof filteredWatchers }>);
  
  // Sort job groups by job_id (newest first)
  $: sortedJobGroups = Object.values(watchersByJob).sort((a, b) => {
    // Try to parse as numbers for proper sorting
    const aNum = parseInt(a.job_id);
    const bNum = parseInt(b.job_id);
    if (!isNaN(aNum) && !isNaN(bNum)) {
      return bNum - aNum;
    }
    return b.job_id.localeCompare(a.job_id);
  });
  
  // Counts for badges
  $: activeCount = $watchers.filter(w => w.state === 'active').length;
  $: pausedCount = $watchers.filter(w => w.state === 'paused').length;
  $: completedCount = $watchers.filter(w => w.state === 'completed').length;
  $: totalCount = $watchers.length;
  
  // Filter events by watcher ID if specified
  $: filteredEvents = filterWatcherId 
    ? $watcherEvents.filter(e => e.watcher_id === filterWatcherId)
    : $watcherEvents;
  
  $: eventCount = filteredEvents.length;
  
  // Metrics from events
  $: metricEvents = filteredEvents.filter(e => e.action_type === 'store_metric');
  
  function toggleJobGroup(jobKey: string) {
    if (collapsedJobs.has(jobKey)) {
      collapsedJobs.delete(jobKey);
    } else {
      collapsedJobs.add(jobKey);
    }
    collapsedJobs = collapsedJobs; // Trigger reactivity
  }
  
  async function openAttachDialog() {
    // Fetch fresh jobs list
    await jobsStore.fetchAllJobs();
    
    // Get running jobs that we can attach watchers to
    const runningJobs = $allCurrentJobs.filter(job => 
      job.state === 'R' || job.state === 'PD'
    );
    
    if (runningJobs.length === 0) {
      alert('No running or pending jobs found to attach watchers to.');
      return;
    }
    
    // If there's only one running job, select it automatically
    if (runningJobs.length === 1) {
      selectedJobId = runningJobs[0].job_id;
      selectedHostname = runningJobs[0].hostname;
      showAttachDialog = true;
    } else {
      // Show job selection dialog
      showJobSelectionDialog = true;
    }
  }
  
  function handleJobSelection(event: CustomEvent) {
    const job = event.detail;
    selectedJobId = job.job_id;
    selectedHostname = job.hostname;
    showJobSelectionDialog = false;
    showAttachDialog = true;
  }
  
  async function handleWatcherCopy(event: CustomEvent) {
    // Store the copied config
    copiedWatcherConfig = event.detail;
    
    // Fetch fresh jobs list
    await jobsStore.fetchAllJobs();
    
    // Get running jobs that we can attach watchers to
    const runningJobs = $allCurrentJobs.filter(job => 
      job.state === 'R' || job.state === 'PD'
    );
    
    if (runningJobs.length === 0) {
      alert('No running or pending jobs found to attach the copied watcher to.');
      return;
    }
    
    // If there's only one running job, select it automatically
    if (runningJobs.length === 1) {
      selectedJobId = runningJobs[0].job_id;
      selectedHostname = runningJobs[0].hostname;
      showAttachDialog = true;
    } else {
      // Show job selection dialog
      showJobSelectionDialog = true;
    }
  }
  
  function handleCloseJobSelectionDialog() {
    showJobSelectionDialog = false;
    // Resume refresh when dialog closes
    startRefreshInterval();
  }
  
  function handleCloseAttachDialog() {
    showAttachDialog = false;
    selectedJobId = null;
    selectedHostname = null;
    // Resume refresh when dialog closes
    startRefreshInterval();
  }
  
  async function handleAttachSuccess(event: CustomEvent) {
    showAttachDialog = false;
    selectedJobId = null;
    selectedHostname = null;
    
    // Refresh watchers list
    await refreshData();
    
    // Show success message
    const { watcher_ids } = event.detail;
    if (watcher_ids && watcher_ids.length > 0) {
      alert(`Successfully attached ${watcher_ids.length} watcher(s)`);
    }
  }
</script>

<div class="watchers-page">
  <div class="page-header">
    <h1>Job Watchers</h1>
    <div class="header-actions">
      <button 
        class="attach-btn"
        on:click={openAttachDialog}
        title="Attach new watchers to a running job"
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/>
        </svg>
        Attach Watchers
      </button>
      <button 
        class="refresh-btn"
        on:click={() => refreshData()}
        disabled={$watchersLoading || $eventsLoading || $statsLoading}
      >
        {#if $watchersLoading || $eventsLoading || $statsLoading}
          <span class="spinner"></span> Refreshing...
        {:else}
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z"/>
          </svg>
          Refresh
        {/if}
      </button>
    </div>
  </div>
  
  <!-- Simple status overview -->
  <div class="status-overview">
    <div class="status-item active">
      <span class="status-value">{activeCount}</span>
      <span class="status-label">Active</span>
    </div>
    <div class="status-item paused">
      <span class="status-value">{pausedCount}</span>
      <span class="status-label">Paused</span>
    </div>
    <div class="status-item completed">
      <span class="status-value">{completedCount}</span>
      <span class="status-label">Completed</span>
    </div>
    <div class="status-item total">
      <span class="status-value">{totalCount}</span>
      <span class="status-label">Total</span>
    </div>
  </div>
  
  <!-- Simplified tabs -->
  <div class="tabs">
    <button 
      class="tab {activeTab === 'watchers' ? 'active' : ''}"
      on:click={() => handleTabChange('watchers')}
    >
      Watchers
      {#if totalCount > 0}
        <span class="badge">{totalCount}</span>
      {/if}
    </button>
    
    <button 
      class="tab {activeTab === 'events' ? 'active' : ''}"
      on:click={() => handleTabChange('events')}
    >
      Events
      {#if eventCount > 0}
        <span class="badge">{eventCount}</span>
      {/if}
    </button>
    
    <button 
      class="tab {activeTab === 'metrics' ? 'active' : ''}"
      on:click={() => handleTabChange('metrics')}
    >
      Metrics
      {#if metricEvents.length > 0}
        <span class="badge">{metricEvents.length}</span>
      {/if}
    </button>
  </div>
  
  <div class="tab-content">
    {#if activeTab === 'watchers'}
      <!-- Filter buttons for watchers view -->
      <div class="filter-bar">
        <button 
          class="filter-btn {filterState === 'all' ? 'active' : ''}"
          on:click={() => filterState = 'all'}
        >
          All ({totalCount})
        </button>
        <button 
          class="filter-btn {filterState === 'active' ? 'active' : ''}"
          on:click={() => filterState = 'active'}
        >
          Active ({activeCount})
        </button>
        <button 
          class="filter-btn {filterState === 'paused' ? 'active' : ''}"
          on:click={() => filterState = 'paused'}
        >
          Paused ({pausedCount})
        </button>
        <button 
          class="filter-btn {filterState === 'completed' ? 'active' : ''}"
          on:click={() => filterState = 'completed'}
        >
          Completed ({completedCount})
        </button>
      </div>
      
      {#if $watchersLoading}
        <div class="loading-message">
          <span class="spinner"></span> Loading watchers...
        </div>
      {:else if filteredWatchers.length === 0}
        <div class="empty-state">
          <h3>No Watchers Found</h3>
          <p>
            {#if filterState !== 'all'}
              No {filterState} watchers at the moment. Try changing the filter.
            {:else}
              Watchers will appear here when jobs with watcher configurations are launched.
            {/if}
          </p>
        </div>
      {:else}
        <!-- Watchers grouped by job -->
        <div class="job-groups">
          {#each sortedJobGroups as jobGroup}
            {@const jobKey = `${jobGroup.job_id}_${jobGroup.hostname}`}
            {@const isCollapsed = collapsedJobs.has(jobKey)}
            {@const activeInJob = jobGroup.watchers.filter(w => w.state === 'active').length}
            <div class="job-group">
              <button 
                class="job-header"
                on:click={() => toggleJobGroup(jobKey)}
              >
                <div class="job-header-left">
                  <span class="collapse-icon {isCollapsed ? 'collapsed' : ''}">
                    ▼
                  </span>
                  <div class="job-info">
                    <div class="job-main-info">
                      <span class="job-title">Job #{jobGroup.job_id}</span>
                      {#if jobGroup.job_name}
                        <span class="job-name">• {jobGroup.job_name}</span>
                      {/if}
                    </div>
                    <span class="job-host">on {jobGroup.hostname}</span>
                  </div>
                  <div class="watcher-counts">
                    <span class="count-badge total">{jobGroup.watchers.length} watcher{jobGroup.watchers.length !== 1 ? 's' : ''}</span>
                    {#if activeInJob > 0}
                      <span class="count-badge active">{activeInJob} active</span>
                    {/if}
                  </div>
                </div>
                <div class="job-header-right">
                  <span class="toggle-hint">
                    {isCollapsed ? 'Click to expand' : 'Click to collapse'}
                  </span>
                </div>
              </button>
              
              {#if !isCollapsed}
                <div class="job-watchers">
                  <div class="watchers-grid">
                    {#each jobGroup.watchers as watcher}
                      <WatcherCard 
                        {watcher} 
                        showJobLink={false}
                        on:copy={handleWatcherCopy}
                      />
                    {/each}
                  </div>
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
      
    {:else if activeTab === 'events'}
      <div class="events-container">
        {#if $eventsLoading}
          <div class="loading-message">
            <span class="spinner"></span> Loading events...
          </div>
        {:else}
          <!-- Timeline view for recent activity -->
          <div class="timeline-section">
            <h2>Activity Timeline</h2>
            <WatcherTimeline events={filteredEvents} />
          </div>
          
          <!-- Events list -->
          <div class="events-section">
            <div class="events-header">
              <h2>Recent Events {filterWatcherId ? `(Watcher #${filterWatcherId})` : ''}</h2>
              {#if filterWatcherId}
                <button 
                  class="clear-filter-btn"
                  on:click={() => {
                    filterWatcherId = null;
                    // Update URL to remove query params
                    push('/watchers?tab=events');
                  }}
                >
                  Clear Filter
                </button>
              {/if}
            </div>
            <WatcherEvents events={filteredEvents} loading={false} />
          </div>
        {/if}
      </div>
      
    {:else if activeTab === 'metrics'}
      <div class="metrics-container">
        {#if metricEvents.length === 0}
          <div class="empty-state">
            <h3>No Metrics Available</h3>
            <p>Metrics will appear here when watchers with metric actions are triggered.</p>
          </div>
        {:else}
          <WatcherMetrics events={filteredEvents} />
        {/if}
      </div>
    {/if}
  </div>
</div>

{#if showJobSelectionDialog}
  <JobSelectionDialog
    jobs={$allCurrentJobs.filter(job => job.state === 'R' || job.state === 'PD')}
    title="Select Job for Watchers"
    description="Choose a running or pending job to attach watchers to"
    on:select={handleJobSelection}
    on:close={handleCloseJobSelectionDialog}
  />
{/if}

{#if showAttachDialog && selectedJobId && selectedHostname}
  <AttachWatchersDialog
    jobId={selectedJobId}
    hostname={selectedHostname}
    copiedConfig={copiedWatcherConfig}
    on:success={handleAttachSuccess}
    on:close={() => {
      handleCloseAttachDialog();
      copiedWatcherConfig = null;
    }}
  />
{/if}

<style>
  .watchers-page {
    padding: 1rem;
    max-width: 1400px;
    margin: 0 auto;
    height: 100%;
    overflow-y: auto;
  }
  
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
  }
  
  .page-header h1 {
    margin: 0;
    font-size: 1.8rem;
    color: var(--color-text-primary);
  }
  
  .header-actions {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }
  
  .attach-btn,
  .refresh-btn {
    padding: 0.5rem 1rem;
    background: var(--color-primary);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
    transition: background 0.2s;
  }
  
  .attach-btn svg,
  .refresh-btn svg {
    width: 18px;
    height: 18px;
  }
  
  .attach-btn {
    background: #10b981;
  }
  
  .attach-btn:hover:not(:disabled) {
    background: #059669;
  }
  
  .refresh-btn:hover:not(:disabled) {
    background: var(--color-primary-dark);
  }
  
  .attach-btn:disabled,
  .refresh-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid #ffffff30;
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  /* Status overview */
  .status-overview {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 2rem;
  }
  
  .status-item {
    background: var(--color-bg-secondary);
    border-radius: 8px;
    padding: 1rem;
    text-align: center;
    border: 1px solid var(--color-border);
  }
  
  .status-item.active {
    border-color: #10b981;
    background: #10b98110;
  }
  
  .status-item.paused {
    border-color: #f59e0b;
    background: #f59e0b10;
  }
  
  .status-item.completed {
    border-color: #3b82f6;
    background: #3b82f610;
  }
  
  .status-item.total {
    border-color: var(--color-primary);
    background: var(--color-primary-bg);
  }
  
  .status-value {
    display: block;
    font-size: 2rem;
    font-weight: 700;
    color: var(--color-text-primary);
    margin-bottom: 0.25rem;
  }
  
  .status-label {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
  }
  
  /* Tabs */
  .tabs {
    display: flex;
    gap: 0.5rem;
    border-bottom: 2px solid var(--color-border);
    margin-bottom: 1.5rem;
  }
  
  .tab {
    padding: 0.75rem 1.5rem;
    background: none;
    border: none;
    color: var(--color-text-secondary);
    cursor: pointer;
    font-size: 0.95rem;
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: color 0.2s;
  }
  
  .tab:hover {
    color: var(--color-text-primary);
  }
  
  .tab.active {
    color: var(--color-primary);
    font-weight: 500;
  }
  
  .tab.active::after {
    content: '';
    position: absolute;
    bottom: -2px;
    left: 0;
    right: 0;
    height: 2px;
    background: var(--color-primary);
  }
  
  .badge {
    background: var(--color-primary);
    color: white;
    padding: 0.15rem 0.5rem;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
  }
  
  .tab:not(.active) .badge {
    background: var(--color-bg-secondary);
    color: var(--color-text-secondary);
  }
  
  /* Filter bar */
  .filter-bar {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
    padding: 0.5rem;
    background: var(--color-bg-secondary);
    border-radius: 8px;
  }
  
  .filter-btn {
    padding: 0.5rem 1rem;
    background: none;
    border: 1px solid transparent;
    border-radius: 6px;
    color: var(--color-text-secondary);
    cursor: pointer;
    font-size: 0.875rem;
    transition: all 0.2s;
  }
  
  .filter-btn:hover {
    background: white;
    border-color: var(--color-border);
  }
  
  .filter-btn.active {
    background: white;
    color: var(--color-primary);
    border-color: var(--color-primary);
    font-weight: 500;
  }
  
  /* Content areas */
  .tab-content {
    min-height: 400px;
  }
  
  /* Job groups */
  .job-groups {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .job-group {
    background: var(--color-bg-secondary);
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid var(--color-border);
  }
  
  .job-header {
    width: 100%;
    padding: 1rem 1.5rem;
    background: var(--color-bg-primary);
    border: none;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: background 0.2s;
    text-align: left;
  }
  
  .job-header:hover {
    background: var(--color-bg-hover, #f9fafb);
  }
  
  .job-header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  
  .collapse-icon {
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    transition: transform 0.2s;
    display: inline-block;
  }
  
  .collapse-icon.collapsed {
    transform: rotate(-90deg);
  }
  
  .job-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .job-main-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .job-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--color-text-primary);
  }
  
  .job-name {
    font-size: 1rem;
    color: var(--color-text-secondary);
    font-weight: 400;
  }
  
  .job-host {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
  }
  
  .watcher-counts {
    display: flex;
    gap: 0.5rem;
    margin-left: 1rem;
  }
  
  .count-badge {
    padding: 0.25rem 0.75rem;
    border-radius: 16px;
    font-size: 0.75rem;
    font-weight: 500;
  }
  
  .count-badge.total {
    background: var(--color-bg-secondary);
    color: var(--color-text-secondary);
    border: 1px solid var(--color-border);
  }
  
  .count-badge.active {
    background: #10b98120;
    color: #10b981;
    border: 1px solid #10b981;
  }
  
  .job-header-right {
    display: flex;
    align-items: center;
  }
  
  .toggle-hint {
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    opacity: 0;
    transition: opacity 0.2s;
  }
  
  .job-header:hover .toggle-hint {
    opacity: 1;
  }
  
  .job-watchers {
    padding: 1.5rem;
    background: var(--color-bg-secondary);
    animation: slideDown 0.3s ease;
  }
  
  @keyframes slideDown {
    from {
      opacity: 0;
      max-height: 0;
    }
    to {
      opacity: 1;
      max-height: 2000px;
    }
  }
  
  .watchers-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(450px, 1fr));
    gap: 1rem;
  }
  
  .events-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .events-header h2 {
    margin: 0;
  }
  
  .clear-filter-btn {
    padding: 0.4rem 0.8rem;
    background: var(--color-bg-secondary);
    color: var(--color-text-secondary);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .clear-filter-btn:hover {
    background: var(--color-error-bg);
    color: var(--color-error);
    border-color: var(--color-error);
  }
  
  .events-container,
  .metrics-container {
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }
  
  .timeline-section,
  .events-section {
    background: var(--color-bg-primary);
    border: 1px solid var(--color-border);
    border-radius: 12px;
    padding: 1.5rem;
  }
  
  .timeline-section h2,
  .events-section h2 {
    margin: 0 0 1.5rem 0;
    font-size: 1.25rem;
    color: var(--color-text-primary);
  }
  
  .empty-state {
    text-align: center;
    padding: 3rem;
    background: var(--color-bg-secondary);
    border-radius: 12px;
    color: var(--color-text-secondary);
  }
  
  .empty-state h3 {
    color: var(--color-text-primary);
    margin-bottom: 1rem;
  }
  
  .empty-state p {
    max-width: 500px;
    margin: 0 auto;
  }
  
  .loading-message {
    text-align: center;
    padding: 3rem;
    color: var(--color-text-secondary);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
  }
  
  @media (max-width: 768px) {
    .watchers-page {
      padding: 0.5rem;
    }
    
    .page-header {
      flex-direction: column;
      gap: 1rem;
      align-items: stretch;
    }
    
    .header-actions {
      width: 100%;
      display: flex;
      gap: 0.5rem;
    }
    
    .attach-btn,
    .refresh-btn {
      flex: 1;
      justify-content: center;
    }
    
    .status-overview {
      grid-template-columns: repeat(2, 1fr);
    }
    
    .tabs {
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }
    
    .tab {
      padding: 0.5rem 1rem;
      white-space: nowrap;
    }
    
    .filter-bar {
      flex-wrap: wrap;
    }
    
    .watchers-grid {
      grid-template-columns: 1fr;
    }
  }
</style>