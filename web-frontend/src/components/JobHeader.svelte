<script lang="ts">
  import { push } from "svelte-spa-router";
  import type { JobInfo } from "../types/api";
  import Button from "../lib/components/ui/Button.svelte";
  import { ArrowLeft, Menu, Play, Square, Trash2, Plus, MoreHorizontal, RefreshCw, RotateCcw, Download, FileText } from 'lucide-svelte';
  import { resubmitStore } from '../stores/resubmit.ts';
  import { api } from '../services/api';

  interface Props {
    job?: JobInfo | null;
    isMobile?: boolean;
    showSidebarOnly?: boolean;
    onToggleSidebar?: () => void;
    onShareJob?: () => void;
    onCancelJob?: () => void;
    onAttachWatchers?: () => void;
    onRefreshJob?: () => void;
    refreshing?: boolean;
  }

  let {
    job = null,
    isMobile = false,
    showSidebarOnly = false,
    onToggleSidebar = () => {},
    onShareJob = () => {},
    onCancelJob = () => {},
    onAttachWatchers = () => {},
    onRefreshJob = () => {},
    refreshing = false
  }: Props = $props();

  function getJobStateColor(state: string): string {
    switch (state) {
      case 'R': return 'bg-green-100 text-green-800';
      case 'PD': return 'bg-yellow-100 text-yellow-800';
      case 'CD': return 'bg-blue-100 text-blue-800';
      case 'F': return 'bg-red-100 text-red-800';
      case 'CA': return 'bg-gray-100 text-gray-800';
      case 'TO': return 'bg-orange-100 text-orange-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  }

  function getJobStateName(state: string): string {
    switch (state) {
      case 'R': return 'Running';
      case 'PD': return 'Pending';
      case 'CD': return 'Completed';
      case 'F': return 'Failed';
      case 'CA': return 'Cancelled';
      case 'TO': return 'Timeout';
      default: return state;
    }
  }

  let showDropdown = $state(false);

  async function handleResubmitJob() {
    if (!job) return;

    try {
      // Use the api service for proper authentication
      const response = await api.get(`/api/jobs/${job.job_id}/script?host=${job.hostname}`);
      const scriptData = response.data;

      console.log('Fetched script for resubmit:', scriptData);

      // Ensure we have script content
      if (!scriptData.script_content) {
        throw new Error('No script content returned from API');
      }

      // Fetch watchers and extract captured variables
      let watcherVariables: Record<string, string> = {};
      let watcherConfigs: any[] = [];
      try {
        const watchersResponse = await api.get(`/api/jobs/${job.job_id}/watchers?host=${job.hostname}`);
        const watchersData = watchersResponse.data;

        // Store full watcher configurations
        if (watchersData.watchers && watchersData.watchers.length > 0) {
          watcherConfigs = watchersData.watchers;

          // Extract all captured variables from all watchers
          watchersData.watchers.forEach((watcher: any) => {
            if (watcher.variables) {
              Object.entries(watcher.variables).forEach(([key, value]) => {
                // If multiple watchers have the same variable, prefix with watcher name
                const varKey = watchersData.watchers.length > 1 && watcher.name
                  ? `${watcher.name}_${key}`
                  : key;
                watcherVariables[varKey] = value as string;
              });
            }
          });
        }
        console.log('Captured variables from watchers:', watcherVariables);
        console.log('Watcher configurations:', watcherConfigs);
      } catch (watcherError) {
        console.warn('Could not fetch watcher variables:', watcherError);
        // Continue without watcher variables - they're optional
      }

      // Store resubmit data with captured variables and watcher configurations
      resubmitStore.setResubmitData({
        scriptContent: scriptData.script_content,
        hostname: job.hostname,
        workDir: job.work_dir,
        localSourceDir: scriptData.local_source_dir,  // Use the local source dir from the API
        originalJobId: job.job_id,
        jobName: job.name,
        submitLine: job.submit_line,
        watcherVariables: Object.keys(watcherVariables).length > 0 ? watcherVariables : undefined,
        watchers: watcherConfigs.length > 0 ? watcherConfigs : undefined
      });

      // Navigate to job launcher
      push('/launch');
    } catch (error: any) {
      console.error('Failed to prepare resubmit:', error);
      // Show user-friendly error
      alert(`Failed to fetch job script: ${error.message || 'Unknown error'}`);
    }

    showDropdown = false;
  }

  // Close dropdown when clicking outside
  function handleClickOutside(event: Event) {
    if (showDropdown) {
      const target = event.target as HTMLElement;
      const dropdown = target.closest('.relative');
      if (!dropdown) {
        showDropdown = false;
      }
    }
  }

  async function handleDownloadOutputs() {
    if (!job) return;

    try {
      const response = await api.get(`/api/jobs/${job.job_id}/output?host=${job.hostname}`);
      const data = response.data;

      // Create a blob with the output content
      const blob = new Blob([data.stdout || ''], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);

      // Create download link
      const a = document.createElement('a');
      a.href = url;
      a.download = `job_${job.job_id}_output.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to download outputs:', error);
    }

    showDropdown = false;
  }

  async function handleDownloadScript() {
    if (!job) return;

    try {
      const response = await api.get(`/api/jobs/${job.job_id}/script?host=${job.hostname}`);
      const data = response.data;

      // Create a blob with the script content
      const blob = new Blob([data.script_content || ''], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);

      // Create download link
      const a = document.createElement('a');
      a.href = url;
      a.download = `job_${job.job_id}_script.sh`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to download script:', error);
    }

    showDropdown = false;
  }

  function handleCancelFromMenu() {
    onCancelJob();
    showDropdown = false;
  }

  function handleAttachWatchersFromMenu() {
    onAttachWatchers();
    showDropdown = false;
  }
</script>

<div
  class="header"
  onclick={handleClickOutside}
  onkeydown={(e) => { if (e.key === 'Escape' && showDropdown) showDropdown = false; }}
  role="presentation"
>
  <div class="header-left">
    {#if !isMobile}
      {#if showSidebarOnly}
        <!-- Desktop Jobs Page: Home button -->
        <button class="flex items-center gap-2 px-3 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg font-medium transition-colors" onclick={() => push('/')}>
          <ArrowLeft class="w-4 h-4" />
          Home
        </button>
      {:else}
        <!-- Desktop Job Detail Page: Jobs button -->
        <button class="flex items-center gap-2 px-3 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg font-medium transition-colors" onclick={() => push('/jobs')}>
          <ArrowLeft class="w-4 h-4" />
          Jobs
        </button>
      {/if}
    {/if}

    {#if !showSidebarOnly}
      {#if isMobile}
        <!-- Mobile hamburger menu button -->
        <button
          class="flex items-center justify-center p-1.5 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded transition-colors"
          onclick={onToggleSidebar}
          aria-label="Show job list"
        >
          <Menu class="w-4 h-4" />
        </button>
      {/if}

      {#if !isMobile}
        <div class="w-px h-6 bg-gray-300"></div>
      {/if}

      {#if job}
        <div class="flex items-center gap-2 md:gap-3 min-w-0 flex-1">
          <div class="flex flex-col justify-center min-w-0">
            <h1 class="text-sm md:text-lg font-semibold text-gray-900">
              Job {job.job_id}
            </h1>
            {#if job.name && job.name !== 'N/A'}
              <span class="text-xs text-gray-500 truncate">
                {job.name}
              </span>
            {/if}
          </div>

          {#if job.hostname}
            <span class="text-xs md:text-sm text-gray-500 hidden sm:inline">
              on {job.hostname}
            </span>
          {/if}
        </div>
      {:else}
        <h1 class="text-sm md:text-lg font-semibold text-gray-900">Loading...</h1>
      {/if}
    {:else}
      <div class="w-px h-6 bg-gray-300"></div>
      <h1 class="text-lg font-semibold text-gray-900">Jobs</h1>
    {/if}
  </div>

  {#if !showSidebarOnly && job}
    <div class="header-right">
      <!-- Job Status Badge -->
      <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium {getJobStateColor(job.state)}">
        {getJobStateName(job.state)}
      </span>

      <!-- Refresh Button -->
      <Button variant="ghost" size="sm" on:click={onRefreshJob} disabled={refreshing}>
        <RefreshCw class="w-4 h-4 {refreshing ? 'animate-spin' : ''}" />
        {#if !isMobile}<span class="ml-1">Refresh</span>{/if}
      </Button>

      {#if !isMobile}
        <Button variant="outline" size="sm" on:click={onAttachWatchers}>
          <Plus class="w-4 h-4" />
          Watchers
        </Button>
      {/if}

      <!-- Three-dots menu -->
      <div class="relative">
        <Button variant="ghost" size="sm" on:click={() => showDropdown = !showDropdown}>
          <MoreHorizontal class="w-4 h-4" />
        </Button>

        {#if showDropdown}
          <div class="absolute right-0 top-full mt-2 w-56 bg-white rounded-md shadow-lg border border-gray-200 z-50">
            <div class="py-1">
              {#if job.state === 'R' || job.state === 'PD'}
                <button
                  class="flex items-center gap-2 w-full px-4 py-2 text-sm text-red-700 hover:bg-red-50 font-medium"
                  onclick={handleCancelFromMenu}
                >
                  <Square class="w-4 h-4" />
                  Cancel Job
                </button>
              {/if}

              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                onclick={handleResubmitJob}
              >
                <RotateCcw class="w-4 h-4" />
                Resubmit Job
              </button>

              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                onclick={handleAttachWatchersFromMenu}
              >
                <Plus class="w-4 h-4" />
                Attach Watchers
              </button>

              <div class="border-t border-gray-100 my-1"></div>

              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                onclick={handleDownloadOutputs}
              >
                <Download class="w-4 h-4" />
                Download Output
              </button>

              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                onclick={handleDownloadScript}
              >
                <FileText class="w-4 h-4" />
                Download Script
              </button>
            </div>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .header {
    background: white;
    padding: 1rem 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: relative;
    z-index: 60; /* Higher than the global header (z-50) */
  }

  /* Mobile optimizations - smaller, more compact */
  @media (max-width: 768px) {
    .header {
      padding: 0.375rem 0.75rem; /* Much smaller padding on mobile */
      min-height: 2.5rem;
    }
  }


  .header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex: 1;
    min-width: 0;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
</style>