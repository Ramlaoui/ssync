import { Color, Icon } from "@raycast/api";
import { relay } from "./design";
import { jobStatus } from "./jobs";
import type { JobInfo, JobState } from "../types/ssync";

export function stateLabel(state: JobState): string {
  return jobStatus(state).label;
}
export function stateIcon(state: JobState): Icon {
  const status = jobStatus(state);
  if (status.category === "running") return Icon.Play;
  if (status.category === "pending") return Icon.Clock;
  if (status.tone === "success") return Icon.CheckCircle;
  if (status.tone === "danger") return Icon.XmarkCircle;
  if (status.tone === "warning") return Icon.Hourglass;
  return Icon.Stop;
}
export function stateColor(state: JobState): Color.ColorLike {
  return relay[jobStatus(state).tone];
}
export function isRunning(job: JobInfo): boolean {
  return jobStatus(job.state).category === "running";
}
export function isPending(job: JobInfo): boolean {
  return jobStatus(job.state).category === "pending";
}
export function isHistorical(job: JobInfo): boolean {
  return jobStatus(job.state).category === "historical";
}
export function canCancelJob(job: JobInfo): boolean {
  return !isHistorical(job);
}

export function jobSortTime(job: JobInfo): number {
  const raw = job.start_time || job.submit_time || job.end_time || "";
  const parsed = Date.parse(raw);
  return Number.isNaN(parsed) ? 0 : parsed;
}

export function sortJobs(jobs: JobInfo[]): JobInfo[] {
  return [...jobs].sort((left, right) => {
    const byTime = jobSortTime(right) - jobSortTime(left);
    if (byTime !== 0) return byTime;
    return right.job_id.localeCompare(left.job_id, undefined, {
      numeric: true,
    });
  });
}

export function flattenJobs(
  responses: { hostname: string; jobs: JobInfo[] }[],
): JobInfo[] {
  return responses.flatMap((response) =>
    (response.jobs || []).map((job) => ({
      ...job,
      hostname: job.hostname || response.hostname,
    })),
  );
}

export function jobTitle(job: JobInfo): string {
  return job.name || `Job ${job.job_id}`;
}

export function compactJobSubtitle(job: JobInfo): string {
  const parts = [job.hostname, `#${job.job_id}`];
  if (job.runtime) parts.push(job.runtime);
  if (job.partition) parts.push(job.partition);
  if (job.reason && job.state === "PD") parts.push(job.reason);
  return parts.filter(Boolean).join(" · ");
}

export function formatDate(value?: string | null): string {
  if (!value) return "n/a";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Date(parsed).toLocaleString();
}

export function formatRelativeAge(timestamp: number): string {
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function bytesLabel(value?: number | null): string {
  if (value === undefined || value === null) return "n/a";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}

export function metadataText(value?: string | number | boolean | null): string {
  if (value === undefined || value === null || value === "") return "n/a";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

export function webJobUrl(apiUrl: string, job: JobInfo): string {
  const base = apiUrl.replace(/\/+$/, "");
  return `${base}/#/jobs/${encodeURIComponent(job.job_id)}/${encodeURIComponent(job.hostname)}`;
}

export function stateCountLabel(jobs: JobInfo[]): string {
  const running = jobs.filter(isRunning).length;
  const pending = jobs.filter(isPending).length;
  const parts = [];
  if (running) parts.push(`${running}R`);
  if (pending) parts.push(`${pending}PD`);
  return parts.join(" ");
}
