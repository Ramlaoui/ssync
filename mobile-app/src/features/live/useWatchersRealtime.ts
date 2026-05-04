import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import type { Watcher, WatcherEvent } from '@/src/api/schemas';
import { watcherKeys } from '@/src/features/watchers/hooks';
import { toWebSocketUrl } from '@/src/lib/network';
import { useSessionStore } from '@/src/features/session/session-store';

export function useWatchersRealtime(enabled: boolean) {
  const queryClient = useQueryClient();
  const { baseUrl, apiKey } = useSessionStore((state) => ({
    baseUrl: state.baseUrl,
    apiKey: state.apiKey,
  }));

  useEffect(() => {
    if (!enabled || !baseUrl) {
      return;
    }

    const query = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : '';
    const socket = new WebSocket(toWebSocketUrl(baseUrl, `/ws/watchers${query}`));

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(String(event.data)) as {
          type: string;
          event?: WatcherEvent;
          watcher?: Watcher;
          watcher_id?: number;
          state?: string;
          events?: WatcherEvent[];
        };

        if (payload.type === 'initial' && payload.events) {
          queryClient.setQueryData(watcherKeys.events(), payload.events);
          return;
        }

        if (payload.type === 'watcher_event' && payload.event) {
          queryClient.setQueryData<WatcherEvent[]>(watcherKeys.events(), (current = []) => [
            payload.event!,
            ...current,
          ]);
          queryClient.invalidateQueries({ queryKey: watcherKeys.stats() });
        }

        if (payload.type === 'watcher_update' && payload.watcher) {
          queryClient.setQueryData<Watcher[]>(watcherKeys.list(), (current = []) =>
            current.map((watcher) => (watcher.id === payload.watcher!.id ? payload.watcher! : watcher)),
          );
        }

        if (payload.type === 'watcher_state_change' && payload.watcher_id && payload.state) {
          queryClient.setQueryData<Watcher[]>(watcherKeys.list(), (current = []) =>
            current.map((watcher) =>
              watcher.id === payload.watcher_id ? { ...watcher, state: payload.state! } : watcher,
            ),
          );
        }
      } catch {
        // Ignore malformed watcher events and let polling repair the cache.
      }
    };

    return () => socket.close();
  }, [apiKey, baseUrl, enabled, queryClient]);
}
