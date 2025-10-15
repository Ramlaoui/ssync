<script lang="ts">
  import { jobUtils } from '../lib/jobUtils';
  import type { JobInfo } from '../types/api';

  interface Props {
    job: JobInfo;
  }

  let { job }: Props = $props();
  
  interface TimelineStep {
    id: string;
    title: string;
    time: string | null;
    status: 'completed' | 'active' | 'pending' | 'failed';
    duration?: string;
    description?: string;
    icon: string;
  }
  
  
  function createTimelineSteps(job: JobInfo): TimelineStep[] {
    const steps: TimelineStep[] = [
      {
        id: 'submitted',
        title: 'Submitted',
        time: job.submit_time,
        status: job.submit_time ? 'completed' : 'pending',
        description: `Job ${job.job_id} submitted to ${job.partition || 'default'} partition`,
        icon: 'upload'
      },
      {
        id: 'queued',
        title: 'Queued',
        time: job.submit_time,
        status: job.submit_time ? 'completed' : 'pending',
        description: job.state === 'PD' ? 
          `Waiting for resources${job.reason && job.reason !== 'None' ? ` (${job.reason})` : ''}` : 
          'Queued and waiting for resources',
        icon: 'clock'
      },
      {
        id: 'started',
        title: 'Started',
        time: job.start_time,
        status: job.start_time ? 'completed' : 
                job.state === 'PD' ? 'pending' : 
                job.state === 'R' ? 'active' : 'pending',
        description: job.start_time ? 
          `Started on ${job.node_list || 'compute nodes'}` : 
          'Waiting to start execution',
        icon: 'play'
      },
      {
        id: 'running',
        title: 'Running',
        time: job.state === 'R' ? 'now' : job.start_time,
        status: job.state === 'R' ? 'active' : 
                job.state === 'CG' ? 'active' :
                ['CD', 'F', 'CA', 'TO'].includes(job.state) ? 'completed' :
                'pending',
        duration: job.state === 'R' ? jobUtils.formatDuration(job.runtime) : undefined,
        description: job.state === 'R' ? 
          `Running for ${jobUtils.formatDuration(job.runtime)}` : 
          job.state === 'CG' ? 'Completing execution' :
          'Execute job commands',
        icon: 'cpu'
      },
      {
        id: 'completed',
        title: getCompletionTitle(job),
        time: job.end_time,
        status: getCompletionStatus(job),
        description: getCompletionDescription(job),
        icon: getCompletionIcon(job)
      }
    ];
    
    return steps;
  }
  
  function getCurrentStepIndex(job: JobInfo): number {
    switch (job.state) {
      case 'PD': return 1;
      case 'R': return 3;
      case 'CG': return 3;
      case 'CD':
      case 'F':
      case 'CA':
      case 'TO': return 4;
      default: return 0;
    }
  }
  
  function getCompletionTitle(job: JobInfo): string {
    switch (job.state) {
      case 'CD': return 'Completed';
      case 'F': return 'Failed';
      case 'CA': return 'Cancelled';
      case 'TO': return 'Timeout';
      default: return 'Complete';
    }
  }
  
  function getCompletionStatus(job: JobInfo): 'completed' | 'failed' | 'pending' {
    if (['CD', 'F', 'CA', 'TO'].includes(job.state)) {
      return job.state === 'F' ? 'failed' : 'completed';
    }
    return 'pending';
  }
  
  function getCompletionDescription(job: JobInfo): string {
    switch (job.state) {
      case 'CD': 
        return `Completed successfully${job.exit_code ? ` (exit ${job.exit_code})` : ''}`;
      case 'F': 
        return `Failed${job.exit_code ? ` with exit code ${job.exit_code}` : ''}`;
      case 'CA': 
        return 'Job was cancelled';
      case 'TO': 
        return 'Exceeded time limit';
      default: 
        return 'Finish execution and cleanup';
    }
  }
  
  function getCompletionIcon(job: JobInfo): string {
    switch (job.state) {
      case 'CD': return 'check';
      case 'F': return 'x';
      case 'CA': return 'stop';
      case 'TO': return 'clock';
      default: return 'flag';
    }
  }
  
  function formatTimelineTime(time: string | null): string {
    if (!time || time === 'N/A') return '';
    if (time === 'now') return 'now';
    return jobUtils.formatTime(time);
  }
  let steps = $derived(createTimelineSteps(job));
  let currentStepIndex = $derived(getCurrentStepIndex(job));
</script>

