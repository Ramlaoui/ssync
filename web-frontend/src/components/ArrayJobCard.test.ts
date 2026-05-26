import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import ArrayJobCard from './ArrayJobCard.svelte';
import type { ArrayJobGroup, JobInfo } from '../types/api';

const task = {
  job_id: '123_0',
  name: 'array-task',
  state: 'R',
  hostname: 'cluster.test',
  user: null,
  partition: null,
  nodes: null,
  cpus: null,
  memory: null,
  time_limit: null,
  runtime: '00:01',
  reason: null,
  work_dir: null,
  stdout_file: null,
  stderr_file: null,
  submit_time: null,
  submit_line: null,
  start_time: null,
  end_time: null,
  node_list: null,
  array_job_id: '123',
  array_task_id: '0',
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

const group = {
  array_job_id: '123',
  job_name: 'array-job',
  hostname: 'cluster.test',
  total_tasks: 1,
  tasks: [task],
  pending_count: 0,
  running_count: 1,
  completed_count: 0,
  failed_count: 0,
  cancelled_count: 0,
} satisfies ArrayJobGroup;

describe('ArrayJobCard', () => {
  let container: HTMLElement;
  let component: Record<string, unknown> | undefined;

  beforeEach(() => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (component) {
      unmount(component as never);
      component = undefined;
    }
    container.remove();
    vi.restoreAllMocks();
  });

  it('opens a context menu on right click without crashing', () => {
    component = mount(ArrayJobCard, {
      target: container,
      props: { group },
    });

    const card = container.querySelector<HTMLButtonElement>('.array-job-card');
    expect(card).toBeTruthy();

    card?.dispatchEvent(
      new MouseEvent('contextmenu', {
        bubbles: true,
        cancelable: true,
        clientX: 42,
        clientY: 64,
      }),
    );
    flushSync();

    const menu = container.querySelector<HTMLElement>('.context-menu');
    expect(menu).toBeTruthy();
    expect(menu?.style.left).toBe('42px');
    expect(menu?.style.top).toBe('64px');
  });

  it('does not crash when an array group has no task list yet', () => {
    component = mount(ArrayJobCard, {
      target: container,
      props: {
        group: {
          ...group,
          tasks: undefined,
        } as unknown as ArrayJobGroup,
      },
    });

    const card = container.querySelector<HTMLButtonElement>('.array-job-card');
    card?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    flushSync();

    expect(container.querySelector('.task-list')).toBeTruthy();
    expect(container.textContent).toContain('array-job');
  });
});
