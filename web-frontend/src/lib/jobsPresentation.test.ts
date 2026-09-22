import { describe, expect, it } from 'vitest';
import { get } from 'svelte/store';
import { createMockJob } from '../test/utils/mockData';
import { jobsWorkspace, selectJob, setJobView } from '../stores/workspace';
import { durationSeconds, filterJobs, gpuCount, jobRoute, jobStatus, withinHistoryWindow } from './jobsPresentation';

const filters = { query: '', host: '', user: '', view: 'all' as const, newestFirst: true };

describe('Jobs workspace', () => {
  it('filters identical job IDs independently by host and searches case insensitively', () => {
    const jobs = [
      createMockJob({ job_id: '42', hostname: 'alpha', name: 'Train', user: 'alice' }),
      createMockJob({ job_id: '42', hostname: 'beta', name: 'Train', user: 'alice' }),
      createMockJob({ job_id: '43', hostname: 'alpha', name: 'Other', user: 'bob' }),
    ];
    expect(filterJobs(jobs, { ...filters, query: 'TRAIN', host: 'alpha', user: 'ali' })).toEqual([jobs[0]]);
  });

  it('orders jobs by submission date without mutating live data', () => {
    const jobs = [
      createMockJob({ job_id: '3', submit_time: '2026-09-20T10:00:00Z' }),
      createMockJob({ job_id: '2', submit_time: '2026-09-21T10:00:00Z' }),
    ];
    expect(filterJobs(jobs, filters).map(job => job.job_id)).toEqual(['2', '3']);
    expect(filterJobs(jobs, { ...filters, newestFirst: false })).toEqual(jobs);
    expect(jobs[0].job_id).toBe('3');
  });

  it('recognizes Slurm state names and flags failures for attention', () => {
    expect(jobStatus('RUNNING').tone).toBe('running');
    expect(jobStatus('COMPLETED').tone).toBe('success');
    expect(jobStatus('CANCELLED by 1001').label).toBe('Cancelled');
    expect(jobStatus('OUT_OF_MEMORY+').attention).toBe(true);
    expect(jobStatus('unrecognized').label).toBe('Unknown');
    expect(filterJobs([createMockJob({ state: 'TO' }), createMockJob({ state: 'CD' })], { ...filters, view: 'attention' })).toHaveLength(1);
  });

  it('narrows cached history while keeping active and recently finished long jobs', () => {
    const now = Date.parse('2026-09-22T12:00:00Z');
    const old = createMockJob({ state: 'CD', end_time: '2026-08-01T12:00:00Z' });
    expect(withinHistoryWindow(old, '7d', now)).toBe(false);
    expect(withinHistoryWindow({ ...old, state: 'R' }, '7d', now)).toBe(true);
    expect(withinHistoryWindow({ ...old, end_time: '2026-09-22T11:00:00Z' }, '7d', now)).toBe(true);
    expect(withinHistoryWindow({ ...old, end_time: null, submit_time: null }, '7d', now)).toBe(true);
  });

  it('preserves list context when selecting and expanding a failed job', () => {
    setJobView('attention', 'cluster.test');
    jobsWorkspace.update(state => ({ ...state, query: 'train', scrollTop: 640 }));
    selectJob(createMockJob({ job_id: '42_3', hostname: 'cluster.test', state: 'F' }));
    const state = get(jobsWorkspace);
    expect(state).toMatchObject({ query: 'train', host: 'cluster.test', scrollTop: 640, selection: { id: '42_3', host: 'cluster.test' }, tab: 'errors' });
    expect(jobRoute('42_3', 'cluster + test', state.tab)).toBe('/jobs/42_3/cluster%20%2B%20test?tab=errors');
    setJobView('all');
  });
});

describe('Reported resources', () => {
  it('uses allocated GPUs without double counting typed TRES', () => {
    expect(gpuCount(createMockJob({ alloc_tres: 'cpu=8,gres/gpu=2,gres/gpu:a100=2', req_tres: 'gres/gpu=8' }))).toBe(2);
    expect(gpuCount(createMockJob({ alloc_tres: null, req_tres: 'gres/gpu:a100=2,gres/gpu:v100=1' }))).toBe(3);
    expect(gpuCount(createMockJob({ alloc_tres: null, req_tres: null, gres: 'gpu:a100:4(S:0)' }))).toBe(4);
    expect(gpuCount(createMockJob({ alloc_tres: null, req_tres: null, gres: null }))).toBeNull();
  });

  it.each([['01:30:00', 5400], ['15:30', 930], ['2-01:30:00', 178200], ['1-02:30', 95400], ['60', 3600], ['UNLIMITED', null], [null, null]])('parses duration %s', (value, expected) => {
    expect(durationSeconds(value as string | null)).toBe(expected);
  });
});
