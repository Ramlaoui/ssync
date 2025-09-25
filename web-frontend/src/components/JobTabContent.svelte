<script lang="ts">
  import type { JobInfo, OutputData, ScriptData } from "../types/api";
  import OutputViewer from "./OutputViewer.svelte";
  import ScriptViewer from "./ScriptViewer.svelte";
  import WatchersTab from "./WatchersTab.svelte";

  export let job: JobInfo | null = null;
  export let activeTab: string = 'details';
  export let outputData: OutputData | null = null;
  export let outputError: string | null = null;
  export let loadingOutput: boolean = false;
  export let loadingMoreOutput: boolean = false;
  export let scriptData: ScriptData | null = null;
  export let scriptError: string | null = null;
  export let loadingScript: boolean = false;

  export let onRetryLoadOutput: () => void = () => {};
  export let onLoadMoreOutput: () => void = () => {};
  export let onScrollToTop: () => void = () => {};
  export let onScrollToBottom: () => void = () => {};
  export let onRetryLoadScript: () => void = () => {};
  export let onDownloadScript: () => void = () => {};
  export let onRefreshOutput: () => void = () => {};
  export let refreshingOutput: boolean = false;
</script>

{#if activeTab === 'output'}
  <div class="output-section">
    {#if outputError}
      <div class="error-state">
        <span>{outputError}</span>
        <button class="retry-btn" on:click={onRetryLoadOutput}>Retry</button>
      </div>
    {:else}
      <OutputViewer
        content={outputData?.stdout || ''}
        isLoading={loadingOutput}
        hasMoreContent={loadingMoreOutput}
        onLoadMore={onLoadMoreOutput}
        onScrollToTop={onScrollToTop}
        onScrollToBottom={onScrollToBottom}
        type="output"
        isStreaming={job?.state === 'R'}
        onRefresh={onRefreshOutput}
        refreshing={refreshingOutput}
      />
    {/if}
  </div>

{:else if activeTab === 'errors'}
  <div class="output-section">
    {#if outputError}
      <div class="error-state">
        <span>{outputError}</span>
        <button class="retry-btn" on:click={onRetryLoadOutput}>Retry</button>
      </div>
    {:else}
      <OutputViewer
        content={outputData?.stderr || ''}
        isLoading={loadingOutput}
        hasMoreContent={loadingMoreOutput}
        onLoadMore={onLoadMoreOutput}
        onScrollToTop={onScrollToTop}
        onScrollToBottom={onScrollToBottom}
        type="error"
        isStreaming={job?.state === 'R'}
        onRefresh={onRefreshOutput}
        refreshing={refreshingOutput}
      />
    {/if}
  </div>

{:else if activeTab === 'script'}
  <div class="output-section">
    {#if scriptError}
      <div class="error-state">
        <span>{scriptError}</span>
        <button class="retry-btn" on:click={onRetryLoadScript}>Retry</button>
      </div>
    {:else}
      <ScriptViewer
        content={scriptData?.script_content || ''}
        isLoading={loadingScript}
        onDownload={onDownloadScript}
        onScrollToTop={onScrollToTop}
        onScrollToBottom={onScrollToBottom}
        fileName={`job_${job?.job_id || 'unknown'}_script.sh`}
      />
    {/if}
  </div>

{:else if activeTab === 'watchers'}
  <div class="output-section">
    {#if job}
      <WatchersTab {job} />
    {/if}
  </div>
{/if}

<style>
  .output-section {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    height: 100%;
  }

  .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex: 1;
    gap: 1rem;
    color: #dc2626;
    font-size: 0.875rem;
  }

  .retry-btn {
    padding: 0.5rem 1rem;
    background: #ef4444;
    color: white;
    border: none;
    border-radius: 0.375rem;
    cursor: pointer;
    font-size: 0.875rem;
    transition: background-color 0.2s;
  }

  .retry-btn:hover {
    background: #dc2626;
  }
</style>