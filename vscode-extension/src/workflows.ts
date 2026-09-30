import * as vscode from 'vscode';
import * as path from 'path';
import { SsyncClient, isLoopback } from './client';
import { JobStore } from './jobStore';
import { JobInfo, errorMessage, isActive, jobKey, parseJob, record } from './model';

export function commandJob(argument: unknown, store: JobStore): JobInfo | undefined {
  if (!record(argument) || !record(argument.job)) return;
  try { const job = parseJob(argument.job); return store.find(jobKey(job)) ?? job; } catch { return; }
}

export async function pickHost(client: SsyncClient): Promise<string | undefined> {
  const hosts = await client.getHosts();
  if (!hosts.length) { void vscode.window.showInformationMessage('No hosts configured. Add a cluster to your ssync config first.'); return; }
  const picked = await vscode.window.showQuickPick(hosts.map(host => ({ label: host.hostname, description: 'Configured cluster' })), {
    title: 'ssync · Target cluster', placeHolder: 'Choose where to run',
  });
  return picked?.label;
}

export async function cancelJob(job: JobInfo, store: JobStore): Promise<void> {
  if (!isActive(job)) { void vscode.window.showInformationMessage('This job is already finished.'); return; }
  const client = store.client;
  const confirmed = await vscode.window.showWarningMessage(`Cancel ${job.name} (${job.job_id}) on ${job.hostname}?`, { modal: true }, 'Cancel Job');
  if (confirmed !== 'Cancel Job') return;
  if (client !== store.client) throw new Error('Connection changed. Review the job and cancel again.');
  await client.cancelJob(job.job_id, job.hostname);
  await store.refresh(true);
  void vscode.window.showInformationMessage(`Cancellation requested for ${job.job_id} on ${job.hostname}.`);
}

export async function syncWorkspace(store: JobStore, uri?: vscode.Uri): Promise<void> {
  if (!vscode.workspace.isTrusted) throw new Error('Trust this workspace before syncing files.');
  const folder = uri ? vscode.workspace.getWorkspaceFolder(uri) : await vscode.window.showWorkspaceFolderPick({ placeHolder: 'Workspace to sync' });
  const target = uri ?? folder?.uri;
  if (!target) return;
  if (target.scheme !== 'file') throw new Error('Open a local workspace folder to sync.');
  const client = store.client;
  if (!isLoopback(client.url)) throw new Error('Workspace sync uses your local ssync CLI. Configure a local server to sync from this machine.');
  const hostname = await pickHost(client);
  if (!hostname) return;
  if (client !== store.client) throw new Error('Connection changed. Review the target and sync again.');
  // VS Code handles shell quoting for the platform; no interpolated command strings.
  const task = new vscode.Task({ type: 'ssync', operation: 'sync' }, folder ?? vscode.TaskScope.Workspace,
    `Sync to ${hostname}`, 'ssync', new vscode.ShellExecution('ssync', ['sync', target.fsPath, '--host', hostname]));
  task.presentationOptions = { reveal: vscode.TaskRevealKind.Always, panel: vscode.TaskPanelKind.Dedicated };
  await vscode.tasks.executeTask(task);
}

export async function submitScript(store: JobStore, showJob: (job: JobInfo) => void, uri?: vscode.Uri): Promise<void> {
  if (!vscode.workspace.isTrusted) throw new Error('Trust this workspace before submitting scripts.');
  const client = store.client;
  const file = uri ?? (vscode.window.activeTextEditor?.document.languageId === 'shellscript' ? vscode.window.activeTextEditor.document.uri : undefined)
    ?? (await vscode.window.showOpenDialog({ canSelectMany: false, filters: { 'Shell scripts': ['sh'] }, title: 'Script to submit' }))?.[0];
  if (!file) return;
  if (!['file', 'vscode-remote'].includes(file.scheme)) throw new Error('Choose a local or Remote SSH shell script.');
  const document = await vscode.workspace.openTextDocument(file);
  const content = document.getText();
  if (!content.trim()) throw new Error('The selected script is empty.');
  const host = await pickHost(client);
  if (!host) return;
  const folder = vscode.workspace.getWorkspaceFolder(file);
  const canSync = !!folder && folder.uri.scheme === 'file' && isLoopback(client.url);
  const choices = [
    ...(canSync ? [{ label: 'Sync project and submit', description: folder.uri.fsPath, sync: true }] : []),
    { label: 'Submit script only', description: 'Use files already on the cluster', sync: false },
  ];
  const choice = await vscode.window.showQuickPick(choices, { title: 'ssync · Submission', placeHolder: 'Choose what to send' });
  if (!choice) return;
  const source = choice.sync ? folder?.uri.fsPath : undefined;
  const confirmed = await vscode.window.showInformationMessage(`Submit ${path.basename(file.fsPath)} to ${host}?`, {
    modal: true,
    detail: `${source ? `Sync: ${source}` : 'Submit script only'}\n${document.isDirty ? 'Uses the current unsaved editor contents.\n' : ''}${!content.includes('#SBATCH') ? 'No #SBATCH directives; cluster defaults will apply.' : 'Resource directives are read from the script.'}`,
  }, 'Submit');
  if (confirmed !== 'Submit') return;
  if (client !== store.client) throw new Error('Connection changed. Review the target and submit again.');

  await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: `ssync · ${host}`, cancellable: true }, async (progress, token) => {
    progress.report({ message: source ? 'Starting sync and submission…' : 'Submitting script…' });
    let response;
    try { response = await client.launchJob({ script_content: content, source_dir: source, host }); }
    catch (error) { throw new Error(`${errorMessage(error)} Submission status is unknown; check Jobs before submitting again.`); }
    if (response.requires_confirmation) throw new Error(response.message || 'The server requires launch confirmation. Review the launch in the ssync web app.');
    if (!response.success) throw new Error(response.message);
    let jobId = response.job_id;
    if (!jobId && response.launch_id) {
      const launchId = response.launch_id;
      const deadline = Date.now() + 15 * 60_000;
      while (!token.isCancellationRequested && Date.now() < deadline) {
        let status;
        try { status = await client.getLaunchStatus(launchId); }
        catch (error) { throw new Error(`${errorMessage(error)} Launch ${launchId} may still be running. Check Jobs before submitting again.`); }
        progress.report({ message: status.message || status.stage });
        if (status.terminal) {
          if (!status.success || !status.job_id) throw new Error(status.message || 'Launch failed.');
          jobId = status.job_id;
          break;
        }
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      if (!jobId) {
        void vscode.window.showInformationMessage(`Stopped watching launch ${launchId}. The server may still submit it. Check ssync Jobs before submitting again.`);
        return;
      }
    }
    if (!jobId) throw new Error('The server did not return a job or launch ID. Check Jobs before submitting again.');
    await store.refresh(true);
    const action = await vscode.window.showInformationMessage(`Submitted job ${jobId} on ${host}.`, 'Open Job');
    if (action === 'Open Job') showJob(store.snapshot.jobs.find(job => job.hostname === host && job.job_id === jobId) ?? {
      job_id: jobId, hostname: host, name: path.basename(file.fsPath), state: 'PD',
    });
  });
}

export function safeCommand<Args extends unknown[]>(action: (...args: Args) => Promise<void>): (...args: Args) => Promise<void> {
  return async (...args) => {
    try { await action(...args); }
    catch (error) { void vscode.window.showErrorMessage(`ssync: ${errorMessage(error)}`); }
  };
}
