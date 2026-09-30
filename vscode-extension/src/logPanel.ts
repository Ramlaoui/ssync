import * as vscode from 'vscode';
import { JobStore } from './jobStore';
import { JobInfo, STATES, errorMessage, isActive, jobKey, record } from './model';
import { JobOutput } from './client';
import { webviewHtml } from './webview';

/** One panel per host + job, with incremental updates and visibility-aware polling. */
export class LogPanels implements vscode.Disposable {
  private readonly panels = new Map<string, JobLog>();
  constructor(private readonly extensionUri: vscode.Uri, private readonly store: JobStore, private readonly visibilityChanged: () => void) {}
  get visible(): boolean { return [...this.panels.values()].some(panel => panel.visible); }
  show(job: JobInfo): void {
    const key = jobKey(job);
    const existing = this.panels.get(key);
    if (existing) { existing.reveal(); return; }
    this.panels.set(key, new JobLog(job, this.extensionUri, this.store, () => { this.panels.delete(key); this.visibilityChanged(); }, this.visibilityChanged));
    this.visibilityChanged();
  }
  dispose(): void { for (const panel of this.panels.values()) panel.dispose(); this.panels.clear(); }
}

class JobLog implements vscode.Disposable {
  private readonly panel: vscode.WebviewPanel;
  private readonly subscription: { dispose(): void };
  private timer?: ReturnType<typeof setTimeout>;
  private fetching = false;
  private disposed = false;
  private output?: JobOutput;
  private error?: string;
  private updatedAt?: number;
  private readonly originalClient;

  constructor(private job: JobInfo, extensionUri: vscode.Uri, private readonly store: JobStore, onDispose: () => void, visibilityChanged: () => void) {
    this.originalClient = store.client;
    this.panel = vscode.window.createWebviewPanel('ssyncLog', `ssync · ${job.name}`, vscode.ViewColumn.Two, {
      enableScripts: true, retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'media')],
    });
    this.panel.webview.html = webviewHtml(this.panel.webview, extensionUri, 'logs');
    this.subscription = store.subscribe(() => {
      if (store.client !== this.originalClient) { this.dispose(); return; }
      const current = store.find(jobKey(this.job));
      const wasActive = isActive(this.job);
      if (current) this.job = current;
      this.send();
      if (wasActive !== isActive(this.job)) { void this.fetch(); }
    });
    this.panel.onDidDispose(() => {
      this.disposed = true;
      if (this.timer) clearTimeout(this.timer);
      this.subscription.dispose();
      onDispose();
    });
    this.panel.onDidChangeViewState(() => {
      visibilityChanged();
      if (this.panel.visible) { this.send(); void this.fetch(); }
      else if (this.timer) { clearTimeout(this.timer); this.timer = undefined; }
    });
    this.panel.webview.onDidReceiveMessage((message: unknown) => {
      if (!record(message)) return;
      if (message.command === 'ready') { this.send(); void this.fetch(); }
      if (message.command === 'refresh') void this.fetch();
      if (message.command === 'cancel') void vscode.commands.executeCommand('ssync.cancelJob', { job: this.job });
      if (message.command === 'copy') {
        const content = message.stream === 'stderr' ? this.output?.stderr : this.output?.stdout;
        if (content) void vscode.env.clipboard.writeText(content);
      }
    });
  }
  get visible(): boolean { return this.panel.visible; }
  reveal(): void { this.panel.reveal(vscode.ViewColumn.Two); }
  private send(): void {
    if (this.disposed || !this.panel.visible) return;
    void this.panel.webview.postMessage({
      type: 'output', job: this.job, states: STATES, ...this.output,
      error: this.error, loading: this.fetching, updatedAt: this.updatedAt,
    });
  }
  private async fetch(): Promise<void> {
    if (this.fetching || this.disposed || !this.panel.visible) return;
    if (this.timer) { clearTimeout(this.timer); this.timer = undefined; }
    this.fetching = true;
    this.send();
    try {
      const output = await this.originalClient.getJobOutput(this.job.job_id, this.job.hostname);
      if (this.disposed) return;
      this.output = output;
      this.error = undefined;
      this.updatedAt = Date.now();
    } catch (error) { this.error = errorMessage(error); }
    finally {
      this.fetching = false;
      this.send();
      if (!this.disposed && this.panel.visible && isActive(this.job)) this.timer = setTimeout(() => { void this.fetch(); }, 5000);
    }
  }
  dispose(): void { this.panel.dispose(); }
}
