<script lang="ts">
  import { onMount } from 'svelte';
  import { Eye, ChevronRight, Copy, Terminal } from 'lucide-svelte';
  import type { JobInfo } from '../../types/api';
  import { api } from '../../services/api';
  import { watchers, jobWatchersErrors, jobWatchersLoading, getWatcherJobKey } from '../../stores/watchers';
  import { compactDuration, durationSeconds, jobFacts, jobStatus, jobValue, relativeTime, jobDate, type JobFact } from '../../lib/jobsPresentation';
  import { safeGetItem, safeSetItem } from '../../lib/safeStorage';
  let { job, onwatchers, oncopy, onoutput = () => { } }: {
    job: JobInfo;
    onwatchers: () => void;
    oncopy: (text: string) => void;
    onoutput?: () => void;
  } = $props();
  const status = $derived(jobStatus(job.state));
  const details = $derived(jobFacts(job));
  const jobWatchers = $derived($watchers.filter(w => w.job_id === job.job_id && w.hostname === job.hostname));
  const watcherKey = $derived(getWatcherJobKey(job.job_id, job.hostname));
  const elapsed = $derived(durationSeconds(job.runtime));
  const limit = $derived(durationSeconds(job.time_limit));
  const percentage = $derived(limit && elapsed !== null ? Math.min(100, Math.round(elapsed / limit * 100)) : null);
  const exitCode = $derived(jobValue(job.exit_code));
  const succeeded = $derived(exitCode ? /^0(:0)?$/.test(exitCode) : job.state === 'CD');
  const collapsedKey = 'ssync-job-overview-collapsed';
  let collapsed = $state<Set<string>>(new Set(['usage', 'details']));
  let tail = $state<string[]>([]);
  let tailState = $state<'loading' | 'ready' | 'empty' | 'error'>('loading');

  onMount(() => {
    try {
      const saved = safeGetItem(collapsedKey);
      if (saved) collapsed = new Set(JSON.parse(saved));
    } catch { /* keep defaults */ }
  });
  function toggle(id: string, open: boolean) {
    const next = new Set(collapsed);
    if (open) next.delete(id); else next.add(id);
    collapsed = next;
    safeSetItem(collapsedKey, JSON.stringify([...next]));
  }
  // A short stdout tail so progress is visible without opening the output tab.
  $effect(() => {
    const id = job.job_id, host = job.hostname, pending = status.category === 'pending';
    if (pending) { tailState = 'empty'; return; }
    let cancelled = false;
    tailState = 'loading';
    api.get<{ stdout?: string | null }>(`/api/jobs/${encodeURIComponent(id)}/output`, { params: { host, output_type: 'stdout', lines: 8 } })
      .then(response => {
        if (cancelled) return;
        const lines = (response.data?.stdout ?? '').replace(/\s+$/, '').split('\n');
        tail = lines.filter((line, index) => line || index < lines.length - 1).slice(-8);
        tailState = tail.join('').trim() ? 'ready' : 'empty';
      })
      .catch(() => { if (!cancelled) tailState = 'error'; });
    return () => { cancelled = true; };
  });
</script>

