import * as vscode from 'vscode';
import { SsyncClient, isLoopback, serverUrl } from './client';
import { JobStore, MonitorOptions } from './jobStore';
import { JobsTreeProvider } from './jobsTree';
import { Dashboard } from './dashboard';
import { LogPanels } from './logPanel';
import { cancelJob, commandJob, safeCommand, submitScript, syncWorkspace } from './workflows';
import { errorMessage } from './model';

const DEFAULT_URL = 'https://localhost:8042';
function monitorOptions(): MonitorOptions {
  const config = vscode.workspace.getConfiguration('ssync');
  return {
    pollInterval: config.get<number>('pollInterval', 120),
    showCompleted: config.get<boolean>('showCompletedJobs', true),
    since: config.get<string>('completedJobsWindow', '3d'),
  };
}
function secretName(url: string): string { return `ssync.apiKey:${serverUrl(url).toString()}`; }
async function createClient(context: vscode.ExtensionContext): Promise<SsyncClient> {
  const config = vscode.workspace.getConfiguration('ssync');
  const url = config.get<string>('apiUrl', DEFAULT_URL);
  try { serverUrl(url); } catch (error) {
    // Keep the UI available, but never send requests to an unintended server.
    return new SsyncClient(DEFAULT_URL, '', 30_000, true, `Invalid server URL. ${errorMessage(error)} Run ssync: Configure Connection.`);
  }
  const saved = await context.secrets.get(secretName(url));
  const legacy = config.get<string>('apiKey', '');
  const key = saved ?? (isLoopback(serverUrl(url)) ? SsyncClient.resolveApiKey(legacy) : legacy);
  return new SsyncClient(url, key, config.get<number>('requestTimeout', 30) * 1000, config.get<boolean>('trustLocalCertificate', true));
}

async function configure(context: vscode.ExtensionContext): Promise<void> {
  const config = vscode.workspace.getConfiguration('ssync');
  const url = await vscode.window.showInputBox({
    title: 'ssync · Server URL', value: config.get<string>('apiUrl', DEFAULT_URL),
    prompt: 'Address of your ssync server',
    validateInput: value => { try { serverUrl(value); return undefined; } catch { return 'Enter an HTTP(S) URL without credentials, query, or fragment.'; } },
  });
  if (!url) return;
  const choice = await vscode.window.showQuickPick(['Keep existing key / use local key file', 'Set API key', 'Remove saved API key'], { title: 'ssync · Authentication' });
  if (!choice) return;
  if (choice === 'Set API key') {
    const key = await vscode.window.showInputBox({ title: 'ssync · API key', password: true, ignoreFocusOut: true, prompt: 'Stored in VS Code SecretStorage for this server', validateInput: value => value.trim() ? undefined : 'Enter an API key.' });
    if (key === undefined) return;
    await context.secrets.store(secretName(url), key.trim());
  }
  if (choice === 'Remove saved API key') await context.secrets.delete(secretName(url));
  await config.update('apiUrl', serverUrl(url).toString().replace(/\/$/, ''), vscode.ConfigurationTarget.Global);
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  let disposed = false;
  context.subscriptions.push({ dispose: () => { disposed = true; } });
  const store = new JobStore(await createClient(context), monitorOptions());
  const tree = new JobsTreeProvider(store);
  const treeView = vscode.window.createTreeView('ssync.jobsView', { treeDataProvider: tree, showCollapseAll: true });
  const syncMonitoring = () => {
    if (disposed) return;
    if (treeView.visible || dashboard.visible || logs.visible) store.start();
    else store.stop();
  };
  const dashboard = new Dashboard(context.extensionUri, store, syncMonitoring);
  const logs = new LogPanels(context.extensionUri, store, syncMonitoring);
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 10);
  status.command = 'ssync.openDashboard';
  const updateStatus = () => {
    const snapshot = store.snapshot;
    const running = snapshot.jobs.filter(job => job.state === 'R').length;
    const queued = snapshot.jobs.filter(job => job.state === 'PD').length;
    status.text = `${snapshot.refreshing ? '$(sync~spin)' : '$(server-process)'} ssync${snapshot.error ? ': offline' : ` · ${running} running · ${queued} queued`}`;
    status.tooltip = `${snapshot.error ?? `Connection: ${snapshot.connection}`}\nClick to open Jobs`;
    treeView.message = snapshot.error ? 'Last known jobs · retry to update' : snapshot.connection === 'live' ? 'Live updates' : snapshot.connection === 'polling' ? 'Polling · reconnecting to live updates' : undefined;
    treeView.badge = running ? { value: running, tooltip: `${running} running jobs` } : undefined;
  };
  status.show();
  updateStatus();
  context.subscriptions.push(store, tree, treeView, dashboard, logs, status,
    store.subscribe(updateStatus), treeView.onDidChangeVisibility(syncMonitoring));

  // Serialize async secret reads so older configuration cannot win a race.
  let configurationUpdate = Promise.resolve();
  const rebuild = () => {
    configurationUpdate = configurationUpdate.then(async () => {
      const client = await createClient(context);
      if (disposed) { client.dispose(); return; }
      store.update(client, monitorOptions());
      syncMonitoring();
    }).catch(error => { void vscode.window.showErrorMessage(`ssync: ${errorMessage(error)}`); });
  };
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(event => { if (event.affectsConfiguration('ssync')) rebuild(); }));
  context.subscriptions.push(context.secrets.onDidChange(event => { if (event.key.startsWith('ssync.apiKey:')) rebuild(); }));

  let submitting = false;
  context.subscriptions.push(
    vscode.commands.registerCommand('ssync.openDashboard', () => dashboard.show()),
    vscode.commands.registerCommand('ssync.configure', safeCommand(() => configure(context))),
    vscode.commands.registerCommand('ssync.refreshJobs', () => { syncMonitoring(); return store.refresh(true); }),
    vscode.commands.registerCommand('ssync.viewLogs', (argument?: unknown) => { const job = commandJob(argument, store); if (job) logs.show(job); }),
    vscode.commands.registerCommand('ssync.cancelJob', safeCommand(async (argument?: unknown) => { const job = commandJob(argument, store); if (job) await cancelJob(job, store); })),
    vscode.commands.registerCommand('ssync.syncWorkspace', safeCommand((uri?: vscode.Uri) => syncWorkspace(store, uri))),
    vscode.commands.registerCommand('ssync.submitScript', safeCommand(async (uri?: vscode.Uri) => {
      if (submitting) { void vscode.window.showInformationMessage('A submission is already in progress.'); return; }
      submitting = true;
      try { await submitScript(store, job => logs.show(job), uri); } finally { submitting = false; }
    })),
    vscode.commands.registerCommand('ssync.startServer', () => {
      if (!vscode.workspace.isTrusted) { void vscode.window.showErrorMessage('Trust this workspace before starting the server.'); return; }
      const existing = vscode.window.terminals.find(item => item.name === 'ssync web');
      const terminal = existing ?? vscode.window.createTerminal({ name: 'ssync web' });
      terminal.show();
      if (!existing) terminal.sendText('ssync web --foreground --no-browser');
    }),
  );
  syncMonitoring();
}
