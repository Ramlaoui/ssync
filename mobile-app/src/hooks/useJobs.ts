import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppState } from "react-native";

import type { SsyncApiClient } from "../api/client";
import type { ArrayJobGroup, HostInfo, JobInfo, JobStatusResponse, PartitionStatusResponse } from "../types/api";
import type { JobNotificationConfig, UIPreferences } from "../types/settings";
import { jobKey } from "../utils/format";

type JobFilters = {
  host?: string;
  user?: string;
  since?: string;
  limit?: number;
  state?: string;
  activeOnly?: boolean;
  completedOnly?: boolean;
  search?: string;
};

type HostState = {
  hostname: string;
  status: "idle" | "loading" | "connected" | "error";
  lastSync?: number;
  lastError?: string;
  isTimeout?: boolean;
};

function flattenStatus(responses: JobStatusResponse[]): {
  jobs: JobInfo[];
  arrayGroups: ArrayJobGroup[];
} {
  const jobs: JobInfo[] = [];
  const arrayGroups: ArrayJobGroup[] = [];
  for (const response of responses) {
    for (const job of response.jobs || []) {
      jobs.push({ ...job, hostname: job.hostname || response.hostname });
    }
    for (const group of response.array_groups || []) {
      arrayGroups.push({ ...group, hostname: group.hostname || response.hostname });
    }
  }
  return { jobs, arrayGroups };
}

function mergeJobs(current: Map<string, JobInfo>, nextJobs: JobInfo[]): Map<string, JobInfo> {
  const next = new Map(current);
  for (const job of nextJobs) {
    next.set(jobKey(job.job_id, job.hostname), job);
  }
  return next;
}

function isConcreteArrayTask(job: JobInfo) {
  return Boolean(job.array_job_id && job.array_task_id && /^\d+$/.test(job.array_task_id));
}

function countArrayTasks(tasks: JobInfo[]) {
  return tasks.reduce(
    (counts, task) => {
      if (task.state === "PD") counts.pending_count += 1;
      else if (task.state === "R") counts.running_count += 1;
      else if (task.state === "CD") counts.completed_count += 1;
      else if (task.state === "F") counts.failed_count += 1;
      else if (task.state === "CA") counts.cancelled_count += 1;
      return counts;
    },
    {
      pending_count: 0,
      running_count: 0,
      completed_count: 0,
      failed_count: 0,
      cancelled_count: 0
    }
  );
}

function mergeArrayGroupUpdates(current: ArrayJobGroup[], incomingJobs: JobInfo[]) {
  const updates = incomingJobs.filter(isConcreteArrayTask);
  if (updates.length === 0 || current.length === 0) return current;

  let changed = false;
  const next = current.map((group) => {
    const groupUpdates = updates.filter(
      (job) => job.array_job_id === group.array_job_id && (job.hostname || group.hostname) === group.hostname
    );
    if (groupUpdates.length === 0) return group;

    let tasks = group.tasks;
    for (const update of groupUpdates) {
      const updateKey = jobKey(update.job_id, update.hostname || group.hostname);
      const taskIndex = tasks.findIndex((task) => {
        const taskKey = jobKey(task.job_id, task.hostname || group.hostname);
        return taskKey === updateKey || task.array_task_id === update.array_task_id;
      });

      if (taskIndex === -1) {
        tasks = [...tasks, { ...update, hostname: update.hostname || group.hostname }];
        changed = true;
      } else {
        tasks = tasks.map((task, index) =>
          index === taskIndex ? { ...task, ...update, hostname: update.hostname || task.hostname || group.hostname } : task
        );
        changed = true;
      }
    }

    return {
      ...group,
      ...countArrayTasks(tasks),
      total_tasks: Math.max(group.total_tasks, tasks.length),
      tasks
    };
  });

  return changed ? next : current;
}

