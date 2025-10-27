<script lang="ts">
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import type { JobInfo } from '../types/api';
  import LoadingSpinner from './LoadingSpinner.svelte';
  import HostStatusIndicator from './HostStatusIndicator.svelte';
  import { jobUtils } from '../lib/jobUtils';
  import { jobStateManager } from '../lib/JobStateManager';
  import { RefreshCw } from 'lucide-svelte';

  interface Props {
    hostname: string;
    jobs: JobInfo[];
    queryTime: string;
    loading?: boolean;
  }

  let {
    hostname,
    jobs,
    queryTime,
    loading = false
  }: Props = $props();

  const dispatch = createEventDispatcher<{
    jobSelect: JobInfo;
  }>();

  // Mobile detection
  let isMobile = $state(false);

  function checkMobile() {
    isMobile = window.innerWidth <= 768;
  }

  function selectJob(job: JobInfo): void {
    if (loading) return;
    dispatch('jobSelect', job);
  }

  async function refreshHost(): Promise<void> {
    await jobStateManager.syncHost(hostname, true); // true = force sync
  }
  
  function formatTime(timeStr: string | null): string {
    if (!timeStr || timeStr === 'N/A') return 'N/A';
    try {
      const date = new Date(timeStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
      const diffDays = Math.floor(diffHours / 24);
      
      // Show relative time for recent submissions
      if (diffHours < 1) {
        const diffMinutes = Math.floor(diffMs / (1000 * 60));
        return `${diffMinutes}m ago`;
      } else if (diffHours < 24) {
        return `${diffHours}h ago`;
      } else if (diffDays < 7) {
        return `${diffDays}d ago`;
      } else {
        // Show actual date for older submissions
        return date.toLocaleDateString('en-US', { 
          month: 'short', 
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        });
      }
    } catch {
      return timeStr;
    }
  }
  
  function truncate(str: string | null, length = 20): string {
    if (!str || str.length <= length) return str || '';
    return str.substring(0, length) + '...';
  }

  function smartTruncate(str: string | null, maxLength = 30): string {
    if (!str || str.length <= maxLength) return str || '';
    // Try to break at word boundaries if possible
    const truncated = str.substring(0, maxLength);
    const lastSpace = truncated.lastIndexOf(' ');
    if (lastSpace > maxLength * 0.6) {
      return str.substring(0, lastSpace) + '...';
    }
    return truncated + '...';
  }
  
  onMount(() => {
    checkMobile();
    window.addEventListener('resize', checkMobile);
  });
  
  onDestroy(() => {
    window.removeEventListener('resize', checkMobile);
  });
</script>

<div class="bg-white dark:bg-card rounded-lg shadow-sm mb-4 border dark:border-border">
  <div class="bg-gray-50 dark:bg-secondary px-4 py-3 border-b border-gray-200 dark:border-border flex justify-between items-center">
    <h3 class="text-gray-700 dark:text-foreground flex items-center gap-3 font-medium">
      <svg class="w-5 h-5 text-gray-600 dark:text-gray-400" viewBox="0 0 24 24" fill="currentColor">
        <path d="M4,6H20V16H4M20,18A2,2 0 0,0 22,16V6C22,4.89 21.1,4 20,4H4C2.89,4 2,4.89 2,6V16A2,2 0 0,0 4,18H0V20H24V18H20Z"/>
      </svg>
      {hostname}
      <span class="text-sm font-normal text-gray-600 dark:text-gray-400">({jobs.length} jobs)</span>
    </h3>
    <div class="flex items-center gap-3">
      <HostStatusIndicator {hostname} compact={false} />
      <button
        class="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
        onclick={refreshHost}
        title="Refresh jobs for {hostname}"
      >
        <RefreshCw class="h-4 w-4 text-gray-600 dark:text-gray-400" />
      </button>
    </div>
  </div>
  
  {#if jobs.length === 0}
    <div class="py-8 text-center text-gray-600 dark:text-gray-400">
      No jobs found
    </div>
  {:else if isMobile}
    <!-- Mobile Card Layout -->
    <div class="p-2 space-y-2">
      {#each jobs as job}
        <button
          class="w-full bg-white dark:bg-card border border-gray-200 dark:border-border rounded-lg p-3 hover:bg-gray-50 dark:hover:bg-secondary transition-colors text-left {loading ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer'}"
          onclick={() => selectJob(job)}
          disabled={loading}
          aria-label="View job details for job {job.job_id}"
        >
          <div class="flex justify-between items-start mb-2">
            <div class="flex flex-col">
              <span class="text-base font-semibold text-gray-700 dark:text-gray-200">{job.job_id}</span>
              <span class="text-xs text-gray-500 dark:text-gray-400">{job.user || 'N/A'}</span>
            </div>
            <span
              class="px-2 py-1 rounded-full text-xs font-semibold uppercase text-white"
              style="background-color: {jobUtils.getStateColor(job.state)}"
            >
              {job.state}
            </span>
          </div>

          <h4 class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-2" title={job.name}>
            {smartTruncate(job.name, 60)}
          </h4>

          <div class="flex gap-3 text-xs text-gray-600 dark:text-gray-400">
            <span>{job.runtime || 'N/A'}</span>
            {#if job.submit_time}
              <span title={new Date(job.submit_time).toLocaleString()}>
                {formatTime(job.submit_time)}
              </span>
            {/if}
          </div>
        </button>
      {/each}
    </div>
  {:else}
    <!-- Desktop Table Layout -->
    <div class="overflow-x-auto">
      <table class="w-full">
        <thead class="bg-gray-50 dark:bg-secondary border-b border-gray-200 dark:border-border">
          <tr>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Job ID</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Name</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">State</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">User</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Runtime</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Resources</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider hidden xl:table-cell">Partition</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider hidden xl:table-cell">Submitted</th>
          </tr>
        </thead>
        <tbody class="bg-white dark:bg-card divide-y divide-gray-200 dark:divide-border">
          {#each jobs as job}
            <tr
              class="hover:bg-gray-50 dark:hover:bg-secondary transition-colors {loading ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer'}"
              onclick={() => selectJob(job)}
              tabindex="0"
              role="button"
              aria-label="View job details"
              onkeydown={(e) => e.key === 'Enter' && selectJob(job)}
            >
              <td class="px-4 py-3 whitespace-nowrap">
                <strong class="text-gray-700 dark:text-gray-200 font-semibold">{job.job_id}</strong>
              </td>
              <td class="px-4 py-3">
                <div class="text-sm font-medium text-gray-700 dark:text-gray-200" title={job.name}>
                  {smartTruncate(job.name, 30)}
                </div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span
                  class="px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full text-white"
                  style="background-color: {jobUtils.getStateColor(job.state)}"
                >
                  {job.state}
                </span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                {job.user || 'N/A'}
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                {job.runtime || 'N/A'}
              </td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                {#if job.cpus || job.memory || job.nodes}
                  <div class="space-y-1">
                    {#if job.nodes && job.nodes !== 'N/A'}
                      <div class="flex gap-2">
                        <span class="text-gray-500 dark:text-gray-500 text-xs">Nodes:</span>
                        <span class="font-medium text-xs">{job.nodes}</span>
                      </div>
                    {/if}
                    {#if job.cpus && job.cpus !== 'N/A'}
                      <div class="flex gap-2">
                        <span class="text-gray-500 dark:text-gray-500 text-xs">CPUs:</span>
                        <span class="font-medium text-xs">{job.cpus}</span>
                      </div>
                    {/if}
                    {#if job.memory && job.memory !== 'N/A'}
                      <div class="flex gap-2">
                        <span class="text-gray-500 dark:text-gray-500 text-xs">Mem:</span>
                        <span class="font-medium text-xs">{job.memory}</span>
                      </div>
                    {/if}
                  </div>
                {:else}
                  <span class="text-gray-400 dark:text-gray-500 text-xs">N/A</span>
                {/if}
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400 hidden xl:table-cell">
                {job.partition || 'N/A'}
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400 hidden xl:table-cell">
                <span title={job.submit_time ? new Date(job.submit_time).toLocaleString() : 'N/A'}>
                  {job.submit_time ? formatTime(job.submit_time) : 'N/A'}
                </span>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>