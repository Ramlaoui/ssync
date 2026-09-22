import {
  Action,
  ActionPanel,
  Icon,
  Keyboard,
  List,
  Toast,
  open,
  showToast,
} from "@raycast/api";
import type { ReactNode } from "react";
import { useEffect, useRef } from "react";
import { SsyncClient } from "../api/client";
import { useResource } from "../hooks/useResource";
import { connectionScope } from "../lib/connections";
import { gpuCount, jobKey } from "../lib/jobs";
import { cancelJob as confirmCancelJob } from "../lib/actions";
import { LaunchView } from "./LaunchView";
import { HostSettingsForm } from "./HostsView";
import {
  canCancelJob,
  compactJobSubtitle,
  formatDate,
  metadataText,
  stateColor,
  stateIcon,
  stateLabel,
  webJobUrl,
} from "../lib/format";
import { bulletList, codeBlock, escapeMarkdown } from "../lib/markdown";
import { openJobOutputFile } from "../lib/output-file";
import {
  WATCHERS_SHORTCUT,
  OUTPUT_SHORTCUT,
  SCRIPT_SHORTCUT,
  RELAUNCH_SHORTCUT,
} from "../lib/shortcuts";
import type { ConnectionSettings, JobInfo } from "../types/ssync";
import { OutputView } from "./OutputView";
import { ScriptView } from "./ScriptView";
import { WatchersView } from "./WatchersView";

type Props = {
  connection: ConnectionSettings;
  job: JobInfo;
  onJobUpdated?: (job: JobInfo) => void;
};

type InspectorItemProps = {
  id: string;
  title: string;
  subtitle?: string | null;
  icon?: List.Item.Props["icon"];
  accessories?: List.Item.Props["accessories"];
  keywords?: string[];
  markdown: string;
  metadata?: ReactNode;
  actions: ReactNode;
};

type JobInspectorActionsProps = {
  connection: ConnectionSettings;
  job: JobInfo;
  canCancel: boolean;
  refreshJob: () => Promise<void>;
  cancelJob: () => Promise<void>;
  primary?: ReactNode;
  includeRelatedViews?: boolean;
};

