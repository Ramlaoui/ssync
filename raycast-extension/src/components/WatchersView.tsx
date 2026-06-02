import { Action, ActionPanel, Color, Icon, Keyboard, List, Toast, showToast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { SsyncClient } from "../api/client";
import { formatDate, metadataText } from "../lib/format";
import { codeBlock, escapeMarkdown } from "../lib/markdown";
import type { ConnectionSettings, JobInfo, Watcher, WatcherAction, WatcherEvent } from "../types/ssync";

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
              detail={<List.Item.Detail markdown={watcherMarkdown(watcher)} metadata={<WatcherMetadata watcher={watcher} />} />}
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
              detail={<List.Item.Detail markdown={eventMarkdown(event)} metadata={<EventMetadata event={event} />} />}
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

function WatcherMetadata({ watcher }: { watcher: Watcher }) {
  return (
    <List.Item.Detail.Metadata>
      <List.Item.Detail.Metadata.Label title="State" text={watcher.state} icon={{ source: Icon.Eye, tintColor: watcherStateColor(watcher.state) }} />
      <List.Item.Detail.Metadata.Label title="Job" text={`${watcher.job_id} @ ${watcher.hostname}`} />
      <List.Item.Detail.Metadata.Separator />
      <List.Item.Detail.Metadata.Label title="Created" text={formatDate(watcher.created_at)} />
      <List.Item.Detail.Metadata.Label title="Last Check" text={formatDate(watcher.last_check)} />
      <List.Item.Detail.Metadata.Label title="Interval" text={`${watcher.interval_seconds}s`} />
      <List.Item.Detail.Metadata.Label title="Last Position" text={metadataText(watcher.last_position)} />
      <List.Item.Detail.Metadata.Separator />
      <List.Item.Detail.Metadata.Label title="Triggers" text={metadataText(watcher.trigger_count)} />
      <List.Item.Detail.Metadata.Label title="Failures" text={metadataText(watcher.failure_count)} />
      <List.Item.Detail.Metadata.Label title="Max Failures" text={metadataText(watcher.max_failures)} />
      <List.Item.Detail.Metadata.Separator />
      <List.Item.Detail.Metadata.Label title="Timer Mode" text={metadataText(watcher.timer_mode_enabled)} />
      <List.Item.Detail.Metadata.Label title="Timer Active" text={metadataText(watcher.timer_mode_active)} />
      <List.Item.Detail.Metadata.Label title="Trigger On Job End" text={metadataText(watcher.trigger_on_job_end)} />
      <List.Item.Detail.Metadata.Label title="Resubmits Left" text={metadataText(watcher.remaining_resubmits)} />
    </List.Item.Detail.Metadata>
  );
}

function EventMetadata({ event }: { event: WatcherEvent }) {
  return (
    <List.Item.Detail.Metadata>
      <List.Item.Detail.Metadata.Label
        title="Result"
        text={event.success ? "success" : "failed"}
        icon={{ source: event.success ? Icon.CheckCircle : Icon.XmarkCircle, tintColor: event.success ? Color.Green : Color.Red }}
      />
      <List.Item.Detail.Metadata.Label title="Action" text={event.action_type} />
      <List.Item.Detail.Metadata.Label title="Watcher" text={event.watcher_name} />
      <List.Item.Detail.Metadata.Label title="Watcher ID" text={metadataText(event.watcher_id)} />
      <List.Item.Detail.Metadata.Separator />
      <List.Item.Detail.Metadata.Label title="Job" text={`${event.job_id} @ ${event.hostname}`} />
      <List.Item.Detail.Metadata.Label title="Timestamp" text={formatDate(event.timestamp)} />
      <List.Item.Detail.Metadata.Label title="Action Result" text={metadataText(event.action_result)} />
    </List.Item.Detail.Metadata>
  );
}

function watcherMarkdown(watcher: Watcher): string {
  const lines = [`# ${escapeMarkdown(watcher.name)}`];
  if (watcher.condition) {
    lines.push("", `**Condition:** ${escapeMarkdown(watcher.condition)}`);
  }
  lines.push(
    "",
    "## Pattern",
    "",
    codeBlock(watcher.pattern, "text"),
    "",
    "## Captures",
    "",
    stringList(watcher.captures),
    "",
    "## Captured Variables",
    "",
    objectList(watcher.variables),
    "",
    "## Actions",
    "",
    watcher.actions.length > 0 ? watcher.actions.map(actionMarkdown).join("\n\n") : "_No actions configured._",
  );
  return lines.join("\n");
}

function eventMarkdown(event: WatcherEvent): string {
  return [
    `# ${escapeMarkdown(event.action_type)} event`,
    "",
    "## Matched Text",
    "",
    codeBlock(event.matched_text, "text"),
    "",
    "## Captured Variables",
    "",
    objectList(event.captured_vars),
    ...(event.action_result ? ["", "## Action Result", "", codeBlock(event.action_result, "text")] : []),
  ].join("\n");
}

function stringList(values?: string[]): string {
  if (!values || values.length === 0) return "_No captures configured._";
  return values.map((value) => `- ${escapeMarkdown(value)}`).join("\n");
}

function objectList(values?: Record<string, unknown>): string {
  const entries = Object.entries(values || {});
  if (entries.length === 0) return "_No values captured._";
  return entries.map(([key, value]) => `- **${escapeMarkdown(key)}:** ${escapeMarkdown(formatUnknown(value))}`).join("\n");
}

function actionMarkdown(action: WatcherAction, index: number): string {
  const lines = [`### ${index + 1}. ${escapeMarkdown(action.type)}`];
  if (action.condition) lines.push("", `**Condition:** ${escapeMarkdown(action.condition)}`);
  if (action.params && Object.keys(action.params).length > 0) lines.push("", "**Params**", "", objectList(action.params));
  if (action.config && Object.keys(action.config).length > 0) lines.push("", "**Config**", "", objectList(action.config));
  return lines.join("\n");
}

function formatUnknown(value: unknown): string {
  if (value === undefined || value === null || value === "") return "n/a";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return metadataText(value);
  return JSON.stringify(value);
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
