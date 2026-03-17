import * as https from 'https';
import * as http from 'http';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { URL } from 'url';

// Allow self-signed certs for localhost
const httpsAgent = new https.Agent({ rejectUnauthorized: false });

export interface JobInfo {
  job_id: string;
  name: string;
  state: 'PD' | 'R' | 'CD' | 'F' | 'CA' | 'TO' | 'UNKNOWN';
  hostname: string;
  partition?: string;
  runtime?: string;
  time_limit?: string;
  nodes?: string;
  cpus?: string;
  memory?: string;
  reason?: string;
  work_dir?: string;
  submit_time?: string;
  start_time?: string;
  end_time?: string;
  array_job_id?: string;
  array_task_id?: string;
}

export interface HostInfo {
  hostname: string;
  work_dir: string;
  scratch_dir?: string;
  slurm_defaults?: {
    partition?: string;
    account?: string;
    cpus?: number;
    mem?: number;
    time?: string;
    nodes?: number;
    gpus_per_node?: number;
    gres?: string;
    python_env?: string;
    qos?: string;
  };
}

export interface JobStatusResult {
  hostname: string;
  jobs: JobInfo[];
  total_jobs: number;
  cached: boolean;
}

export interface JobOutput {
  job_id: string;
  hostname: string;
  stdout?: string;
  stderr?: string;
}

export interface LaunchRequest {
  script_content: string;
  source_dir?: string;
  host: string;
  job_name?: string;
  cpus?: number;
  mem?: number;
  time?: number;
  partition?: string;
  nodes?: number;
  gpus_per_node?: number;
  account?: string;
  python_env?: string;
}

export interface LaunchResponse {
  success: boolean;
  job_id?: string;
  message: string;
  hostname: string;
  requires_confirmation?: boolean;
}

export class SsyncClient {
  constructor(private apiUrl: string, private apiKey: string) {}

  /** Try to read API key from ~/.config/ssync/.api_key if not configured */
  static resolveApiKey(configured: string): string {
    if (configured) return configured;
    const keyFile = path.join(os.homedir(), '.config', 'ssync', '.api_key');
    try {
      const raw = fs.readFileSync(keyFile, 'utf8').trim();
      // File is JSON: { "key": { name, ... } } — first key is the api key string
      const parsed = JSON.parse(raw);
      return Object.keys(parsed)[0] ?? '';
    } catch {
      return '';
    }
  }

  private request<T>(method: string, urlPath: string, body?: unknown): Promise<T> {
    return new Promise((resolve, reject) => {
      const parsed = new URL(urlPath, this.apiUrl);
      const isHttps = parsed.protocol === 'https:';
      const options: https.RequestOptions = {
        hostname: parsed.hostname,
        port: parsed.port || (isHttps ? '443' : '80'),
        path: parsed.pathname + parsed.search,
        method,
        headers: {
          'X-API-Key': this.apiKey,
          'Content-Type': 'application/json',
        },
        ...(isHttps ? { agent: httpsAgent } : {}),
      };

      const mod = isHttps ? https : http;
      const req = mod.request(options, (res) => {
        let data = '';
        res.on('data', (chunk) => { data += chunk; });
        res.on('end', () => {
          if ((res.statusCode ?? 0) >= 400) {
            let msg = `HTTP ${res.statusCode}`;
            try { msg += `: ${JSON.parse(data).detail ?? data.slice(0, 200)}`; } catch { msg += `: ${data.slice(0, 200)}`; }
            reject(new Error(msg));
            return;
          }
          try {
            resolve(JSON.parse(data) as T);
          } catch {
            reject(new Error(`Invalid JSON: ${data.slice(0, 100)}`));
          }
        });
      });

      req.on('error', reject);
      if (body !== undefined) req.write(JSON.stringify(body));
      req.end();
    });
  }

  async health(): Promise<boolean> {
    try {
      const res = await this.request<{ status: string }>('GET', '/health');
      return res.status === 'healthy';
    } catch {
      return false;
    }
  }

  async getHosts(): Promise<HostInfo[]> {
    return this.request<HostInfo[]>('GET', '/api/hosts');
  }

  async getJobs(opts: { host?: string; activeOnly?: boolean; since?: string } = {}): Promise<JobStatusResult[]> {
    const params = new URLSearchParams();
    if (opts.host) params.set('host', opts.host);
    if (opts.activeOnly) params.set('active_only', 'true');
    if (opts.since) params.set('since', opts.since);
    params.set('group_array_jobs', 'false');
    return this.request<JobStatusResult[]>('GET', `/api/status?${params}`);
  }

  async getJobOutput(jobId: string, hostname: string, lines = 300): Promise<JobOutput> {
    return this.request<JobOutput>(
      'GET',
      `/api/jobs/${encodeURIComponent(jobId)}/output?host=${encodeURIComponent(hostname)}&lines=${lines}`
    );
  }

  async launchJob(req: LaunchRequest): Promise<LaunchResponse> {
    return this.request<LaunchResponse>('POST', '/api/jobs/launch', req);
  }

  async cancelJob(jobId: string, hostname: string): Promise<void> {
    await this.request('POST', `/api/jobs/${encodeURIComponent(jobId)}/cancel?host=${encodeURIComponent(hostname)}`);
  }

  /** Stream output lines via SSE. Returns an async generator of text chunks. */
  streamOutput(jobId: string, hostname: string, tailLines = 50): { stop: () => void; readable: NodeJS.ReadableStream } {
    const parsed = new URL(
      `/api/jobs/${encodeURIComponent(jobId)}/output/stream?host=${encodeURIComponent(hostname)}&tail_lines=${tailLines}`,
      this.apiUrl
    );
    const isHttps = parsed.protocol === 'https:';
    const options: https.RequestOptions = {
      hostname: parsed.hostname,
      port: parsed.port || (isHttps ? '443' : '80'),
      path: parsed.pathname + parsed.search,
      method: 'GET',
      headers: { 'X-API-Key': this.apiKey },
      ...(isHttps ? { agent: httpsAgent } : {}),
    };
    const mod = isHttps ? https : http;
    const req = mod.request(options);
    req.end();
    let responseStream: NodeJS.ReadableStream | null = null;
    req.on('response', (res) => { responseStream = res; });
    return {
      stop: () => req.destroy(),
      get readable() { return responseStream!; },
    };
  }
}
