import { useCallback, useEffect, useRef, useState } from "react";

// One owner per request: switching scope or unmounting cancels the old request.
export function useResource<T>(
  key: string,
  loader: (signal: AbortSignal) => Promise<T>,
  initial?: T,
) {
  const currentLoader = useRef(loader);
  currentLoader.current = loader;
  const controller = useRef<AbortController | null>(null);
  const [data, setData] = useState<T | undefined>(initial);
  const [error, setError] = useState<string>();
  const [isLoading, setLoading] = useState(true);
  const refresh = useCallback(async (): Promise<boolean> => {
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setLoading(true);
    setError(undefined);
    try {
      const result = await currentLoader.current(request.signal);
      if (request.signal.aborted) return false;
      setData(result);
      return true;
    } catch (failure) {
      if (!request.signal.aborted)
        setError(failure instanceof Error ? failure.message : String(failure));
      return false;
    } finally {
      if (!request.signal.aborted) setLoading(false);
    }
  }, []);
  useEffect(() => {
    setData(initial);
    void refresh();
    return () => controller.current?.abort();
    // Initial data is a snapshot, not a reason to re-fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, refresh]);
  return { data, error, isLoading, refresh, setData };
}
