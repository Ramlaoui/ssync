import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiConfig } from '../services/api';
import { LaunchEventStream } from './launchStreaming';
import { streamJobOutput } from './streaming';

type EventSourceCall = {
  url: string;
  options?: EventSourceInit;
};

class MockEventSource {
  static calls: EventSourceCall[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string | URL, options?: EventSourceInit) {
    MockEventSource.calls.push({ url: String(url), options });
  }

  close(): void {}
}

describe('realtime auth URLs', () => {
  beforeEach(() => {
    MockEventSource.calls = [];
    vi.stubGlobal('EventSource', MockEventSource);
    apiConfig.set({
      baseURL: '',
      apiKey: 'secret-key',
      authenticated: true,
      authError: null,
    });
  });

  afterEach(() => {
    apiConfig.set({
      baseURL: '',
      apiKey: '',
      authenticated: false,
      authError: null,
    });
    vi.unstubAllGlobals();
  });

  it('does not put the API key in output EventSource URLs', () => {
    streamJobOutput('123', 'cluster', 'stdout', {
      onChunk: vi.fn(),
      onComplete: vi.fn(),
      onError: vi.fn(),
    });

    expect(MockEventSource.calls).toHaveLength(1);
    expect(MockEventSource.calls[0].url).toContain('/api/jobs/123/output/stream');
    expect(MockEventSource.calls[0].url).not.toContain('api_key');
    expect(MockEventSource.calls[0].url).not.toContain('secret-key');
    expect(MockEventSource.calls[0].options).toEqual({ withCredentials: true });
  });

  it('does not put the API key in launch EventSource URLs', () => {
    apiConfig.set({
      baseURL: 'https://ssync.example.com',
      apiKey: 'secret-key',
      authenticated: true,
      authError: null,
    });

    const stream = new LaunchEventStream();
    stream.start('launch 1', vi.fn(), vi.fn());

    expect(MockEventSource.calls).toHaveLength(1);
    expect(MockEventSource.calls[0].url).toBe(
      'https://ssync.example.com/api/launches/launch%201/events',
    );
    expect(MockEventSource.calls[0].url).not.toContain('api_key');
    expect(MockEventSource.calls[0].url).not.toContain('secret-key');
    expect(MockEventSource.calls[0].options).toEqual({ withCredentials: true });
  });
});
