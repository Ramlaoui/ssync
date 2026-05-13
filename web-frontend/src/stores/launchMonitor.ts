import { get, writable } from 'svelte/store';
import { safeGetItem, safeSetItem } from '../lib/safeStorage';
import { LaunchEventStream, fetchLaunchStatus } from '../lib/launchStreaming';
import { api } from '../services/api';
import type { LaunchEvent, LaunchJobRequest, LaunchJobResponse } from '../types/api';

const STORAGE_KEY = 'ssync_launch_monitor_v1';
const MAX_EVENTS_PER_LAUNCH = 80;
const MAX_LOG_LINES_PER_LAUNCH = 24;
const MAX_STORED_LAUNCHES = 30;
const STORAGE_DEBOUNCE_MS = 200;

export type LaunchMonitorStatus = 'queued' | 'launching' | 'success' | 'error' | 'lost';

export interface LaunchMonitorItem {
  clientId: string;
  launchId?: string;
  attempt: number;
  request: LaunchJobRequest;
  host: string;
  jobName?: string;
  sourceDir?: string;
  status: LaunchMonitorStatus;
  stage?: string;
  message?: string;
  jobId?: string;
  events: LaunchEvent[];
  logs: string[];
  createdAt: string;
  updatedAt: string;
  terminal: boolean;
  dismissed: boolean;
}

export const launchMonitorItems = writable<LaunchMonitorItem[]>(loadStoredItems());

const streams = new Map<string, LaunchEventStream>();
let persistTimer: ReturnType<typeof setTimeout> | null = null;

launchMonitorItems.subscribe(() => {
  schedulePersist();
});

function isBrowser(): boolean {
  return typeof window !== 'undefined';
}

function nowIso(): string {
  return new Date().toISOString();
}

