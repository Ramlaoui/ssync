import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import JobTabContent from './JobTabContent.svelte';
import { mockJobs } from '../test/utils/mockData';
import type { OutputData } from '../types/api';

describe('JobTabContent output states', () => {
  let container: HTMLElement;
  let component: Record<string, unknown> | undefined;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (component) {
      unmount(component as never);
      component = undefined;
    }
    container.remove();
  });

  it('shows a retrieval state while a background output refresh is queued', async () => {
    const outputData = {
      job_id: '12347',
      hostname: 'cluster1.example.com',
      output_type: 'stdout',
      stdout: null,
      stderr: null,
      stdout_metadata: {
        path: '/tmp/slurm-12347.out',
        exists: false,
        size_bytes: null,
        last_modified: null,
        access_path: null,
      },
      stderr_metadata: null,
      content_truncated: false,
      content_limit_bytes: 524288,
      cached: true,
      stale: true,
      refresh_queued: true,
    } satisfies OutputData;

    component = mount(JobTabContent, {
      target: container,
      props: {
        job: mockJobs[2],
        activeTab: 'output',
        outputData,
        loadingOutput: false,
      },
    });

    await tick();
    flushSync();

    expect(container.textContent).toContain('Retrieving output from cluster...');
    expect(container.textContent).toContain('Checking');
    expect(container.textContent).not.toContain('No output available');
  });
});
