import * as vscode from 'vscode';
import { SsyncClient, JobInfo } from './client';

// ─── Log Panel (one per job) ──────────────────────────────────────────────────

export class LogPanel {
  private static readonly panels = new Map<string, LogPanel>();

  private readonly panel: vscode.WebviewPanel;
  private timer?: ReturnType<typeof setInterval>;
  private job: JobInfo;

  private constructor(job: JobInfo, private client: SsyncClient) {
    this.job = job;
    this.panel = vscode.window.createWebviewPanel(
      'ssyncLog',
      `ssync · ${job.name}`,
      { viewColumn: vscode.ViewColumn.Two, preserveFocus: true },
      { enableScripts: true, retainContextWhenHidden: true }
    );

    this.panel.onDidDispose(() => {
      LogPanel.panels.delete(job.job_id);
      if (this.timer) clearInterval(this.timer);
    });

    // Handle messages from webview (e.g. "cancel", "refresh")
    this.panel.webview.onDidReceiveMessage((msg: { command: string }) => {
      if (msg.command === 'refresh') this.fetchAndRender();
      if (msg.command === 'cancel') vscode.commands.executeCommand('ssync.cancelJob', { job: this.job, _isJobItem: true });
    });

    this.renderSkeleton();
    this.fetchAndRender();

    // Poll while the job is active
    if (job.state === 'R' || job.state === 'PD') {
      this.timer = setInterval(() => this.fetchAndRender(), 5000);
    }
  }

  static show(job: JobInfo, client: SsyncClient) {
    const existing = LogPanel.panels.get(job.job_id);
    if (existing) {
      existing.panel.reveal(vscode.ViewColumn.Two, true);
      // Refresh job state in case it changed
      existing.job = job;
      existing.fetchAndRender();
      return;
    }
    LogPanel.panels.set(job.job_id, new LogPanel(job, client));
  }

  private renderSkeleton() {
    this.panel.webview.html = buildHtml(this.job, undefined, undefined, true);
  }

  private async fetchAndRender() {
    try {
      const output = await this.client.getJobOutput(this.job.job_id, this.job.hostname);
      this.panel.webview.html = buildHtml(this.job, output.stdout, output.stderr);
      // If job finished, stop polling
      if (this.job.state !== 'R' && this.job.state !== 'PD') {
        if (this.timer) { clearInterval(this.timer); this.timer = undefined; }
      }
    } catch (err) {
      this.panel.webview.html = buildHtml(this.job, undefined, undefined, false, String(err));
    }
  }
}

// ─── HTML builder ─────────────────────────────────────────────────────────────

const STATE_COLORS: Record<string, string> = {
  R: '#4ec9b0', PD: '#dcdcaa', CD: '#569cd6',
  F: '#f44747', CA: '#808080', TO: '#ce9178',
};

