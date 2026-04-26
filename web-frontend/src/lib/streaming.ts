import { apiConfig } from '../services/api';
import { get } from 'svelte/store';

export interface OutputStreamMetadata {
  type: 'metadata';
  output_type: 'stdout' | 'stderr';
  job_id: string;
  host: string;
  original_size?: number;
  truncated?: boolean;
  source?: string;
}

export interface OutputStreamChunk {
  type: 'chunk';
  index: number;
  data: string;
  compressed: boolean;
}

export interface OutputStreamTruncationNotice {
  type: 'truncation_notice';
  original_size: number;
}

export interface OutputStreamHandlers {
  onMetadata?: (metadata: OutputStreamMetadata) => void;
  onChunk: (chunk: string) => void;
  onComplete: () => void;
  onError: (error: string) => void;
  onTruncationNotice?: (notice: OutputStreamTruncationNotice) => void;
}

export class OutputStreamSession {
  private eventSource: EventSource | null = null;
  private readonly handlers: OutputStreamHandlers;

  constructor(handlers: OutputStreamHandlers) {
    this.handlers = handlers;
  }

  start(url: string): void {
    this.close();

    const config = get(apiConfig);
    const streamUrl = new URL(url, window.location.origin);
    if (config.apiKey) {
      streamUrl.searchParams.set('api_key', config.apiKey);
    }

    this.eventSource = new EventSource(streamUrl.toString());
    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as
          | OutputStreamMetadata
          | OutputStreamChunk
          | OutputStreamTruncationNotice
          | { type: 'complete' }
          | { type: 'error'; message?: string };

        if (data.type === 'metadata') {
          this.handlers.onMetadata?.(data);
          return;
        }

        if (data.type === 'chunk') {
          this.handlers.onChunk(data.data || '');
          return;
        }

        if (data.type === 'truncation_notice') {
          this.handlers.onTruncationNotice?.(data);
          return;
        }

        if (data.type === 'complete') {
          this.handlers.onComplete();
          this.close();
          return;
        }

        if (data.type === 'error') {
          this.handlers.onError(data.message || 'Unknown error');
          this.close();
        }
      } catch (error) {
        console.error('Error parsing stream data:', error);
        this.handlers.onError('Failed to parse stream data');
        this.close();
      }
    };

    this.eventSource.onerror = () => {
      this.handlers.onError('Connection lost');
      this.close();
    };
  }

  close(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}

export function streamJobOutput(
  jobId: string,
  hostname: string,
  outputType: 'stdout' | 'stderr',
  handlers: OutputStreamHandlers,
  maxInitialBytes: number = 512 * 1024,
): OutputStreamSession {
  const baseUrl = import.meta.env.VITE_API_URL || '';
  const url =
    `${baseUrl}/api/jobs/${encodeURIComponent(jobId)}/output/stream` +
    `?host=${encodeURIComponent(hostname)}` +
    `&output_type=${outputType}` +
    `&max_initial_bytes=${maxInitialBytes}`;

  const session = new OutputStreamSession(handlers);
  session.start(url);
  return session;
}