export function JobDetail({ connection, job, onJobUpdated }: Props) {
  const client = new SsyncClient(connection);
  const force = useRef(false);
  const resource = useResource(
    connectionScope(connection) + jobKey(job),
    async (signal) => {
      const result = await new SsyncClient(connection, signal).getJob(
        job,
        force.current,
      );
      if (!signal.aborted) force.current = false;
      return result;
    },
    job,
  );
  const currentJob =
    resource.data && jobKey(resource.data) === jobKey(job)
      ? resource.data
      : job;
  const isLoading = resource.isLoading;
  const cancelling = useRef(false);
  useEffect(() => {
    if (resource.data) onJobUpdated?.(resource.data);
  }, [resource.data, onJobUpdated]);
  async function refreshJob(forceRefresh = true) {
    force.current = forceRefresh;
    if (!(await resource.refresh()))
      await showToast({
        style: Toast.Style.Failure,
        title: "Could not refresh job",
      });
  }
  async function cancelJob() {
    if (cancelling.current) return;
    cancelling.current = true;
    try {
      if (await confirmCancelJob(connection, currentJob))
        await refreshJob(true);
    } finally {
      cancelling.current = false;
    }
  }
  const canCancel = canCancelJob(currentJob);
  const actions = {
    connection,
    job: currentJob,
    canCancel,
    refreshJob: () => refreshJob(),
    cancelJob,
  };

  return (
    <List
      isLoading={isLoading}
      isShowingDetail
      navigationTitle={`${currentJob.job_id} @ ${currentJob.hostname}`}
      searchBarPlaceholder="Search job fields"
    >
      {resource.error ? (
        <List.Item
          title="Could not refresh job"
          icon={Icon.Warning}
          detail={
            <List.Item.Detail markdown={escapeMarkdown(resource.error)} />
          }
          actions={<JobInspectorActions {...actions} />}
        />
      ) : null}
      <List.Section title="Overview">
        <InspectorItem
          id="status"
          title="Status"
          subtitle={statusSubtitle(currentJob)}
          icon={{
            source: stateIcon(currentJob.state),
            tintColor: stateColor(currentJob.state),
          }}
          accessories={[
            {
              tag: {
                value: stateLabel(currentJob.state),
                color: stateColor(currentJob.state),
              },
            },
          ]}
          keywords={keywords(
            currentJob.state,
            stateLabel(currentJob.state),
            currentJob.reason,
            currentJob.exit_code,
          )}
          markdown={statusMarkdown(currentJob)}
          metadata={<StatusMetadata job={currentJob} />}
          actions={
            <JobInspectorActions
              {...actions}
              primary={
                <Action.CopyToClipboard
                  title="Copy State"
                  content={stateLabel(currentJob.state)}
                />
              }
            />
          }
        />
        <InspectorItem
          id="identity"
          title="Identity"
          subtitle={currentJob.name || `Job ${currentJob.job_id}`}
          icon={Icon.Hashtag}
          keywords={keywords(
            currentJob.job_id,
            currentJob.name,
            currentJob.user,
          )}
          markdown={identityMarkdown(currentJob)}
          metadata={<IdentityMetadata job={currentJob} />}
          actions={
            <JobInspectorActions
              {...actions}
              primary={
                <Action.CopyToClipboard
                  title="Copy Job ID"
                  content={currentJob.job_id}
                />
              }
            />
          }
        />
      </List.Section>

      <List.Section title="Scheduling">
        <InspectorItem
          id="placement"
          title="Placement"
          subtitle={placementSubtitle(currentJob)}
          icon={Icon.Network}
          keywords={keywords(
            currentJob.hostname,
            currentJob.partition,
            currentJob.account,
            currentJob.qos,
          )}
          markdown={placementMarkdown(currentJob)}
          metadata={<PlacementMetadata job={currentJob} />}
          actions={
            <JobInspectorActions
              {...actions}
              primary={
                <Action.CopyToClipboard
                  title="Copy Host"
                  content={currentJob.hostname}
                />
              }
            />
          }
        />
        <InspectorItem
          id="resources"
          title="Resources"
          subtitle={resourcesSubtitle(currentJob)}
          icon={Icon.MemoryChip}
          keywords={keywords(
            currentJob.nodes,
            currentJob.cpus,
            currentJob.memory,
          )}
          markdown={resourcesMarkdown(currentJob)}
          metadata={<ResourcesMetadata job={currentJob} />}
          actions={<JobInspectorActions {...actions} />}
        />
      </List.Section>

      <List.Section title="Timing">
        <InspectorItem
          id="timing"
          title="Timing"
          subtitle={timingSubtitle(currentJob)}
          icon={Icon.Clock}
          keywords={keywords(
            currentJob.submit_time,
            currentJob.start_time,
            currentJob.end_time,
            currentJob.runtime,
            currentJob.time_limit,
          )}
          markdown={timingMarkdown(currentJob)}
          metadata={<TimingMetadata job={currentJob} />}
          actions={<JobInspectorActions {...actions} />}
        />
      </List.Section>

      <List.Section title="Paths">
        <InspectorItem
          id="work-dir"
          title="Work Directory"
          subtitle={currentJob.work_dir || "n/a"}
          icon={Icon.Folder}
          keywords={keywords(currentJob.work_dir)}
          markdown={pathMarkdown("Work Directory", currentJob.work_dir)}
          metadata={
            <PathMetadata
              title="Work Directory"
              value={currentJob.work_dir}
              job={currentJob}
            />
          }
          actions={
            <JobInspectorActions
              {...actions}
              primary={
                currentJob.work_dir ? (
                  <Action.CopyToClipboard
                    title="Copy Work Directory"
                    content={currentJob.work_dir}
                  />
                ) : undefined
              }
            />
          }
        />
        <InspectorItem
          id="stdout-path"
          title="stdout Path"
          subtitle={currentJob.stdout_file || "n/a"}
          icon={Icon.Terminal}
          keywords={keywords("stdout", currentJob.stdout_file)}
          markdown={pathMarkdown("stdout Path", currentJob.stdout_file)}
          metadata={
            <PathMetadata
              title="stdout Path"
              value={currentJob.stdout_file}
              job={currentJob}
            />
          }
          actions={
            <JobInspectorActions
              {...actions}
              primary={
                <>
                  <Action.Push
                    title="View stdout"
                    icon={Icon.Terminal}
                    target={
                      <OutputView
                        connection={connection}
                        job={currentJob}
                        initialOutputType="stdout"
                      />
                    }
                  />
                  {currentJob.stdout_file ? (
                    <Action
                      title="Open stdout in Editor"
                      icon={Icon.Pencil}
                      shortcut={Keyboard.Shortcut.Common.Open}
                      onAction={() =>
                        openJobOutputFile({
                          client,
                          job: currentJob,
                          outputType: "stdout",
                        })
                      }
                    />
                  ) : null}
                  {currentJob.stdout_file ? (
                    <Action.CopyToClipboard
                      title="Copy stdout Path"
                      content={currentJob.stdout_file}
                    />
                  ) : null}
                </>
              }
            />
          }
        />
        <InspectorItem
          id="stderr-path"
          title="stderr Path"
          subtitle={currentJob.stderr_file || "n/a"}
          icon={Icon.Terminal}
          keywords={keywords("stderr", currentJob.stderr_file)}
          markdown={pathMarkdown("stderr Path", currentJob.stderr_file)}
          metadata={
            <PathMetadata
              title="stderr Path"
              value={currentJob.stderr_file}
              job={currentJob}
            />
          }
          actions={
            <JobInspectorActions
              {...actions}
              primary={
                <>
                  <Action.Push
                    title="View stderr"
                    icon={Icon.Terminal}
                    target={
                      <OutputView
                        connection={connection}
                        job={currentJob}
                        initialOutputType="stderr"
                      />
                    }
                  />
                  {currentJob.stderr_file ? (
                    <Action
                      title="Open stderr in Editor"
                      icon={Icon.Pencil}
                      shortcut={Keyboard.Shortcut.Common.Open}
                      onAction={() =>
                        openJobOutputFile({
                          client,
                          job: currentJob,
                          outputType: "stderr",
                        })
                      }
                    />
                  ) : null}
                  {currentJob.stderr_file ? (
                    <Action.CopyToClipboard
                      title="Copy stderr Path"
                      content={currentJob.stderr_file}
                    />
                  ) : null}
                </>
              }
            />
          }
        />
      </List.Section>

      <List.Section title="Related Views">
        <InspectorItem
          id="output"
          title="Output"
          subtitle="stdout by default, stderr on demand"
          icon={Icon.Terminal}
          keywords={keywords("output", "stdout", "stderr")}
          markdown={relatedViewMarkdown(
            "Output",
            "Open stdout first. Stderr and full output remain explicit actions so the API is not spammed.",
          )}
          metadata={<RelatedViewMetadata job={currentJob} kind="Output" />}
          actions={
            <JobInspectorActions
              {...actions}
              includeRelatedViews={false}
              primary={
                <Action.Push
                  title="View Output"
                  icon={Icon.Terminal}
                  shortcut={OUTPUT_SHORTCUT}
                  target={
                    <OutputView connection={connection} job={currentJob} />
                  }
                />
              }
            />
          }
        />
        <InspectorItem
          id="script"
          title="Script"
          subtitle="submitted batch script"
          icon={Icon.Code}
          keywords={keywords("script", "batch")}
          markdown={relatedViewMarkdown(
            "Script",
            "Open the submitted batch script in a formatted read-only view.",
          )}
          metadata={<RelatedViewMetadata job={currentJob} kind="Script" />}
          actions={
            <JobInspectorActions
              {...actions}
              includeRelatedViews={false}
              primary={
                <Action.Push
                  title="View Script"
                  icon={Icon.Code}
                  shortcut={SCRIPT_SHORTCUT}
                  target={
                    <ScriptView connection={connection} job={currentJob} />
                  }
                />
              }
            />
          }
        />
        <InspectorItem
          id="watchers"
          title="Watchers & Events"
          subtitle="read-only watcher context"
          icon={Icon.Eye}
          keywords={keywords("watchers", "events")}
          markdown={relatedViewMarkdown(
            "Watchers & Events",
            "Open watcher rules and recorded watcher events associated with this job.",
          )}
          metadata={<RelatedViewMetadata job={currentJob} kind="Watchers" />}
          actions={
            <JobInspectorActions
              {...actions}
              includeRelatedViews={false}
              primary={
                <Action.Push
                  title="View Watchers & Events"
                  icon={Icon.Eye}
                  shortcut={WATCHERS_SHORTCUT}
                  target={
                    <WatchersView connection={connection} job={currentJob} />
                  }
                />
              }
            />
          }
        />
        <InspectorItem
          id="web"
          title="Open in ssync Web"
          subtitle={webJobUrl(connection.apiUrl, currentJob)}
          icon={Icon.Globe}
          keywords={keywords(
            "web",
            connection.apiUrl,
            currentJob.job_id,
            currentJob.hostname,
          )}
          markdown={relatedViewMarkdown(
            "ssync Web",
            "Open this job in the ssync web interface.",
          )}
          metadata={<RelatedViewMetadata job={currentJob} kind="Web" />}
          actions={
            <JobInspectorActions
              {...actions}
              includeRelatedViews={false}
              primary={
                <Action
                  title="Open in ssync Web"
                  icon={Icon.Globe}
                  onAction={() =>
                    open(webJobUrl(connection.apiUrl, currentJob))
                  }
                />
              }
            />
          }
        />
      </List.Section>
    </List>
  );
}

