<script lang="ts">
  import { onMount, onDestroy, untrack } from "svelte";
  import { push } from "svelte-spa-router";
  import type { AxiosError } from "axios";
  import { api } from "../services/api";
  import type { JobInfo, OutputData, ScriptData } from "../types/api";
  import { jobStateManager } from "../lib/JobStateManager";
  import { streamJobOutput, type OutputStreamSession } from "../lib/streaming";
  import type { Readable } from "svelte/store";
  import JobOverview from '../components/workspace/JobOverview.svelte';
  import JobActivity from '../components/workspace/JobActivity.svelte';
  import JobStatus from '../components/workspace/JobStatus.svelte';
  import IconButton from '../components/workspace/IconButton.svelte';
  import Dialog from '../lib/components/ui/Dialog.svelte';
  import { jobsWorkspace } from '../stores/workspace';
  import { jobRoute } from '../lib/jobsPresentation';
  import { jobUtils } from '../lib/jobUtils';
  import { prepareRelaunch } from '../lib/relaunch';
  import JobTabContent from "../components/JobTabContent.svelte";
  import WatcherAttachmentDialog from "../components/WatcherAttachmentDialog.svelte";
  import LoadingSpinner from "../components/LoadingSpinner.svelte";
  import { ArrowLeft, Server, Eye, Maximize2, Minimize2, X, Copy, RefreshCw, Square, RotateCcw } from 'lucide-svelte';
  import { navigationActions } from '../stores/navigation';
  import { fetchJobWatchers, prefetchJobWatchers } from '../stores/watchers';
  interface Props {
    params?: {
      id?: string;
      host?: string;
    };
    embedded?: boolean;
    onclose?: () => void;
    onexpand?: () => void;
  }
  let { params = {}, embedded = false, onclose = closeJob, onexpand = () => { } }: Props = $props();
  let cancelOpen = $state(false);
  let canceling = $state(false);
  let relaunching = $state(false);
  let notice = $state('');
  let jobRequestVersion = 0;
  let scriptRequestVersion = 0;
  let jobStore: Readable<JobInfo | null> | null = $state(null);
  const job = $derived.by((): JobInfo | null => jobStore ? $jobStore : null);
  let loading = $state(false);
  let initialLoadComplete = $state(false);
  let error: string | null = $state(null);
  type JobTab = 'details' | 'output' | 'errors' | 'script' | 'watchers' | 'activity';
  const validTabs: JobTab[] = ['details', 'output', 'errors', 'script', 'watchers', 'activity'];
  let activeTab = $state<JobTab>('details');
  let showAttachWatchersDialog = $state(false);
  // Output related state
  type OutputStreamType = 'stdout' | 'stderr';
  const DEFAULT_OUTPUT_MAX_BYTES = 512 * 1024;
  const MAX_OUTPUT_BUFFER_CHARS = 768 * 1024;
  const OUTPUT_HEAD_BUFFER_CHARS = 128 * 1024;
  let outputData: OutputData | null = $state(null);
  let outputError: string | null = $state(null);
  let loadingOutput = $state(false);
  let loadingMoreOutput = false;
  let refreshingOutput = $state(false);
  let outputBackgroundRetryCount = $state(0);
  let outputRetryTimer: ReturnType<typeof setTimeout> | null = null;
  let currentOutputType: OutputStreamType | null = $state(null);
  let outputStreamSession: OutputStreamSession | null = null;
  let outputRequestVersion = 0;
  // Script related state
  let scriptData: ScriptData | null = $state(null);
  let scriptError: string | null = $state(null);
  let loadingScript = $state(false);
  function getRouteSearchParams(): URLSearchParams {
    if (typeof window === 'undefined')
      return new URLSearchParams();
    const hashQueryIndex = window.location.hash.indexOf('?');
    if (hashQueryIndex >= 0) {
      return new URLSearchParams(window.location.hash.slice(hashQueryIndex + 1));
    }
    return new URLSearchParams(window.location.search);
  }
  function getInitialActiveTab(): JobTab {
    const routeTab = embedded ? $jobsWorkspace.tab : getRouteSearchParams().get('tab');
    return validTabs.includes(routeTab as JobTab) ? (routeTab as JobTab) : 'details';
  }
  function updateActiveTabInUrl(tab: JobTab) {
    jobsWorkspace.update(state => ({ ...state, tab }));
    if (embedded || typeof window === 'undefined' || !params.id || !params.host)
      return;
    const routeParams = getRouteSearchParams();
    if (tab === 'details') {
      routeParams.delete('tab');
    }
    else {
      routeParams.set('tab', tab);
    }
    const nextQuery = routeParams.toString();
    const nextUrl = `${window.location.origin}${window.location.pathname}#/jobs/${encodeURIComponent(params.id)}/${encodeURIComponent(params.host)}${nextQuery ? `?${nextQuery}` : ''}`;
    window.history.replaceState({}, '', nextUrl);
  }
  // Load job data using JobStateManager
  async function loadJob(forceRefresh = false) {
    if (!params.id || !params.host) {
      error = "Invalid job parameters";
      return;
    }
    // For initial load or force refresh, show loading state
    if (!initialLoadComplete || forceRefresh) {
      loading = true;
    }
    error = null;
    const requestVersion = ++jobRequestVersion;
    try {
      // Fetch the job data (will update the store automatically)
      const jobData = await jobStateManager.fetchSingleJob(params.id, params.host, forceRefresh);
      if (requestVersion !== jobRequestVersion)
        return;
      if (!jobData) {
        error = "Job not found";
      }
      initialLoadComplete = true;
    }
    catch (err: unknown) {
      if (requestVersion !== jobRequestVersion)
        return;
      const axiosError = err as AxiosError;
      if (axiosError.response?.status === 404) {
        error = "Job not found";
      }
      else {
        error = `Failed to load job: ${axiosError.message}`;
      }
    }
    finally {
      if (requestVersion === jobRequestVersion)
        loading = false;
    }
  }
  // Load output data
  function clearOutputRetryTimer() {
    if (outputRetryTimer) {
      clearTimeout(outputRetryTimer);
      outputRetryTimer = null;
    }
  }
  function stopOutputStream() {
    outputStreamSession?.close();
    outputStreamSession = null;
  }
  function getActiveOutputType(tab: string = activeTab): OutputStreamType | null {
    if (tab === 'output')
      return 'stdout';
    if (tab === 'errors')
      return 'stderr';
    return null;
  }
  function emptyOutputData(outputType: OutputStreamType): OutputData {
    return {
      job_id: params.id || '',
      hostname: params.host || '',
      output_type: outputType,
      stdout: null,
      stderr: null,
      stdout_metadata: null,
      stderr_metadata: null,
      content_truncated: false,
      content_limit_bytes: DEFAULT_OUTPUT_MAX_BYTES,
      cached: false,
      stale: false,
      refresh_queued: false,
    };
  }
  function mergeOutputData(outputType: OutputStreamType, patch: Partial<OutputData>): OutputData {
    const base = outputData && outputData.output_type === outputType
      ? outputData
      : emptyOutputData(outputType);
    return {
      ...base,
      ...patch,
      output_type: outputType,
    };
  }
  function appendBoundedChunk(current: string | null | undefined, chunk: string): string {
    if (!chunk) {
      return current || '';
    }
    const next = `${current || ''}${chunk}`;
    if (next.length <= MAX_OUTPUT_BUFFER_CHARS) {
      return next;
    }
    const marker = '\n\n[... older live output omitted; showing beginning and latest output ...]\n\n';
    const tailSize = MAX_OUTPUT_BUFFER_CHARS - OUTPUT_HEAD_BUFFER_CHARS - marker.length;
    if (tailSize <= 0) {
      return next.slice(next.length - MAX_OUTPUT_BUFFER_CHARS);
    }
    return `${next.slice(0, OUTPUT_HEAD_BUFFER_CHARS)}${marker}${next.slice(next.length - tailSize)}`;
  }
  function resetOutputState(options: {
    clearError?: boolean;
  } = {}) {
    stopOutputStream();
    clearOutputRetryTimer();
    outputBackgroundRetryCount = 0;
    outputData = null;
    currentOutputType = null;
    loadingOutput = false;
    refreshingOutput = false;
    if (options.clearError !== false) {
      outputError = null;
    }
    outputRequestVersion += 1;
  }
  function scheduleOutputRetry(outputType: OutputStreamType) {
    if (outputBackgroundRetryCount >= 2)
      return;
    clearOutputRetryTimer();
    outputRetryTimer = setTimeout(() => {
      if (getActiveOutputType() !== outputType) {
        return;
      }
      outputBackgroundRetryCount += 1;
      void loadOutput(outputType, { backgroundRetry: true });
    }, 1200);
  }
  async function loadOutput(outputType: OutputStreamType, options: {
    backgroundRetry?: boolean;
    forceRefresh?: boolean;
  } = {}) {
    if (!job || !params.id || !params.host)
      return;
    if (!options.backgroundRetry) {
      outputBackgroundRetryCount = 0;
      clearOutputRetryTimer();
      stopOutputStream();
    }
    loadingOutput = !options.backgroundRetry;
    outputError = null;
    currentOutputType = outputType;
    if (!options.backgroundRetry || !outputData || outputData.output_type !== outputType) {
      outputData = emptyOutputData(outputType);
    }
    const requestVersion = ++outputRequestVersion;
    try {
      if (job.state === 'R') {
        const metadataResponse = await api.get<OutputData>(`/api/jobs/${params.id}/output`, {
          params: {
            host: params.host,
            output_type: outputType,
            metadata_only: true,
            max_bytes: DEFAULT_OUTPUT_MAX_BYTES,
            force_refresh: options.forceRefresh ? 'true' : undefined,
          },
        });
        if (requestVersion !== outputRequestVersion || currentOutputType !== outputType) {
          return;
        }
        outputData = mergeOutputData(outputType, metadataResponse.data);
        loadingOutput = false;
        refreshingOutput = false;
        outputStreamSession = streamJobOutput(params.id, params.host, outputType, {
          onMetadata: (metadata) => {
            if (requestVersion !== outputRequestVersion || currentOutputType !== outputType) {
              return;
            }
            outputData = mergeOutputData(outputType, {
              content_truncated: Boolean(metadata.truncated),
              content_limit_bytes: DEFAULT_OUTPUT_MAX_BYTES,
            });
          },
          onChunk: (chunk) => {
            if (requestVersion !== outputRequestVersion || currentOutputType !== outputType) {
              return;
            }
            const currentContent = (outputType === 'stdout' ? outputData?.stdout : outputData?.stderr) || '';
            const willTrim = currentContent.length + chunk.length > MAX_OUTPUT_BUFFER_CHARS;
            outputData = mergeOutputData(outputType, {
              stdout: outputType === 'stdout'
                ? appendBoundedChunk(currentContent, chunk)
                : null,
              stderr: outputType === 'stderr'
                ? appendBoundedChunk(currentContent, chunk)
                : null,
              content_truncated: Boolean(outputData?.content_truncated || willTrim),
            });
          },
          onTruncationNotice: () => {
            if (requestVersion !== outputRequestVersion || currentOutputType !== outputType) {
              return;
            }
            outputData = mergeOutputData(outputType, {
              content_truncated: true,
            });
          },
          onComplete: () => {
            if (requestVersion !== outputRequestVersion || currentOutputType !== outputType) {
              return;
            }
            stopOutputStream();
            loadingOutput = false;
            refreshingOutput = false;
          },
          onError: (message) => {
            if (requestVersion !== outputRequestVersion || currentOutputType !== outputType) {
              return;
            }
            stopOutputStream();
            outputError = message;
            loadingOutput = false;
            refreshingOutput = false;
          },
        }, DEFAULT_OUTPUT_MAX_BYTES);
      }
      else {
        const response = await api.get<OutputData>(`/api/jobs/${params.id}/output`, {
          params: {
            host: params.host,
            output_type: outputType,
            max_bytes: DEFAULT_OUTPUT_MAX_BYTES,
            force_refresh: options.forceRefresh ? 'true' : undefined,
          },
        });
        if (requestVersion !== outputRequestVersion || currentOutputType !== outputType) {
          return;
        }
        outputData = response.data;
        if (response.data.refresh_queued) {
          scheduleOutputRetry(outputType);
        }
        else {
          clearOutputRetryTimer();
        }
      }
    }
    catch (err: unknown) {
      const axiosError = err as AxiosError;
      if (requestVersion === outputRequestVersion)
        outputError = `Failed to load output: ${axiosError.message}`;
    }
    finally {
      if (requestVersion === outputRequestVersion) {
        loadingOutput = false;
        refreshingOutput = false;
      }
    }
  }
  // Refresh output data
  async function refreshOutput() {
    const outputType = getActiveOutputType();
    if (!job || !outputType)
      return;
    refreshingOutput = true;
    outputError = null;
    outputBackgroundRetryCount = 0;
    clearOutputRetryTimer();
    try {
      await loadOutput(outputType, { forceRefresh: true });
    }
    catch (err: unknown) {
      const axiosError = err as AxiosError;
      outputError = `Failed to refresh output: ${axiosError.message}`;
    }
  }
  // Load script data
  async function loadScript() {
    if (!job)
      return;
    loadingScript = true;
    scriptError = null;
    const requestVersion = ++scriptRequestVersion;
    try {
      const response = await api.get<ScriptData>(`/api/jobs/${encodeURIComponent(params.id!)}/script`, { params: { host: params.host } });
      if (requestVersion === scriptRequestVersion)
        scriptData = response.data;
    }
    catch (err: unknown) {
      const axiosError = err as AxiosError;
      if (requestVersion === scriptRequestVersion)
        scriptError = `Failed to load script: ${axiosError.message}`;
    }
    finally {
      if (requestVersion === scriptRequestVersion)
        loadingScript = false;
    }
  }
  // Event handlers
  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      notice = 'Copied to clipboard';
    }
    catch {
      notice = 'Clipboard is unavailable in this browser.';
    }
  }
  function handleShareJob() { if (params.id && params.host)
    void copy(window.location.origin + window.location.pathname + '#' + jobRoute(params.id, params.host, activeTab)); }
  async function handleCancelJob() {
    if (!job || canceling)
      return;
    canceling = true;
    try {
      await api.post('/api/jobs/' + encodeURIComponent(job.job_id) + '/cancel', null, { params: { host: job.hostname } });
      cancelOpen = false;
      await loadJob(true);
    }
    catch (err) {
      notice = err instanceof Error ? err.message : 'Could not cancel the job.';
    }
    finally {
      canceling = false;
    }
  }
  async function relaunch() {
    if (!job || relaunching)
      return;
    relaunching = true;
    try {
      await prepareRelaunch(job);
      await push('/launch');
    }
    catch (err) {
      notice = err instanceof Error ? err.message : 'Could not prepare relaunch.';
    }
    finally {
      relaunching = false;
    }
  }
  function closeJob() {
    jobsWorkspace.update(state => ({ ...state, selection: null }));
    void push('/');
  }
  function restore() {
    if (params.id && params.host)
      jobsWorkspace.update(state => ({ ...state, selection: { id: params.id!, host: params.host! }, tab: activeTab }));
    void push('/');
  }
  function downloadScript() {
    if (!scriptData)
      return;
    const url = URL.createObjectURL(new Blob([scriptData.script_content], { type: 'text/plain' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'job_' + params.id + '.sh';
    anchor.click();
    URL.revokeObjectURL(url);
  }
  function handleAttachWatchers() {
    showAttachWatchersDialog = true;
  }
  // Tab management
  function handleTabClick(tab: JobTab) {
    activeTab = tab;
    updateActiveTabInUrl(tab);
  }
  function handleBackNavigation() {
    // Use smart navigation based on where we came from
    navigationActions.goBack();
  }
  // Track previous params to avoid recreating store on every reactive run
  let prefetchedWatcherKey: string | undefined = $state();
  function prefetchWatchersForJob(jobId: string, hostname: string) {
    const key = `${hostname}::${jobId}`;
    if (prefetchedWatcherKey === key)
      return;
    prefetchedWatcherKey = key;
    queueMicrotask(() => {
      void prefetchJobWatchers(jobId, hostname).catch((err) => {
        console.warn('Failed to prefetch job watchers:', err);
      });
    });
  }
  $effect(() => {
    const { id, host } = params;
    if (!id || !host)
      return;
    // Only changing the job identity resets the inspector. Resource updates and
    // tab changes must not start a second fetch or discard the active stream.
    untrack(() => {
      resetOutputState();
      jobRequestVersion++;
      scriptRequestVersion++;
      notice = '';
      cancelOpen = false;
      showAttachWatchersDialog = false;
      scriptData = null;
      loadingScript = false;
      scriptError = null;
      error = null;
      activeTab = getInitialActiveTab();
      initialLoadComplete = false;
      jobStore = jobStateManager.getJob(id, host);
      jobStateManager.setCurrentViewJob(id, host);
      void loadJob();
      prefetchWatchersForJob(id, host);
    });
  });
  $effect(() => {
    const selectedJob = job;
    const outputType = getActiveOutputType();
    const identityMatches = selectedJob?.job_id === params.id && selectedJob?.hostname === params.host;
    untrack(() => {
      if (!selectedJob || !identityMatches || !outputType) {
        if (!outputType && (outputData || outputError || currentOutputType))
          resetOutputState();
        return;
      }
      if (currentOutputType !== outputType && (outputData || outputError))
        resetOutputState();
      if (!outputData && !outputError && !loadingOutput)
        void loadOutput(outputType);
    });
  });
  $effect(() => {
    if (job?.job_id === params.id && job?.hostname === params.host && activeTab === 'script') {
      untrack(() => {
        if (!scriptData && !scriptError && !loadingScript)
          void loadScript();
      });
    }
  });
  onMount(async () => {
    // Job loading is now handled by reactive statement above
    // Set navigation context for job page
    if (params.id && params.host) {
      navigationActions.setContext('job', {
        jobId: params.id,
        hostname: params.host
      });
      // Note: setCurrentViewJob is now called in the reactive block to avoid duplication
    }
  });
  onDestroy(() => {
    jobRequestVersion++;
    scriptRequestVersion++;
    resetOutputState();
    // Clear current view job
    jobStateManager.setCurrentViewJob(null, null);
  });
</script>

<section class="job-panel" class:embedded aria-label="Job detail">
  <div class="job-panel-toolbar">
    <div class="job-panel-meta">
      {#if !embedded}
        <button class="relay-text-button" onclick={restore}>
          <ArrowLeft size={16}/>
          Jobs
        </button>
      {/if}
      {#if job}
        <JobStatus state={job.state}/>
        <span class="mono">#{job.job_id}</span>
      {/if}
    </div>
    <div class="job-panel-controls">
      <IconButton label="Refresh job" disabled={loading} onclick={()=>void loadJob(true)}>
        <RefreshCw size={16} class={loading?'animate-spin':''}/>
      </IconButton>
      {#if embedded}
        <IconButton label="Maximize job" onclick={onexpand}>
          <Maximize2 size={16}/>
        </IconButton>
      {:else}
        <IconButton label="Restore split view" onclick={restore}>
          <Minimize2 size={16}/>
        </IconButton>
      {/if}
      <IconButton label="Close job" onclick={onclose}>
        <X size={18}/>
      </IconButton>
    </div>
  </div>
  {#if job}
    <div class="job-panel-heading">
      <h1>{job.name||job.job_id}</h1>
      <div>
        <Server size={14}/>
        {job.hostname}
        {#if job.user}
          <span>·</span>
          {job.user}
        {/if}
        {#if job.partition}
          <span>·</span>
          {job.partition}
        {/if}
      </div>
    </div>
  {/if}
  {#if error}
    <div class="relay-banner error" role="alert">
      <span>{error}</span>
      <button class="relay-text-button" onclick={()=>void loadJob(true)}>Retry</button>
    </div>
  {/if}
  {#if notice}
    <div class="job-panel-notice" role="status">
      <span>{notice}</span>
      <IconButton label="Dismiss message" onclick={()=>notice=''}>
        <X size={14}/>
      </IconButton>
    </div>
  {/if}
  {#if loading&&!job}
    <LoadingSpinner message="Loading job…"/>
    {:else if job}
      <nav class="relay-tabs job-panel-tabs" aria-label="Job sections">
        {#each [{id:'details',label:'Overview'},{id:'output',label:'Output'},{id:'script',label:'Script'},{id:'watchers',label:'Watchers'},{id:'activity',label:'Activity'}] as tab}
          <button class:active={activeTab===tab.id||(tab.id==='output'&&activeTab==='errors')} onclick={()=>handleTabClick(tab.id as JobTab)} aria-current={activeTab===tab.id?'page':undefined}>{tab.label}</button>
        {/each}
      </nav>
      {#if activeTab==='output'||activeTab==='errors'}
        <div class="job-output-streams" aria-label="Output stream">
          <button class:active={activeTab==='output'} onclick={()=>handleTabClick('output')}>stdout</button>
          <button class:active={activeTab==='errors'} onclick={()=>handleTabClick('errors')}>stderr</button>
        </div>
      {/if}
      <div class="job-panel-body" class:scrollable={activeTab==='details'||activeTab==='activity'}>
        {#if activeTab==='details'}
          <JobOverview {job} onwatchers={()=>handleTabClick('watchers')} oncopy={value=>void copy(value)}/>
          {:else if activeTab==='activity'}
            {#key job.hostname+':'+job.job_id}
              <JobActivity {job}/>
            {/key}
          {:else}
            <JobTabContent {job} {activeTab} {outputData} {outputError} {loadingOutput} {loadingMoreOutput} {scriptData} {scriptError} {loadingScript} onRetryLoadOutput={()=>{const type=getActiveOutputType();if(type)void loadOutput(type);}} onRetryLoadScript={loadScript} onDownloadScript={downloadScript} onRefreshOutput={refreshOutput} {refreshingOutput}/>
          {/if}
      </div>
      <footer class="job-panel-footer">
        <button class="relay-button" disabled={relaunching} onclick={()=>void relaunch()}>
          <RotateCcw size={15}/>
          {relaunching?'Preparing…':'Relaunch'}
        </button>
        <IconButton label="Attach watchers" onclick={handleAttachWatchers}>
          <Eye size={17}/>
        </IconButton>
        <IconButton label="Copy job link" onclick={handleShareJob}>
          <Copy size={17}/>
        </IconButton>
        {#if jobUtils.canCancelJob(job.state)}
          <IconButton label="Cancel job" onclick={()=>cancelOpen=true}>
            <Square size={16}/>
          </IconButton>
        {/if}
      </footer>
    {/if}
</section>

{#if showAttachWatchersDialog&&job}
  <WatcherAttachmentDialog jobId={job.job_id} hostname={job.hostname} on:close={()=>showAttachWatchersDialog=false} on:success={()=>{showAttachWatchersDialog=false;if(job)void fetchJobWatchers(job.job_id,job.hostname,{silent:true,maxAgeMs:0});}}/>
{/if}

<Dialog bind:open={cancelOpen} title="Cancel this job?" closeOnEscape={!canceling} closeOnBackdropClick={!canceling}>
  <p class="cancel-copy">Cancel #{job?.job_id} on {job?.hostname}? Running work will stop.</p>
  {#snippet footer()}
    <button class="relay-button" disabled={canceling} onclick={()=>cancelOpen=false}>Keep running</button>
    <button class="relay-button danger" disabled={canceling} onclick={()=>void handleCancelJob()}>{canceling?'Cancelling…':'Cancel job'}</button>
  {/snippet}
</Dialog>

<style>
  .job-panel {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    min-width: 0;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-card);
    overflow: hidden;
    margin: 20px 24px 24px;
  }

  .job-panel.embedded {
    height: 100%;
    margin: 0;
  }

  .job-panel-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 13px 24px 0;
  }

  .job-panel-meta,.job-panel-controls {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .job-panel-meta {
    font-size: .8125rem;
    color: var(--muted-foreground);
    min-width: 0;
  }

  .job-panel-meta>.relay-text-button {
    margin-right: 13px;
  }

  .job-panel-meta>.mono {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .job-panel-heading {
    padding: 12px 24px 23px;
  }

  .job-panel-heading h1 {
    font-size: clamp(1.5rem,2.2vw,2rem);
    line-height: 1.25;
    letter-spacing: -.03em;
    font-weight: 600;
    margin: 0 0 10px;
    overflow-wrap: anywhere;
  }

  .job-panel-heading>div {
    display: flex;
    gap: 9px;
    align-items: center;
    flex-wrap: wrap;
    color: var(--muted-foreground);
    font-size: .875rem;
  }

  .job-panel-tabs {
    padding: 0 24px;
    gap: 28px;
    flex-shrink: 0;
  }

  .job-panel-body {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .job-panel-body.scrollable {
    overflow: auto;
    display: block;
  }

  .job-panel-footer {
    display: flex;
    gap: 8px;
    align-items: center;
    border-top: 1px solid var(--border);
    padding: 12px 24px;
    flex-shrink: 0;
  }

  .job-panel-footer>.relay-button {
    margin-right: auto;
  }

  .job-panel-notice {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 8px 20px;
    color: var(--accent);
    background: var(--accent-soft);
    font-size: .8125rem;
  }

  .job-output-streams {
    display: flex;
    gap: 4px;
    padding: 12px 24px;
    flex-shrink: 0;
  }

  .job-output-streams>button {
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 5px 12px;
    font-size: .8125rem;
    background: transparent;
    color: var(--muted-foreground);
  }

  .job-output-streams>button.active {
    background: var(--secondary);
    color: var(--foreground);
    border-color: var(--border);
  }

  .job-output-streams>button:hover {
    background: var(--hover);
  }

  .embedded .job-panel-toolbar {
    padding: 12px 14px 0;
  }

  .embedded .job-panel-meta {
    gap: 7px;
    font-size: .75rem;
  }

  .embedded .job-panel-controls {
    gap: 0;
  }

  .embedded .job-panel-heading {
    padding: 10px 20px 20px;
  }

  .embedded .job-panel-heading h1 {
    font-size: 1.2rem;
  }

  .embedded .job-panel-heading>div {
    font-size: .8125rem;
  }

  .embedded .job-panel-tabs {
    padding: 0 20px;
    gap: 20px;
  }

  .embedded .job-panel-tabs button {
    font-size: .8125rem;
  }

  .embedded .job-panel-footer {
    padding: 12px 18px;
  }

  .cancel-copy {
    font-size: .9375rem;
    color: var(--muted-foreground);
  }

  @media (max-width:760px) {
    .job-panel {
      margin: 10px;
    }
    .job-panel-toolbar {
      padding: 10px 14px 0;
    }
    .job-panel-heading {
      padding: 12px 18px 20px;
    }
    .job-panel-tabs {
      padding: 0 18px;
      gap: 22px;
    }
    .job-panel-heading h1 {
      font-size: 1.4rem;
    }
    .job-panel-meta>.relay-text-button {
      margin-right: 2px;
    }
    .job-panel-controls {
      gap: 0;
    }
    .job-panel-footer {
      padding: 12px 18px;
    }
  }
</style>
