<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { push } from 'svelte-spa-router';
  import { Search, X, Server, Plus, RefreshCw, ArrowDownWideNarrow, ChevronRight, Layers, SlidersHorizontal, TriangleAlert } from 'lucide-svelte';
  import JobPage from './JobPage.svelte';
  import ArrayJobCard from '../components/ArrayJobCard.svelte';
  import JobStatus from '../components/workspace/JobStatus.svelte';
  import IconButton from '../components/workspace/IconButton.svelte';
  import { jobStateManager } from '../lib/JobStateManager';
  import { getArrayGroupTasks } from '../lib/arrayJobs';
  import { filterJobs, withinHistoryWindow, matchesJobView, gpuCount, jobRoute, relativeTime } from '../lib/jobsPresentation';
  import { jobUtils } from '../lib/jobUtils';
  import { api, apiConfig } from '../services/api';
  import { jobsWorkspace, selectJob, type JobView } from '../stores/workspace';
  import { preferences, preferencesActions } from '../stores/preferences';
  import { fetchAllWatchers } from '../stores/watchers';
  import { focusTrap } from '../lib/actions';
  import type { JobInfo, HostInfo } from '../types/api';
  const jobs = jobStateManager.getAllJobs();
  const groups = jobStateManager.getArrayJobGroups();
  const hostStates = jobStateManager.getHostStates();
  const manager = jobStateManager.getState();
  const tabs: {
    id: JobView;
    label: string;
  }[] = [{ id: 'all', label: 'All jobs' }, { id: 'running', label: 'Running' }, { id: 'pending', label: 'Pending' }, { id: 'attention', label: 'Needs attention' }, { id: 'historical', label: 'Historical' }];
  let hosts = $state<HostInfo[]>([]);
  let refreshing = $state(false);
  let error = $state('');
  let extraFilters = $state(false);
  let visibleLimit = $state(50);
  let scrollElement: HTMLDivElement;
  let focusedRow: HTMLButtonElement | undefined;
  let narrow = $state(false);
  const loading = $derived(refreshing || Array.from($hostStates.values()).some(h => h.status === 'loading'));
  const historyJobs = $derived($jobs.filter(job => withinHistoryWindow(job, $preferences.defaultSince)));
  const filtered = $derived(filterJobs(historyJobs, $jobsWorkspace));
  const arrayGroups = $derived($preferences.groupArrayJobs ? $groups.filter(group => getArrayGroupTasks(group).some(job => withinHistoryWindow(job, $preferences.defaultSince) && filterJobs([job], $jobsWorkspace).length > 0)) : []);
  const groupedKeys = $derived(new Set(arrayGroups.flatMap(group => getArrayGroupTasks(group).map(job => `${job.hostname}:${job.job_id}`))));
  const rows = $derived(filtered.filter(job => !groupedKeys.has(`${job.hostname}:${job.job_id}`)).slice(0, visibleLimit));
  const visibleHosts = $derived([...new Set([...rows.map(job => job.hostname), ...arrayGroups.map(group => group.hostname)])]);
  const hostNames = $derived([...new Set([...hosts.map(host => host.hostname), ...$hostStates.keys()])]);
  const selected = $derived($jobsWorkspace.selection);
  const hostErrors = $derived(Array.from($hostStates.values()).filter(host => host.status === 'error'));
  const running = $derived($jobs.filter(job => matchesJobView(job, 'running')).length);
  const pending = $derived($jobs.filter(job => matchesJobView(job, 'pending')).length);
  $effect(() => { visibleLimit = $preferences.jobsPerPage; });
  $effect(() => {
    if (!$preferences.autoRefresh)
      return;
    const timer = setInterval(() => { if (!document.hidden)
      void refresh(false, visibleLimit, false); }, Math.max(10000, $preferences.refreshInterval));
    return () => clearInterval(timer);
  });
  async function refresh(force = false, limit = visibleLimit, userInitiated = true) {
    if (refreshing)
      return;
    refreshing = true;
    error = '';
    try {
      const filters = { since: $preferences.defaultSince, limit, groupArrayJobs: $preferences.groupArrayJobs };
      if (force)
        await jobStateManager.forceRefresh(filters);
      else
        await jobStateManager.syncAllHosts(false, userInitiated, filters);
    }
    catch (err) {
      error = err instanceof Error ? err.message : 'Could not refresh jobs.';
    }
    finally {
      refreshing = false;
    }
  }
  async function more() { visibleLimit += $preferences.jobsPerPage; if (visibleLimit > filtered.length)
    await refresh(false, visibleLimit); }
  function open(job: JobInfo, event: MouseEvent) { focusedRow = event.currentTarget as HTMLButtonElement; selectJob(job); }
  async function close() { jobsWorkspace.update(state => ({ ...state, selection: null })); await tick(); focusedRow?.focus(); }
  function setTab(view: JobView) { jobsWorkspace.update(state => ({ ...state, view, selection: null, scrollTop: 0 })); }
  function clearFilters() { jobsWorkspace.update(state => ({ ...state, query: '', host: '', user: '', view: 'all' })); }
  onMount(() => {
    const media = matchMedia('(max-width: 1050px)');
    const resize = () => narrow = media.matches;
    resize();
    media.addEventListener('change', resize);
    scrollElement.scrollTop = $jobsWorkspace.scrollTop;
    void refresh();
    void api.get<HostInfo[]>('/api/hosts').then(response => hosts = response.data).catch(() => { });
    void fetchAllWatchers().catch(() => { });
    return () => { media.removeEventListener('change', resize); };
  });
  function keydown(event: KeyboardEvent) { if (event.key === 'Escape' && selected && !(event.target as Element)?.closest('[aria-modal="true"]')) {
    void close();
  } }
