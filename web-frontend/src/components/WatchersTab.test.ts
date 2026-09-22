import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { http, HttpResponse } from 'msw';
import WatchersTab from './WatchersTab.svelte';
import { addHandler, setupMSW } from '../test/utils/mockApi';
import {
  jobWatchersErrors,
  jobWatchersLoadedAt,
  jobWatchersLoading,
  watcherEvents,
  watchers,
} from '../stores/watchers';
import type { JobInfo } from '../types/api';
import type { Watcher, WatcherEvent } from '../types/watchers';

setupMSW();

const job = {
  job_id: '12345',
  hostname: 'cluster.example.com',
  name: 'watcher-test-job',
  state: 'R',
  user: null,
  partition: null,
  nodes: null,
  cpus: null,
  memory: null,
  time_limit: null,
  runtime: null,
  reason: null,
  work_dir: null,
  stdout_file: null,
  stderr_file: null,
  submit_time: null,
  submit_line: null,
  start_time: null,
  end_time: null,
  node_list: null,
  alloc_tres: null,
  req_tres: null,
  cpu_time: null,
  total_cpu: null,
  user_cpu: null,
  system_cpu: null,
  ave_cpu: null,
  ave_cpu_freq: null,
  req_cpu_freq_min: null,
  req_cpu_freq_max: null,
  max_rss: null,
  ave_rss: null,
  max_vmsize: null,
  ave_vmsize: null,
  max_disk_read: null,
  max_disk_write: null,
  ave_disk_read: null,
  ave_disk_write: null,
  consumed_energy: null,
} satisfies JobInfo;

const watcher = {
  id: 17,
  job_id: job.job_id,
  hostname: job.hostname,
  name: 'command-output-watcher',
  pattern: 'DONE',
  interval_seconds: 30,
  captures: [],
  actions: [{ type: 'run_command', config: { command: 'cat result.txt' } }],
  state: 'active',
  trigger_count: 1,
  created_at: '2026-05-13T12:00:00Z',
  last_check: '2026-05-13T12:01:00Z',
} satisfies Watcher;

const commandEvent = {
  id: 99,
  watcher_id: watcher.id,
  watcher_name: watcher.name,
  job_id: job.job_id,
  hostname: job.hostname,
  timestamp: '2026-05-13T12:02:00Z',
  matched_text: '',
  captured_vars: {},
  action_type: 'run_command',
  action_result: 'COMMAND_OUTPUT_SENTINEL\nline two from command',
  success: true,
} satisfies WatcherEvent;

describe('WatchersTab', () => {
  let container: HTMLElement;
  let component: Record<string, unknown> | undefined;

  beforeEach(() => {
    vi.useFakeTimers();
    container = document.createElement('div');
    document.body.appendChild(container);
    watchers.set([]);
    watcherEvents.set([]);
    jobWatchersLoading.set({});
    jobWatchersErrors.set({});
    jobWatchersLoadedAt.set({});

    addHandler(
      http.get('/api/jobs/:jobId/watchers', () =>
        HttpResponse.json({
          job_id: job.job_id,
          watchers: [watcher],
          count: 1,
        }),
      ),
    );
    addHandler(
      http.get('/api/watchers/events', () =>
        HttpResponse.json({
          events: [commandEvent],
          count: 1,
        }),
      ),
    );
  });

  afterEach(() => {
    if (component) {
      unmount(component as never);
      component = undefined;
    }
    container.remove();
    watchers.set([]);
    watcherEvents.set([]);
    jobWatchersLoading.set({});
    jobWatchersErrors.set({});
    jobWatchersLoadedAt.set({});
    vi.useRealTimers();
  });

  it('embeds command output events inside the expanded watcher details', async () => {
    component = mount(WatchersTab, {
      target: container,
      props: { job },
    });

    await tick();
    await vi.runAllTimersAsync();
    await tick();

    expect(container.textContent).toContain('command-output-watcher');
    expect(container.querySelector('.activity-section')).toBeFalsy();

    const expandButton = container.querySelector<HTMLButtonElement>('button.header-left');
    expect(expandButton).toBeTruthy();

    expandButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    flushSync();

    const activitySection = container.querySelector('.activity-section');
    expect(activitySection).toBeTruthy();
    expect(activitySection?.textContent).toContain('Related Activity');
    expect(activitySection?.textContent).toContain('COMMAND_OUTPUT_SENTINEL');
    expect(activitySection?.textContent).toContain('line two from command');
  });
});
