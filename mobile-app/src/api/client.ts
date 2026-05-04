import axios, { AxiosError } from 'axios';
import { z } from 'zod';

import { AppError } from '@/src/lib/errors';
import { buildAbsoluteUrl, normalizeBaseUrl } from '@/src/lib/network';
import {
  healthSchema,
  hostInfoSchema,
  jobInfoSchema,
  jobOutputSchema,
  jobScriptSchema,
  jobStatusResponseSchema,
  launchJobResponseSchema,
  launchStatusSchema,
  notificationDeviceResponseSchema,
  notificationPreferencesSchema,
  watcherEventsResponseSchema,
  watcherMessageResponseSchema,
  watcherStatsSchema,
  watcherTriggerResponseSchema,
  watchersResponseSchema,
  watcherSchema,
} from '@/src/api/schemas';
import { useSessionStore } from '@/src/features/session/session-store';

export type JobFilters = {
  host?: string;
  user?: string;
  state?: string;
  limit?: number;
  activeOnly?: boolean;
  completedOnly?: boolean;
  since?: string;
};

export type LaunchJobRequest = {
  host: string;
  source_dir?: string;
  script_content: string;
  job_name?: string;
  partition?: string;
  cpus?: number;
  mem?: number;
  time?: number;
  exclude: string[];
  include: string[];
  no_gitignore: boolean;
  force_sync?: boolean;
};

export type WatcherActionInput = {
  type: string;
  params?: Record<string, unknown>;
  condition?: string;
};

export type WatcherDefinitionInput = {
  name: string;
  pattern: string;
  interval_seconds: number;
  captures: string[];
  condition?: string;
  actions: WatcherActionInput[];
  output_type?: 'stdout' | 'stderr' | 'both';
  max_triggers?: number;
  timer_mode_enabled?: boolean;
  timer_interval_seconds?: number;
};

function getConfiguredClient() {
  const { baseUrl, apiKey } = useSessionStore.getState();
  const normalized = normalizeBaseUrl(baseUrl);

  if (!normalized) {
    throw new AppError('Configure the ssync server URL before loading data.');
  }

  return axios.create({
    baseURL: normalized,
    timeout: 90_000,
    headers: apiKey ? { 'X-API-Key': apiKey } : undefined,
  });
}

function parseResponse<T>(schema: z.ZodType<T>, data: unknown) {
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    throw new AppError('Server returned an unexpected payload.', undefined, parsed.error.flatten());
  }
  return parsed.data;
}

function toAppError(error: unknown) {
  if (error instanceof AppError) {
    return error;
  }
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ detail?: string }>;
    const detail = axiosError.response?.data?.detail;
    const message = detail ?? axiosError.message ?? 'Network request failed';
    return new AppError(message, axiosError.response?.status, axiosError.response?.data);
  }
  return new AppError(error instanceof Error ? error.message : 'Unexpected error');
}

async function request<T>(
  schema: z.ZodType<T>,
  config: Parameters<ReturnType<typeof getConfiguredClient>['request']>[0],
) {
  const client = getConfiguredClient();

  try {
    const response = await client.request(config);
    return parseResponse(schema, response.data);
  } catch (error) {
    throw toAppError(error);
  }
}