function InspectorItem({
  id,
  title,
  subtitle,
  icon,
  accessories,
  keywords,
  markdown,
  metadata,
  actions,
}: InspectorItemProps) {
  return (
    <List.Item
      id={id}
      title={title}
      subtitle={subtitle ? { value: subtitle, tooltip: subtitle } : undefined}
      icon={icon}
      accessories={accessories}
      keywords={keywords}
      detail={<List.Item.Detail markdown={markdown} metadata={metadata} />}
      actions={actions}
    />
  );
}

function JobInspectorActions({
  connection,
  job,
  canCancel,
  refreshJob,
  cancelJob,
  primary,
  includeRelatedViews = true,
}: JobInspectorActionsProps) {
  return (
    <ActionPanel>
      {primary ? <ActionPanel.Section>{primary}</ActionPanel.Section> : null}
      {includeRelatedViews ? (
        <ActionPanel.Section>
          <Action.Push
            title="View Output"
            icon={Icon.Terminal}
            target={<OutputView connection={connection} job={job} />}
          />
          <Action.Push
            title="View Script"
            icon={Icon.Code}
            target={<ScriptView connection={connection} job={job} />}
          />
          <Action.Push
            title="View Watchers & Events"
            icon={Icon.Eye}
            shortcut={WATCHERS_SHORTCUT}
            target={<WatchersView connection={connection} job={job} />}
          />
        </ActionPanel.Section>
      ) : null}
      <ActionPanel.Section>
        <Action.Push
          title="Relaunch Job"
          icon={Icon.Rocket}
          shortcut={RELAUNCH_SHORTCUT}
          target={<LaunchView connection={connection} job={job} />}
        />
        <Action.Push
          title="Edit Host Defaults"
          icon={Icon.Gear}
          target={
            <HostSettingsForm connection={connection} host={job.hostname} />
          }
        />
        <Action
          title="Refresh Job"
          icon={Icon.ArrowClockwise}
          shortcut={Keyboard.Shortcut.Common.Refresh}
          onAction={refreshJob}
        />
        {canCancel ? (
          <Action
            title="Cancel Job"
            icon={Icon.Stop}
            style={Action.Style.Destructive}
            onAction={cancelJob}
          />
        ) : null}
        <Action
          title="Open in ssync Web"
          icon={Icon.Globe}
          onAction={() => open(webJobUrl(connection.apiUrl, job))}
        />
      </ActionPanel.Section>
      <ActionPanel.Section>
        <Action.CopyToClipboard title="Copy Job ID" content={job.job_id} />
        {job.work_dir ? (
          <Action.CopyToClipboard
            title="Copy Work Directory"
            content={job.work_dir}
          />
        ) : null}
        {job.stdout_file ? (
          <Action.CopyToClipboard
            title="Copy stdout Path"
            content={job.stdout_file}
          />
        ) : null}
        {job.stderr_file ? (
          <Action.CopyToClipboard
            title="Copy stderr Path"
            content={job.stderr_file}
          />
        ) : null}
      </ActionPanel.Section>
    </ActionPanel>
  );
}

