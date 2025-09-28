<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
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
  import { jobStateManager } from '../lib/JobStateManager';
  import WatcherCard from '../components/WatcherCard.svelte';
  import WatcherEvents from '../components/WatcherEvents.svelte';
  import WatcherTimeline from '../components/WatcherTimeline.svelte';
  import WatcherMetrics from '../components/WatcherMetrics.svelte';
  import AttachWatchersDialog from '../components/AttachWatchersDialog.svelte';
  import JobSelectionDialog from '../components/JobSelectionDialog.svelte';
  
  // UI Components
  import Button from '../lib/components/ui/Button.svelte';
  import Badge from '../lib/components/ui/Badge.svelte';
  import Input from '../lib/components/ui/Input.svelte';
  import Card from '../lib/components/ui/Card.svelte';
  import Skeleton from '../lib/components/ui/Skeleton.svelte';
  import Alert from '../lib/components/ui/Alert.svelte';
  
  // Lucide Icons
  import {
    Eye,
    Bell,
    BarChart3,
    RefreshCw,
    Plus,
    Search,
    X,
    Grid3X3,
    List,
    Clock,
    CheckCircle,
    Pause,
    Circle,
    ChevronDown,
    Menu,
    Filter,
    ArrowLeft
  } from 'lucide-svelte';

  // Get jobs store from JobStateManager
  const allCurrentJobs = jobStateManager.getAllJobs();
  
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
  let searchExpanded = false;
  let searchInput: HTMLInputElement;
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
  
  // Lifecycle
  onMount(async () => {
    // Check if mobile
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    await refreshData();
    // Fetch jobs for cross-referencing with watchers
    await jobStateManager.forceRefresh();
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
      // Sync job data
      await jobStateManager.syncAllHosts();
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
    await jobStateManager.forceRefresh();
    const allJobs = jobStateManager.getAllJobs();
    const runningJobs = get(allJobs).filter(job => 
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

  function toggleSearch() {
    searchExpanded = !searchExpanded;
    if (!searchExpanded) {
      searchQuery = '';
    } else {
      // Focus the input after expanding
      setTimeout(() => searchInput?.focus(), 100);
    }
  }

  function handleBackNavigation() {
    if (window.history.length > 1) {
      window.history.back();
    } else {
      push('/dashboard');
    }
  }

  function focus(element) {
    element.focus();
  }
</script>

<div 
  class="h-full flex flex-col bg-background relative" 
  on:touchstart={handleTouchStart} 
  on:touchend={handleTouchEnd}
>
  
  <!-- Subtle gradient accent at the top -->
  <div class="absolute top-0 left-0 right-0 h-48 bg-gradient-to-b from-primary/5 to-transparent pointer-events-none z-0"></div>

  <!-- Desktop Header -->
  {#if !isMobile}
    <div class="w-full p-4 lg:px-8 bg-white border-b border-gray-200 relative z-10" transition:slide={{ duration: 300 }}>
      <!-- Navigation Header -->
      <div class="flex justify-between items-center mb-4">
        <div class="flex items-center gap-3">
          <!-- Back Button (just arrow) -->
          <Button
            variant="ghost"
            size="icon"
            class="h-8 w-8"
            on:click={handleBackNavigation}
            title="Back"
          >
            <ArrowLeft class="h-4 w-4" />
          </Button>

          <!-- Tab Selection -->
          <div class="flex gap-1">
            <Button
              variant={activeTab === 'watchers' ? 'default' : 'ghost'}
              size="sm"
              class="gap-2"
              on:click={() => activeTab = 'watchers'}
            >
              <Eye class="h-4 w-4" />
              <span>Watchers</span>
            </Button>
            <Button
              variant={activeTab === 'events' ? 'default' : 'ghost'}
              size="sm"
              class="gap-2"
              on:click={() => activeTab = 'events'}
            >
              <Bell class="h-4 w-4" />
              <span>Events</span>
            </Button>
            <Button
              variant={activeTab === 'metrics' ? 'default' : 'ghost'}
              size="sm"
              class="gap-2"
              on:click={() => activeTab = 'metrics'}
            >
              <BarChart3 class="h-4 w-4" />
              <span>Metrics</span>
            </Button>
          </div>
        </div>

        <!-- Tab Actions on the right -->
        <div class="flex items-center gap-2">
          <!-- Expandable Search (Desktop) -->
          <div class="search-container" class:expanded={searchExpanded}>
            {#if searchExpanded}
              <div class="relative">
                <Search class="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Search watchers..."
                  bind:value={searchQuery}
                  class="pl-10 pr-10 w-64"
                  on:blur={() => { if (!searchQuery) toggleSearch(); }}
                  bind:this={searchInput}
                />
                {#if searchQuery}
                  <Button
                    variant="ghost"
                    size="icon"
                    class="absolute right-1 top-1/2 transform -translate-y-1/2 h-6 w-6"
                    on:click={() => searchQuery = ''}
                  >
                    <X class="h-4 w-4" />
                  </Button>
                {/if}
              </div>
            {:else}
              <Button
                variant="ghost"
                size="icon"
                class="h-8 w-8"
                on:click={toggleSearch}
                title="Search"
              >
                <Search class="h-4 w-4" />
              </Button>
            {/if}
          </div>

          <Button
            variant="ghost"
            size="icon"
            on:click={() => refreshData()}
            disabled={$watchersLoading}
            class="h-8 w-8"
            title="Refresh"
          >
            <RefreshCw class="h-4 w-4 {$watchersLoading ? 'animate-spin' : ''}" />
          </Button>

          {#if activeTab === 'watchers'}
            <!-- New Watcher Button (just plus) -->
            <Button
              size="icon"
              class="h-8 w-8"
              on:click={openAttachDialog}
              title="New Watcher"
            >
              <Plus class="h-4 w-4" />
            </Button>
          {/if}
        </div>
      </div>
    </div>
  {:else}
    <!-- Mobile Header -->
    <div class="mobile-header border-b border-gray-200">
      <!-- Top row: Back button, tabs, and actions -->
      <div class="mobile-header-row">
        <!-- Back Button -->
        <Button
          variant="ghost"
          size="icon"
          class="h-8 w-8 flex-shrink-0"
          on:click={handleBackNavigation}
          title="Back"
        >
          <ArrowLeft class="h-4 w-4" />
        </Button>

        <!-- Tab Selection -->
        <div class="flex gap-1 flex-1 justify-center">
          <Button
            variant={activeTab === 'watchers' ? 'default' : 'ghost'}
            size="sm"
            class="gap-2"
            on:click={() => activeTab = 'watchers'}
          >
            <Eye class="h-4 w-4" />
            <span class="text-xs">Watchers</span>
          </Button>
          <Button
            variant={activeTab === 'events' ? 'default' : 'ghost'}
            size="sm"
            class="gap-2"
            on:click={() => activeTab = 'events'}
          >
            <Bell class="h-4 w-4" />
            <span class="text-xs">Events</span>
          </Button>
        </div>

        <!-- Flexible spacer to push actions to the right -->
        <div style="flex: 1;"></div>

        <!-- Expandable search -->
        <div class="mobile-search-container {searchExpanded ? 'expanded' : ''}">
          {#if searchExpanded}
            <div class="search-bar expanded">
              <div class="search-icon">
                <Search size={16} />
              </div>
              <input
                type="text"
                class="search-input"
                placeholder="Search..."
                bind:value={searchQuery}
                on:blur={() => { if (!searchQuery) searchExpanded = false; }}
                bind:this={searchInput}
              />
              {#if searchQuery}
                <button class="clear-btn" on:click={() => searchQuery = ''}>
                  <X size={14} />
                </button>
              {/if}
            </div>
          {:else}
            <button class="search-toggle-btn" on:click={() => { searchExpanded = true; setTimeout(() => searchInput?.focus(), 100); }}>
              <Search size={16} />
            </button>
          {/if}
        </div>

        <!-- Action buttons on the right -->
        <button
          on:click={() => refreshData()}
          disabled={$watchersLoading}
          class="refresh-btn"
          title="{$watchersLoading ? 'Loading...' : 'Refresh'}"
        >
          <RefreshCw class="icon {$watchersLoading ? 'animate-spin' : ''}" />
        </button>

        {#if activeTab === 'watchers'}
          <button
            on:click={openAttachDialog}
            class="refresh-btn"
            title="New Watcher"
          >
            <Plus class="icon" />
          </button>
        {/if}
      </div>
    </div>
  {/if}
    
    {#if activeTab === 'watchers'}
      
      <!-- Filter chips -->
      <div class="flex flex-col sm:flex-row gap-4 justify-between items-start sm:items-center">
        <div class="flex gap-2 overflow-x-auto pb-2 sm:pb-0">
          <Button
            variant={filterState === 'all' ? 'default' : 'outline'}
            size="sm"
            class="watcher-filter-btn"
            on:click={() => filterState = 'all'}
          >
            <span class="mobile-filter-text hidden sm:inline">All</span>
            <span class="mobile-filter-count">({totalWatchers})</span>
          </Button>
          <Button
            variant={filterState === 'active' ? 'default' : 'outline'}
            size="sm"
            class="gap-2 watcher-filter-btn"
            on:click={() => filterState = 'active'}
          >
            <div class="h-2 w-2 rounded-full bg-green-500"></div>
            <span class="mobile-filter-text hidden sm:inline">Active</span>
            <span class="mobile-filter-count">({activeCount})</span>
          </Button>
          <Button
            variant={filterState === 'paused' ? 'default' : 'outline'}
            size="sm"
            class="gap-2 watcher-filter-btn"
            on:click={() => filterState = 'paused'}
          >
            <div class="h-2 w-2 rounded-full bg-yellow-500"></div>
            <span class="mobile-filter-text hidden sm:inline">Paused</span>
            <span class="mobile-filter-count">({pausedCount})</span>
          </Button>
          <Button
            variant={filterState === 'completed' ? 'default' : 'outline'}
            size="sm"
            class="gap-2 watcher-filter-btn"
            on:click={() => filterState = 'completed'}
          >
            <div class="h-2 w-2 rounded-full bg-blue-500"></div>
            <span class="mobile-filter-text hidden sm:inline">Completed</span>
            <span class="mobile-filter-count">({completedCount})</span>
          </Button>
        </div>
        
        <div class="flex gap-2 items-center">
          <select 
            bind:value={sortBy}
            class="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <option value="recent">Most Recent</option>
            <option value="name">Name</option>
            <option value="triggers">Most Triggers</option>
            <option value="job">Job ID</option>
          </select>
          
          <div class="flex rounded-lg border border-border p-1 bg-muted">
            <Button 
              variant={viewMode === 'grid' ? 'secondary' : 'ghost'}
              size="icon"
              class="h-7 w-7"
              on:click={() => viewMode = 'grid'}
            >
              <Grid3X3 class="h-4 w-4" />
            </Button>
            <Button 
              variant={viewMode === 'list' ? 'secondary' : 'ghost'}
              size="icon"
              class="h-7 w-7"
              on:click={() => viewMode = 'list'}
            >
              <List class="h-4 w-4" />
            </Button>
            <Button 
              variant={viewMode === 'timeline' ? 'secondary' : 'ghost'}
              size="icon"
              class="h-7 w-7"
              on:click={() => viewMode = 'timeline'}
            >
              <Clock class="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    {/if}
    
    {#if activeTab === 'metrics' && !isMobile}
      <!-- Metrics summary -->
      <div class="flex items-center">
        <span class="text-sm text-muted-foreground">Analytics and performance insights</span>
      </div>
    {/if}
  </div>
  
  <!-- Main Content -->
  <main class="flex-1 overflow-y-auto p-2 sm:p-4 lg:p-6">
    {#if activeTab === 'watchers'}
      <!-- Watchers Content -->
      <div class="space-y-6">
        {#if $watchersLoading}
          <div class="flex flex-col items-center justify-center py-16 space-y-4">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
            <p class="text-muted-foreground">Loading watchers...</p>
          </div>
        {:else if sortedWatchers.length === 0}
          <div class="flex flex-col items-center justify-center py-16 space-y-4" in:scale={{ duration: 300 }}>
            <Eye class="h-16 w-16 text-muted-foreground/50" />
            <h3 class="text-xl font-semibold">No watchers found</h3>
            <p class="text-muted-foreground text-center">
              {#if searchQuery}
                No watchers match your search criteria.
              {:else if filterState !== 'all'}
                No {filterState} watchers at the moment.
              {:else}
                Create your first watcher to start monitoring jobs.
              {/if}
            </p>
            <Button on:click={openAttachDialog} class="mt-4">
              <Plus class="h-4 w-4 mr-2" />
              Create Watcher
            </Button>
          </div>
        {:else if viewMode === 'grid'}
          <!-- Grid View -->
          <div class="space-y-6">
            {#each Object.entries(watchersByJob) as [jobKey, jobGroup]}
              <Card 
                class="overflow-hidden transition-all duration-200 hover:shadow-lg"
              >
                <button 
                  class="w-full p-4 bg-muted/50 dark:bg-muted/20 border-b border-border hover:bg-muted/70 dark:hover:bg-muted/30 transition-colors text-left flex justify-between items-center"
                  on:click={() => toggleJobGroup(jobKey)}
                >
                  <div class="space-y-1">
                    <h3 class="text-lg font-semibold flex items-center gap-2">
                      Job #{jobGroup.job_id}
                      {#if jobGroup.job_name}
                        <span class="text-muted-foreground font-normal">• {jobGroup.job_name}</span>
                      {/if}
                    </h3>
                    <p class="text-sm text-muted-foreground">{jobGroup.hostname}</p>
                  </div>
                  
                  <div class="flex items-center gap-6">
                    <div class="text-center">
                      <div class="text-lg font-semibold">{jobGroup.watchers.length}</div>
                      <div class="text-xs text-muted-foreground">watchers</div>
                    </div>
                    <div class="text-center">
                      <div class="text-lg font-semibold text-green-600">{jobGroup.stats.active}</div>
                      <div class="text-xs text-green-600">active</div>
                    </div>
                    <ChevronDown
                      class="h-5 w-5 text-muted-foreground transition-transform duration-300 {!collapsedJobs.has(jobKey) ? 'rotate-180' : ''}"
                    />
                  </div>
                </button>
                
                {#if !collapsedJobs.has(jobKey)}
                  <div class="p-4 grid grid-cols-1 xl:grid-cols-2 2xl:grid-cols-3 gap-4" transition:slide={{ duration: 300 }}>
                    {#each jobGroup.watchers as watcher}
                      <div class="transition-all duration-200 hover:scale-[1.02]" in:scale={{ duration: 200 }}>
                        <WatcherCard 
                          {watcher}
                          showJobLink={false}
                          on:copy={handleWatcherCopy}
                        />
                      </div>
                    {/each}
                  </div>
                {/if}
              </Card>
            {/each}
          </div>
          
        {:else if viewMode === 'list'}
          <!-- List View -->
          <Card class="overflow-hidden">
            {#each sortedWatchers as watcher, i}
              <div 
                class="flex items-center p-4 border-b border-border last:border-b-0 hover:bg-muted/50 dark:hover:bg-muted/20 transition-colors"
                in:fly={{ x: -20, duration: 300, delay: i * 50 }}
              >
                <div class="mr-4">
                  <input 
                    type="checkbox"
                    checked={selectedWatchers.has(watcher.id)}
                    on:change={() => selectWatcher(watcher.id)}
                    class="rounded border-input"
                  />
                </div>
                
                <div class="mr-4">
                  {#if watcher.state === 'active'}
                    <div class="h-3 w-3 rounded-full bg-green-500 shadow-sm shadow-green-500/50"></div>
                  {:else if watcher.state === 'paused'}
                    <div class="h-3 w-3 rounded-full bg-yellow-500 shadow-sm shadow-yellow-500/50"></div>
                  {:else}
                    <div class="h-3 w-3 rounded-full bg-blue-500 shadow-sm shadow-blue-500/50"></div>
                  {/if}
                </div>
                
                <div class="flex-1 min-w-0">
                  <h4 class="font-semibold text-sm truncate">{watcher.name}</h4>
                  <p class="text-xs text-muted-foreground font-mono truncate">{watcher.pattern}</p>
                </div>
                
                <div class="mx-4 text-sm text-muted-foreground">
                  Job #{watcher.job_id}
                </div>
                
                <div class="mx-4 text-sm">
                  <Badge variant="outline">
                    {watcher.trigger_count || 0} triggers
                  </Badge>
                </div>
                
                <div class="flex gap-1">
                  <Button 
                    variant="ghost"
                    size="icon"
                    class="h-8 w-8"
                    on:click={() => push(`/watchers?tab=events&watcher=${watcher.id}`)}
                  >
                    <Eye class="h-4 w-4" />
                  </Button>
                </div>
              </div>
            {/each}
          </Card>
          
        {:else if viewMode === 'timeline'}
          <!-- Timeline View -->
          <div class="space-y-4">
            <WatcherTimeline events={$watcherEvents} />
          </div>
        {/if}
      </div>
      
    {:else if activeTab === 'events'}
      <div in:fade={{ duration: 300 }}>
        <WatcherEvents 
          events={filterWatcherId ? 
            $watcherEvents.filter(e => e.watcher_id === filterWatcherId) : 
            $watcherEvents
          } 
          loading={$eventsLoading} 
        />
      </div>
      
    {:else if !isMobile && activeTab === 'metrics'}
      <div in:fade={{ duration: 300 }}>
        <WatcherMetrics events={$watcherEvents} />
      </div>
      
    {/if}
  </main>
  
  <!-- Notification -->
  {#if notification}
    <div 
      class="fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium"
      class:bg-green-500={notification.type === 'success'}
      class:bg-yellow-500={notification.type === 'warning'}  
      class:bg-red-500={notification.type === 'error'}
      class:text-white={true}
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
  .search-container {
    display: flex;
    align-items: center;
    transition: all 0.3s ease;
  }

  .search-container.expanded {
    min-width: 250px;
    flex: 1;
    max-width: 100%;
  }

  /* Mobile Header Styles */
  .mobile-header {
    padding: 0.75rem 1rem;
    background: white;
  }

  .mobile-header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    min-height: 40px;
  }

  .mobile-search-container {
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
  }

  .mobile-search-container:not(.expanded) {
    width: 32px;
  }

  .mobile-search-container.expanded {
    width: 180px;
    max-width: 180px;
  }

  .search-toggle-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.2s;
  }

  .search-toggle-btn:hover {
    background: #f3f4f6;
    color: #374151;
  }

  .search-bar {
    position: relative;
    width: 100%;
  }

  .search-bar.expanded {
    width: 100%;
    animation: searchExpand 0.4s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  }

  @keyframes searchExpand {
    from {
      width: 32px;
      opacity: 0;
    }
    to {
      width: 100%;
      opacity: 1;
    }
  }

  .search-icon {
    position: absolute;
    left: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
    color: #9ca3af;
    pointer-events: none;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .search-input {
    width: 100%;
    padding: 0.5rem 2.5rem 0.5rem 2.5rem;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    transition: all 0.15s;
    background: #f9fafb;
  }

  .search-input:focus {
    outline: none;
    border-color: #3b82f6;
    background: white;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .search-input::placeholder {
    color: #9ca3af;
  }

  .clear-btn {
    position: absolute;
    right: 0.5rem;
    top: 50%;
    transform: translateY(-50%);
    padding: 0.25rem;
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    border-radius: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }

  .clear-btn:hover {
    background: #f3f4f6;
    color: #ef4444;
  }

  .refresh-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.375rem;
    padding: 0.5rem;
    width: 32px;
    height: 32px;
    background: white;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 0.5rem;
    font-size: 0.813rem;
    font-weight: 500;
    color: #475569;
    cursor: pointer;
    transition: all 0.15s;
    flex-shrink: 0;
  }

  .refresh-btn:hover:not(:disabled) {
    background: #f8fafc;
    border-color: rgba(0, 0, 0, 0.12);
  }

  .refresh-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .icon {
    width: 1rem;
    height: 1rem;
  }

  .animate-spin {
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
</style>