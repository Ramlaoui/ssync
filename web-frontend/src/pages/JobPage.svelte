<script lang="ts">
  import { run, createBubbler, stopPropagation } from 'svelte/legacy';

  const bubble = createBubbler();
  import { onMount, onDestroy } from "svelte";
  import { push } from "svelte-spa-router";
  import type { AxiosError } from "axios";
  import { api, apiConfig } from "../services/api";
  import type { JobInfo, OutputData, ScriptData } from "../types/api";
  import { jobStateManager } from "../lib/JobStateManager";
  import type { Readable } from "svelte/store";
  import JobSidebar from "../components/JobSidebar.svelte";
  import JobHeader from "../components/JobHeader.svelte";
  import JobDetailsView from "../components/JobDetailsView.svelte";
  import JobTabContent from "../components/JobTabContent.svelte";
  import WatcherAttachmentDialog from "../components/WatcherAttachmentDialog.svelte";
  import LoadingSpinner from "../components/LoadingSpinner.svelte";
  import { Info, Terminal, AlertTriangle, Code, ArrowLeft, Eye } from 'lucide-svelte';
  import { navigationState, navigationActions } from '../stores/navigation';

  interface Props {
    params?: any;
    showSidebarOnly?: boolean;
  }

  let { params = {}, showSidebarOnly = false }: Props = $props();

  let job: JobInfo | null = $state(null);
  let jobStore: Readable<JobInfo | null> | null = $state(null);
  let loading = $state(false);
  let initialLoadComplete = $state(false);
  let error: string | null = $state(null);
  let activeTab = $state('details');
  let sidebarCollapsed = $state(false);
  let isMobile = $state(false);
  let showMobileSidebar = $state(false);
  let showAttachWatchersDialog = $state(false);
  let isClosingSidebar = $state(false);

  // Output related state
  let outputData: OutputData | null = $state(null);
  let outputError: string | null = $state(null);
  let loadingOutput = $state(false);
  let loadingMoreOutput = false;
  let refreshingOutput = $state(false);

  // Script related state
  let scriptData: ScriptData | null = $state(null);
  let scriptError: string | null = $state(null);
  let loadingScript = $state(false);

  // Check mobile
  function checkMobile() {
    isMobile = window.innerWidth < 768;
  }

  // Handle mobile sidebar closure without navigation
  function handleMobileSidebarClose() {
    isClosingSidebar = true;
    setTimeout(() => {
      showMobileSidebar = false;
      isClosingSidebar = false;
    }, 300);
  }

  // Handle mobile job selection - called after JobSidebar navigates
  function handleMobileJobSelect() {
    // JobSidebar has already handled navigation, close sidebar immediately
    // The navigation will happen independently
    showMobileSidebar = false;
    isClosingSidebar = false;
  }

  // Load job data using JobStateManager
  async function loadJob(forceRefresh = false) {
    if (!params.id || !params.host) {
      error = "Invalid job parameters";
      return;
    }

    // For initial load or force refresh, show loading state
    if (!initialLoadComplete || forceRefresh) {
      loading = true;
    }
    error = null;

    try {
      // Fetch the job data (will update the store automatically)
      const jobData = await jobStateManager.fetchSingleJob(params.id, params.host, forceRefresh);

      if (!jobData) {
        error = "Job not found";
      }

      initialLoadComplete = true;
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      if (axiosError.response?.status === 404) {
        error = "Job not found";
      } else {
        error = `Failed to load job: ${axiosError.message}`;
      }
    } finally {
      loading = false;
    }
  }

  // Load output data
  async function loadOutput() {
    if (!job) return;

    loadingOutput = true;
    outputError = null;

    try {
      const response = await api.get<OutputData>(`/api/jobs/${params.id}/output?host=${params.host}`);
      outputData = response.data;
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      outputError = `Failed to load output: ${axiosError.message}`;
    } finally {
      loadingOutput = false;
    }
  }

  // Refresh output data
  async function refreshOutput() {
    if (!job) return;

    refreshingOutput = true;
    outputError = null;

    try {
      const response = await api.get<OutputData>(`/api/jobs/${params.id}/output?host=${params.host}&force=true`);
      outputData = response.data;
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      outputError = `Failed to refresh output: ${axiosError.message}`;
    } finally {
      refreshingOutput = false;
    }
  }

  // Load script data
  async function loadScript() {
    if (!job) return;

    loadingScript = true;
    scriptError = null;

    try {
      const response = await api.get<ScriptData>(`/api/jobs/${params.id}/script?host=${params.host}`);
      scriptData = response.data;
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      scriptError = `Failed to load script: ${axiosError.message}`;
    } finally {
      loadingScript = false;
    }
  }

  // Event handlers
  function handleShareJob() {
    const url = `${window.location.origin}/jobs/${params.id}/${params.host}`;
    navigator.clipboard.writeText(url);
  }

  async function handleCancelJob() {
    if (!job || !confirm('Are you sure you want to cancel this job?')) return;

    try {
      await api.post(`/api/jobs/${params.id}/cancel?host=${params.host}`);
      // Force refresh through JobStateManager
      await loadJob(true);
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      error = `Failed to cancel job: ${axiosError.message}`;
    }
  }

  function handleAttachWatchers() {
    showAttachWatchersDialog = true;
  }

  // Tab management
  function handleTabClick(tab: string) {
    activeTab = tab;
  }

  function handleBackNavigation() {
    // Use smart navigation based on where we came from
    navigationActions.goBack();
  }

  // Track previous params to avoid recreating store on every reactive run
  let prevParamsId: string | undefined = $state();
  let prevParamsHost: string | undefined = $state();

  // Reactive block 1: Set up job store when params change (not on every run)
  run(() => {
    if (params.id && params.host && !showSidebarOnly) {
      // Only set up store if params actually changed
      if (params.id !== prevParamsId || params.host !== prevParamsHost) {
        console.log(`[JobPage] Params changed from ${prevParamsHost}:${prevParamsId} to ${params.host}:${params.id}`);

        // Clear previous data when switching jobs
        outputData = null;
        scriptData = null;
        outputError = null;
        scriptError = null;
        error = null;
        activeTab = 'details';
        initialLoadComplete = false;

        // Update tracked params
        prevParamsId = params.id;
        prevParamsHost = params.host;

        // Get reactive store for this job (only when params change)
        jobStore = jobStateManager.getJob(params.id, params.host);

        // Set current view for priority updates
        jobStateManager.setCurrentViewJob(params.id, params.host);

        // Load the job data
        loadJob();
      }
    }
  });

  // Reactive block 2: Subscribe to job updates from the store
  run(() => {
    if (jobStore) {
      job = $jobStore;
    }
  });

  // Reactive block 3: Load output data when tab changes
  run(() => {
    if (job && activeTab === 'output' && !outputData) {
      loadOutput();
    }
  });

  // Reactive block 4: Load script data when tab changes
  run(() => {
    if (job && activeTab === 'script' && !scriptData) {
      loadScript();
    }
  });

  onMount(async () => {
    // Job loading is now handled by reactive statement above
    checkMobile();
    window.addEventListener("resize", checkMobile);

    // Set navigation context for job page
    if (params.id && params.host) {
      navigationActions.setContext('job', {
        jobId: params.id,
        hostname: params.host
      });
      // Note: setCurrentViewJob is now called in the reactive block to avoid duplication
    }
  });

  onDestroy(() => {
    window.removeEventListener("resize", checkMobile);

    // Clear current view job
    jobStateManager.setCurrentViewJob(null, null);
  });
