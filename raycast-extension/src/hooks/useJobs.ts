import { useCallback, useEffect, useRef, useState } from "react";
import { SsyncClient } from "../api/client";
import { getJobCache, saveJobCache, STALE_JOB_CACHE_MS } from "../api/storage";
import { connectionScope } from "../lib/connections";
import type { ConnectionSettings, JobCache } from "../types/ssync";

export function useJobs(connection: ConnectionSettings) {
  const [cache, setCache] = useState<JobCache>();
  const [error, setError] = useState<string>();
  const [isLoading, setLoading] = useState(true);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const current = useRef(connection);
  current.current = connection;
  const scope = connectionScope(connection);
  const refresh = useCallback(
    async (forceRefresh = false): Promise<boolean> => {
      generation.current++;
      controller.current?.abort();
      const request = new AbortController();
      controller.current = request;
      const active = current.current;
      setLoading(true);
      setError(undefined);
      try {
        const responses = await new SsyncClient(
          active,
          request.signal,
        ).getStatus({
          since: active.historyWindow,
          limit: active.jobLimit,
          forceRefresh,
        });
        if (request.signal.aborted) return false;
        const snapshot = { loadedAt: Date.now(), responses };
        setCache(snapshot);
        // A disk-cache failure must not turn a successful API refresh into an error.
        await saveJobCache(active, snapshot).catch(() => undefined);
        return true;
      } catch (failure) {
        if (!request.signal.aborted)
          setError(
            failure instanceof Error ? failure.message : String(failure),
          );
        return false;
      } finally {
        if (!request.signal.aborted) setLoading(false);
      }
    },
    [],
  );
  useEffect(() => {
    let disposed = false;
    const cacheGeneration = ++generation.current;
    const active = current.current;
    setCache(undefined);
    setError(undefined);
    setLoading(true);
    void (async () => {
      try {
        const stored = await getJobCache(active);
        if (disposed || cacheGeneration !== generation.current) return;
        if (stored) setCache(stored);
        if (!stored || Date.now() - stored.loadedAt > STALE_JOB_CACHE_MS)
          await refresh();
        else setLoading(false);
      } catch {
        if (!disposed && cacheGeneration === generation.current)
          await refresh();
      }
    })();
    return () => {
      disposed = true;
      controller.current?.abort();
    };
  }, [scope, refresh]);
  return { cache, error, isLoading, refresh };
}
