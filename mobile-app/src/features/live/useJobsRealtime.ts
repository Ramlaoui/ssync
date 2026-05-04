import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { jobsKeys } from '@/src/features/jobs/hooks';
import { toWebSocketUrl } from '@/src/lib/network';
import { useSessionStore } from '@/src/features/session/session-store';
import type { JobInfo, JobStatusResponse, LaunchStatus } from '@/src/api/schemas';

function upsertJobIntoResponse(response: JobStatusResponse, nextJob: JobInfo) {
  if (response.hostname !== nextJob.hostname) {
    return response;
  }

  const existingIndex = response.jobs.findIndex((job) => job.job_id === nextJob.job_id);
  if (existingIndex === -1) {
    return {
      ...response,
      total_jobs: response.total_jobs + 1,
      jobs: [nextJob, ...response.jobs],
    };
  }

  const jobs = [...response.jobs];
  jobs[existingIndex] = nextJob;
  return { ...response, jobs };
}

export function useJobsRealtime(enabled: boolean) {
  const queryClient = useQueryClient();
  const { baseUrl, apiKey, markWebsocketHealthy, markPollingFallback } = useSessionStore((state) => ({
    baseUrl: state.baseUrl,
    apiKey: state.apiKey,
    markWebsocketHealthy: state.markWebsocketHealthy,
    markPollingFallback: state.markPollingFallback,
  }));

  useEffect(() => {
    if (!enabled || !baseUrl) {
      return;
    }

    const query = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : '';
    const socket = new WebSocket(toWebSocketUrl(baseUrl, `/ws/jobs${query}`));

    socket.onopen = () => {
      markWebsocketHealthy();
    };

    socket.onmessage = (event) => {
      const raw = event.data;
      if (raw === 'pong') {
        markWebsocketHealthy();
        return;
      }

      try {
        const payload = JSON.parse(String(raw)) as {
          type: string;
          job?: JobInfo;
          updates?: Array<{ type: string; job?: JobInfo }>;
          launch_id?: string;
          hostname?: string;
          stage?: string;
          success?: boolean | null;
          job_id?: string | null;
          message?: string | null;
        };

        if (payload.type === 'launch_stage' || payload.type === 'launch_log' || payload.type === 'launch_result') {
          if (payload.launch_id) {
            queryClient.setQueryData<LaunchStatus | undefined>(
              ['launches', payload.launch_id],
              (current) => ({
                launch_id: payload.launch_id!,
                hostname: payload.hostname ?? current?.hostname ?? '',
                stage: payload.stage ?? current?.stage ?? 'accepted',
                terminal: payload.type === 'launch_result' ? true : current?.terminal ?? false,
                success: payload.type === 'launch_result' ? payload.success ?? null : current?.success,
                job_id: payload.job_id ?? current?.job_id ?? null,
                message: payload.message ?? current?.message ?? null,
                events: [
                  ...(current?.events ?? []),
                  {
                    type: payload.type,
                    launch_id: payload.launch_id!,
                    hostname: payload.hostname ?? current?.hostname ?? '',
                    sequence: (current?.events.length ?? 0) + 1,
                    timestamp: new Date().toISOString(),
                    stage: payload.stage ?? null,
                    source: null,
                    stream: null,
                    level: null,
                    message: payload.message ?? null,
                    job_id: payload.job_id ?? null,
                    success: payload.success ?? null,
                  },
                ],
              }),
            );
          }
          return;
        }

        const jobs =
          payload.type === 'batch_update'
            ? payload.updates?.map((item) => item.job).filter(Boolean)
            : [payload.job];

        if (!jobs?.length) {
          return;
        }

        queryClient.setQueriesData<JobStatusResponse[]>({ queryKey: jobsKeys.all }, (current) => {
          if (!current) {
            return current;
          }

          let next = current;
          for (const job of jobs) {
            if (!job) {
              continue;
            }

            next = next.map((response) => upsertJobIntoResponse(response, job));
            queryClient.setQueryData(jobsKeys.detail(job.job_id, job.hostname), job);
          }
          return next;
        });
        markWebsocketHealthy();
      } catch {
        markPollingFallback('Live updates are degraded. Falling back to polling.');
      }
    };

    socket.onerror = () => {
      markPollingFallback('Live updates are degraded. Falling back to polling.');
    };

    socket.onclose = () => {
      markPollingFallback();
    };

    return () => socket.close();
  }, [apiKey, baseUrl, enabled, markPollingFallback, markWebsocketHealthy, queryClient]);
}
