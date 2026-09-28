import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import WatchersPage from './WatchersPage.svelte';
import { watcherEvents, watchers, watcherStats } from '../stores/watchers';
import type { Watcher, WatcherStats } from '../types/watchers';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
  push: vi.fn(),
}));

vi.mock('../services/api', async () => {
  const { writable } = await import('svelte/store');
  return {
    api: { get: mocks.get, post: mocks.post, delete: mocks.delete },
    apiConfig: writable({ authenticated: true, apiKey: '', baseURL: '', authError: null }),
  };
});
vi.mock('svelte-spa-router', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  push: mocks.push,
}));
vi.mock('../lib/JobStateManager', async () => {
  const { writable } = await import('svelte/store');
  return {
    jobStateManager: {
      getAllJobs: () => writable([]),
      syncAllHosts: vi.fn().mockResolvedValue(undefined),
    },
  };
});

function makeWatcher(id: number, overrides: Partial<Watcher> = {}): Watcher {
  return {
    id,
    job_id: String(58_000_000 + id),
    hostname: 'leonardo',
    name: `watcher-${id}`,
    pattern: '',
    interval_seconds: 60,
    captures: [],
    actions: [{ type: 'resubmit', config: {} }],
    state: 'active',
    trigger_count: 0,
    created_at: '2026-09-28T10:00:00Z',
    last_check: '2026-09-28T10:05:00Z',
    trigger_on_job_end: true,
    trigger_job_states: ['timeout'],
    ...overrides,
  };
}

const sampleWatchers = [
  makeWatcher(1, { name: 'mlff-distill auto resubmit on timeout' }),
  makeWatcher(2, { name: 'wandb sync', pattern: 'HYDRA_OUTPUT_DIR=(.*)', trigger_on_job_end: false, state: 'paused' }),
  makeWatcher(3, { name: 'finished sync', state: 'completed' }),
];

const stats = {
  total_watchers: 33_712,
  watchers_by_state: { active: 45, paused: 612, completed: 33_001, static: 0 },
  total_events: 0,
  events_by_action: {},
  events_last_hour: 0,
  top_watchers: [],
} as unknown as WatcherStats;

function mockApi(list: Watcher[], statsResponse: Promise<unknown>) {
  mocks.get.mockImplementation((url: string) => {
    if (url === '/api/watchers') return Promise.resolve({ data: { watchers: list } });
    if (url === '/api/watchers/events') return Promise.resolve({ data: { events: [], count: 0 } });
    if (url === '/api/watchers/stats') return statsResponse;
    return Promise.resolve({ data: {} });
  });
}

class FakeWebSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: (() => void) | null = null;
  close() {}
}

beforeEach(() => {
  vi.stubGlobal('WebSocket', FakeWebSocket);
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  window.history.replaceState({}, '', '/#/watchers');
  watchers.set([]);
  watcherEvents.set([]);
  watcherStats.set(null);
  mocks.get.mockReset();
  mocks.post.mockReset();
  mocks.delete.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function rowNames(): string[] {
  return Array.from(document.querySelectorAll('.w-open')).map((row) => row.textContent?.trim() || '');
}

describe('WatchersPage', () => {
  it('shows active and paused watchers by default and real totals from stats', async () => {
    mockApi(sampleWatchers, Promise.resolve({ data: stats }));
    render(WatchersPage);

    await waitFor(() => expect(rowNames()).toEqual(['mlff-distill auto resubmit on timeout', 'wandb sync']));

    const tabs = screen.getByRole('group', { name: 'Filter by state' });
    await waitFor(() => expect(within(tabs).getByRole('button', { name: /All/ })).toHaveTextContent('33,712'));
    expect(within(tabs).getByRole('button', { name: /Active & paused/ })).toHaveTextContent('657');
    expect(within(tabs).queryByRole('button', { name: /Static/ })).toBeNull();
    expect(screen.getByText(/45 active · 612 paused/)).toBeInTheDocument();

    await fireEvent.click(within(tabs).getByRole('button', { name: /Completed/ }));
    expect(rowNames()).toEqual(['finished sync']);
  });

  it('marks counts as lower bounds when the list hits its cap and no totals are known', async () => {
    const capped = Array.from({ length: 300 }, (_, index) =>
      makeWatcher(index + 10, { state: index < 5 ? 'active' : 'completed' }),
    );
    mockApi(capped, new Promise(() => {}));
    render(WatchersPage);

    const tabs = await screen.findByRole('group', { name: 'Filter by state' });
    await waitFor(() => expect(within(tabs).getByRole('button', { name: /All/ })).toHaveTextContent('300+'));
    expect(within(tabs).getByRole('button', { name: 'Active 5+' })).toBeInTheDocument();
    expect(screen.getByText(/Only the 300 most recent watchers are loaded/)).toBeInTheDocument();
  });

  it('summarises triggers in the row and selects a row for the activity panel', async () => {
    mockApi(sampleWatchers, Promise.resolve({ data: stats }));
    render(WatchersPage);

    await waitFor(() => expect(rowNames()).toHaveLength(2));
    expect(screen.getByText('Job ends: timeout')).toBeInTheDocument();
    expect(screen.getByText('HYDRA_OUTPUT_DIR=(.*)')).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('button', { name: /Show activity for wandb sync/ }));
    const panel = document.getElementById('watcher-activity-panel');
    expect(panel).not.toBeNull();
    expect(within(panel as HTMLElement).getByRole('heading', { level: 2 })).toHaveTextContent('wandb sync');
    expect(window.location.hash).toContain('watcher=2');
  });

  it('offers row actions as a labelled menu without invoking them', async () => {
    mockApi(sampleWatchers, Promise.resolve({ data: stats }));
    render(WatchersPage);

    await waitFor(() => expect(rowNames()).toHaveLength(2));
    await fireEvent.click(screen.getByRole('button', { name: 'Actions for mlff-distill auto resubmit on timeout' }));

    const menu = await screen.findByRole('menu');
    const labels = within(menu).getAllByRole('menuitem').map((item) => item.textContent?.trim());
    expect(labels).toEqual(['Run now', 'Pause', 'Edit…', 'Copy to jobs…', 'Open job', 'Delete…']);
    expect(within(menu).getByRole('separator')).toBeInTheDocument();
    expect(within(menu).getByRole('menuitem', { name: 'Delete…' })).toHaveClass('danger');

    await fireEvent.keyDown(menu, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.delete).not.toHaveBeenCalled();
  });
});
