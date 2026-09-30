export const STATES = {
  R: { label: 'Running', icon: 'play-circle', color: 'charts.green', order: 0 },
  PD: { label: 'Queued', icon: 'clock', color: 'charts.yellow', order: 1 },
  F: { label: 'Failed', icon: 'error', color: 'charts.red', order: 2 },
  TO: { label: 'Timed out', icon: 'watch', color: 'charts.orange', order: 3 },
  CD: { label: 'Completed', icon: 'check', color: 'charts.blue', order: 4 },
  CA: { label: 'Cancelled', icon: 'circle-slash', color: 'descriptionForeground', order: 5 },
  UNKNOWN: { label: 'Unknown', icon: 'question', color: 'descriptionForeground', order: 6 },
} as const;
export type JobState = keyof typeof STATES;
export interface JobInfo {
  job_id: string; name: string; state: JobState; hostname: string;
  partition?: string | null; runtime?: string | null; time_limit?: string | null;
  nodes?: string | null; cpus?: string | null; memory?: string | null;
  reason?: string | null; work_dir?: string | null; submit_time?: string | null;
  start_time?: string | null; end_time?: string | null; exit_code?: string | null;
  account?: string | null; array_job_id?: string | null; array_task_id?: string | null;
  stale?: boolean;
}
export interface JobStatusResult { hostname: string; jobs: JobInfo[] }
export function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
export function parseJob(value: unknown, host?: string): JobInfo {
  if (!record(value) || typeof value.job_id !== 'string' || !value.job_id || typeof value.name !== 'string') {
    throw new Error('Server returned an invalid job.');
  }
  const hostname = host ?? value.hostname;
  if (typeof hostname !== 'string' || !hostname) throw new Error('Job has no host.');
  for (const field of ['partition', 'runtime', 'time_limit', 'nodes', 'cpus', 'memory', 'reason', 'work_dir', 'submit_time', 'start_time', 'end_time', 'exit_code', 'account', 'array_job_id', 'array_task_id']) {
    if (value[field] != null && typeof value[field] !== 'string') throw new Error(`Job has an invalid ${field}.`);
  }
  const state = typeof value.state === 'string' && Object.hasOwn(STATES, value.state) ? value.state as JobState : 'UNKNOWN';
  return { ...value, hostname, state } as unknown as JobInfo;
}
export function jobKey(job: Pick<JobInfo, 'hostname' | 'job_id'>): string {
  return JSON.stringify([job.hostname, job.job_id]);
}
export function isActive(job: JobInfo): boolean { return job.state === 'R' || job.state === 'PD'; }
export function sortJobs(jobs: JobInfo[]): JobInfo[] {
  return jobs.sort((a, b) => STATES[a.state].order - STATES[b.state].order ||
    (b.submit_time ?? '').localeCompare(a.submit_time ?? '') || b.job_id.localeCompare(a.job_id, undefined, { numeric: true }));
}
export function errorMessage(error: unknown): string { return error instanceof Error ? error.message : String(error); }
