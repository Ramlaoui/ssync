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

  function formatBytes(bytes: number | null | undefined): string {
    if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return 'N/A';
    const units = ['B', 'KB', 'MB', 'GB'];
    let value = bytes;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
      value /= 1024;
      unitIndex++;
    }
    return `${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
  }

  function formatTime(value: string | null | undefined): string {
    if (!value) return 'N/A';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString();
  }

  function scriptLineCount(content: string | undefined): number {
    if (!content) return 0;
    return content.split('\n').length;
  }
</script>

{#if activeTab === 'output'}
  <div class="output-section">
    {#if outputError}
      <div class="error-state">
        <span>{outputError}</span>
        <button class="retry-btn" onclick={onRetryLoadOutput}>Retry</button>
      </div>
    {:else}
      {#if outputData?.stdout_metadata}
        <div class="metadata-strip">
          <div class="metadata-row">
            <span class="metadata-label">File</span>
            <code class="metadata-value">{outputData.stdout_metadata.path || 'N/A'}</code>
          </div>
          <div class="metadata-row">
            <span class="metadata-label">Exists</span>
            <span class="metadata-value">{outputData.stdout_metadata.exists ? 'Yes' : 'No'}</span>
          </div>
          <div class="metadata-row">
            <span class="metadata-label">Size</span>
            <span class="metadata-value">{formatBytes(outputData.stdout_metadata.size_bytes)}</span>
          </div>
          <div class="metadata-row">
            <span class="metadata-label">Updated</span>
            <span class="metadata-value">{formatTime(outputData.stdout_metadata.last_modified)}</span>
          </div>
          {#if outputData.stdout_metadata.access_path}
            <div class="metadata-row">
              <span class="metadata-label">Open</span>
              <a class="metadata-link" href={outputData.stdout_metadata.access_path} target="_blank" rel="noopener noreferrer">raw file</a>
            </div>
          {/if}
        </div>
      {/if}
      {#if outputData?.content_truncated}
        <div class="output-notice">
          Showing a bounded tail for speed. Use the raw file link for the full log.
        </div>
      {/if}
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
      {#if outputData?.stderr_metadata}
        <div class="metadata-strip">
          <div class="metadata-row">
            <span class="metadata-label">File</span>
            <code class="metadata-value">{outputData.stderr_metadata.path || 'N/A'}</code>
          </div>
          <div class="metadata-row">
            <span class="metadata-label">Exists</span>
            <span class="metadata-value">{outputData.stderr_metadata.exists ? 'Yes' : 'No'}</span>
          </div>
          <div class="metadata-row">
            <span class="metadata-label">Size</span>
            <span class="metadata-value">{formatBytes(outputData.stderr_metadata.size_bytes)}</span>
          </div>
          <div class="metadata-row">
            <span class="metadata-label">Updated</span>
            <span class="metadata-value">{formatTime(outputData.stderr_metadata.last_modified)}</span>
          </div>
          {#if outputData.stderr_metadata.access_path}
            <div class="metadata-row">
              <span class="metadata-label">Open</span>
              <a class="metadata-link" href={outputData.stderr_metadata.access_path} target="_blank" rel="noopener noreferrer">raw file</a>
            </div>
          {/if}
        </div>
      {/if}
      {#if outputData?.content_truncated}
        <div class="output-notice">
          Showing a bounded tail for speed. Use the raw file link for the full log.
        </div>
      {/if}
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
      {#if scriptData}
        <div class="metadata-strip">
          <div class="metadata-row">
            <span class="metadata-label">Characters</span>
            <span class="metadata-value">{scriptData.content_length.toLocaleString()} chars</span>
          </div>
          <div class="metadata-row">
            <span class="metadata-label">Lines</span>
            <span class="metadata-value">{scriptLineCount(scriptData.script_content)}</span>
          </div>
          {#if scriptData.local_source_dir}
            <div class="metadata-row">
              <span class="metadata-label">Source Dir</span>
              <code class="metadata-value">{scriptData.local_source_dir}</code>
            </div>
          {/if}
        </div>
      {/if}
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

  .metadata-strip {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 0.35rem 0.75rem;
    padding: 0.6rem 0.8rem;
    margin-bottom: 0.5rem;
    border: 1px solid var(--border);
    border-radius: 0.625rem;
    background: var(--secondary);
  }

  .output-notice {
    margin-bottom: 0.5rem;
    padding: 0.55rem 0.75rem;
    border: 1px solid color-mix(in srgb, var(--accent) 18%, transparent);
    border-radius: 0.625rem;
    background: color-mix(in srgb, var(--accent) 7%, var(--card));
    color: var(--muted-foreground);
    font-size: 0.78rem;
  }

  .metadata-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
    font-size: 0.75rem;
  }

  .metadata-label {
    color: var(--muted-foreground);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    flex-shrink: 0;
  }

  .metadata-value {
    color: var(--foreground);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }

  .metadata-link {
    color: var(--accent);
    text-decoration: underline;
    font-weight: 600;
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
