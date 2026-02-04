<script lang="ts">
  import type { JobInfo } from "../types/api";
  import LoadingSpinner from './LoadingSpinner.svelte';

  interface Props {
    job?: JobInfo | null;
  }

  let { job = null }: Props = $props();

  function formatTime(time: string | null): string {
    if (!time || time === 'N/A' || time === 'Unknown') return 'N/A';
    try {
      const date = new Date(time);
      return date.toLocaleString();
    } catch {
      return time;
    }
  }

  function formatDuration(seconds: number | string | null): string {
    if (!seconds || seconds === 'N/A' || seconds === 'Unknown') return 'N/A';

    const totalSeconds = typeof seconds === 'string' ? parseFloat(seconds) : seconds;
    if (isNaN(totalSeconds)) return 'N/A';

    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const secs = Math.floor(totalSeconds % 60);

    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  }

  function formatMemory(memory: string | null): string {
    if (!memory || memory === 'N/A' || memory === 'Unknown') return 'N/A';

    // Parse memory string (e.g., "1024K", "2G", "512M")
    const match = memory.match(/^(\d+(?:\.\d+)?)([KMGT]?)$/);
    if (!match) return memory;

    const value = parseFloat(match[1]);
    const unit = match[2];

    switch (unit) {
      case 'K': return `${(value / 1024).toFixed(1)} MB`;
      case 'M': return `${value} MB`;
      case 'G': return `${value} GB`;
      case 'T': return `${value} TB`;
      default: return `${(value / 1024 / 1024).toFixed(1)} MB`;
    }
  }
</script>

