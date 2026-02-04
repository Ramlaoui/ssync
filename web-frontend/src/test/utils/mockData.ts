/**
 * Mock data for tests
 */

import type {
  JobInfo,
  HostInfo,
  JobStatusResponse,
  ArrayJobGroup,
  PartitionStatusResponse
} from '../../types/api';

const baseJob: JobInfo = {
  job_id: '0',
  name: '',
  state: 'PD',
  hostname: '',
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
};

function buildJob(overrides: Partial<JobInfo>): JobInfo {
  return { ...baseJob, ...overrides };
}

export const mockHosts: HostInfo[] = [
  { hostname: 'cluster1.example.com', work_dir: '/home/testuser', scratch_dir: '/scratch' },
  { hostname: 'cluster2.example.com', work_dir: '/home/testuser', scratch_dir: '/scratch' },
];

export const mockJobs: JobInfo[] = [
  buildJob({
    job_id: '12345',
    hostname: 'cluster1.example.com',
    name: 'test-job-1',
    state: 'R',
    user: 'testuser',
    partition: 'gpu',
    cpus: '4',
    nodes: '1',
    memory: '8G',
    runtime: '00:15:32',
    time_limit: '02:00:00',
    submit_time: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
    start_time: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
    work_dir: '/home/testuser/jobs/test-job-1',
    stdout_file: '/home/testuser/jobs/test-job-1/output.log',
    stderr_file: '/home/testuser/jobs/test-job-1/error.log',
  }),
  buildJob({
    job_id: '12346',
    hostname: 'cluster1.example.com',
    name: 'test-job-2',
    state: 'PD',
    user: 'testuser',
    partition: 'cpu',
    cpus: '2',
    nodes: '1',
    memory: '4G',
    runtime: 'N/A',
    time_limit: '01:00:00',
    submit_time: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    work_dir: '/home/testuser/jobs/test-job-2',
    stdout_file: '/home/testuser/jobs/test-job-2/output.log',
    stderr_file: '/home/testuser/jobs/test-job-2/error.log',
  }),
  buildJob({
    job_id: '12347',
    hostname: 'cluster1.example.com',
    name: 'test-job-3',
    state: 'CD',
    user: 'testuser',
    partition: 'cpu',
    cpus: '8',
    nodes: '2',
    memory: '16G',
    runtime: '01:23:45',
    time_limit: '02:00:00',
    submit_time: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    start_time: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    end_time: new Date(Date.now() - 36 * 60 * 1000).toISOString(),
    work_dir: '/home/testuser/jobs/test-job-3',
    stdout_file: '/home/testuser/jobs/test-job-3/output.log',
    stderr_file: '/home/testuser/jobs/test-job-3/error.log',
    exit_code: '0',
  }),
  buildJob({
    job_id: '12348',
    hostname: 'cluster2.example.com',
    name: 'test-job-4',
    state: 'F',
    user: 'testuser',
    partition: 'gpu',
    cpus: '4',
    nodes: '1',
    memory: '8G',
    runtime: '00:05:12',
    time_limit: '01:00:00',
    submit_time: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    start_time: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    end_time: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    work_dir: '/home/testuser/jobs/test-job-4',
    stdout_file: '/home/testuser/jobs/test-job-4/output.log',
    stderr_file: '/home/testuser/jobs/test-job-4/error.log',
    exit_code: '1',
  }),
];

