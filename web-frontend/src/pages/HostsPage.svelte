<script lang="ts">
  import { onMount } from 'svelte';
  import { push } from 'svelte-spa-router';
  import { Server, RefreshCw, ArrowRight, TriangleAlert } from 'lucide-svelte';
  import IconButton from '../components/workspace/IconButton.svelte';
  import { api } from '../services/api';
  import { jobStateManager } from '../lib/JobStateManager';
  import { relativeTime, matchesJobView } from '../lib/jobsPresentation';
  import { setJobView } from '../stores/workspace';
  import type { HostInfo, PartitionStatusResponse } from '../types/api';
  let hosts = $state<HostInfo[]>([]);
  let snapshots = $state<PartitionStatusResponse[]>([]);
  let loading = $state(true);
  let error = $state('');
  const jobs = jobStateManager.getAllJobs();
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
  <div class="host-grid">
    {#each hosts as host (host.hostname)}
      {@const snapshot=snapshots.find(item=>item.hostname===host.hostname)}
      {@const state=$hostStates.get(host.hostname)}
      {@const unavailable=Boolean(snapshot?.error||state?.status==='error')}
      <section class="host-card">
        <div class="host-title">
          <span class="host-icon">
            <Server size={23}/>
          </span>
          <h2>{host.hostname}</h2>
          <span class="host-health" class:unavailable={unavailable||Boolean(snapshot?.stale)}>
            <span class="relay-dot" class:connected={!unavailable&&!snapshot?.stale&&Boolean(snapshot)}></span>
            {unavailable?'Unavailable':snapshot?.stale?'Stale':snapshot?'Available':loading?'Loading':'Unknown'}
          </span>
        </div>
        {#if snapshot?.error}
          <p class="host-error">{snapshot.error}</p>
        {/if}
        <dl class="host-paths">
          <div>
            <dt>Work directory</dt>
            <dd>{host.work_dir||'—'}</dd>
          </div>
          <div>
            <dt>Scratch</dt>
            <dd>{host.scratch_dir||'—'}</dd>
          </div>
        </dl>
        <div class="host-jobs">
          <span>
            <strong>{$jobs.filter(job=>job.hostname===host.hostname&&matchesJobView(job,'running')).length}</strong>
            running
          </span>
          <span>
            <strong>{$jobs.filter(job=>job.hostname===host.hostname&&matchesJobView(job,'pending')).length}</strong>
            pending
          </span>
          <button class="relay-text-button" onclick={()=>openJobs(host.hostname)}>
            View jobs
            <ArrowRight size={14}/>
          </button>
        </div>
        {#if snapshot?.partitions.length}
          <div class="host-partitions">
            {#each snapshot.partitions as partition}
              <details open>
                <summary>
                  <span>{partition.partition}</span>
                  <small>{partition.availability||'Unknown'}</small>
                </summary>
                <div class="partition-resources">
                  <div>
                    <span>CPUs allocated</span>
                    <strong>
                      {partition.cpus_alloc}
                      <small>/ {partition.cpus_total}</small>
                    </strong>
                    <meter min="0" max={Math.max(partition.cpus_total,1)} value={partition.cpus_alloc} aria-label={`${partition.partition} allocated CPUs`}></meter>
                    <small>{partition.cpus_idle} idle · {partition.nodes_total} nodes</small>
                  </div>
                  {#if partition.gpus_total!==null}
                    <div>
                      <span>GPUs allocated</span>
                      <strong>
                        {partition.gpus_used??'—'}
                        <small>/ {partition.gpus_total}</small>
                      </strong>
                      {#if partition.gpus_used!==null}
                        <meter min="0" max={Math.max(partition.gpus_total,1)} value={partition.gpus_used} aria-label={`${partition.partition} allocated GPUs`}></meter>
                      {/if}
                      <small>{partition.gpus_idle===null?'Idle count unavailable':`${partition.gpus_idle} idle`}</small>
                    </div>
                  {/if}
                </div>
              </details>
            {/each}
          </div>
        {:else}
          <p class="relay-empty-message">{loading?'Loading capacity…':'No partition data available.'}</p>
        {/if}
        <footer>
          {snapshot?.stale?'Cached · ':''}
          {relativeTime(snapshot?.updated_at||state?.lastSync)}
          <span>SSH</span>
        </footer>
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
  .host-grid {
    display: grid;
    grid-template-columns: repeat(2,minmax(0,1fr));
    gap: 24px;
  }

  .host-card {
    padding: 24px;
    border: 1px solid var(--border);
    background: var(--card);
    border-radius: var(--radius-card);
    min-width: 0;
    transition: border-color var(--motion-state);
  }

  .host-card:hover {
    border-color: color-mix(in srgb,var(--accent) 50%,var(--border));
  }

  .host-title {
    display: flex;
    align-items: center;
    gap: 13px;
  }

  .host-title h2 {
    font-size: 1.25rem;
    font-weight: 600;
    margin: 0;
    overflow-wrap: anywhere;
  }

  .host-icon {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    flex-shrink: 0;
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--accent);
    background: var(--accent-soft);
  }

  .host-health {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--success);
    font-size: .8125rem;
    margin-left: auto;
  }

  .host-health.unavailable,.host-error {
    color: var(--warning);
  }

  .host-error {
    font-size: .8125rem;
    margin-top: 18px;
    overflow-wrap: anywhere;
  }

  .host-paths {
    display: flex;
    flex-direction: column;
    gap: 14px;
    margin: 26px 0;
    font-size: .8125rem;
  }

  .host-paths dt {
    color: var(--muted-foreground);
    margin-bottom: 5px;
  }

  .host-paths dd {
    font-family: monospace;
    overflow-wrap: anywhere;
    margin: 0;
  }

  .host-jobs {
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: .8125rem;
    color: var(--muted-foreground);
    margin: 24px 0;
  }

  .host-jobs strong {
    color: var(--foreground);
    font-weight: 600;
  }

  .host-jobs .relay-text-button {
    margin-left: auto;
  }

  .host-partitions {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .host-partitions details {
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--background);
  }

  .host-partitions summary {
    cursor: pointer;
    color: var(--foreground);
    font-size: .9375rem;
    font-weight: 550;
  }

  .host-partitions summary small {
    float: right;
    color: var(--muted-foreground);
    font-size: .75rem;
    font-weight: 400;
  }

  .partition-resources {
    display: grid;
    grid-template-columns: repeat(auto-fit,minmax(130px,1fr));
    gap: 22px;
    margin-top: 22px;
  }

  .partition-resources>div {
    display: flex;
    flex-direction: column;
    gap: 7px;
    font-size: .875rem;
  }

  .partition-resources>div>span,.partition-resources small {
    color: var(--muted-foreground);
    font-size: .75rem;
  }

  .partition-resources strong {
    font-size: 1.375rem;
    font-weight: 550;
    font-variant-numeric: tabular-nums;
  }

  .partition-resources strong small {
    font-size: .8125rem;
  }

  .partition-resources meter {
    width: 100%;
    height: 7px;
    appearance: none;
    background: var(--secondary);
    border-radius: 6px;
    border: 0;
  }

  .partition-resources meter::-webkit-meter-bar {
    background: var(--secondary);
    border: 0;
    height: 7px;
  }

  .partition-resources meter::-webkit-meter-optimum-value {
    background: var(--accent);
    border-radius: 6px;
  }

  .partition-resources meter::-moz-meter-bar {
    background: var(--accent);
  }

  .host-card footer {
    display: flex;
    justify-content: space-between;
    color: var(--muted-foreground);
    font-size: .75rem;
    margin-top: 24px;
  }

  .hosts-page>.relay-banner {
    margin-bottom: 24px;
  }

  @media (max-width:1120px) {
    .host-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width:600px) {
    .host-card {
      padding: 20px;
    }
    .host-jobs {
      flex-wrap: wrap;
    }
    .host-title h2 {
      font-size: 1.125rem;
    }
  }
</style>
