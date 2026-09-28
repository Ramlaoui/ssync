import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import JobTabContent from './JobTabContent.svelte';
import { createMockJob } from '../test/utils/mockData';

beforeEach(() => {
  Element.prototype.animate = vi.fn(() => ({ cancel: vi.fn(), finish: vi.fn(), finished: Promise.resolve(), effect: null, currentTime: 0 })) as never;
});
afterEach(cleanup);

describe('Output controls', () => {
  it('shows a retrieval state while a background output refresh is queued', async () => {
    render(JobTabContent, {
      job: createMockJob({ job_id: '12347', hostname: 'cluster1.example.com', state: 'CD' }),
      activeTab: 'output', loadingOutput: false,
      outputData: {
        job_id: '12347', hostname: 'cluster1.example.com', output_type: 'stdout',
        stdout: null, stderr: null, stderr_metadata: null,
        stdout_metadata: { path: '/tmp/slurm-12347.out', exists: false, size_bytes: null, last_modified: null, access_path: null },
        content_truncated: false, content_limit_bytes: 524288, cached: true, stale: true, refresh_queued: true,
      },
    });
    expect(screen.getByText('Retrieving output…')).toBeInTheDocument();
    expect(screen.queryByText('No output available')).not.toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button', { name: 'File details' }));
    expect(within(await screen.findByRole('dialog', { name: 'stdout file' })).getByText('Checking')).toBeInTheDocument();
  });

  it('keeps stream selection and full log access visible while file details stay on demand', async () => {
    const onOutputTypeChange = vi.fn();
    render(JobTabContent, {
      job: createMockJob({ job_id: '42', hostname: 'alpha', state: 'CD' }),
      activeTab: 'output',
      outputData: {
        job_id: '42', hostname: 'alpha', output_type: 'stdout', stderr_metadata: null,
        stdout: 'step 1: finished', stderr: null, content_truncated: true,
        stdout_metadata: { path: '/work/stdout.log', exists: true, size_bytes: 2000000, last_modified: null, access_path: '/raw/stdout' },
      },
      onOutputTypeChange,
    });

    const streams = screen.getByRole('combobox', { name: 'Output stream' });
    expect(streams).toHaveValue('stdout');
    expect(screen.getByRole('link', { name: 'Open full stdout log' })).toHaveAttribute('href', '/raw/stdout');
    expect(screen.getByRole('button', { name: 'Preview' })).toBeInTheDocument();
    expect(screen.queryByText('/work/stdout.log')).not.toBeInTheDocument();

    await fireEvent.click(screen.getByRole('button', { name: 'File details' }));
    const details = within(await screen.findByRole('dialog', { name: 'stdout file' }));
    expect(details.getByText('/work/stdout.log')).toBeInTheDocument();
    await fireEvent.click(details.getByRole('button', { name: 'Close dialog' }));
    await fireEvent.change(streams, { target: { value: 'stderr' } });
    expect(onOutputTypeChange).toHaveBeenCalledWith('stderr');
  });

  it('keeps stream switching and retry available when an output request fails', async () => {
    const retry = vi.fn();
    const changeStream = vi.fn();
    render(JobTabContent, {
      activeTab: 'errors', outputError: 'Output temporarily unavailable',
      onRetryLoadOutput: retry, onOutputTypeChange: changeStream,
    });
    expect(screen.getByRole('alert')).toHaveTextContent('Output temporarily unavailable');
    await fireEvent.change(screen.getByRole('combobox', { name: 'Output stream' }), { target: { value: 'stdout' } });
    expect(changeStream).toHaveBeenCalledWith('stdout');
    await fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
