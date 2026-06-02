import {
  Action,
  ActionPanel,
  Icon,
  Keyboard,
  LaunchProps,
  List,
  Toast,
  open,
  showToast,
  useNavigation,
} from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { SsyncClient } from "./api/client";
import {
  STALE_JOB_CACHE_MS,
  clearJobCache,
  getConnection,
  getJobCache,
  saveJobCache,
} from "./api/storage";
import { ConnectionForm } from "./components/ConnectionForm";
import { JobDetail } from "./components/JobDetail";
import { OutputView } from "./components/OutputView";
import { ScriptView } from "./components/ScriptView";
import { WatchersView } from "./components/WatchersView";
import {
  compactJobSubtitle,
  flattenJobs,
  formatRelativeAge,
  isHistorical,
  isPending,
  isRunning,
  jobTitle,
  sortJobs,
  stateColor,
  stateIcon,
  stateLabel,
  webJobUrl,
} from "./lib/format";
import type { ConnectionSettings, JobCache, JobInfo, JobsLaunchContext } from "./types/ssync";

type Props = LaunchProps<{ launchContext?: JobsLaunchContext }>;

export default function Command(props: Props) {
  const [connection, setConnection] = useState<ConnectionSettings | undefined>();
  const [didLoadConnection, setDidLoadConnection] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getConnection().then((loaded) => {
      if (cancelled) return;
      setConnection(loaded);
      setDidLoadConnection(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!didLoadConnection) {
    return <List isLoading />;
  }

  if (!connection) {
    return <ConnectionForm onConfigured={setConnection} />;
  }

  const context = props.launchContext;
  if (context?.job && context.view === "output") {
    return <OutputView connection={connection} job={context.job} />;
  }
  if (context?.job && context.view === "script") {
    return <ScriptView connection={connection} job={context.job} />;
  }
  if (context?.job && context.view === "watchers") {
    return <WatchersView connection={connection} job={context.job} />;
  }
  if (context?.job) {
    return <JobDetail connection={connection} job={context.job} />;
  }

  return <JobsList connection={connection} onConnectionChanged={setConnection} />;
}

function JobsList({
  connection,
  onConnectionChanged,
}: {
  connection: ConnectionSettings;
  onConnectionChanged: (connection: ConnectionSettings) => void;
}) {
  const client = useMemo(() => new SsyncClient(connection), [connection]);
  const { push, pop } = useNavigation();
  const [cache, setCache] = useState<JobCache | undefined>();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadInitial() {
      setIsLoading(true);
      const storedCache = await getJobCache();
      if (cancelled) return;
      if (storedCache) {
        setCache(storedCache);
        setIsLoading(false);
      }
      if (!storedCache || Date.now() - storedCache.loadedAt > STALE_JOB_CACHE_MS) {
        await refreshJobs({ silent: Boolean(storedCache) });
      } else {
        setIsLoading(false);
      }
    }
    void loadInitial();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connection.apiUrl, connection.apiKey, connection.historyWindow, connection.jobLimit]);

  async function refreshJobs(options: { silent?: boolean } = {}) {
    if (!options.silent) setIsLoading(true);
    setError(null);
    try {
      const responses = await client.getStatus({
        since: connection.historyWindow,
        limit: connection.jobLimit,
      });
      const nextCache = { loadedAt: Date.now(), responses };
      setCache(nextCache);
      await saveJobCache(nextCache);
    } catch (refreshError) {
      const message = refreshError instanceof Error ? refreshError.message : String(refreshError);
      setError(message);
      if (!cache) {
        await showToast({ style: Toast.Style.Failure, title: "Failed to load jobs", message });
      }
    } finally {
      if (!options.silent) setIsLoading(false);
    }
  }

  const jobs = useMemo(() => sortJobs(flattenJobs(cache?.responses || [])), [cache]);
  const runningJobs = jobs.filter(isRunning);
  const pendingJobs = jobs.filter(isPending);
  const historicalJobs = jobs.filter(isHistorical);
  const cacheAge = cache ? formatRelativeAge(cache.loadedAt) : "never";

  function configureConnection() {
    push(
      <ConnectionForm
        initial={connection}
        onConfigured={(nextConnection) => {
          onConnectionChanged(nextConnection);
          pop();
          void clearJobCache();
          setCache(undefined);
        }}
      />,
    );
  }

  return (
    <List
      isLoading={isLoading}
      searchBarPlaceholder="Search jobs by name, ID, host, state, partition, or reason"
      navigationTitle="ssync Jobs"
      actions={
        <ActionPanel>
          <Action title="Refresh Jobs" icon={Icon.ArrowClockwise} shortcut={Keyboard.Shortcut.Common.Refresh} onAction={() => refreshJobs()} />
          <Action title="Configure Connection" icon={Icon.Gear} onAction={configureConnection} />
        </ActionPanel>
      }
    >
      {error ? (
        <List.EmptyView
          icon={Icon.Warning}
          title="Failed to load jobs"
          description={error}
          actions={
            <ActionPanel>
              <Action title="Refresh Jobs" icon={Icon.ArrowClockwise} onAction={() => refreshJobs()} />
              <Action title="Configure Connection" icon={Icon.Gear} onAction={configureConnection} />
            </ActionPanel>
          }
        />
      ) : null}
      {!error && jobs.length === 0 && !isLoading ? (
        <List.EmptyView
          icon={Icon.Tray}
          title="No jobs found"
          description={`Loaded ${connection.historyWindow} with limit ${connection.jobLimit}. Cache age: ${cacheAge}.`}
          actions={
            <ActionPanel>
              <Action title="Refresh Jobs" icon={Icon.ArrowClockwise} onAction={() => refreshJobs()} />
              <Action title="Configure Connection" icon={Icon.Gear} onAction={configureConnection} />
            </ActionPanel>
          }
        />
      ) : null}
      <JobSection
        title={`Running Jobs (${runningJobs.length})`}
        jobs={runningJobs}
        connection={connection}
        onRefresh={() => refreshJobs()}
        onConfigure={configureConnection}
      />
      <JobSection
        title={`Pending Jobs (${pendingJobs.length})`}
        jobs={pendingJobs}
        connection={connection}
        onRefresh={() => refreshJobs()}
        onConfigure={configureConnection}
      />
      <JobSection
        title={`Historical Jobs (${historicalJobs.length})`}
        jobs={historicalJobs}
        connection={connection}
        onRefresh={() => refreshJobs()}
        onConfigure={configureConnection}
      />
    </List>
  );
}

