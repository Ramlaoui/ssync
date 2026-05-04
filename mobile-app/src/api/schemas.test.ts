import { jobStatusResponseSchema, watchersResponseSchema } from '@/src/api/schemas';

describe('API schemas', () => {
  it('parses a realistic job status payload', () => {
    const parsed = jobStatusResponseSchema.parse({
      hostname: 'cluster-a',
      jobs: [
        {
          job_id: '1234',
          name: 'train-model',
          state: 'R',
          hostname: 'cluster-a',
          user: 'alice',
          partition: 'gpu',
          nodes: '1',
          cpus: '8',
          memory: '32G',
          time_limit: '02:00:00',
          runtime: '00:15:11',
          reason: null,
          work_dir: '/scratch/alice/project',
          stdout_file: '/tmp/out.log',
          stderr_file: '/tmp/err.log',
          submit_time: '2026-04-02T14:30:00Z',
          submit_line: null,
          start_time: '2026-04-02T14:31:00Z',
          end_time: null,
          node_list: 'gpu001',
          alloc_tres: 'cpu=8,mem=32G',
          req_tres: 'cpu=8,mem=32G',
          cpu_time: null,
          total_cpu: null,
          user_cpu: null,
          system_cpu: null,
          ave_cpu: null,
          ave_cpu_freq: null,
          max_rss: null,
          ave_rss: null,
          max_vmsize: null,
          ave_vmsize: null,
          max_disk_read: null,
          max_disk_write: null,
          ave_disk_read: null,
          ave_disk_write: null,
          consumed_energy: null,
        },
      ],
      total_jobs: 1,
      query_time: '2026-04-02T14:31:15Z',
      cached: false,
    });

    expect(parsed.jobs[0].job_id).toBe('1234');
    expect(parsed.jobs[0].hostname).toBe('cluster-a');
  });

  it('rejects malformed watcher payloads', () => {
    expect(() =>
      watchersResponseSchema.parse({
        watchers: [{ id: 'oops', state: 'active' }],
      }),
    ).toThrow();
  });
});