function StatusMetadata({ job }: { job: JobInfo }) {
  return (
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
        title="Raw State"
        text={metadataText(job.state)}
      />
      <List.Item.Detail.Metadata.Label
        title="Reason"
        text={metadataText(job.reason)}
      />
      <List.Item.Detail.Metadata.Label
        title="Exit Code"
        text={metadataText(job.exit_code)}
      />
    </List.Item.Detail.Metadata>
  );
}

function IdentityMetadata({ job }: { job: JobInfo }) {
  return (
    <List.Item.Detail.Metadata>
      <List.Item.Detail.Metadata.Label title="Job ID" text={job.job_id} />
      <List.Item.Detail.Metadata.Label
        title="Name"
        text={metadataText(job.name)}
      />
      <List.Item.Detail.Metadata.Label
        title="User"
        text={metadataText(job.user)}
      />
      <List.Item.Detail.Metadata.Label
        title="Summary"
        text={compactJobSubtitle(job)}
      />
    </List.Item.Detail.Metadata>
  );
}

function PlacementMetadata({ job }: { job: JobInfo }) {
  return (
    <List.Item.Detail.Metadata>
      <List.Item.Detail.Metadata.Label title="Host" text={job.hostname} />
      <List.Item.Detail.Metadata.Label
        title="Partition"
        text={metadataText(job.partition)}
      />
      <List.Item.Detail.Metadata.Label
        title="Account"
        text={metadataText(job.account)}
      />
      <List.Item.Detail.Metadata.Label
        title="QoS"
        text={metadataText(job.qos)}
      />
    </List.Item.Detail.Metadata>
  );
}