export const mockArrayJobs: JobInfo[] = [
  buildJob({
    job_id: '12349_1',
    hostname: 'cluster1.example.com',
    name: 'array-job[1]',
    state: 'R',
    user: 'testuser',
    partition: 'cpu',
    cpus: '2',
    nodes: '1',
    memory: '4G',
    runtime: '00:10:00',
    time_limit: '01:00:00',
    submit_time: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    start_time: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    array_job_id: '12349',
    array_task_id: '1',
    work_dir: '/home/testuser/jobs/array-job',
    stdout_file: '/home/testuser/jobs/array-job/output_1.log',
    stderr_file: '/home/testuser/jobs/array-job/error_1.log',
  }),
  buildJob({
    job_id: '12349_2',
    hostname: 'cluster1.example.com',
    name: 'array-job[2]',
    state: 'R',
    user: 'testuser',
    partition: 'cpu',
    cpus: '2',
    nodes: '1',
    memory: '4G',
    runtime: '00:10:00',
    time_limit: '01:00:00',
    submit_time: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    start_time: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    array_job_id: '12349',
    array_task_id: '2',
    work_dir: '/home/testuser/jobs/array-job',
    stdout_file: '/home/testuser/jobs/array-job/output_2.log',
    stderr_file: '/home/testuser/jobs/array-job/error_2.log',
  }),
];

export const mockArrayGroup: ArrayJobGroup = {
  array_job_id: '12349',
  job_name: 'array-job',
  hostname: 'cluster1.example.com',
  user: 'testuser',
  total_tasks: 2,
  tasks: mockArrayJobs,
  pending_count: 0,
  running_count: 2,
  completed_count: 0,
  failed_count: 0,
  cancelled_count: 0,
};

export const mockJobStatusResponse: JobStatusResponse = {
  hostname: 'cluster1.example.com',
  jobs: mockJobs.filter(j => j.hostname === 'cluster1.example.com'),
  total_jobs: mockJobs.filter(j => j.hostname === 'cluster1.example.com').length,
  query_time: '0.234s',
  array_groups: [],
};

export const mockPartitionStatusResponse: PartitionStatusResponse[] = [
  {
    hostname: 'cluster1.example.com',
    partitions: [
      {
        partition: 'gpu',
        availability: 'up',
        states: ['mix'],
        nodes_total: 4,
        cpus_alloc: 64,
        cpus_idle: 32,
        cpus_other: 0,
        cpus_total: 96,
        gpus_total: 16,
        gpus_used: 10,
        gpus_idle: 6,
        gpu_types: {
          V100: { total: 16, used: 10 }
        }
      },
      {
        partition: 'cpu',
        availability: 'up',
        states: ['idle'],
        nodes_total: 8,
        cpus_alloc: 0,
        cpus_idle: 128,
        cpus_other: 0,
        cpus_total: 128,
        gpus_total: 0,
        gpus_used: 0,
        gpus_idle: 0
      }
    ],
    query_time: '0.145s',
    cached: false,
    stale: false
  },
  {
    hostname: 'cluster2.example.com',
    partitions: [
      {
        partition: 'compute',
        availability: 'up',
        states: ['alloc'],
        nodes_total: 2,
        cpus_alloc: 32,
        cpus_idle: 0,
        cpus_other: 0,
        cpus_total: 32,
        gpus_total: null,
        gpus_used: null,
        gpus_idle: null
      }
    ],
    query_time: '0.167s',
    cached: true,
    cache_age_seconds: 12
  }
];

/**
 * Create a mock job with custom properties
 */
export function createMockJob(overrides: Partial<JobInfo> = {}): JobInfo {
  return buildJob({
    job_id: '99999',
    hostname: 'test.example.com',
    name: 'test-job',
    state: 'R',
    user: 'testuser',
    partition: 'cpu',
    cpus: '1',
    nodes: '1',
    memory: '1G',
    runtime: '00:00:00',
    time_limit: '01:00:00',
    submit_time: new Date().toISOString(),
    work_dir: '/home/testuser/test',
    stdout_file: '/home/testuser/test/output.log',
    stderr_file: '/home/testuser/test/error.log',
    ...overrides,
  });
}

/**
 * Create multiple mock jobs
 */
export function createMockJobs(count: number, overrides: Partial<JobInfo> = {}): JobInfo[] {
  return Array.from({ length: count }, (_, i) =>
    createMockJob({
      job_id: `${10000 + i}`,
      name: `test-job-${i}`,
      ...overrides,
    })
  );
}
