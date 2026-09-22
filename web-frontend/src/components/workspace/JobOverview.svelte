<script lang="ts">
  import { Clock3, Cpu, Eye, ChevronRight, Copy, TriangleAlert } from 'lucide-svelte';
  import type { JobInfo } from '../../types/api';
  import JobDetailsView from '../JobDetailsView.svelte';
  import { watchers, jobWatchersErrors, jobWatchersLoading, getWatcherJobKey } from '../../stores/watchers';
  import { durationSeconds, gpuCount, relativeTime } from '../../lib/jobsPresentation';
  import { jobUtils } from '../../lib/jobUtils';
  let { job, onwatchers, oncopy }: {
    job: JobInfo;
    onwatchers: () => void;
    oncopy: (text: string) => void;
  } = $props();
  const jobWatchers = $derived($watchers.filter(w => w.job_id === job.job_id && w.hostname === job.hostname));
  const watcherKey = $derived(getWatcherJobKey(job.job_id, job.hostname));
  const elapsed = $derived(durationSeconds(job.runtime));
  const limit = $derived(durationSeconds(job.time_limit));
  const percentage = $derived(limit && elapsed !== null ? Math.min(100, Math.round(elapsed / limit * 100)) : null);
  const gpus = $derived(gpuCount(job));
</script>

