<script lang="ts">
  import type { JobInfo, OutputData, ScriptData } from "../types/api";
  import OutputViewer from "./OutputViewer.svelte";
  import ScriptViewer from "./ScriptViewer.svelte";
  import WatchersTab from "./WatchersTab.svelte";
  import Dialog from '../lib/components/ui/Dialog.svelte';
  import { Info, Download } from 'lucide-svelte';


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
    onOutputTypeChange?: (type: 'stdout' | 'stderr') => void;
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
    refreshingOutput = false,
    onOutputTypeChange = () => {}
  }: Props = $props();

  let fileDetailsOpen = $state(false);
  const outputType = $derived(activeTab === 'errors' ? 'stderr' : 'stdout');
  const outputMetadata = $derived(outputType === 'stdout' ? outputData?.stdout_metadata : outputData?.stderr_metadata);

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

  function streamContent(outputType: 'stdout' | 'stderr'): string {
    return (outputType === 'stdout' ? outputData?.stdout : outputData?.stderr) || '';
  }

  function isOutputPending(outputType: 'stdout' | 'stderr'): boolean {
    return Boolean(outputData?.refresh_queued && !streamContent(outputType));
  }

  function existsLabel(exists: boolean | null | undefined, pending: boolean): string {
    if (pending && !exists) return 'Checking';
    if (exists === null || exists === undefined) return 'Unknown';
    return exists ? 'Yes' : 'No';
  }
</script>

{#if activeTab === 'output' || activeTab === 'errors'}
  <div class="output-section">
    {#if outputError}
      <div class="output-error" role="alert">
        <span>{outputError}</span>
        <button class="relay-text-button" onclick={onRetryLoadOutput}>Retry</button>
      </div>
    {/if}
    <OutputViewer
      content={streamContent(outputType)}
      isLoading={loadingOutput}
      isPending={isOutputPending(outputType)}
      pendingMessage="Retrieving output…"
      hasMoreContent={loadingMoreOutput}
      onLoadMore={onLoadMoreOutput}
      onScrollToTop={onScrollToTop}
      onScrollToBottom={onScrollToBottom}
      type={outputType === 'stdout' ? 'output' : 'error'}
      isStreaming={job?.state === 'R'}
      onRefresh={onRefreshOutput}
      refreshing={refreshingOutput}
    >
      {#snippet toolbarStart()}
        <select class="output-stream-select" aria-label="Output stream" value={outputType} onchange={event=>onOutputTypeChange(event.currentTarget.value as 'stdout' | 'stderr')}>
          <option value="stdout">stdout</option>
          <option value="stderr">stderr</option>
        </select>
        {#if outputData?.content_truncated}
          <button class="output-preview" title="Showing the beginning and latest output. Open the full log for all lines." onclick={()=>fileDetailsOpen=true}>Preview</button>
        {/if}
      {/snippet}
      {#snippet toolbarEnd()}
        <button class="output-tool" aria-label="File details" title="File details" onclick={()=>fileDetailsOpen=true}><Info size={16}/></button>
        {#if outputMetadata?.access_path}
          <a class="output-tool" href={outputMetadata.access_path} target="_blank" rel="noopener noreferrer" aria-label={`Open full ${outputType} log`} title={`Open full ${outputType} log`}><Download size={16}/></a>
        {/if}
      {/snippet}
    </OutputViewer>
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

<Dialog bind:open={fileDetailsOpen} title={`${outputType} file`} size="sm">
  <dl class="file-details">
    <dt>Path</dt>
    <dd class="font-mono break-all">{outputMetadata?.path || (outputType === 'stdout' ? job?.stdout_file : job?.stderr_file) || 'Not available'}</dd>
    <dt>Exists</dt>
    <dd>{existsLabel(outputMetadata?.exists, isOutputPending(outputType))}</dd>
    <dt>Size</dt>
    <dd>{formatBytes(outputMetadata?.size_bytes)}</dd>
    <dt>Updated</dt>
    <dd>{formatTime(outputMetadata?.last_modified)}</dd>
  </dl>
  {#if outputData?.content_truncated}
    <p class="mt-4 text-sm text-muted-foreground">This preview contains the beginning and latest output. Open the full log to see all lines.</p>
  {/if}
  {#if outputMetadata?.access_path}
    <a class="relay-button mt-4" href={outputMetadata.access_path} target="_blank" rel="noopener noreferrer"><Download size={16}/>Open full log</a>
  {/if}
</Dialog>

<style>
  .output-section {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    height: 100%;
    min-height: 0;
    min-width: 0;
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

  .output-stream-select {
    width: 88px;
    min-height: 30px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--card);
    color: var(--foreground);
    padding: 3px 22px 3px 8px;
    font-size: .8125rem;
    flex-shrink: 0;
  }

  .output-tool {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 30px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--muted-foreground);
    flex-shrink: 0;
  }

  .output-tool:hover,.output-preview:hover {
    color: var(--foreground);
    background: var(--hover);
  }

  .output-preview {
    padding: 3px 6px;
    border-radius: 4px;
    border: 0;
    color: var(--muted-foreground);
    background: var(--secondary);
    font-size: .6875rem;
  }

  @container (max-width:350px) {
    .output-stream-select { width: 72px; }
    .output-preview { width: 22px; height: 24px; padding: 0; font-size: 0; }
    .output-preview::after { content: '…'; font-size: .875rem; }
  }

  .file-details {
    display: grid;
    gap: 6px;
    font-size: .8125rem;
  }

  .file-details dt {
    margin-top: 8px;
    color: var(--muted-foreground);
  }

  .file-details dd {
    margin: 0;
  }

  .output-error {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 8px 12px;
    color: var(--destructive);
    font-size: .8125rem;
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
