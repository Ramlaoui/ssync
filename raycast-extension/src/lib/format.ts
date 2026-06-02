import { Color, Icon } from "@raycast/api";
import type { JobInfo, JobState } from "../types/ssync";

export function stateLabel(state: JobState): string {
  switch (state) {
    case "PD":
      return "Pending";
    case "R":
      return "Running";
    case "CD":
      return "Completed";
    case "F":
      return "Failed";
    case "CA":
      return "Cancelled";
    case "TO":
      return "Timed out";
    case "UNKNOWN":
      return "Unknown";
    default:
      return String(state);
  }
}

export function stateIcon(state: JobState): Icon {
  switch (state) {
    case "R":
      return Icon.Play;
    case "PD":
      return Icon.Clock;
    case "CD":
      return Icon.CheckCircle;
    case "F":
      return Icon.XmarkCircle;
    case "CA":
      return Icon.Stop;
    case "TO":
      return Icon.Hourglass;
    default:
      return Icon.QuestionMark;
  }
}

export function stateColor(state: JobState): Color {
  switch (state) {
    case "R":
      return Color.Green;
    case "PD":
      return Color.Yellow;
    case "CD":
      return Color.Blue;
    case "F":
    case "TO":
      return Color.Red;
    case "CA":
      return Color.Orange;
    default:
      return Color.SecondaryText;
  }
}

export function isRunning(job: JobInfo): boolean {
  return job.state === "R";
}

export function isPending(job: JobInfo): boolean {
  return job.state === "PD";
}

export function isHistorical(job: JobInfo): boolean {
  return !isRunning(job) && !isPending(job);
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
    return right.job_id.localeCompare(left.job_id);
  });
}

export function flattenJobs(responses: { hostname: string; jobs: JobInfo[] }[]): JobInfo[] {
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

export function webJobUrl(apiUrl: string, job: JobInfo): string {
  const base = apiUrl.replace(/\/+$/, "");
  return `${base}/#/jobs/${encodeURIComponent(job.job_id)}/${encodeURIComponent(job.hostname)}`;
}

export function stateCountLabel(jobs: JobInfo[]): string {
  const running = jobs.filter(isRunning).length;
  const pending = jobs.filter(isPending).length;
  const failed = jobs.filter((job) => job.state === "F" || job.state === "TO").length;
  const parts = [];
  if (running) parts.push(`${running}R`);
  if (pending) parts.push(`${pending}PD`);
  if (failed) parts.push(`${failed}F`);
  return parts.join(" ");
}
