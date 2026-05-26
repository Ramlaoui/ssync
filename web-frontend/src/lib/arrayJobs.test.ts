import { describe, expect, it } from 'vitest';
import { getArrayGroupTasks } from './arrayJobs';
import type { ArrayJobGroup, JobInfo } from '../types/api';

const task = {
  job_id: '123_0',
  name: 'array-task',
  state: 'R',
  hostname: 'cluster.test',
} as JobInfo;

const group = {
  array_job_id: '123',
  job_name: 'array-job',
  hostname: 'cluster.test',
  total_tasks: 1,
  tasks: [task],
  pending_count: 0,
  running_count: 1,
  completed_count: 0,
  failed_count: 0,
  cancelled_count: 0,
} satisfies ArrayJobGroup;

describe('getArrayGroupTasks', () => {
  it('returns valid tasks', () => {
    expect(getArrayGroupTasks(group)).toEqual([task]);
  });

  it('treats missing task lists as empty', () => {
    expect(
      getArrayGroupTasks({
        ...group,
        tasks: undefined,
      } as unknown as ArrayJobGroup),
    ).toEqual([]);
  });
});