</script>

<div class="job-page">
  <!-- Desktop-only navigation header -->
  {#if !showSidebarOnly && !isMobile}
    <header class="desktop-header sticky top-0 z-40" style="background: var(--card); border-bottom: 1px solid var(--border);">
      <div class="px-6">
        <div class="flex h-16 items-center justify-between">
          <!-- Left side - Back button -->
          <button
            class="desktop-back-button flex items-center gap-2 px-3 py-2 rounded-lg font-medium transition-colors"
            onclick={handleBackNavigation}
          >
            <ArrowLeft class="w-4 h-4" />
            Back
          </button>

          <!-- Right side - Job info (if available) -->
          {#if job}
            <div class="flex items-center gap-3">
              <span class="text-sm desktop-job-info">Job {job.job_id}</span>
              {#if job.hostname}
                <span class="text-sm desktop-job-info-secondary">on {job.hostname}</span>
              {/if}
            </div>
          {/if}
        </div>
      </div>
    </header>
  {/if}
  {#if showSidebarOnly}
    <!-- Jobs Page with Sidebar Only -->
    <div class="page-layout">
      {#if !isMobile}
        <JobSidebar
          currentJobId=""
          currentHost=""
          bind:collapsed={sidebarCollapsed}
          {isMobile}
        />
      {/if}

      <div class="flex flex-col flex-1 min-h-0 h-full overflow-hidden">
        <JobHeader
          {job}
          {isMobile}
          {showSidebarOnly}
          onToggleSidebar={() => showMobileSidebar = true}
        />

        <!-- Empty State Content -->
        <div class="flex-1 flex items-center justify-center" style="background: var(--secondary);">
          <div class="text-center">
            <svg class="mx-auto h-12 w-12" style="color: var(--muted-foreground);" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <h3 class="mt-2 text-sm font-medium" style="color: var(--foreground);">No job selected</h3>
            <p class="mt-1 text-sm" style="color: var(--muted-foreground);">Choose a job from the sidebar to view its details</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Mobile Sidebar for Jobs Page -->
    {#if isMobile && showMobileSidebar}
      <div class="fixed inset-0 bg-black/50 z-50 flex backdrop-blur-sm {isClosingSidebar ? 'animate-out fade-out duration-300' : 'animate-in fade-in duration-300'}" role="dialog" tabindex="-1" onclick={handleMobileSidebarClose} onkeydown={() => {}}>
        <div role="dialog" tabindex="0" onclick={stopPropagation(bubble('click'))} onkeydown={() => {}}>
          <JobSidebar
            currentJobId=""
            currentHost=""
            collapsed={false}
            {isMobile}
            onMobileJobSelect={handleMobileJobSelect}
            onClose={handleMobileSidebarClose}
          />
        </div>
      </div>
    {/if}

  {:else}
    <!-- Regular Job Detail Page -->
    {#if isMobile && showMobileSidebar}
      <div class="fixed inset-0 bg-black/50 z-50 flex backdrop-blur-sm {isClosingSidebar ? 'animate-out fade-out duration-300' : 'animate-in fade-in duration-300'}" role="dialog" tabindex="-1" onclick={handleMobileSidebarClose} onkeydown={() => {}}>
        <div role="dialog" tabindex="0" onclick={stopPropagation(bubble('click'))} onkeydown={() => {}}>
          <JobSidebar
            currentJobId={params.id || ''}
            currentHost={params.host || ''}
            collapsed={false}
            {isMobile}
            onMobileJobSelect={handleMobileJobSelect}
            onClose={handleMobileSidebarClose}
          />
        </div>
      </div>
    {:else}
      <div class="page-layout" class:sidebar-collapsed={sidebarCollapsed}>
        {#if !isMobile}
          <JobSidebar
            currentJobId={params.id || ''}
            currentHost={params.host || ''}
            bind:collapsed={sidebarCollapsed}
            {isMobile}
          />
        {/if}

        <div class="flex flex-col flex-1 min-h-0 {isMobile ? 'h-full overflow-hidden' : 'h-full overflow-hidden'}">
          <JobHeader
            {job}
            {isMobile}
            {showSidebarOnly}
            refreshing={loading}
            onToggleSidebar={() => showMobileSidebar = !showMobileSidebar}
            onShareJob={handleShareJob}
            onCancelJob={handleCancelJob}
            onAttachWatchers={handleAttachWatchers}
            onRefreshJob={() => loadJob(true)}
          />

          {#if error}
            <div class="bg-red-50 border-b border-red-200 p-3">
              <p class="text-sm font-medium text-red-800">{error}</p>
            </div>
          {/if}

          {#if loading}
            <LoadingSpinner message="Loading job..." />
          {:else if job}
            <!-- Tab Navigation -->
            <div class="tab-navigation">
              <nav class="tab-nav-container">
                <button
                  class="tab-button {activeTab === 'details' ? 'tab-button-active' : ''}"
                  onclick={() => handleTabClick('details')}
                >
                  <Info class="w-4 h-4" />
                  <span class="tab-label">Details</span>
                </button>
                <button
                  class="tab-button {activeTab === 'output' ? 'tab-button-active' : ''}"
                  onclick={() => handleTabClick('output')}
                >
                  <Terminal class="w-4 h-4" />
                  <span class="tab-label">Output</span>
                </button>
                <button
                  class="tab-button {activeTab === 'errors' ? 'tab-button-active' : ''}"
                  onclick={() => handleTabClick('errors')}
                >
                  <AlertTriangle class="w-4 h-4" />
                  <span class="tab-label">Errors</span>
                </button>
                <button
                  class="tab-button {activeTab === 'script' ? 'tab-button-active' : ''}"
                  onclick={() => handleTabClick('script')}
                >
                  <Code class="w-4 h-4" />
                  <span class="tab-label">Script</span>
                </button>
                <button
                  class="tab-button {activeTab === 'watchers' ? 'tab-button-active' : ''}"
                  onclick={() => handleTabClick('watchers')}
                >
                  <Eye class="w-4 h-4" />
                  <span class="tab-label">Watchers</span>
                </button>
              </nav>
            </div>

            <!-- Tab Content -->
            <div class="flex-1 overflow-hidden {isMobile ? 'min-h-0' : ''}">
              {#if activeTab === 'details'}
                <div class="overflow-y-auto h-full">
                  <JobDetailsView {job} />
                </div>
              {:else}
                <div class="h-full flex flex-col">
                  <JobTabContent
                  {job}
                  {activeTab}
                  {outputData}
                  {outputError}
                  {loadingOutput}
                  {loadingMoreOutput}
                  {scriptData}
                  {scriptError}
                  {loadingScript}
                  onRetryLoadOutput={loadOutput}
                  onLoadMoreOutput={() => {}}
                  onScrollToTop={() => {}}
                  onScrollToBottom={() => {}}
                  onRetryLoadScript={loadScript}
                  onDownloadScript={() => {}}
                  onRefreshOutput={refreshOutput}
                  {refreshingOutput}
                  />
                </div>
              {/if}
            </div>
          {/if}
        </div>
      </div>
    {/if}
  {/if}
</div>

{#if showAttachWatchersDialog && job}
  <WatcherAttachmentDialog
    jobId={job.job_id}
    hostname={params.host}
    on:close={() => showAttachWatchersDialog = false}
    on:success={() => {
      showAttachWatchersDialog = false;
      loadJob(true);
    }}
  />
{/if}

<style>
  .job-page {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    background: var(--background);
    overflow: hidden;
  }

  /* Remove fixed positioning on mobile to allow natural scrolling */
  @media (max-width: 768px) {
    .job-page {
      position: relative;
      min-height: 100vh;
      overflow-y: visible;
    }
  }

  .page-layout {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  /* Allow scrolling on mobile */
  @media (max-width: 768px) {
    .page-layout {
      overflow-y: auto;
      overflow-x: hidden;
      height: calc(100vh - var(--mobile-nav-height, 56px));
      position: relative;
    }
  }

  .page-layout.sidebar-collapsed {
    /* Styles for collapsed sidebar state */
  }

  /* Tab navigation container */
  .tab-navigation {
    border-bottom: 1px solid var(--border);
    background: var(--card);
    padding: 0 1.5rem;
    overflow-x: auto;
    overflow-y: hidden;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none; /* Firefox */
  }

  .tab-navigation::-webkit-scrollbar {
    display: none; /* Chrome/Safari */
  }

  /* On mobile, reduce padding */
  @media (max-width: 768px) {
    .tab-navigation {
      padding: 0 0.75rem;
    }
  }

  .tab-nav-container {
    display: flex;
    gap: 0;
    min-width: max-content; /* Prevent wrapping, allow horizontal scroll */
  }

  .tab-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 1rem 1rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: rgb(107 114 128 / 1); /* text-gray-500 */
    border-bottom: 2px solid transparent;
    transition: all 0.2s;
    background: none;
    border-left: none;
    border-right: none;
    border-top: none;
    cursor: pointer;
    white-space: nowrap;
    flex-shrink: 0; /* Prevent buttons from shrinking */
  }

  /* Dark mode colors */
  :global(.dark) .tab-button {
    color: var(--muted-foreground);
  }

  .tab-button:hover {
    color: rgb(55 65 81 / 1); /* text-gray-700 */
  }

  :global(.dark) .tab-button:hover {
    color: var(--foreground);
  }

  .tab-button-active {
    color: rgb(31 41 55 / 1); /* text-gray-900 */
    border-bottom-color: #3b82f6;
  }

  :global(.dark) .tab-button-active {
    color: var(--foreground);
    border-bottom-color: var(--accent);
  }

  /* On mobile, make tabs more compact */
  @media (max-width: 768px) {
    .tab-button {
      padding: 0.75rem 0.75rem;
      font-size: 0.8125rem; /* Slightly smaller text */
      gap: 0.375rem; /* Tighter spacing */
    }

    /* Hide labels on very small screens, show only icons */
    @media (max-width: 480px) {
      .tab-label {
        display: none;
      }

      .tab-button {
        padding: 0.75rem 1rem;
        justify-content: center;
      }
    }
  }

  /* Desktop header button styles */
  .desktop-back-button {
    color: var(--muted-foreground);
    background: transparent;
  }

  .desktop-back-button:hover {
    color: var(--foreground);
    background: var(--secondary);
  }

  .desktop-job-info {
    color: var(--muted-foreground);
  }

  .desktop-job-info-secondary {
    color: var(--muted-foreground);
    opacity: 0.7;
  }

</style>