import { writable, derived, get } from 'svelte/store';
import type { Watcher, WatcherEvent, WatcherStats, WatchersResponse, WatcherEventsResponse } from '../types/watchers';
import { api, apiConfig } from '../services/api';

// Debug mode - set to true to enable verbose logging
const DEBUG_WATCHERS = true;

// Validate and sanitize watcher data
function validateWatcher(watcher: any, source: string): Watcher | null {
  if (!watcher) {
    if (DEBUG_WATCHERS) {
      console.warn(`[Watchers] Null/undefined watcher from ${source}`, { watcher });
    }
    return null;
  }

  const hasRequiredFields = watcher.id != null && watcher.state != null && watcher.job_id != null;

  if (!hasRequiredFields) {
    if (DEBUG_WATCHERS) {
      console.error(`[Watchers] Invalid watcher from ${source} - missing required fields:`, {
        watcher,
        hasId: watcher.id != null,
        hasState: watcher.state != null,
        hasJobId: watcher.job_id != null,
        stack: new Error().stack
      });
    }
    return null;
  }

  return watcher as Watcher;
}

// Validate array of watchers
function validateWatchers(watchers: any[], source: string): Watcher[] {
  if (!Array.isArray(watchers)) {
    if (DEBUG_WATCHERS) {
      console.error(`[Watchers] Expected array from ${source}, got:`, typeof watchers);
    }
    return [];
  }

  const validated = watchers
    .map(w => validateWatcher(w, source))
    .filter((w): w is Watcher => w !== null);

  const invalidCount = watchers.length - validated.length;
  if (invalidCount > 0 && DEBUG_WATCHERS) {
    console.warn(`[Watchers] Filtered out ${invalidCount} invalid watchers from ${source}`);
  }

  return validated;
}

// Store for all watchers
export const watchers = writable<Watcher[]>([]);

// Store for watcher events
export const watcherEvents = writable<WatcherEvent[]>([]);

// Store for watcher statistics
export const watcherStats = writable<WatcherStats | null>(null);

// Store for selected watcher
export const selectedWatcher = writable<Watcher | null>(null);

// Store for loading states
export const watchersLoading = writable(false);
export const eventsLoading = writable(false);
export const statsLoading = writable(false);

// Derived store for active watchers
export const activeWatchers = derived(
  watchers,
  $watchers => $watchers.filter(w => w && w.state === 'active')
);

// Derived store for watchers by job
export const watchersByJob = derived(
  watchers,
  $watchers => {
    const grouped: Record<string, Watcher[]> = {};
    $watchers.forEach(w => {
      if (!grouped[w.job_id]) {
        grouped[w.job_id] = [];
      }
      grouped[w.job_id].push(w);
    });
    return grouped;
  }
);

// Fetch watchers for a job
export async function fetchJobWatchers(jobId: string, host?: string): Promise<void> {
  watchersLoading.set(true);
  try {
    const params = host ? { host } : {};
    const response = await api.get<WatchersResponse>(
      `/api/jobs/${encodeURIComponent(jobId)}/watchers`,
      { params }
    );
    
    // Update watchers store with job-specific watchers
    watchers.update(current => {
      // Validate incoming watchers
      const newWatchers = validateWatchers(response.data.watchers || [], `fetchJobWatchers(${jobId})`);

      if (DEBUG_WATCHERS) {
        console.log(`[Watchers] Fetched ${newWatchers.length} watchers for job ${jobId}`, newWatchers);
      }

      // Remove old watchers for this job
      const filtered = current.filter(w => w.job_id !== jobId);
      // Add new validated watchers
      return [...filtered, ...newWatchers];
    });
  } catch (error) {
    console.error('Failed to fetch job watchers:', error);
    throw error;
  } finally {
    watchersLoading.set(false);
  }
}

// Fetch all watchers using the global endpoint
export async function fetchAllWatchers(): Promise<void> {
  watchersLoading.set(true);
  try {
    const response = await api.get<WatchersResponse>('/api/watchers', {
      params: { limit: 100 }
    });

    const validatedWatchers = validateWatchers(response.data.watchers || [], 'fetchAllWatchers');

    if (DEBUG_WATCHERS) {
      console.log(`[Watchers] Fetched ${validatedWatchers.length} watchers globally`, validatedWatchers);
    }

    watchers.set(validatedWatchers);
  } catch (error) {
    console.error('Failed to fetch all watchers:', error);
    throw error;
  } finally {
    watchersLoading.set(false);
  }
}

