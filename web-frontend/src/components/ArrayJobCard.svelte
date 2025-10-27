<script lang="ts">
  import { ChevronDown, ChevronRight, Zap, Clock, CheckCircle, AlertCircle, XCircle } from 'lucide-svelte';
  import { push } from 'svelte-spa-router';
  import type { ArrayJobGroup } from '../types/api';
  import { jobUtils } from '../lib/jobUtils';

  interface Props {
    group: ArrayJobGroup;
    expanded?: boolean;
  }

  let { group, expanded = $bindable(false) }: Props = $props();

  function toggleExpanded() {
    expanded = !expanded;
  }

  function selectTask(taskId: string) {
    // Navigate using URL encoding for safety
    const encodedTaskId = encodeURIComponent(taskId);
    push(`/jobs/${encodedTaskId}/${group.hostname}`);
  }

  function getGroupState(): string {
    // Determine overall group state
    if (group.running_count > 0) return 'R';
    if (group.pending_count === group.total_tasks) return 'PD';
    if (group.completed_count === group.total_tasks) return 'CD';
    if (group.failed_count > 0) return 'F';
    if (group.cancelled_count > 0) return 'CA';
    return 'CD';
  }

  let groupState = $derived(getGroupState());
</script>

<button
  class="array-job-card"
  onclick={toggleExpanded}
>
  <div class="job-status" style="background-color: {jobUtils.getStateColor(groupState)}"></div>

  <div class="expand-icon">
    {#if expanded}
      <ChevronDown size={14} />
    {:else}
      <ChevronRight size={14} />
    {/if}
  </div>

  <div class="job-info">
    <div class="job-header">
      <span class="job-id">{group.array_job_id}</span>
      <span class="array-badge">ARRAY</span>
    </div>
    <div class="job-content">
      <span class="job-name">{group.job_name}</span>
    </div>
    <div class="job-meta">
      <span class="job-host">{group.hostname.toUpperCase()}</span>
      <div class="task-counts">
        {#if group.running_count > 0}
          <span class="count count-running" title="Running">
            <Zap size={10} />
            {group.running_count}
          </span>
        {/if}
        {#if group.pending_count > 0}
          <span class="count count-pending" title="Pending">
            <Clock size={10} />
            {group.pending_count}
          </span>
        {/if}
        {#if group.completed_count > 0}
          <span class="count count-completed" title="Completed">
            <CheckCircle size={10} />
            {group.completed_count}
          </span>
        {/if}
        {#if group.failed_count > 0}
          <span class="count count-failed" title="Failed">
            <AlertCircle size={10} />
            {group.failed_count}
          </span>
        {/if}
      </div>
    </div>
  </div>
</button>

{#if expanded}
  <div class="task-list">
    {#each group.tasks.filter(task => task && task.job_id) as task (task.job_id)}
      <button
        class="task-item"
        onclick={(e) => {
          e.stopPropagation();
          selectTask(task.job_id);
        }}
      >
        <div class="task-status-dot" style="background-color: {task.state ? jobUtils.getStateColor(task.state) : '#d1d5db'}"></div>
        <span class="task-id">#{task.array_task_id || task.job_id.split('_').pop()}</span>
        <span class="task-state">{task.state || 'Unknown'}</span>
        {#if task.runtime}
          <span class="task-runtime">{task.runtime}</span>
        {/if}
        {#if task.node_list}
          <span class="task-node" title={task.node_list}>{task.node_list}</span>
        {/if}
      </button>
    {/each}
  </div>
{/if}

<style>
  /* Main array card - matches job-item style */
  .array-job-card {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    width: 100%;
    padding: 0.75rem;
    background: rgb(243 244 246); /* gray-100 for light mode */
    border: 1px solid var(--border);
    border-radius: 0.875rem;
    cursor: pointer;
    text-align: left;
    transition: all 0.25s ease;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.08), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
    position: relative;
    margin-bottom: 0.5rem;
  }

  /* Dark mode override with high specificity to beat global.css */
  :global(.dark) .array-job-card {
    background: #262626 !important; /* gray-100 dark - lighter than sidebar #1a1a1a */
  }

  .array-job-card:hover {
    background: rgb(229 231 235); /* gray-200 for light mode */
    border-color: var(--muted);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    transform: translateY(-1px);
  }

  :global(.dark) .array-job-card:hover {
    background: #333333 !important; /* gray-200 dark - lighter on hover */
  }

  .job-status {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 4px;
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.8);
  }

  .expand-icon {
    color: var(--muted-foreground);
    display: flex;
    align-items: center;
    flex-shrink: 0;
    margin-top: 2px;
  }

  .job-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .job-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
  }

  .job-id {
    font-size: 1rem;
    font-weight: 700;
    color: var(--foreground);
  }

  .array-badge {
    font-size: 0.55rem;
    font-weight: 700;
    color: var(--accent);
    background: rgba(59, 130, 246, 0.15);
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    border: 1px solid var(--accent);
    letter-spacing: 0.05em;
  }

  .job-content {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .job-name {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--foreground);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .job-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
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

  .task-counts {
    display: flex;
    gap: 0.375rem;
    align-items: center;
  }

  .count {
    display: inline-flex;
    align-items: center;
    gap: 0.125rem;
    font-size: 0.625rem;
    font-weight: 600;
    padding: 0.125rem 0.25rem;
    border-radius: 0.25rem;
  }

  .count-running {
    background: rgba(16, 185, 129, 0.15);
    color: #10b981;
  }

  .count-pending {
    background: rgba(245, 158, 11, 0.15);
    color: #f59e0b;
  }

  .count-completed {
    background: rgba(139, 92, 246, 0.15);
    color: #a78bfa;
  }

  .count-failed {
    background: rgba(239, 68, 68, 0.15);
    color: #ef4444;
  }

  /* Expanded task list */
  .task-list {
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
    padding-left: 2rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .task-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem 0.5rem;
    background: rgb(229 231 235); /* gray-200 for light mode */
    border: 1px solid var(--border);
    border-radius: 0.375rem;
    cursor: pointer;
    text-align: left;
    transition: all 0.15s ease;
    font-size: 0.75rem;
  }

  :global(.dark) .task-item {
    background: #333333 !important; /* gray-200 dark */
  }

  .task-item:hover {
    background: rgb(209 213 219); /* gray-300 for light mode */
    border-color: var(--accent);
  }

  :global(.dark) .task-item:hover {
    background: #404040 !important; /* gray-300 dark */
  }

  .task-status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .task-id {
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 0.7rem;
    color: var(--muted-foreground);
    font-weight: 600;
    min-width: 2rem;
  }

  .task-state {
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--muted-foreground);
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .task-runtime {
    font-size: 0.65rem;
    color: var(--muted-foreground);
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    margin-left: auto;
  }

  .task-node {
    font-size: 0.65rem;
    color: var(--muted-foreground);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 8rem;
  }

  @media (max-width: 640px) {
    .task-node {
      display: none;
    }
  }
</style>