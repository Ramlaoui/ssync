import { Action, ActionPanel, Icon, Keyboard } from "@raycast/api";
import { useRef, type ReactNode } from "react";
import { cancelJob } from "../lib/actions";
import { canCancelJob, webJobUrl } from "../lib/format";
import {
  OUTPUT_SHORTCUT,
  SCRIPT_SHORTCUT,
  WATCHERS_SHORTCUT,
  PIN_SHORTCUT,
  RELAUNCH_SHORTCUT,
} from "../lib/shortcuts";
import type { ConnectionSettings, JobInfo } from "../types/ssync";
import { HostSettingsForm } from "./HostsView";
import { JobDetail } from "./JobDetail";
import { LaunchView } from "./LaunchView";
import { OutputView } from "./OutputView";
import { ScriptView } from "./ScriptView";
import { WatchersView } from "./WatchersView";

export function JobActions({
  connection,
  job,
  onRefresh,
  pinned,
  onPin,
  children,
}: {
  connection: ConnectionSettings;
  job: JobInfo;
  onRefresh: () => Promise<boolean>;
  pinned: boolean;
  onPin: () => void;
  children?: ReactNode;
}) {
  const cancelling = useRef(false);
  async function cancel() {
    if (cancelling.current) return;
    cancelling.current = true;
    try {
      if (await cancelJob(connection, job)) await onRefresh();
    } finally {
      cancelling.current = false;
    }
  }
  return (
    <ActionPanel>
      <ActionPanel.Section>
        <Action.Push
          title="Open Job Detail"
          icon={Icon.Sidebar}
          target={<JobDetail connection={connection} job={job} />}
        />
        <Action.Push
          title="View Output"
          icon={Icon.Terminal}
          shortcut={OUTPUT_SHORTCUT}
          target={<OutputView connection={connection} job={job} />}
        />
        <Action.Push
          title="View Script"
          icon={Icon.Code}
          shortcut={SCRIPT_SHORTCUT}
          target={<ScriptView connection={connection} job={job} />}
        />
        <Action.Push
          title="View Watchers"
          icon={Icon.Eye}
          shortcut={WATCHERS_SHORTCUT}
          target={<WatchersView connection={connection} job={job} />}
        />
        <Action
          title={pinned ? "Unpin Job" : "Pin Job"}
          icon={pinned ? Icon.StarDisabled : Icon.Star}
          shortcut={PIN_SHORTCUT}
          onAction={onPin}
        />
      </ActionPanel.Section>
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
        <Action.OpenInBrowser
          title="Open in ssync Web"
          url={webJobUrl(connection.apiUrl, job)}
          shortcut={Keyboard.Shortcut.Common.OpenWith}
        />
        {canCancelJob(job) ? (
          <Action
            title="Cancel Job"
            icon={Icon.Stop}
            style={Action.Style.Destructive}
            onAction={cancel}
          />
        ) : null}
      </ActionPanel.Section>
      <ActionPanel.Section>
        <Action.CopyToClipboard title="Copy Job ID" content={job.job_id} />
        <Action.CopyToClipboard
          title="Copy Job Link"
          content={webJobUrl(connection.apiUrl, job)}
        />
        {job.work_dir ? (
          <Action.CopyToClipboard
            title="Copy Work Directory"
            content={job.work_dir}
          />
        ) : null}
      </ActionPanel.Section>
      <ActionPanel.Section>
        <Action
          title="Refresh Jobs"
          icon={Icon.ArrowClockwise}
          shortcut={Keyboard.Shortcut.Common.Refresh}
          onAction={() => void onRefresh()}
        />
      </ActionPanel.Section>
      {children}
    </ActionPanel>
  );
}
