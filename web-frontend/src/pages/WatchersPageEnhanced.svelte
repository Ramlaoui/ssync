<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { querystring, push } from 'svelte-spa-router';
  import { fade, fly, scale, slide } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
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
  import AttachWatchersDialog from '../components/AttachWatchersDialogEnhanced.svelte';
  import JobSelectionDialog from '../components/JobSelectionDialog.svelte';
  
  // View modes
  type ViewMode = 'grid' | 'list' | 'timeline';
  let viewMode: ViewMode = 'grid';
  
  // Tab state - simplified
  type TabType = 'watchers' | 'events' | 'metrics';
  type MobileTabType = 'watchers' | 'events';
  let activeTab: TabType = 'watchers';
  
  // Mobile detection
  let isMobile = false;
  let showMobileMenu = false;
  let showMobileFilters = false;
  
  function checkMobile() {
    isMobile = window.innerWidth <= 768;
    if (!isMobile) {
      showMobileMenu = false;
      showMobileFilters = false;
    } else {
      // On mobile, only allow mobile tabs
      const mobileTabs: MobileTabType[] = ['watchers', 'events'];
      if (!mobileTabs.includes(activeTab as MobileTabType)) {
        activeTab = 'watchers';
      }
    }
  }
  
  // Filter and search state
  let searchQuery = '';
  let filterState: 'all' | 'active' | 'paused' | 'completed' = 'all';
  let filterWatcherId: number | null = null;
  let selectedTags: Set<string> = new Set();
  let sortBy: 'recent' | 'name' | 'triggers' | 'job' = 'recent';
  
  // UI state
  let showFilters = false;
  let collapsedJobs: Set<string> = new Set();
  let selectedWatchers: Set<number> = new Set();
  let refreshInterval: number | null = null;
  
  // Dialog states
  let showJobSelectionDialog = false;
  let showAttachDialog = false;
  let selectedJobId: string | null = null;
  let selectedHostname: string | null = null;
  let copiedWatcherConfig: any = null;
  
  // Animation state
  let isTransitioning = false;
  
  // Stats calculations
  $: totalWatchers = $watchers.length;
  $: activeCount = $watchers.filter(w => w.state === 'active').length;
  $: pausedCount = $watchers.filter(w => w.state === 'paused').length;
  $: completedCount = $watchers.filter(w => w.state === 'completed').length;
  $: totalTriggers = $watchers.reduce((sum, w) => sum + (w.trigger_count || 0), 0);
  $: recentEvents = $watcherEvents.slice(0, 10);
  
  // Success rate calculation
  $: successRate = $watcherEvents.length > 0 
    ? Math.round(($watcherEvents.filter(e => e.success).length / $watcherEvents.length) * 100)
    : 100;
  
  // Parse query parameters
  $: {
    const params = new URLSearchParams($querystring);
    const tab = params.get('tab');
    const watcherId = params.get('watcher');
    
    if (tab === 'watchers' || tab === 'events' || tab === 'metrics') {
      activeTab = tab;
    }
    
    if (watcherId) {
      filterWatcherId = parseInt(watcherId, 10);
      if (!tab) activeTab = 'events';
    }
    
    // Fetch data when params change
    setTimeout(() => refreshData(!!watcherId), 0);
  }
  
  // Load events when switching to events tab
  $: if (activeTab === 'events' && $watcherEvents.length === 0) {
    fetchWatcherEvents();
  }
  
  // Advanced filtering
  $: filteredWatchers = $watchers.filter(watcher => {
    // State filter
    if (filterState !== 'all' && watcher.state !== filterState) return false;
    
    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      const matchesSearch = 
        watcher.name.toLowerCase().includes(query) ||
        watcher.pattern.toLowerCase().includes(query) ||
        watcher.job_id.toLowerCase().includes(query) ||
        watcher.hostname.toLowerCase().includes(query);
      if (!matchesSearch) return false;
    }
    
    return true;
  });
  
  // Sort watchers
  $: sortedWatchers = [...filteredWatchers].sort((a, b) => {
    switch (sortBy) {
      case 'name':
        return a.name.localeCompare(b.name);
      case 'triggers':
        return (b.trigger_count || 0) - (a.trigger_count || 0);
      case 'job':
        return a.job_id.localeCompare(b.job_id);
      case 'recent':
      default:
        return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
    }
  });
  
  // Group by job with enhanced info
  $: watchersByJob = sortedWatchers.reduce((acc, watcher) => {
    const key = `${watcher.job_id}_${watcher.hostname}`;
    if (!acc[key]) {
      const jobInfo = $allCurrentJobs.find(
        j => j.job_id === watcher.job_id && j.hostname === watcher.hostname
      );
      
      acc[key] = {
        job_id: watcher.job_id,
        hostname: watcher.hostname,
        job_name: jobInfo?.name || watcher.job_name || null,
        job_state: jobInfo?.state || null,
        watchers: [],
        stats: {
          active: 0,
          paused: 0,
          completed: 0,
          totalTriggers: 0
        }
      };
    }
    
    acc[key].watchers.push(watcher);
    acc[key].stats[watcher.state]++;
    acc[key].stats.totalTriggers += watcher.trigger_count || 0;
    
    return acc;
  }, {} as Record<string, any>);
  
  // Lifecycle
  onMount(async () => {
    // Check if mobile
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    // Ensure hosts are loaded first
    await jobsStore.fetchAvailableHosts();
    
    await refreshData();
    await jobsStore.fetchAllJobs(true); // Force refresh on page load
    connectWatcherWebSocket();
    startRefreshInterval();
    
    // Add keyboard shortcuts
    window.addEventListener('keydown', handleKeydown);
  });
  
  onDestroy(() => {
    stopRefreshInterval();
    disconnectWatcherWebSocket();
    clearWatcherData();
    window.removeEventListener('keydown', handleKeydown);
    window.removeEventListener('resize', checkMobile);
  });
  
  // Touch swipe handling for mobile tabs
  let touchStartX = 0;
  let touchStartY = 0;
  let touchEndX = 0;
  let touchEndY = 0;
  
  function handleTouchStart(e: TouchEvent) {
    touchStartX = e.changedTouches[0].screenX;
    touchStartY = e.changedTouches[0].screenY;
  }
  
  function handleTouchEnd(e: TouchEvent) {
    touchEndX = e.changedTouches[0].screenX;
    touchEndY = e.changedTouches[0].screenY;
    handleSwipe();
  }
  
  function handleSwipe() {
    // Only process swipes on mobile
    if (!isMobile) return;
    
    const swipeThreshold = 50;
    const horizontalDiff = touchEndX - touchStartX;
    const verticalDiff = Math.abs(touchEndY - touchStartY);
    
    // Ignore if vertical movement is larger than horizontal (scrolling)
    if (verticalDiff > Math.abs(horizontalDiff)) return;
    
    // Prevent processing if swipe is too small
    if (Math.abs(horizontalDiff) < swipeThreshold) return;
    
    // Only allow watchers and events tabs on mobile
    const mobileTabs: MobileTabType[] = ['watchers', 'events'];
    
    // Ensure current tab is valid for mobile
    if (!mobileTabs.includes(activeTab as MobileTabType)) {
      activeTab = 'watchers';
      return;
    }
    
    const currentIndex = mobileTabs.indexOf(activeTab as MobileTabType);
    
    if (horizontalDiff < -swipeThreshold && currentIndex < mobileTabs.length - 1) {
      // Swipe left - next tab (watchers -> events)
      activeTab = mobileTabs[currentIndex + 1];
    } else if (horizontalDiff > swipeThreshold && currentIndex > 0) {
      // Swipe right - previous tab (events -> watchers)
      activeTab = mobileTabs[currentIndex - 1];
    }
  }
  
  // Functions
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
    if (showJobSelectionDialog || showAttachDialog) return;
    
    try {
      // Ensure hosts are available before fetching jobs
      if ($allCurrentJobs.length === 0) {
        await jobsStore.fetchAvailableHosts();
      }
      await jobsStore.fetchAllJobs();
      await fetchAllWatchers();
      
      // Always fetch events on initial load or when needed
      if (forceEventRefresh || activeTab === 'events' || $watcherEvents.length === 0) {
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
  
  function handleKeydown(event: KeyboardEvent) {
    // Keyboard shortcuts
    if (event.key === '/' && !event.metaKey) {
      event.preventDefault();
      document.getElementById('search-input')?.focus();
    } else if (event.key === 'a' && event.metaKey) {
      event.preventDefault();
      openAttachDialog();
    } else if (event.key === 'r' && event.metaKey) {
      event.preventDefault();
      refreshData();
    } else if (event.key === 'Escape') {
      searchQuery = '';
      filterState = 'all';
      selectedTags.clear();
    }
  }
  
  async function openAttachDialog() {
    // Ensure we have fresh job data
    await jobsStore.fetchAvailableHosts();
    await jobsStore.fetchAllJobs(true);
    const runningJobs = $allCurrentJobs.filter(job => 
      job.state === 'R' || job.state === 'PD'
    );
    
    if (runningJobs.length === 0) {
      showNotification('No running or pending jobs found', 'warning');
      return;
    }
    
    if (runningJobs.length === 1) {
      selectedJobId = runningJobs[0].job_id;
      selectedHostname = runningJobs[0].hostname;
      showAttachDialog = true;
    } else {
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
    copiedWatcherConfig = event.detail;
    await openAttachDialog();
  }
  
  async function handleAttachSuccess(event: CustomEvent) {
    showAttachDialog = false;
    selectedJobId = null;
    selectedHostname = null;
    copiedWatcherConfig = null;
    
    await refreshData();
    showNotification('Watcher attached successfully', 'success');
  }
  
  function toggleJobGroup(jobKey: string) {
    if (collapsedJobs.has(jobKey)) {
      collapsedJobs.delete(jobKey);
    } else {
      collapsedJobs.add(jobKey);
    }
    collapsedJobs = collapsedJobs;
  }
  
  function selectWatcher(watcherId: number) {
    if (selectedWatchers.has(watcherId)) {
      selectedWatchers.delete(watcherId);
    } else {
      selectedWatchers.add(watcherId);
    }
    selectedWatchers = selectedWatchers;
  }
  
  let notification: { message: string; type: 'success' | 'warning' | 'error' } | null = null;
  
  function showNotification(message: string, type: 'success' | 'warning' | 'error' = 'success') {
    notification = { message, type };
    setTimeout(() => notification = null, 3000);
  }
</script>

<div class="watchers-page-enhanced" on:touchstart={handleTouchStart} on:touchend={handleTouchEnd}>
  
  <!-- Stats Cards -->
  {#if false}
    <div class="stats-grid" in:fade={{ duration: 300 }}>
      <div class="stat-card gradient-green">
        <div class="stat-icon">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M11,7V13L15.2,15.2L16.2,13.7L12.5,11.7V7H11Z"/>
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-value">{activeCount}</div>
          <div class="stat-label">Active Watchers</div>
          <div class="stat-trend up">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M7,14L12,9L17,14H7Z"/>
            </svg>
            <span>Running smoothly</span>
          </div>
        </div>
      </div>
      
      <div class="stat-card gradient-blue">
        <div class="stat-icon">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M9,3V4H4V6H5V19A2,2 0 0,0 7,21H17A2,2 0 0,0 19,19V6H20V4H15V3H9M7,6H17V19H7V6M9,8V17H11V8H9M13,8V17H15V8H13Z"/>
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-value">{totalTriggers}</div>
          <div class="stat-label">Total Triggers</div>
          <div class="stat-trend">
            <span>{successRate}% success rate</span>
          </div>
        </div>
      </div>
      
      <div class="stat-card gradient-purple">
        <div class="stat-icon">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2M12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4M12,6A6,6 0 0,1 18,12A6,6 0 0,1 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6M12,8A4,4 0 0,0 8,12A4,4 0 0,0 12,16A4,4 0 0,0 16,12A4,4 0 0,0 12,8Z"/>
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-value">{Object.keys(watchersByJob).length}</div>
          <div class="stat-label">Monitored Jobs</div>
          <div class="stat-trend">
            <span>{totalWatchers} total watchers</span>
          </div>
        </div>
      </div>
      
      <div class="stat-card gradient-orange">
        <div class="stat-icon">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z"/>
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-value">{pausedCount}</div>
          <div class="stat-label">Paused</div>
          <div class="stat-trend">
            <span>{completedCount} completed</span>
          </div>
        </div>
      </div>
    </div>
  {/if}
  

  <!-- Integrated Content Controls -->
  <div class="content-controls" transition:slide={{ duration: 300 }}>
    <!-- Tab Selection -->
    <div class="view-selection">
      <div class="tabs-left">
        <button 
          class="view-tab"
          class:active={activeTab === 'watchers'}
          on:click={() => activeTab = 'watchers'}
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z"/>
          </svg>
          <span class="tab-label">Watchers</span>
        </button>
        <button 
          class="view-tab"
          class:active={activeTab === 'events'}
          on:click={() => activeTab = 'events'}
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M10,21H14A2,2 0 0,1 12,23A2,2 0 0,1 10,21M21,19V20H3V19L5,17V11C5,7.9 7.03,5.17 10,4.29C10,4.19 10,4.1 10,4A2,2 0 0,1 12,2A2,2 0 0,1 14,4C14,4.1 14,4.19 14,4.29C16.97,5.17 19,7.9 19,11V17L21,19M17,11A5,5 0 0,0 12,6A5,5 0 0,0 7,11V18H17V11Z"/>
          </svg>
          <span class="tab-label">Events</span>
        </button>
        {#if !isMobile}
          <button 
            class="view-tab"
            class:active={activeTab === 'metrics'}
            on:click={() => activeTab = 'metrics'}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M22,21H2V3H4V19H6V17H10V19H12V16H16V19H18V17H22V21Z"/>
            </svg>
            <span class="tab-label">Metrics</span>
          </button>
        {/if}
      </div>
      
      <!-- Tab Actions on the right -->
      <div class="tabs-right">
        <button 
          class="tab-action-btn"
          on:click={() => refreshData()}
          disabled={$watchersLoading}
          title="Refresh {activeTab}"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" class:spinning={$watchersLoading}>
            <path d="M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z"/>
          </svg>
        </button>
        {#if activeTab === 'watchers'}
          <button 
            class="tab-action-btn primary"
            on:click={openAttachDialog}
            title="New Watcher"
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/>
            </svg>
          </button>
        {/if}
      </div>
    </div>
    
    {#if activeTab === 'watchers'}
      <!-- Search and filter tools -->
      <div class="content-tools">
        <div class="search-box">
          <svg viewBox="0 0 24 24" fill="currentColor" class="search-icon">
            <path d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z"/>
          </svg>
          <input
            id="search-input"
            type="text"
            placeholder="Search watchers..."
            bind:value={searchQuery}
            class="search-input"
          />
          {#if searchQuery}
            <button 
              class="clear-search"
              on:click={() => searchQuery = ''}
              transition:scale={{ duration: 200 }}
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
              </svg>
            </button>
          {/if}
        </div>
      </div>
      
      <!-- Filter chips -->
      <div class="filter-controls">
        <div class="filter-chips">
          <button 
            class="filter-chip"
            class:active={filterState === 'all'}
            on:click={() => filterState = 'all'}
          >
            All ({totalWatchers})
          </button>
          <button 
            class="filter-chip"
            class:active={filterState === 'active'}
            on:click={() => filterState = 'active'}
          >
            <span class="chip-dot active"></span>
            Active ({activeCount})
          </button>
          <button 
            class="filter-chip"
            class:active={filterState === 'paused'}
            on:click={() => filterState = 'paused'}
          >
            <span class="chip-dot paused"></span>
            Paused ({pausedCount})
          </button>
          <button 
            class="filter-chip"
            class:active={filterState === 'completed'}
            on:click={() => filterState = 'completed'}
          >
            <span class="chip-dot completed"></span>
            Completed ({completedCount})
          </button>
        </div>
        
        <div class="view-controls">
          <select 
            class="sort-select"
            bind:value={sortBy}
          >
            <option value="recent">Most Recent</option>
            <option value="name">Name</option>
            <option value="triggers">Most Triggers</option>
            <option value="job">Job ID</option>
          </select>
          
          <div class="view-mode-toggle">
            <button 
              class="view-btn"
              class:active={viewMode === 'grid'}
              on:click={() => viewMode = 'grid'}
              title="Grid view"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M3,3H11V11H3V3M13,3H21V11H13V3M3,13H11V21H3V13M13,13H21V21H13V13Z"/>
              </svg>
            </button>
            <button 
              class="view-btn"
              class:active={viewMode === 'list'}
              on:click={() => viewMode = 'list'}
              title="List view"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M3,4H21V8H3V4M3,10H21V14H3V10M3,16H21V20H3V16Z"/>
              </svg>
            </button>
            <button 
              class="view-btn"
              class:active={viewMode === 'timeline'}
              on:click={() => viewMode = 'timeline'}
              title="Timeline view"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M16.2,16.2L11,13V7H12.5V12.2L17,14.9L16.2,16.2Z"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    {/if}
    
    {#if activeTab === 'events'}
      <!-- Clean events tab - no summary needed -->
    {/if}
    
    {#if activeTab === 'metrics' && !isMobile}
      <!-- Metrics summary -->
      <div class="content-tools">
        <div class="content-summary">
          <span class="summary-text">Analytics and performance insights</span>
        </div>
      </div>
    {/if}
  </div>
  
  <!-- Main Content -->
  <main class="main-content">
    {#if activeTab === 'watchers'}
      <!-- Watchers Content -->
      <div class="watchers-content">
        {#if $watchersLoading}
          <div class="loading-state">
            <div class="loading-spinner"></div>
            <p>Loading watchers...</p>
          </div>
        {:else if sortedWatchers.length === 0}
          <div class="empty-state" in:scale={{ duration: 300 }}>
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z"/>
            </svg>
            <h3>No watchers found</h3>
            <p>
              {#if searchQuery}
                No watchers match your search criteria.
              {:else if filterState !== 'all'}
                No {filterState} watchers at the moment.
              {:else}
                Create your first watcher to start monitoring jobs.
              {/if}
            </p>
            <button class="action-btn primary" on:click={openAttachDialog}>
              Create Watcher
            </button>
          </div>
        {:else if viewMode === 'grid'}
          <!-- Grid View -->
          <div class="job-groups-grid">
            {#each Object.entries(watchersByJob) as [jobKey, jobGroup]}
              <div 
                class="job-group-card"
                in:fly={{ y: 20, duration: 300 }}
                class:collapsed={collapsedJobs.has(jobKey)}
              >
                <button 
                  class="job-group-header"
                  on:click={() => toggleJobGroup(jobKey)}
                >
                  <div class="job-header-info">
                    <h3>
                      Job #{jobGroup.job_id}
                      {#if jobGroup.job_name}
                        <span class="job-name">• {jobGroup.job_name}</span>
                      {/if}
                    </h3>
                    <p class="job-host">{jobGroup.hostname}</p>
                  </div>
                  
                  <div class="job-header-stats">
                    <div class="mini-stat">
                      <span class="stat-number">{jobGroup.watchers.length}</span>
                      <span class="stat-label">watchers</span>
                    </div>
                    <div class="mini-stat">
                      <span class="stat-number">{jobGroup.stats.active}</span>
                      <span class="stat-label active">active</span>
                    </div>
                    <svg 
                      viewBox="0 0 24 24" 
                      fill="currentColor"
                      class="expand-icon"
                      class:rotated={!collapsedJobs.has(jobKey)}
                    >
                      <path d="M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z"/>
                    </svg>
                  </div>
                </button>
                
                {#if !collapsedJobs.has(jobKey)}
                  <div class="job-watchers-grid" transition:slide={{ duration: 300 }}>
                    {#each jobGroup.watchers as watcher}
                      <div class="watcher-card-enhanced" in:scale={{ duration: 200 }}>
                        <WatcherCard 
                          {watcher}
                          showJobLink={false}
                          on:copy={handleWatcherCopy}
                        />
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
          
        {:else if viewMode === 'list'}
          <!-- List View -->
          <div class="watchers-list">
            {#each sortedWatchers as watcher}
              <div class="watcher-list-item" in:fly={{ x: -20, duration: 300 }}>
                <div class="watcher-checkbox">
                  <input 
                    type="checkbox"
                    checked={selectedWatchers.has(watcher.id)}
                    on:change={() => selectWatcher(watcher.id)}
                  />
                </div>
                
                <div class="watcher-status">
                  <span class="status-dot {watcher.state}"></span>
                </div>
                
                <div class="watcher-info">
                  <h4>{watcher.name}</h4>
                  <p class="watcher-pattern">{watcher.pattern}</p>
                </div>
                
                <div class="watcher-job">
                  Job #{watcher.job_id}
                </div>
                
                <div class="watcher-stats">
                  <span class="trigger-count">{watcher.trigger_count || 0} triggers</span>
                </div>
                
                <div class="watcher-actions">
                  <button 
                    class="icon-btn"
                    on:click={() => push(`/watchers?tab=events&watcher=${watcher.id}`)}
                  >
                    <svg viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z"/>
                    </svg>
                  </button>
                </div>
              </div>
            {/each}
          </div>
          
        {:else if viewMode === 'timeline'}
          <!-- Timeline View -->
          <div class="timeline-view">
            <WatcherTimeline events={$watcherEvents} />
          </div>
        {/if}
      </div>
      
    {:else if activeTab === 'events'}
      <div class="events-content" in:fade={{ duration: 300 }}>
        <WatcherEvents 
          events={filterWatcherId ? 
            $watcherEvents.filter(e => e.watcher_id === filterWatcherId) : 
            $watcherEvents
          } 
          loading={$eventsLoading} 
        />
      </div>
      
    {:else if !isMobile && activeTab === 'metrics'}
      <div class="metrics-content" in:fade={{ duration: 300 }}>
        <WatcherMetrics events={$watcherEvents} />
      </div>
      
    {/if}
  </main>
  
  <!-- Notification -->
  {#if notification}
    <div 
      class="notification {notification.type}"
      in:fly={{ y: -20, duration: 300 }}
      out:fade={{ duration: 200 }}
    >
      {notification.message}
    </div>
  {/if}
  
  <!-- Dialogs -->
  {#if showJobSelectionDialog}
    <JobSelectionDialog
      jobs={$allCurrentJobs.filter(job => job.state === 'R' || job.state === 'PD')}
      title="Select Job for Watchers"
      description="Choose a running or pending job to attach watchers to"
      on:select={handleJobSelection}
      on:close={() => showJobSelectionDialog = false}
    />
  {/if}
  
  {#if showAttachDialog && selectedJobId && selectedHostname}
    <AttachWatchersDialog
      jobId={selectedJobId}
      hostname={selectedHostname}
      copiedConfig={copiedWatcherConfig}
      on:success={handleAttachSuccess}
      on:close={() => {
        showAttachDialog = false;
        selectedJobId = null;
        selectedHostname = null;
        copiedWatcherConfig = null;
      }}
    />
  {/if}
  
</div>

<style>
  .watchers-page-enhanced {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: #f8fafc;
    position: relative;
  }
  
  /* Subtle gradient accent at the top */
  .watchers-page-enhanced::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 200px;
    background: linear-gradient(180deg, rgba(102, 126, 234, 0.05) 0%, transparent 100%);
    pointer-events: none;
    z-index: 0;
  }
  
  /* Minimal Navigation */
  .minimal-nav-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 2rem 0 2rem;
  }
  
  .minimal-nav {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .minimal-tab {
    padding: 0.5rem 1rem;
    background: none;
    border: none;
    color: #9ca3af;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: color 0.2s;
    border-radius: 6px;
  }
  
  .minimal-tab:hover {
    color: #4b5563;
    background: #f9fafb;
  }
  
  .minimal-tab.active {
    color: #667eea;
    background: #f0f4ff;
  }
  
  .minimal-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .minimal-btn {
    padding: 0.5rem 0.75rem;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    color: #64748b;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: all 0.2s;
  }
  
  .minimal-btn:hover:not(:disabled) {
    background: #f1f5f9;
    border-color: #cbd5e1;
    color: #475569;
  }
  
  .minimal-btn.primary {
    background: #667eea;
    border-color: #667eea;
    color: white;
  }
  
  .minimal-btn.primary:hover:not(:disabled) {
    background: #5a67d8;
    border-color: #5a67d8;
  }
  
  .minimal-btn svg {
    width: 16px;
    height: 16px;
  }
  
  .minimal-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  
  .action-btn {
    padding: 0.75rem 1.25rem;
    border: none;
    border-radius: 10px;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }
  
  .action-btn.primary {
    background: #667eea;
    color: white;
    box-shadow: 0 2px 4px rgba(102, 126, 234, 0.2);
  }
  
  .action-btn.primary:hover {
    background: #5a67d8;
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(102, 126, 234, 0.25);
  }
  
  .action-btn.secondary {
    background: white;
    color: #4b5563;
    border: 1px solid #e5e7eb;
  }
  
  .action-btn.secondary:hover {
    background: #f9fafb;
    border-color: #d1d5db;
  }
  
  .action-btn svg {
    width: 20px;
    height: 20px;
  }
  
  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  .spinning {
    animation: spin 1s linear infinite;
  }
  
  /* Stats Grid */
  .stats-grid {
    margin: 1rem 0;
    padding: 0 1rem;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.5rem;
  }
  
  .stat-card {
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    border: 1px solid #e5e7eb;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    display: flex;
    gap: 1rem;
    transition: all 0.2s ease;
  }
  
  .stat-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.08);
    border-color: #d1d5db;
  }
  
  .stat-card.gradient-green {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    color: white;
  }
  
  .stat-card.gradient-blue {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
  }
  
  .stat-card.gradient-purple {
    background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
    color: white;
  }
  
  .stat-card.gradient-orange {
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    color: white;
  }
  
  .stat-icon {
    width: 48px;
    height: 48px;
    background: rgba(255, 255, 255, 0.2);
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .stat-icon svg {
    width: 28px;
    height: 28px;
    opacity: 0.9;
  }
  
  .stat-content {
    flex: 1;
  }
  
  .stat-value {
    font-size: 2rem;
    font-weight: 700;
    line-height: 1;
    margin-bottom: 0.25rem;
  }
  
  .stat-label {
    font-size: 0.9rem;
    opacity: 0.9;
    margin-bottom: 0.5rem;
  }
  
  .stat-trend {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.8rem;
    opacity: 0.8;
  }
  
  .stat-trend svg {
    width: 16px;
    height: 16px;
  }
  
  /* Navigation Tabs */
  .nav-tabs {
    background: white;
    border-bottom: 1px solid #e5e7eb;
    display: flex;
    gap: 0;
    padding: 0 2rem;
    max-width: 1400px;
    margin: 0 auto;
    width: 100%;
    overflow-x: auto;
  }
  
  
  .tab-badge {
    background: #667eea;
    color: white;
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-left: 0.25rem;
  }
  
  /* Controls Bar */
  .controls-bar {
    background: white;
    padding: 1.5rem 2rem;
    border-bottom: 1px solid #e5e7eb;
    width: 100%;
  }
  
  .search-box {
    position: relative;
    max-width: 400px;
    margin-bottom: 1rem;
  }
  
  .search-icon {
    position: absolute;
    left: 1rem;
    top: 50%;
    transform: translateY(-50%);
    width: 20px;
    height: 20px;
    color: #9ca3af;
  }
  
  .search-input {
    width: 100%;
    padding: 0.75rem 1rem 0.75rem 3rem;
    border: 2px solid #e5e7eb;
    border-radius: 12px;
    font-size: 0.9rem;
    transition: all 0.2s;
  }
  
  .search-input:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }
  
  .clear-search {
    position: absolute;
    right: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
    background: #f3f4f6;
    border: none;
    border-radius: 6px;
    padding: 0.25rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .clear-search:hover {
    background: #e5e7eb;
  }
  
  .clear-search svg {
    width: 16px;
    height: 16px;
    color: #6b7280;
  }
  
  .filter-controls {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
  }
  
  .filter-chips {
    display: flex;
    gap: 0.5rem;
  }
  
  .filter-chip {
    padding: 0.5rem 1rem;
    background: #f3f4f6;
    border: 2px solid transparent;
    border-radius: 20px;
    color: #6b7280;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .filter-chip:hover {
    background: #e5e7eb;
  }
  
  .filter-chip.active {
    background: white;
    color: #3b82f6;
    border-color: #3b82f6;
  }
  
  .chip-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }
  
  .chip-dot.active {
    background: #10b981;
  }
  
  .chip-dot.paused {
    background: #f59e0b;
  }
  
  .chip-dot.completed {
    background: #3b82f6;
  }
  
  .view-controls {
    display: flex;
    gap: 1rem;
    align-items: center;
  }
  
  .sort-select {
    padding: 0.5rem 1rem;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    background: white;
    color: #4b5563;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .sort-select:focus {
    outline: none;
    border-color: #3b82f6;
  }
  
  .view-mode-toggle {
    display: flex;
    background: #f3f4f6;
    border-radius: 8px;
    padding: 0.25rem;
  }
  
  .view-btn {
    padding: 0.5rem;
    background: none;
    border: none;
    border-radius: 6px;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .view-btn:hover {
    background: #e5e7eb;
  }
  
  .view-btn.active {
    background: white;
    color: #3b82f6;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }
  
  .view-btn svg {
    width: 18px;
    height: 18px;
  }
  
  /* Main Content */
  .main-content {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem;
    width: 100%;
  }
  
  /* Job Groups Grid */
  .job-groups-grid {
    display: grid;
    gap: 1.5rem;
  }
  
  .job-group-card {
    background: white;
    border-radius: 12px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    overflow: hidden;
    transition: all 0.2s ease;
  }
  
  .job-group-card:hover {
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.08);
    border-color: #d1d5db;
  }
  
  .job-group-header {
    width: 100%;
    padding: 1.5rem;
    background: #f9fafb;
    border: none;
    border-bottom: 1px solid #e5e7eb;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: background 0.2s;
    text-align: left;
  }
  
  .job-group-header:hover {
    background: #f3f4f6;
  }
  
  .job-header-info h3 {
    margin: 0;
    font-size: 1.1rem;
    font-weight: 600;
    color: #1f2937;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .job-name {
    font-weight: 400;
    color: #6b7280;
  }
  
  .job-host {
    margin: 0.25rem 0 0 0;
    font-size: 0.85rem;
    color: #9ca3af;
  }
  
  .job-header-stats {
    display: flex;
    align-items: center;
    gap: 1.5rem;
  }
  
  .mini-stat {
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  
  .stat-number {
    font-size: 1.25rem;
    font-weight: 600;
    color: #374151;
  }
  
  .stat-label {
    font-size: 0.75rem;
    color: #9ca3af;
  }
  
  .stat-label.active {
    color: #10b981;
  }
  
  .expand-icon {
    width: 24px;
    height: 24px;
    color: #6b7280;
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }
  
  .expand-icon.rotated {
    transform: rotate(180deg);
  }
  
  .job-watchers-grid {
    padding: 1.5rem;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
    gap: 1rem;
    background: #fafafa;
  }
  
  .watcher-card-enhanced {
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }
  
  .watcher-card-enhanced:hover {
    transform: translateY(-2px);
  }
  
  /* List View */
  .watchers-list {
    background: white;
    border-radius: 12px;
    overflow: hidden;
  }
  
  .watcher-list-item {
    display: flex;
    align-items: center;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid #f3f4f6;
    transition: background 0.2s;
  }
  
  .watcher-list-item:hover {
    background: #f9fafb;
  }
  
  .watcher-checkbox {
    margin-right: 1rem;
  }
  
  .watcher-status {
    margin-right: 1rem;
  }
  
  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
  }
  
  .status-dot.active {
    background: #10b981;
    box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
  }
  
  .status-dot.paused {
    background: #f59e0b;
    box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.2);
  }
  
  .status-dot.completed {
    background: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
  }
  
  .watcher-info {
    flex: 1;
  }
  
  .watcher-info h4 {
    margin: 0;
    font-size: 0.95rem;
    font-weight: 600;
    color: #1f2937;
  }
  
  .watcher-pattern {
    margin: 0.25rem 0 0 0;
    font-size: 0.8rem;
    color: #6b7280;
    font-family: monospace;
  }
  
  .watcher-job {
    margin: 0 1rem;
    font-size: 0.85rem;
    color: #6b7280;
  }
  
  .watcher-stats {
    margin: 0 1rem;
  }
  
  .trigger-count {
    font-size: 0.85rem;
    color: #3b82f6;
    font-weight: 500;
  }
  
  .watcher-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .icon-btn {
    padding: 0.5rem;
    background: none;
    border: none;
    border-radius: 6px;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .icon-btn:hover {
    background: #f3f4f6;
    color: #4b5563;
  }
  
  .icon-btn svg {
    width: 18px;
    height: 18px;
  }
  
  /* Activity Feed */
  .quick-actions {
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }
  
  .quick-actions h2 {
    margin: 0 0 1rem 0;
    font-size: 1.25rem;
    color: #1f2937;
  }
  
  .activity-feed {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  
  .activity-item {
    display: flex;
    gap: 1rem;
    padding: 1rem;
    background: #f9fafb;
    border-radius: 8px;
    transition: all 0.2s;
  }
  
  .activity-item:hover {
    background: #f3f4f6;
  }
  
  .activity-icon {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .activity-icon.success {
    background: #d1fae5;
    color: #10b981;
  }
  
  .activity-icon.error {
    background: #fee2e2;
    color: #ef4444;
  }
  
  .activity-icon svg {
    width: 20px;
    height: 20px;
  }
  
  .activity-content {
    flex: 1;
  }
  
  .activity-title {
    font-weight: 600;
    color: #1f2937;
    font-size: 0.9rem;
  }
  
  .activity-description {
    font-size: 0.85rem;
    color: #6b7280;
    margin-top: 0.25rem;
  }
  
  .activity-time {
    font-size: 0.75rem;
    color: #9ca3af;
    margin-top: 0.25rem;
  }
  
  .empty-activity {
    text-align: center;
    padding: 2rem;
    color: #9ca3af;
  }
  
  .empty-activity svg {
    width: 48px;
    height: 48px;
    margin-bottom: 1rem;
    opacity: 0.5;
  }
  
  /* Insights */
  .insights-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 1.5rem;
  }
  
  .insight-card {
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  }
  
  .insight-card h3 {
    margin: 0 0 1rem 0;
    font-size: 1.1rem;
    color: #1f2937;
  }
  
  .insight-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .insight-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem;
    background: #f9fafb;
    border-radius: 6px;
  }
  
  .item-name {
    font-size: 0.9rem;
    color: #4b5563;
  }
  
  .item-value {
    font-size: 0.85rem;
    font-weight: 600;
    color: #3b82f6;
  }
  
  .success-rate-display {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 2rem;
  }
  
  .rate-circle {
    position: relative;
    width: 120px;
    height: 120px;
  }
  
  .rate-circle svg {
    width: 100%;
    height: 100%;
  }
  
  .rate-text {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 1.5rem;
    font-weight: 700;
    color: #10b981;
  }
  
  /* Empty & Loading States */
  .empty-state,
  .loading-state {
    text-align: center;
    padding: 4rem 2rem;
    background: white;
    border-radius: 12px;
  }
  
  .empty-state svg,
  .loading-state svg {
    width: 64px;
    height: 64px;
    color: #d1d5db;
    margin-bottom: 1rem;
  }
  
  .empty-state h3,
  .loading-state h3 {
    margin: 0 0 0.5rem 0;
    font-size: 1.25rem;
    color: #4b5563;
  }
  
  .empty-state p,
  .loading-state p {
    color: #9ca3af;
    margin-bottom: 1.5rem;
  }
  
  .loading-spinner {
    width: 48px;
    height: 48px;
    margin: 0 auto 1rem;
    border: 4px solid #e5e7eb;
    border-top-color: #667eea;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
  
  /* Notification */
  .notification {
    position: fixed;
    top: 2rem;
    right: 2rem;
    padding: 1rem 1.5rem;
    background: white;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    font-size: 0.9rem;
    font-weight: 500;
    z-index: 1000;
  }
  
  .notification.success {
    background: #10b981;
    color: white;
  }
  
  .notification.warning {
    background: #f59e0b;
    color: white;
  }
  
  .notification.error {
    background: #ef4444;
    color: white;
  }
  
  /* Responsive */
  @media (max-width: 768px) {
    
    .action-btn {
      flex: 1;
      justify-content: center;
    }
    
    .stats-grid {
      grid-template-columns: 1fr;
    }
    
    .filter-controls {
      flex-direction: column;
      align-items: stretch;
    }
    
    .filter-chips {
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }
    
    .job-watchers-grid {
      grid-template-columns: 1fr;
    }
    
    .main-content {
      padding: 0.5rem;
    }
    
    .events-content {
      padding: 0;
      margin: 0;
    }
  }
  
  /* Mobile Specific Styles */
  .mobile-header {
    position: sticky;
    top: 0;
    z-index: 100;
    background: white;
    border-bottom: 1px solid #e5e7eb;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    height: 56px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }
  
  .mobile-nav {
    display: flex;
    gap: 0.25rem;
    margin-right: 0.75rem;
  }
  
  .nav-icon-btn {
    position: relative;
    background: none;
    border: none;
    padding: 0.375rem 0.625rem;
    cursor: pointer;
    color: #9ca3af;
    border-radius: 8px;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.125rem;
  }
  
  .nav-icon-btn:hover {
    background: #f3f4f6;
  }
  
  .nav-icon-btn:active {
    transform: scale(0.95);
  }
  
  .nav-icon-btn.active {
    color: #3b82f6;
    background: rgba(59, 130, 246, 0.1);
  }
  
  .nav-icon-btn svg {
    width: 22px;
    height: 22px;
  }
  
  .nav-icon-label {
    font-size: 0.625rem;
    font-weight: 600;
    letter-spacing: 0.025em;
  }
  
  .nav-badge {
    position: absolute;
    top: 4px;
    right: 4px;
    background: #ef4444;
    color: white;
    font-size: 0.625rem;
    font-weight: 600;
    padding: 0.125rem 0.25rem;
    border-radius: 999px;
    min-width: 16px;
    height: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .mobile-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: #1f2937;
    margin: 0;
    flex: 1;
    text-align: center;
  }
  
  .mobile-actions {
    display: flex;
    gap: 0.25rem;
  }
  
  .mobile-header-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .mobile-refresh-btn,
  .mobile-add-btn {
    background: none;
    border: none;
    padding: 0.5rem;
    cursor: pointer;
    color: #4b5563;
    border-radius: 8px;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }
  
  .mobile-refresh-btn:active,
  .mobile-add-btn:active {
    background: #e5e7eb;
    transform: scale(0.95);
  }
  
  .mobile-refresh-btn svg,
  .mobile-add-btn svg {
    width: 24px;
    height: 24px;
  }
  
  .mobile-add-btn {
    background: #3b82f6;
    color: white;
  }
  
  .mobile-add-btn:active {
    background: #2563eb;
  }
  
  /* Mobile Menu */
  .mobile-menu-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 200;
    animation: fadeIn 0.2s;
  }
  
  .mobile-menu {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    width: 280px;
    background: white;
    box-shadow: 2px 0 12px rgba(0, 0, 0, 0.1);
    animation: slideInLeft 0.3s;
    overflow-y: auto;
  }
  
  .mobile-menu-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .mobile-menu-header h2 {
    margin: 0;
    font-size: 1.25rem;
    color: #1f2937;
  }
  
  .close-menu {
    background: none;
    border: none;
    padding: 0.5rem;
    cursor: pointer;
    color: #6b7280;
  }
  
  .close-menu svg {
    width: 20px;
    height: 20px;
  }
  
  .mobile-nav {
    padding: 1rem 0;
  }
  
  .mobile-nav-item {
    display: flex;
    align-items: center;
    gap: 1rem;
    width: 100%;
    padding: 0.875rem 1rem;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    color: #4b5563;
    transition: background 0.2s;
  }
  
  .mobile-nav-item:hover {
    background: #f9fafb;
  }
  
  .mobile-nav-item svg {
    width: 20px;
    height: 20px;
  }
  
  .mobile-nav-item span {
    font-size: 0.9375rem;
    font-weight: 500;
  }
  
  .mobile-menu-actions {
    padding: 1rem;
    border-top: 1px solid #e5e7eb;
  }
  
  .mobile-action-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.75rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
  }
  
  .mobile-action-btn svg {
    width: 18px;
    height: 18px;
  }
  
  .tab-badge {
    position: absolute;
    top: 0.5rem;
    right: calc(50% - 20px);
    background: #ef4444;
    color: white;
    font-size: 0.625rem;
    font-weight: 600;
    padding: 0.125rem 0.25rem;
    border-radius: 10px;
    min-width: 16px;
    text-align: center;
  }
  
  /* Animations */
  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  
  @keyframes slideInLeft {
    from { transform: translateX(-100%); }
    to { transform: translateX(0); }
  }
  
  /* Enhanced Mobile Media Queries */
  @media (max-width: 768px) {
    .watchers-page-enhanced {
      padding-bottom: 60px; /* Space for bottom tabs */
    }
    
    .stats-grid {
      grid-template-columns: 1fr;
      padding: 1rem;
      margin: 1rem 0;
      gap: 0.75rem;
    }
    
    .stat-card {
      padding: 1rem;
    }
    
    .stat-content {
      padding-left: 0.75rem;
    }
    
    .stat-value {
      font-size: 1.5rem;
    }
    
    .watchers-grid {
      grid-template-columns: 1fr;
      padding: 1rem;
      gap: 0.75rem;
    }
    
    .controls-bar {
      flex-direction: column;
      gap: 0.75rem;
      padding: 1rem;
    }
    
    .search-box {
      width: 100%;
    }
    
    .filter-chips {
      width: 100%;
      overflow-x: auto;
      padding-bottom: 0.5rem;
    }
    
    .view-toggle {
      width: 100%;
      justify-content: center;
    }
    
    .insights-grid {
      grid-template-columns: 1fr;
      padding: 1rem;
      gap: 1rem;
    }
    
    .empty-state,
    .loading-state {
      padding: 3rem 1.5rem;
    }
    
    .notification {
      top: 70px;
      left: 1rem;
      right: 1rem;
      transform: none;
    }
    
    /* Hide desktop elements on mobile */
    .minimal-nav-bar,
    .nav-tabs {
      display: none;
    }
    
    /* Optimize touch targets */
    button {
      min-height: 44px;
      min-width: 44px;
    }
    
    /* Improve text readability */
    body {
      -webkit-text-size-adjust: 100%;
    }
    
    /* Smooth scrolling */
    .main-content {
      -webkit-overflow-scrolling: touch;
      padding: 0.75rem;
      padding-bottom: 80px;
    }
    
    /* Optimize card shadows for performance */
    .watcher-card-enhanced,
    .stat-card,
    .insight-card {
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
    }
    
    .watcher-card-enhanced:hover,
    .stat-card:hover,
    .insight-card:hover {
      transform: none;
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.12);
    }
  }
  
  /* Small mobile devices */
  @media (max-width: 480px) {
    .mobile-title {
      font-size: 1rem;
    }
    
    .stat-value {
      font-size: 1.25rem;
    }
    
    .stat-label {
      font-size: 0.75rem;
    }
    
  }
  
  /* Landscape orientation fixes */
  @media (max-height: 500px) and (orientation: landscape) {
    .mobile-header {
      height: 48px;
    }
    
  }
  
  /* Integrated Content Controls - Seamless Navigation */
  .content-controls {
    width: 100%;
    padding: 1rem 2rem;
    background: white;
    border-bottom: 1px solid #e2e8f0;
  }
  
  .view-selection {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .tabs-left {
    display: flex;
    gap: 0.25rem;
  }
  
  .tabs-right {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  
  .view-tab {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 1rem;
    border: none;
    background: transparent;
    border-radius: 8px;
    color: #64748b;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
    outline: none !important;
  }
  
  .view-tab:focus {
    outline: none !important;
    box-shadow: none !important;
  }
  
  .view-tab svg {
    width: 16px;
    height: 16px;
  }
  
  .view-tab:hover {
    background: #f1f5f9;
    color: #475569;
  }
  
  .view-tab.active {
    background: #3b82f6;
    color: white;
    box-shadow: 0 1px 3px rgba(59, 130, 246, 0.2);
  }
  
  .tab-label {
    font-weight: 500;
  }
  
  .tab-action-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    padding: 0;
    border: 1px solid #e2e8f0;
    background: white;
    border-radius: 6px;
    color: #64748b;
    cursor: pointer;
    transition: all 0.15s ease;
    outline: none !important;
  }
  
  .tab-action-btn:focus {
    outline: none !important;
    box-shadow: none !important;
  }
  
  .tab-action-btn:hover {
    background: #f1f5f9;
    border-color: #cbd5e1;
    color: #3b82f6;
  }
  
  .tab-action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .tab-action-btn.primary {
    background: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }
  
  .tab-action-btn.primary:hover {
    background: #2563eb;
  }
  
  .tab-action-btn svg {
    width: 16px;
    height: 16px;
  }
  
  .content-tools {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .search-box {
    position: relative;
    flex: 1;
    max-width: 400px;
    margin-right: 1rem;
  }
  
  .search-icon {
    position: absolute;
    left: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
    width: 18px;
    height: 18px;
    color: #9ca3af;
  }
  
  .search-input {
    width: 100%;
    padding: 0.75rem 2.5rem 0.75rem 3rem;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 0.95rem;
    background: white;
    transition: all 0.2s;
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
    padding: 0.25rem;
    border: none;
    background: none;
    color: #9ca3af;
    cursor: pointer;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .clear-search:hover {
    background: #f3f4f6;
    color: #6b7280;
  }
  
  .clear-search svg {
    width: 16px;
    height: 16px;
  }
  
  .quick-actions {
    display: flex;
    gap: 0.75rem;
  }
  
  .action-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    border: 1px solid #e5e7eb;
    background: transparent;
    border-radius: 8px;
    color: #374151;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .action-btn:hover {
    background: rgba(0, 0, 0, 0.03);
    border-color: #d1d5db;
  }
  
  .action-btn.primary {
    background: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }
  
  .action-btn.primary:hover {
    background: #2563eb;
  }
  
  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .action-btn svg {
    width: 16px;
    height: 16px;
  }
  
  .btn-label {
    font-weight: 600;
  }
  
  .content-summary {
    display: flex;
    align-items: center;
  }
  
  .summary-text {
    color: #6b7280;
    font-size: 0.9rem;
  }
  
  /* Mobile adaptations */
  @media (max-width: 768px) {
    .content-controls {
      padding: 0.75rem 1rem;
    }
    
    .view-selection {
      margin-bottom: 1rem;
      padding-bottom: 0.75rem;
    }
    
    .view-tab {
      padding: 0.5rem 0.75rem;
      font-size: 0.85rem;
    }
    
    .view-tab svg {
      width: 16px;
      height: 16px;
    }
    
    .tab-label {
      display: none;
    }
    
    .content-tools {
      flex-direction: column;
      gap: 0.75rem;
      align-items: stretch;
    }
    
    .search-box {
      max-width: none;
      margin-right: 0;
    }
    
    .quick-actions {
      justify-content: space-between;
    }
    
    .action-btn {
      flex: 1;
      justify-content: center;
    }
    
    .btn-label {
      display: none;
    }
    
    .content-summary {
      justify-content: center;
      margin-bottom: 0.5rem;
    }
    
    .summary-text {
      font-size: 0.8rem;
      text-align: center;
    }
  }
</style>