export const api = {
  async healthcheck() {
    return request(healthSchema, { method: 'GET', url: '/health' });
  },

  async getHosts() {
    return request(z.array(hostInfoSchema), { method: 'GET', url: '/api/hosts' });
  },

  async getJobs(filters: JobFilters) {
    return request(z.array(jobStatusResponseSchema), {
      method: 'GET',
      url: '/api/status',
      params: {
        host: filters.host || undefined,
        user: filters.user || undefined,
        state: filters.state || undefined,
        limit: filters.limit ?? 200,
        active_only: filters.activeOnly || undefined,
        completed_only: filters.completedOnly || undefined,
        since: filters.since || undefined,
      },
    });
  },

  async getJobDetail(jobId: string, host?: string) {
    return request(jobInfoSchema, {
      method: 'GET',
      url: `/api/jobs/${encodeURIComponent(jobId)}`,
      params: host ? { host } : undefined,
    });
  },

  async getJobScript(jobId: string, host?: string) {
    return request(jobScriptSchema, {
      method: 'GET',
      url: `/api/jobs/${encodeURIComponent(jobId)}/script`,
      params: host ? { host } : undefined,
    });
  },

  async getJobOutput(jobId: string, host: string, outputType: 'stdout' | 'stderr' | 'both' = 'both') {
    return request(jobOutputSchema, {
      method: 'GET',
      url: `/api/jobs/${encodeURIComponent(jobId)}/output`,
      params: { host, output_type: outputType, lines: 400 },
    });
  },

  async cancelJob(jobId: string, host?: string) {
    return request(watcherMessageResponseSchema, {
      method: 'POST',
      url: `/api/jobs/${encodeURIComponent(jobId)}/cancel`,
      params: host ? { host } : undefined,
    });
  },

  async launchJob(payload: LaunchJobRequest) {
    return request(launchJobResponseSchema, {
      method: 'POST',
      url: '/api/jobs/launch',
      data: payload,
    });
  },

  async getLaunchStatus(launchId: string) {
    return request(launchStatusSchema, {
      method: 'GET',
      url: `/api/launches/${encodeURIComponent(launchId)}`,
    });
  },

  async getJobWatchers(jobId: string, host?: string) {
    return request(watchersResponseSchema, {
      method: 'GET',
      url: `/api/jobs/${encodeURIComponent(jobId)}/watchers`,
      params: host ? { host } : undefined,
    });
  },

  async getAllWatchers(limit = 100, state?: string) {
    return request(watchersResponseSchema, {
      method: 'GET',
      url: '/api/watchers',
      params: { limit, state: state || undefined },
    });
  },

  async getWatcherEvents(limit = 50, jobId?: string) {
    return request(watcherEventsResponseSchema, {
      method: 'GET',
      url: '/api/watchers/events',
      params: { limit, job_id: jobId || undefined },
    });
  },

  async getWatcherStats() {
    return request(watcherStatsSchema, {
      method: 'GET',
      url: '/api/watchers/stats',
    });
  },

  async pauseWatcher(watcherId: number) {
    return request(watcherMessageResponseSchema, {
      method: 'POST',
      url: `/api/watchers/${watcherId}/pause`,
    });
  },

  async resumeWatcher(watcherId: number) {
    return request(watcherMessageResponseSchema, {
      method: 'POST',
      url: `/api/watchers/${watcherId}/resume`,
    });
  },

  async triggerWatcher(watcherId: number) {
    return request(watcherTriggerResponseSchema, {
      method: 'POST',
      url: `/api/watchers/${watcherId}/trigger`,
    });
  },

  async deleteWatcher(watcherId: number) {
    return request(watcherMessageResponseSchema, {
      method: 'DELETE',
      url: `/api/watchers/${watcherId}`,
    });
  },

  async attachWatcher(jobId: string, host: string, definition: WatcherDefinitionInput) {
    return request(watcherMessageResponseSchema, {
      method: 'POST',
      url: `/api/jobs/${encodeURIComponent(jobId)}/watchers`,
      params: { host },
      data: [definition],
    });
  },

  async createWatcher(payload: {
    job_id: string;
    hostname: string;
    name: string;
    pattern: string;
    interval_seconds: number;
    captures: string[];
    condition?: string;
    actions: WatcherActionInput[];
    output_type?: 'stdout' | 'stderr' | 'both';
    timer_mode_enabled?: boolean;
    timer_interval_seconds?: number;
    max_triggers?: number;
  }) {
    return request(watcherSchema, {
      method: 'POST',
      url: '/api/watchers',
      data: payload,
    });
  },

  async getNotificationPreferences() {
    return request(notificationPreferencesSchema, {
      method: 'GET',
      url: '/api/notifications/preferences',
    });
  },

  async updateNotificationPreferences(payload: {
    enabled?: boolean;
    allowed_states?: string[];
    muted_hosts?: string[];
    muted_job_ids?: string[];
    muted_job_name_patterns?: string[];
    allowed_users?: string[];
  }) {
    return request(notificationPreferencesSchema, {
      method: 'PATCH',
      url: '/api/notifications/preferences',
      data: payload,
    });
  },

  async registerNotificationDevice(payload: {
    token: string;
    platform: 'ios';
    environment?: string;
    bundle_id?: string;
    device_id?: string;
    enabled?: boolean;
  }) {
    return request(notificationDeviceResponseSchema, {
      method: 'POST',
      url: '/api/notifications/devices',
      data: payload,
    });
  },
};

export function buildApiUrl(path: string) {
  const { baseUrl } = useSessionStore.getState();
  return buildAbsoluteUrl(baseUrl, path);
}
