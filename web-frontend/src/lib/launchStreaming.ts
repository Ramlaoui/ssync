import { get } from 'svelte/store';
import { api, apiConfig } from '../services/api';
import type { LaunchEvent, LaunchStatusResponse } from '../types/api';

function buildLaunchStreamUrl(launchId: string): string {
  const config = get(apiConfig);
  const normalizedBase = (config.baseURL || '').replace(/\/$/, '');
  const apiBase = normalizedBase.endsWith('/api')
    ? normalizedBase
    : `${normalizedBase}/api`;
  const rawUrl = `${apiBase}/launches/${encodeURIComponent(launchId)}/events`;
  const url = new URL(rawUrl, window.location.origin);

  if (config.apiKey) {
    url.searchParams.set('api_key', config.apiKey);
  }

  return url.toString();
}

export async function fetchLaunchStatus(launchId: string): Promise<LaunchStatusResponse> {
  const response = await api.get<LaunchStatusResponse>(
    `/api/launches/${encodeURIComponent(launchId)}`,
  );
  return response.data;
}

export class LaunchEventStream {
  private eventSource: EventSource | null = null;

  start(launchId: string, onEvent: (event: LaunchEvent) => void, onError: (error: string) => void): void {
    this.close();

    this.eventSource = new EventSource(buildLaunchStreamUrl(launchId));

    this.eventSource.onmessage = (message) => {
      try {
        const payload = JSON.parse(message.data) as LaunchEvent;
        onEvent(payload);
      } catch (error) {
        console.error('Failed to parse launch stream payload:', error);
      }
    };

    this.eventSource.onerror = () => {
      onError('Launch progress stream disconnected');
      this.close();
    };
  }

  close(): void {
    if (!this.eventSource) {
      return;
    }

    this.eventSource.close();
    this.eventSource = null;
  }
}
