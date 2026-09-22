import {
  Clipboard,
  Color,
  Icon,
  LaunchType,
  MenuBarExtra,
  Toast,
  getPreferenceValues,
  launchCommand,
  showToast,
} from "@raycast/api";
import { useRef, useState } from "react";
import {
  getConnection,
  getConnections,
  getWorkspace,
  setActiveConnection,
} from "./api/storage";
import { useJobs } from "./hooks/useJobs";
import { useResource } from "./hooks/useResource";
import { cancelJob } from "./lib/actions";
import { connectionScope } from "./lib/connections";
import { relay } from "./lib/design";
import {
  canCancelJob,
  flattenJobs,
  formatRelativeAge,
  isPending,
  isRunning,
  jobTitle,
  sortJobs,
  stateColor,
  stateIcon,
} from "./lib/format";
import { jobKey, jobStatus, jobSummary } from "./lib/jobs";
import type {
  ConnectionSettings,
  JobInfo,
  JobsLaunchContext,
} from "./types/ssync";

export default function Command() {
  const [revision, setRevision] = useState(0);
  const data = useResource("menu-connections:" + revision, async () => ({
    connection: await getConnection(),
    profiles: await getConnections(),
  }));
  if (!data.data?.connection)
    return (
      <MenuBarExtra
        icon={Icon.Plug}
        title="ssync"
        isLoading={data.isLoading}
        tooltip={data.error || "Connect to ssync"}
      >
        <MenuBarExtra.Item
          title={data.error ? "Connection unavailable" : "Add Connection"}
          icon={Icon.Plug}
          onAction={() => openCommand("connections")}
        />
        {data.error ? (
          <MenuBarExtra.Item
            title="Retry"
            icon={Icon.ArrowClockwise}
            onAction={() => setRevision((value) => value + 1)}
          />
        ) : null}
      </MenuBarExtra>
    );
  return (
    <Summary
      key={connectionScope(data.data.connection)}
      connection={data.data.connection}
      profiles={data.data.profiles.profiles}
      onSwitch={async (id) => {
        await setActiveConnection(id);
        setRevision((value) => value + 1);
      }}
    />
  );
}

