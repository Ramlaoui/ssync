import { useMutation, useQuery } from '@tanstack/react-query';

import { api, type LaunchJobRequest } from '@/src/api/client';

export const launchKeys = {
  status: (launchId: string) => ['launches', launchId] as const,
};

export function useLaunchJob() {
  return useMutation({
    mutationFn: (payload: LaunchJobRequest) => api.launchJob(payload),
  });
}

export function useLaunchStatus(launchId?: string | null) {
  return useQuery({
    queryKey: launchId ? launchKeys.status(launchId) : ['launches', 'idle'],
    queryFn: () => api.getLaunchStatus(launchId!),
    enabled: Boolean(launchId),
    refetchInterval: (query) => {
      const status = query.state.data;
      return status?.terminal ? false : 5_000;
    },
  });
}
