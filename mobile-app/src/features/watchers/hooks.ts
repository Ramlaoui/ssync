import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/src/api/client';

export const watcherKeys = {
  all: ['watchers'] as const,
  list: () => [...watcherKeys.all, 'list'] as const,
  job: (jobId: string, host?: string) => [...watcherKeys.all, 'job', host ?? 'any', jobId] as const,
  events: (jobId?: string) => [...watcherKeys.all, 'events', jobId ?? 'global'] as const,
  stats: () => [...watcherKeys.all, 'stats'] as const,
};

export function useWatchersList() {
  return useQuery({
    queryKey: watcherKeys.list(),
    queryFn: async () => (await api.getAllWatchers()).watchers,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}

export function useJobWatchers(jobId: string, host?: string) {
  return useQuery({
    queryKey: watcherKeys.job(jobId, host),
    queryFn: async () => (await api.getJobWatchers(jobId, host)).watchers,
    enabled: Boolean(jobId),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}

export function useWatcherEvents(jobId?: string) {
  return useQuery({
    queryKey: watcherKeys.events(jobId),
    queryFn: async () => (await api.getWatcherEvents(50, jobId)).events,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}

export function useWatcherStats() {
  return useQuery({
    queryKey: watcherKeys.stats(),
    queryFn: () => api.getWatcherStats(),
    staleTime: 30_000,
    refetchInterval: 45_000,
  });
}

function invalidateAll(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: watcherKeys.all });
}

export function usePauseWatcher() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (watcherId: number) => api.pauseWatcher(watcherId),
    onSuccess: () => invalidateAll(queryClient),
  });
}

export function useResumeWatcher() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (watcherId: number) => api.resumeWatcher(watcherId),
    onSuccess: () => invalidateAll(queryClient),
  });
}

export function useTriggerWatcher() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (watcherId: number) => api.triggerWatcher(watcherId),
    onSuccess: () => invalidateAll(queryClient),
  });
}

export function useDeleteWatcher() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (watcherId: number) => api.deleteWatcher(watcherId),
    onSuccess: () => invalidateAll(queryClient),
  });
}

export function useAttachWatcher() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      jobId,
      host,
      name,
      pattern,
    }: {
      jobId: string;
      host: string;
      name: string;
      pattern: string;
    }) =>
      api.attachWatcher(jobId, host, {
        name,
        pattern,
        interval_seconds: 30,
        captures: [],
        actions: [{ type: 'log_event', params: {} }],
        output_type: 'stdout',
      }),
    onSuccess: (_, variables) => {
      invalidateAll(queryClient);
      queryClient.invalidateQueries({ queryKey: watcherKeys.job(variables.jobId, variables.host) });
    },
  });
}