{#if job}
  <div class="p-6 w-full">
    <!-- Main horizontal layout container -->
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
    <!-- Job Status & Basic Info -->
    <div class="bg-card border border-border rounded-xl p-6 shadow-sm hover:shadow-md transition-all duration-300">
      <h3 class="text-sm font-bold text-muted-foreground uppercase tracking-wider mb-5 flex items-center gap-2">
        <div class="w-1 h-5 bg-gradient-to-b from-blue-500 to-indigo-500 dark:from-blue-400/40 dark:to-indigo-400/40 rounded-full"></div>
        Job Overview
      </h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="space-y-4">
          <div class="py-2 border-b border-border/30 last:border-b-0">
            <span class="text-sm font-medium text-muted-foreground block mb-2">Job ID:</span>
            <span class="text-sm font-semibold text-foreground">{job.job_id}</span>
          </div>
          {#if job.name && job.name !== 'N/A'}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">Job Name:</span>
              <span class="text-sm font-semibold text-foreground">{job.name}</span>
            </div>
          {/if}
          <div class="py-2 border-b border-border/30 last:border-b-0">
            <span class="text-sm font-medium text-muted-foreground block mb-2">User:</span>
            <span class="text-sm font-semibold text-foreground">{job.user || 'N/A'}</span>
          </div>
          <div class="py-2 border-b border-border/30 last:border-b-0">
            <span class="text-sm font-medium text-muted-foreground block mb-2">Hostname:</span>
            <span class="text-sm font-semibold text-foreground">{job.hostname || 'N/A'}</span>
          </div>
        </div>
        <div class="space-y-4">
          <div class="py-2 border-b border-border/30 last:border-b-0">
            <span class="text-sm font-medium text-muted-foreground block mb-2">Status:</span>
            <span class="text-sm font-semibold text-foreground">{job.state}</span>
          </div>
          {#if job.partition && job.partition !== 'N/A'}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">Partition:</span>
              <span class="text-sm font-semibold text-foreground">{job.partition}</span>
            </div>
          {/if}
          {#if job.account && job.account !== 'N/A'}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">Account:</span>
              <span class="text-sm font-semibold text-foreground">{job.account}</span>
            </div>
          {/if}
          {#if job.qos && job.qos !== 'N/A'}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">QOS:</span>
              <span class="text-sm font-semibold text-foreground">{job.qos}</span>
            </div>
          {/if}
        </div>
      </div>
    </div>

    <!-- Timing Information -->
    <div class="bg-card border border-border rounded-xl p-6 shadow-sm hover:shadow-md transition-all duration-300">
      <h3 class="text-sm font-bold text-muted-foreground uppercase tracking-wider mb-5 flex items-center gap-2">
        <div class="w-1 h-5 bg-gradient-to-b from-green-500 to-emerald-500 dark:from-green-400/40 dark:to-emerald-400/40 rounded-full"></div>
        Timing
      </h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="space-y-4">
          <div class="py-2 border-b border-border/30 last:border-b-0">
            <span class="text-sm font-medium text-muted-foreground block mb-2">Submit Time:</span>
            <span class="text-sm font-semibold text-foreground">{formatTime(job.submit_time)}</span>
          </div>
          <div class="py-2 border-b border-border/30 last:border-b-0">
            <span class="text-sm font-medium text-muted-foreground block mb-2">Start Time:</span>
            <span class="text-sm font-semibold text-foreground">{formatTime(job.start_time)}</span>
          </div>
          <div class="py-2 border-b border-border/30 last:border-b-0">
            <span class="text-sm font-medium text-muted-foreground block mb-2">End Time:</span>
            <span class="text-sm font-semibold text-foreground">{formatTime(job.end_time)}</span>
          </div>
        </div>
        <div class="space-y-4">
          <div class="py-2 border-b border-border/30 last:border-b-0">
            <span class="text-sm font-medium text-muted-foreground block mb-2">Runtime:</span>
            <span class="text-sm font-semibold text-foreground">{formatDuration(job.runtime)}</span>
          </div>
          {#if job.time_limit && job.time_limit !== 'N/A'}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">Time Limit:</span>
              <span class="text-sm font-semibold text-foreground">{job.time_limit}</span>
            </div>
          {/if}
        </div>
      </div>
    </div>

    <!-- Resource Information -->
    {#if (job.nodes && job.nodes !== 'N/A') || (job.cpus && job.cpus !== 'N/A') || (job.memory && job.memory !== 'N/A')}
      <div class="bg-card border border-border rounded-xl p-6 shadow-sm hover:shadow-md transition-all duration-300">
        <h3 class="text-sm font-bold text-muted-foreground uppercase tracking-wider mb-5 flex items-center gap-2">
          <div class="w-1 h-5 bg-gradient-to-b from-purple-500 to-violet-500 dark:from-purple-400/40 dark:to-violet-400/40 rounded-full"></div>
          Resources
        </h3>
        <div class="space-y-4">
          {#if job.nodes && job.nodes !== 'N/A'}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">Nodes:</span>
              <span class="text-sm font-semibold text-foreground">{job.nodes}</span>
            </div>
          {/if}
          {#if job.cpus && job.cpus !== 'N/A'}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">CPUs:</span>
              <span class="text-sm font-semibold text-foreground">{job.cpus}</span>
            </div>
          {/if}
          {#if job.memory && job.memory !== 'N/A'}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">Memory:</span>
              <span class="text-sm font-semibold text-foreground">{formatMemory(job.memory)}</span>
            </div>
          {/if}
        </div>
      </div>
    {/if}

    <!-- File Information -->
    {#if (job.work_dir && job.work_dir !== 'N/A') || (job.stdout_file && job.stdout_file !== 'N/A') || (job.stderr_file && job.stderr_file !== 'N/A')}
      <div class="bg-card border border-border rounded-xl p-6 shadow-sm hover:shadow-md transition-all duration-300">
        <h3 class="text-sm font-bold text-muted-foreground uppercase tracking-wider mb-5 flex items-center gap-2">
          <div class="w-1 h-5 bg-gradient-to-b from-orange-500 to-red-500 dark:from-orange-400/40 dark:to-red-400/40 rounded-full"></div>
          Files & Paths
        </h3>
        <div class="space-y-4">
          {#if job.work_dir && job.work_dir !== 'N/A'}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">Working Directory:</span>
              <div class="bg-secondary border border-border rounded-md px-3 py-2">
                <span class="text-xs font-mono text-foreground break-all">{job.work_dir}</span>
              </div>
            </div>
          {/if}
          {#if job.stdout_file && job.stdout_file !== 'N/A'}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">Output File:</span>
              <div class="bg-secondary border border-border rounded-md px-3 py-2">
                <span class="text-xs font-mono text-foreground break-all">{job.stdout_file}</span>
              </div>
            </div>
          {/if}
          {#if job.stderr_file && job.stderr_file !== 'N/A'}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">Error File:</span>
              <div class="bg-secondary border border-border rounded-md px-3 py-2">
                <span class="text-xs font-mono text-foreground break-all">{job.stderr_file}</span>
              </div>
            </div>
          {/if}
        </div>
      </div>
    {/if}

    <!-- Additional Information -->
    {#if (job.reason && job.reason !== 'N/A' && job.reason !== 'None') || job.submit_line}
      <div class="bg-card border border-border rounded-xl p-6 shadow-sm hover:shadow-md transition-all duration-300">
        <h3 class="text-sm font-bold text-muted-foreground uppercase tracking-wider mb-5 flex items-center gap-2">
          <div class="w-1 h-5 bg-gradient-to-b from-rose-500 to-pink-500 dark:from-rose-400/40 dark:to-pink-400/40 rounded-full"></div>
          Additional Details
        </h3>
        <div class="space-y-4">
          {#if job.reason && job.reason !== 'N/A' && job.reason !== 'None'}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">Reason:</span>
              <span class="text-sm font-semibold text-foreground">{job.reason}</span>
            </div>
          {/if}
          {#if job.submit_line}
            <div class="py-2 border-b border-border/30 last:border-b-0">
              <span class="text-sm font-medium text-muted-foreground block mb-2">Submit Command:</span>
              <div class="bg-secondary border border-border rounded-md px-3 py-2">
                <span class="text-xs font-mono text-foreground break-all">{job.submit_line}</span>
              </div>
            </div>
          {/if}
        </div>
      </div>
    {/if}

    </div> <!-- End grid container -->
  </div>
{:else}
  <div class="h-64">
    <LoadingSpinner message="Loading job details..." />
  </div>
{/if}