export function useJobs({
  api,
  preferences,
  jobNotifications,
  authenticated
}: {
  api: SsyncApiClient;
  preferences: UIPreferences;
  jobNotifications: Record<string, JobNotificationConfig>;
  authenticated: boolean;
}) {
  const [hosts, setHosts] = useState<HostInfo[]>([]);
  const [jobsByKey, setJobsByKey] = useState<Map<string, JobInfo>>(new Map());
  const [arrayGroups, setArrayGroups] = useState<ArrayJobGroup[]>([]);
  const [partitions, setPartitions] = useState<PartitionStatusResponse[]>([]);
  const [hostStates, setHostStates] = useState<Map<string, HostState>>(new Map());
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [loadingPartitions, setLoadingPartitions] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(null);

  const previousStatesRef = useRef<Map<string, string>>(new Map());
  const initialLoadSeenRef = useRef(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const appActiveRef = useRef(true);

  const jobs = useMemo(
    () =>
      Array.from(jobsByKey.values()).sort((left, right) => {
        const leftTime = Date.parse(left.submit_time || left.start_time || left.end_time || "0");
        const rightTime = Date.parse(right.submit_time || right.start_time || right.end_time || "0");
        return rightTime - leftTime || right.job_id.localeCompare(left.job_id);
      }),
    [jobsByKey]
  );

  const processJobs = useCallback(
    (incomingJobs: JobInfo[]) => {
      const previousStates = previousStatesRef.current;

      for (const job of incomingJobs) {
        const key = jobKey(job.job_id, job.hostname);
        const newState = String(job.state || "UNKNOWN");
        previousStates.set(key, newState);
      }

      setJobsByKey((current) => mergeJobs(current, incomingJobs));
      setArrayGroups((current) => mergeArrayGroupUpdates(current, incomingJobs));

      if (!initialLoadSeenRef.current) {
        initialLoadSeenRef.current = true;
      }
    },
    []
  );

  const refreshHosts = useCallback(async () => {
    if (!authenticated) return;
    const nextHosts = await api.getHosts();
    setHosts(nextHosts);
  }, [api, authenticated]);

  const refreshJobs = useCallback(
    async (filters: JobFilters = {}, forceRefresh = false) => {
      if (!authenticated) return;
      setLoadingJobs(true);
      setError(null);
      try {
        const responses = await api.getStatus({
          host: filters.host,
          user: filters.user,
          since: filters.since || preferences.defaultSince,
          limit: filters.limit || preferences.jobsPerPage,
          state: filters.state,
          active_only: filters.activeOnly,
          completed_only: filters.completedOnly,
          search: filters.search,
          group_array_jobs: preferences.groupArrayJobs,
          force_refresh: forceRefresh
        });
        const flattened = flattenStatus(responses);
        processJobs(flattened.jobs);
        setArrayGroups(flattened.arrayGroups);
        setLastSyncAt(Date.now());
        setHostStates((current) => {
          const next = new Map(current);
          responses.forEach((response) => {
            next.set(response.hostname, {
              hostname: response.hostname,
              status: "connected",
              lastSync: Date.now()
            });
          });
          return next;
        });
      } catch (refreshError) {
        setError((refreshError as Error).message || "Failed to load jobs");
      } finally {
        setLoadingJobs(false);
      }
    },
    [api, authenticated, preferences.defaultSince, preferences.groupArrayJobs, preferences.jobsPerPage, processJobs]
  );

  const refreshPartitions = useCallback(
    async (host?: string, forceRefresh = false) => {
      if (!authenticated) return;
      setLoadingPartitions(true);
      try {
        const next = await api.getPartitions(host, forceRefresh);
        setPartitions(next);
      } catch (partitionError) {
        setError((partitionError as Error).message || "Failed to load partition resources");
      } finally {
        setLoadingPartitions(false);
      }
    },
    [api, authenticated]
  );

  const updateFromWebSocket = useCallback(
    (message: unknown) => {
      const data = message as Record<string, unknown>;
      if (data.type === "pong") return;

      if (data.type === "initial" && data.jobs && typeof data.jobs === "object") {
        const incoming: JobInfo[] = [];
        Object.entries(data.jobs as Record<string, unknown>).forEach(([hostname, hostJobs]) => {
          if (!Array.isArray(hostJobs)) return;
          hostJobs.forEach((job) => incoming.push({ ...(job as JobInfo), hostname }));
        });
        void processJobs(incoming);
        if (data.array_groups && typeof data.array_groups === "object") {
          const groups = Object.values(data.array_groups as Record<string, unknown>).flatMap((value) =>
            Array.isArray(value) ? (value as ArrayJobGroup[]) : []
          );
          setArrayGroups(groups);
        }
        return;
      }

      if ((data.type === "job_update" || data.type === "state_change") && data.job) {
        const job = data.job as JobInfo;
        const hostname = String(data.hostname || job.hostname || "");
        if (hostname && job.job_id) {
          void processJobs([{ ...job, hostname }]);
        }
        return;
      }

      if (data.type === "batch_update" && Array.isArray(data.updates)) {
        const incoming = (data.updates as Array<Record<string, unknown>>).flatMap((update) => {
          const job = update.job as JobInfo | undefined;
          const hostname = String(update.hostname || job?.hostname || "");
          return job && hostname ? [{ ...job, hostname }] : [];
        });
        void processJobs(incoming);
      }
    },
    [processJobs]
  );

  const closeWebSocket = useCallback(() => {
    if (reconnectRef.current) {
      clearTimeout(reconnectRef.current);
      reconnectRef.current = null;
    }
    wsRef.current?.close();
    wsRef.current = null;
    setWsConnected(false);
  }, []);

  const connectWebSocket = useCallback(() => {
    if (!authenticated || !api.wsBaseURL || wsRef.current?.readyState === WebSocket.OPEN) return;
    closeWebSocket();
    const ws = new WebSocket(api.buildWebSocketURL("/ws/jobs"));
    wsRef.current = ws;
    ws.onopen = () => {
      setWsConnected(true);
      ws.send(JSON.stringify({ type: "ping" }));
    };
    ws.onmessage = (event) => {
      try {
        updateFromWebSocket(JSON.parse(event.data));
      } catch {
        // Ignore malformed realtime payloads.
      }
    };
    ws.onerror = () => {
      setWsConnected(false);
    };
    ws.onclose = () => {
      setWsConnected(false);
      wsRef.current = null;
      if (preferences.websocket.autoReconnect && appActiveRef.current) {
        reconnectRef.current = setTimeout(connectWebSocket, preferences.websocket.initialRetryDelay);
      }
    };
  }, [api, authenticated, closeWebSocket, preferences.websocket.autoReconnect, preferences.websocket.initialRetryDelay, updateFromWebSocket]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      appActiveRef.current = state === "active";
      if (state === "active") {
        connectWebSocket();
      }
    });
    return () => subscription.remove();
  }, [connectWebSocket]);

  useEffect(() => {
    if (!authenticated) {
      closeWebSocket();
      setHosts([]);
      setJobsByKey(new Map());
      setArrayGroups([]);
      setPartitions([]);
      initialLoadSeenRef.current = false;
      previousStatesRef.current = new Map();
      return;
    }
    void refreshHosts();
    void refreshJobs();
    void refreshPartitions();
    connectWebSocket();
    return closeWebSocket;
  }, [authenticated, closeWebSocket, connectWebSocket, refreshHosts, refreshJobs, refreshPartitions]);

  useEffect(() => {
    if (!authenticated || !preferences.autoRefresh) return;
    const timer = setInterval(() => {
      void refreshJobs();
      void refreshPartitions();
    }, Math.max(10, preferences.refreshInterval) * 1000);
    return () => clearInterval(timer);
  }, [authenticated, preferences.autoRefresh, preferences.refreshInterval, refreshJobs, refreshPartitions]);

  return {
    hosts,
    jobs,
    jobsByKey,
    arrayGroups,
    partitions,
    hostStates,
    loadingJobs,
    loadingPartitions,
    error,
    wsConnected,
    lastSyncAt,
    refreshHosts,
    refreshJobs,
    refreshPartitions,
    setJobsByKey,
    processJobs
  };
}
