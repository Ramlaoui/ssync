import * as http from 'http';
import { AddressInfo } from 'net';
import { WebSocketServer, WebSocket } from 'ws';
import { JobInfo } from '../src/model';

export const demoJobs: JobInfo[] = [
  { job_id: '28491', name: 'train-foundation-model', hostname: 'atlas', state: 'R', partition: 'gpu-a100', cpus: '16', memory: '64G', nodes: '1', runtime: '02:14:36', time_limit: '12:00:00', work_dir: '/scratch/research/foundation', submit_time: '2026-09-30T08:10:00' },
  { job_id: '28492', name: 'embedding-evaluation', hostname: 'atlas', state: 'PD', partition: 'gpu-a100', cpus: '8', memory: '32G', reason: 'Resources', time_limit: '04:00:00' },
  { job_id: '28491', name: 'molecular-dynamics', hostname: 'borealis', state: 'R', partition: 'compute', cpus: '64', memory: '128G', runtime: '00:42:18', time_limit: '06:00:00' },
  { job_id: '28374', name: 'parameter-sweep_07', hostname: 'borealis', state: 'F', partition: 'compute', runtime: '00:03:12', time_limit: '02:00:00', exit_code: '1:0' },
  { job_id: '28208', name: 'preprocess-dataset', hostname: 'atlas', state: 'CD', partition: 'cpu', runtime: '00:18:49', time_limit: '01:00:00', exit_code: '0:0' },
  { job_id: '28140', name: 'long-relaxation', hostname: 'borealis', state: 'TO', partition: 'compute', runtime: '24:00:00', time_limit: '24:00:00' },
];

/** Isolated server for transport tests and UI demos. Never talks to a cluster. */
export async function fixture(port = 0, preview?: (request: http.IncomingMessage, response: http.ServerResponse) => boolean) {
  const requests: { method: string; url: string; key?: string; body?: unknown }[] = [];
  let jobs = demoJobs.map(job => ({ ...job }));
  let mode: 'ok' | 'error' | 'invalid' | 'stall' = 'ok';
  let release: (() => void) | undefined;
  let held = false;
  let launchPolls = 0;
  const server = http.createServer(async (request, response) => {
    if (preview?.(request, response)) return;
    const entry = { method: request.method ?? '', url: request.url ?? '', key: request.headers['x-api-key'] as string | undefined, body: undefined as unknown };
    requests.push(entry);
    const url = new URL(entry.url, 'http://localhost');
    const chunks: Buffer[] = [];
    for await (const chunk of request) chunks.push(chunk);
    if (chunks.length) entry.body = JSON.parse(Buffer.concat(chunks).toString());
    const send = (data: unknown, code = 200) => { response.writeHead(code, { 'Content-Type': 'application/json' }); response.end(JSON.stringify(data)); };
    if (url.pathname === '/api/status') {
      if (mode === 'stall') return;
      if (mode === 'error') { send({ detail: 'Fixture unavailable' }, 503); return; }
      if (mode === 'invalid') { send({ wrong: true }); return; }
      const snapshot = ['atlas', 'borealis', 'idle-cluster'].map(hostname => ({ hostname, jobs: jobs.filter(job => job.hostname === hostname && (url.searchParams.get('active_only') !== 'true' || ['R', 'PD'].includes(job.state))) }));
      if (held) await new Promise<void>(resolve => { release = resolve; });
      send(snapshot);
    } else if (url.pathname === '/api/hosts') send(['atlas', 'borealis', 'idle-cluster'].map(hostname => ({ hostname })));
    else if (url.pathname.endsWith('/output')) send({ stdout: `${url.searchParams.get('host')} / ${url.pathname.split('/')[3]}\nepoch 1 · loss 0.8421\nepoch 2 · loss 0.7018\n<script>alert('untrusted log')</script>\n`, stderr: 'UserWarning: falling back to CPU for preprocessing\n' });
    else if (url.pathname === '/api/jobs/launch') { launchPolls = 0; send({ success: true, launch_id: 'fixture-launch', hostname: 'atlas', message: 'Launch started' }); }
    else if (url.pathname === '/api/launches/fixture-launch') {
      launchPolls++;
      send({ stage: launchPolls > 1 ? 'result' : 'sync', terminal: launchPolls > 1, success: launchPolls > 1 ? true : null, job_id: launchPolls > 1 ? '28491' : null, message: launchPolls > 1 ? 'Submitted' : 'Syncing project…' });
    } else if (url.pathname.endsWith('/cancel')) {
      const job = jobs.find(job => job.hostname === url.searchParams.get('host') && job.job_id === url.pathname.split('/')[3]);
      if (job) job.state = 'CA';
      send({ message: 'Job cancelled successfully' });
    } else send({ detail: 'Fixture endpoint not found' }, 404);
  });
  const websocket = new WebSocketServer({ server });
  websocket.on('connection', (socket, request) => {
    requests.push({ method: 'WS', url: request.url ?? '', key: request.headers['x-api-key'] as string | undefined });
    socket.send(JSON.stringify({ type: 'initial', jobs: { atlas: [], borealis: [], 'idle-cluster': [] }, total: 0 }));
    socket.on('message', raw => {
      if (JSON.parse(raw.toString()).type === 'ping') socket.send(JSON.stringify({ type: 'pong' }));
    });
  });
  await new Promise<void>(resolve => server.listen(port, '127.0.0.1', resolve));
  return {
    url: `http://127.0.0.1:${(server.address() as AddressInfo).port}`, requests,
    setMode(value: typeof mode) { mode = value; },
    hold() { held = true; },
    release() { held = false; release?.(); },
    update(job: JobInfo) {
      jobs = jobs.filter(existing => !(existing.hostname === job.hostname && existing.job_id === job.job_id));
      jobs.push(job);
      this.broadcast({ type: 'batch_update', updates: [{ type: 'job_update', hostname: job.hostname, job_id: job.job_id, job }] });
    },
    broadcast(data: unknown) { for (const socket of websocket.clients) if (socket.readyState === WebSocket.OPEN) socket.send(typeof data === 'string' ? data : JSON.stringify(data)); },
    disconnect() { for (const socket of websocket.clients) socket.terminate(); },
    async close() {
      this.release();
      this.disconnect();
      await new Promise<void>(resolve => websocket.close(() => resolve()));
      server.closeAllConnections();
      await new Promise<void>(resolve => server.close(() => resolve()));
    },
  };
}
