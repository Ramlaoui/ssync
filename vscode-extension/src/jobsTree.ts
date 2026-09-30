import * as vscode from 'vscode';
import { JobStore } from './jobStore';
import { JobInfo, STATES, isActive, jobKey } from './model';

export class HostItem extends vscode.TreeItem {
  constructor(public readonly hostname: string, public readonly jobs: JobInfo[]) {
    super(hostname, vscode.TreeItemCollapsibleState.Expanded);
    this.id = `host:${hostname}`;
    this.iconPath = new vscode.ThemeIcon('server');
    const running = jobs.filter(job => job.state === 'R').length;
    const queued = jobs.filter(job => job.state === 'PD').length;
    this.description = `${running} running · ${queued} queued · ${jobs.length} total`;
    this.contextValue = 'host';
  }
}
export class JobItem extends vscode.TreeItem {
  constructor(public readonly job: JobInfo) {
    super(job.name || job.job_id, vscode.TreeItemCollapsibleState.None);
    this.id = jobKey(job);
    const state = STATES[job.state];
    this.description = `${state.label} · ${job.job_id}${job.runtime ? ` · ${job.runtime}` : ''}`;
    const tooltip = new vscode.MarkdownString();
    tooltip.appendText(`${job.name}\n${job.job_id} · ${job.hostname}\n${state.label}\n`);
    for (const [label, value] of [
      ['Partition', job.partition], ['CPUs', job.cpus], ['Memory', job.memory],
      ['Time limit', job.time_limit], ['Queue reason', job.reason], ['Directory', job.work_dir],
    ]) { if (value) tooltip.appendText(`${label}: ${value}\n`); }
    this.tooltip = tooltip;
    this.iconPath = new vscode.ThemeIcon(state.icon, new vscode.ThemeColor(state.color));
    this.contextValue = isActive(job) ? `job-${job.state === 'R' ? 'running' : 'pending'}` : 'job';
    this.command = { command: 'ssync.viewLogs', title: 'Open Job', arguments: [this] };
    this.accessibilityInformation = { label: `${job.name}, ${state.label}, job ${job.job_id}, ${job.hostname}` };
  }
}
class MessageItem extends vscode.TreeItem {
  constructor(label: string, icon: string, command?: string) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon(icon);
    if (command) this.command = { command, title: label };
  }
}
type Item = HostItem | JobItem | MessageItem;

export class JobsTreeProvider implements vscode.TreeDataProvider<Item>, vscode.Disposable {
  private readonly changes = new vscode.EventEmitter<Item | undefined>();
  readonly onDidChangeTreeData = this.changes.event;
  private readonly subscription: { dispose(): void };
  constructor(private readonly store: JobStore) {
    this.subscription = store.subscribe(() => this.changes.fire(undefined));
  }
  getTreeItem(item: Item): vscode.TreeItem { return item; }
  getChildren(item?: Item): Item[] {
    if (item instanceof HostItem) return item.jobs.map(job => new JobItem(job));
    if (item) return [];
    const { connection, refreshing, jobs, hosts, error } = this.store.snapshot;
    const items: Item[] = [];
    if (error) {
      const warning = new MessageItem(jobs.length ? 'Connection lost · showing last known jobs' : 'Cannot connect · configure ssync', 'warning', 'ssync.configure');
      warning.tooltip = error;
      items.push(warning, new MessageItem('Retry connection', 'refresh', 'ssync.refreshJobs'));
    }
    if (!jobs.length && connection === 'connecting') return [new MessageItem('Connecting…', 'loading~spin')];
    for (const host of hosts) items.push(new HostItem(host, jobs.filter(job => job.hostname === host)));
    if (!hosts.length && !error) {
      items.push(new MessageItem(refreshing ? 'Refreshing…' : 'No jobs yet · open dashboard', refreshing ? 'loading~spin' : 'info', 'ssync.openDashboard'));
    }
    return items;
  }
  dispose(): void { this.subscription.dispose(); this.changes.dispose(); }
}