{#snippet factList(facts: JobFact[])}
  <dl class="overview-facts">
    {#each facts as fact (fact.label)}
      <div class:stacked={fact.mono||fact.value.length>32}>
        <dt>{fact.label}</dt>
        <dd class:mono={fact.mono}>
          {fact.value}
          {#if fact.mono}
            <button class="overview-copy" aria-label={`Copy ${fact.label}`} title={`Copy ${fact.label}`} onclick={()=>oncopy(fact.value)}><Copy size={13}/></button>
          {/if}
        </dd>
      </div>
    {/each}
  </dl>
{/snippet}

{#snippet section(id: string, title: string, facts: JobFact[])}
  {#if facts.length}
    <details class="overview-section" open={!collapsed.has(id)} ontoggle={event=>toggle(id,(event.currentTarget as HTMLDetailsElement).open)}>
      <summary><ChevronRight size={14}/>{title}</summary>
      {@render factList(facts)}
    </details>
  {/if}
{/snippet}

<div class="job-overview">
  <section class="overview-summary tone-{status.tone}">
    {#if status.category==='pending'}
      <strong class="overview-headline">{jobValue(job.reason)??'Waiting for resources'}</strong>
      <p>
        {#if job.priority_rank}
          {job.priority_jobs_ahead?.toLocaleString()??job.priority_rank-1} jobs ahead · position {job.priority_rank.toLocaleString()}{job.priority_queue_size?` of ${job.priority_queue_size.toLocaleString()}`:''}
        {:else if jobDate(job.submit_time)}
          Queued {relativeTime(job.submit_time).toLowerCase()}
        {:else}
          Waiting for the scheduler
        {/if}
      </p>
    {:else}
      <div class="overview-time">
        <strong>{job.runtime?compactDuration(job.runtime):'—'}</strong>
        {#if job.time_limit}<span>of {compactDuration(job.time_limit)}</span>{/if}
        {#if status.category==='historical'&&exitCode}
          <span class="overview-exit" class:failed={!succeeded}>Exit {exitCode}</span>
        {/if}
      </div>
      {#if percentage!==null&&status.category==='active'}
        <div class="overview-meter" class:late={percentage>=90} role="meter" aria-label="Time limit used" aria-valuemin="0" aria-valuemax="100" aria-valuenow={percentage}>
          <span style={`width:${Math.max(percentage,1)}%`}></span>
        </div>
      {/if}
      <p>
        {#if status.category==='active'}
          {percentage!==null?`${percentage}% of the time limit used`:'Running'}{jobDate(job.start_time)?` · started ${relativeTime(job.start_time).toLowerCase()}`:''}
        {:else}
          {status.label}{jobDate(job.end_time)?` ${relativeTime(job.end_time).toLowerCase()}`:''}
        {/if}
      </p>
    {/if}
  </section>

  {#if status.category!=='pending'}
    <button class="overview-output" onclick={onoutput} aria-label="Open output">
      <span class="overview-output-title"><Terminal size={14}/> Latest output <ChevronRight size={14}/></span>
      {#if tailState==='ready'}
        <pre>{tail.join('\n')}</pre>
      {:else}
        <span class="overview-muted">{tailState==='loading'?'Loading output…':tailState==='error'?'Output unavailable':'No output yet'}</span>
      {/if}
    </button>
  {/if}

  <section class="overview-section overview-watchers">
    <div class="overview-heading">
      <span>Watchers</span>
      <button class="relay-text-button" onclick={onwatchers}>Manage</button>
    </div>
    {#each jobWatchers as watcher}
      <button class="overview-watcher" onclick={onwatchers}>
        <Eye size={15}/>
        <span>
          <strong>{watcher.name}</strong>
          <small>{watcher.state} · {watcher.trigger_count} triggers</small>
        </span>
        <ChevronRight size={14}/>
      </button>
    {:else}
      <p class="overview-muted">{$jobWatchersLoading[watcherKey]?'Loading watchers…':$jobWatchersErrors[watcherKey]?'Watchers could not be loaded.':'No watchers attached.'}</p>
    {/each}
  </section>

  {@render section('timeline', 'Timeline', details.timeline)}
  {@render section('queue', 'Queue', details.queue)}
  {@render section('resources', 'Resources', details.resources)}
  {@render section('usage', 'Usage', details.usage)}
  {@render section('details', 'Details', details.scheduling)}
</div>

<style>
  .job-overview {
    container-type: inline-size;
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 18px 20px 24px;
  }

  .overview-summary {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 14px 16px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--card);
  }

  .overview-summary p {
    margin: 0;
    font-size: .8125rem;
    color: var(--muted-foreground);
  }

  .overview-headline {
    font-size: 1.0625rem;
    font-weight: 600;
    color: var(--warning);
  }

  .overview-time {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
  }

  .overview-time strong {
    font-size: 1.625rem;
    font-weight: 600;
    letter-spacing: -.02em;
    font-variant-numeric: tabular-nums;
  }

  .overview-time>span {
    color: var(--muted-foreground);
    font-size: .875rem;
  }

  .overview-time .overview-exit {
    margin-left: auto;
    font-size: .8125rem;
    font-weight: 600;
    color: var(--success);
    font-variant-numeric: tabular-nums;
  }

  .overview-time .overview-exit.failed {
    color: var(--error);
  }

  .overview-meter {
    height: 5px;
    border-radius: 5px;
    background: var(--secondary);
    overflow: hidden;
  }

  .overview-meter>span {
    display: block;
    height: 100%;
    background: var(--accent);
    border-radius: inherit;
  }

  .overview-meter.late>span {
    background: var(--warning);
  }

  .overview-output {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 100%;
    padding: 12px 14px;
    text-align: left;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--card);
    color: inherit;
    transition: border-color var(--motion-state);
  }

  .overview-output:hover {
    border-color: var(--accent);
  }

  .overview-output-title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: .75rem;
    font-weight: 600;
    color: var(--muted-foreground);
    text-transform: uppercase;
    letter-spacing: .03em;
  }

  .overview-output-title>:global(svg:last-child) {
    margin-left: auto;
  }

  .overview-output pre {
    margin: 0;
    padding: 10px 12px;
    border-radius: 8px;
    background: var(--secondary);
    font-size: .75rem;
    line-height: 1.5;
    white-space: pre;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--foreground);
  }

  .overview-section {
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--card);
    padding: 4px 14px;
  }

  .overview-section summary,.overview-heading {
    display: flex;
    align-items: center;
    gap: 6px;
    min-height: 38px;
    font-size: .75rem;
    font-weight: 600;
    color: var(--muted-foreground);
    text-transform: uppercase;
    letter-spacing: .03em;
    cursor: pointer;
    list-style: none;
  }

  .overview-section summary::-webkit-details-marker {
    display: none;
  }

  .overview-section summary :global(svg) {
    transition: transform var(--motion-state);
  }

  .overview-section[open] summary :global(svg) {
    transform: rotate(90deg);
  }

  .overview-heading {
    justify-content: space-between;
    cursor: default;
  }

  .overview-heading .relay-text-button {
    text-transform: none;
    letter-spacing: 0;
  }

  .overview-facts {
    margin: 0 0 8px;
  }

  .overview-facts>div {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    padding: 7px 0;
    border-top: 1px solid var(--border-soft);
    font-size: .8125rem;
  }

  .overview-facts>div.stacked {
    flex-direction: column;
    gap: 3px;
  }

  .overview-facts dt {
    color: var(--muted-foreground);
    flex-shrink: 0;
  }

  .overview-facts dd {
    margin: 0;
    text-align: right;
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
  }

  .overview-facts .stacked dd {
    text-align: left;
    display: flex;
    align-items: flex-start;
    gap: 6px;
  }

  .overview-facts dd.mono {
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: .75rem;
  }

  .overview-copy {
    flex-shrink: 0;
    margin-left: auto;
    padding: 2px;
    border: 0;
    background: none;
    color: var(--muted-foreground);
    border-radius: 4px;
  }

  .overview-copy:hover {
    color: var(--accent);
  }

  .overview-watchers {
    padding-bottom: 8px;
  }

  .overview-watcher {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 7px 4px;
    border: 0;
    border-top: 1px solid var(--border-soft);
    background: none;
    text-align: left;
    color: var(--accent);
  }

  .overview-watcher:hover {
    background: var(--hover);
  }

  .overview-watcher>span {
    flex: 1;
    min-width: 0;
  }

  .overview-watcher strong {
    display: block;
    color: var(--foreground);
    font-size: .8125rem;
    font-weight: 550;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .overview-watcher small {
    color: var(--muted-foreground);
    font-size: .75rem;
  }

  .overview-muted {
    margin: 0 0 6px;
    color: var(--muted-foreground);
    font-size: .8125rem;
  }

  /* Maximized: summary, output and watchers on the left; facts on the right. */
  @container (min-width: 900px) {
    .job-overview {
      display: grid;
      grid-template-columns: minmax(0,1.2fr) minmax(0,1fr);
      grid-auto-flow: dense;
      align-items: start;
      padding: 22px 24px 28px;
    }
    .overview-summary,.overview-output,.overview-watchers {
      grid-column: 1;
    }
    .job-overview>details {
      grid-column: 2;
    }
  }
</style>
