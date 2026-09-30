import * as http from 'http';
import * as https from 'https';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import WebSocket from 'ws';
import { JobInfo, JobStatusResult, parseJob, record } from './model';

export interface HostInfo { hostname: string; work_dir?: string }
export interface JobOutput { stdout?: string | null; stderr?: string | null }
export interface LaunchRequest { script_content: string; source_dir?: string; host: string }
export interface LaunchResponse {
  success: boolean;
  job_id?: string;
  launch_id?: string;
  message: string;
  hostname: string;
  requires_confirmation?: boolean;
}
export interface LaunchStatus { stage: string; terminal: boolean; success?: boolean; job_id?: string; message?: string }
export interface WebSocketConnection { close(): void; ping(): void }
export interface WebSocketHandlers {
  onJobs(jobs: JobInfo[], initial: boolean, hosts: string[]): void;
  onRefresh(): void;
  onConnect(): void;
  onPong(): void;
  onClose(): void;
  onError(error: Error): void;
}

export function isLoopback(url: URL): boolean {
  return ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
}
export function serverUrl(value: string): URL {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('Use an HTTP(S) server URL without credentials, a query, or a fragment.');
  }
  url.pathname = url.pathname.replace(/\/+$/, '') + '/';
  return url;
}

export class SsyncClient {
  readonly url: URL;
  private readonly requests = new Set<http.ClientRequest>();
  private disposed = false;
  private readonly verifyTls: boolean;

