<script lang="ts">
  import { jobUtils } from '../lib/jobUtils';
  import type { JobInfo } from '../types/api';

  interface Props {
    job: JobInfo;
  }

  let { job }: Props = $props();
  
  let progress = $derived(jobUtils.calculateProgress(job));
  let timeRemaining = $derived(jobUtils.getTimeRemaining(job));
  let statusColor = $derived(jobUtils.getStateColor(job.state));
  let statusLabel = $derived(jobUtils.getStateLabel(job.state));
  let isActive = $derived(jobUtils.isActiveJob(job.state));
  
  function getStatusSubtitle(job: JobInfo): string {
    switch (job.state) {
      case 'R':
        return `Running for ${jobUtils.formatDuration(job.runtime)}`;
      case 'PD':
        const reason = job.reason && job.reason !== 'None' ? job.reason : 'Resources';
        return `Waiting for ${reason.toLowerCase()}`;
      case 'CD':
        return `Completed • Exit code ${job.exit_code || '0'}`;
      case 'F':
        return `Failed • Exit code ${job.exit_code || 'Unknown'}`;
      case 'CA':
        return `Cancelled by ${job.user || 'system'}`;
      case 'TO':
        return 'Exceeded time limit';
      case 'CG':
        return 'Finishing up...';
      default:
        return 'Status unknown';
    }
  }

  function getQueuePosition(job: JobInfo): string {
    // This would come from the API in a real implementation
    // For demo purposes, we'll simulate it
    if (job.state === 'PD' && job.priority) {
      const pos = Math.floor(Math.random() * 50) + 1;
      return `#${pos} in ${job.partition || 'queue'}`;
    }
    return '';
  }
</script>

