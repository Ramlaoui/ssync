import { EventEmitter } from 'events';
import { SsyncClient, WebSocketConnection } from './client';
import { JobInfo, errorMessage, isActive, jobKey, sortJobs } from './model';

export interface MonitorOptions { pollInterval: number; showCompleted: boolean; since: string }
export interface JobSnapshot {
  jobs: JobInfo[]; hosts: string[];
  connection: 'connecting' | 'live' | 'polling' | 'offline' | 'paused';
  refreshing: boolean; updatedAt?: number; error?: string;
}
/** Owns transport lifecycle and data; UI surfaces only subscribe and render. */
export class JobStore {
  private readonly events = new EventEmitter();
  private jobs = new Map<string, JobInfo>();
  private hosts = new Set<string>();
  private connection: JobSnapshot['connection'] = 'connecting';
  private error?: string;
  private updatedAt?: number;
  private running = false;
  private disposed = false;
  private generation = 0;
  private pollTimer?: ReturnType<typeof setInterval>;
  private heartbeat?: ReturnType<typeof setInterval>;
  private reconnect?: ReturnType<typeof setTimeout>;
  private socket?: WebSocketConnection;
  private live = false;
  private attempts = 0;
  private lastPong = 0;
  private pending?: Promise<void>;
  private realtimeDuringRefresh = new Map<string, JobInfo>();

  constructor(public client: SsyncClient, private options: MonitorOptions) {}
  subscribe(listener: () => void): { dispose(): void } {
    this.events.on('change', listener);
    return { dispose: () => { this.events.off('change', listener); } };
  }
  get snapshot(): JobSnapshot {
    return {
      jobs: sortJobs([...this.jobs.values()].filter(job => this.options.showCompleted || isActive(job))),
      hosts: [...this.hosts].sort(), connection: this.connection,
      refreshing: !!this.pending, updatedAt: this.updatedAt, error: this.error,
    };
  }
  find(key: string): JobInfo | undefined { return this.jobs.get(key); }
  private changed(): void { this.events.emit('change'); }
  start(): void {
    if (this.running || this.disposed) return;
    this.running = true;
    this.connection = 'connecting';
    const generation = this.generation;
    // One timer reconciles history and supplies polling if realtime is unavailable.
    this.pollTimer = setInterval(() => { void this.refresh(); }, Math.max(30, this.options.pollInterval) * 1000);
    void this.refresh().then(() => { if (this.running && generation === this.generation) this.connect(); });
  }
  stop(): void {
    this.running = false;
    this.generation++;
    if (this.pollTimer) clearInterval(this.pollTimer);
    if (this.heartbeat) clearInterval(this.heartbeat);
    if (this.reconnect) clearTimeout(this.reconnect);
    this.pollTimer = this.heartbeat = this.reconnect = undefined;
    const socket = this.socket;
    this.socket = undefined;
    socket?.close();
    this.live = false;
    this.pending = undefined;
    this.realtimeDuringRefresh.clear();
    this.connection = 'paused';
    this.changed();
  }
  update(client: SsyncClient, options: MonitorOptions): void {
    if (this.disposed) { client.dispose(); return; }
    const wasRunning = this.running;
    this.stop();
    this.client.dispose();
    this.client = client;
    this.options = options;
    this.jobs.clear();
    this.hosts.clear();
    this.updatedAt = undefined;
    this.error = undefined;
    this.attempts = 0;
    if (wasRunning) this.start();
    else this.changed();
  }
  refresh(force = false): Promise<void> {
    if (this.disposed) return Promise.resolve();
    if (this.pending) return this.pending;
    const generation = this.generation;
    const client = this.client;
    const options = this.options;
    this.realtimeDuringRefresh.clear();
    const pending = Promise.resolve().then(async () => {
      try {
        const results = await client.getJobs({
          activeOnly: !options.showCompleted,
          since: options.showCompleted ? options.since : undefined, force,
        });
        if (generation !== this.generation) return;
        this.jobs = new Map(results.flatMap(host => host.jobs.map(job => [jobKey(job), job] as const)));
        this.hosts = new Set(results.map(host => host.hostname));
        // Replay realtime changes received after this HTTP request started.
        for (const [key, job] of this.realtimeDuringRefresh) { this.jobs.set(key, job); this.hosts.add(job.hostname); }
        this.error = undefined;
        this.updatedAt = Date.now();
        this.connection = this.live ? 'live' : 'polling';
      } catch (error) {
        if (generation !== this.generation) return;
        this.error = errorMessage(error);
        this.connection = 'offline';
      } finally {
        if (generation === this.generation) {
          this.pending = undefined;
          this.realtimeDuringRefresh.clear();
          this.changed();
        }
      }
    });
    this.pending = pending;
    this.changed();
    return pending;
  }
  private connect(): void {
    if (!this.running || this.socket) return;
    const generation = this.generation;
    let socket: WebSocketConnection;
    const current = () => this.running && generation === this.generation && this.socket === socket;
    socket = this.client.connectWebSocket({
      onConnect: () => {
        if (!current()) return;
        this.lastPong = Date.now();
        this.heartbeat = setInterval(() => {
          if (Date.now() - this.lastPong > 75_000) { socket.close(); return; }
          socket.ping();
        }, 30_000);
        socket.ping();
      },
      onPong: () => { if (current()) this.lastPong = Date.now(); },
      onJobs: (jobs, initial, hosts) => {
        if (!current()) return;
        // WS initial data is a one-day cache, so it only fills gaps in HTTP history.
        for (const job of jobs) {
          const key = jobKey(job);
          if (initial && (this.jobs.has(key) || !isActive(job))) continue;
          this.jobs.set(key, job);
          this.hosts.add(job.hostname);
          if (this.pending) this.realtimeDuringRefresh.set(key, job);
        }
        for (const host of hosts) this.hosts.add(host);
        this.live = true;
        this.attempts = 0;
        this.connection = 'live';
        this.error = undefined;
        this.updatedAt = Date.now();
        this.changed();
      },
      onRefresh: () => { if (current()) void this.refresh(); },
      onError: () => { /* HTTP polling remains available; close triggers reconnection. */ },
      onClose: () => {
        if (!current()) return;
        this.socket = undefined;
        this.live = false;
        if (this.heartbeat) clearInterval(this.heartbeat);
        this.heartbeat = undefined;
        this.connection = this.error ? 'offline' : 'polling';
        this.changed();
        void this.refresh();
        const delay = Math.min(1000 * 2 ** this.attempts++, 60_000);
        this.reconnect = setTimeout(() => { this.reconnect = undefined; this.connect(); }, delay);
      },
    });
    this.socket = socket;
  }
  dispose(): void { this.disposed = true; this.stop(); this.client.dispose(); this.events.removeAllListeners(); }
}
