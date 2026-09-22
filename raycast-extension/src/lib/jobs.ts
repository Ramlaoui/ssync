import type { JobInfo, JobView, WorkspaceSettings } from "../types/ssync";

export type StateCategory = "running" | "pending" | "historical";
const states: Record<
  string,
  {
    label: string;
    category: StateCategory;
    tone: "running" | "warning" | "success" | "danger" | "muted";
    attention?: boolean;
  }
> = {
  R: { label: "Running", category: "running", tone: "running" },
  CG: { label: "Completing", category: "running", tone: "running" },
  S: { label: "Suspended", category: "running", tone: "warning" },
  PD: { label: "Pending", category: "pending", tone: "warning" },
  CF: { label: "Configuring", category: "pending", tone: "warning" },
  CD: { label: "Completed", category: "historical", tone: "success" },
  F: {
    label: "Failed",
    category: "historical",
    tone: "danger",
    attention: true,
  },
  OOM: {
    label: "Out of memory",
    category: "historical",
    tone: "danger",
    attention: true,
  },
  NF: {
    label: "Node failed",
    category: "historical",
    tone: "danger",
    attention: true,
  },
  BF: {
    label: "Boot failed",
    category: "historical",
    tone: "danger",
    attention: true,
  },
  TO: {
    label: "Timed out",
    category: "historical",
    tone: "warning",
    attention: true,
  },
  DL: {
    label: "Deadline",
    category: "historical",
    tone: "warning",
    attention: true,
  },
  PR: {
    label: "Preempted",
    category: "historical",
    tone: "warning",
    attention: true,
  },
  CA: { label: "Cancelled", category: "historical", tone: "muted" },
};
const names: Record<string, string> = {
  RUNNING: "R",
  COMPLETING: "CG",
  SUSPENDED: "S",
  PENDING: "PD",
  CONFIGURING: "CF",
  COMPLETED: "CD",
  FAILED: "F",
  OUT_OF_MEMORY: "OOM",
  NODE_FAIL: "NF",
  BOOT_FAIL: "BF",
  TIMEOUT: "TO",
  DEADLINE: "DL",
  PREEMPTED: "PR",
  CANCELLED: "CA",
};
export function jobStatus(value: string) {
  const raw = value.toUpperCase().split(/[+\s]/)[0];
  return (
    states[names[raw] || raw] || {
      label: value || "Unknown",
      category: "historical" as const,
      tone: "muted" as const,
      attention: false,
    }
  );
}
export const jobKey = (job: Pick<JobInfo, "hostname" | "job_id">) =>
  JSON.stringify([job.hostname, job.job_id]);
export function matchesView(job: JobInfo, view: JobView, pins: string[] = []) {
  const status = jobStatus(job.state);
  return (
    view === "all" ||
    (view === "pinned"
      ? pins.includes(jobKey(job))
      : view === "attention"
        ? Boolean(status.attention)
        : status.category === view)
  );
}
export function visibleJobs(
  jobs: JobInfo[],
  settings: WorkspaceSettings,
): JobInfo[] {
  return jobs.filter(
    (job) =>
      (!settings.host || settings.host === job.hostname) &&
      matchesView(job, settings.view, settings.pinnedJobs),
  );
}
export function togglePinned(pins: string[], job: JobInfo): string[] {
  const key = jobKey(job);
  return pins.includes(key)
    ? pins.filter((item) => item !== key)
    : [...pins, key];
}
export function gpuCount(job: JobInfo): number | undefined {
  for (const raw of [
    job.alloc_tres,
    job.req_tres,
    job.gres,
    job.tres_per_node,
  ]) {
    if (!raw) continue;
    const total = raw.match(/(?:^|,)gres\/gpu=(\d+)/);
    if (total) return Number(total[1]);
    const typed = [...raw.matchAll(/(?:gres\/)?gpu(?::[^:=,()]+)?[=:](\d+)/g)];
    if (typed.length)
      return typed.reduce((sum, value) => sum + Number(value[1]), 0);
  }
}
export function jobSummary(job: JobInfo): string {
  const status = jobStatus(job.state);
  if (status.category === "pending" && job.reason) return job.reason;
  if (status.attention && job.exit_code) return "Exit " + job.exit_code;
  if (job.runtime)
    return job.runtime + (job.time_limit ? " / " + job.time_limit : "");
  return job.partition || status.label;
}
