import { Clipboard, Icon, LaunchType, MenuBarExtra, Toast, launchCommand, showToast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { SsyncClient } from "./api/client";
import { STALE_JOB_CACHE_MS, getConnection, getJobCache, saveJobCache } from "./api/storage";
import {
  compactJobSubtitle,
  flattenJobs,
  isPending,
  isRunning,
  jobTitle,
  sortJobs,
  stateColor,
  stateCountLabel,
  stateIcon,
} from "./lib/format";
import type { ConnectionSettings, JobCache, JobInfo, JobsLaunchContext } from "./types/ssync";

export default function Command() {
  const [connection, setConnection] = useState<ConnectionSettings | undefined>();
  const [cache, setCache] = useState<JobCache | undefined>();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const loadedConnection = await getConnection();
      if (cancelled) return;
      setConnection(loadedConnection);
      if (!loadedConnection) {
        setIsLoading(false);
        return;
      }

      const storedCache = await getJobCache();
      if (cancelled) return;
      if (storedCache) {
        setCache(storedCache);
        setIsLoading(false);
      }
      if (!storedCache || Date.now() - storedCache.loadedAt > STALE_JOB_CACHE_MS) {
        await refresh(loadedConnection, { silent: Boolean(storedCache) });
      } else {
        setIsLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh(connectionOverride?: ConnectionSettings, options: { silent?: boolean } = {}) {
    const activeConnection = connectionOverride || connection;
    if (!activeConnection) {
      await openJobsCommand();
      return;
    }
    const activeClient = new SsyncClient(activeConnection);
    if (!options.silent) setIsLoading(true);
    setError(null);
    try {
      const responses = await activeClient.getStatus({
        since: activeConnection.historyWindow,
        limit: activeConnection.jobLimit,
      });
      const nextCache = { loadedAt: Date.now(), responses };
      setCache(nextCache);
      await saveJobCache(nextCache);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : String(refreshError));
    } finally {
      if (!options.silent) setIsLoading(false);
    }
  }

  const jobs = sortJobs(flattenJobs(cache?.responses || []));
  const runningJobs = jobs.filter(isRunning);
  const pendingJobs = jobs.filter(isPending);
  const label = stateCountLabel(jobs);

  if (!connection) {
    return (
      <MenuBarExtra icon={Icon.Gear} title="ssync setup" isLoading={isLoading}>
        <MenuBarExtra.Item title="Configure Connection" icon={Icon.Gear} onAction={() => openJobsCommand()} />
      </MenuBarExtra>
    );
  }

  return (
    <MenuBarExtra icon={Icon.ComputerChip} title={label || "ssync"} isLoading={isLoading}>
      {error ? <MenuBarExtra.Item title="ssync API offline" subtitle={error} icon={Icon.Warning} onAction={() => openJobsCommand()} /> : null}
      <MenuBarExtra.Section title={`Running Jobs (${runningJobs.length})`}>
        {runningJobs.length ? runningJobs.map((job) => <JobMenuItem key={`${job.hostname}:${job.job_id}`} job={job} />) : <MenuBarExtra.Item title="No running jobs" icon={Icon.Circle} />}
      </MenuBarExtra.Section>
      <MenuBarExtra.Section title={`Pending Jobs (${pendingJobs.length})`}>
        {pendingJobs.length ? pendingJobs.map((job) => <JobMenuItem key={`${job.hostname}:${job.job_id}`} job={job} />) : <MenuBarExtra.Item title="No pending jobs" icon={Icon.Circle} />}
      </MenuBarExtra.Section>
      <MenuBarExtra.Section>
        <MenuBarExtra.Item title="Open Jobs" icon={Icon.List} onAction={() => openJobsCommand()} />
        <MenuBarExtra.Item
          title="Refresh"
          icon={Icon.ArrowClockwise}
          onAction={async () => {
            await refresh();
            await showToast({ style: Toast.Style.Success, title: "ssync jobs refreshed" });
          }}
        />
        <MenuBarExtra.Item title="Configure Connection" icon={Icon.Gear} onAction={() => openJobsCommand()} />
      </MenuBarExtra.Section>
    </MenuBarExtra>
  );
}

function JobMenuItem({ job }: { job: JobInfo }) {
  return (
    <MenuBarExtra.Submenu
      title={jobTitle(job)}
      icon={{ source: stateIcon(job.state), tintColor: stateColor(job.state) }}
    >
      <MenuBarExtra.Item title={compactJobSubtitle(job)} icon={Icon.Info} />
      <MenuBarExtra.Item title="Open Job Detail" icon={Icon.Sidebar} onAction={() => openJobsCommand({ job, view: "detail" })} />
      <MenuBarExtra.Item title="View Output" icon={Icon.Terminal} onAction={() => openJobsCommand({ job, view: "output" })} />
      <MenuBarExtra.Item title="View Script" icon={Icon.Code} onAction={() => openJobsCommand({ job, view: "script" })} />
      <MenuBarExtra.Item title="Copy Job ID" icon={Icon.Clipboard} onAction={() => Clipboard.copy(job.job_id)} />
    </MenuBarExtra.Submenu>
  );
}

async function openJobsCommand(context?: JobsLaunchContext) {
  await launchCommand({
    name: "jobs",
    type: LaunchType.UserInitiated,
    context,
  });
}
