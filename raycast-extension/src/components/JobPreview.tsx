import { Icon, List } from "@raycast/api";
import { formatDate, stateColor, stateIcon, stateLabel } from "../lib/format";
import { gpuCount, jobSummary } from "../lib/jobs";
import { escapeMarkdown } from "../lib/markdown";
import type { JobInfo } from "../types/ssync";

export function JobPreview({ job }: { job: JobInfo }) {
  const gpu = gpuCount(job);
  return (
    <List.Item.Detail
      markdown={
        "# " +
        escapeMarkdown(job.name || "Job " + job.job_id) +
        "\n\n" +
        escapeMarkdown(jobSummary(job))
      }
      metadata={
        <List.Item.Detail.Metadata>
          <List.Item.Detail.Metadata.Label
            title="State"
            text={stateLabel(job.state)}
            icon={{
              source: stateIcon(job.state),
              tintColor: stateColor(job.state),
            }}
          />
          <List.Item.Detail.Metadata.Label
            title="Host"
            text={job.hostname}
            icon={Icon.Desktop}
          />
          <List.Item.Detail.Metadata.Label title="Job" text={job.job_id} />
          {job.user ? (
            <List.Item.Detail.Metadata.Label title="User" text={job.user} />
          ) : null}
          {job.partition ? (
            <List.Item.Detail.Metadata.Label
              title="Partition"
              text={job.partition}
            />
          ) : null}
          <List.Item.Detail.Metadata.Separator />
          {job.cpus ? (
            <List.Item.Detail.Metadata.Label title="CPUs" text={job.cpus} />
          ) : null}
          {gpu !== undefined ? (
            <List.Item.Detail.Metadata.Label title="GPUs" text={String(gpu)} />
          ) : null}
          {job.memory ? (
            <List.Item.Detail.Metadata.Label title="Memory" text={job.memory} />
          ) : null}
          {job.nodes ? (
            <List.Item.Detail.Metadata.Label title="Nodes" text={job.nodes} />
          ) : null}
          {job.time_limit ? (
            <List.Item.Detail.Metadata.Label
              title="Time Limit"
              text={job.time_limit}
            />
          ) : null}
          {job.submit_time ? (
            <List.Item.Detail.Metadata.Label
              title="Submitted"
              text={formatDate(job.submit_time)}
            />
          ) : null}
          {job.end_time ? (
            <List.Item.Detail.Metadata.Label
              title="Finished"
              text={formatDate(job.end_time)}
            />
          ) : null}
          {job.array_job_id ? (
            <List.Item.Detail.Metadata.Label
              title="Array"
              text={
                job.array_job_id +
                (job.array_task_id ? " · task " + job.array_task_id : "")
              }
            />
          ) : null}
          {job.exit_code ? (
            <List.Item.Detail.Metadata.Label
              title="Exit Code"
              text={job.exit_code}
            />
          ) : null}
        </List.Item.Detail.Metadata>
      }
    />
  );
}
