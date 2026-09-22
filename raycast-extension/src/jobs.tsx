import {
  Action,
  ActionPanel,
  Icon,
  Keyboard,
  List,
  type LaunchProps,
  useNavigation,
} from "@raycast/api";
import { useEffect, useRef, useState } from "react";
import { ConnectionGate } from "./components/ConnectionGate";
import { ConnectionsView } from "./components/ConnectionsView";
import { HostsView } from "./components/HostsView";
import { JobActions } from "./components/JobActions";
import { JobDetail } from "./components/JobDetail";
import { JobPreview } from "./components/JobPreview";
import { LaunchView } from "./components/LaunchView";
import { OutputView } from "./components/OutputView";
import { ScriptView } from "./components/ScriptView";
import { WatchersView } from "./components/WatchersView";
import { useJobs } from "./hooks/useJobs";
import { useWorkspace } from "./hooks/useWorkspace";
import { connectionScope } from "./lib/connections";
import { relay } from "./lib/design";
import {
  flattenJobs,
  formatRelativeAge,
  jobTitle,
  sortJobs,
  stateColor,
  stateIcon,
  stateLabel,
} from "./lib/format";
import {
  jobKey,
  jobStatus,
  jobSummary,
  togglePinned,
  visibleJobs,
} from "./lib/jobs";
import { escapeMarkdown } from "./lib/markdown";
import {
  CONNECTIONS_SHORTCUT,
  HOSTS_SHORTCUT,
  INSPECTOR_SHORTCUT,
} from "./lib/shortcuts";
import type {
  ConnectionSettings,
  JobInfo,
  JobsLaunchContext,
  JobView,
} from "./types/ssync";

export default function Command(
  props: LaunchProps<{ launchContext?: JobsLaunchContext }>,
) {
  return (
    <ConnectionGate connectionId={props.launchContext?.connectionId}>
      {(connection, reload) => (
        <JobsWorkspace
          key={connectionScope(connection)}
          connection={connection}
          onConnectionChanged={reload}
          initialContext={props.launchContext}
        />
      )}
    </ConnectionGate>
  );
}

