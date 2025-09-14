<script lang="ts">
  import { jobUtils } from '../lib/jobUtils';
  import type { JobInfo } from '../types/api';

  export let job: JobInfo;
  
  $: progress = jobUtils.calculateProgress(job);
  $: timeRemaining = jobUtils.getTimeRemaining(job);
  $: statusColor = jobUtils.getStateColor(job.state);
  $: statusLabel = jobUtils.getStateLabel(job.state);
  $: isActive = jobUtils.isActiveJob(job.state);
  
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

<div class="status-card">
  <div class="status-main">
    <!-- Animated Status Indicator -->
    <div class="status-indicator" style="--status-color: {statusColor}">
      {#if progress > 0 && job.state === 'R'}
        <!-- Progress ring for running jobs -->
        <svg class="progress-ring" viewBox="0 0 36 36">
          <path
            class="progress-ring-bg"
            d="M18 2.0845
              a 15.9155 15.9155 0 0 1 0 31.831
              a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-opacity="0.1"
          />
          <path
            class="progress-ring-fill"
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
          <div class="pulse-rings">
            <div class="pulse-ring"></div>
            <div class="pulse-ring delay-1"></div>
          </div>
        {/if}
      {/if}
      
      <!-- Status Icon -->
      <div class="status-icon">
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
    <div class="status-details">
      <h3 class="status-title">{statusLabel}</h3>
      <p class="status-subtitle">{getStatusSubtitle(job)}</p>
      
      {#if job.state === 'PD'}
        <p class="queue-position">{getQueuePosition(job)}</p>
      {:else if job.state === 'R' && timeRemaining !== 'N/A'}
        <p class="time-remaining">{timeRemaining} remaining</p>
      {/if}
    </div>
  </div>

  <!-- Progress Bar for Running Jobs -->
  {#if job.state === 'R' && progress > 0}
    <div class="progress-bar-container">
      <div class="progress-bar">
        <div 
          class="progress-fill" 
          style="width: {progress * 100}%; background-color: {statusColor}"
        ></div>
      </div>
      <span class="progress-text">{Math.round(progress * 100)}%</span>
    </div>
  {/if}

  <!-- Quick Stats -->
  <div class="quick-stats">
    {#if job.runtime}
      <div class="stat">
        <span class="stat-label">Runtime</span>
        <span class="stat-value">{jobUtils.formatDuration(job.runtime)}</span>
      </div>
    {/if}
    {#if job.cpus}
      <div class="stat">
        <span class="stat-label">CPUs</span>
        <span class="stat-value">{job.cpus}</span>
      </div>
    {/if}
    {#if job.memory}
      <div class="stat">
        <span class="stat-label">Memory</span>
        <span class="stat-value">{job.memory}</span>
      </div>
    {/if}
  </div>
</div>

<style>
  .status-card {
    background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 16px;
    padding: 1.5rem;
    box-shadow: 
      0 0 0 1px rgba(255, 255, 255, 0.8),
      0 1px 3px rgba(0, 0, 0, 0.04),
      0 4px 12px rgba(0, 0, 0, 0.04);
    transition: all 0.3s ease;
  }

  .status-card:hover {
    transform: translateY(-2px);
    box-shadow: 
      0 0 0 1px rgba(255, 255, 255, 0.9),
      0 4px 6px rgba(0, 0, 0, 0.05),
      0 10px 25px rgba(0, 0, 0, 0.08);
  }

  .status-main {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .status-indicator {
    position: relative;
    width: 64px;
    height: 64px;
    color: var(--status-color);
    flex-shrink: 0;
  }

  .progress-ring {
    width: 100%;
    height: 100%;
    transform: rotate(-90deg);
  }

  .pulse-rings {
    position: absolute;
    inset: 0;
  }

  .pulse-ring {
    position: absolute;
    inset: 0;
    border: 2px solid currentColor;
    border-radius: 50%;
    animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    opacity: 0.6;
  }

  .pulse-ring.delay-1 {
    animation-delay: 1s;
  }

  @keyframes pulse {
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

  .status-icon {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: white;
    border-radius: 50%;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }

  .status-icon svg {
    width: 24px;
    height: 24px;
  }

  .status-details {
    flex: 1;
    min-width: 0;
  }

  .status-title {
    font-size: 1.25rem;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 0.25rem 0;
    letter-spacing: -0.025em;
  }

  .status-subtitle {
    font-size: 0.875rem;
    color: #64748b;
    margin: 0;
    font-weight: 500;
  }

  .queue-position,
  .time-remaining {
    font-size: 0.75rem;
    color: #94a3b8;
    margin: 0.25rem 0 0 0;
    font-weight: 500;
  }

  .progress-bar-container {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .progress-bar {
    flex: 1;
    height: 8px;
    background: rgba(0, 0, 0, 0.06);
    border-radius: 4px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s ease;
    background: linear-gradient(90deg, currentColor 0%, color-mix(in srgb, currentColor 80%, white) 100%);
  }

  .progress-text {
    font-size: 0.75rem;
    font-weight: 600;
    color: #64748b;
    min-width: 3rem;
    text-align: right;
  }

  .quick-stats {
    display: flex;
    gap: 1.5rem;
    padding-top: 1rem;
    border-top: 1px solid rgba(148, 163, 184, 0.15);
  }

  .stat {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }

  .stat-label {
    font-size: 0.6875rem;
    color: #94a3b8;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
  }

  .stat-value {
    font-size: 0.875rem;
    font-weight: 600;
    color: #0f172a;
  }

  @media (max-width: 640px) {
    .status-card {
      padding: 1rem;
    }

    .status-indicator {
      width: 48px;
      height: 48px;
    }

    .status-icon svg {
      width: 20px;
      height: 20px;
    }

    .status-title {
      font-size: 1.125rem;
    }

    .quick-stats {
      gap: 1rem;
    }
  }
</style>