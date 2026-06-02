import { Action, ActionPanel, Color, Icon, Keyboard, List, Toast, showToast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { SsyncClient } from "../api/client";
import { formatDate } from "../lib/format";
import { codeBlock, escapeMarkdown, kvTable } from "../lib/markdown";
import type { ConnectionSettings, JobInfo, Watcher, WatcherEvent } from "../types/ssync";

type Props = {
  connection: ConnectionSettings;
  job: JobInfo;
};

export function WatchersView({ connection, job }: Props) {
  const client = useMemo(() => new SsyncClient(connection), [connection]);
  const [watchers, setWatchers] = useState<Watcher[]>([]);
  const [events, setEvents] = useState<WatcherEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setIsLoading(true);
    setError(null);
    try {
      const [watcherPayload, eventPayload] = await Promise.all([client.getWatchers(job), client.getWatcherEvents(job, 100)]);
      setWatchers(watcherPayload.watchers || []);
      setEvents(eventPayload.events || []);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.job_id, job.hostname]);

  async function refresh() {
    await load();
    await showToast({ style: Toast.Style.Success, title: "Watchers refreshed" });
  }

  return (
    <List
      isLoading={isLoading}
      isShowingDetail
      navigationTitle={`Watchers · ${job.job_id} @ ${job.hostname}`}
      searchBarPlaceholder="Search watchers and events"
    >
      {error ? (
        <List.EmptyView
          icon={Icon.Warning}
          title="Failed to load watchers"
          description={error}
          actions={
            <ActionPanel>
              <Action title="Retry" icon={Icon.ArrowClockwise} onAction={refresh} />
            </ActionPanel>
          }
        />
      ) : null}
      {!error && watchers.length === 0 && events.length === 0 ? (
        <List.EmptyView title="No watchers or watcher events" icon={Icon.EyeDisabled} description="This job has no watcher records in ssync." />
      ) : null}
      {watchers.length > 0 ? (
        <List.Section title={`Watchers (${watchers.length})`}>
          {watchers.map((watcher) => (
            <List.Item
              key={`watcher-${watcher.id}`}
              icon={{ source: Icon.Eye, tintColor: watcherStateColor(watcher.state) }}
              title={watcher.name}
              subtitle={`${watcher.state} · ${watcher.trigger_count} trigger${watcher.trigger_count === 1 ? "" : "s"}`}
              accessories={[
                watcher.timer_mode_active ? { tag: { value: "timer", color: Color.Blue } } : {},
                watcher.remaining_resubmits !== undefined ? { text: `${watcher.remaining_resubmits} resubmits left` } : {},
              ]}
              detail={<List.Item.Detail markdown={watcherMarkdown(watcher)} />}
              actions={<WatcherActions watcher={watcher} onRefresh={refresh} />}
            />
          ))}
        </List.Section>
      ) : null}
      {events.length > 0 ? (
        <List.Section title={`Watcher Events (${events.length})`}>
          {events.map((event) => (
            <List.Item
              key={`event-${event.id}`}
              icon={{ source: event.success ? Icon.CheckCircle : Icon.XmarkCircle, tintColor: event.success ? Color.Green : Color.Red }}
              title={`${event.action_type} · ${event.watcher_name}`}
              subtitle={formatDate(event.timestamp)}
              accessories={[{ text: event.success ? "success" : "failed" }]}
              detail={<List.Item.Detail markdown={eventMarkdown(event)} />}
              actions={<EventActions event={event} onRefresh={refresh} />}
            />
          ))}
        </List.Section>
      ) : null}
    </List>
  );
}

function WatcherActions({ watcher, onRefresh }: { watcher: Watcher; onRefresh: () => void }) {
  return (
    <ActionPanel>
      <Action title="Refresh Watchers" icon={Icon.ArrowClockwise} shortcut={Keyboard.Shortcut.Common.Refresh} onAction={onRefresh} />
      <Action.CopyToClipboard title="Copy Pattern" content={watcher.pattern || ""} />
      <Action.CopyToClipboard title="Copy Captured Variables" content={JSON.stringify(watcher.variables || {}, null, 2)} />
      <Action.CopyToClipboard title="Copy Watcher JSON" content={JSON.stringify(watcher, null, 2)} />
    </ActionPanel>
  );
}

function EventActions({ event, onRefresh }: { event: WatcherEvent; onRefresh: () => void }) {
  return (
    <ActionPanel>
      <Action title="Refresh Watchers" icon={Icon.ArrowClockwise} shortcut={Keyboard.Shortcut.Common.Refresh} onAction={onRefresh} />
      <Action.CopyToClipboard title="Copy Matched Text" content={event.matched_text || ""} />
      <Action.CopyToClipboard title="Copy Captured Variables" content={JSON.stringify(event.captured_vars || {}, null, 2)} />
      <Action.CopyToClipboard title="Copy Event JSON" content={JSON.stringify(event, null, 2)} />
    </ActionPanel>
  );
}

function watcherMarkdown(watcher: Watcher): string {
  return [
    `# ${escapeMarkdown(watcher.name)}`,
    "",
    kvTable([
      ["State", watcher.state],
      ["Job", `${watcher.job_id} @ ${watcher.hostname}`],
      ["Created", formatDate(watcher.created_at)],
      ["Last check", formatDate(watcher.last_check)],
      ["Interval", `${watcher.interval_seconds}s`],
      ["Trigger count", watcher.trigger_count],
      ["Failure count", watcher.failure_count],
      ["Timer mode", watcher.timer_mode_enabled ? "enabled" : "disabled"],
      ["Trigger on job end", watcher.trigger_on_job_end ? "yes" : "no"],
      ["Remaining resubmits", watcher.remaining_resubmits],
    ]),
    "",
    "## Pattern",
    "",
    codeBlock(watcher.pattern, "text"),
    "",
    "## Captures",
    "",
    codeBlock(JSON.stringify(watcher.captures || [], null, 2), "json"),
    "",
    "## Captured Variables",
    "",
    codeBlock(JSON.stringify(watcher.variables || {}, null, 2), "json"),
    "",
    "## Actions",
    "",
    codeBlock(JSON.stringify(watcher.actions || [], null, 2), "json"),
  ].join("\n");
}

function eventMarkdown(event: WatcherEvent): string {
  return [
    `# ${escapeMarkdown(event.action_type)} event`,
    "",
    kvTable([
      ["Watcher", event.watcher_name],
      ["Watcher ID", event.watcher_id],
      ["Job", `${event.job_id} @ ${event.hostname}`],
      ["Timestamp", formatDate(event.timestamp)],
      ["Success", event.success ? "yes" : "no"],
      ["Action result", event.action_result],
    ]),
    "",
    "## Matched Text",
    "",
    codeBlock(event.matched_text, "text"),
    "",
    "## Captured Variables",
    "",
    codeBlock(JSON.stringify(event.captured_vars || {}, null, 2), "json"),
  ].join("\n");
}

function watcherStateColor(state: string): Color {
  switch (state) {
    case "active":
      return Color.Green;
    case "paused":
      return Color.Yellow;
    case "failed":
      return Color.Red;
    case "completed":
      return Color.Blue;
    default:
      return Color.SecondaryText;
  }
}
