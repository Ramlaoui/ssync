import * as vscode from 'vscode';
import { SsyncClient, JobInfo, JobStatusResult, WebSocketConnection } from './client';

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

  /** hostname → (job_id → JobInfo) */
  private jobsByHost = new Map<string, Map<string, JobInfo>>();
  private status: 'unknown' | 'online' | 'offline' = 'unknown';

  // WebSocket state
  private wsConn: WebSocketConnection | null = null;
  private wsConnected = false;
  private pingTimer?: ReturnType<typeof setInterval>;
  private reconnectTimer?: ReturnType<typeof setTimeout>;
  private reconnectAttempts = 0;

  // HTTP fallback polling
  private pollTimer?: ReturnType<typeof setInterval>;
  private fallbackIntervalMs = 120_000;

  constructor(private client: SsyncClient) {}

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  start(fallbackIntervalSecs: number) {
    this.fallbackIntervalMs = fallbackIntervalSecs * 1000;

    // Initial HTTP fetch for full history (since=3d), then connect WebSocket
    this.httpPoll().then(() => this.connectWebSocket());

    // Slow HTTP fallback — ensures completeness even if WS misses something
    this.pollTimer = setInterval(() => this.httpPoll(), this.fallbackIntervalMs);
  }

  stop() {
    this.disconnectWebSocket();
    if (this.pollTimer) clearInterval(this.pollTimer);
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
  }

  /** Manual refresh — always does a full HTTP fetch. */
  async refresh() {
    await this.httpPoll();
  }

  // ── WebSocket ──────────────────────────────────────────────────────────────

  private connectWebSocket() {
    this.disconnectWebSocket();

    this.wsConn = this.client.connectWebSocket({
      onConnect: () => {
        this.wsConnected = true;
        this.reconnectAttempts = 0;
        this.startPing();
      },

      onInitial: (data) => {
        // Merge WS initial data into existing store (don't replace — HTTP has fuller history)
        for (const [hostname, jobs] of Object.entries(data.jobs)) {
          if (!Array.isArray(jobs)) continue;
          if (!this.jobsByHost.has(hostname)) {
            this.jobsByHost.set(hostname, new Map());
          }
          const hostMap = this.jobsByHost.get(hostname)!;
          for (const job of jobs) {
            if (job.job_id) hostMap.set(job.job_id, job);
          }
        }
        this.status = 'online';
        this.fireChange();
      },

      onUpdate: (updates) => {
        for (const update of updates) {
          if (!update.hostname || !update.job_id || !update.job) continue;
          if (!this.jobsByHost.has(update.hostname)) {
            this.jobsByHost.set(update.hostname, new Map());
          }
          this.jobsByHost.get(update.hostname)!.set(update.job_id, update.job);
        }
        this.fireChange();
      },

      onClose: () => {
        this.wsConnected = false;
        this.stopPing();
        this.scheduleReconnect();
      },

      onError: () => {
        // onClose will fire after this — reconnect handled there
      },
    });
  }

  private disconnectWebSocket() {
    this.stopPing();
    if (this.wsConn) {
      this.wsConn.close();
      this.wsConn = null;
    }
    this.wsConnected = false;
  }

  private startPing() {
    this.stopPing();
    this.pingTimer = setInterval(() => this.wsConn?.ping(), 30_000);
  }

  private stopPing() {
    if (this.pingTimer) { clearInterval(this.pingTimer); this.pingTimer = undefined; }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), 60_000);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => this.connectWebSocket(), delay);
  }

  // ── HTTP polling ───────────────────────────────────────────────────────────

  private async httpPoll() {
    const cfg = vscode.workspace.getConfiguration('ssync');
    const showCompleted = cfg.get<boolean>('showCompletedJobs', true);
    const since = cfg.get<string>('completedJobsWindow', '3d');

    const alive = await this.client.health();
    if (!alive) {
      this.status = 'offline';
      this.jobsByHost.clear();
      this.fireChange();
      return;
    }

    try {
      const results = await this.client.getJobs({ since: showCompleted ? since : '0' });
      this.status = 'online';

      // Full replace from HTTP — this is the authoritative source
      this.jobsByHost.clear();
      for (const result of results) {
        const hostMap = new Map<string, JobInfo>();
        for (const job of result.jobs) hostMap.set(job.job_id, job);
        this.jobsByHost.set(result.hostname, hostMap);
      }
    } catch {
      this.status = 'online'; // server is up but query failed
      this.jobsByHost.clear();
    }
    this.fireChange();
  }

  private fireChange() {
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
    const hosts: HostItem[] = [];
    for (const [hostname, jobMap] of this.jobsByHost) {
      const jobs = Array.from(jobMap.values());
      if (jobs.length > 0) hosts.push(new HostItem(hostname, jobs));
    }
    if (!hosts.length) {
      return [new MessageItem('No jobs found', 'info')];
    }
    return hosts;
  }

  updateClient(client: SsyncClient) {
    this.client = client;
    // Reconnect WebSocket with new client
    this.connectWebSocket();
  }

  // ── Helpers for status bar ─────────────────────────────────────────────────

  get isOnline(): boolean {
    return this.status === 'online';
  }

  countByState(state: string): number {
    let count = 0;
    for (const jobMap of this.jobsByHost.values()) {
      for (const job of jobMap.values()) {
        if (job.state === state) count++;
      }
    }
    return count;
  }
}
