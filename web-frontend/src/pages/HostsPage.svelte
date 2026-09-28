<script module lang="ts">
  import { getArrayGroupTasks } from '../lib/arrayJobs';
  import { matchesJobView } from '../lib/jobsPresentation';
  import type { ArrayJobGroup, JobInfo, PartitionResources } from '../types/api';

  export const PARTITION_PREVIEW = 6;

  // The server redacts filesystem paths as bracketed tokens such as "[CONFIGURED]".
  export function displayPath(value: string | null | undefined): string | null {
    const path = value?.trim();
    return path && !/^\[[A-Z _-]+\]$/.test(path) ? path : null;
  }

  export function formatCount(value: number | null | undefined, locale?: string): string {
    return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString(locale) : '—';
  }

  export function hasGpus(partition: PartitionResources): boolean {
    return (partition.gpus_total ?? 0) > 0;
  }

  // Partitions with nodes first, keeping the scheduler's order within each group.
  export function orderPartitions(partitions: PartitionResources[]): PartitionResources[] {
    return [...partitions.filter(item => item.nodes_total > 0), ...partitions.filter(item => item.nodes_total <= 0)];
  }

  // Same job set as the Jobs page: listed jobs plus tasks held in server-side array groups.
  export function hostJobCounts(jobs: JobInfo[], groups: ArrayJobGroup[], hostname: string): { running: number; pending: number } {
    const seen = new Set<string>();
    let running = 0;
    let pending = 0;
    for (const job of [...jobs, ...groups.flatMap(getArrayGroupTasks)]) {
      const key = `${job.hostname}:${job.job_id}`;
      if (job.hostname !== hostname || seen.has(key))
        continue;
      seen.add(key);
      if (matchesJobView(job, 'running'))
        running++;
      else if (matchesJobView(job, 'pending'))
        pending++;
    }
    return { running, pending };
  }

  export function share(part: number | null | undefined, total: number | null | undefined): number {
    return total && part ? Math.min(100, Math.max(0, (part / total) * 100)) : 0;
  }
</script>

<script lang="ts">
  import { onMount } from 'svelte';
  import { push } from 'svelte-spa-router';
  import { Server, RefreshCw, ArrowRight, TriangleAlert, ChevronRight, Info } from 'lucide-svelte';
  import IconButton from '../components/workspace/IconButton.svelte';
  import { api } from '../services/api';
  import { jobStateManager } from '../lib/JobStateManager';
  import { relativeTime } from '../lib/jobsPresentation';
  import { setJobView } from '../stores/workspace';
  import type { HostInfo, PartitionStatusResponse } from '../types/api';
  let hosts = $state<HostInfo[]>([]);
  let snapshots = $state<PartitionStatusResponse[]>([]);
  let loading = $state(true);
  let error = $state('');
  let expanded = $state<Record<string, boolean>>({});
  const jobs = jobStateManager.getAllJobs();
  const groups = jobStateManager.getArrayJobGroups();
  const hostStates = jobStateManager.getHostStates();
  async function load(force = false) {
    loading = true;
    error = '';
    const results = await Promise.allSettled([api.get<HostInfo[]>('/api/hosts'), api.get<PartitionStatusResponse[]>('/api/partitions', { params: force ? { force_refresh: true } : {} })]);
    if (results[0].status === 'fulfilled')
      hosts = results[0].value.data;
    else
      error = 'Could not load configured hosts.';
    if (results[1].status === 'fulfilled')
      snapshots = results[1].value.data;
    else
      error += (error ? ' ' : '') + 'Capacity data is unavailable.';
    loading = false;
  }
  function openJobs(host: string) { setJobView('all', host); void push('/'); }
  onMount(() => { void load(); });
</script>