function ResourcesMetadata({ job }: { job: JobInfo }) {
  return (
    <List.Item.Detail.Metadata>
      <List.Item.Detail.Metadata.Label
        title="Nodes"
        text={metadataText(job.nodes)}
      />
      <List.Item.Detail.Metadata.Label
        title="CPUs"
        text={metadataText(job.cpus)}
      />
      {gpuCount(job) !== undefined ? (
        <List.Item.Detail.Metadata.Label
          title="GPUs"
          text={String(gpuCount(job))}
        />
      ) : null}
      <List.Item.Detail.Metadata.Label
        title="Memory"
        text={metadataText(job.memory)}
      />
    </List.Item.Detail.Metadata>
  );
}

function TimingMetadata({ job }: { job: JobInfo }) {
  return (
    <List.Item.Detail.Metadata>
      <List.Item.Detail.Metadata.Label
        title="Submitted"
        text={formatDate(job.submit_time)}
      />
      <List.Item.Detail.Metadata.Label
        title="Started"
        text={formatDate(job.start_time)}
      />
      <List.Item.Detail.Metadata.Label
        title="Ended"
        text={formatDate(job.end_time)}
      />
      <List.Item.Detail.Metadata.Label
        title="Runtime"
        text={metadataText(job.runtime)}
      />
      <List.Item.Detail.Metadata.Label
        title="Time Limit"
        text={metadataText(job.time_limit)}
      />
    </List.Item.Detail.Metadata>
  );
}