function makeClientId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `launch-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function loadStoredItems(): LaunchMonitorItem[] {
  if (!isBrowser()) {
    return [];
  }

  try {
    const raw = safeGetItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter((item): item is LaunchMonitorItem => {
        return (
          item &&
          typeof item.clientId === 'string' &&
          item.request &&
          typeof item.host === 'string'
        );
      })
      .map((item) => ({
        ...item,
        events: Array.isArray(item.events) ? item.events.slice(-MAX_EVENTS_PER_LAUNCH) : [],
        logs: Array.isArray(item.logs) ? item.logs.slice(-MAX_LOG_LINES_PER_LAUNCH) : [],
        dismissed: Boolean(item.dismissed),
        terminal: Boolean(item.terminal),
        attempt: item.attempt || 1,
      }));
  } catch (error) {
    console.warn('Failed to restore launch monitor state:', error);
    return [];
  }
}

function schedulePersist(): void {
  if (!isBrowser()) {
    return;
  }
  if (persistTimer) {
    clearTimeout(persistTimer);
  }
  persistTimer = setTimeout(() => {
    persistTimer = null;
    persistItems();
  }, STORAGE_DEBOUNCE_MS);
}

function persistItems(): void {
  if (!isBrowser()) {
    return;
  }

  const items = get(launchMonitorItems)
    .slice()
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt))
    .slice(0, MAX_STORED_LAUNCHES);

  safeSetItem(STORAGE_KEY, JSON.stringify(items));
}

function formatLogLine(event: LaunchEvent): string | null {
  if (event.type !== 'launch_log' || !event.message) {
    return null;
  }
  const source = event.source || 'launch';
  const stream = event.stream || 'stdout';
  return `[${source}/${stream}] ${event.message}`;
}

function extractErrorMessage(error: any, fallback: string): string {
  const errorData = error?.response?.data;
  if (typeof errorData?.detail === 'string') {
    return errorData.detail;
  }
  if (Array.isArray(errorData?.detail)) {
    return errorData.detail
      .map((entry: any) => `${entry.loc?.join('.') || 'request'}: ${entry.msg || entry}`)
      .join(', ');
  }
  if (errorData?.detail && typeof errorData.detail === 'object') {
    return JSON.stringify(errorData.detail);
  }
  if (typeof errorData?.message === 'string') {
    return errorData.message;
  }
  if (errorData) {
    return JSON.stringify(errorData);
  }
  return error?.message || fallback;
}

function updateItem(clientId: string, updater: (item: LaunchMonitorItem) => LaunchMonitorItem): void {
  launchMonitorItems.update((items) =>
    items.map((item) => (item.clientId === clientId ? updater(item) : item)),
  );
}

function upsertItem(item: LaunchMonitorItem): void {
  launchMonitorItems.update((items) => {
    const withoutExisting = items.filter((existing) => existing.clientId !== item.clientId);
    return [item, ...withoutExisting].slice(0, MAX_STORED_LAUNCHES);
  });
}

function closeStream(clientId: string): void {
  const stream = streams.get(clientId);
  if (stream) {
    stream.close();
    streams.delete(clientId);
  }
}

function applyLaunchEvent(clientId: string, event: LaunchEvent): void {
  updateItem(clientId, (item) => {
    if (item.launchId && event.launch_id !== item.launchId) {
      return item;
    }
    if (item.events.some((existing) => existing.sequence === event.sequence)) {
      return item;
    }

    const logLine = formatLogLine(event);
    const nextEvents = [...item.events, event].slice(-MAX_EVENTS_PER_LAUNCH);
    const nextLogs = logLine
      ? [...item.logs, logLine].slice(-MAX_LOG_LINES_PER_LAUNCH)
      : item.logs;
    const terminal = event.type === 'launch_result';
    const success = terminal && event.success;
    const failed = terminal && !event.success;

    return {
      ...item,
      status: success ? 'success' : failed ? 'error' : 'launching',
      stage: event.stage ?? item.stage,
      message: event.message ?? item.message,
      jobId: event.job_id ?? item.jobId,
      events: nextEvents,
      logs: nextLogs,
      terminal: terminal ? true : item.terminal,
      updatedAt: nowIso(),
    };
  });

  if (event.type === 'launch_result') {
    closeStream(clientId);
  }
}

function attachStream(clientId: string, launchId: string): void {
  closeStream(clientId);
  const stream = new LaunchEventStream();
  streams.set(clientId, stream);
  stream.start(
    launchId,
    (event) => applyLaunchEvent(clientId, event),
    () => {
      closeStream(clientId);
      void recoverLaunch(clientId);
    },
  );
}

function buildItem(request: LaunchJobRequest, attempt = 1): LaunchMonitorItem {
  const timestamp = nowIso();
  return {
    clientId: makeClientId(),
    attempt,
    request: { ...request },
    host: request.host,
    jobName: request.job_name,
    sourceDir: request.source_dir,
    status: 'queued',
    stage: 'queued',
    message: 'Submitting launch request...',
    events: [],
    logs: [],
    createdAt: timestamp,
    updatedAt: timestamp,
    terminal: false,
    dismissed: false,
  };
}

async function postLaunch(clientId: string, request: LaunchJobRequest): Promise<void> {
  const response = await api.post<LaunchJobResponse>('/api/jobs/launch', request);
  const payload = response.data;

  if (payload?.success && payload.launch_id) {
    updateItem(clientId, (item) => ({
      ...item,
      launchId: payload.launch_id,
      host: payload.hostname || item.host,
      status: 'launching',
      stage: 'accepted',
      message: payload.message || 'Launch accepted. Waiting for background execution.',
      terminal: false,
      updatedAt: nowIso(),
    }));
    attachStream(clientId, payload.launch_id);
    return;
  }

  if (payload?.success && payload.job_id) {
    updateItem(clientId, (item) => ({
      ...item,
      host: payload.hostname || item.host,
      jobId: payload.job_id,
      status: 'success',
      stage: 'completed',
      message: payload.message || `Job ${payload.job_id} launched successfully`,
      terminal: true,
      updatedAt: nowIso(),
    }));
    return;
  }

  throw new Error(payload?.message || 'Invalid launch response from server');
}

async function startLaunch(request: LaunchJobRequest): Promise<string> {
  const item = buildItem(request);
  upsertItem(item);

  try {
    await postLaunch(item.clientId, request);
  } catch (error: any) {
    updateItem(item.clientId, (current) => ({
      ...current,
      status: 'error',
      stage: 'failed',
      message: extractErrorMessage(error, 'Failed to launch job'),
      terminal: true,
      updatedAt: nowIso(),
    }));
    throw error;
  }

  return item.clientId;
}

async function relaunch(clientId: string): Promise<void> {
  const item = get(launchMonitorItems).find((candidate) => candidate.clientId === clientId);
  if (!item) {
    return;
  }

  closeStream(clientId);
  updateItem(clientId, (current) => ({
    ...current,
    attempt: current.attempt + 1,
    launchId: undefined,
    jobId: undefined,
    status: 'queued',
    stage: 'queued',
    message: 'Relaunching...',
    events: [],
    logs: [],
    terminal: false,
    dismissed: false,
    updatedAt: nowIso(),
  }));

  try {
    await postLaunch(clientId, item.request);
  } catch (error: any) {
    updateItem(clientId, (current) => ({
      ...current,
      status: 'error',
      stage: 'failed',
      message: extractErrorMessage(error, 'Failed to relaunch job'),
      terminal: true,
      updatedAt: nowIso(),
    }));
  }
}

async function recoverLaunch(clientId: string): Promise<void> {
  const item = get(launchMonitorItems).find((candidate) => candidate.clientId === clientId);
  if (!item?.launchId || item.terminal) {
    return;
  }

  try {
    const status = await fetchLaunchStatus(item.launchId);
    for (const event of status.events) {
      applyLaunchEvent(clientId, event);
    }

    const latest = get(launchMonitorItems).find((candidate) => candidate.clientId === clientId);
    if (status.terminal || latest?.terminal) {
      if (!latest?.terminal) {
        updateItem(clientId, (current) => ({
          ...current,
          status: status.success ? 'success' : 'error',
          stage: status.stage,
          message: status.message || current.message,
          jobId: status.job_id || current.jobId,
          terminal: true,
          updatedAt: nowIso(),
        }));
      }
      closeStream(clientId);
      return;
    }

    updateItem(clientId, (current) => ({
      ...current,
      status: 'launching',
      stage: status.stage || current.stage,
      message: status.message || current.message,
      updatedAt: nowIso(),
    }));
    attachStream(clientId, item.launchId);
  } catch (error) {
    console.warn('Failed to recover launch status:', error);
    updateItem(clientId, (current) => ({
      ...current,
      status: 'lost',
      terminal: true,
      message: 'Launch progress connection was lost',
      updatedAt: nowIso(),
    }));
  }
}

async function recoverActiveLaunches(): Promise<void> {
  const items = get(launchMonitorItems).filter(
    (item) => !item.terminal && item.status !== 'lost' && item.launchId,
  );
  await Promise.all(items.map((item) => recoverLaunch(item.clientId)));
}

function dismiss(clientId: string): void {
  closeStream(clientId);
  updateItem(clientId, (item) => ({
    ...item,
    dismissed: true,
    updatedAt: nowIso(),
  }));
}

function clearTerminal(): void {
  launchMonitorItems.update((items) => {
    for (const item of items) {
      if (item.terminal || item.status === 'lost') {
        closeStream(item.clientId);
      }
    }
    return items.filter((item) => !(item.terminal || item.status === 'lost'));
  });
}

function visibleItems(): LaunchMonitorItem[] {
  return get(launchMonitorItems).filter((item) => !item.dismissed);
}

export const launchMonitor = {
  items: launchMonitorItems,
  startLaunch,
  relaunch,
  recoverActiveLaunches,
  dismiss,
  clearTerminal,
  closeStream,
  visibleItems,
};