</script>

<svelte:window onkeydown={keydown}/>

<div class="relay-page jobs-page" bind:this={scrollElement} onscroll={()=>jobsWorkspace.update(state=>({...state,scrollTop:scrollElement.scrollTop}))}>
  <div class="relay-heading">
    <div>
      <h1>Jobs</h1>
      <p>{running} running · {pending} pending</p>
    </div>
    <div class="relay-heading-actions">
      <IconButton label="Refresh jobs" disabled={loading} onclick={()=>void refresh(true)}>
        <RefreshCw size={18} class={loading?'animate-spin':''}/>
      </IconButton>
      <a class="relay-button primary" href="#/launch">
        <Plus size={17}/>
        New job
      </a>
    </div>
  </div>
  {#if error}
    <div class="relay-banner error" role="alert">
      <TriangleAlert size={17}/>
      <span>{error}</span>
      <button class="relay-text-button" onclick={()=>void refresh(true)}>Retry</button>
    </div>
  {/if}
  {#if hostErrors.length}
    <div class="jobs-host-warning" role="status">
      <TriangleAlert size={15}/>
      {hostErrors.map(host=>host.hostname).join(', ')}
      unavailable. Showing the last received jobs.
    </div>
  {/if}
  <div class="jobs-workspace" class:has-inspector={selected!==null}>
    <section class="jobs-list" aria-label="Jobs">
      <div class="relay-tabs">
        {#each tabs as tab}
          <button class:active={$jobsWorkspace.view===tab.id} aria-pressed={$jobsWorkspace.view===tab.id} onclick={()=>setTab(tab.id)}>
            {tab.label}
            <span>{historyJobs.filter(job=>matchesJobView(job,tab.id)).length}</span>
          </button>
        {/each}
      </div>
      <div class="jobs-filters">
        <label class="relay-search">
          <Search size={17}/>
          <input placeholder="Search jobs…" aria-label="Search jobs" bind:value={$jobsWorkspace.query}/>
          {#if $jobsWorkspace.query}
            <IconButton label="Clear search" onclick={()=>jobsWorkspace.update(state=>({...state,query:''}))}>
              <X size={14}/>
            </IconButton>
          {/if}
        </label>
        <select class="relay-select" aria-label="Filter by host" bind:value={$jobsWorkspace.host}>
          <option value="">All hosts</option>
          {#each hostNames as host}
            <option value={host}>{host}</option>
          {/each}
        </select>
        <IconButton label={$jobsWorkspace.newestFirst?'Sort oldest first':'Sort newest first'} class="bordered" onclick={()=>jobsWorkspace.update(state=>({...state,newestFirst:!state.newestFirst}))}>
          <ArrowDownWideNarrow size={17}/>
        </IconButton>
        <button class="relay-icon-button bordered" aria-label="More filters" aria-expanded={extraFilters} title="More filters" onclick={()=>extraFilters=!extraFilters}>
          <SlidersHorizontal size={17}/>
        </button>
      </div>
      {#if extraFilters}
        <div class="jobs-extra-filters">
          <label>
            User
            <input class="relay-select" placeholder="All users" bind:value={$jobsWorkspace.user}/>
          </label>
          <label>
            History
            <select class="relay-select" value={$preferences.defaultSince} onchange={event=>{preferencesActions.setDefaultSince(event.currentTarget.value);void refresh();}}>
              {#each ['1d','7d','14d','30d','90d'] as period}
                <option value={period}>{period.replace('d',' days')}</option>
              {/each}
            </select>
          </label>
          <label class="jobs-checkbox">
            <input type="checkbox" checked={$preferences.groupArrayJobs} onchange={event=>{preferencesActions.setArrayGrouping(event.currentTarget.checked);void refresh();}}/>
            Group array jobs
          </label>
        </div>
      {/if}
      {#if $jobsWorkspace.query||$jobsWorkspace.host||$jobsWorkspace.user}
        <div class="jobs-active-filters">
          <span>{filtered.length} matching jobs</span>
          <button class="relay-text-button" onclick={clearFilters}>
            Clear filters
            <X size={13}/>
          </button>
        </div>
      {/if}
      {#each visibleHosts as hostname}
        {@const host=$hostStates.get(hostname)}
        <section class="jobs-host-group" aria-label={`${hostname} jobs`}>
          <div class="jobs-host-heading">
            <div>
              <Server size={16}/>
              <strong>{hostname}</strong>
              <span>{rows.filter(job=>job.hostname===hostname).length+arrayGroups.filter(group=>group.hostname===hostname).length}</span>
            </div>
            <span class:host-error={host?.status==='error'} title={host?.lastError||'Last successful job update'}>
              <span class="relay-dot" class:connected={host?.status==='connected'}></span>
              {host?.status==='loading'?'Updating':host?.status==='error'?'Cached':relativeTime(host?.lastSync)}
            </span>
          </div>
          {#if rows.some(job=>job.hostname===hostname)}
            <div class="jobs-table">
              <div class="jobs-table-head" aria-hidden="true">
                <span>Job</span>
                <span>State</span>
                <span>Resources</span>
                <span>Runtime</span>
                <span></span>
              </div>
              {#each rows.filter(job=>job.hostname===hostname) as job (`${job.hostname}:${job.job_id}`)}
                {@const gpus=gpuCount(job)}
                <button class="jobs-row" class:selected={selected?.id===job.job_id&&selected?.host===job.hostname} aria-pressed={selected?.id===job.job_id&&selected?.host===job.hostname} aria-label={`Inspect ${job.name||job.job_id}, job ${job.job_id} on ${job.hostname}`} onclick={event=>open(job,event)}>
                  <span class="jobs-identity">
                    <strong title={job.name}>{job.name||job.job_id}</strong>
                    <small>
                      <span class="mono">#{job.job_id}</span>
                      <span>{job.user||job.partition||''}</span>
                      {#if job.array_job_id}
                        <Layers size={12}/>
                      {/if}
                    </small>
                  </span>
                  <JobStatus state={job.state}/>
                  <span class="jobs-resources">
                    {gpus!==null?`${gpus} GPU`:`${job.cpus||'—'} CPU`}
                    <small>{job.memory||job.partition||'—'}</small>
                  </span>
                  <span class="jobs-runtime">
                    {job.runtime?jobUtils.formatDuration(job.runtime):'—'}
                    <small>{job.priority_rank?`#${job.priority_rank} in queue`:relativeTime(job.submit_time)}</small>
                  </span>
                  <ChevronRight size={15}/>
                </button>
              {/each}
            </div>
          {/if}
          {#each arrayGroups.filter(group=>group.hostname===hostname) as group (`${group.hostname}:${group.array_job_id}`)}
            <div class="jobs-array">
              <ArrayJobCard {group}/>
            </div>
          {/each}
        </section>
      {/each}
      {#if !visibleHosts.length}
        <div class="relay-empty">
          {#if loading}
            <RefreshCw size={24} class="animate-spin"/>
            <h2>Loading jobs</h2>
            {:else if !$apiConfig.authenticated}
              <Server size={24}/>
              <h2>Connect your workspace</h2>
              <a href="#/settings" class="relay-button">Connection settings</a>
            {:else}
              <Search size={24}/>
              <h2>{$jobs.length?'No matching jobs':'No jobs yet'}</h2>
              {#if $jobs.length}
                <button class="relay-button" onclick={clearFilters}>Clear filters</button>
              {:else}
                <button class="relay-button" onclick={()=>void refresh(true)}>Refresh jobs</button>
              {/if}
            {/if}
        </div>
      {/if}
      <div class="jobs-footer">
        <span>{filtered.length} jobs · {$preferences.defaultSince} history</span>
        {#if filtered.length>=visibleLimit||$jobs.length>=$preferences.jobsPerPage}
          <button class="relay-text-button" disabled={refreshing} onclick={()=>void more()}>Load more</button>
        {/if}
        <span>{$manager.dataSource==='cache'?'Cached data':''}</span>
      </div>
    </section>
    {#if selected}
      {#if narrow}
        <button class="inspector-backdrop" aria-label="Close job inspector" onclick={()=>void close()}></button>
      {/if}
      <aside class="jobs-inspector" class:mobile-inspector={narrow} aria-label="Selected job" use:focusTrap={{enabled:narrow}}>
        <JobPage embedded params={selected} onclose={()=>void close()} onexpand={()=>void push(jobRoute(selected.id,selected.host,$jobsWorkspace.tab))}/>
      </aside>
    {/if}
  </div>
</div>

<style>
  .jobs-page {
    container-type: inline-size;
  }

  .inspector-backdrop {
    position: fixed;
    inset: 0;
    background: #080e1c60;
    z-index: 34;
    border: 0;
  }

  .jobs-workspace {
    display: grid;
    grid-template-columns: minmax(0,1fr);
    gap: 24px;
    align-items: start;
  }

  .jobs-workspace.has-inspector {
    grid-template-columns: minmax(0,1fr) 390px;
  }

  .jobs-list {
    min-width: 0;
  }

  .jobs-filters {
    display: flex;
    gap: 8px;
    padding: 18px 0 22px;
    align-items: center;
  }

  .jobs-filters .relay-search {
    flex: 1;
  }

  .jobs-filters>.relay-select {
    max-width: 155px;
  }

  .jobs-extra-filters {
    display: flex;
    gap: 16px;
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--card);
    margin-bottom: 20px;
    flex-wrap: wrap;
  }

  .jobs-extra-filters label {
    display: flex;
    flex-direction: column;
    gap: 7px;
    font-size: .8125rem;
    color: var(--muted-foreground);
    flex: 1;
  }

  .jobs-extra-filters label.jobs-checkbox {
    flex-direction: row;
    align-items: center;
    align-self: end;
    min-height: 40px;
    white-space: nowrap;
  }

  .jobs-active-filters {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 18px;
    color: var(--muted-foreground);
    font-size: .8125rem;
  }

  .jobs-host-warning {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--warning);
    font-size: .8125rem;
    margin-bottom: 20px;
  }

  .jobs-host-group {
    margin-bottom: 26px;
  }

  .jobs-host-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
    font-size: .8125rem;
    color: var(--muted-foreground);
  }

  .jobs-host-heading>div {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .jobs-host-heading strong {
    font-size: .9375rem;
    font-weight: 550;
    color: var(--foreground);
  }

  .jobs-host-heading>span {
    display: flex;
    gap: 6px;
    align-items: center;
    font-size: .75rem;
  }

  .jobs-host-heading .host-error {
    color: var(--warning);
  }

  .jobs-table {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }

  .jobs-table-head,.jobs-row {
    display: grid;
    grid-template-columns: minmax(150px,1fr) 110px 76px 76px 12px;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 12px 14px;
    text-align: left;
  }

  .jobs-table-head {
    background: var(--secondary);
    color: var(--muted-foreground);
    font-size: .75rem;
    border-bottom: 1px solid var(--border);
  }

  .jobs-row {
    min-height: 78px;
    background: transparent;
    border: 0;
    border-bottom: 1px solid var(--border-soft);
    position: relative;
    transition: background var(--motion-state);
  }

  .jobs-row:last-child {
    border-bottom: 0;
  }

  .jobs-row:hover {
    background: var(--hover);
  }

  .jobs-row.selected {
    background: var(--accent-soft);
  }

  .jobs-row.selected::before {
    content: '';
    position: absolute;
    top: 18px;
    bottom: 18px;
    left: 0;
    width: 3px;
    background: var(--accent);
    border-radius: 0 4px 4px 0;
  }

  .jobs-row:focus-visible {
    outline-offset: -3px;
  }

  .jobs-identity {
    min-width: 0;
  }

  .jobs-identity>strong {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: .9375rem;
    font-weight: 550;
  }

  .jobs-identity small {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-top: 6px;
    color: var(--muted-foreground);
    font-size: .75rem;
    white-space: nowrap;
    overflow: hidden;
  }

  .jobs-identity small>span:nth-child(2) {
    text-overflow: ellipsis;
    overflow: hidden;
  }

  .jobs-resources,.jobs-runtime {
    font-size: .8125rem;
    color: var(--foreground);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }

  .jobs-resources small,.jobs-runtime small {
    display: block;
    color: var(--muted-foreground);
    font-size: .75rem;
    margin-top: 6px;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .jobs-row>:global(svg) {
    color: var(--muted-foreground);
    opacity: .5;
    transition: transform var(--motion-state),opacity var(--motion-state);
  }

  .jobs-row:hover>:global(svg) {
    color: var(--accent);
    opacity: 1;
    transform: translateX(2px);
  }

  .jobs-array {
    margin-top: 12px;
  }

  .jobs-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 15px;
    font-size: .75rem;
    color: var(--muted-foreground);
    padding: 0 2px 20px;
  }

  .jobs-inspector {
    position: sticky;
    top: 0;
    min-width: 0;
    height: calc(100dvh - 210px);
    min-height: 420px;
  }

  .jobs-inspector.mobile-inspector {
    position: fixed;
    inset: 72px 12px 12px auto;
    width: min(480px,calc(100vw - 24px));
    height: auto;
    min-height: 0;
    z-index: 35;
    box-shadow: 0 20px 80px #080e1c40;
    border-radius: 20px;
  }

  :global(.compact-mode) .jobs-row {
    min-height: 58px;
    padding-top: 8px;
    padding-bottom: 8px;
  }

  @container (min-width:1450px) {
    .jobs-workspace.has-inspector {
      grid-template-columns: minmax(0,1fr) 440px;
    }
  }

  @container (max-width:1050px) {
    .jobs-workspace.has-inspector {
      grid-template-columns: minmax(0,1fr) 350px;
    }
    .has-inspector .jobs-table-head,.has-inspector .jobs-row {
      grid-template-columns: minmax(115px,1fr) 108px 66px 12px;
      gap: 8px;
      padding-left: 11px;
      padding-right: 11px;
    }
    .has-inspector .jobs-resources,.has-inspector .jobs-table-head>span:nth-child(3) {
      display: none;
    }
    .jobs-filters>.relay-select {
      max-width: 125px;
    }
  }

  @media (max-width:1050px) {
    .jobs-workspace.has-inspector {
      grid-template-columns: minmax(0,1fr);
    }
  }

  @media (max-width:760px) {
    .jobs-table-head,.jobs-row,.has-inspector .jobs-table-head,.has-inspector .jobs-row {
      grid-template-columns: minmax(100px,1fr) 108px 12px;
      gap: 8px;
      padding: 13px 11px;
    }
    .jobs-resources,.jobs-runtime,.jobs-table-head>span:nth-child(3),.jobs-table-head>span:nth-child(4) {
      display: none;
    }
    .jobs-filters {
      flex-wrap: wrap;
    }
    .jobs-filters .relay-search {
      flex-basis: 100%;
      margin-bottom: 2px;
    }
    .jobs-filters>.relay-select {
      max-width: none;
      flex: 1;
    }
    .jobs-inspector.mobile-inspector {
      inset: 64px 8px 8px;
      width: auto;
    }
    .jobs-footer {
      flex-wrap: wrap;
    }
    .jobs-host-heading>span {
      font-size: .75rem;
    }
    .jobs-extra-filters label {
      min-width: 110px;
    }
  }
</style>
