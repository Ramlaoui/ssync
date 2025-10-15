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

<div class="array-job-card">
  <button
    class="array-header"
    onclick={toggleExpanded}
    style="border-left-color: {jobUtils.getStateColor(groupState)}"
  >
    <div class="header-content">
      <div class="expand-icon">
        {#if expanded}
          <ChevronDown size={20} />
        {:else}
          <ChevronRight size={20} />
        {/if}
      </div>

      <div class="job-info">
        <span class="array-id">{group.array_job_id}</span>
        <span class="job-name">{group.job_name}</span>
      </div>

      <div class="task-summary">
        <div class="summary-badges">
          {#if group.running_count > 0}
            <span class="badge badge-running">
              <Zap size={14} />
              {group.running_count}
            </span>
          {/if}
          {#if group.pending_count > 0}
            <span class="badge badge-pending">
              <Clock size={14} />
              {group.pending_count}
            </span>
          {/if}
          {#if group.completed_count > 0}
            <span class="badge badge-completed">
              <CheckCircle size={14} />
              {group.completed_count}
            </span>
          {/if}
          {#if group.failed_count > 0}
            <span class="badge badge-failed">
              <AlertCircle size={14} />
              {group.failed_count}
            </span>
          {/if}
          {#if group.cancelled_count > 0}
            <span class="badge badge-cancelled">
              <XCircle size={14} />
              {group.cancelled_count}
            </span>
          {/if}
        </div>
        <span class="total-tasks">{group.total_tasks} tasks</span>
      </div>
    </div>
  </button>

  {#if expanded}
    <div class="task-list">
      {#each group.tasks.filter(task => task && task.job_id) as task (task.job_id)}
        <button
          class="task-item"
          onclick={() => selectTask(task.job_id)}
          style="border-left-color: {task.state ? jobUtils.getStateColor(task.state) : '#d1d5db'}"
        >
          <span class="task-id">#{task.array_task_id || task.job_id.split('_').pop()}</span>
          <span class="task-state state-{task.state ? task.state.toLowerCase() : 'unknown'}">{task.state || 'Unknown'}</span>
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
</div>

<style>
  .array-job-card {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 8px;
  }

  .array-header {
    width: 100%;
    padding: 12px;
    background: white;
    border: none;
    border-left: 4px solid transparent;
    cursor: pointer;
    text-align: left;
    transition: background-color 0.2s;
  }

  .array-header:hover {
    background: #f9fafb;
  }

  .header-content {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .expand-icon {
    color: #6b7280;
    display: flex;
    align-items: center;
  }

  .job-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .array-id {
    font-weight: 600;
    font-size: 14px;
    color: #111827;
  }

  .job-name {
    font-size: 12px;
    color: #6b7280;
  }

  .task-summary {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .summary-badges {
    display: flex;
    gap: 8px;
  }

  .badge {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    padding: 2px 6px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
  }

  .badge-running {
    background: #fef3c7;
    color: #92400e;
  }

  .badge-pending {
    background: #e0e7ff;
    color: #3730a3;
  }

  .badge-completed {
    background: #d1fae5;
    color: #065f46;
  }

  .badge-failed {
    background: #fee2e2;
    color: #991b1b;
  }

  .badge-cancelled {
    background: #f3f4f6;
    color: #4b5563;
  }

  .total-tasks {
    font-size: 12px;
    color: #9ca3af;
  }

  .task-list {
    border-top: 1px solid #e5e7eb;
    max-height: 400px;
    overflow-y: auto;
  }

  .task-item {
    width: 100%;
    padding: 6px 8px 6px 32px;
    background: white;
    border: none;
    border-left: 3px solid transparent;
    border-bottom: 1px solid #f3f4f6;
    cursor: pointer;
    text-align: left;
    display: flex;
    align-items: center;
    gap: 8px;
    transition: background-color 0.2s;
  }

  .task-item:hover {
    background: #f9fafb;
  }

  .task-item:last-child {
    border-bottom: none;
  }

  .task-id {
    font-family: 'Courier New', monospace;
    font-size: 11px;
    color: #6b7280;
    min-width: 32px;
    font-weight: 600;
  }

  .task-state {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
  }

  .state-pd {
    background: #e0e7ff;
    color: #3730a3;
  }

  .state-r {
    background: #fef3c7;
    color: #92400e;
  }

  .state-cd {
    background: #d1fae5;
    color: #065f46;
  }

  .state-f {
    background: #fee2e2;
    color: #991b1b;
  }

  .state-ca {
    background: #f3f4f6;
    color: #4b5563;
  }

  .task-runtime {
    font-size: 11px;
    color: #6b7280;
  }

  .task-node {
    font-size: 11px;
    color: #6b7280;
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  @media (max-width: 640px) {
    .task-node {
      display: none;
    }
  }
</style>