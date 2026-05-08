import type { JobInfo, JobState } from "../types/api";

export const TERMINAL_STATES = new Set(["CD", "F", "CA", "TO"]);
export const ACTIVE_STATES = new Set(["R", "PD"]);

export function hasValue(value: string | null | undefined): value is string {
  return Boolean(value && value !== "N/A" && value !== "Unknown" && value !== "None" && value !== "(null)");
}

export function stateLabel(state: JobState | null | undefined): string {
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
    default:
      return state || "Unknown";
  }
}

export function stateTone(state: JobState | null | undefined): "success" | "warning" | "danger" | "info" | "neutral" {
  switch (state) {
    case "R":
      return "success";
    case "PD":
      return "warning";
    case "CD":
      return "info";
    case "F":
    case "CA":
    case "TO":
      return "danger";
    default:
      return "neutral";
  }
}

export function isTerminalState(state: JobState | null | undefined): boolean {
  return Boolean(state && TERMINAL_STATES.has(String(state)));
}

export function formatDateTime(value: string | null | undefined): string {
  if (!hasValue(value)) return "N/A";
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;
  return new Date(timestamp).toLocaleString();
}

export function formatTimeAgo(value: string | null | undefined): string {
  if (!value) return "never";
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;
  const diff = Date.now() - timestamp;
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  if (diff < 604_800_000) return `${Math.floor(diff / 86_400_000)}d ago`;
  return new Date(timestamp).toLocaleDateString();
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || Number.isNaN(bytes)) return "N/A";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatMemory(memory: string | null | undefined): string {
  if (!hasValue(memory)) return "N/A";
  const match = memory.match(/^(\d+(?:\.\d+)?)([KMGTP]?)([nc]?)$/i);
  if (!match) return memory;
  const value = Number(match[1]);
  const unit = (match[2] || "M").toUpperCase();
  const suffix = match[3]?.toLowerCase();
  const scope = suffix === "n" ? " per node" : suffix === "c" ? " per CPU" : "";
  if (unit === "K") return `${(value / 1024).toFixed(1)} MB${scope}`;
  if (unit === "M") return `${value} MB${scope}`;
  if (unit === "G") return `${value} GB${scope}`;
  if (unit === "T") return `${value} TB${scope}`;
  if (unit === "P") return `${value} PB${scope}`;
  return memory;
}

export function compactJobTitle(job: JobInfo): string {
  return job.name && job.name !== job.job_id ? `${job.name} #${job.job_id}` : `Job #${job.job_id}`;
}

export function jobKey(jobId: string, hostname: string): string {
  return `${hostname}::${jobId}`;
}

export function truncateMiddle(value: string, limit = 56): string {
  if (value.length <= limit) return value;
  const left = Math.ceil((limit - 3) / 2);
  const right = Math.floor((limit - 3) / 2);
  return `${value.slice(0, left)}...${value.slice(value.length - right)}`;
}

export function linesCount(content: string | null | undefined): number {
  if (!content) return 0;
  return content.split("\n").length;
}
