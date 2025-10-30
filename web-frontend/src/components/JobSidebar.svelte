<!-- @migration-task Error while migrating Svelte code: can't migrate `$: actuallyCollapsed = !isMobile && collapsed;` to `$derived` because there's a variable named derived.
     Rename the variable and try again or migrate by hand. -->
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { push, location } from 'svelte-spa-router';
  import type { JobInfo } from '../types/api';
  import { jobStateManager } from '../lib/JobStateManager';
  import { jobUtils } from '../lib/jobUtils';
  import { navigationActions } from '../stores/navigation';
  import { preferences, preferencesActions } from '../stores/preferences';
  import { debounce } from '../lib/debounce';
  import ArrayJobCard from './ArrayJobCard.svelte';
  import LoadingSpinner from './LoadingSpinner.svelte';
  import CollapsibleSection from '../lib/components/ui/CollapsibleSection.svelte';
  import { Eye } from 'lucide-svelte';
  import { watchersByJob } from '../stores/watchers';

  interface Props {
    currentJobId?: string;
    currentHost?: string;
    collapsed?: boolean;
    isMobile?: boolean;
    onMobileJobSelect?: (() => void);
    onClose?: (() => void);
  }

  let {
    currentJobId = '',
    currentHost = '',
    collapsed = $bindable(false),
    isMobile = false,
    onMobileJobSelect = undefined,
    onClose = undefined
  }: Props = $props();

  // On mobile, we never want the sidebar to be collapsed
  let actuallyCollapsed = $derived(!isMobile && collapsed);

  let loading = $state(false);
  let hamburgerToX = $state(false);
  let isClosing = $state(false);
  let searchInputValue = $state('');
  let searchQuery = $state(''); // This will be the debounced value
  let searchFocused = $state(false);
  let showSearch = $state(false);

  // Get reactive stores from JobStateManager
  const allJobs = jobStateManager.getAllJobs();
  const runningJobs = jobStateManager.getJobsByState('R');
  const pendingJobs = jobStateManager.getJobsByState('PD');
  const connectionStatus = jobStateManager.getConnectionStatus();
  const managerState = jobStateManager.getState();
  const arrayJobGroups = jobStateManager.getArrayJobGroups(); // ✅ Use JobStateManager's array groups

  // Derive hasArrayJobGrouping from arrayJobGroups store
  import { derived } from 'svelte/store';
  const hasArrayJobGrouping = derived(arrayJobGroups, $groups => $groups && $groups.length > 0);

  // Compute recent jobs from all jobs
  let recentJobs = $derived($allJobs.filter(j => j && j.state && jobUtils.isTerminalState(j.state)).slice(0, 50));

  // Create filtered arrays with optimized computation
  let filteredRunningJobs = $state<JobInfo[]>([]);
  let filteredPendingJobs = $state<JobInfo[]>([]);
  let filteredRecentJobs = $state<JobInfo[]>([]);

  // For array job groups
  let filteredArrayGroups = $state<any[]>([]);
  let arrayTaskIds = new Set<string>();

  // Track which jobs are part of array groups
  $effect(() => {
    arrayTaskIds.clear();
    if ($preferences.groupArrayJobs && $hasArrayJobGrouping && $arrayJobGroups) {
      $arrayJobGroups.forEach(group => {
        if (group.tasks && Array.isArray(group.tasks)) {
          group.tasks.forEach(task => {
            if (task && task.job_id && task.hostname) {
              arrayTaskIds.add(`${task.job_id}-${task.hostname}`);
            }
          });
        }
      });
    }
  });

  // Categorize array groups by activity state using $derived
  let runningArrayGroups = $derived(filteredArrayGroups.filter(g => g.running_count > 0));
  let pendingArrayGroups = $derived(filteredArrayGroups.filter(g =>
    g.pending_count > 0 && g.running_count === 0
  ));
  let completedArrayGroups = $derived(filteredArrayGroups.filter(g =>
    g.running_count === 0 && g.pending_count === 0
  ));

  // Filter jobs to exclude those in array groups when grouping is enabled
  function filterOutArrayTasks(jobs: JobInfo[]): JobInfo[] {
    if (!$preferences.groupArrayJobs || !$hasArrayJobGrouping) {
      return jobs;
    }
    return jobs.filter(job => {
      // Check if it's an individual task that's been grouped
      if (arrayTaskIds.has(`${job.job_id}-${job.hostname}`)) {
        return false;
      }

      // Check if it's a parent array job (has brackets in job_id like "2187421_[0-4]")
      if (job.job_id.includes('[') && job.job_id.includes(']')) {
        // Extract the array ID (part before underscore)
        const arrayId = job.job_id.split('_')[0];
        // Hide parent job if we have a group for this array
        if ($arrayJobGroups && $arrayJobGroups.some(g => g.array_job_id === arrayId && g.hostname === job.hostname)) {
          return false;
        }
      }

      return true;
    });
  }

  // Debounced search update function
  const updateSearchQuery = debounce((value: string) => {
    searchQuery = value;
  }, 150); // 150ms debounce delay

  // Update search query when input changes
  $effect(() => {
    updateSearchQuery(searchInputValue);
  });

  // Use $effect to handle filtering synchronously (no requestAnimationFrame needed)
  $effect(() => {
    const baseRunning = filterOutArrayTasks($runningJobs);
    const basePending = filterOutArrayTasks($pendingJobs);
    const baseRecent = filterOutArrayTasks(recentJobs);

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filteredRunningJobs = baseRunning.filter(job => matchesSearch(job, query));
      filteredPendingJobs = basePending.filter(job => matchesSearch(job, query));
      filteredRecentJobs = baseRecent.filter(job => matchesSearch(job, query));

      // Filter array groups (only when grouping is enabled)
      if ($preferences.groupArrayJobs && $hasArrayJobGrouping && $arrayJobGroups) {
        filteredArrayGroups = $arrayJobGroups.filter(group =>
          group.array_job_id.toLowerCase().includes(query) ||
          group.job_name.toLowerCase().includes(query)
        );
      } else {
        filteredArrayGroups = [];
      }
    } else {
      filteredRunningJobs = baseRunning;
      filteredPendingJobs = basePending;
      filteredRecentJobs = baseRecent;
      // Only populate array groups when grouping is enabled
      filteredArrayGroups = ($preferences.groupArrayJobs && $arrayJobGroups) ? $arrayJobGroups : [];
    }
  });

  let hasSearchResults = $derived(
    filteredRunningJobs.length > 0 ||
    filteredPendingJobs.length > 0 ||
    filteredRecentJobs.length > 0 ||
    runningArrayGroups.length > 0 ||
    pendingArrayGroups.length > 0 ||
    completedArrayGroups.length > 0
  );

  function matchesSearch(job: JobInfo, query: string): boolean {
    // Early return for better performance
    if (!query) return true;

    // Cache lowercase values
    const jobIdLower = job.job_id.toLowerCase();
    if (jobIdLower.includes(query)) return true;

    if (job.name) {
      const nameLower = job.name.toLowerCase();
      if (nameLower.includes(query)) return true;
    }

    if (job.hostname) {
      const hostnameLower = job.hostname.toLowerCase();
      if (hostnameLower.includes(query)) return true;
    }

    if (job.partition) {
      const partitionLower = job.partition.toLowerCase();
      if (partitionLower.includes(query)) return true;
    }

    if (!job.state) return false;
    const stateNameLower = jobUtils.getStateLabel(job.state).toLowerCase();
    return stateNameLower.includes(query);
  }

  function toggleSearch() {
    showSearch = !showSearch;
    if (showSearch) {
      // Focus the input immediately and after animation to ensure keyboard opens on mobile
      // Immediate focus for mobile keyboard
      requestAnimationFrame(() => {
        const input = document.querySelector('.sidebar-search-input') as HTMLInputElement;
        if (input) {
          input.focus();
          // Force click event on mobile to ensure keyboard appears
          if (isMobile) {
            input.click();
          }
        }
      });
      // Additional delayed focus in case animation interferes
      setTimeout(() => {
        const input = document.querySelector('.sidebar-search-input') as HTMLInputElement;
        if (input) input.focus();
      }, 100);
    } else {
      searchInputValue = '';
      searchQuery = '';
      searchFocused = false;
    }
  }

  function clearSearch() {
    searchInputValue = '';
    searchQuery = '';
    const input = document.querySelector('.sidebar-search-input') as HTMLInputElement;
    if (input) input.focus();
  }
  
  // Track loading state
  let isLoading = $derived(Array.from($managerState.hostStates.values()).some(h => h.status === 'loading'));
  
  async function loadJobs(forceRefresh = false) {
    if (loading) return;
    
    try {
      loading = true;
      
      if (forceRefresh) {
        await jobStateManager.forceRefresh();
      } else {
        await jobStateManager.syncAllHosts();
      }
      
      setTimeout(() => loading = false, 500);
    } catch (error) {
      console.error('Error loading jobs for sidebar:', error);
      loading = false;
    }
  }
  
  function selectJob(job: JobInfo) {
    // Track where we're coming from for smart back navigation
    navigationActions.setPreviousRoute($location);

    // Navigate to the job with URL encoding for safety
    const encodedJobId = encodeURIComponent(job.job_id);
    push(`/jobs/${encodedJobId}/${job.hostname}`);

    // Close mobile sidebar if callback provided
    if (isMobile && onMobileJobSelect) {
      onMobileJobSelect();
    }
  }
  
  // Use centralized job utilities
  
  function formatRuntime(runtime: string | null): string {
    if (!runtime || runtime === 'N/A') return '';
    return runtime;
  }
  
  function formatJobName(name: string | null): string {
    if (!name) return 'Unnamed Job';
    // Remove file extension if present
    const cleanName = name.replace(/\.(sh|slurm|sbatch)$/, '');
    if (cleanName.length > 28) {
      return cleanName.substring(0, 25) + '...';
    }
    return cleanName;
  }

  function hasWatchers(jobId: string): boolean {
    return ($watchersByJob[jobId]?.length || 0) > 0;
  }

  function getWatcherCount(jobId: string): number {
    return $watchersByJob[jobId]?.length || 0;
  }

  function formatWatcherCount(count: number): string {
    return count > 99 ? '99+' : count.toString();
  }

  onMount(() => {
    // JobStateManager automatically handles initial load

    // Trigger hamburger animation after sidebar slides in
    if (isMobile) {
      // Reset states on mount
      isClosing = false;
      hamburgerToX = false;

      // Start morphing to X after slide begins
      setTimeout(() => {
        hamburgerToX = true;
      }, 200); // Start morphing partway through slide animation
    }
  });
  
  onDestroy(() => {
    // Cleanup handled by JobStateManager
  });