function JobSection({
  title,
  jobs,
  connection,
  onRefresh,
  onConfigure,
}: {
  title: string;
  jobs: JobInfo[];
  connection: ConnectionSettings;
  onRefresh: () => void;
  onConfigure: () => void;
}) {
  if (jobs.length === 0) return null;
  return (
    <List.Section title={title}>
      {jobs.map((job) => (
        <JobListItem
          key={`${job.hostname}:${job.job_id}`}
          connection={connection}
          job={job}
          onRefresh={onRefresh}
          onConfigure={onConfigure}
        />
      ))}
    </List.Section>
  );
}

function JobListItem({
  connection,
  job,
  onRefresh,
  onConfigure,
}: {
  connection: ConnectionSettings;
  job: JobInfo;
  onRefresh: () => void;
  onConfigure: () => void;
}) {
  const accessories = [
    { tag: { value: stateLabel(job.state), color: stateColor(job.state) } },
    { text: job.hostname, tooltip: "Host" },
    job.runtime ? { text: job.runtime, tooltip: "Runtime" } : undefined,
    job.partition ? { text: job.partition, tooltip: "Partition" } : undefined,
  ].filter((item): item is NonNullable<typeof item> => Boolean(item));

  const keywords = [
    job.job_id,
    job.hostname,
    job.name,
    job.state,
    job.partition || "",
    job.reason || "",
    job.work_dir || "",
  ].filter(Boolean);

  return (
    <List.Item
      icon={{ source: stateIcon(job.state), tintColor: stateColor(job.state) }}
      title={jobTitle(job)}
      subtitle={compactJobSubtitle(job)}
      accessories={accessories}
      keywords={keywords}
      actions={
        <ActionPanel>
          <ActionPanel.Section>
            <Action.Push title="View Job Detail" icon={Icon.Sidebar} target={<JobDetail connection={connection} job={job} />} />
            <Action.Push title="View Output" icon={Icon.Terminal} target={<OutputView connection={connection} job={job} />} />
            <Action.Push title="View Script" icon={Icon.Code} target={<ScriptView connection={connection} job={job} />} />
            <Action.Push title="View Watchers & Events" icon={Icon.Eye} target={<WatchersView connection={connection} job={job} />} />
          </ActionPanel.Section>
          <ActionPanel.Section>
            <Action title="Refresh Jobs" icon={Icon.ArrowClockwise} shortcut={Keyboard.Shortcut.Common.Refresh} onAction={onRefresh} />
            <Action title="Open in ssync Web" icon={Icon.Globe} onAction={() => open(webJobUrl(connection.apiUrl, job))} />
            <Action title="Configure Connection" icon={Icon.Gear} onAction={onConfigure} />
          </ActionPanel.Section>
          <ActionPanel.Section>
            <Action.CopyToClipboard title="Copy Job ID" content={job.job_id} />
            {job.work_dir ? <Action.CopyToClipboard title="Copy Work Dir" content={job.work_dir} /> : null}
          </ActionPanel.Section>
        </ActionPanel>
      }
    />
  );
}
