import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { SsyncClient, isLoopback, serverUrl } from '../src/client';
import { JobStore } from '../src/jobStore';
import { jobKey, parseJob } from '../src/model';
import { fixture, demoJobs } from './fixture';

const options = { pollInterval: 120, showCompleted: true, since: '3d' };
async function until(predicate: () => boolean): Promise<void> {
  const deadline = Date.now() + 4000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error('Condition did not become true.');
    await new Promise(resolve => setTimeout(resolve, 10));
  }
}

test('validates URLs, confines local certificate trust, parses both key file formats', () => {
  assert.equal(serverUrl('https://cluster.example/base/').toString(), 'https://cluster.example/base/');
  for (const url of ['file:///tmp/key', 'https://key:secret@host', 'https://host/?api_key=secret']) assert.throws(() => serverUrl(url));
  assert.equal(isLoopback(serverUrl('https://localhost:8042')), true);
  assert.equal(isLoopback(serverUrl('https://[::1]:8042')), true);
  assert.equal(isLoopback(serverUrl('https://localhost.example')), false);
  const directory = mkdtempSync(join(tmpdir(), 'ssync-keys-'));
  try {
    const file = join(directory, 'key');
    writeFileSync(file, 'fixture-key\n'); assert.equal(SsyncClient.resolveApiKey('', file), 'fixture-key');
    writeFileSync(file, '{"fixture-json-key": {}}'); assert.equal(SsyncClient.resolveApiKey('', file), 'fixture-json-key');
    assert.equal(SsyncClient.resolveApiKey('explicit', file), 'explicit');
  } finally { rmSync(directory, { recursive: true }); }
});

test('host/job identity and unknown states are handled safely', () => {
  assert.notEqual(jobKey(demoJobs[0]), jobKey(demoJobs[2]));
  assert.equal(parseJob({ ...demoJobs[0], state: 'NEW_SLURM_STATE' }).state, 'UNKNOWN');
  assert.throws(() => parseJob({ name: 'missing ID' }));
  assert.throws(() => parseJob({ ...demoJobs[0], submit_time: {} }), /invalid submit_time/);
});

test('real HTTP transport authenticates, uses active_only, validates errors, tracks asynchronous launches', async () => {
  const api = await fixture();
  const client = new SsyncClient(api.url, 'fixture-key', 1000);
  try {
    const results = await client.getJobs({ activeOnly: true });
    assert.equal(results.flatMap(host => host.jobs).length, 3);
    assert.match(api.requests[0].url, /active_only=true/);
    assert.doesNotMatch(api.requests[0].url, /since=0/);
    assert.equal(api.requests[0].key, 'fixture-key');
    assert.match((await client.getJobOutput('28491', 'borealis')).stdout!, /borealis/);
    const launch = await client.launchJob({ host: 'atlas', script_content: '#!/bin/bash\necho hello' });
    assert.equal(launch.job_id, undefined);
    assert.equal((await client.getLaunchStatus(launch.launch_id!)).terminal, false);
    assert.equal((await client.getLaunchStatus(launch.launch_id!)).job_id, '28491');
    api.setMode('invalid'); await assert.rejects(client.getJobs(), /invalid job list/);
    api.setMode('error'); await assert.rejects(client.getJobs(), /HTTP 503/);
  } finally { client.dispose(); await api.close(); }
});

test('wall-clock deadline and disposal abort outstanding HTTP requests', async () => {
  const api = await fixture();
  api.setMode('stall');
  const client = new SsyncClient(api.url, '', 50);
  try {
    await assert.rejects(client.getJobs(), /timed out/);
    const pending = client.getHosts(); client.dispose();
    await assert.rejects(pending, /Connection changed/);
  } finally { client.dispose(); await api.close(); }
});

