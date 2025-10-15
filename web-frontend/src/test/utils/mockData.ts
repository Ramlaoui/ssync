/**
 * Mock data for tests
 */

import type { JobInfo, HostInfo, JobStatusResponse, ArrayJobGroup } from '../../types/api';

export const mockHosts: HostInfo[] = [
  { hostname: 'cluster1.example.com', status: 'connected' },
  { hostname: 'cluster2.example.com', status: 'connected' },
];

export const mockJobs: JobInfo[] = [
  {
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
    stdout_path: '/home/testuser/jobs/test-job-1/output.log',
    stderr_path: '/home/testuser/jobs/test-job-1/error.log',
  },
  {
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
    stdout_path: '/home/testuser/jobs/test-job-2/output.log',
    stderr_path: '/home/testuser/jobs/test-job-2/error.log',
  },
  {
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
    stdout_path: '/home/testuser/jobs/test-job-3/output.log',
    stderr_path: '/home/testuser/jobs/test-job-3/error.log',
    exit_code: '0',
  },
  {
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
    stdout_path: '/home/testuser/jobs/test-job-4/output.log',
    stderr_path: '/home/testuser/jobs/test-job-4/error.log',
    exit_code: '1',
  },
];

export const mockArrayJobs: JobInfo[] = [
  {
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
    stdout_path: '/home/testuser/jobs/array-job/output_1.log',
    stderr_path: '/home/testuser/jobs/array-job/error_1.log',
  },
  {
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
    stdout_path: '/home/testuser/jobs/array-job/output_2.log',
    stderr_path: '/home/testuser/jobs/array-job/error_2.log',
  },
];

export const mockArrayGroup: ArrayJobGroup = {
  array_job_id: '12349',
  hostname: 'cluster1.example.com',
  name: 'array-job',
  task_count: 2,
  states: { R: 2 },
  user: 'testuser',
  partition: 'cpu',
  submit_time: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
};

export const mockJobStatusResponse: JobStatusResponse = {
  hostname: 'cluster1.example.com',
  jobs: mockJobs.filter(j => j.hostname === 'cluster1.example.com'),
  timestamp: new Date().toISOString(),
  query_time: '0.234s',
  array_groups: [],
};

/**
 * Create a mock job with custom properties
 */
export function createMockJob(overrides: Partial<JobInfo> = {}): JobInfo {
  return {
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
    stdout_path: '/home/testuser/test/output.log',
    stderr_path: '/home/testuser/test/error.log',
    ...overrides,
  };
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
