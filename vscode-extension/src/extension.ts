import * as vscode from 'vscode';
import { SsyncClient } from './client';
import { JobsTreeProvider, JobItem, HostItem } from './jobsTree';
import { LogPanel } from './logPanel';

// ─── Client factory ───────────────────────────────────────────────────────────

function buildClient(): SsyncClient {
  const cfg    = vscode.workspace.getConfiguration('ssync');
  const apiUrl = cfg.get<string>('apiUrl', 'https://localhost:8042');
  const rawKey = cfg.get<string>('apiKey', '');
  const apiKey = SsyncClient.resolveApiKey(rawKey);
  return new SsyncClient(apiUrl, apiKey);
}

// ─── Activation ───────────────────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext) {
  let client = buildClient();

  // ── Status bar ─────────────────────────────────────────────────────────────
  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 10);
  statusBar.command = 'ssync.refreshJobs';
  statusBar.text    = '$(server-process) ssync';
  statusBar.tooltip = 'ssync — click to refresh';
  statusBar.show();
  context.subscriptions.push(statusBar);

  // ── Tree provider ──────────────────────────────────────────────────────────
  const tree = new JobsTreeProvider(client);
  const treeView = vscode.window.createTreeView('ssync.jobsView', {
    treeDataProvider: tree,
    showCollapseAll: true,
  });
  context.subscriptions.push(treeView);

  const pollInterval = vscode.workspace.getConfiguration('ssync').get<number>('pollInterval', 10);
  tree.start(pollInterval);

  // ── Update status bar on tree refresh ─────────────────────────────────────
  tree.onDidChangeTreeData(() => {
    if (!tree.isOnline) {
      statusBar.text    = '$(server-process) ssync: offline';
      statusBar.tooltip = 'ssync API is offline — click to refresh';
      return;
    }
    const running = tree.countByState('R');
    const pending = tree.countByState('PD');
    const failed  = tree.countByState('F') + tree.countByState('TO');
    const parts: string[] = [];
    if (running) parts.push(`${running}R`);
    if (pending) parts.push(`${pending}PD`);
    if (failed)  parts.push(`${failed}F`);
    statusBar.text    = `$(server-process) ssync${parts.length ? ': ' + parts.join(' ') : ''}`;
    statusBar.tooltip = `ssync API online · ${running} running, ${pending} pending`;
  });

  // ── Recreate client on config change ──────────────────────────────────────
  vscode.workspace.onDidChangeConfiguration(e => {
    if (e.affectsConfiguration('ssync')) {
      client = buildClient();
      tree.updateClient(client);
      tree.refresh();
    }
  }, null, context.subscriptions);

  // ─── Commands ──────────────────────────────────────────────────────────────

  context.subscriptions.push(

    // Refresh tree
    vscode.commands.registerCommand('ssync.refreshJobs', () => {
      tree.refresh();
    }),

    // View logs for a job (called from tree item click or context menu)
    vscode.commands.registerCommand('ssync.viewLogs', (item?: JobItem | { job: { job_id: string; hostname: string; name: string; state: 'R' | 'PD' | 'CD' | 'F' | 'CA' | 'TO' | 'UNKNOWN' } }) => {
      const job = item instanceof JobItem ? item.job : (item as any)?.job;
      if (job) LogPanel.show(job, client);
    }),

    // Cancel a job
    vscode.commands.registerCommand('ssync.cancelJob', async (item?: JobItem | { job: any; _isJobItem?: boolean }) => {
      const job = item instanceof JobItem ? item.job : (item as any)?.job;
      if (!job) return;
      const answer = await vscode.window.showWarningMessage(
        `Cancel job "${job.name}" (${job.job_id})?`,
        { modal: true },
        'Cancel Job',
      );
      if (answer !== 'Cancel Job') return;
      try {
        await client.cancelJob(job.job_id, job.hostname);
        vscode.window.showInformationMessage(`Job ${job.job_id} cancelled.`);
        tree.refresh();
      } catch (err) {
        vscode.window.showErrorMessage(`Failed to cancel: ${err}`);
      }
    }),

    // Sync workspace (or a specific folder) to a host via terminal
    vscode.commands.registerCommand('ssync.syncWorkspace', async (uri?: vscode.Uri) => {
      const folder = uri?.fsPath
        ?? vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!folder) {
        vscode.window.showErrorMessage('No workspace folder open.');
        return;
      }

      const hosts = await pickHost(client);
      if (!hosts) return;

      const term = vscode.window.createTerminal({ name: `ssync sync → ${hosts}` });
      term.show();
      term.sendText(`ssync sync "${folder}" --host "${hosts}"`);
    }),

    // Submit the current/right-clicked .sh script
    vscode.commands.registerCommand('ssync.submitScript', async (uri?: vscode.Uri) => {
      const fileUri = uri ?? vscode.window.activeTextEditor?.document.uri;
      if (!fileUri) {
        vscode.window.showErrorMessage('No .sh file selected or open.');
        return;
      }

      const doc           = await vscode.workspace.openTextDocument(fileUri);
      const scriptContent = doc.getText();

      if (!scriptContent.includes('#SBATCH') && !scriptContent.includes('sbatch')) {
        const go = await vscode.window.showWarningMessage(
          'No #SBATCH directives detected. Submit anyway?',
          'Submit', 'Cancel',
        );
        if (go !== 'Submit') return;
      }

      const hostname = await pickHost(client);
      if (!hostname) return;

      // Offer sync
      const syncChoice = await vscode.window.showQuickPick(
        ['Yes — sync workspace first', 'No — just submit the script'],
        { placeHolder: 'Sync workspace before submitting?' },
      );
      if (!syncChoice) return;

      const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      const source_dir = syncChoice.startsWith('Yes') ? workspaceFolder : undefined;

      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: `Submitting to ${hostname}…`, cancellable: false },
        async () => {
          try {
            const res = await client.launchJob({ script_content: scriptContent, source_dir, host: hostname });
            if (res.success) {
              const action = await vscode.window.showInformationMessage(
                `Job submitted: ${res.job_id} on ${hostname}`,
                'View Logs',
              );
              tree.refresh();
              if (action === 'View Logs' && res.job_id) {
                // Wait a moment, then show logs for the new job
                await new Promise(r => setTimeout(r, 1500));
                await tree.refresh();
                // Find the job in the tree and open logs
                const results = await client.getJobs({ host: hostname });
                const job = results.flatMap(r => r.jobs).find(j => j.job_id === res.job_id);
                if (job) LogPanel.show(job, client);
              }
            } else {
              vscode.window.showErrorMessage(`Submission failed: ${res.message}`);
            }
          } catch (err) {
            vscode.window.showErrorMessage(`Error submitting job: ${err}`);
          }
        }
      );
    }),

    // Start ssync api server in a terminal
    vscode.commands.registerCommand('ssync.startServer', () => {
      const existing = vscode.window.terminals.find(t => t.name === 'ssync api');
      if (existing) {
        existing.show();
        return;
      }
      const term = vscode.window.createTerminal({ name: 'ssync api' });
      term.show();
      term.sendText('ssync api --foreground');
    }),
  );
}

export function deactivate() {}

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function pickHost(client: SsyncClient): Promise<string | undefined> {
  let hosts: { hostname: string }[] = [];
  try {
    hosts = await client.getHosts();
  } catch {
    // server offline — let user type manually
  }

  if (!hosts.length) {
    return vscode.window.showInputBox({
      prompt: 'ssync API unreachable — enter host name manually',
      placeHolder: 'entalpic',
    });
  }

  return vscode.window.showQuickPick(
    hosts.map(h => h.hostname),
    { placeHolder: 'Select target host' },
  );
}

