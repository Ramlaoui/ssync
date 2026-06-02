import type { JobInfo } from "../types/ssync";
import { formatDate, stateLabel } from "./format";

export function escapeMarkdown(value: string): string {
  return value.replace(/[\\`*_{}[\]()#+\-.!|]/g, "\\$&");
}

export function codeBlock(content?: string | null, language = ""): string {
  const body = content && content.length > 0 ? content : "No content available.";
  return `~~~${language}\n${body.replace(/\n?$/, "\n")}~~~`;
}

export function kvTable(rows: [string, string | number | null | undefined][]): string {
  const filtered = rows.map(([key, value]) => [key, value === undefined || value === null || value === "" ? "n/a" : String(value)]);
  return [
    "| Field | Value |",
    "| --- | --- |",
    ...filtered.map(([key, value]) => `| ${escapeMarkdown(key)} | ${escapeMarkdown(value)} |`),
  ].join("\n");
}

export function jobDetailMarkdown(job: JobInfo): string {
  return [
    `# ${escapeMarkdown(job.name || `Job ${job.job_id}`)}`,
    "",
    kvTable([
      ["State", stateLabel(job.state)],
      ["Host", job.hostname],
      ["Job ID", job.job_id],
      ["User", job.user],
      ["Partition", job.partition],
      ["Runtime", job.runtime],
      ["Time limit", job.time_limit],
      ["Reason", job.reason],
      ["Exit code", job.exit_code],
      ["Nodes", job.nodes],
      ["CPUs", job.cpus],
      ["Memory", job.memory],
      ["Account", job.account],
      ["QoS", job.qos],
      ["Submit time", formatDate(job.submit_time)],
      ["Start time", formatDate(job.start_time)],
      ["End time", formatDate(job.end_time)],
      ["Work dir", job.work_dir],
      ["stdout", job.stdout_file],
      ["stderr", job.stderr_file],
    ]),
  ].join("\n");
}
