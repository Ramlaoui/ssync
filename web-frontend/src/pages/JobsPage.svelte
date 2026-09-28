<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { push } from 'svelte-spa-router';
  import { Search, X, Server, Plus, RefreshCw, ArrowDownWideNarrow, ChevronRight, SlidersHorizontal, TriangleAlert } from 'lucide-svelte';
  import JobPage from './JobPage.svelte';
  import JobStatus from '../components/workspace/JobStatus.svelte';
  import IconButton from '../components/workspace/IconButton.svelte';
  import { jobStateManager } from '../lib/JobStateManager';
  import { getArrayGroupTasks } from '../lib/arrayJobs';
  import { filterJobs, withinHistoryWindow, matchesJobView, gpuCount, jobRoute, jobStatus, jobTiming, groupArrayTasks, summarizeTasks, type JobListEntry } from '../lib/jobsPresentation';
  import { api, apiConfig } from '../services/api';
  import { jobsWorkspace, selectJob, type JobView } from '../stores/workspace';
  import { preferences, preferencesActions } from '../stores/preferences';
  import { fetchAllWatchers } from '../stores/watchers';
  import { focusTrap } from '../lib/actions';
  import { safeGetItem, safeSetItem, safeRemoveItem } from '../lib/safeStorage';
  import type { JobInfo, HostInfo } from '../types/api';
  const jobs = jobStateManager.getAllJobs();
  const groups = jobStateManager.getArrayJobGroups();
  const hostStates = jobStateManager.getHostStates();
  const manager = jobStateManager.getState();
  const tabs: {
    id: JobView;
    label: string;
  }[] = [{ id: 'all', label: 'All' }, { id: 'running', label: 'Running' }, { id: 'pending', label: 'Queued' }, { id: 'historical', label: 'Finished' }];
  const sections: { id: 'active' | 'pending' | 'historical'; label: string }[] = [{ id: 'active', label: 'Running' }, { id: 'pending', label: 'Queued' }, { id: 'historical', label: 'Finished' }];
  const collapsedStorageKey = 'ssync-jobs-collapsed';
  let collapsed = $state<Set<string>>(new Set());
  let expandedArrays = $state<Set<string>>(new Set());
  let searchInput: HTMLInputElement | undefined = $state();
  let hosts = $state<HostInfo[]>([]);
  let refreshing = $state(false);
  let error = $state('');
  let extraFilters = $state(false);
  let visibleLimit = $state(50);
  let scrollElement: HTMLDivElement;
  let focusedRow: HTMLButtonElement | undefined;
  let narrow = $state(false);
  const minListWidth = 280;
  const minDetailWidth = 360;
  const dividerWidth = 24;
  const listWidthStorageKey = 'ssync-jobs-list-width';
  let workspaceWidth = $state(0);
  let preferredListWidth = $state<number | null>(null);
  let resizing = $state<{ pointerId: number; startX: number; startWidth: number } | null>(null);
  const maxListWidth = $derived(Math.max(minListWidth, workspaceWidth - minDetailWidth - dividerWidth));
  const listWidth = $derived(Math.max(minListWidth, Math.min(maxListWidth, preferredListWidth ?? Math.min(360, workspaceWidth * .28))));
  const loading = $derived(refreshing || Array.from($hostStates.values()).some(h => h.status === 'loading'));
  const historyJobs = $derived($jobs.filter(job => withinHistoryWindow(job, $preferences.defaultSince)));
  const filtered = $derived(filterJobs(historyJobs, $jobsWorkspace));
  // Tasks from any server-side array groups are listed like other jobs, then grouped client-side.
  const groupTasks = $derived(filterJobs($groups.flatMap(getArrayGroupTasks).filter(job => withinHistoryWindow(job, $preferences.defaultSince)), $jobsWorkspace));
  const listed = $derived.by(() => {
    const seen = new Set(filtered.map(job => `${job.hostname}:${job.job_id}`));
    return [...filtered, ...groupTasks.filter(job => !seen.has(`${job.hostname}:${job.job_id}`))];
  });
  const entries = $derived($preferences.collapseArrayTasks ? groupArrayTasks(listed) : listed.map(job => ({ kind: 'job' as const, key: `${job.hostname}:${job.job_id}`, job })));
  const entryCategory = (entry: JobListEntry) => {
    const states = (entry.kind === 'job' ? [entry.job] : entry.tasks).map(job => jobStatus(job.state).category);
    return states.includes('active') ? 'active' : states.includes('pending') ? 'pending' : 'historical';
  };
  // Count the jobs in a section; an array row counts only its tasks in that state.
  const entryJobs = (entry: JobListEntry, category: string) => entry.kind === 'job' ? 1 : entry.tasks.filter(task => jobStatus(task.state).category === category).length;
  // Running and queued work is always shown in full; finished work is paged.
  const sectioned = $derived(sections.map(section => {
    const all = entries.filter(entry => entryCategory(entry) === section.id);
    return { ...section, entries: section.id === 'historical' ? all.slice(0, visibleLimit) : all, total: all.reduce((sum, entry) => sum + entryJobs(entry, section.id), 0), hidden: section.id === 'historical' ? Math.max(0, all.length - visibleLimit) : 0 };
  }).filter(section => section.total));
  const finishedTotal = $derived(entries.filter(entry => entryCategory(entry) === 'historical').length);
  const loadingHosts = $derived(Array.from($hostStates.values()).filter(host => host.status === 'loading').map(host => host.hostname));
  const hostNames = $derived([...new Set([...hosts.map(host => host.hostname), ...$hostStates.keys()])]);
  const selected = $derived($jobsWorkspace.selection);
  $effect(() => { if (!selected || narrow) finishResize(); });
  const hostErrors = $derived(Array.from($hostStates.values()).filter(host => host.status === 'error'));
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
      const filters = { since: $preferences.defaultSince, limit, groupArrayJobs: false };
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
  async function more() { visibleLimit += $preferences.jobsPerPage; if (visibleLimit > finishedTotal)
    await refresh(false, visibleLimit); }
  function open(job: JobInfo, event: MouseEvent) { focusedRow = event.currentTarget as HTMLButtonElement; selectJob(job); }
  async function close() { jobsWorkspace.update(state => ({ ...state, selection: null })); await tick(); focusedRow?.focus(); }
  function toggleSection(id: string) {
    const next = new Set(collapsed);
    if (next.has(id)) next.delete(id); else next.add(id);
    collapsed = next;
    safeSetItem(collapsedStorageKey, JSON.stringify([...next]));
  }
  function toggleArray(key: string) {
    const next = new Set(expandedArrays);
    if (next.has(key)) next.delete(key); else next.add(key);
    expandedArrays = next;
  }
  function setTab(view: JobView) { jobsWorkspace.update(state => ({ ...state, view, selection: null, scrollTop: 0 })); }
  function clearFilters() { jobsWorkspace.update(state => ({ ...state, query: '', host: '', user: '', view: 'all' })); }
  function setListWidth(width: number) {
    preferredListWidth = Math.round(Math.max(minListWidth, Math.min(maxListWidth, width)));
  }
  function startResize(event: PointerEvent) {
    if (event.button !== 0 || !event.isPrimary || resizing)
      return;
    event.preventDefault();
    const handle = event.currentTarget as HTMLDivElement;
    handle.focus();
    handle.setPointerCapture(event.pointerId);
    resizing = { pointerId: event.pointerId, startX: event.clientX, startWidth: listWidth };
  }
  function moveResize(event: PointerEvent) {
    if (resizing?.pointerId === event.pointerId)
      setListWidth(resizing.startWidth + event.clientX - resizing.startX);
  }
  function finishResize(event?: PointerEvent) {
    if (!resizing || (event && event.pointerId !== resizing.pointerId))
      return;
    resizing = null;
    safeSetItem(listWidthStorageKey, String(listWidth));
  }
  function resizeWithKeyboard(event: KeyboardEvent) {
    const step = event.shiftKey ? 48 : 16;
    const nextWidth = event.key === 'ArrowLeft' ? listWidth - step : event.key === 'ArrowRight' ? listWidth + step : event.key === 'Home' ? minListWidth : event.key === 'End' ? maxListWidth : null;
    if (nextWidth === null)
      return;
    event.preventDefault();
    setListWidth(nextWidth);
    safeSetItem(listWidthStorageKey, String(listWidth));
  }
  function resetListWidth() {
    preferredListWidth = null;
    safeRemoveItem(listWidthStorageKey);
  }
  onMount(() => {
    try { collapsed = new Set(JSON.parse(safeGetItem(collapsedStorageKey) || '[]')); } catch { collapsed = new Set(); }
    const savedWidth = Number(safeGetItem(listWidthStorageKey));
    if (Number.isFinite(savedWidth) && savedWidth >= minListWidth)
      preferredListWidth = savedWidth;
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
  function keydown(event: KeyboardEvent) {
    if (event.key === 'Escape' && !event.defaultPrevented && selected && !document.querySelector('[aria-modal="true"]')) {
      void close();
      return;
    }
    // j/k move through rows and / focuses search, unless the user is typing or a dialog is open.
    const target = event.target as HTMLElement | null;
    if (event.metaKey || event.ctrlKey || event.altKey || target?.closest('input, textarea, select, [contenteditable="true"], .jobs-inspector') || document.querySelector('[aria-modal="true"]'))
      return;
    if (event.key === '/') {
      event.preventDefault();
      searchInput?.focus();
    }
    else if (event.key === 'j' || event.key === 'k') {
      const rowButtons = Array.from(document.querySelectorAll<HTMLButtonElement>('.jobs-list .jobs-row'));
      if (!rowButtons.length)
        return;
      event.preventDefault();
      const index = rowButtons.indexOf(document.activeElement as HTMLButtonElement);
      const next = index < 0 ? 0 : Math.max(0, Math.min(rowButtons.length - 1, index + (event.key === 'j' ? 1 : -1)));
      rowButtons[next].focus();
      rowButtons[next].scrollIntoView({ block: 'nearest' });
    }
  }
</script>

<svelte:window onkeydown={keydown}/>

{#snippet jobRow(job: JobInfo, task: boolean)}
  {@const gpus=gpuCount(job)}
  {@const status=jobStatus(job.state)}
  {@const timing=jobTiming(job)}
  {@const isSelected=selected?.id===job.job_id&&selected?.host===job.hostname}
  <button class="jobs-row" class:task class:selected={isSelected} aria-pressed={isSelected} aria-label={`Inspect ${job.name||job.job_id}, job ${job.job_id} on ${job.hostname}`} onclick={event=>open(job,event)}>
    <span class="jobs-state tone-{status.tone}" title={status.label}>
      <span class="jobs-dot"></span>
      <span class="jobs-state-label">{status.label}</span>
    </span>
    <span class="jobs-name">
      <strong title={job.name}>{task&&job.array_task_id?`Task ${job.array_task_id}`:job.name||job.job_id}</strong>
      <small class="mono">#{job.job_id}</small>
    </span>
    <span class="jobs-host">{job.hostname}</span>
    <span class="jobs-partition" title={job.partition||''}>{job.partition||''}</span>
    <span class="jobs-resources">{gpus!==null?`${gpus} GPU`:job.cpus?`${job.cpus} CPU`:''}{job.memory?` · ${job.memory}`:''}</span>
    <span class="jobs-time" title={timing.detail}>
      <span>{timing.primary}</span>
      {#if timing.secondary}<small>{timing.secondary}</small>{/if}
    </span>
  </button>
{/snippet}


<div class="relay-page jobs-page" bind:this={scrollElement} onscroll={()=>jobsWorkspace.update(state=>({...state,scrollTop:scrollElement.scrollTop}))}>
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
  <div class="jobs-workspace" class:has-inspector={selected!==null} class:resizing={resizing!==null} bind:clientWidth={workspaceWidth} style:--jobs-list-width={`${listWidth}px`} style:--jobs-divider-width={`${dividerWidth}px`}>
    <section id="jobs-list" class="jobs-list" aria-label="Jobs">
      <div class="jobs-toolbar">
        <div class="relay-tabs jobs-tabs">
          {#each tabs as tab}
            <button class:active={$jobsWorkspace.view===tab.id} aria-pressed={$jobsWorkspace.view===tab.id} onclick={()=>setTab(tab.id)}>
              {tab.label}
              <span>{historyJobs.filter(job=>matchesJobView(job,tab.id)).length.toLocaleString()}</span>
            </button>
          {/each}
        </div>
        <div class="jobs-toolbar-actions">
          <IconButton label="Refresh jobs" disabled={loading} onclick={()=>void refresh(true)}>
            <RefreshCw size={16} class={loading?'animate-spin':''}/>
          </IconButton>
          <a class="relay-button primary compact" href="#/launch">
            <Plus size={16}/>
            <span class="jobs-new-label">New job</span>
          </a>
        </div>
      </div>
      <div class="jobs-filters">
        <label class="relay-search">
          <Search size={16}/>
          <input bind:this={searchInput} placeholder="Search jobs…  /" aria-label="Search jobs" bind:value={$jobsWorkspace.query}/>
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
          <ArrowDownWideNarrow size={16}/>
        </IconButton>
        <button class="relay-icon-button bordered" aria-label="More filters" aria-expanded={extraFilters} title="More filters" onclick={()=>extraFilters=!extraFilters}>
          <SlidersHorizontal size={16}/>
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
            <input type="checkbox" checked={$preferences.collapseArrayTasks} onchange={event=>preferencesActions.setArrayGrouping(event.currentTarget.checked)}/>
            Group array tasks
          </label>
        </div>
      {/if}
      {#if $jobsWorkspace.query||$jobsWorkspace.host||$jobsWorkspace.user}
        <div class="jobs-active-filters">
          <span>{filtered.length.toLocaleString()} matching jobs</span>
          <button class="relay-text-button" onclick={clearFilters}>
            Clear filters
            <X size={13}/>
          </button>
        </div>
      {/if}
      {#if entries.length}
        <div class="jobs-table" role="list">
          {#each sectioned as section (section.id)}
            {@const isCollapsed=$jobsWorkspace.view==='all'&&collapsed.has(section.id)}
            {#if $jobsWorkspace.view==='all'}
              <button class="jobs-section" aria-expanded={!isCollapsed} onclick={()=>toggleSection(section.id)}>
                <ChevronRight size={14} class="jobs-chevron"/>
                <span>{section.label}</span>
                <small>{section.total.toLocaleString()}</small>
              </button>
            {/if}
            {#if !isCollapsed}
              {#each section.entries as entry (entry.key)}
                {#if entry.kind==='job'}
                  {@render jobRow(entry.job, false)}
                {:else}
                  {@const expanded=expandedArrays.has(entry.key)}
                  <button class="jobs-row jobs-array-row" aria-expanded={expanded} aria-label={`Array ${entry.name}, ${entry.tasks.length} tasks on ${entry.hostname}`} onclick={()=>toggleArray(entry.key)}>
                    <span class="jobs-state"><ChevronRight size={14} class="jobs-chevron"/></span>
                    <span class="jobs-name">
                      <strong title={entry.name}>{entry.name}</strong>
                      <small class="mono">#{entry.arrayId} · {entry.tasks.length} tasks</small>
                    </span>
                    <span class="jobs-host">{entry.hostname}</span>
                    <span class="jobs-partition">{entry.tasks[0]?.partition||''}</span>
                    <span class="jobs-resources"></span>
                    <span class="jobs-time"><span>{summarizeTasks(entry.tasks)}</span></span>
                  </button>
                  {#if expanded}
                    {#each entry.tasks as task (`${task.hostname}:${task.job_id}`)}
                      {@render jobRow(task, true)}
                    {/each}
                  {/if}
                {/if}
              {/each}
            {/if}
          {/each}
        </div>
      {:else}
        <div class="relay-empty">
          {#if loading}
            <RefreshCw size={24} class="animate-spin"/>
            <h2>Loading jobs</h2>
            {#if loadingHosts.length}<p>Waiting for {loadingHosts.join(', ')}</p>{/if}
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
        <span>
          {filtered.length.toLocaleString()} jobs · last {$preferences.defaultSince.replace('d',' days')}
          {#if loadingHosts.length&&entries.length} · updating {loadingHosts.join(', ')}{/if}
          {#if $manager.dataSource==='cache'} · cached{/if}
        </span>
        {#if finishedTotal>visibleLimit||$jobs.length>=$preferences.jobsPerPage}
          <button class="relay-text-button" disabled={refreshing} onclick={()=>void more()}>Load more finished jobs</button>
        {/if}
        <span class="jobs-shortcuts">j / k to move · Enter to open · / to search</span>
      </div>
    </section>
    {#if selected}
      {#if narrow}
        <button class="inspector-backdrop" aria-label="Close job inspector" onclick={()=>void close()}></button>
      {:else}
        <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions (A focusable ARIA window splitter supports both pointer and keyboard resizing.) -->
        <div
          class="jobs-resizer"
          role="separator"
          tabindex="0"
          aria-label="Resize jobs list"
          aria-controls="jobs-list"
          aria-orientation="vertical"
          aria-valuemin={minListWidth}
          aria-valuemax={Math.round(maxListWidth)}
          aria-valuenow={Math.round(listWidth)}
          aria-valuetext={`${Math.round(listWidth)} pixels for the jobs list`}
          title="Drag to resize. Arrow keys adjust width; double-click to reset."
          onpointerdown={startResize}
          onpointermove={moveResize}
          onpointerup={finishResize}
          onpointercancel={finishResize}
          onlostpointercapture={finishResize}
          onkeydown={resizeWithKeyboard}
          ondblclick={resetListWidth}
        ></div>
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
    grid-template-columns: var(--jobs-list-width) var(--jobs-divider-width) minmax(0,1fr);
    gap: 0;
  }

  .jobs-resizer {
    position: sticky;
    top: 0;
    display: grid;
    place-items: center;
    height: calc(100dvh - 210px);
    min-height: 420px;
    cursor: col-resize;
    touch-action: none;
    outline-offset: -3px;
  }

  .jobs-resizer::before {
    content: '';
    width: 3px;
    height: 48px;
    border-radius: 3px;
    background: var(--border);
  }

  .jobs-resizer:hover::before,.jobs-resizer:focus-visible::before,.resizing .jobs-resizer::before {
    background: var(--accent);
  }

  .resizing,.resizing :global(*) {
    cursor: col-resize !important;
    user-select: none;
  }

  .jobs-list {
    min-width: 0;
  }

  .jobs-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    border-bottom: 1px solid var(--border);
  }

  .jobs-toolbar .jobs-tabs {
    border-bottom: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .jobs-toolbar-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
    padding-bottom: 6px;
  }

  .relay-button.compact {
    min-height: 34px;
    padding: 0 12px;
    font-size: .8125rem;
  }

  .jobs-filters {
    display: flex;
    gap: 8px;
    padding: 12px 0;
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
    padding: 14px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--card);
    margin-bottom: 12px;
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
    margin-bottom: 10px;
    color: var(--muted-foreground);
    font-size: .8125rem;
  }

  .jobs-host-warning {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--warning);
    font-size: .8125rem;
    margin-bottom: 12px;
  }

  .jobs-table {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }

  .jobs-section {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    padding: 7px 12px;
    border: 0;
    border-bottom: 1px solid var(--border-soft);
    background: var(--secondary);
    color: var(--muted-foreground);
    font-size: .75rem;
    font-weight: 600;
    letter-spacing: .02em;
    text-transform: uppercase;
    text-align: left;
    position: sticky;
    top: 0;
    z-index: 1;
  }

  .jobs-section small {
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }

  .jobs-section :global(.jobs-chevron),.jobs-array-row :global(.jobs-chevron) {
    transition: transform var(--motion-state);
    transform: rotate(90deg);
  }

  .jobs-section[aria-expanded=false] :global(.jobs-chevron),.jobs-array-row[aria-expanded=false] :global(.jobs-chevron) {
    transform: none;
  }

  .jobs-row {
    display: grid;
    grid-template-columns: 104px minmax(180px,1fr) 88px 130px 104px 150px;
    align-items: center;
    gap: 12px;
    width: 100%;
    min-height: 40px;
    padding: 6px 12px;
    text-align: left;
    background: transparent;
    border: 0;
    border-bottom: 1px solid var(--border-soft);
    position: relative;
    font-size: .8125rem;
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
    top: 8px;
    bottom: 8px;
    left: 0;
    width: 3px;
    background: var(--accent);
    border-radius: 0 4px 4px 0;
  }

  .jobs-row:focus-visible {
    outline-offset: -3px;
  }

  .jobs-row.task {
    background: color-mix(in srgb, var(--secondary) 45%, transparent);
  }

  .jobs-row.task .jobs-name {
    padding-left: 18px;
  }

  .jobs-state {
    display: flex;
    align-items: center;
    gap: 7px;
    min-width: 0;
    color: var(--muted-foreground);
    white-space: nowrap;
  }

  .jobs-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    background: currentColor;
  }

  .jobs-state-label {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .tone-running { color: var(--accent); }
  .tone-pending { color: var(--warning); }
  .tone-success { color: var(--success); }
  .tone-danger { color: var(--error); }
  .tone-warning { color: var(--warning); }
  .tone-cancelled,.tone-unknown,.tone-paused { color: var(--muted-foreground); }
  .tone-pending .jobs-dot { background: transparent; border: 2px solid currentColor; }

  .jobs-name {
    display: flex;
    align-items: baseline;
    gap: 8px;
    min-width: 0;
  }

  .jobs-name strong {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 550;
    color: var(--foreground);
  }

  .jobs-name small,.jobs-host,.jobs-partition,.jobs-resources,.jobs-time small {
    color: var(--muted-foreground);
    font-size: .75rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .jobs-name small {
    flex-shrink: 0;
  }

  .jobs-time {
    display: flex;
    align-items: baseline;
    justify-content: flex-end;
    gap: 5px;
    min-width: 0;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .jobs-time>span {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .jobs-time small {
    flex-shrink: 0;
    font-size: .75rem;
  }

  .jobs-array-row .jobs-state {
    color: var(--muted-foreground);
  }

  .jobs-array-row .jobs-time>span {
    color: var(--muted-foreground);
    font-size: .75rem;
  }

  .jobs-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 15px;
    font-size: .75rem;
    color: var(--muted-foreground);
    padding: 10px 2px 20px;
  }

  .jobs-shortcuts {
    opacity: .75;
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

  .has-inspector .jobs-filters {
    flex-wrap: wrap;
  }

  .has-inspector .jobs-filters .relay-search {
    flex-basis: 100%;
  }

  .has-inspector .jobs-filters>.relay-select {
    max-width: none;
    flex: 1;
  }

  .has-inspector .jobs-row {
    grid-template-columns: 18px minmax(0,1fr) 72px;
    gap: 8px;
  }

  .has-inspector .jobs-state-label,.has-inspector .jobs-host,.has-inspector .jobs-partition,
  .has-inspector .jobs-resources,.has-inspector .jobs-shortcuts,.has-inspector .jobs-toolbar-actions .relay-button {
    display: none;
  }

  .has-inspector .jobs-name {
    flex-direction: column;
    gap: 1px;
  }

  .has-inspector .jobs-time small {
    display: none;
  }

  @container (max-width:960px) {
    .jobs-row {
      grid-template-columns: 100px minmax(140px,1fr) 84px 130px;
    }
    .jobs-partition,.jobs-resources {
      display: none;
    }
  }

  @media (max-width:1050px) {
    .jobs-workspace.has-inspector {
      grid-template-columns: minmax(0,1fr);
    }
    .jobs-resizer {
      display: none;
    }
  }

  @media (max-width:760px) {
    .jobs-row,.has-inspector .jobs-row {
      grid-template-columns: 18px minmax(0,1fr) 78px;
      gap: 8px;
      min-height: 48px;
    }
    .jobs-state-label,.jobs-host,.jobs-partition,.jobs-resources,.jobs-shortcuts,.jobs-time small {
      display: none;
    }
    .jobs-toolbar-actions .relay-button {
      padding: 0 10px;
    }
    .jobs-toolbar-actions .relay-button :global(svg) {
      margin: 0;
    }
    .jobs-new-label {
      display: none;
    }
    .jobs-name {
      flex-direction: column;
      gap: 1px;
    }
    .jobs-filters {
      flex-wrap: wrap;
    }
    .jobs-filters .relay-search {
      flex-basis: 100%;
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
    .jobs-extra-filters label {
      min-width: 110px;
    }
  }
</style>