</script>

<div class="job-sidebar" class:collapsed={actuallyCollapsed} class:mobile={isMobile} class:closing={isClosing}>
  <div class="sidebar-header">
    {#if !actuallyCollapsed}
    <div class="header-actions">
      <!-- Search button -->
      <button
        class="icon-btn search-toggle"
        class:active={showSearch}
        onclick={toggleSearch}
        aria-label="Search jobs"
        title="Search jobs"
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z"/>
        </svg>
      </button>

      <!-- Array grouping toggle -->
      <button
        class="icon-btn"
        class:active={$preferences.groupArrayJobs}
        onclick={async () => {
          preferencesActions.toggleArrayGrouping();
          // Trigger a refresh to fetch data with new grouping preference
          await loadJobs(true);
        }}
        aria-label="Toggle array job grouping"
        title={$preferences.groupArrayJobs ? "Disable array job grouping" : "Enable array job grouping"}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          {#if $preferences.groupArrayJobs}
            <path d="M19,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5A2,2 0 0,0 19,3M5,7H19V9H5V7M5,11H19V13H5V11M5,15H19V17H5V15" />
          {:else}
            <path d="M3,3H21V5H3V3M3,7H21V9H3V7M3,11H21V13H3V11M3,15H21V17H3V15M3,19H21V21H3V19Z" />
          {/if}
        </svg>
      </button>

      <!-- Refresh button -->
      <button class="icon-btn" onclick={() => loadJobs(true)} disabled={loading || isLoading} aria-label="Refresh jobs">
        <svg viewBox="0 0 24 24" fill="currentColor" class:spinning={loading || isLoading}>
          <path d="M12,6V9L16,5L12,1V4A8,8 0 0,0 4,12C4,13.57 4.46,15.03 5.24,16.26L6.7,14.8C6.25,13.97 6,13 6,12A6,6 0 0,1 12,6M18.76,7.74L17.3,9.2C17.74,10.04 18,11 18,12A6,6 0 0,1 12,18V15L8,19L12,23V20A8,8 0 0,0 20,12C20,10.43 19.54,8.97 18.76,7.74Z" />
        </svg>
      </button>
      {#if isMobile && onClose}
        <button class="close-btn" onclick={() => {
          isClosing = true;
          hamburgerToX = false;  // Start morphing back to hamburger
          setTimeout(() => {
            onClose();
            isClosing = false;  // Reset for next open
          }, 400);
        }} aria-label="Close job list">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class={hamburgerToX ? 'hamburger-to-x' : ''}>
            <line x1="3" y1="6" x2="21" y2="6" class="hamburger-line top" />
            <line x1="3" y1="12" x2="21" y2="12" class="hamburger-line middle" />
            <line x1="3" y1="18" x2="21" y2="18" class="hamburger-line bottom" />
          </svg>
        </button>
      {/if}
    </div>
    {/if}
  </div>

  <!-- Animated Search Bar -->
  {#if !actuallyCollapsed && showSearch}
    <div class="search-container" class:focused={searchFocused}>
      <div class="search-wrapper">
        <svg viewBox="0 0 24 24" fill="currentColor" class="search-icon">
          <path d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z"/>
        </svg>
        <input
          type="text"
          class="sidebar-search-input"
          placeholder="Search jobs..."
          bind:value={searchInputValue}
          onfocus={() => searchFocused = true}
          onblur={() => searchFocused = false}
        />
        {#if searchInputValue}
          <button
            class="clear-btn"
            onclick={clearSearch}
            aria-label="Clear search"
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
            </svg>
          </button>
        {/if}
      </div>
    </div>
  {/if}

  {#if !actuallyCollapsed}
  <div class="sidebar-content">
    {#if loading && $allJobs.length === 0}
      <div class="loading-state">
        <LoadingSpinner size="sm" message="Loading jobs..." centered={false} />
      </div>
    {:else}
      <!-- Running Jobs (includes running array groups when grouping enabled) -->
      {#if filteredRunningJobs.length > 0 || ($preferences.groupArrayJobs && runningArrayGroups.length > 0)}
        <div class="job-section">
          <h4 class="section-title">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M8,5.14V19.14L19,12.14L8,5.14Z" />
            </svg>
            Running ({filteredRunningJobs.length}{#if $preferences.groupArrayJobs && runningArrayGroups.length > 0} + {runningArrayGroups.length} ARRAYS{/if}{#if searchQuery && $runningJobs.length !== filteredRunningJobs.length} <span class="search-count">of {$runningJobs.length}</span>{/if})
          </h4>
          <div class="job-list">
            <!-- Running array groups first -->
            {#if $preferences.groupArrayJobs}
              {#each runningArrayGroups as group (group.array_job_id + group.hostname)}
                <div class="array-job-wrapper">
                  <ArrayJobCard {group} />
                </div>
              {/each}
            {/if}

            <!-- Then individual running jobs -->
            {#each filteredRunningJobs as job (job.job_id + job.hostname)}
              <button
                class="job-item"
                class:selected={currentJobId === job.job_id && currentHost === job.hostname}
                onclick={() => selectJob(job)}
              >
                <div class="job-status" style="background-color: {job.state ? jobUtils.getStateColor(job.state) : '#9ca3af'}"></div>
                <div class="job-info">
                  <div class="job-header">
                    <div class="job-id-wrapper">
                      <span class="job-id">{job.job_id}</span>
                      {#if hasWatchers(job.job_id)}
                        <span class="watcher-indicator" title="{getWatcherCount(job.job_id)} watcher(s) active">
                          <Eye size={12} />
                          <span class="watcher-count">{formatWatcherCount(getWatcherCount(job.job_id))}</span>
                        </span>
                      {/if}
                    </div>
                    {#if job.runtime}
                      <span class="job-runtime-badge runtime-active">{formatRuntime(job.runtime)}</span>
                    {/if}
                  </div>
                  <div class="job-content">
                    <span class="job-name">{formatJobName(job.name)}</span>
                    <span class="job-state-label state-running">
                      <svg viewBox="0 0 24 24" fill="currentColor" class="state-icon">
                        <path d="M8,5.14V19.14L19,12.14L8,5.14Z" />
                      </svg>
                      Running
                    </span>
                  </div>
                  <div class="job-meta">
                    <span class="job-host">{job.hostname.toUpperCase()}</span>
                  </div>
                </div>
              </button>
            {/each}
          </div>
        </div>
      {/if}
      
      <!-- Pending Jobs (includes pending array groups when grouping enabled) -->
      {#if filteredPendingJobs.length > 0 || ($preferences.groupArrayJobs && pendingArrayGroups.length > 0)}
        <div class="job-section">
          <h4 class="section-title">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z" />
            </svg>
            Pending ({filteredPendingJobs.length}{#if $preferences.groupArrayJobs && pendingArrayGroups.length > 0} + {pendingArrayGroups.length} ARRAYS{/if}{#if searchQuery && $pendingJobs.length !== filteredPendingJobs.length} <span class="search-count">of {$pendingJobs.length}</span>{/if})
          </h4>
          <div class="job-list">
            <!-- Pending array groups first -->
            {#if $preferences.groupArrayJobs}
              {#each pendingArrayGroups as group (group.array_job_id + group.hostname)}
                <div class="array-job-wrapper">
                  <ArrayJobCard {group} />
                </div>
              {/each}
            {/if}

            <!-- Then individual pending jobs -->
            {#each filteredPendingJobs as job (job.job_id + job.hostname)}
              <button
                class="job-item"
                class:selected={currentJobId === job.job_id && currentHost === job.hostname}
                onclick={() => selectJob(job)}
              >
                <div class="job-status" style="background-color: {job.state ? jobUtils.getStateColor(job.state) : '#9ca3af'}"></div>
                <div class="job-info">
                  <div class="job-header">
                    <div class="job-id-wrapper">
                      <span class="job-id">{job.job_id}</span>
                      {#if hasWatchers(job.job_id)}
                        <span class="watcher-indicator" title="{getWatcherCount(job.job_id)} watcher(s) active">
                          <Eye size={12} />
                          <span class="watcher-count">{formatWatcherCount(getWatcherCount(job.job_id))}</span>
                        </span>
                      {/if}
                    </div>
                  </div>
                  <div class="job-content">
                    <span class="job-name">{formatJobName(job.name)}</span>
                    <span class="job-state-label state-pending">
                      <svg viewBox="0 0 24 24" fill="currentColor" class="state-icon">
                        <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z" />
                      </svg>
                      Pending
                    </span>
                  </div>
                  <div class="job-meta">
                    <span class="job-host">{job.hostname.toUpperCase()}</span>
                    {#if job.reason}
                      <span class="job-reason-badge">{job.reason}</span>
                    {/if}
                  </div>
                </div>
              </button>
            {/each}
          </div>
        </div>
      {/if}
      
      <!-- Completed Array Jobs (collapsible section) -->
      {#if $preferences.groupArrayJobs && completedArrayGroups.length > 0}
        <div class="job-section">
          <CollapsibleSection
            title="Completed Array Jobs"
            badge={completedArrayGroups.length}
            defaultExpanded={false}
            storageKey="sidebar-completed-arrays-expanded"
          >
            <div class="job-list">
              {#each completedArrayGroups as group (group.array_job_id + group.hostname)}
                <div class="array-job-wrapper">
                  <ArrayJobCard {group} />
                </div>
              {/each}
            </div>
          </CollapsibleSection>
        </div>
      {/if}

      <!-- Recent Jobs (individual jobs only, no arrays) -->
      {#if filteredRecentJobs.length > 0}
        <div class="job-section">
          <h4 class="section-title">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M13.5,8H12V13L16.28,15.54L17,14.33L13.5,12.25V8M13,3A9,9 0 0,0 4,12H1L4.96,16.03L9,12H6A7,7 0 0,1 13,5A7,7 0 0,1 20,12A7,7 0 0,1 13,19C11.07,19 9.32,18.21 8.06,16.94L6.64,18.36C8.27,20 10.5,21 13,21A9,9 0 0,0 22,12A9,9 0 0,0 13,3" />
            </svg>
            Recent ({filteredRecentJobs.length}{#if searchQuery && recentJobs.length !== filteredRecentJobs.length} <span class="search-count">of {recentJobs.length}</span>{/if})
          </h4>
          <div class="job-list">
            {#each filteredRecentJobs as job (job.job_id + job.hostname)}
              <button
                class="job-item"
                class:selected={currentJobId === job.job_id && currentHost === job.hostname}
                onclick={() => selectJob(job)}
              >
                <div class="job-status" style="background-color: {job.state ? jobUtils.getStateColor(job.state) : '#9ca3af'}"></div>
                <div class="job-info">
                  <div class="job-header">
                    <div class="job-id-wrapper">
                      <span class="job-id">{job.job_id}</span>
                      {#if hasWatchers(job.job_id)}
                        <span class="watcher-indicator" title="{getWatcherCount(job.job_id)} watcher(s) active">
                          <Eye size={12} />
                          <span class="watcher-count">{formatWatcherCount(getWatcherCount(job.job_id))}</span>
                        </span>
                      {/if}
                    </div>
                    {#if job.runtime}
                      <span class="job-runtime-badge">{formatRuntime(job.runtime)}</span>
                    {/if}
                  </div>
                  <div class="job-content">
                    <span class="job-name">{formatJobName(job.name)}</span>
                    <span class="job-state-label state-{job.state ? job.state.toLowerCase() : 'unknown'}">{job.state ? jobUtils.getStateLabel(job.state) : 'Unknown'}</span>
                  </div>
                  <div class="job-meta">
                    <span class="job-host">{job.hostname.toUpperCase()}</span>
                  </div>
                </div>
              </button>
            {/each}
          </div>
        </div>
      {/if}

      <!-- No search results state -->
      {#if searchQuery && !hasSearchResults && $allJobs.length > 0}
        <div class="no-search-results">
          <svg viewBox="0 0 24 24" fill="currentColor" class="no-results-icon">
            <path d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z"/>
          </svg>
          <p style="margin-bottom: 0.5rem; color: var(--muted-foreground);">No results for "{searchQuery}"</p>
          <button class="clear-search-btn" onclick={clearSearch}>
            Clear search
          </button>
        </div>
      {/if}

      {#if $allJobs.length === 0}
        <div class="empty-state">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M19,8L15,12H18A6,6 0 0,1 12,18C11,18 10.03,17.75 9.2,17.3L7.74,18.76C8.97,19.54 10.43,20 12,20A8,8 0 0,0 20,12H23M6,12A6,6 0 0,1 12,6C13,6 13.97,6.25 14.8,6.7L16.26,5.24C15.03,4.46 13.57,4 12,4A8,8 0 0,0 4,12H1L5,16L9,12" />
          </svg>
          <p>No jobs found</p>
        </div>
      {/if}
    {/if}
  </div>
  {/if}
</div>

<style>
  .job-sidebar {
    width: 320px;
    height: 100%;
    max-height: 100vh;
    background: var(--secondary);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    position: relative;
    transition: width 0.3s ease;
    overflow: hidden;
    flex-shrink: 0; /* Prevent sidebar from shrinking */
    /* Optimize composite layer creation */
    contain: layout style paint;
    transform: translateZ(0);
  }
  
  .job-sidebar.collapsed {
    width: 48px;
  }
  
  .job-sidebar.mobile {
    width: 85vw; /* 85% of viewport width */
    max-width: 400px; /* Maximum width on larger mobile devices */
    height: 100%;
    border-right: none;
    /* On mobile overlay, add shadow for depth */
    box-shadow: 2px 0 8px rgba(0, 0, 0, 0.15);
    box-sizing: border-box; /* Include padding/border in width calculation */
  }

  .job-sidebar.mobile.closing {
    animation: slideOutToLeft 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
  }

  @keyframes slideInFromLeft {
    0% {
      transform: translateX(-100%);
      opacity: 0;
    }
    60% {
      opacity: 1;
    }
    100% {
      transform: translateX(0);
      opacity: 1;
    }
  }

  @keyframes slideOutToLeft {
    0% {
      transform: translateX(0);
      opacity: 1;
    }
    40% {
      opacity: 1;
    }
    100% {
      transform: translateX(-100%);
      opacity: 0;
    }
  }

  .job-sidebar.mobile.collapsed {
    width: 100%;
  }

  .sidebar-header {
    height: 64px; /* Match NavigationHeader height */
    padding: 0 1rem;
    display: flex;
    justify-content: flex-end;
    align-items: center;
    flex-shrink: 0;
  }

  .job-sidebar.mobile .sidebar-header {
    /* Ensure header is always visible on mobile */
    display: flex;
    padding: 0.75rem; /* Smaller padding on mobile */
  }

  .job-sidebar.mobile .sidebar-header h3 {
    font-size: 0.9rem; /* Smaller title on mobile */
  }
  
  .sidebar-header h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--foreground);
  }
  
  .header-actions {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  
  .refresh-btn {
    width: 28px;
    height: 28px;
    padding: 0;
    background: transparent;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.25rem;
    transition: background 0.2s;
  }
  
  .refresh-btn:hover:not(:disabled) {
    background: var(--secondary);
  }
  
  .refresh-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .close-btn {
    width: 28px;
    height: 28px;
    padding: 0;
    background: transparent;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.25rem;
    transition: all 0.15s;
  }

  .close-btn:hover {
    background: var(--secondary);
  }

  .close-btn svg {
    width: 18px;
    height: 18px;
    color: var(--muted-foreground);
  }

  /* Hamburger to X animation - synchronized with sidebar slide */
  .hamburger-line {
    transition: all 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    transform-origin: center;
  }

  /* Initial hamburger state */
  .hamburger-line.top {
    transform: translateY(0) rotate(0);
  }

  .hamburger-line.middle {
    opacity: 1;
    transform: scaleX(1);
  }

  .hamburger-line.bottom {
    transform: translateY(0) rotate(0);
  }

  /* Transform to X with proper positioning */
  .hamburger-to-x .hamburger-line.top {
    transform: rotate(45deg) translateY(6px);
  }

  .hamburger-to-x .hamburger-line.middle {
    opacity: 0;
    transform: scaleX(0);
  }

  .hamburger-to-x .hamburger-line.bottom {
    transform: rotate(-45deg) translateY(-6px);
  }

  /* When closing, ensure smooth transition back */
  .job-sidebar.closing .hamburger-line {
    transition: all 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94);
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  
  .sidebar-content {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 0.5rem;
    /* Optimize scrolling performance */
    -webkit-overflow-scrolling: touch;
    scroll-behavior: smooth;
    will-change: scroll-position;
    transform: translateZ(0);
    /* Hide scrollbar while maintaining scroll functionality */
    scrollbar-width: none; /* Firefox */
    -ms-overflow-style: none; /* IE and Edge */
  }

  /* Hide scrollbar for WebKit browsers (Chrome, Safari, Edge) */
  .sidebar-content::-webkit-scrollbar {
    display: none;
    width: 0;
    height: 0;
  }

  /* Additional scrollbar hiding for all states */
  .sidebar-content::-webkit-scrollbar-track {
    display: none;
  }

  .sidebar-content::-webkit-scrollbar-thumb {
    display: none;
  }

  .job-sidebar.mobile .sidebar-content {
    /* Ensure content is always visible on mobile */
    display: flex;
    flex-direction: column;
    padding: 0.375rem; /* Much smaller padding on mobile */
    max-width: 100%; /* Prevent content from expanding beyond sidebar */
    overflow-x: hidden; /* Hide horizontal overflow */
    box-sizing: border-box;
  }
  
  .loading-state,
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    color: var(--muted-foreground);
  }
  
  
  .empty-state svg {
    width: 2rem;
    height: 2rem;
    margin-bottom: 0.5rem;
    opacity: 0.5;
  }
  
  .empty-state p {
    margin: 0;
    font-size: 0.875rem;
  }
  
  .job-section {
    margin-bottom: 1rem;
  }
  
  .section-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0 0 0.75rem 0;
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--muted-foreground);
    letter-spacing: 0.05em;
  }
  
  .section-title svg {
    width: 14px;
    height: 14px;
    opacity: 0.6;
  }
  
  .job-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  /* Array job wrapper - subtle distinction in sidebar context */
  .array-job-wrapper {
    margin-left: -4px;
    padding-left: 4px;
    border-left: 2px solid var(--border);
  }

  .job-item {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    width: 100%;
    max-width: 100%; /* Prevent expansion beyond parent */
    padding: 1rem;
    background: rgb(243 244 246); /* gray-100 for light mode */
    border: 1px solid var(--border);
    border-radius: 0.875rem;
    cursor: pointer;
    text-align: left;
    transition: all 0.25s ease;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.08), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
    position: relative;
    overflow: hidden;
    box-sizing: border-box; /* Include padding/border in width */
    /* Optimize rendering performance */
    backface-visibility: hidden;
    transform: translateZ(0);
    will-change: transform, box-shadow;
  }

  /* Dark mode override with high specificity to beat global.css */
  :global(.dark) .job-item {
    background: #262626 !important; /* gray-100 dark - lighter than sidebar #1a1a1a */
  }

  /* Mobile job items - much more compact */
  .job-sidebar.mobile .job-item {
    padding: 0.5rem; /* Much smaller padding */
    gap: 0.5rem; /* Smaller gap */
    border-radius: 0.5rem; /* Less rounded */
    font-size: 0.875rem; /* Smaller text */
  }

  .job-item:hover {
    background: rgb(229 231 235); /* gray-200 for light mode */
    border-color: var(--muted);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    transform: translateY(-1px);
  }

  :global(.dark) .job-item:hover {
    background: #333333 !important; /* gray-200 dark - lighter on hover */
  }

  .job-item.selected {
    background: var(--accent);
    background: rgba(59, 130, 246, 0.15);
    border-color: var(--accent);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2), 0 4px 6px -1px rgba(59, 130, 246, 0.1);
  }
  
  .job-status {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 6px;
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.8);
  }
  
  .job-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .job-name {
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--foreground);
    line-height: 1.2;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .job-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-top: 0.25rem;
  }

  .job-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.25rem;
    gap: 0.5rem;
    min-width: 0; /* Allow flex items to shrink */
    max-width: 100%;
  }

  .job-id-wrapper {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    min-width: 0;
    flex: 1;
  }

  .watcher-indicator {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.15rem;
    color: #6366f1;
    opacity: 0.7;
    transition: opacity 0.2s ease;
    margin-left: 0.25rem;
  }

  .watcher-indicator:hover {
    opacity: 1;
  }

  .watcher-count {
    font-size: 0.65rem;
    font-weight: 600;
    line-height: 1;
  }

  .job-content {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.25rem;
    gap: 0.5rem;
    min-width: 0; /* Allow flex items to shrink */
    max-width: 100%;
  }

  .job-id {
    font-size: 1rem;
    font-weight: 700;
    color: var(--foreground);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }

  .job-runtime {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--muted-foreground);
  }

  .job-reason {
    font-size: 0.75rem;
    color: var(--muted-foreground);
  }

  .job-state-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--muted-foreground);
    text-transform: uppercase;
  }

  .job-host {
    font-size: 0.65rem;
    color: var(--foreground);
    font-weight: 600;
    letter-spacing: 0.05em;
    background: var(--secondary);
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    border: 1px solid var(--border);
  }

  /* Mobile job elements - smaller and more compact */
  .job-sidebar.mobile .job-id {
    font-size: 0.875rem; /* Smaller job ID text */
    font-weight: 600;
  }

  .job-sidebar.mobile .job-runtime {
    font-size: 0.75rem; /* Smaller runtime text */
  }

  .job-sidebar.mobile .job-reason {
    font-size: 0.625rem; /* Even smaller reason text */
  }

  .job-sidebar.mobile .job-state-label {
    font-size: 0.625rem; /* Smaller state label */
  }

  .job-sidebar.mobile .job-host {
    font-size: 0.5rem; /* Much smaller host label */
    padding: 0.0625rem 0.25rem; /* Tighter padding */
  }

  /* Enhanced job state labels */
  .job-state-label {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.6rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 0.125rem 0.375rem;
    border-radius: 0.375rem;
    background: var(--secondary);
    color: var(--muted-foreground);
  }

  .state-icon {
    width: 10px;
    height: 10px;
  }

  .state-running {
    background: rgba(16, 185, 129, 0.2);
    color: #10b981;
    border: 1px solid rgba(16, 185, 129, 0.3);
  }

  .state-pending {
    background: rgba(245, 158, 11, 0.2);
    color: #f59e0b;
    border: 1px solid rgba(245, 158, 11, 0.3);
  }

  .state-cd {
    background: rgba(139, 92, 246, 0.2);
    color: #a78bfa;
    border: 1px solid rgba(139, 92, 246, 0.3);
  }

  .state-f {
    background: rgba(239, 68, 68, 0.2);
    color: #ef4444;
    border: 1px solid rgba(239, 68, 68, 0.3);
  }

  .state-ca {
    background: var(--secondary);
    color: var(--foreground);
    border: 1px solid var(--border);
  }

  .state-to {
    background: rgba(249, 115, 22, 0.2);
    color: #fb923c;
    border: 1px solid rgba(249, 115, 22, 0.3);
  }

  /* Runtime and reason badges */
  .job-runtime-badge {
    display: inline-flex;
    align-items: center;
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--foreground);
    background: var(--secondary);
    padding: 0.125rem 0.5rem;
    border-radius: 0.375rem;
    border: 1px solid var(--border);
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  }

  .runtime-active {
    background: rgba(16, 185, 129, 0.25);
    color: #10b981;
    border-color: rgba(16, 185, 129, 0.5);
    animation: pulse-runtime 2s ease-in-out infinite;
  }

  @keyframes pulse-runtime {
    0%, 100% {
      opacity: 1;
      transform: translateZ(0);
    }
    50% {
      opacity: 0.8;
      transform: translateZ(0);
    }
  }

  .job-reason-badge {
    display: inline-flex;
    align-items: center;
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--foreground);
    background: var(--secondary);
    padding: 0.125rem 0.375rem;
    border-radius: 0.375rem;
    border: 1px solid var(--border);
    max-width: 80px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Search functionality styles */
  .icon-btn {
    width: 28px;
    height: 28px;
    padding: 0;
    background: transparent;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.25rem;
    transition: all 0.2s;
    color: var(--muted-foreground);
  }

  .icon-btn:hover:not(:disabled) {
    background: var(--secondary);
    color: var(--foreground);
  }

  .icon-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .icon-btn svg {
    width: 16px;
    height: 16px;
  }

  .search-toggle {
    position: relative;
  }

  .search-toggle.active {
    background: #3b82f6;
    color: white;
  }

  .search-toggle.active:hover {
    background: #2563eb;
  }

  /* Animated search container */
  .search-container {
    overflow: hidden;
    padding: 0.5rem 0.75rem;
    margin-bottom: 0.5rem;
  }

  .search-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    background: var(--secondary);
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    transition: all 0.2s;
  }

  .search-container.focused .search-wrapper {
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .search-icon {
    position: absolute;
    left: 0.75rem;
    width: 16px;
    height: 16px;
    color: var(--muted-foreground);
    pointer-events: none;
  }

  .sidebar-search-input {
    flex: 1;
    padding: 0.5rem 2rem 0.5rem 2.5rem;
    background: transparent;
    border: none;
    outline: none;
    font-size: 0.875rem;
    color: var(--foreground);
  }

  .sidebar-search-input::placeholder {
    color: var(--muted-foreground);
  }

  .clear-btn {
    position: absolute;
    right: 0.5rem;
    width: 24px;
    height: 24px;
    padding: 0;
    background: transparent;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.25rem;
    color: var(--muted-foreground);
    transition: all 0.2s;
  }

  .clear-btn:hover {
    background: var(--secondary);
    color: var(--foreground);
  }

  .clear-btn svg {
    width: 14px;
    height: 14px;
  }

  /* No search results state */
  .no-search-results {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem 1rem;
    text-align: center;
  }

  .no-results-icon {
    width: 48px;
    height: 48px;
    color: var(--muted-foreground);
    opacity: 0.5;
    margin-bottom: 1rem;
  }

  .clear-search-btn {
    padding: 0.375rem 0.75rem;
    background: var(--secondary);
    border: 1px solid var(--border);
    border-radius: 0.375rem;
    font-size: 0.75rem;
    color: var(--foreground);
    cursor: pointer;
    transition: all 0.2s;
  }

  .clear-search-btn:hover {
    background: var(--secondary);
    border-color: #3b82f6;
  }

  /* Search count in section headers */
  .search-count {
    font-size: 0.75rem;
    color: var(--muted-foreground);
    font-weight: 400;
  }

  /* Mobile adjustments */
  .job-sidebar.mobile .search-container {
    padding: 0 0.5rem;
  }

  .job-sidebar.mobile .sidebar-search-input {
    font-size: 0.875rem;
  }
</style>