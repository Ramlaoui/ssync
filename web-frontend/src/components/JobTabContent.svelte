<script lang="ts">
  import type { JobInfo, OutputData, ScriptData } from "../types/api";
  import OutputViewer from "./OutputViewer.svelte";
  import ScriptViewer from "./ScriptViewer.svelte";
  import WatchersTab from "./WatchersTab.svelte";


  interface Props {
    job?: JobInfo | null;
    activeTab?: string;
    outputData?: OutputData | null;
    outputError?: string | null;
    loadingOutput?: boolean;
    loadingMoreOutput?: boolean;
    scriptData?: ScriptData | null;
    scriptError?: string | null;
    loadingScript?: boolean;
    onRetryLoadOutput?: () => void;
    onLoadMoreOutput?: () => void;
    onScrollToTop?: () => void;
    onScrollToBottom?: () => void;
    onRetryLoadScript?: () => void;
    onDownloadScript?: () => void;
    onRefreshOutput?: () => void;
    refreshingOutput?: boolean;
  }

  let {
    job = null,
    activeTab = 'details',
    outputData = null,
    outputError = null,
    loadingOutput = false,
    loadingMoreOutput = false,
    scriptData = null,
    scriptError = null,
    loadingScript = false,
    onRetryLoadOutput = () => {},
    onLoadMoreOutput = () => {},
    onScrollToTop = () => {},
    onScrollToBottom = () => {},
    onRetryLoadScript = () => {},
    onDownloadScript = () => {},
    onRefreshOutput = () => {},
    refreshingOutput = false
  }: Props = $props();
</script>

{#if activeTab === 'output'}
  <div class="output-section">
    {#if outputError}
      <div class="error-state">
        <span>{outputError}</span>
        <button class="retry-btn" onclick={onRetryLoadOutput}>Retry</button>
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
        <button class="retry-btn" onclick={onRetryLoadOutput}>Retry</button>
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
        <button class="retry-btn" onclick={onRetryLoadScript}>Retry</button>
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