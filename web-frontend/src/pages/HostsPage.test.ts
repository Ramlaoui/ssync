import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import HostsPage, { displayPath, formatCount, hostJobCounts, orderPartitions } from './HostsPage.svelte';
import { createMockJob } from '../test/utils/mockData';
import type { ArrayJobGroup, PartitionResources } from '../types/api';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('../services/api', () => ({ api: { get: mocks.get } }));
vi.mock('svelte-spa-router', async importOriginal => ({ ...await importOriginal<object>(), push: vi.fn() }));
vi.mock('../lib/JobStateManager', async () => {
  const { writable } = await import('svelte/store');
  const { createMockJob } = await import('../test/utils/mockData');
  return { jobStateManager: {
    getAllJobs: () => writable([createMockJob({ job_id: '1', hostname: 'alpha', state: 'R' }), createMockJob({ job_id: '2', hostname: 'alpha', state: 'PD' })]),
    getArrayJobGroups: () => writable([]),
    getHostStates: () => writable(new Map()),
  } };
});

function partition(name: string, overrides: Partial<PartitionResources> = {}): PartitionResources {
  return { partition: name, availability: 'up', states: [], nodes_total: 4, cpus_alloc: 169344, cpus_idle: 36480, cpus_other: 0, cpus_total: 205824, gpus_total: 0, gpus_used: 0, gpus_idle: 0, ...overrides };
}

beforeEach(() => {
  mocks.get.mockImplementation((url: string) => Promise.resolve({ data: url === '/api/hosts'
    ? [{ hostname: 'alpha', work_dir: '[CONFIGURED]', scratch_dir: '/scratch/alpha' }]
    : [{ hostname: 'alpha', query_time: new Date().toISOString(), partitions: [partition('empty', { nodes_total: 0, cpus_total: 0, cpus_alloc: 0, cpus_idle: 0 }), ...Array.from({ length: 7 }, (_, i) => partition(`p${i}`))] }] }));
});
afterEach(() => cleanup());

describe('Hosts page helpers', () => {
  it('hides redaction placeholders but keeps real paths', () => {
    expect(displayPath('[CONFIGURED]')).toBeNull();
    expect(displayPath('[REDACTED]')).toBeNull();
    expect(displayPath('  ')).toBeNull();
    expect(displayPath('/scratch/user')).toBe('/scratch/user');
  });

  it('formats counts with thousands separators', () => {
    expect(formatCount(169344, 'en-US')).toBe('169,344');
    expect(formatCount(0, 'en-US')).toBe('0');
    expect(formatCount(null)).toBe('—');
  });

  it('counts running and pending jobs including array group tasks once', () => {
    const jobs = [createMockJob({ job_id: '1', hostname: 'alpha', state: 'R' }), createMockJob({ job_id: '2', hostname: 'beta', state: 'R' })];
    const groups = [{ hostname: 'alpha', tasks: [createMockJob({ job_id: '1', hostname: 'alpha', state: 'R' }), createMockJob({ job_id: '3_1', hostname: 'alpha', state: 'PD' }), createMockJob({ job_id: '3_2', hostname: 'alpha', state: 'CD' })] }] as ArrayJobGroup[];
    expect(hostJobCounts(jobs, groups, 'alpha')).toEqual({ running: 1, pending: 1 });
  });

  it('moves partitions without nodes to the end', () => {
    expect(orderPartitions([partition('a', { nodes_total: 0 }), partition('b')]).map(item => item.partition)).toEqual(['b', 'a']);
  });
});

describe('Hosts page', () => {
  it('renders a compact partition table without placeholders', async () => {
    render(HostsPage);
    const table = await screen.findByRole('table');
    expect(screen.queryByText('[CONFIGURED]')).not.toBeInTheDocument();
    expect(screen.getByText('/scratch/alpha')).toBeInTheDocument();
    expect(within(table).queryByText('GPUs', { exact: false })).not.toBeInTheDocument();
    expect(within(table).getAllByText((205824).toLocaleString(), { exact: false }).length).toBe(6);
    expect(document.querySelector('.host-meta')).toHaveTextContent('1 running · 1 pending');
    await fireEvent.click(screen.getByRole('button', { name: 'Show all 8 partitions' }));
    expect(within(table).getAllByRole('row')).toHaveLength(9);
  });
});