<div class="relay-page hosts-page">
  <div class="relay-heading">
    <div>
      <h1>Hosts</h1>
      <p>{hosts.length} configured</p>
    </div>
    <IconButton label="Refresh hosts" disabled={loading} onclick={()=>void load(true)}>
      <RefreshCw size={18} class={loading?'animate-spin':''}/>
    </IconButton>
  </div>
  {#if error}
    <div class="relay-banner error" role="alert">
      <TriangleAlert size={17}/>
      <span>{error}</span>
      <button class="relay-text-button" onclick={()=>void load(true)}>Retry</button>
    </div>
  {/if}
  {#if hosts.length}
    <p class="hosts-note">
      <Info size={14}/>
      <span>Allocated is what Slurm has reserved, not measured utilization. Partitions can share nodes, so totals may overlap.</span>
    </p>
  {/if}
  <div class="host-grid">
    {#each hosts as host (host.hostname)}
      {@const snapshot=snapshots.find(item=>item.hostname===host.hostname)}
      {@const state=$hostStates.get(host.hostname)}
      {@const unavailable=Boolean(snapshot?.error||state?.status==='error')}
      {@const counts=hostJobCounts($jobs,$groups,host.hostname)}
      {@const paths=[['Work', displayPath(host.work_dir)], ['Scratch', displayPath(host.scratch_dir)]].filter(([,path])=>path)}
      {@const partitions=orderPartitions(snapshot?.partitions??[])}
      {@const showGpus=partitions.some(hasGpus)}
      {@const open=Boolean(expanded[host.hostname])}
      {@const visible=open?partitions:partitions.slice(0,PARTITION_PREVIEW)}
      <section class="host-card" aria-labelledby={`host-${host.hostname}`}>
        <header class="host-header">
          <span class="host-icon"><Server size={16}/></span>
          <div class="host-title">
            <div class="host-name">
              <h2 id={`host-${host.hostname}`}>{host.hostname}</h2>
              <span class="host-health" class:unavailable={unavailable||Boolean(snapshot?.stale)}>
                <span class="relay-dot" class:connected={!unavailable&&!snapshot?.stale&&Boolean(snapshot)}></span>
                {unavailable?'Unavailable':snapshot?.stale?'Stale':snapshot?'Available':loading?'Loading':'Unknown'}
              </span>
            </div>
            <p class="host-meta">
              <span><strong>{formatCount(counts.running)}</strong> running</span>
              <span aria-hidden="true">·</span>
              <span><strong>{formatCount(counts.pending)}</strong> pending</span>
              {#if snapshot}
                <span aria-hidden="true">·</span>
                <span title="Last capacity update">{snapshot.stale?'Cached':'Updated'} {relativeTime(snapshot.updated_at||snapshot.query_time).toLowerCase()}</span>
              {/if}
            </p>
          </div>
          <button class="relay-text-button host-jobs-link" onclick={()=>openJobs(host.hostname)}>
            View jobs
            <ArrowRight size={14}/>
          </button>
        </header>
        {#if snapshot?.error}
          <p class="host-error">{snapshot.error}</p>
        {/if}
        {#if paths.length}
          <dl class="host-paths">
            {#each paths as [label, path] (label)}
              <div>
                <dt>{label}</dt>
                <dd class="mono" title={path}>{path}</dd>
              </div>
            {/each}
          </dl>
        {/if}
        {#if partitions.length}
          <table class="partition-table" class:with-gpus={showGpus}>
            <thead>
              <tr>
                <th scope="col">Partition</th>
                <th scope="col">CPUs<span class="wide-only">&nbsp;allocated</span></th>
                {#if showGpus}<th scope="col">GPUs<span class="wide-only">&nbsp;allocated</span></th>{/if}
                <th scope="col" class="numeric">Nodes</th>
              </tr>
            </thead>
            <tbody>
              {#each visible as partition (partition.partition)}
                {@const up=(partition.availability||'').toLowerCase()==='up'}
                <tr class:empty={partition.nodes_total<=0}>
                  <th scope="row">
                    <span class="partition-name">
                      <span class="partition-dot" class:up title={partition.availability||'Unknown'}></span>
                      <span class="partition-label" title={partition.partition}>{partition.partition}</span>
                      {#if !up}<small class="partition-state">{partition.availability||'unknown'}</small>{/if}
                    </span>
                  </th>
                  <td>
                    <span class="resource">
                      <span class="bar" role="img" aria-label={`${formatCount(partition.cpus_alloc)} of ${formatCount(partition.cpus_total)} CPUs allocated`}>
                        <span class="bar-alloc" style:width={`${share(partition.cpus_alloc,partition.cpus_total)}%`}></span>
                        <span class="bar-other" style:width={`${share(partition.cpus_other,partition.cpus_total)}%`}></span>
                      </span>
                      <span class="resource-text"><strong>{formatCount(partition.cpus_idle)}</strong> idle of {formatCount(partition.cpus_total)}</span>
                    </span>
                  </td>
                  {#if showGpus}
                    <td>
                      {#if hasGpus(partition)}
                        <span class="resource">
                          {#if partition.gpus_used!==null}
                            <span class="bar" role="img" aria-label={`${formatCount(partition.gpus_used)} of ${formatCount(partition.gpus_total)} GPUs allocated`}>
                              <span class="bar-alloc" style:width={`${share(partition.gpus_used,partition.gpus_total)}%`}></span>
                            </span>
                          {/if}
                          <span class="resource-text">
                            {#if partition.gpus_idle!==null}
                              <strong>{formatCount(partition.gpus_idle)}</strong> idle of {formatCount(partition.gpus_total)}
                            {:else}
                              {formatCount(partition.gpus_total)} total
                            {/if}
                          </span>
                        </span>
                      {:else}
                        <span class="none" aria-label="No GPUs">—</span>
                      {/if}
                    </td>
                  {/if}
                  <td class="numeric">{formatCount(partition.nodes_total)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
          {#if partitions.length>PARTITION_PREVIEW}
            <button class="partition-toggle" aria-expanded={open} onclick={()=>expanded[host.hostname]=!open}>
              <ChevronRight size={14} class="partition-chevron"/>
              {open?'Show fewer':`Show all ${partitions.length} partitions`}
            </button>
          {/if}
        {:else}
          <p class="relay-empty-message host-empty">{loading?'Loading capacity…':'No partition data available.'}</p>
        {/if}
      </section>
    {/each}
  </div>
  {#if !hosts.length&&!loading}
    <div class="relay-empty">
      <Server size={26}/>
      <h2>No configured hosts</h2>
      <a href="#/settings" class="relay-button">Connection settings</a>
    </div>
  {/if}
</div>

<style>
  .hosts-page>.relay-banner {
    margin-bottom: 20px;
  }

  .hosts-note {
    display: flex;
    align-items: flex-start;
    gap: 7px;
    margin: -12px 0 18px;
    color: var(--muted-foreground);
    font-size: .8125rem;
    line-height: 1.4;
  }

  .hosts-note :global(svg) {
    flex-shrink: 0;
    margin-top: 2px;
  }

  .host-grid {
    display: grid;
    grid-template-columns: repeat(2,minmax(0,1fr));
    gap: 16px;
    align-items: start;
  }

  .host-card {
    padding: 16px 18px 12px;
    border: 1px solid var(--border);
    background: var(--card);
    border-radius: var(--radius-card);
    min-width: 0;
    transition: border-color var(--motion-state);
  }

  .host-card:hover {
    border-color: color-mix(in srgb,var(--accent) 40%,var(--border));
  }

  .host-header {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
  }

  .host-icon {
    display: grid;
    place-items: center;
    width: 32px;
    height: 32px;
    flex-shrink: 0;
    border-radius: 9px;
    color: var(--accent);
    background: var(--accent-soft);
  }

  .host-title {
    flex: 1;
    min-width: 0;
  }

  .host-name {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .host-name h2 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .host-health {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    flex-shrink: 0;
    color: var(--success);
    font-size: .75rem;
  }

  .host-health.unavailable,.host-error {
    color: var(--warning);
  }

  .host-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 2px 6px;
    margin: 2px 0 0;
    color: var(--muted-foreground);
    font-size: .8125rem;
    font-variant-numeric: tabular-nums;
  }

  .host-meta strong {
    color: var(--foreground);
    font-weight: 600;
  }

  .host-jobs-link {
    flex-shrink: 0;
    font-size: .8125rem;
  }

  .host-error {
    margin: 10px 0 0;
    font-size: .8125rem;
    overflow-wrap: anywhere;
  }

  .host-paths {
    display: grid;
    gap: 4px;
    margin: 10px 0 0;
    font-size: .75rem;
  }

  .host-paths div {
    display: flex;
    gap: 8px;
    min-width: 0;
  }

  .host-paths dt {
    flex: 0 0 52px;
    color: var(--muted-foreground);
  }

  .host-paths dd {
    margin: 0;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .partition-table {
    width: 100%;
    margin-top: 12px;
    border-collapse: collapse;
    table-layout: fixed;
    font-size: .8125rem;
    font-variant-numeric: tabular-nums;
  }

  .partition-table th:first-child {
    width: 34%;
  }

  .partition-table th:last-child {
    width: 58px;
  }

  .partition-table.with-gpus th:first-child {
    width: 28%;
  }

  .partition-table thead th {
    padding: 0 8px 6px 0;
    color: var(--muted-foreground);
    font-size: .6875rem;
    font-weight: 500;
    letter-spacing: .02em;
    text-align: left;
    text-transform: uppercase;
    border-bottom: 1px solid var(--border-soft);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .partition-table tbody th,.partition-table td {
    height: 38px;
    padding: 0 10px 0 0;
    border-bottom: 1px solid var(--border-soft);
    font-weight: 400;
    text-align: left;
    vertical-align: middle;
  }

  .partition-table tbody tr:last-child th,.partition-table tbody tr:last-child td {
    border-bottom: 0;
  }

  .partition-table .numeric {
    padding-right: 0;
    text-align: right;
  }

  .partition-table tr.empty {
    color: var(--muted-foreground);
  }

  .partition-name {
    display: flex;
    align-items: center;
    gap: 7px;
    min-width: 0;
  }

  .partition-label {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 500;
  }

  .partition-dot {
    width: 6px;
    height: 6px;
    flex-shrink: 0;
    border-radius: 50%;
    background: var(--warning);
  }

  .partition-dot.up {
    background: var(--success);
  }

  .partition-state {
    flex-shrink: 0;
    color: var(--warning);
    font-size: .6875rem;
  }

  .resource {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  .bar {
    display: flex;
    width: 100%;
    max-width: 180px;
    height: 4px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--secondary);
  }

  .bar-alloc {
    background: var(--accent);
  }

  .bar-other {
    background: color-mix(in srgb,var(--warning) 55%,var(--secondary));
  }

  .resource-text {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--muted-foreground);
    font-size: .75rem;
  }

  .resource-text strong {
    color: var(--foreground);
    font-weight: 550;
  }

  .none {
    color: var(--muted-foreground);
  }

  .partition-toggle {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-top: 6px;
    padding: 4px 0;
    border: 0;
    background: none;
    color: var(--accent);
    font-size: .8125rem;
  }

  .partition-toggle:hover {
    text-decoration: underline;
  }

  .partition-toggle :global(.partition-chevron) {
    transition: transform var(--motion-state);
    transform: rotate(90deg);
  }

  .partition-toggle[aria-expanded=true] :global(.partition-chevron) {
    transform: rotate(-90deg);
  }

  .host-empty {
    margin: 12px 0 4px;
  }

  @media (max-width:1100px) {
    .host-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width:600px) {
    .host-card {
      padding: 14px 14px 10px;
    }
    .host-header {
      flex-wrap: wrap;
      row-gap: 6px;
    }
    .host-jobs-link {
      margin-left: 44px;
    }
    .partition-table th:last-child {
      width: 44px;
    }
    .partition-table.with-gpus th:first-child {
      width: 30%;
    }
    .partition-table tbody th,.partition-table td {
      height: auto;
      min-height: 38px;
      padding-block: 7px;
    }
    .resource-text {
      white-space: normal;
      line-height: 1.3;
    }
    .wide-only {
      display: none;
    }
  }
</style>
