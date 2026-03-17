import * as vscode from 'vscode';
import { SsyncClient, JobInfo, JobStatusResult } from './client';

// ─── Icons ────────────────────────────────────────────────────────────────────

const STATE_ICONS: Record<string, string> = {
  PD: 'clock',
  R:  'play-circle',
  CD: 'check',
  F:  'error',
  CA: 'circle-slash',
  TO: 'watch',
};

const STATE_LABELS: Record<string, string> = {
  PD: 'Pending',
  R:  'Running',
  CD: 'Completed',
  F:  'Failed',
  CA: 'Cancelled',
  TO: 'Timeout',
};

// ─── Tree items ───────────────────────────────────────────────────────────────

export class HostItem extends vscode.TreeItem {
  constructor(
    public readonly hostname: string,
    public readonly jobs: JobInfo[],
  ) {
    super(hostname, vscode.TreeItemCollapsibleState.Expanded);
    const running  = jobs.filter(j => j.state === 'R').length;
    const pending  = jobs.filter(j => j.state === 'PD').length;
    const failed   = jobs.filter(j => j.state === 'F' || j.state === 'TO').length;
    const parts: string[] = [];
    if (running)  parts.push(`${running} running`);
    if (pending)  parts.push(`${pending} pending`);
    if (failed)   parts.push(`${failed} failed`);
    this.description = parts.length ? parts.join(', ') : 'no active jobs';
    this.iconPath = new vscode.ThemeIcon('server');
    this.contextValue = 'host';
  }
}

export class JobItem extends vscode.TreeItem {
  constructor(public readonly job: JobInfo) {
    super(job.name, vscode.TreeItemCollapsibleState.None);

    const stateLabel = STATE_LABELS[job.state] ?? job.state;
    const runtime    = job.runtime ? ` · ${job.runtime}` : '';
    const reason     = job.state === 'PD' && job.reason ? ` (${job.reason})` : '';
    this.description = `${stateLabel}${runtime}${reason}`;

    this.tooltip = new vscode.MarkdownString(
      `**${job.name}** \`${job.job_id}\`\n\n` +
      `- Host: ${job.hostname}\n` +
      (job.partition  ? `- Partition: ${job.partition}\n`   : '') +
      (job.cpus       ? `- CPUs: ${job.cpus}\n`             : '') +
      (job.memory     ? `- Memory: ${job.memory}\n`         : '') +
      (job.nodes      ? `- Nodes: ${job.nodes}\n`           : '') +
      (job.time_limit ? `- Time limit: ${job.time_limit}\n` : '') +
      (job.work_dir   ? `- Dir: \`${job.work_dir}\`\n`      : '')
    );

    this.iconPath = new vscode.ThemeIcon(
      STATE_ICONS[job.state] ?? 'question',
      job.state === 'R' ? new vscode.ThemeColor('charts.green')   :
      job.state === 'F' ? new vscode.ThemeColor('charts.red')     :
      job.state === 'TO'? new vscode.ThemeColor('charts.orange')  :
      job.state === 'CD'? new vscode.ThemeColor('charts.blue')    :
      undefined
    );

    this.contextValue =
      job.state === 'R'  ? 'job-running'  :
      job.state === 'PD' ? 'job-pending'  :
      'job';

    // Double-click / Enter opens logs
    this.command = {
      command: 'ssync.viewLogs',
      title: 'View Logs',
      arguments: [this],
    };
  }
}

export class MessageItem extends vscode.TreeItem {
  constructor(label: string, icon: string, command?: vscode.Command) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon(icon);
    this.contextValue = 'message';
    if (command) this.command = command;
  }
}

type AnyItem = HostItem | JobItem | MessageItem;

// ─── Provider ─────────────────────────────────────────────────────────────────

export class JobsTreeProvider implements vscode.TreeDataProvider<AnyItem> {
  private readonly _onChange = new vscode.EventEmitter<AnyItem | undefined>();
  readonly onDidChangeTreeData = this._onChange.event;

  private results: JobStatusResult[] = [];
  private status: 'unknown' | 'online' | 'offline' = 'unknown';
  private timer?: ReturnType<typeof setInterval>;

  constructor(private client: SsyncClient) {}

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  start(intervalSecs: number) {
    this.poll();
    this.timer = setInterval(() => this.poll(), intervalSecs * 1000);
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
  }

  refresh() {
    return this.poll();
  }

  private async poll() {
    const cfg = vscode.workspace.getConfiguration('ssync');
    const showCompleted  = cfg.get<boolean>('showCompletedJobs', true);
    const since          = cfg.get<string>('completedJobsWindow', '3d');
    const alive = await this.client.health();
    if (!alive) {
      this.status = 'offline';
      this.results = [];
      this._onChange.fire(undefined);
      return;
    }
    try {
      this.results = await this.client.getJobs({ since: showCompleted ? since : '0' });
      this.status = 'online';
    } catch {
      this.status = 'online'; // server is up but query failed
      this.results = [];
    }
    this._onChange.fire(undefined);
  }

  // ── TreeDataProvider ───────────────────────────────────────────────────────

  getTreeItem(el: AnyItem): vscode.TreeItem {
    return el;
  }

  getChildren(el?: AnyItem): AnyItem[] {
    if (!el) return this.roots();
    if (el instanceof HostItem) {
      return el.jobs.map(j => new JobItem(j));
    }
    return [];
  }

  private roots(): AnyItem[] {
    if (this.status === 'unknown') {
      return [new MessageItem('Connecting to ssync API…', 'loading~spin')];
    }
    if (this.status === 'offline') {
      return [
        new MessageItem('ssync API offline', 'error', {
          command: 'ssync.startServer',
          title: 'Start Server',
        }),
        new MessageItem('Click here to start server', 'server-process', {
          command: 'ssync.startServer',
          title: 'Start Server',
        }),
      ];
    }
    if (!this.results.length) {
      return [new MessageItem('No jobs found', 'info')];
    }
    return this.results
      .filter(r => r.jobs.length > 0)
      .map(r => new HostItem(r.hostname, r.jobs));
  }

  updateClient(client: SsyncClient) {
    this.client = client;
  }

  // ── Helpers for status bar ─────────────────────────────────────────────────

  get isOnline(): boolean {
    return this.status === 'online';
  }

  countByState(state: string): number {
    return this.results.reduce(
      (n, r) => n + r.jobs.filter(j => j.state === state).length,
      0
    );
  }
}
