import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, configure, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';

const mocks = vi.hoisted(() => ({ launch: vi.fn().mockResolvedValue(undefined), get: vi.fn().mockResolvedValue({ data: [{ hostname: 'cluster.test' }] }) }));
vi.mock('./CodeMirrorEditor.svelte', () => import('../test/fixtures/Editor.svelte'));
vi.mock('../services/api', async () => {
  const { writable } = await import('svelte/store');
  return { api: { get: mocks.get }, apiConfig: writable({ authenticated: true, apiKey: '', baseURL: '' }) };
});
vi.mock('../stores/launchMonitor', async () => {
  const { writable } = await import('svelte/store');
  return { launchMonitor: { startLaunch: mocks.launch }, launchEditDraft: writable(null) };
});

configure({ getElementError: message => new Error(message || 'Element not found') });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('updates resource directives, restores the draft, and submits only after review', async () => {
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  Element.prototype.animate = vi.fn(() => ({ cancel: vi.fn(), finish: vi.fn(), finished: Promise.resolve(), effect: null, currentTime: 0 })) as never;
  const { default: JobLauncher } = await import('./JobLauncher.svelte');
  const view = render(JobLauncher);
  await fireEvent.input(screen.getByRole('textbox', { name: 'Source directory' }), { target: { value: '/work/training' } });
  await fireEvent.input(screen.getByRole('spinbutton', { name: 'CPUs' }), { target: { value: '8' } });
  await waitFor(() => expect((screen.getByRole('textbox', { name: 'Batch script' }) as HTMLTextAreaElement).value).toContain('#SBATCH --cpus-per-task=8'));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Review job' })).toBeEnabled());
  const draft = vi.mocked(localStorage.setItem).mock.calls.filter(([key]) => key === 'ssync_launch_draft').at(-1)?.[1];
  expect(draft).toBeTruthy();
  await view.unmount();
  vi.mocked(localStorage.getItem).mockImplementation(key => key === 'ssync_launch_draft' ? draft! : null);
  render(JobLauncher);
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Source directory' })).toHaveValue('/work/training'));
  expect(screen.getByRole('spinbutton', { name: 'CPUs' })).toHaveValue(8);
  await fireEvent.click(screen.getByRole('button', { name: 'Review job' }));
  const review = await screen.findByRole('dialog', { name: 'Review job' });
  expect(review).toHaveTextContent('/work/training');
  expect(mocks.launch).not.toHaveBeenCalled();
  await fireEvent.click(within(review).getByRole('button', { name: 'Launch job' }));
  await waitFor(() => expect(mocks.launch).toHaveBeenCalledWith(expect.objectContaining({ host: 'cluster.test', source_dir: '/work/training', cpus: 8, script_content: expect.stringContaining('#SBATCH --cpus-per-task=8') })));
  expect(mocks.launch).toHaveBeenCalledTimes(1);
});
