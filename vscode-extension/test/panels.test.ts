import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Window } from 'happy-dom';
import { demoJobs } from './fixture';
import { STATES, jobKey } from '../src/model';

function panel(page: 'dashboard' | 'logs') {
  const window = new Window();
  const messages: Record<string, unknown>[] = [];
  let saved: unknown;
  Object.assign(window, { acquireVsCodeApi: () => ({
    getState: () => saved, setState: (value: unknown) => { saved = value; },
    postMessage: (value: Record<string, unknown>) => { messages.push(structuredClone(value)); },
  }) });
  window.document.body.innerHTML = readFileSync(`media/${page}.html`, 'utf8');
  window.eval(readFileSync(`media/${page}.js`, 'utf8'));
  const byId = (id: string) => window.document.getElementById(id)!;
  return {
    window, messages, byId,
    send(data: unknown) { window.dispatchEvent(new window.MessageEvent('message', { data })); },
    close() { window.happyDOM.abort(); window.close(); },
  };
}
function snapshot(overrides = {}) {
  return { type: 'snapshot', jobs: demoJobs, hosts: ['atlas', 'borealis', 'idle-cluster'], states: STATES, connection: 'live', updatedAt: Date.now(), ...overrides };
}

test('dashboard renders counts, searches jobs and distinguishes identical IDs across hosts', () => {
  const ui = panel('dashboard');
  try {
    assert.equal(ui.messages[0].command, 'ready');
    ui.send(snapshot());
    assert.equal(ui.byId('count-all').textContent, '6');
    assert.equal(ui.byId('count-running').textContent, '2');
    assert.equal(ui.byId('count-queued').textContent, '1');
    assert.equal(ui.byId('count-failed').textContent, '2');
    const search = ui.byId('search') as unknown as { value: string; dispatchEvent(event: unknown): void };
    search.value = '28491'; search.dispatchEvent(new ui.window.Event('input'));
    assert.equal(ui.byId('jobs').querySelectorAll('tr').length, 2);
    const keys = [...ui.byId('jobs').querySelectorAll('.job-link')].map(button => button.getAttribute('data-key'));
    assert.deepEqual(keys.sort(), [jobKey(demoJobs[0]), jobKey(demoJobs[2])].sort());
  } finally { ui.close(); }
});

test('dashboard card and cluster filters offer a recoverable empty state', () => {
  const ui = panel('dashboard');
  try {
    ui.send(snapshot());
    (ui.window.document.querySelector('[data-filter="failed"]') as any).click();
    assert.equal(ui.byId('jobs').querySelectorAll('tr').length, 2);
    const host = ui.byId('host') as any;
    host.value = 'idle-cluster'; host.dispatchEvent(new ui.window.Event('change'));
    assert.equal(ui.byId('empty-title').textContent, 'No matching jobs');
    assert.equal(ui.byId('empty-action').textContent, 'Clear filters');
    (ui.byId('empty-action') as any).click();
    assert.equal(ui.byId('jobs').querySelectorAll('tr').length, 6);
  } finally { ui.close(); }
});

test('outage updates preserve job DOM and keyboard focus; changed jobs restore focused actions', () => {
  const ui = panel('dashboard');
  try {
    ui.send(snapshot());
    const button = ui.byId('jobs').querySelector('.job-link') as any;
    button.focus();
    ui.send(snapshot({ connection: 'offline', error: 'HTTP 503', refreshing: false }));
    assert.equal(ui.byId('jobs').querySelector('.job-link'), button);
    assert.equal(ui.window.document.activeElement, button);
    assert.equal(ui.byId('warning').hidden, false);
    assert.match(ui.byId('stale-note').textContent!, /last known jobs/);
    const updated = demoJobs.map((job, index) => index === 0 ? { ...job, runtime: '02:15:00' } : job);
    ui.send(snapshot({ jobs: updated }));
    assert.equal(ui.window.document.activeElement?.getAttribute('data-key'), jobKey(demoJobs[0]));
  } finally { ui.close(); }
});

test('dashboard renders hostile job content as text and posts exact job identities', () => {
  const ui = panel('dashboard');
  try {
    ui.send(snapshot({ jobs: [{ ...demoJobs[0], name: '<img src=x onerror=alert(1)>' }] }));
    assert.equal(ui.byId('jobs').querySelector('img'), null);
    const button = ui.byId('jobs').querySelector('.job-link') as any;
    assert.match(button.textContent, /<img/);
    button.click();
    assert.deepEqual(ui.messages.at(-1), { command: 'open', key: jobKey(demoJobs[0]) });
  } finally { ui.close(); }
});

test('log tabs, copy and keyboard navigation work; output is literal text', () => {
  const ui = panel('logs');
  try {
    ui.send({ type: 'output', job: demoJobs[0], states: STATES, stdout: '<script>alert(1)</script>', stderr: 'warning', updatedAt: Date.now(), loading: false });
    assert.equal(ui.byId('output').querySelector('script'), null);
    assert.equal(ui.byId('output').textContent, '<script>alert(1)</script>');
    (ui.byId('stderr-tab') as any).click();
    assert.equal(ui.byId('output').textContent, 'warning');
    (ui.byId('copy') as any).click();
    assert.deepEqual(ui.messages.at(-1), { command: 'copy', stream: 'stderr' });
    ui.window.document.querySelector('.tabs')!.dispatchEvent(new ui.window.KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
    assert.equal(ui.byId('stdout-tab').getAttribute('aria-selected'), 'true');
    assert.equal(ui.window.document.activeElement, ui.byId('stdout-tab'));
  } finally { ui.close(); }
});

test('log output remains readable after errors and terminal states remove cancellation', () => {
  const ui = panel('logs');
  try {
    const output = { type: 'output', job: demoJobs[0], states: STATES, stdout: 'epoch 1\nepoch 2\n', updatedAt: Date.now(), loading: false };
    ui.send(output);
    const region = ui.byId('log-region') as any;
    const follow = ui.byId('follow') as any;
    follow.checked = false; follow.dispatchEvent(new ui.window.Event('change'));
    region.scrollTop = 20;
    ui.send({ ...output, stdout: 'epoch 1\nepoch 2\nepoch 3\n', error: 'Connection lost' });
    assert.equal(region.scrollTop, 20);
    assert.match(ui.byId('log-error').textContent!, /last fetched output/);
    assert.equal(ui.byId('output').textContent, 'epoch 1\nepoch 2\nepoch 3\n');
    ui.send({ ...output, job: { ...demoJobs[0], state: 'CD' } });
    assert.equal(ui.byId('cancel').hidden, true);
    assert.match(ui.byId('log-status').textContent!, /job finished/);
  } finally { ui.close(); }
});