<div class="job-overview">
  {#if job.reason&&job.reason!=='None'&&job.reason!=='(null)'}
    <div class="overview-notice" class:failed={job.state==='F'}>
      <TriangleAlert size={18}/>
      <div>
        <strong>{job.reason}</strong>
        {#if job.priority_rank}
          <p>Position {job.priority_rank} in queue{job.priority_jobs_ahead!==null&&job.priority_jobs_ahead!==undefined?` · ${job.priority_jobs_ahead} jobs ahead`:''}</p>
        {/if}
      </div>
    </div>
  {/if}
  <section class="overview-section">
    <div class="overview-label">
      Time allocation
      <Clock3 size={16}/>
    </div>
    <div class="overview-time">
      <strong>{job.runtime?jobUtils.formatDuration(job.runtime):'—'}</strong>
      <span>of {job.time_limit?jobUtils.formatDuration(job.time_limit):'unknown limit'}</span>
    </div>
    {#if percentage!==null}
      <div class="overview-meter" role="meter" aria-label="Time allocation used" aria-valuemin="0" aria-valuemax="100" aria-valuenow={percentage}>
        <span style={`width:${percentage}%`}></span>
      </div>
    {/if}
    <div class="overview-time-meta">
      <span>{job.start_time?`Started ${relativeTime(job.start_time)}`:`Submitted ${relativeTime(job.submit_time)}`}</span>
      {#if percentage!==null}
        <span>{percentage}% used</span>
      {/if}
    </div>
  </section>
  <section class="overview-section">
    <div class="overview-label">
      Resources
      <Cpu size={16}/>
    </div>
    <div class="overview-resources">
      <div>
        <strong>{gpus??'—'}</strong>
        <span>GPUs</span>
      </div>
      <div>
        <strong>{job.cpus||'—'}</strong>
        <span>CPUs</span>
      </div>
      <div>
        <strong>{job.memory||'—'}</strong>
        <span>Memory</span>
      </div>
    </div>
    <dl>
      <div>
        <dt>Partition</dt>
        <dd>{job.partition||'—'}</dd>
      </div>
      {#if job.nodes}
        <div>
          <dt>Nodes</dt>
          <dd>{job.nodes}</dd>
        </div>
      {/if}
      {#if job.node_list}
        <div>
          <dt>Node list</dt>
          <dd>{job.node_list}</dd>
        </div>
      {/if}
    </dl>
  </section>
  <section class="overview-section">
    <div class="overview-label">
      Watchers
      <button class="relay-text-button" onclick={onwatchers}>Manage</button>
    </div>
    {#each jobWatchers as watcher}
      <button class="overview-watcher" onclick={onwatchers}>
        <span class="overview-watcher-icon">
          <Eye size={18}/>
        </span>
        <span>
          <strong>{watcher.name}</strong>
          <small>{watcher.state} · {watcher.trigger_count} events</small>
        </span>
        <ChevronRight size={15}/>
      </button>
    {:else}
      <p class="overview-muted">{$jobWatchersLoading[watcherKey]?'Loading watchers…':$jobWatchersErrors[watcherKey]?'Watchers could not be loaded.':'No watchers attached.'}</p>
    {/each}
  </section>
  {#if job.work_dir}
    <section class="overview-section">
      <div class="overview-label">Working directory</div>
      <button class="overview-path" title="Copy working directory" onclick={()=>oncopy(job.work_dir!)}>
        <code>{job.work_dir}</code>
        <Copy size={15}/>
      </button>
      {#if job.account}
        <dl>
          <div>
            <dt>Account</dt>
            <dd>{job.account}</dd>
          </div>
        </dl>
      {/if}
    </section>
  {/if}
  <details class="overview-advanced">
    <summary>All job details</summary>
    <JobDetailsView {job}/>
  </details>
</div>

<style>
  .job-overview {
    display: grid;
    grid-template-columns: repeat(2,minmax(0,1fr));
    gap: 24px;
    padding: 24px;
    align-content: start;
  }

  .overview-section {
    border: 1px solid var(--border-soft);
    background: var(--background);
    border-radius: 12px;
    padding: 24px;
    min-width: 0;
  }

  .overview-label {
    display: flex;
    align-items: center;
    justify-content: space-between;
    color: var(--muted-foreground);
    font-size: .875rem;
    margin-bottom: 20px;
  }

  .overview-label>:global(svg) {
    color: var(--muted-foreground);
  }

  .overview-time {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
  }

  .overview-time strong {
    font-size: 1.75rem;
    font-weight: 550;
    letter-spacing: -.03em;
    font-variant-numeric: tabular-nums;
  }

  .overview-time>span {
    font-size: .875rem;
    color: var(--muted-foreground);
  }

  .overview-meter {
    height: 5px;
    border-radius: 5px;
    background: var(--secondary);
    margin: 16px 0 10px;
    overflow: hidden;
  }

  .overview-meter>span {
    display: block;
    height: 100%;
    background: var(--accent);
    border-radius: 5px;
  }

  .overview-time-meta {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    font-size: .75rem;
    color: var(--muted-foreground);
    margin-top: 12px;
  }

  .overview-resources {
    display: grid;
    grid-template-columns: repeat(3,minmax(0,1fr));
    margin-bottom: 23px;
  }

  .overview-resources>div {
    padding: 0 16px;
    border-right: 1px solid var(--border);
  }

  .overview-resources>div:first-child {
    padding-left: 0;
  }

  .overview-resources>div:last-child {
    border: 0;
    padding-right: 0;
  }

  .overview-resources strong {
    display: block;
    font-size: 1.5rem;
    font-weight: 550;
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
  }

  .overview-resources span {
    display: block;
    color: var(--muted-foreground);
    font-size: .8125rem;
    margin-top: 4px;
  }

  dl {
    display: flex;
    flex-direction: column;
    gap: 12px;
    font-size: .8125rem;
    margin: 15px 0 0;
  }

  dl>div {
    display: flex;
    justify-content: space-between;
    gap: 15px;
  }

  dt {
    color: var(--muted-foreground);
  }

  dd {
    margin: 0;
    overflow-wrap: anywhere;
    text-align: right;
  }

  .overview-notice {
    display: flex;
    gap: 12px;
    grid-column: 1/-1;
    padding: 16px;
    border-radius: 12px;
    background: var(--warning-bg);
    color: var(--warning);
    font-size: .875rem;
  }

  .overview-notice.failed {
    background: var(--error-bg);
    color: var(--error);
  }

  .overview-notice strong {
    font-weight: 550;
  }

  .overview-notice p {
    font-size: .8125rem;
    margin: 6px 0 0;
  }

  .overview-watcher {
    display: flex;
    gap: 10px;
    align-items: center;
    padding: 10px 8px;
    margin: 0 -8px;
    text-align: left;
    background: none;
    border: 0;
    border-radius: 10px;
    width: calc(100% + 16px);
  }

  .overview-watcher:hover,.overview-path:hover {
    background: var(--hover);
  }

  .overview-watcher-icon {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    background: var(--accent-soft);
    color: var(--accent);
    display: grid;
    place-items: center;
    flex-shrink: 0;
  }

  .overview-watcher strong {
    display: block;
    font-size: .875rem;
    font-weight: 500;
  }

  .overview-watcher small {
    display: block;
    font-size: .75rem;
    color: var(--muted-foreground);
    margin-top: 4px;
  }

  .overview-watcher>:global(svg) {
    margin-left: auto;
    color: var(--muted-foreground);
  }

  .overview-muted {
    color: var(--muted-foreground);
    font-size: .8125rem;
    margin: 0;
  }

  .overview-path {
    display: flex;
    align-items: center;
    gap: 10px;
    border: 0;
    padding: 8px;
    margin-left: -8px;
    border-radius: 8px;
    background: transparent;
    text-align: left;
    max-width: 100%;
    color: var(--muted-foreground);
  }

  .overview-path code {
    font-size: .8125rem;
    overflow-wrap: anywhere;
  }

  .overview-path :global(svg) {
    flex-shrink: 0;
  }

  .overview-advanced {
    grid-column: 1/-1;
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }

  .overview-advanced summary {
    padding: 18px 24px;
    cursor: pointer;
    font-size: .875rem;
    color: var(--muted-foreground);
  }

  .overview-advanced summary:hover {
    color: var(--accent);
  }

  :global(.job-panel.embedded) .job-overview {
    display: block;
    padding: 0 20px;
  }

  :global(.job-panel.embedded) .overview-section {
    padding: 22px 0;
    border: 0;
    border-bottom: 1px solid var(--border-soft);
    border-radius: 0;
    background: transparent;
  }

  :global(.job-panel.embedded) .overview-notice {
    margin: 18px 0;
  }

  :global(.job-panel.embedded) .overview-advanced {
    margin: 18px 0;
  }

  :global(.job-panel.embedded) .overview-resources strong {
    font-size: 1.3rem;
  }

  @media (max-width:850px) {
    .job-overview {
      grid-template-columns: 1fr;
      padding: 18px;
      gap: 18px;
    }
    .overview-section {
      padding: 20px;
    }
  }
</style>