function Summary({
  connection,
  profiles,
  onSwitch,
}: {
  connection: ConnectionSettings;
  profiles: Array<Omit<ConnectionSettings, "apiKey">>;
  onSwitch: (id: string) => Promise<void>;
}) {
  const resource = useJobs(connection);
  const workspace = useResource("menu-workspace:" + connection.id, () =>
    getWorkspace(connection),
  );
  const cancelling = useRef(false);
  const jobs = sortJobs(flattenJobs(resource.cache?.responses || []));
  const pins = jobs.filter((job) =>
    workspace.data?.pinnedJobs.includes(jobKey(job)),
  );
  const unpinned = jobs.filter(
    (job) => !pins.some((pin) => jobKey(pin) === jobKey(job)),
  );
  const running = unpinned.filter(isRunning),
    pending = unpinned.filter(isPending);
  const attention = unpinned.filter((job) => jobStatus(job.state).attention);
  const preferences = getPreferenceValues<{
    menuBarJobLimit?: string;
    menuBarAttention?: boolean;
  }>();
  const limit = Math.min(
    20,
    Math.max(3, Number(preferences.menuBarJobLimit) || 8),
  );
  const allRunning = jobs.filter(isRunning).length,
    allPending = jobs.filter(isPending).length;
  const title =
    allRunning || allPending ? allRunning + "R " + allPending + "P" : "ssync";
  async function refresh() {
    const selected = await getConnection();
    if (selected && connectionScope(selected) !== connectionScope(connection)) {
      await onSwitch(selected.id);
      return;
    }
    await workspace.refresh();
    const ok = await resource.refresh(true);
    await showToast({
      style: ok ? Toast.Style.Success : Toast.Style.Failure,
      title: ok ? "Jobs refreshed" : "Could not refresh jobs",
    });
  }
  async function cancel(job: JobInfo) {
    if (cancelling.current) return;
    cancelling.current = true;
    try {
      if (await cancelJob(connection, job)) await resource.refresh(true);
    } finally {
      cancelling.current = false;
    }
  }
  function section(label: string, list: JobInfo[]) {
    return list.length ? (
      <MenuBarExtra.Section title={label + " · " + list.length}>
        {list.slice(0, limit).map((job) => (
          <JobMenuItem
            key={jobKey(job)}
            connection={connection}
            job={job}
            onCancel={cancel}
          />
        ))}
        {list.length > limit ? (
          <MenuBarExtra.Item
            title={"Show All " + label + " Jobs"}
            icon={Icon.List}
            onAction={() =>
              openCommand("jobs", { connectionId: connection.id })
            }
          />
        ) : null}
      </MenuBarExtra.Section>
    ) : null;
  }
  return (
    <MenuBarExtra
      icon={{ source: "relay-mark.svg", tintColor: Color.PrimaryText }}
      title={title}
      isLoading={resource.isLoading || workspace.isLoading}
      tooltip={
        connection.name +
        " · " +
        allRunning +
        " running · " +
        allPending +
        " pending" +
        (resource.error ? " · Refresh failed" : "")
      }
    >
      <MenuBarExtra.Section
        title={
          connection.name +
          (resource.cache
            ? " · " + formatRelativeAge(resource.cache.loadedAt)
            : "")
        }
      >
        {resource.error ? (
          <MenuBarExtra.Item
            title="Refresh failed · showing saved jobs"
            subtitle={resource.error}
            icon={{ source: Icon.Warning, tintColor: relay.warning }}
            onAction={() => openCommand("connections")}
          />
        ) : null}
        {!jobs.length && !resource.isLoading ? (
          <MenuBarExtra.Item
            title="No jobs in this window"
            icon={Icon.Tray}
            onAction={() =>
              openCommand("jobs", { connectionId: connection.id })
            }
          />
        ) : null}
      </MenuBarExtra.Section>
      {section("Pinned", pins)}
      {section("Running", running)}
      {section("Pending", pending)}
      {preferences.menuBarAttention !== false
        ? section("Needs Attention", attention)
        : null}
      <MenuBarExtra.Section>
        <MenuBarExtra.Item
          title="Open Jobs"
          icon={Icon.List}
          onAction={() => openCommand("jobs", { connectionId: connection.id })}
        />
        <MenuBarExtra.Item
          title="Hosts & Defaults"
          icon={Icon.Desktop}
          onAction={() => openCommand("hosts")}
        />
        <MenuBarExtra.Item
          title="Watchers"
          icon={Icon.Eye}
          onAction={() => openCommand("watchers")}
        />
        <MenuBarExtra.Item
          title="Launch Job"
          icon={Icon.Rocket}
          onAction={() => openCommand("launch")}
        />
        <MenuBarExtra.Item
          title="Refresh Jobs"
          icon={Icon.ArrowClockwise}
          onAction={refresh}
        />
      </MenuBarExtra.Section>
      <MenuBarExtra.Submenu title="Connections" icon={Icon.Plug}>
        {profiles.map((profile) => (
          <MenuBarExtra.Item
            key={profile.id}
            title={profile.name}
            icon={profile.id === connection.id ? Icon.Checkmark : Icon.Plug}
            onAction={() => onSwitch(profile.id)}
          />
        ))}
        <MenuBarExtra.Item
          title="Manage Connections"
          icon={Icon.Gear}
          onAction={() => openCommand("connections")}
        />
      </MenuBarExtra.Submenu>
    </MenuBarExtra>
  );
}

function JobMenuItem({
  connection,
  job,
  onCancel,
}: {
  connection: ConnectionSettings;
  job: JobInfo;
  onCancel: (job: JobInfo) => Promise<void>;
}) {
  const openJob = (view: JobsLaunchContext["view"]) =>
    openCommand("jobs", { connectionId: connection.id, job, view });
  return (
    <MenuBarExtra.Submenu
      title={jobTitle(job) + " · " + job.hostname + " · #" + job.job_id}
      icon={{ source: stateIcon(job.state), tintColor: stateColor(job.state) }}
    >
      <MenuBarExtra.Item title={jobSummary(job)} />
      <MenuBarExtra.Item
        title="Open Job"
        icon={Icon.Sidebar}
        onAction={() => openJob("detail")}
      />
      <MenuBarExtra.Item
        title="View Output"
        icon={Icon.Terminal}
        onAction={() => openJob("output")}
      />
      <MenuBarExtra.Item
        title="View Script"
        icon={Icon.Code}
        onAction={() => openJob("script")}
      />
      <MenuBarExtra.Item
        title="View Watchers"
        icon={Icon.Eye}
        onAction={() => openJob("watchers")}
      />
      <MenuBarExtra.Item
        title="Copy Job ID"
        icon={Icon.Clipboard}
        onAction={() => Clipboard.copy(job.job_id)}
      />
      {canCancelJob(job) ? (
        <MenuBarExtra.Item
          title="Cancel Job"
          icon={Icon.Stop}
          onAction={() => onCancel(job)}
        />
      ) : null}
    </MenuBarExtra.Submenu>
  );
}
async function openCommand(name: string, context?: JobsLaunchContext) {
  await launchCommand({ name, type: LaunchType.UserInitiated, context });
}
