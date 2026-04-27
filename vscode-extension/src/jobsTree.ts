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
  private started = false;

  // WebSocket state
  private wsConn: WebSocketConnection | null = null;
  private wsConnected = false;
  private pingTimer?: ReturnType<typeof setInterval>;
  private reconnectTimer?: ReturnType<typeof setTimeout>;
  private reconnectAttempts = 0;
  private lastPongAt = 0;
  private readonly heartbeatIntervalMs = 30_000;
  private readonly heartbeatTimeoutMs = 75_000;

  // HTTP fallback polling, enabled only while WebSocket is unhealthy.
  private fallbackTimer?: ReturnType<typeof setTimeout>;
  private fallbackPollInFlight = false;
  private fallbackIntervalMs = 120_000;

  constructor(private client: SsyncClient) {}

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  start(fallbackIntervalSecs: number) {
    this.fallbackIntervalMs = Math.max(30, fallbackIntervalSecs) * 1000;
    if (this.started) return;

    this.started = true;
    this.status = 'unknown';
    this.fireChange();

    // Initial HTTP fetch for full history (since=3d), then use WebSocket for live updates.
    void this.httpPoll().finally(() => {
      if (this.started) this.connectWebSocket();
    });
  }

  stop() {
    if (!this.started) return;
    this.started = false;
    this.stopFallbackPolling();
    this.disconnectWebSocket();
    this.clearReconnectTimer();
  }

  /** Manual refresh — always does a full HTTP fetch. */
  async refresh() {
    await this.httpPoll();
    if (this.started && !this.wsConn) this.connectWebSocket();
  }

  // ── WebSocket ──────────────────────────────────────────────────────────────

  private connectWebSocket() {
    if (!this.started) return;

    this.clearReconnectTimer();
    this.disconnectWebSocket();

    let connection: WebSocketConnection | null = null;
    connection = this.client.connectWebSocket({
      onConnect: () => {
        if (!this.started || this.wsConn !== connection) return;
        this.wsConnected = true;
        this.reconnectAttempts = 0;
        this.lastPongAt = Date.now();
        this.stopFallbackPolling();
        this.startPing();
      },

      onPong: () => {
        if (this.wsConn !== connection) return;
        this.lastPongAt = Date.now();
      },

      onInitial: (data) => {
        if (this.wsConn !== connection) return;
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
        if (this.wsConn !== connection) return;
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
        if (this.wsConn !== connection) return;
        this.handleWebSocketClose();
      },

      onError: () => {
        if (this.wsConn !== connection) return;
        if (!this.wsConnected) this.startFallbackPolling();
      },
    });
    this.wsConn = connection;
  }

  private disconnectWebSocket() {
    this.stopPing();
    const connection = this.wsConn;
    this.wsConn = null;
    this.wsConnected = false;
    if (connection) connection.close();
  }

  private handleWebSocketClose() {
    this.wsConnected = false;
    this.stopPing();

    if (!this.started) return;
    this.startFallbackPolling();
    this.scheduleReconnect();
  }

  private startPing() {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      if (!this.wsConn) return;
      if (Date.now() - this.lastPongAt > this.heartbeatTimeoutMs) {
        this.disconnectWebSocket();
        this.startFallbackPolling();
        this.scheduleReconnect();
        return;
      }
      this.wsConn.ping();
    }, this.heartbeatIntervalMs);
    this.wsConn?.ping();
  }

  private stopPing() {
    if (this.pingTimer) { clearInterval(this.pingTimer); this.pingTimer = undefined; }
  }

  private clearReconnectTimer() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
    }
  }

  private scheduleReconnect() {
    if (!this.started) return;
    this.clearReconnectTimer();
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), 60_000);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => this.connectWebSocket(), delay);
  }

  private startFallbackPolling() {
    if (!this.started || this.wsConnected || this.fallbackTimer) return;
    this.scheduleFallbackPoll(true);
  }

  private stopFallbackPolling() {
    if (this.fallbackTimer) {
      clearTimeout(this.fallbackTimer);
      this.fallbackTimer = undefined;
    }
    this.fallbackPollInFlight = false;
  }

  private scheduleFallbackPoll(immediate: boolean) {
    if (!this.started || this.wsConnected || this.fallbackTimer) return;

    const jitterMs = Math.min(15_000, this.fallbackIntervalMs * 0.25);
    const delay = immediate
      ? 500 + Math.floor(Math.random() * 2_000)
      : this.fallbackIntervalMs + Math.floor(Math.random() * jitterMs);

    this.fallbackTimer = setTimeout(async () => {
      this.fallbackTimer = undefined;
      if (!this.started || this.wsConnected) return;

      if (!this.fallbackPollInFlight) {
        this.fallbackPollInFlight = true;
        try {
          await this.httpPoll();
        } finally {
          this.fallbackPollInFlight = false;
        }
      }

      this.scheduleFallbackPoll(false);
    }, delay);
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
    if (!this.started) return;

    this.stopFallbackPolling();
    this.connectWebSocket();
    void this.httpPoll();
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
