import { Action, ActionPanel, Alert, Detail, Icon, Keyboard, Toast, confirmAlert, open, showToast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { SsyncClient } from "../api/client";
import { jobDetailMarkdown } from "../lib/markdown";
import { compactJobSubtitle, formatDate, isPending, isRunning, metadataText, stateColor, stateIcon, stateLabel, webJobUrl } from "../lib/format";
import type { ConnectionSettings, JobInfo } from "../types/ssync";
import { OutputView } from "./OutputView";
import { ScriptView } from "./ScriptView";
import { WatchersView } from "./WatchersView";

type Props = {
  connection: ConnectionSettings;
  job: JobInfo;
  onJobUpdated?: (job: JobInfo) => void;
};

export function JobDetail({ connection, job, onJobUpdated }: Props) {
  const client = useMemo(() => new SsyncClient(connection), [connection]);
  const [currentJob, setCurrentJob] = useState(job);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    setCurrentJob(job);
  }, [job]);

  async function refreshJob(forceRefresh = false) {
    setIsLoading(true);
    try {
      const next = await client.getJob(currentJob, forceRefresh);
      setCurrentJob(next);
      onJobUpdated?.(next);
      await showToast({ style: Toast.Style.Success, title: "Job refreshed" });
    } catch (error) {
      await showToast({
        style: Toast.Style.Failure,
        title: "Failed to refresh job",
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setIsLoading(false);
    }
  }

  async function cancelJob() {
    const confirmed = await confirmAlert({
      title: `Cancel job ${currentJob.job_id}?`,
      message: `${currentJob.name || "This job"} on ${currentJob.hostname} will be cancelled with scancel.`,
      primaryAction: {
        title: "Cancel Job",
        style: Alert.ActionStyle.Destructive,
      },
    });
    if (!confirmed) return;

    const toast = await showToast({ style: Toast.Style.Animated, title: "Cancelling job" });
    try {
      await client.cancelJob(currentJob);
      toast.style = Toast.Style.Success;
      toast.title = "Job cancelled";
      await refreshJob();
    } catch (error) {
      toast.style = Toast.Style.Failure;
      toast.title = "Failed to cancel job";
      toast.message = error instanceof Error ? error.message : String(error);
    }
  }

  const canCancel = isRunning(currentJob) || isPending(currentJob);

  return (
    <Detail
      isLoading={isLoading}
      navigationTitle={`${currentJob.job_id} @ ${currentJob.hostname}`}
      markdown={jobDetailMarkdown(currentJob)}
      metadata={
        <Detail.Metadata>
          <Detail.Metadata.Label title="State" text={stateLabel(currentJob.state)} icon={{ source: stateIcon(currentJob.state), tintColor: stateColor(currentJob.state) }} />
          <Detail.Metadata.Label title="Host" text={currentJob.hostname} />
          <Detail.Metadata.Label title="Job ID" text={currentJob.job_id} />
          <Detail.Metadata.Label title="User" text={metadataText(currentJob.user)} />
          <Detail.Metadata.Separator />
          <Detail.Metadata.Label title="Summary" text={compactJobSubtitle(currentJob)} />
          <Detail.Metadata.Label title="Partition" text={metadataText(currentJob.partition)} />
          <Detail.Metadata.Label title="Account" text={metadataText(currentJob.account)} />
          <Detail.Metadata.Label title="QoS" text={metadataText(currentJob.qos)} />
          <Detail.Metadata.Separator />
          <Detail.Metadata.Label title="Submitted" text={formatDate(currentJob.submit_time)} />
          <Detail.Metadata.Label title="Started" text={formatDate(currentJob.start_time)} />
          <Detail.Metadata.Label title="Ended" text={formatDate(currentJob.end_time)} />
          <Detail.Metadata.Label title="Runtime" text={metadataText(currentJob.runtime)} />
          <Detail.Metadata.Label title="Time Limit" text={metadataText(currentJob.time_limit)} />
          <Detail.Metadata.Separator />
          <Detail.Metadata.Label title="Nodes" text={metadataText(currentJob.nodes)} />
          <Detail.Metadata.Label title="CPUs" text={metadataText(currentJob.cpus)} />
          <Detail.Metadata.Label title="Memory" text={metadataText(currentJob.memory)} />
        </Detail.Metadata>
      }
      actions={
        <ActionPanel>
          <ActionPanel.Section>
            <Action.Push title="View Output" icon={Icon.Terminal} target={<OutputView connection={connection} job={currentJob} />} />
            <Action.Push title="View Script" icon={Icon.Code} target={<ScriptView connection={connection} job={currentJob} />} />
            <Action.Push title="View Watchers & Events" icon={Icon.Eye} target={<WatchersView connection={connection} job={currentJob} />} />
          </ActionPanel.Section>
          <ActionPanel.Section>
            <Action title="Refresh Job" icon={Icon.ArrowClockwise} shortcut={Keyboard.Shortcut.Common.Refresh} onAction={() => refreshJob()} />
            {canCancel ? <Action title="Cancel Job" icon={Icon.Stop} style={Action.Style.Destructive} onAction={cancelJob} /> : null}
            <Action title="Open in ssync Web" icon={Icon.Globe} onAction={() => open(webJobUrl(connection.apiUrl, currentJob))} />
          </ActionPanel.Section>
          <ActionPanel.Section>
            <Action.CopyToClipboard title="Copy Job ID" content={currentJob.job_id} />
            {currentJob.work_dir ? <Action.CopyToClipboard title="Copy Work Dir" content={currentJob.work_dir} /> : null}
            {currentJob.stdout_file ? <Action.CopyToClipboard title="Copy stdout Path" content={currentJob.stdout_file} /> : null}
            {currentJob.stderr_file ? <Action.CopyToClipboard title="Copy stderr Path" content={currentJob.stderr_file} /> : null}
          </ActionPanel.Section>
        </ActionPanel>
      }
    />
  );
}
