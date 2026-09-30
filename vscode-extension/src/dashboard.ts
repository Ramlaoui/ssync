import * as vscode from 'vscode';
import { JobStore } from './jobStore';
import { STATES, record } from './model';
import { webviewHtml } from './webview';

export class Dashboard implements vscode.Disposable {
  private panel?: vscode.WebviewPanel;
  private readonly subscription: { dispose(): void };
  constructor(private readonly extensionUri: vscode.Uri, private readonly store: JobStore, private readonly visibilityChanged: () => void) {
    this.subscription = store.subscribe(() => this.send());
  }
  get visible(): boolean { return !!this.panel?.visible; }
  show(): void {
    if (this.panel) { this.panel.reveal(); return; }
    const panel = vscode.window.createWebviewPanel('ssyncDashboard', 'ssync · Jobs', vscode.ViewColumn.One, {
      enableScripts: true, retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, 'media')],
    });
    this.panel = panel;
    panel.webview.html = webviewHtml(panel.webview, this.extensionUri, 'dashboard');
    panel.onDidChangeViewState(() => { this.visibilityChanged(); this.send(); });
    panel.onDidDispose(() => { this.panel = undefined; this.visibilityChanged(); });
    panel.webview.onDidReceiveMessage((message: unknown) => {
      if (!record(message)) return;
      if (message.command === 'ready') this.send();
      const commands: Record<string, string> = {
        refresh: 'ssync.refreshJobs', submit: 'ssync.submitScript', sync: 'ssync.syncWorkspace',
        configure: 'ssync.configure', startServer: 'ssync.startServer',
      };
      if (typeof message.command === 'string' && Object.hasOwn(commands, message.command)) {
        void vscode.commands.executeCommand(commands[message.command]);
      }
      if (['open', 'cancel'].includes(String(message.command)) && typeof message.key === 'string') {
        const job = this.store.find(message.key);
        if (job) void vscode.commands.executeCommand(message.command === 'open' ? 'ssync.viewLogs' : 'ssync.cancelJob', { job });
      }
    });
    this.visibilityChanged();
  }
  private send(): void {
    if (this.panel?.visible) void this.panel.webview.postMessage({ type: 'snapshot', ...this.store.snapshot, states: STATES });
  }
  dispose(): void { this.subscription.dispose(); this.panel?.dispose(); }
}
