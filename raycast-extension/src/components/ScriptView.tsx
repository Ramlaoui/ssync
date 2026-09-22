import { Action, ActionPanel, Detail, Icon, Keyboard } from "@raycast/api";
import { SsyncClient } from "../api/client";
import { useResource } from "../hooks/useResource";
import { connectionScope } from "../lib/connections";
import { jobKey } from "../lib/jobs";
import { codeBlock, escapeMarkdown } from "../lib/markdown";
import { RELAUNCH_SHORTCUT } from "../lib/shortcuts";
import type { ConnectionSettings, JobInfo } from "../types/ssync";
import { LaunchView } from "./LaunchView";

export function ScriptView({
  connection,
  job,
}: {
  connection: ConnectionSettings;
  job: JobInfo;
}) {
  const resource = useResource(
    connectionScope(connection) + jobKey(job),
    (signal) => new SsyncClient(connection, signal).getScript(job),
  );
  const script = resource.data;
  return (
    <Detail
      isLoading={resource.isLoading}
      navigationTitle={"Script · " + job.job_id + " · " + job.hostname}
      markdown={
        (resource.error
          ? "**Refresh failed:** " + escapeMarkdown(resource.error) + "\n\n"
          : "") + codeBlock(script?.script_content, "bash")
      }
      metadata={
        <Detail.Metadata>
          <Detail.Metadata.Label
            title="Job"
            text={job.name || job.job_id}
            icon={Icon.Code}
          />
          <Detail.Metadata.Label title="Host" text={job.hostname} />
          {script?.local_source_dir ? (
            <Detail.Metadata.Label
              title="Source Directory"
              text={script.local_source_dir}
            />
          ) : null}
        </Detail.Metadata>
      }
      actions={
        <ActionPanel>
          {script?.script_content ? (
            <Action.CopyToClipboard
              title="Copy Script"
              content={script.script_content}
            />
          ) : null}
          <Action.Push
            title="Relaunch Job"
            icon={Icon.Rocket}
            shortcut={RELAUNCH_SHORTCUT}
            target={<LaunchView connection={connection} job={job} />}
          />
          <Action
            title="Refresh Script"
            icon={Icon.ArrowClockwise}
            shortcut={Keyboard.Shortcut.Common.Refresh}
            onAction={() => void resource.refresh()}
          />
          {script?.local_source_dir ? (
            <Action.CopyToClipboard
              title="Copy Source Directory"
              content={script.local_source_dir}
            />
          ) : null}
        </ActionPanel>
      }
    />
  );
}