function PathMetadata({
  title,
  value,
  job,
}: {
  title: string;
  value?: string | null;
  job: JobInfo;
}) {
  return (
    <List.Item.Detail.Metadata>
      <List.Item.Detail.Metadata.Label title="Path Type" text={title} />
      <List.Item.Detail.Metadata.Label
        title="Path"
        text={metadataText(value)}
      />
      <List.Item.Detail.Metadata.Label
        title="Job"
        text={`${job.job_id} @ ${job.hostname}`}
      />
    </List.Item.Detail.Metadata>
  );
}

function RelatedViewMetadata({ job, kind }: { job: JobInfo; kind: string }) {
  return (
    <List.Item.Detail.Metadata>
      <List.Item.Detail.Metadata.Label title="View" text={kind} />
      <List.Item.Detail.Metadata.Label title="Job" text={job.job_id} />
      <List.Item.Detail.Metadata.Label title="Host" text={job.hostname} />
    </List.Item.Detail.Metadata>
  );
}

function statusMarkdown(job: JobInfo): string {
  return [
    `# ${escapeMarkdown(stateLabel(job.state))}`,
    "",
    bulletList([
      ["Raw state", job.state],
      ["Reason", job.reason],
      ["Exit code", job.exit_code],
    ]),
  ].join("\n");
}

function identityMarkdown(job: JobInfo): string {
  return [
    `# ${escapeMarkdown(job.name || `Job ${job.job_id}`)}`,
    "",
    bulletList([
      ["Job ID", job.job_id],
      ["User", job.user],
      ["Host", job.hostname],
    ]),
  ].join("\n");
}

function placementMarkdown(job: JobInfo): string {
  return [
    "# Placement",
    "",
    bulletList([
      ["Host", job.hostname],
      ["Partition", job.partition],
      ["Account", job.account],
      ["QoS", job.qos],
    ]),
  ].join("\n");
}

function resourcesMarkdown(job: JobInfo): string {
  return [
    "# Resources",
    "",
    bulletList([
      ["Nodes", job.nodes],
      ["CPUs", job.cpus],
      ["Memory", job.memory],
    ]),
  ].join("\n");
}

function timingMarkdown(job: JobInfo): string {
  return [
    "# Timing",
    "",
    bulletList([
      ["Submitted", formatDate(job.submit_time)],
      ["Started", formatDate(job.start_time)],
      ["Ended", formatDate(job.end_time)],
      ["Runtime", job.runtime],
      ["Time limit", job.time_limit],
    ]),
  ].join("\n");
}

function pathMarkdown(title: string, value?: string | null): string {
  return [`# ${escapeMarkdown(title)}`, "", codeBlock(value, "text")].join(
    "\n",
  );
}

function relatedViewMarkdown(title: string, description: string): string {
  return [`# ${escapeMarkdown(title)}`, "", escapeMarkdown(description)].join(
    "\n",
  );
}

function statusSubtitle(job: JobInfo): string {
  const parts = [stateLabel(job.state)];
  if (job.reason) parts.push(job.reason);
  if (job.exit_code) parts.push(`exit ${job.exit_code}`);
  return parts.join(" · ");
}

function placementSubtitle(job: JobInfo): string {
  return (
    [job.hostname, job.partition, job.account, job.qos]
      .filter(Boolean)
      .join(" · ") || "n/a"
  );
}

function resourcesSubtitle(job: JobInfo): string {
  return [
    `${metadataText(job.nodes)} nodes`,
    `${metadataText(job.cpus)} CPUs`,
    metadataText(job.memory),
  ].join(" · ");
}

function timingSubtitle(job: JobInfo): string {
  return (
    [job.runtime, job.time_limit ? `limit ${job.time_limit}` : undefined]
      .filter(Boolean)
      .join(" · ") || "n/a"
  );
}

function keywords(...values: (string | number | null | undefined)[]): string[] {
  return values
    .filter(
      (value): value is string | number =>
        value !== undefined && value !== null && value !== "",
    )
    .map((value) => String(value));
}
