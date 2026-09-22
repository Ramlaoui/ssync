import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, configure, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { get } from 'svelte/store';
import JobsPage from './JobsPage.svelte';
import JobPage from './JobPage.svelte';
import { jobStateManager } from '../lib/JobStateManager';
import { jobsWorkspace, setJobView } from '../stores/workspace';
import { preferences } from '../stores/preferences';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), push: vi.fn().mockResolvedValue(undefined), fetchJob: vi.fn() }));

vi.mock('../services/api', async () => {
  const { writable } = await import('svelte/store');
  return { api: { get: mocks.get, post: mocks.post }, apiConfig: writable({ authenticated: true, apiKey: '', baseURL: '', authError: null }) };
});
vi.mock('svelte-spa-router', async importOriginal => ({ ...await importOriginal<object>(), push: mocks.push }));
vi.mock('../lib/JobStateManager', async () => {
  const { writable, derived } = await import('svelte/store');
  const { createMockJob } = await import('../test/utils/mockData');
  const jobs = writable([
    createMockJob({ job_id: '111', hostname: 'alpha', name: 'First training', state: 'R' }),
    createMockJob({ job_id: '222', hostname: 'beta', name: 'Second training', state: 'R' }),
  ]);
  return { jobStateManager: {
    getAllJobs: () => jobs,
    getJob: (id: string, host: string) => derived(jobs, values => values.find(job => job.job_id === id && job.hostname === host) || null),
    getArrayJobGroups: () => writable([]),
    getHostStates: () => writable(new Map()),
    getState: () => writable({ dataSource: 'api' }),
    setCurrentViewJob: vi.fn(),
    fetchSingleJob: mocks.fetchJob,
    syncAllHosts: vi.fn().mockResolvedValue(undefined),
    forceRefresh: vi.fn().mockResolvedValue(undefined),
  } };
});

configure({ getElementError: message => new Error(message || 'Element not found') });
beforeEach(() => {
  Element.prototype.animate = vi.fn(() => ({ cancel: vi.fn(), finish: vi.fn(), finished: Promise.resolve(), effect: null, currentTime: 0 })) as never;
  setJobView('all');
  preferences.update(value => ({ ...value, autoRefresh: false }));
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  mocks.fetchJob.mockImplementation((id, host) => Promise.resolve(get(jobStateManager.getAllJobs()).find(job => job.job_id === id && job.hostname === host)));
  mocks.get.mockImplementation((url: string) => Promise.resolve({ data: url === '/api/hosts' ? [] : { watchers: [], events: [] } }));
  mocks.post.mockResolvedValue({ data: { success: true } });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('Job inspector interactions', () => {
  it('opens from the list, maximizes the same job and preserves filters', async () => {
    render(JobsPage);
    await fireEvent.input(screen.getByRole('textbox', { name: 'Search jobs' }), { target: { value: 'Second' } });
    await fireEvent.click(screen.getByRole('button', { name: /Inspect Second training/ }));
    expect(await screen.findByRole('heading', { name: 'Second training', level: 1 })).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button', { name: 'Maximize job' }));
    expect(mocks.push).toHaveBeenCalledWith('/jobs/222/beta');
    expect(get(jobsWorkspace)).toMatchObject({ query: 'Second', selection: { id: '222', host: 'beta' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Close job' }));
    expect(screen.queryByRole('region', { name: 'Job detail' })).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Search jobs' })).toHaveValue('Second');
    cleanup();
    jobsWorkspace.update(state => ({ ...state, selection: { id: '222', host: 'beta' } }));
    render(JobPage, { params: { id: '222', host: 'beta' } });
    await fireEvent.click(await screen.findByRole('button', { name: 'Close job' }));
    expect(get(jobsWorkspace)).toMatchObject({ query: 'Second', selection: null });
    expect(mocks.push).toHaveBeenLastCalledWith('/');
  });

  it('does not replace the selected script when an earlier request arrives late', async () => {
    let resolveEarlier!: (value: unknown) => void;
    mocks.get.mockImplementation((url: string) => {
      if (url === '/api/jobs/111/script') return new Promise(resolve => { resolveEarlier = resolve; });
      if (url === '/api/jobs/222/script') return Promise.resolve({ data: { script_content: 'echo CURRENT_SCRIPT', content_length: 19, script_path: '/work/current.sh' } });
      return Promise.resolve({ data: url === '/api/hosts' ? [] : { watchers: [], events: [] } });
    });
    render(JobsPage);
    await fireEvent.click(screen.getByRole('button', { name: /Inspect First training/ }));
    await fireEvent.click(await screen.findByRole('button', { name: 'Script' }));
    await waitFor(() => expect(mocks.get.mock.calls.map(([url]) => url)).toContain('/api/jobs/111/script'));
    await fireEvent.click(screen.getByRole('button', { name: /Inspect Second training/ }));
    await fireEvent.click(await screen.findByRole('button', { name: 'Script' }));
    await waitFor(() => expect(screen.getByRole('region', { name: 'Job detail' })).toHaveTextContent('CURRENT_SCRIPT'));
    resolveEarlier({ data: { script_content: 'echo OBSOLETE_SCRIPT', content_length: 20, script_path: '/work/old.sh' } });
    await waitFor(() => expect(screen.getByRole('region', { name: 'Job detail' })).not.toHaveTextContent('OBSOLETE_SCRIPT'));
    expect(screen.getByRole('heading', { name: 'Second training', level: 1 })).toBeInTheDocument();
  });

  it('only cancels the selected host/job after confirmation', async () => {
    render(JobsPage);
    await fireEvent.click(screen.getByRole('button', { name: /Inspect First training/ }));
    await fireEvent.click(await screen.findByRole('button', { name: 'Cancel job' }));
    expect(mocks.post).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog', { name: 'Cancel this job?' });
    expect(dialog).toHaveTextContent('Cancel #111 on alpha');
    await fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel job' }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/jobs/111/cancel', null, { params: { host: 'alpha' } }));
  });
});
