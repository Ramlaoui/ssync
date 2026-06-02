import type { JobInfo } from "../types/ssync";
import { formatDate, stateLabel } from "./format";

export function escapeMarkdown(value: string): string {
  return value.replace(/[\\`*_{}[\]()#+\-.!|]/g, "\\$&");
}

export function codeBlock(content?: string | null, language = ""): string {
  const body = content && content.length > 0 ? content : "No content available.";
  return `~~~${language}\n${body.replace(/\n?$/, "\n")}~~~`;
}

export function fieldLine(label: string, value?: string | number | null): string | null {
  if (value === undefined || value === null || value === "") return null;
  return `**${escapeMarkdown(label)}:** ${escapeMarkdown(String(value))}`;
}

export function bulletList(rows: [string, string | number | null | undefined][]): string {
  const lines = rows
    .map(([label, value]) => fieldLine(label, value))
    .filter((line): line is string => Boolean(line))
    .map((line) => `- ${line}`);
  return lines.length > 0 ? lines.join("\n") : "_No values available._";
}

export function jobDetailMarkdown(job: JobInfo): string {
  const statusLines = bulletList([
    ["State", stateLabel(job.state)],
    ["Reason", job.reason],
    ["Exit code", job.exit_code],
  ]);
  const timingLines = bulletList([
    ["Submitted", formatDate(job.submit_time)],
    ["Started", formatDate(job.start_time)],
    ["Ended", formatDate(job.end_time)],
    ["Runtime", job.runtime],
    ["Time limit", job.time_limit],
  ]);
  const pathRows: [string, string | null | undefined][] = [
    ["Work directory", job.work_dir],
    ["stdout", job.stdout_file],
    ["stderr", job.stderr_file],
  ];
  const pathBlocks = pathRows
    .map(([label, value]) => (value ? `**${escapeMarkdown(label)}**\n\n${codeBlock(value, "text")}` : null))
    .filter((value): value is string => Boolean(value));

  return [
    `# ${escapeMarkdown(job.name || `Job ${job.job_id}`)}`,
    "",
    "## Status",
    "",
    statusLines,
    "",
    "## Timing",
    "",
    timingLines,
    ...(pathBlocks.length > 0 ? ["", "## Paths", "", ...pathBlocks.flatMap((block) => [block, ""]).slice(0, -1)] : []),
  ].join("\n");
}
