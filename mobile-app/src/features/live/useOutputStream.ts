import { useEffect, useState } from 'react';
import { Buffer } from 'buffer';
import EventSource from 'react-native-sse';

import { buildApiUrl } from '@/src/api/client';
import { useSessionStore } from '@/src/features/session/session-store';

type OutputStreamState = {
  text: string;
  loading: boolean;
  source: 'stream' | 'snapshot';
  error: string | null;
};

export function useOutputStream(jobId: string, host: string, outputType: 'stdout' | 'stderr') {
  const apiKey = useSessionStore((state) => state.apiKey);
  const [state, setState] = useState<OutputStreamState>({
    text: '',
    loading: Boolean(jobId && host),
    source: 'stream',
    error: null,
  });

  useEffect(() => {
    if (!jobId || !host) {
      return;
    }

    setState({ text: '', loading: true, source: 'stream', error: null });
    const query = new URLSearchParams({
      host,
      output_type: outputType,
    });
    if (apiKey) {
      query.set('api_key', apiKey);
    }

    const stream = new EventSource(
      buildApiUrl(`/api/jobs/${encodeURIComponent(jobId)}/output/stream?${query.toString()}`),
    );

    stream.addEventListener('message', (event) => {
      if (!event.data) {
        return;
      }

      try {
        const payload = JSON.parse(event.data as string) as {
          type: string;
          data?: string;
          compressed?: boolean;
          message?: string;
        };

        if (payload.type === 'chunk' && payload.data) {
          if (payload.compressed) {
            setState((current) => ({
              ...current,
              loading: false,
              source: 'snapshot',
            }));
            return;
          }
          const chunk = Buffer.from(payload.data, 'base64').toString('utf8');
          setState((current) => ({
            ...current,
            text: `${current.text}${chunk}`,
            loading: false,
          }));
        } else if (payload.type === 'metadata') {
          setState((current) => ({ ...current, loading: false }));
        } else if (payload.type === 'error') {
          setState((current) => ({
            ...current,
            loading: false,
            source: 'snapshot',
            error: payload.message ?? 'Failed to stream output.',
          }));
          stream.close();
        } else if (payload.type === 'complete') {
          setState((current) => ({ ...current, loading: false }));
          stream.close();
        }
      } catch {
        setState((current) => ({
          ...current,
          loading: false,
          source: 'snapshot',
          error: 'Failed to parse the output stream.',
        }));
        stream.close();
      }
    });

    stream.addEventListener('error', () => {
      setState((current) => ({
        ...current,
        loading: false,
        source: 'snapshot',
        error: current.text ? null : 'Live output is unavailable right now.',
      }));
      stream.close();
    });

    return () => stream.close();
  }, [apiKey, host, jobId, outputType]);

  return state;
}