<div class="timeline-container">
  <h3 class="timeline-title">Job Progress</h3>
  
  <div class="timeline">
    {#each steps as step, index}
      <div 
        class="timeline-step"
        class:completed={step.status === 'completed'}
        class:active={step.status === 'active'}
        class:failed={step.status === 'failed'}
        class:pending={step.status === 'pending'}
      >
        <!-- Step Connector Line -->
        {#if index > 0}
          <div class="step-line" class:completed={steps[index - 1].status === 'completed'}></div>
        {/if}
        
        <!-- Step Icon -->
        <div class="step-icon">
          {#if step.icon === 'upload'}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M9,16V10H5L12,3L19,10H15V16H9M5,20V18H19V20H5Z"/>
            </svg>
          {:else if step.icon === 'clock'}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z"/>
            </svg>
          {:else if step.icon === 'play'}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M8,5.14V19.14L19,12.14L8,5.14Z"/>
            </svg>
          {:else if step.icon === 'cpu'}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M17,17H7V7H17M21,11V9H19V7C19,5.89 18.1,5 17,5H15V3H13V5H11V3H9V5H7C5.89,5 5,5.89 5,7V9H3V11H5V13H3V15H5V17C5,18.1 5.89,19 7,19H9V21H11V19H13V21H15V19H17C18.1,19 19,18.1 19,17V15H21V13H19V11M15,13H9V9H15"/>
            </svg>
          {:else if step.icon === 'check'}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z"/>
            </svg>
          {:else if step.icon === 'x'}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
            </svg>
          {:else if step.icon === 'stop'}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M18,18H6V6H18V18Z"/>
            </svg>
          {:else if step.icon === 'flag'}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M14.4,6L14,4H5V21H7V14H12.6L13,16H20V6H14.4Z"/>
            </svg>
          {/if}
          
          <!-- Active indicator -->
          {#if step.status === 'active'}
            <div class="active-pulse"></div>
          {/if}
        </div>
        
        <!-- Step Content -->
        <div class="step-content">
          <div class="step-header">
            <h4 class="step-title">{step.title}</h4>
            <div class="step-meta">
              {#if step.time}
                <span class="step-time">{formatTimelineTime(step.time)}</span>
              {/if}
              {#if step.duration}
                <span class="step-duration">{step.duration}</span>
              {/if}
            </div>
          </div>
          <p class="step-description">{step.description}</p>
        </div>
      </div>
    {/each}
  </div>
  
  <!-- Timeline Summary -->
  <div class="timeline-summary">
    <div class="summary-item">
      <span class="summary-label">Total Runtime</span>
      <span class="summary-value">{jobUtils.formatDuration(job.runtime)}</span>
    </div>
    {#if job.time_limit && job.time_limit !== 'UNLIMITED'}
      <div class="summary-item">
        <span class="summary-label">Time Limit</span>
        <span class="summary-value">{job.time_limit}</span>
      </div>
    {/if}
    {#if job.state === 'R' && jobUtils.getTimeRemaining(job) !== 'N/A'}
      <div class="summary-item">
        <span class="summary-label">Remaining</span>
        <span class="summary-value">{jobUtils.getTimeRemaining(job)}</span>
      </div>
    {/if}
  </div>
</div>

<style>
  .timeline-container {
    background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 16px;
    padding: 1.5rem;
    box-shadow: 
      0 0 0 1px rgba(255, 255, 255, 0.8),
      0 1px 3px rgba(0, 0, 0, 0.04),
      0 4px 12px rgba(0, 0, 0, 0.04);
  }

  .timeline-title {
    font-size: 1.125rem;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 1.5rem 0;
    letter-spacing: -0.025em;
  }

  .timeline {
    position: relative;
    padding-left: 1rem;
  }

  .timeline-step {
    position: relative;
    display: flex;
    align-items: flex-start;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .timeline-step:last-child {
    margin-bottom: 0;
  }

  .step-line {
    position: absolute;
    left: 1.5rem;
    top: -1.5rem;
    width: 2px;
    height: 1.5rem;
    background: #e2e8f0;
    transition: background-color 0.3s ease;
  }

  .step-line.completed {
    background: #10b981;
  }

  .step-icon {
    position: relative;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s ease;
    flex-shrink: 0;
  }

  .timeline-step.pending .step-icon {
    background: #f1f5f9;
    color: #94a3b8;
    border: 2px solid #e2e8f0;
  }

  .timeline-step.completed .step-icon {
    background: #dcfdf4;
    color: #059669;
    border: 2px solid #10b981;
    box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.1);
  }

  .timeline-step.active .step-icon {
    background: #dbeafe;
    color: #1d4ed8;
    border: 2px solid #3b82f6;
    box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.1);
  }

  .timeline-step.failed .step-icon {
    background: #fee2e2;
    color: #dc2626;
    border: 2px solid #ef4444;
    box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.1);
  }

  .step-icon svg {
    width: 18px;
    height: 18px;
  }

  .active-pulse {
    position: absolute;
    inset: -4px;
    border: 2px solid #3b82f6;
    border-radius: 50%;
    animation: pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  }

  @keyframes pulse-ring {
    0% {
      transform: scale(1);
      opacity: 0.8;
    }
    50% {
      transform: scale(1.1);
      opacity: 0.4;
    }
    100% {
      transform: scale(1.2);
      opacity: 0;
    }
  }

  .step-content {
    flex: 1;
    min-width: 0;
  }

  .step-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.25rem;
    gap: 1rem;
  }

  .step-title {
    font-size: 1rem;
    font-weight: 600;
    color: #0f172a;
    margin: 0;
  }

  .timeline-step.pending .step-title {
    color: #64748b;
  }

  .step-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .step-time {
    font-size: 0.75rem;
    color: #64748b;
    font-weight: 500;
  }

  .step-duration {
    font-size: 0.75rem;
    color: #3b82f6;
    font-weight: 600;
    background: #eff6ff;
    padding: 0.125rem 0.5rem;
    border-radius: 9999px;
  }

  .step-description {
    font-size: 0.875rem;
    color: #64748b;
    margin: 0;
    line-height: 1.4;
  }

  .timeline-summary {
    display: flex;
    gap: 1.5rem;
    margin-top: 1.5rem;
    padding-top: 1rem;
    border-top: 1px solid rgba(148, 163, 184, 0.15);
  }

  .summary-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }

  .summary-label {
    font-size: 0.6875rem;
    color: #94a3b8;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
  }

  .summary-value {
    font-size: 0.875rem;
    font-weight: 600;
    color: #0f172a;
  }

  @media (max-width: 640px) {
    .timeline-container {
      padding: 1rem;
    }

    .step-header {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }

    .timeline-summary {
      gap: 1rem;
    }
  }
</style>