// Fetch watcher events
export async function fetchWatcherEvents(
  jobId?: string,
  watcherId?: number,
  limit: number = 50
): Promise<void> {
  eventsLoading.set(true);
  try {
    const params: any = { limit };
    if (jobId) params.job_id = jobId;
    if (watcherId) params.watcher_id = watcherId;
    
    const response = await api.get<WatcherEventsResponse>(
      '/api/watchers/events',
      { params }
    );
    
    watcherEvents.set(response.data.events);
  } catch (error) {
    console.error('Failed to fetch watcher events:', error);
    throw error;
  } finally {
    eventsLoading.set(false);
  }
}

// Fetch watcher statistics
export async function fetchWatcherStats(): Promise<void> {
  statsLoading.set(true);
  try {
    const response = await api.get<WatcherStats>(
      '/api/watchers/stats'
    );
    watcherStats.set(response.data);
  } catch (error) {
    console.error('Failed to fetch watcher stats:', error);
    throw error;
  } finally {
    statsLoading.set(false);
  }
}

// Pause a watcher
export async function pauseWatcher(watcherId: number): Promise<void> {
  try {
    await api.post(`/api/watchers/${watcherId}/pause`);
    
    // Update local state
    watchers.update(current => 
      current.map(w => 
        w.id === watcherId ? { ...w, state: 'paused' as const } : w
      )
    );
  } catch (error) {
    console.error('Failed to pause watcher:', error);
    throw error;
  }
}

// Resume a watcher
export async function resumeWatcher(watcherId: number): Promise<void> {
  try {
    await api.post(`/api/watchers/${watcherId}/resume`);
    
    // Update local state
    watchers.update(current => 
      current.map(w => 
        w.id === watcherId ? { ...w, state: 'active' as const } : w
      )
    );
  } catch (error) {
    console.error('Failed to resume watcher:', error);
    throw error;
  }
}

// WebSocket connection for real-time updates
let watcherWs: WebSocket | null = null;

export function connectWatcherWebSocket(jobId?: string): void {
  if (watcherWs) {
    watcherWs.close();
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

  // Add API key to WebSocket URL if configured
  const config = get(apiConfig);
  const apiKeyParam = config.apiKey ? `?api_key=${encodeURIComponent(config.apiKey)}` : '';

  const wsUrl = jobId
    ? `${protocol}//${window.location.host}/ws/watchers/${jobId}${apiKeyParam}`
    : `${protocol}//${window.location.host}/ws/watchers${apiKeyParam}`;

  watcherWs = new WebSocket(wsUrl);
  
  watcherWs.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);

      if (DEBUG_WATCHERS) {
        console.log('[Watchers] WebSocket message:', data);
      }

      if (data.type === 'watcher_event') {
        // Add new event to the store
        watcherEvents.update(events => [data.event, ...events]);

        // Update watcher trigger count
        watchers.update(current =>
          current.map(w =>
            w.id === data.event.watcher_id
              ? { ...w, trigger_count: w.trigger_count + 1 }
              : w
          )
        );
      } else if (data.type === 'watcher_state_change') {
        if (!data.state) {
          console.error('[Watchers] WebSocket watcher_state_change with undefined state:', data);
          return;
        }

        // Update watcher state
        watchers.update(current =>
          current.map(w =>
            w.id === data.watcher_id
              ? { ...w, state: data.state }
              : w
          )
        );
      } else if (data.type === 'watcher_update') {
        // Full watcher update from WebSocket
        const validatedWatcher = validateWatcher(data.watcher, 'WebSocket watcher_update');
        if (validatedWatcher) {
          watchers.update(current =>
            current.map(w =>
              w.id === validatedWatcher.id ? validatedWatcher : w
            )
          );
        }
      }
    } catch (error) {
      console.error('[Watchers] Failed to parse WebSocket message:', error);
    }
  };
  
  watcherWs.onerror = (error) => {
    console.error('WebSocket error:', error);
  };
  
  watcherWs.onclose = () => {
    watcherWs = null;
  };
}

export function disconnectWatcherWebSocket(): void {
  if (watcherWs) {
    watcherWs.close();
    watcherWs = null;
  }
}

// Clear all watcher data
export function clearWatcherData(): void {
  watchers.set([]);
  watcherEvents.set([]);
  watcherStats.set(null);
  selectedWatcher.set(null);
  disconnectWatcherWebSocket();
}