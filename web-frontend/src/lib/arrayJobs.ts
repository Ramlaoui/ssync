import type { ArrayJobGroup, JobInfo } from '../types/api';

export function getArrayGroupTasks(group: ArrayJobGroup): JobInfo[] {
  if (!Array.isArray(group.tasks)) {
    return [];
  }

  return group.tasks.filter(
    (task): task is JobInfo =>
      Boolean(task && task.job_id && task.hostname),
  );
}