export function JobsWorkspace({
  connection,
  onConnectionChanged,
  initialContext,
}: {
  connection: ConnectionSettings;
  onConnectionChanged: () => Promise<void>;
  initialContext?: JobsLaunchContext;
}) {
  const { push } = useNavigation();
  const resource = useJobs(connection);
  const { settings, update } = useWorkspace(connection, initialContext?.host);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string>();
  const didOpen = useRef(false);
  useEffect(() => {
    if (
      didOpen.current ||
      !initialContext?.job ||
      (initialContext.connectionId &&
        initialContext.connectionId !== connection.id)
    )
      return;
    didOpen.current = true;
    const job = initialContext.job;
    const props = { connection, job };
    push(
      initialContext.view === "output" ? (
        <OutputView {...props} />
      ) : initialContext.view === "script" ? (
        <ScriptView {...props} />
      ) : initialContext.view === "watchers" ? (
        <WatchersView {...props} />
      ) : (
        <JobDetail {...props} />
      ),
    );
  }, [connection, initialContext, push]);
  const jobs = sortJobs(flattenJobs(resource.cache?.responses || []));
  const filtered = visibleJobs(jobs, settings);
  const hostnames = [
    ...new Set([
      ...(resource.cache?.responses.map((host) => host.hostname) || []),
      ...jobs.map((job) => job.hostname),
    ]),
  ].sort();
  const pins = filtered.filter((job) =>
    settings.pinnedJobs.includes(jobKey(job)),
  );
  const rest = filtered.filter(
    (job) => !settings.pinnedJobs.includes(jobKey(job)),
  );
  const views: [JobView, string][] = [
    ["all", "All Jobs"],
    ["running", "Running"],
    ["pending", "Pending"],
    ["attention", "Needs Attention"],
    ["historical", "Historical"],
    ["pinned", "Pinned"],
  ];
  const workspaceActions = (
    <ActionPanel.Section title="Workspace">
      <Action.Push
        title="Launch Job"
        icon={Icon.Rocket}
        shortcut={Keyboard.Shortcut.Common.New}
        target={<LaunchView connection={connection} />}
      />
      <ActionPanel.Submenu
        title={settings.host ? "Host: " + settings.host : "Filter by Host"}
        icon={Icon.Desktop}
        shortcut={{ modifiers: ["cmd", "shift"], key: "f" }}
      >
        <Action
          title="All Hosts"
          icon={!settings.host ? Icon.Checkmark : Icon.Desktop}
          onAction={() => update({ host: "" })}
        />
        {hostnames.map((host) => (
          <Action
            key={host}
            title={host}
            icon={settings.host === host ? Icon.Checkmark : Icon.Desktop}
            onAction={() => update({ host })}
          />
        ))}
      </ActionPanel.Submenu>
      <Action
        title={settings.showDetail ? "Hide Inspector" : "Show Inspector"}
        icon={Icon.Sidebar}
        shortcut={INSPECTOR_SHORTCUT}
        onAction={() => update({ showDetail: !settings.showDetail })}
      />
      <Action.Push
        title="Hosts & Defaults"
        icon={Icon.Desktop}
        shortcut={HOSTS_SHORTCUT}
        target={
          <HostsView
            connection={connection}
            onConnectionChanged={onConnectionChanged}
          />
        }
      />
      <Action.Push
        title="All Watchers"
        icon={Icon.Eye}
        target={<WatchersView connection={connection} />}
      />
      <Action.Push
        title="Manage Connections"
        icon={Icon.Plug}
        shortcut={CONNECTIONS_SHORTCUT}
        target={<ConnectionsView onChanged={onConnectionChanged} />}
      />
      <Action
        title="Clear Filters"
        icon={Icon.XmarkCircle}
        onAction={() => {
          update({ host: "", view: "all" });
          setSearch("");
        }}
      />
    </ActionPanel.Section>
  );
  const emptyActions = (
    <ActionPanel>
      <Action
        title="Refresh Jobs"
        icon={Icon.ArrowClockwise}
        shortcut={Keyboard.Shortcut.Common.Refresh}
        onAction={() => void resource.refresh(true)}
      />
      {workspaceActions}
    </ActionPanel>
  );
  function item(job: JobInfo) {
    const pinned = settings.pinnedJobs.includes(jobKey(job));
    return (
      <List.Item
        key={jobKey(job)}
        id={jobKey(job)}
        title={jobTitle(job)}
        subtitle={"#" + job.job_id}
        icon={{
          source: pinned ? Icon.Star : stateIcon(job.state),
          tintColor: stateColor(job.state),
        }}
        keywords={[
          job.job_id,
          job.name,
          job.hostname,
          job.state,
          stateLabel(job.state),
          job.partition || "",
          job.reason || "",
          job.user || "",
          job.work_dir || "",
        ]}
        accessories={
          settings.showDetail
            ? []
            : [
                {
                  tag: {
                    value: stateLabel(job.state),
                    color: stateColor(job.state),
                  },
                },
                { text: jobSummary(job) },
              ]
        }
        detail={<JobPreview job={job} />}
        actions={
          <JobActions
            connection={connection}
            job={job}
            pinned={pinned}
            onPin={() =>
              update({ pinnedJobs: togglePinned(settings.pinnedJobs, job) })
            }
            onRefresh={() => resource.refresh(true)}
          >
            {workspaceActions}
          </JobActions>
        }
      />
    );
  }
  return (
    <List
      isLoading={resource.isLoading}
      isShowingDetail={settings.showDetail}
      navigationTitle={
        "Jobs · " +
        connection.name +
        (settings.host ? " · " + settings.host : "")
      }
      searchText={search}
      onSearchTextChange={setSearch}
      selectedItemId={selected}
      onSelectionChange={(id) => setSelected(id || undefined)}
      searchBarPlaceholder="Search jobs, hosts, users, partitions, or reasons…"
      actions={emptyActions}
      searchBarAccessory={
        <List.Dropdown
          tooltip="Job View"
          value={settings.view}
          onChange={(value) => update({ view: value as JobView })}
        >
          {views.map(([value, title]) => (
            <List.Dropdown.Item key={value} value={value} title={title} />
          ))}
        </List.Dropdown>
      }
    >
      <List.EmptyView
        icon={
          resource.error
            ? Icon.Warning
            : settings.view === "pinned"
              ? Icon.Star
              : Icon.Tray
        }
        title={
          resource.error && !resource.cache
            ? "Jobs unavailable"
            : "No matching jobs"
        }
        description={
          resource.error ||
          (settings.view === "pinned"
            ? "Pin a job to keep it within reach."
            : "Change the view, host filter, or historical job window.")
        }
        actions={emptyActions}
      />
      {resource.error && resource.cache ? (
        <List.Section title="Connection">
          <List.Item
            id="connection-error"
            title="Refresh failed · showing saved jobs"
            icon={{ source: Icon.Warning, tintColor: relay.warning }}
            subtitle={formatRelativeAge(resource.cache.loadedAt)}
            detail={
              <List.Item.Detail markdown={escapeMarkdown(resource.error)} />
            }
            actions={emptyActions}
          />
        </List.Section>
      ) : null}
      {pins.length ? (
        <List.Section title="Pinned" subtitle={String(pins.length)}>
          {pins.map(item)}
        </List.Section>
      ) : null}
      {hostnames.flatMap((host) =>
        (["running", "pending", "historical"] as const).map((category) => {
          const section = rest.filter(
            (job) =>
              job.hostname === host &&
              jobStatus(job.state).category === category,
          );
          return section.length ? (
            <List.Section
              key={host + category}
              title={
                host +
                " · " +
                (category === "running"
                  ? "Running"
                  : category === "pending"
                    ? "Pending"
                    : "Historical")
              }
              subtitle={
                section.length +
                " · " +
                (resource.cache
                  ? formatRelativeAge(resource.cache.loadedAt)
                  : "")
              }
            >
              {section.map(item)}
            </List.Section>
          ) : null;
        }),
      )}
    </List>
  );
}
