import { Action, ActionPanel, Detail, Icon, List } from "@raycast/api";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { getConnection, setActiveConnection } from "../api/storage";
import { escapeMarkdown } from "../lib/markdown";
import type { ConnectionSettings } from "../types/ssync";
import { ConnectionForm } from "./ConnectionForm";

export function ConnectionGate({
  children,
  connectionId,
}: {
  children: (
    connection: ConnectionSettings,
    reload: () => Promise<void>,
  ) => ReactNode;
  connectionId?: string;
}) {
  const [connection, setConnection] = useState<ConnectionSettings>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const load = useCallback(async (id?: string) => {
    setLoading(true);
    try {
      const saved = await getConnection(id);
      if (id && !saved)
        throw new Error(
          "This job belongs to a connection that has been removed.",
        );
      setConnection(saved);
      setError(undefined);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load(connectionId);
  }, [connectionId, load]);
  if (loading) return <List isLoading navigationTitle="ssync" />;
  if (error)
    return (
      <Detail
        markdown={"# Connection unavailable\n\n" + escapeMarkdown(error)}
        actions={
          <ActionPanel>
            <Action
              title="Retry"
              icon={Icon.ArrowClockwise}
              onAction={() => load(connectionId)}
            />
          </ActionPanel>
        }
      />
    );
  if (!connection)
    return (
      <ConnectionForm
        onConfigured={async (saved) => {
          await setActiveConnection(saved.id);
          setConnection(saved);
        }}
      />
    );
  return children(connection, () => load());
}
