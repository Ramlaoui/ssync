// Capture documentation screenshots of the web app with fictional sample data.
// Usage: npm run dev -- --port 5181 (in another terminal), then
//        node scripts/docs-screenshots.mjs [http://127.0.0.1:5181/]
// Every API and websocket request is answered in the browser; nothing reaches a server.
// Then convert for the docs: for f in docs/assets/screenshots/*.png; do cwebp -q 88 "$f" -o "${f%.png}.webp" && rm "$f"; done
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import * as data from './docs-sample-data.mjs';

const base = process.argv[2] || 'http://127.0.0.1:5181/';
const out = fileURLToPath(new URL('../../docs/assets/screenshots/', import.meta.url));
mkdirSync(out, { recursive: true });

const json = body => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
const byId = (id, host) => data.jobs.find(job => job.job_id === id && (!host || job.hostname === host));

function answer(url, method) {
  const path = url.pathname;
  if (method !== 'GET') return json(path === '/api/auth/session' ? { authenticated: true } : { success: true });
  if (path === '/api/hosts') return json(data.hosts);
  if (path === '/api/status') {
    const host = url.searchParams.get('host');
    const hosts = host ? [host] : data.hosts.map(h => h.hostname);
    const responses = hosts.map(hostname => ({ hostname, jobs: data.jobs.filter(job => job.hostname === hostname), total_jobs: data.jobs.filter(job => job.hostname === hostname).length, query_time: '0.4s', array_groups: [] }));
    return json(host ? responses[0] : responses);
  }
  if (path === '/api/partitions') return json(data.partitions);
  if (path === '/api/watchers') return json({ job_id: '', watchers: data.watchers, count: data.watchers.length });
  if (path === '/api/watchers/stats') return json(data.watcherStats);
  if (path === '/api/watchers/events') {
    const watcher = url.searchParams.get('watcher_id'), jobId = url.searchParams.get('job_id');
    const events = data.watcherEvents.filter(event => (!watcher || String(event.watcher_id) === watcher) && (!jobId || event.job_id === jobId));
    return json({ events, count: events.length });
  }
  if (path === '/api/notifications/status') return json({ enabled: false, providers: {} });
  if (path === '/api/notifications/preferences') return json({ enabled: true });
  const match = path.match(/^\/api\/jobs\/([^/]+)(?:\/(\w+))?(?:\/(\w+))?$/);
  if (match) {
    const [, rawId, section, sub] = match;
    const id = decodeURIComponent(rawId), host = url.searchParams.get('host');
    const job = byId(id, host);
    if (!section) return job ? json(job) : { status: 404, contentType: 'application/json', body: '{"detail":"Job not found"}' };
    if (section === 'watchers') return json({ job_id: id, watchers: data.watchers.filter(w => w.job_id === id), count: 0 });
    if (section === 'script') return json({ job_id: id, hostname: job?.hostname, script_content: data.script(job?.name || 'job'), content_length: 900, local_source_dir: '~/projects/protein-fold' });
    if (section === 'output' && sub === 'stream') {
      const events = [{ type: 'metadata', output_type: 'stdout', source: 'live' }, { type: 'chunk', index: 0, data: data.output(id), compressed: false }, { type: 'complete' }];
      return { status: 200, contentType: 'text/event-stream', body: events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('') };
    }
    if (section === 'output') {
      const text = data.output(id);
      const lines = Number(url.searchParams.get('lines'));
      const content = lines ? text.trimEnd().split('\n').slice(-lines).join('\n') : text;
      const metadata = { path: job?.stdout_file, exists: true, size_bytes: text.length, last_modified: new Date().toISOString(), access_path: null };
      return json({ job_id: id, hostname: job?.hostname, output_type: 'stdout', stdout: url.searchParams.get('metadata_only') === 'true' ? null : content, stderr: '', stdout_metadata: metadata, stderr_metadata: { ...metadata, size_bytes: 0 } });
    }
  }
  return json({});
}

const browser = await chromium.launch();
async function session({ width = 1440, height = 900, scheme = 'light' } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, colorScheme: scheme, deviceScaleFactor: 2 });
  await context.addInitScript(() => {
    localStorage.setItem('ssync-jobs-list-width', '520');
    localStorage.setItem('ui-preferences', JSON.stringify({ autoRefresh: false, collapseArrayTasks: true, defaultSince: '7d', jobsPerPage: 50 }));
  });
  await context.route('**/api/**', route => route.fulfill(answer(new URL(route.request().url()), route.request().method())));
  await context.routeWebSocket(/\/ws\//, ws => {
    ws.onMessage(() => { });
    if (ws.url().includes('/ws/jobs')) {
      const byHost = Object.fromEntries(data.hosts.map(h => [h.hostname, data.jobs.filter(job => job.hostname === h.hostname)]));
      ws.send(JSON.stringify({ type: 'initial', jobs: byHost, total: data.jobs.length }));
    }
  });
  const page = await context.newPage();
  page.on('pageerror', error => console.error('page error:', error.message));
  return page;
}
const shot = (page, name) => page.screenshot({ path: `${out}${name}.png` });
const settle = page => page.waitForTimeout(1500);
const row = (page, name) => page.getByRole('button', { name: new RegExp(`^Inspect ${name},`) });

let page = await session();
await page.goto(base);
await page.waitForSelector('.jobs-row');
await settle(page);
await shot(page, 'web-jobs');
await page.locator('.jobs-array-row').first().click();
await settle(page);
await shot(page, 'web-jobs-array');
await page.locator('.jobs-array-row').first().click();
await row(page, 'protein-fold-v3').click();
await page.waitForTimeout(2500);
await shot(page, 'web-job-inspector');
await page.getByRole('button', { name: 'Maximize job' }).click();
await page.waitForTimeout(2500);
await shot(page, 'web-job-overview');
await page.locator('main').getByText('Output', { exact: true }).first().click();
await page.waitForTimeout(2500);
await shot(page, 'web-job-output');
await page.locator('main').getByText('Script', { exact: true }).first().click();
await page.waitForTimeout(2000);
await shot(page, 'web-job-script');
await page.goto(`${base}#/jobs/48215/atlas`);
await page.waitForTimeout(2500);
await shot(page, 'web-job-queued');
await page.goto(`${base}#/watchers?watcher=1`);
await page.waitForTimeout(3000);
await shot(page, 'web-watchers');
for (const [name, route] of [['web-hosts', '#/hosts'], ['web-launch', '#/launch']]) {
  await page.goto(base + route);
  await page.waitForTimeout(3000);
  await shot(page, name);
}
await page.goto(base);
await page.waitForSelector('.jobs-row');
await page.keyboard.press('Meta+k');
await page.waitForTimeout(400);
await page.keyboard.type('fold');
await settle(page);
await shot(page, 'web-quick-find');
await page.context().close();

page = await session({ scheme: 'dark' });
await page.goto(base);
await page.waitForSelector('.jobs-row');
await row(page, 'llm-finetune-7b').click();
await page.waitForTimeout(2500);
await shot(page, 'web-jobs-dark');
await page.context().close();

page = await session({ width: 390, height: 844 });
await page.goto(base);
await page.waitForSelector('.jobs-row');
await settle(page);
await shot(page, 'web-mobile-jobs');
await page.context().close();

await browser.close();
console.log(`Saved screenshots to ${out}`);
