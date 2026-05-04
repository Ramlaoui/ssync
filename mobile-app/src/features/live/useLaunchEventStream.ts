import { useEffect } from 'react';
import EventSource from 'react-native-sse';
import { useQueryClient } from '@tanstack/react-query';

import type { LaunchStatus } from '@/src/api/schemas';
import { buildApiUrl } from '@/src/api/client';
import { useSessionStore } from '@/src/features/session/session-store';

export function useLaunchEventStream(launchId?: string | null) {
  const queryClient = useQueryClient();
  const apiKey = useSessionStore((state) => state.apiKey);

  useEffect(() => {
    if (!launchId) {
      return;
    }

    const separator = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : '';
    const stream = new EventSource(buildApiUrl(`/api/launches/${encodeURIComponent(launchId)}/events${separator}`));

    stream.addEventListener('message', (event) => {
      if (!event.data) {
        return;
      }

      try {
        const payload = JSON.parse(event.data as string) as LaunchStatus['events'][number];
        queryClient.setQueryData<LaunchStatus | undefined>(['launches', launchId], (current) => ({
          launch_id: launchId,
          hostname: payload.hostname ?? current?.hostname ?? '',
          stage: payload.stage ?? current?.stage ?? 'accepted',
          terminal: payload.type === 'launch_result' ? true : current?.terminal ?? false,
          success: payload.type === 'launch_result' ? payload.success ?? null : current?.success,
          job_id: payload.job_id ?? current?.job_id ?? null,
          message: payload.message ?? current?.message ?? null,
          events: [...(current?.events ?? []), payload],
        }));

        if (payload.type === 'launch_result') {
          stream.close();
        }
      } catch {
        stream.close();
      }
    });

    return () => stream.close();
  }, [apiKey, launchId, queryClient]);
}