const STATE_LABELS: Record<string, string> = {
  R: 'Running', PD: 'Pending', CD: 'Completed',
  F: 'Failed', CA: 'Cancelled', TO: 'Timeout',
};

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function buildHtml(
  job: JobInfo,
  stdout?: string,
  stderr?: string,
  loading = false,
  error?: string,
): string {
  const stateColor = STATE_COLORS[job.state] ?? '#808080';
  const stateLabel = STATE_LABELS[job.state] ?? job.state;
  const isActive   = job.state === 'R' || job.state === 'PD';

  const meta = [
    job.partition  && `<span>${job.partition}</span>`,
    job.cpus       && `<span>${job.cpus} CPUs</span>`,
    job.memory     && `<span>${job.memory}</span>`,
    job.nodes      && `<span>${job.nodes} node(s)</span>`,
    job.time_limit && `<span>limit ${job.time_limit}</span>`,
    job.runtime    && `<span>runtime ${job.runtime}</span>`,
  ].filter(Boolean).join('<span class="sep">·</span>');

  const outputHtml = loading
    ? `<div class="loading">Loading output…</div>`
    : error
    ? `<div class="error">${esc(error)}</div>`
    : stdout === undefined && stderr === undefined
    ? `<div class="empty">No output yet.</div>`
    : [
        stdout ? `
          <div class="section-header">
            <span class="section-label">stdout</span>
            <span class="section-lines">${stdout.split('\n').length} lines</span>
          </div>
          <pre class="log">${esc(stdout)}</pre>` : '',
        stderr ? `
          <div class="section-header">
            <span class="section-label stderr-label">stderr</span>
            <span class="section-lines">${stderr.split('\n').length} lines</span>
          </div>
          <pre class="log stderr-log">${esc(stderr)}</pre>` : '',
      ].join('');

  return /* html */ `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline';">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: var(--vscode-font-family, monospace);
    font-size: 13px;
    color: var(--vscode-foreground);
    background: var(--vscode-editor-background);
    padding: 12px 16px;
  }

  /* ── Header ── */
  .header { margin-bottom: 14px; }
  .job-title { font-size: 15px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
  .job-id { font-size: 11px; color: var(--vscode-descriptionForeground); font-family: monospace; }
  .state-badge {
    display: inline-block; padding: 1px 7px; border-radius: 10px;
    font-size: 11px; font-weight: 600; color: #1e1e1e;
    background: ${stateColor};
  }
  .meta { margin-top: 6px; color: var(--vscode-descriptionForeground); font-size: 11px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
  .sep { color: var(--vscode-editorIndentGuide-background); }

  /* ── Toolbar ── */
  .toolbar { display: flex; gap: 8px; margin-bottom: 14px; }
  button {
    padding: 3px 10px; border: 1px solid var(--vscode-button-border, transparent);
    background: var(--vscode-button-secondaryBackground);
    color: var(--vscode-button-secondaryForeground);
    border-radius: 3px; cursor: pointer; font-size: 12px;
  }
  button:hover { background: var(--vscode-button-secondaryHoverBackground); }
  button.danger { background: var(--vscode-inputValidation-errorBackground); color: #fff; }

  /* ── Section headers ── */
  .section-header { display: flex; align-items: center; gap: 8px; margin: 14px 0 4px; }
  .section-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: var(--vscode-descriptionForeground); }
  .stderr-label { color: #ce9178; }
  .section-lines { font-size: 10px; color: var(--vscode-editorLineNumber-foreground); }

  /* ── Log output ── */
  pre.log {
    white-space: pre-wrap; word-break: break-all;
    background: var(--vscode-terminal-background, #1e1e1e);
    color: var(--vscode-terminal-foreground, #cccccc);
    padding: 10px 12px; border-radius: 4px;
    font-family: var(--vscode-editor-font-family, 'Courier New', monospace);
    font-size: 12px; line-height: 1.5;
    max-height: 60vh; overflow-y: auto;
    border: 1px solid var(--vscode-panel-border, transparent);
  }
  pre.stderr-log { color: #f1948a; }

  .loading, .empty { color: var(--vscode-descriptionForeground); font-style: italic; padding: 12px 0; }
  .error { color: var(--vscode-errorForeground); padding: 8px; background: var(--vscode-inputValidation-errorBackground); border-radius: 4px; }
  .refresh-note { font-size: 10px; color: var(--vscode-editorLineNumber-foreground); margin-top: 8px; }
</style>
</head>
<body>
<div class="header">
  <div class="job-title">
    ${esc(job.name)}
    <span class="state-badge">${stateLabel}</span>
  </div>
  <div class="job-id">${esc(job.job_id)} · ${esc(job.hostname)}</div>
  ${meta ? `<div class="meta">${meta}</div>` : ''}
</div>

<div class="toolbar">
  <button onclick="refresh()">↻ Refresh</button>
  ${isActive ? `<button class="danger" onclick="cancel()">■ Cancel Job</button>` : ''}
</div>

${outputHtml}

${isActive ? `<div class="refresh-note">Auto-refreshing every 5s</div>` : ''}

<script>
  const vscode = acquireVsCodeApi();
  function refresh() { vscode.postMessage({ command: 'refresh' }); }
  function cancel()  { vscode.postMessage({ command: 'cancel'  }); }
  // Scroll stdout/stderr to bottom on load
  document.querySelectorAll('pre.log').forEach(el => { el.scrollTop = el.scrollHeight; });
</script>
</body>
</html>`;
}
