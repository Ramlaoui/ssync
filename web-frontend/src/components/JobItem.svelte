<script lang="ts">
  import { Square, RotateCcw, Download, FileText } from 'lucide-svelte';
  import { push } from 'svelte-spa-router';
  import type { JobInfo } from '../types/api';
  import { jobUtils } from '../lib/jobUtils';
  import { api } from '../services/api';

  interface Props {
    job: JobInfo;
    selected?: boolean;
    onSelect: (job: JobInfo) => void;
  }

  let { job, selected = false, onSelect }: Props = $props();

  // Context menu state
  let showContextMenu = $state(false);
  let contextMenuX = $state(0);
  let contextMenuY = $state(0);

  function handleClick() {
    onSelect(job);
  }

  function handleContextMenu(event: MouseEvent) {
    event.preventDefault();
    contextMenuX = event.clientX;
    contextMenuY = event.clientY;
    showContextMenu = true;
  }

  function closeContextMenu() {
    showContextMenu = false;
  }

  async function handleCancelJob(event: MouseEvent) {
    event.stopPropagation();

    if (!confirm(`Are you sure you want to cancel job ${job.job_id}?`)) {
      return;
    }

    try {
      await api.post(`/api/jobs/${job.job_id}/cancel?host=${job.hostname}`);
    } catch (error) {
      console.error('Failed to cancel job:', error);
      alert('Failed to cancel job. Please try again.');
    }
  }

  async function handleResubmitJob() {
    try {
      const scriptResponse = await api.get(`/api/jobs/${job.job_id}/script?host=${job.hostname}`);
      const scriptContent = scriptResponse.data.content;

      // Navigate to launch page with pre-filled script
      push('/launch');
      // TODO: Pass script content to launch page via state or URL
    } catch (error) {
      console.error('Failed to fetch script for resubmit:', error);
      alert('Failed to fetch job script. Please try again.');
    }
  }

  async function handleDownloadScript() {
    try {
      const response = await api.get(`/api/jobs/${job.job_id}/script?host=${job.hostname}`);
      const scriptContent = response.data.content;

      const blob = new Blob([scriptContent], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);
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
  }

  // Close context menu when clicking outside
  function handleDocumentClick(event: MouseEvent) {
    if (showContextMenu) {
      closeContextMenu();
    }
  }

  $effect(() => {
    if (showContextMenu) {
      document.addEventListener('click', handleDocumentClick);
      return () => document.removeEventListener('click', handleDocumentClick);
    }
  });

  function formatJobName(name: string | undefined): string {
    if (!name) return 'Untitled Job';
    return name.length > 50 ? name.substring(0, 50) + '...' : name;
  }

  function formatRuntime(runtime: string | undefined): string {
    if (!runtime) return '';
    // Already formatted by backend
    return runtime;
  }
</script>

<button
  class="job-item"
  class:selected={selected}
  onclick={handleClick}
  oncontextmenu={handleContextMenu}
>
  <div class="job-status" style="background-color: {job.state ? jobUtils.getStateColor(job.state) : '#9ca3af'}"></div>
  <div class="job-info">
    <div class="job-header">
      <span class="job-id">{job.job_id}</span>
      {#if job.runtime}
        <span class="job-runtime-badge" class:runtime-active={job.state === 'R'}>{formatRuntime(job.runtime)}</span>
      {/if}
    </div>
    <div class="job-content">
      <span class="job-name">{formatJobName(job.name)}</span>
      <span class="job-state-label" class:state-running={job.state === 'R'} class:state-pending={job.state === 'PD'}>
        {#if job.state === 'R'}
          <svg viewBox="0 0 24 24" fill="currentColor" class="state-icon">
            <path d="M8,5.14V19.14L19,12.14L8,5.14Z" />
          </svg>
          Running
        {:else if job.state === 'PD'}
          <svg viewBox="0 0 24 24" fill="currentColor" class="state-icon">
            <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z" />
          </svg>
          Pending
        {:else}
          {jobUtils.getStateName(job.state)}
        {/if}
      </span>
    </div>
    <div class="job-meta">
      <span class="job-host">{job.hostname.toUpperCase()}</span>
    </div>
  </div>
</button>

{#if showContextMenu}
  <div
    class="context-menu"
    style="left: {contextMenuX}px; top: {contextMenuY}px;"
    onclick={(e) => e.stopPropagation()}
  >
    {#if job.state === 'R' || job.state === 'PD'}
      <button
        class="context-menu-item danger"
        onclick={async (e) => {
          closeContextMenu();
          await handleCancelJob(e);
        }}
      >
        <Square size={14} />
        Cancel Job
      </button>
    {/if}
    <button
      class="context-menu-item"
      onclick={() => {
        closeContextMenu();
        handleResubmitJob();
      }}
    >
      <RotateCcw size={14} />
      Resubmit Job
    </button>
    <div class="context-menu-divider"></div>
    <button
      class="context-menu-item"
      onclick={() => {
        closeContextMenu();
        handleDownloadScript();
      }}
    >
      <FileText size={14} />
      Download Script
    </button>
  </div>
{/if}

<style>
  /* Context menu */
  .context-menu {
    position: fixed;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
    padding: 0.25rem;
    min-width: 12rem;
    z-index: 1000;
    animation: contextMenuFadeIn 0.1s ease-out;
  }

  @keyframes contextMenuFadeIn {
    from {
      opacity: 0;
      transform: scale(0.95);
    }
    to {
      opacity: 1;
      transform: scale(1);
    }
  }

  .context-menu-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: transparent;
    border: none;
    border-radius: 0.375rem;
    cursor: pointer;
    text-align: left;
    font-size: 0.875rem;
    color: var(--foreground);
    transition: background 0.15s ease;
  }

  .context-menu-item:hover {
    background: var(--muted);
  }

  .context-menu-item.danger {
    color: #ef4444;
  }

  .context-menu-item.danger:hover {
    background: rgba(239, 68, 68, 0.1);
  }

  .context-menu-divider {
    height: 1px;
    background: var(--border);
    margin: 0.25rem 0;
  }
</style>
