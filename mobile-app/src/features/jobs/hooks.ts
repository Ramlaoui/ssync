import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type JobFilters } from '@/src/api/client';
import type { JobInfo, JobStatusResponse } from '@/src/api/schemas';
import { toErrorMessage } from '@/src/lib/errors';
import { useSessionStore } from '@/src/features/session/session-store';

export const jobsKeys = {
  all: ['jobs'] as const,
  list: (filters: JobFilters) => [...jobsKeys.all, 'list', filters] as const,
  detail: (jobId: string, host?: string) => [...jobsKeys.all, 'detail', host ?? 'any', jobId] as const,
  output: (jobId: string, host: string, outputType: string) =>
    [...jobsKeys.all, 'output', host, jobId, outputType] as const,
  script: (jobId: string, host?: string) => [...jobsKeys.all, 'script', host ?? 'any', jobId] as const,
};

function flattenJobs(responses: JobStatusResponse[]) {
  return responses
    .flatMap((response) => response.jobs)
    .sort((left, right) => {
      const rightTime = new Date(right.submit_time ?? 0).getTime();
      const leftTime = new Date(left.submit_time ?? 0).getTime();
      return rightTime - leftTime;
    });
}

export function useJobsList(filters: JobFilters) {
  const markRestSuccess = useSessionStore((state) => state.markRestSuccess);
  const markRestFailure = useSessionStore((state) => state.markRestFailure);

  return useQuery({
    queryKey: jobsKeys.list(filters),
    queryFn: async () => {
      try {
        const jobs = await api.getJobs(filters);
        markRestSuccess();
        return jobs;
      } catch (error) {
        markRestFailure(toErrorMessage(error));
        throw error;
      }
    },
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}

export function useFlattenedJobs(filters: JobFilters) {
  const query = useJobsList(filters);

  return useMemo(
    () => ({
      ...query,
      items: query.data ? flattenJobs(query.data) : [],
    }),
    [query],
  );
}

export function useJobDetail(jobId: string, host?: string) {
  return useQuery({
    queryKey: jobsKeys.detail(jobId, host),
    queryFn: () => api.getJobDetail(jobId, host),
    enabled: Boolean(jobId),
    staleTime: 20_000,
    refetchInterval: 30_000,
  });
}

export function useJobScript(jobId: string, host?: string) {
  return useQuery({
    queryKey: jobsKeys.script(jobId, host),
    queryFn: () => api.getJobScript(jobId, host),
    enabled: Boolean(jobId),
    staleTime: 60_000,
  });
}

export function useJobOutput(jobId: string, host: string, outputType: 'stdout' | 'stderr' | 'both') {
  return useQuery({
    queryKey: jobsKeys.output(jobId, host, outputType),
    queryFn: () => api.getJobOutput(jobId, host, outputType),
    enabled: Boolean(jobId && host),
    staleTime: 20_000,
    refetchInterval: 30_000,
  });
}

export function useCancelJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, host }: { jobId: string; host?: string }) => api.cancelJob(jobId, host),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: jobsKeys.all });
      queryClient.invalidateQueries({ queryKey: jobsKeys.detail(variables.jobId, variables.host) });
    },
  });
}

export function upsertJob(jobList: JobInfo[], nextJob: JobInfo) {
  const index = jobList.findIndex(
    (item) => item.job_id === nextJob.job_id && item.hostname === nextJob.hostname,
  );
  if (index === -1) {
    return [nextJob, ...jobList];
  }

  const clone = [...jobList];
  clone[index] = nextJob;
  return clone;
}