  constructor(apiUrl: string, private readonly apiKey: string, private readonly timeoutMs = 30_000, trustLocalCertificate = true, private readonly configurationError?: string) {
    this.url = serverUrl(apiUrl);
    this.verifyTls = !(trustLocalCertificate && isLoopback(this.url));
  }
  static resolveApiKey(configured: string, keyFile = path.join(os.homedir(), '.config', 'ssync', '.api_key')): string {
    if (configured.trim()) return configured.trim();
    try {
      const raw = fs.readFileSync(keyFile, 'utf8').trim();
      return raw.startsWith('{') ? Object.keys(JSON.parse(raw))[0] ?? '' : raw;
    } catch { return ''; }
  }
  private request<T>(method: string, endpoint: string, body?: unknown): Promise<T> {
    if (this.configurationError) return Promise.reject(new Error(this.configurationError));
    if (this.disposed) return Promise.reject(new Error('Connection changed. Please try again.'));
    return new Promise((resolve, reject) => {
      const url = new URL(endpoint.replace(/^\//, ''), this.url);
      const payload = body === undefined ? undefined : JSON.stringify(body);
      const request = (url.protocol === 'https:' ? https : http).request(url, {
        method, rejectUnauthorized: this.verifyTls,
        headers: {
          'X-API-Key': this.apiKey, 'Content-Type': 'application/json',
          ...(payload ? { 'Content-Length': Buffer.byteLength(payload) } : {}),
        },
      }, response => {
        const chunks: Buffer[] = [];
        let size = 0;
        response.on('data', (chunk: Buffer) => {
          size += chunk.length;
          if (size > 16 * 1024 * 1024) request.destroy(new Error('Server response exceeds 16 MB.'));
          else chunks.push(chunk);
        });
        response.on('error', reject);
        response.on('aborted', () => reject(new Error('Server closed the response before it finished.')));
        response.on('end', () => {
          const status = response.statusCode ?? 0;
          const raw = Buffer.concat(chunks).toString('utf8');
          let data: unknown;
          try { data = raw ? JSON.parse(raw) : undefined; } catch {
            reject(new Error(`Server returned invalid JSON (HTTP ${status}).`)); return;
          }
          if (status < 200 || status >= 300) {
            const hint = status === 401 || status === 403 ? ' Check your API key in ssync: Configure Connection.' : '';
            const detail = record(data) && typeof data.detail === 'string' ? ` ${data.detail.slice(0, 300)}` : '';
            reject(new Error(`HTTP ${status}.${hint}${detail}`));
          } else resolve(data as T);
        });
      });
      this.requests.add(request);
      // The deadline covers DNS, TLS, and responses that trickle forever.
      const deadline = setTimeout(() => request.destroy(new Error(`Request timed out after ${this.timeoutMs / 1000}s.`)), this.timeoutMs);
      request.on('close', () => { clearTimeout(deadline); this.requests.delete(request); });
      request.on('error', reject);
      request.end(payload);
    });
  }
  async getHosts(): Promise<HostInfo[]> {
    const result = await this.request<unknown>('GET', 'api/hosts');
    if (!Array.isArray(result) || !result.every(host => record(host) && typeof host.hostname === 'string')) {
      throw new Error('Server returned an invalid host list.');
    }
    return result.map(host => ({ hostname: host.hostname, work_dir: typeof host.work_dir === 'string' ? host.work_dir : undefined }));
  }
  async getJobs(options: { activeOnly?: boolean; since?: string; force?: boolean } = {}): Promise<JobStatusResult[]> {
    const query = new URLSearchParams({ group_array_jobs: 'false' });
    if (options.activeOnly) query.set('active_only', 'true');
    if (options.since) query.set('since', options.since);
    if (options.force) query.set('force_refresh', 'true');
    const result = await this.request<unknown>('GET', `api/status?${query}`);
    if (!Array.isArray(result)) throw new Error('Server returned an invalid job list.');
    return result.map(host => {
      if (!record(host) || typeof host.hostname !== 'string' || !Array.isArray(host.jobs)) {
        throw new Error('Server returned an invalid job list.');
      }
      const hostname = host.hostname;
      return { hostname, jobs: host.jobs.map(job => parseJob(job, hostname)) };
    });
  }
  async getJobOutput(jobId: string, hostname: string, lines = 500): Promise<JobOutput> {
    const result = await this.request<unknown>('GET', `api/jobs/${encodeURIComponent(jobId)}/output?host=${encodeURIComponent(hostname)}&lines=${lines}`);
    if (!record(result) || !['stdout', 'stderr'].every(key => result[key] == null || typeof result[key] === 'string')) {
      throw new Error('Server returned invalid job output.');
    }
    return { stdout: result.stdout as string | null | undefined, stderr: result.stderr as string | null | undefined };
  }
  async launchJob(body: LaunchRequest): Promise<LaunchResponse> {
    const result = await this.request<LaunchResponse>('POST', 'api/jobs/launch', body);
    if (!record(result) || typeof result.success !== 'boolean' || typeof result.message !== 'string') {
      throw new Error('Server returned an invalid launch response. Check jobs before submitting again.');
    }
    return result;
  }
  async getLaunchStatus(id: string): Promise<LaunchStatus> {
    const result = await this.request<LaunchStatus>('GET', `api/launches/${encodeURIComponent(id)}`);
    if (!record(result) || typeof result.terminal !== 'boolean' || typeof result.stage !== 'string') {
      throw new Error('Server returned an invalid launch status.');
    }
    return result;
  }
  async cancelJob(jobId: string, hostname: string): Promise<void> {
    await this.request('POST', `api/jobs/${encodeURIComponent(jobId)}/cancel?host=${encodeURIComponent(hostname)}`);
  }
  connectWebSocket(handlers: WebSocketHandlers): WebSocketConnection {
    if (this.configurationError || this.disposed) {
      queueMicrotask(() => { handlers.onError(new Error(this.configurationError ?? 'Connection closed.')); handlers.onClose(); });
      return { close() {}, ping() {} };
    }
    const url = new URL('ws/jobs', this.url);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(url, {
      rejectUnauthorized: this.verifyTls, headers: { 'X-API-Key': this.apiKey },
      handshakeTimeout: this.timeoutMs, maxPayload: 16 * 1024 * 1024,
    });
    socket.on('open', handlers.onConnect);
    socket.on('error', handlers.onError);
    socket.on('close', handlers.onClose);
    socket.on('message', raw => {
      try {
        const data: unknown = JSON.parse(raw.toString());
        if (!record(data)) return;
        if (data.type === 'pong') { handlers.onPong(); return; }
        if (data.type === 'initial' && record(data.jobs)) {
          const jobs = Object.entries(data.jobs).flatMap(([host, list]) => {
            if (!Array.isArray(list)) throw new Error('Invalid realtime snapshot.');
            return list.map(job => parseJob(job, host));
          });
          handlers.onJobs(jobs, true, Object.keys(data.jobs));
        } else if (['batch_update', 'job_update', 'state_change', 'job_completed'].includes(String(data.type))) {
          const updates = data.type === 'batch_update' ? data.updates : [data];
          if (!Array.isArray(updates)) throw new Error('Invalid realtime update.');
          const jobs = updates.flatMap(update => {
            if (!record(update)) throw new Error('Invalid realtime update.');
            if (!update.job) { handlers.onRefresh(); return []; }
            return [parseJob(update.job, typeof update.hostname === 'string' ? update.hostname : undefined)];
          });
          handlers.onJobs(jobs, false, []);
        }
      } catch {
        handlers.onError(new Error('Invalid realtime data; refreshing from the server.'));
        handlers.onRefresh();
      }
    });
    return {
      close: () => socket.terminate(),
      ping: () => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'ping' })); },
    };
  }
  dispose(): void {
    this.disposed = true;
    for (const request of this.requests) request.destroy(new Error('Connection changed. Please try again.'));
    this.requests.clear();
  }
}
