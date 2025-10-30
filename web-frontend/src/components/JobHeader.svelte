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
      case 'R': return 'status-running';
      case 'PD': return 'status-pending';
      case 'CD': return 'status-completed';
      case 'F': return 'status-failed';
      case 'CA': return 'status-cancelled';
      case 'TO': return 'status-timeout';
      default: return 'status-default';
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
        <button class="header-nav-button" onclick={() => push('/')}>
          <ArrowLeft class="w-4 h-4" />
          Home
        </button>
      {:else}
        <!-- Desktop Job Detail Page: Jobs button -->
        <button class="header-nav-button" onclick={() => push('/')}>
          <ArrowLeft class="w-4 h-4" />
          Jobs
        </button>
      {/if}
    {/if}

    {#if !showSidebarOnly}
      {#if isMobile}
        <!-- Mobile hamburger menu button -->
        <button
          class="header-menu-button"
          onclick={onToggleSidebar}
          aria-label="Show job list"
        >
          <Menu class="w-4 h-4" />
        </button>
      {/if}

      {#if !isMobile}
        <div class="header-divider"></div>
      {/if}

      {#if job}
        <div class="flex items-center gap-2 md:gap-3 min-w-0 flex-1">
          <div class="flex flex-col justify-center min-w-0">
            <h1 class="header-title text-sm md:text-lg">
              Job {job.job_id}
            </h1>
            {#if job.name && job.name !== 'N/A'}
              <span class="header-subtitle text-xs truncate">
                {job.name}
              </span>
            {/if}
          </div>

          {#if job.hostname}
            <span class="header-subtitle text-xs md:text-sm hidden sm:inline">
              on {job.hostname}
            </span>
          {/if}
        </div>
      {:else}
        <h1 class="header-title text-sm md:text-lg">Loading...</h1>
      {/if}
    {:else}
      <div class="header-divider"></div>
      <h1 class="header-title text-lg">Jobs</h1>
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
          <div class="dropdown-menu">
            <div class="py-1">
              {#if job.state === 'R' || job.state === 'PD' || (job.array_job_id && job.array_task_id && job.array_task_id.includes('['))}
                <button
                  class="dropdown-item dropdown-item-danger"
                  onclick={handleCancelFromMenu}
                  title={job.array_job_id && job.array_task_id && job.array_task_id.includes('[') ? 'Cancel all tasks in this array job' : 'Cancel this job'}
                >
                  <Square class="w-4 h-4" />
                  Cancel Job{job.array_job_id && job.array_task_id && job.array_task_id.includes('[') ? ' (All Tasks)' : ''}
                </button>
              {/if}

              <button
                class="dropdown-item"
                onclick={handleResubmitJob}
              >
                <RotateCcw class="w-4 h-4" />
                Resubmit Job
              </button>

              <button
                class="dropdown-item"
                onclick={handleAttachWatchersFromMenu}
              >
                <Plus class="w-4 h-4" />
                Attach Watchers
              </button>

              <div class="dropdown-divider"></div>

              <button
                class="dropdown-item"
                onclick={handleDownloadOutputs}
              >
                <Download class="w-4 h-4" />
                Download Output
              </button>

              <button
                class="dropdown-item"
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
    background: var(--card);
    padding: 1rem 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: relative;
    z-index: 60; /* Higher than the global header (z-50) */
    border-bottom: 1px solid var(--border);
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

  /* Header navigation button */
  .header-nav-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    color: var(--muted-foreground);
    background: transparent;
    border: none;
    border-radius: 0.5rem;
    font-weight: 500;
    transition: all 0.2s;
    cursor: pointer;
  }

  .header-nav-button:hover {
    color: var(--foreground);
    background: var(--secondary);
  }

  :global(.dark) .header-nav-button {
    color: var(--muted-foreground);
  }

  :global(.dark) .header-nav-button:hover {
    color: var(--foreground);
    background: var(--gray-100);
  }

  /* Header menu button */
  .header-menu-button {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.375rem;
    color: var(--muted-foreground);
    background: transparent;
    border: none;
    border-radius: 0.25rem;
    transition: all 0.2s;
    cursor: pointer;
  }

  .header-menu-button:hover {
    color: var(--foreground);
    background: var(--secondary);
  }

  :global(.dark) .header-menu-button {
    color: var(--muted-foreground);
  }

  :global(.dark) .header-menu-button:hover {
    color: var(--foreground);
    background: var(--gray-100);
  }

  /* Header divider */
  .header-divider {
    width: 1px;
    height: 1.5rem;
    background: var(--border);
  }

  /* Header titles */
  .header-title {
    font-weight: 600;
    color: var(--foreground);
  }

  .header-subtitle {
    color: var(--muted-foreground);
  }

  /* Dropdown menu */
  .dropdown-menu {
    position: absolute;
    right: 0;
    top: 100%;
    margin-top: 0.5rem;
    width: 14rem;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 0.375rem;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
    z-index: 50;
  }

  /* Dropdown item */
  .dropdown-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    color: var(--foreground);
    background: transparent;
    border: none;
    text-align: left;
    transition: background 0.15s;
    cursor: pointer;
  }

  .dropdown-item:hover {
    background: var(--secondary);
  }

  :global(.dark) .dropdown-item:hover {
    background: var(--gray-100);
  }

  .dropdown-item-danger {
    color: var(--error);
    font-weight: 500;
  }

  .dropdown-item-danger:hover {
    background: var(--error-bg);
  }

  :global(.dark) .dropdown-item-danger {
    color: var(--error);
  }

  :global(.dark) .dropdown-item-danger:hover {
    background: var(--error-bg);
  }

  /* Dropdown divider */
  .dropdown-divider {
    height: 1px;
    margin: 0.25rem 0;
    background: var(--border);
  }

  /* Status badge styles - vibrant colors with dark mode support */
  :global(.status-running) {
    background-color: #d1fae5;
    color: #065f46;
    font-weight: 600;
  }

  :global(.dark .status-running) {
    background-color: rgba(16, 185, 129, 0.15);
    color: #6ee7b7;
    border: 1px solid rgba(16, 185, 129, 0.3);
  }

  :global(.status-pending) {
    background-color: #fef3c7;
    color: #78350f;
    font-weight: 600;
  }

  :global(.dark .status-pending) {
    background-color: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.3);
  }

  :global(.status-completed) {
    background-color: #dbeafe;
    color: #1e3a8a;
    font-weight: 600;
  }

  :global(.dark .status-completed) {
    background-color: rgba(59, 130, 246, 0.15);
    color: #93c5fd;
    border: 1px solid rgba(59, 130, 246, 0.3);
  }

  :global(.status-failed) {
    background-color: #fee2e2;
    color: #7f1d1d;
    font-weight: 600;
  }

  :global(.dark .status-failed) {
    background-color: rgba(239, 68, 68, 0.15);
    color: #fca5a5;
    border: 1px solid rgba(239, 68, 68, 0.3);
  }

  :global(.status-cancelled) {
    background-color: #f3f4f6;
    color: #1f2937;
    font-weight: 600;
  }

  :global(.dark .status-cancelled) {
    background-color: rgba(156, 163, 175, 0.15);
    color: #d1d5db;
    border: 1px solid rgba(156, 163, 175, 0.3);
  }

  :global(.status-timeout) {
    background-color: #fed7aa;
    color: #7c2d12;
    font-weight: 600;
  }

  :global(.dark .status-timeout) {
    background-color: rgba(249, 115, 22, 0.15);
    color: #fdba74;
    border: 1px solid rgba(249, 115, 22, 0.3);
  }

  :global(.status-default) {
    background-color: #f3f4f6;
    color: #374151;
    font-weight: 600;
  }

  :global(.dark .status-default) {
    background-color: rgba(107, 114, 128, 0.15);
    color: #d1d5db;
    border: 1px solid rgba(107, 114, 128, 0.3);
  }
</style>