<div class="bg-gradient-to-br from-white to-slate-50 border border-slate-200/20 rounded-2xl p-6 shadow-[0_0_0_1px_rgba(255,255,255,0.8),0_1px_3px_rgba(0,0,0,0.04),0_4px_12px_rgba(0,0,0,0.04)] transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_0_0_1px_rgba(255,255,255,0.9),0_4px_6px_rgba(0,0,0,0.05),0_10px_25px_rgba(0,0,0,0.08)]">
  <div class="flex items-center gap-4 mb-4">
    <!-- Animated Status Indicator -->
    <div class="relative w-16 h-16 flex-shrink-0" style="color: {statusColor}">
      {#if progress > 0 && job.state === 'R'}
        <!-- Progress ring for running jobs -->
        <svg class="w-full h-full -rotate-90" viewBox="0 0 36 36">
          <path
            d="M18 2.0845
              a 15.9155 15.9155 0 0 1 0 31.831
              a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-opacity="0.1"
          />
          <path
            d="M18 2.0845
              a 15.9155 15.9155 0 0 1 0 31.831
              a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-dasharray="{progress * 100}, 100"
            stroke-linecap="round"
          />
        </svg>
      {:else}
        <!-- Pulse animation for active states -->
        {#if isActive}
          <div class="absolute inset-0">
            <div class="absolute inset-0 border-2 border-current rounded-full animate-pulse opacity-60"></div>
            <div class="absolute inset-0 border-2 border-current rounded-full animate-pulse opacity-60 [animation-delay:1s]"></div>
          </div>
        {/if}
      {/if}
      
      <!-- Status Icon -->
      <div class="absolute inset-0 flex items-center justify-center bg-white rounded-full shadow-md">
        {#if job.state === 'R'}
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M8,5.14V19.14L19,12.14L8,5.14Z" />
          </svg>
        {:else if job.state === 'PD'}
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z"/>
          </svg>
        {:else if job.state === 'CD'}
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z"/>
          </svg>
        {:else if job.state === 'F'}
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
          </svg>
        {:else if job.state === 'CA'}
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M14.5,9A1.5,1.5 0 0,0 13,10.5A1.5,1.5 0 0,0 14.5,12A1.5,1.5 0 0,0 16,10.5A1.5,1.5 0 0,0 14.5,9M9.5,9A1.5,1.5 0 0,0 8,10.5A1.5,1.5 0 0,0 9.5,12A1.5,1.5 0 0,0 11,10.5A1.5,1.5 0 0,0 9.5,9M12,14C13.25,14 14.31,14.69 14.71,15.69L13.26,16.16C13.05,15.65 12.57,15.3 12,15.3C11.43,15.3 10.95,15.65 10.74,16.16L9.29,15.69C9.69,14.69 10.75,14 12,14Z"/>
          </svg>
        {:else}
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M13,14H11V10H13M13,18H11V16H13M1,21H23L12,2L1,21Z"/>
          </svg>
        {/if}
      </div>
    </div>

    <!-- Status Details -->
    <div class="flex-1 min-w-0">
      <h3 class="text-xl font-bold text-slate-900 mb-1 tracking-tight">{statusLabel}</h3>
      <p class="text-sm text-slate-600 mb-0 font-medium">{getStatusSubtitle(job)}</p>
      
      {#if job.state === 'PD'}
        <p class="text-xs text-slate-400 mt-1 font-medium">{getQueuePosition(job)}</p>
      {:else if job.state === 'R' && timeRemaining !== 'N/A'}
        <p class="text-xs text-slate-400 mt-1 font-medium">{timeRemaining} remaining</p>
      {/if}
    </div>
  </div>

  <!-- Progress Bar for Running Jobs -->
  {#if job.state === 'R' && progress > 0}
    <div class="flex items-center gap-3 mb-4">
      <div class="flex-1 h-2 bg-black/5 rounded-full overflow-hidden">
        <div
          class="h-full rounded-full transition-[width] duration-300 bg-gradient-to-r from-current to-current/80"
          style="width: {progress * 100}%; background-color: {statusColor}"
        ></div>
      </div>
      <span class="text-xs font-semibold text-slate-600 min-w-[3rem] text-right">{Math.round(progress * 100)}%</span>
    </div>
  {/if}

  <!-- Quick Stats -->
  <div class="flex gap-6 pt-4 border-t border-slate-200/30">
    {#if job.runtime}
      <div class="flex flex-col items-center text-center">
        <span class="text-[0.6875rem] text-slate-400 font-medium uppercase tracking-wider mb-1">Runtime</span>
        <span class="text-sm font-semibold text-slate-900">{jobUtils.formatDuration(job.runtime)}</span>
      </div>
    {/if}
    {#if job.cpus}
      <div class="flex flex-col items-center text-center">
        <span class="text-[0.6875rem] text-slate-400 font-medium uppercase tracking-wider mb-1">CPUs</span>
        <span class="text-sm font-semibold text-slate-900">{job.cpus}</span>
      </div>
    {/if}
    {#if job.memory}
      <div class="flex flex-col items-center text-center">
        <span class="text-[0.6875rem] text-slate-400 font-medium uppercase tracking-wider mb-1">Memory</span>
        <span class="text-sm font-semibold text-slate-900">{job.memory}</span>
      </div>
    {/if}
  </div>
</div>

<style>
  /* Custom animations for pulse effect */
  @keyframes custom-pulse {
    0% {
      transform: scale(0.95);
      opacity: 0.8;
    }
    50% {
      transform: scale(1.05);
      opacity: 0.4;
    }
    100% {
      transform: scale(1.15);
      opacity: 0;
    }
  }

  /* Apply custom pulse animation to override Tailwind's default */
  :global(.animate-pulse) {
    animation: custom-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite !important;
  }

  /* SVG icon sizing */
  svg {
    width: 1.5rem;
    height: 1.5rem;
  }

  /* Mobile responsive adjustments */
  @media (max-width: 640px) {
    svg {
      width: 1.25rem;
      height: 1.25rem;
    }
  }
</style>