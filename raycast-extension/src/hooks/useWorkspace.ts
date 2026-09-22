import { showToast, Toast } from "@raycast/api";
import { useEffect, useRef, useState } from "react";
import { defaultWorkspace, getWorkspace, saveWorkspace } from "../api/storage";
import type { ConnectionSettings, WorkspaceSettings } from "../types/ssync";

export function useWorkspace(
  connection: ConnectionSettings,
  initialHost?: string,
) {
  const [settings, setSettings] = useState<WorkspaceSettings>({
    ...defaultWorkspace,
    host: initialHost || connection.defaultHost || "",
  });
  const current = useRef(settings);
  const activeConnection = useRef(connection);
  activeConnection.current = connection;
  const loaded = useRef(false);
  const pendingPatch = useRef<Partial<WorkspaceSettings>>({});
  const pendingSave = useRef<Promise<void>>(Promise.resolve());
  const scope = JSON.stringify([
    connection.id,
    connection.apiUrl,
    connection.defaultHost,
    initialHost,
  ]);
  function persist(active: ConnectionSettings, next: WorkspaceSettings) {
    pendingSave.current = pendingSave.current
      .then(() => saveWorkspace(active, next))
      .catch(async () => {
        await showToast({
          style: Toast.Style.Failure,
          title: "Could not save view preferences",
        });
      });
  }
  useEffect(() => {
    let disposed = false;
    loaded.current = false;
    pendingPatch.current = {};
    const active = activeConnection.current;
    const fallback = {
      ...defaultWorkspace,
      host: initialHost || active.defaultHost || "",
    };
    current.current = fallback;
    setSettings(fallback);
    void getWorkspace(active)
      .catch(() => fallback)
      .then((saved) => {
        if (disposed) return;
        const next = {
          ...(initialHost
            ? { ...saved, host: initialHost, view: "all" as const }
            : saved),
          ...pendingPatch.current,
        };
        current.current = next;
        setSettings(next);
        loaded.current = true;
        if (Object.keys(pendingPatch.current).length) persist(active, next);
      });
    return () => {
      disposed = true;
    };
  }, [scope, initialHost]);
  function update(patch: Partial<WorkspaceSettings>) {
    const next = { ...current.current, ...patch };
    current.current = next;
    setSettings(next);
    if (loaded.current) persist(activeConnection.current, next);
    else pendingPatch.current = { ...pendingPatch.current, ...patch };
  }
  return { settings, update };
}