test('store coalesces refreshes, preserves jobs on failure, recovers and sorts active jobs first', async () => {
  const api = await fixture();
  const store = new JobStore(new SsyncClient(api.url, ''), options);
  try {
    assert.equal(store.refresh(), store.refresh());
    await store.refresh();
    assert.equal(api.requests.length, 1);
    assert.equal(store.snapshot.jobs.length, 6);
    assert.equal(store.snapshot.jobs[0].state, 'R');
    const updatedAt = store.snapshot.updatedAt;
    api.setMode('error'); await store.refresh();
    assert.equal(store.snapshot.jobs.length, 6);
    assert.equal(store.snapshot.updatedAt, updatedAt);
    assert.equal(store.snapshot.connection, 'offline');
    api.setMode('ok'); await store.refresh();
    assert.equal(store.snapshot.error, undefined);
  } finally { store.dispose(); await api.close(); }
});

test('real WebSocket updates survive racing HTTP snapshots and reconnect with header auth', async () => {
  const api = await fixture();
  const store = new JobStore(new SsyncClient(api.url, 'fixture-key'), options);
  try {
    store.start(); await until(() => store.snapshot.connection === 'live');
    assert.equal(store.snapshot.jobs.length, 6, 'empty WS initial must preserve HTTP history');
    const ws = api.requests.find(request => request.method === 'WS')!;
    assert.equal(ws.key, 'fixture-key'); assert.doesNotMatch(ws.url, /api_key/);
    api.hold(); const pending = store.refresh();
    await until(() => api.requests.filter(request => request.url.startsWith('/api/status')).length === 2);
    const completed = { ...demoJobs[0], state: 'CD' as const };
    api.update(completed); await until(() => store.find(jobKey(completed))?.state === 'CD');
    api.release(); await pending;
    assert.equal(store.find(jobKey(completed))?.state, 'CD');
    api.disconnect(); await until(() => store.snapshot.connection === 'polling');
    await until(() => api.requests.filter(request => request.method === 'WS').length === 2 && store.snapshot.connection === 'live');
    assert.equal(store.snapshot.jobs.length, 6);
  } finally { store.dispose(); await api.close(); }
});

test('late HTTP results cannot leak across configuration changes or revive a stopped store', async () => {
  const api = await fixture();
  const store = new JobStore(new SsyncClient(api.url, ''), options);
  try {
    await store.refresh();
    api.hold(); const old = store.refresh();
    await until(() => api.requests.length === 2);
    store.update(new SsyncClient(api.url, ''), { ...options, showCompleted: false });
    api.release(); await old;
    assert.equal(store.snapshot.jobs.length, 0);
    await store.refresh();
    assert.equal(store.snapshot.jobs.length, 3);
    store.start(); store.stop();
    await new Promise(resolve => setTimeout(resolve, 40));
    assert.equal(store.snapshot.connection, 'paused');
    assert.equal(api.requests.filter(request => request.method === 'WS').length, 0);
  } finally { store.dispose(); await api.close(); }
});

test('malformed realtime data triggers HTTP reconciliation without clearing jobs', async () => {
  const api = await fixture();
  const store = new JobStore(new SsyncClient(api.url, ''), options);
  try {
    store.start(); await until(() => store.snapshot.connection === 'live');
    const count = api.requests.length;
    api.broadcast('invalid JSON');
    await until(() => api.requests.length > count && !store.snapshot.refreshing);
    assert.equal(store.snapshot.jobs.length, 6);
  } finally { store.dispose(); await api.close(); }
});

test('invalid configuration blocks transport and disposed stores cannot restart', async () => {
  const api = await fixture();
  const client = new SsyncClient(api.url, '', 1000, true, 'Invalid configured URL');
  const store = new JobStore(client, options);
  try {
    await store.refresh();
    assert.match(store.snapshot.error!, /Invalid configured URL/);
    assert.equal(api.requests.length, 0);
    store.dispose(); store.start(); await store.refresh();
    assert.equal(api.requests.length, 0);
    assert.equal(store.snapshot.connection, 'paused');
  } finally { store.dispose(); await api.close(); }
});
