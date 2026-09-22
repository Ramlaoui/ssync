import {
  Action,
  ActionPanel,
  Alert,
  Color,
  Form,
  Icon,
  Keyboard,
  List,
  Toast,
  confirmAlert,
  showToast,
  useNavigation,
} from "@raycast/api";
import { useMemo, useRef, useState } from "react";
import { SsyncClient } from "../api/client";
import { useResource } from "../hooks/useResource";
import { connectionScope } from "../lib/connections";
import { jobKey } from "../lib/jobs";
import { relay } from "../lib/design";
import { formatDate, metadataText } from "../lib/format";
import { codeBlock, escapeMarkdown } from "../lib/markdown";
import type {
  ConnectionSettings,
  JobInfo,
  Watcher,
  WatcherAction,
  WatcherEvent,
  WatcherUpdate,
} from "../types/ssync";

export function WatchersView({
  connection,
  job,
}: {
  connection: ConnectionSettings;
  job?: JobInfo;
}) {
  const [view, setView] = useState("all");
  const resource = useResource(
    "watchers:" + connectionScope(connection) + (job ? jobKey(job) : ""),
    async (signal) => {
      const client = new SsyncClient(connection, signal);
      const [rules, activity] = await Promise.allSettled([
        job ? client.getWatchers(job) : client.getAllWatchers(),
        client.getWatcherEvents({ job, limit: 100 }),
      ]);
      if (rules.status === "rejected" && activity.status === "rejected")
        throw rules.reason;
      return {
        watchers: rules.status === "fulfilled" ? rules.value.watchers : [],
        events: activity.status === "fulfilled" ? activity.value.events : [],
        warning:
          rules.status === "rejected"
            ? "Watcher rules could not be refreshed."
            : activity.status === "rejected"
              ? "Watcher events could not be refreshed."
              : undefined,
      };
    },
  );
  async function refresh() {
    const ok = await resource.refresh();
    if (!ok)
      await showToast({
        style: Toast.Style.Failure,
        title: "Could not refresh watchers",
      });
  }
  const watchers = (resource.data?.watchers || []).filter(
    (watcher) =>
      view === "all" ||
      view === "events" ||
      view === "failed-events" ||
      (view === "attention"
        ? watcher.state === "failed" || (watcher.failure_count || 0) > 0
        : watcher.state === view),
  );
  const events = (resource.data?.events || []).filter(
    (event) => view !== "failed-events" || !event.success,
  );
  const showEvents = view === "events" || view === "failed-events";
  const actions = (
    <ActionPanel>
      {job ? (
        <Action.Push
          title="Create Watcher"
          icon={Icon.Plus}
          shortcut={Keyboard.Shortcut.Common.New}
          target={
            <WatcherEditForm
              connection={connection}
              watcher={newWatcher(job)}
              isNew
              job={job}
              onSaved={refresh}
            />
          }
        />
      ) : null}
      <Action
        title="Refresh Watchers"
        icon={Icon.ArrowClockwise}
        shortcut={Keyboard.Shortcut.Common.Refresh}
        onAction={refresh}
      />
    </ActionPanel>
  );
  const warning = resource.error || resource.data?.warning;
  return (
    <List
      isLoading={resource.isLoading}
      isShowingDetail
      navigationTitle={
        job
          ? "Watchers · " + job.job_id + " · " + job.hostname
          : "Watchers · " + connection.name
      }
      searchBarPlaceholder="Find rules, jobs, hosts, or actions…"
      actions={actions}
      searchBarAccessory={
        <List.Dropdown tooltip="Watcher View" value={view} onChange={setView}>
          {[
            ["all", "All Watchers"],
            ["active", "Active"],
            ["paused", "Paused"],
            ["attention", "Needs Attention"],
            ["events", "Recent Events"],
            ["failed-events", "Failed Events"],
          ].map(([value, title]) => (
            <List.Dropdown.Item key={value} value={value} title={title} />
          ))}
        </List.Dropdown>
      }
    >
      <List.EmptyView
        title={
          warning
            ? "Watchers unavailable"
            : showEvents
              ? "No matching events"
              : "No matching watchers"
        }
        description={
          warning ||
          (job
            ? "Create a watcher for this job."
            : "Open a job to attach a watcher.")
        }
        icon={Icon.Eye}
        actions={actions}
      />
      {warning && resource.data ? (
        <List.Item
          id="watcher-warning"
          title="Some data could not be refreshed"
          icon={{ source: Icon.Warning, tintColor: relay.warning }}
          detail={<List.Item.Detail markdown={escapeMarkdown(warning)} />}
          actions={actions}
        />
      ) : null}
      {!showEvents
        ? watchers.map((watcher) => (
            <List.Item
              key={"watcher-" + watcher.id}
              id={"watcher-" + watcher.id}
              icon={{
                source: watcher.state === "paused" ? Icon.Pause : Icon.Eye,
                tintColor: watcherStateColor(watcher.state),
              }}
              title={watcher.name}
              subtitle={watcher.hostname + " · #" + watcher.job_id}
              keywords={[
                watcher.state,
                watcher.pattern || "",
                watcher.hostname,
                watcher.job_id,
                ...watcher.actions.map((action) => action.type),
              ]}
              detail={
                <List.Item.Detail
                  markdown={watcherMarkdown(watcher)}
                  metadata={<WatcherMetadata watcher={watcher} />}
                />
              }
              actions={
                <WatcherActions
                  connection={connection}
                  job={
                    job || {
                      job_id: watcher.job_id,
                      hostname: watcher.hostname,
                      name: watcher.job_name || watcher.job_id,
                      state: "UNKNOWN",
                    }
                  }
                  watcher={watcher}
                  events={events.filter(
                    (event) =>
                      event.watcher_id === watcher.id &&
                      event.hostname === watcher.hostname,
                  )}
                  onRefresh={refresh}
                />
              }
            />
          ))
        : events.map((event) => (
            <List.Item
              key={"event-" + event.id}
              id={"event-" + event.id}
              icon={{
                source: event.success ? Icon.CheckCircle : Icon.XmarkCircle,
                tintColor: event.success ? relay.success : relay.danger,
              }}
              title={event.watcher_name + " · " + event.action_type}
              subtitle={formatDate(event.timestamp)}
              keywords={[
                event.hostname,
                event.job_id,
                event.matched_text || "",
                event.action_result || "",
              ]}
              detail={
                <List.Item.Detail
                  markdown={eventMarkdown(event)}
                  metadata={<EventMetadata event={event} />}
                />
              }
              actions={<EventActions event={event} onRefresh={refresh} />}
            />
          ))}
    </List>
  );
}

function newWatcher(job: JobInfo): Watcher {
  return {
    id: 0,
    job_id: job.job_id,
    hostname: job.hostname,
    name: "Job result",
    pattern: "",
    interval_seconds: 30,
    captures: [],
    actions: [{ type: "log_event", config: { message: "Job finished" } }],
    state: "active",
    trigger_count: 0,
    trigger_on_job_end: true,
    trigger_job_states: ["CD", "F", "TO", "CA"],
  };
}

function WatcherActions({
  connection,
  job,
  watcher,
  events,
  onRefresh,
}: {
  connection: ConnectionSettings;
  job: JobInfo;
  watcher: Watcher;
  events: WatcherEvent[];
  onRefresh: () => Promise<void>;
}) {
  const client = new SsyncClient(connection);
  const canTrigger = watcher.state === "active" || watcher.state === "static";
  const canPause = watcher.state === "active";
  const canResume = watcher.state === "paused";
  const busy = useRef(false);
  async function run(action: () => Promise<void>) {
    if (busy.current) return;
    busy.current = true;
    try {
      await action();
    } finally {
      busy.current = false;
    }
  }

  async function triggerWatcher() {
    if (
      !(await confirmAlert({
        title: "Trigger " + watcher.name + "?",
        message:
          "This evaluates the watcher and can execute its configured actions, including watcher resubmission.",
        primaryAction: { title: "Trigger Watcher" },
      }))
    )
      return;
    const toast = await showToast({
      style: Toast.Style.Animated,
      title: "Triggering watcher",
    });
    try {
      const result = await client.triggerWatcher(watcher);
      toast.style = result.success ? Toast.Style.Success : Toast.Style.Failure;
      toast.title =
        result.matches || result.timer_mode
          ? "Watcher triggered"
          : "No watcher match";
      toast.message = result.message;
      await onRefresh();
    } catch (error) {
      toast.style = Toast.Style.Failure;
      toast.title = "Failed to trigger watcher";
      toast.message = error instanceof Error ? error.message : String(error);
    }
  }

  async function cancelWatcher() {
    const toast = await showToast({
      style: Toast.Style.Animated,
      title: "Pausing watcher",
    });
    try {
      await client.pauseWatcher(watcher);
      toast.style = Toast.Style.Success;
      toast.title = "Watcher paused";
      await onRefresh();
    } catch (error) {
      toast.style = Toast.Style.Failure;
      toast.title = "Could not pause watcher";
      toast.message = error instanceof Error ? error.message : String(error);
    }
  }

  async function resumeWatcher() {
    const toast = await showToast({
      style: Toast.Style.Animated,
      title: "Resuming watcher",
    });
    try {
      await client.resumeWatcher(watcher);
      toast.style = Toast.Style.Success;
      toast.title = "Watcher resumed";
      await onRefresh();
    } catch (error) {
      toast.style = Toast.Style.Failure;
      toast.title = "Failed to resume watcher";
      toast.message = error instanceof Error ? error.message : String(error);
    }
  }

  async function deleteWatcher() {
    const confirmed = await confirmAlert({
      title: `Delete ${watcher.name}?`,
      message: "This permanently removes the watcher and its recorded events.",
      primaryAction: {
        title: "Delete Watcher",
        style: Alert.ActionStyle.Destructive,
      },
    });
    if (!confirmed) return;

    const toast = await showToast({
      style: Toast.Style.Animated,
      title: "Deleting watcher",
    });
    try {
      await client.deleteWatcher(watcher);
      toast.style = Toast.Style.Success;
      toast.title = "Watcher deleted";
      await onRefresh();
    } catch (error) {
      toast.style = Toast.Style.Failure;
      toast.title = "Failed to delete watcher";
      toast.message = error instanceof Error ? error.message : String(error);
    }
  }

  return (
    <ActionPanel>
      <ActionPanel.Section>
        <Action.Push
          title="View Watcher Events & Logs"
          icon={Icon.List}
          target={
            <WatcherEventsView
              connection={connection}
              job={job}
              watcher={watcher}
              initialEvents={events}
            />
          }
        />
        <Action.Push
          title="Edit Watcher"
          shortcut={Keyboard.Shortcut.Common.Edit}
          icon={Icon.Pencil}
          target={
            <WatcherEditForm
              connection={connection}
              watcher={watcher}
              onSaved={onRefresh}
            />
          }
        />
        <Action.Push
          title="Create Watcher"
          icon={Icon.Plus}
          shortcut={Keyboard.Shortcut.Common.New}
          target={
            <WatcherEditForm
              connection={connection}
              watcher={newWatcher(job)}
              isNew
              job={job}
              onSaved={onRefresh}
            />
          }
        />
      </ActionPanel.Section>
      <ActionPanel.Section>
        {canTrigger ? (
          <Action
            title="Trigger Watcher"
            icon={Icon.Bolt}
            onAction={() => run(triggerWatcher)}
          />
        ) : null}
        {canPause ? (
          <Action
            title="Pause Watcher"
            icon={Icon.Pause}
            onAction={() => run(cancelWatcher)}
          />
        ) : null}
        {canResume ? (
          <Action
            title="Resume Watcher"
            icon={Icon.Play}
            onAction={() => run(resumeWatcher)}
          />
        ) : null}
        <Action
          title="Refresh Watchers"
          icon={Icon.ArrowClockwise}
          shortcut={Keyboard.Shortcut.Common.Refresh}
          onAction={onRefresh}
        />
      </ActionPanel.Section>
      <ActionPanel.Section>
        <Action
          title="Delete Watcher"
          icon={Icon.Trash}
          style={Action.Style.Destructive}
          onAction={() => run(deleteWatcher)}
        />
        <Action.CopyToClipboard
          title="Copy Pattern"
          content={watcher.pattern || ""}
        />
        <Action.CopyToClipboard
          title="Copy Captured Variables"
          content={JSON.stringify(watcher.variables || {}, null, 2)}
        />
        <Action.CopyToClipboard
          title="Copy Watcher JSON"
          content={JSON.stringify(watcher, null, 2)}
        />
      </ActionPanel.Section>
    </ActionPanel>
  );
}

function EventActions({
  event,
  onRefresh,
}: {
  event: WatcherEvent;
  onRefresh: () => void;
}) {
  return (
    <ActionPanel>
      <Action
        title="Refresh Watchers"
        icon={Icon.ArrowClockwise}
        shortcut={Keyboard.Shortcut.Common.Refresh}
        onAction={onRefresh}
      />
      <Action.CopyToClipboard
        title="Copy Matched Text"
        content={event.matched_text || ""}
      />
      {event.action_result ? (
        <Action.CopyToClipboard
          title="Copy Event Logs"
          content={event.action_result}
        />
      ) : null}
      <Action.CopyToClipboard
        title="Copy Captured Variables"
        content={JSON.stringify(event.captured_vars || {}, null, 2)}
      />
      <Action.CopyToClipboard
        title="Copy Event JSON"
        content={JSON.stringify(event, null, 2)}
      />
    </ActionPanel>
  );
}

function WatcherEventsView({
  connection,
  job,
  watcher,
  initialEvents,
}: {
  connection: ConnectionSettings;
  job: JobInfo;
  watcher: Watcher;
  initialEvents: WatcherEvent[];
}) {
  const resource = useResource(
    "watcher-events:" +
      connectionScope(connection) +
      ":" +
      watcher.id +
      jobKey(job),
    (signal) =>
      new SsyncClient(connection, signal).getWatcherEvents({
        job,
        watcherId: watcher.id,
        limit: 300,
      }),
    { events: initialEvents, count: initialEvents.length },
  );
  const events = resource.data?.events || [];
  const { isLoading, error } = resource;
  async function refresh() {
    if (!(await resource.refresh()))
      await showToast({
        style: Toast.Style.Failure,
        title: "Could not refresh events",
      });
  }

  return (
    <List
      isLoading={isLoading}
      isShowingDetail
      navigationTitle={`Events · ${watcher.name}`}
      searchBarPlaceholder="Search watcher events and logs"
    >
      {error ? (
        <List.EmptyView
          icon={Icon.Warning}
          title="Failed to load watcher events"
          description={error}
          actions={
            <ActionPanel>
              <Action
                title="Retry"
                icon={Icon.ArrowClockwise}
                onAction={refresh}
              />
            </ActionPanel>
          }
        />
      ) : null}
      {!error && events.length === 0 ? (
        <List.EmptyView
          title="No watcher events"
          icon={Icon.List}
          description="This watcher has not recorded events yet."
          actions={
            <ActionPanel>
              <Action
                title="Refresh Events"
                icon={Icon.ArrowClockwise}
                onAction={refresh}
              />
            </ActionPanel>
          }
        />
      ) : null}
      {events.map((event) => (
        <List.Item
          key={`watcher-event-${event.id}`}
          icon={{
            source: event.success ? Icon.CheckCircle : Icon.XmarkCircle,
            tintColor: event.success ? relay.success : relay.danger,
          }}
          title={event.action_type}
          subtitle={formatDate(event.timestamp)}
          accessories={[
            { text: event.success ? "success" : "failed" },
            event.action_result
              ? { tag: { value: "logs", color: relay.accent } }
              : {},
          ]}
          detail={
            <List.Item.Detail
              markdown={eventMarkdown(event)}
              metadata={<EventMetadata event={event} />}
            />
          }
          actions={<EventActions event={event} onRefresh={refresh} />}
        />
      ))}
    </List>
  );
}

type WatcherEditValues = {
  name: string;
  pattern: string;
  intervalSeconds: string;
  captures: string;
  condition: string;
  actionsJson: string;
  actionMessage?: string;
  timerModeEnabled: boolean;
  timerIntervalSeconds: string;
  triggerOnJobEnd: boolean;
  triggerJobStates: string;
};

function WatcherEditForm({
  connection,
  watcher,
  onSaved,
  isNew = false,
  job,
}: {
  connection: ConnectionSettings;
  watcher: Watcher;
  onSaved: () => Promise<void>;
  isNew?: boolean;
  job?: JobInfo;
}) {
  const client = useMemo(() => new SsyncClient(connection), [connection]);
  const { pop } = useNavigation();
  const [isSaving, setIsSaving] = useState(false);
  const busy = useRef(false);
  const [actionPreset, setActionPreset] = useState(
    isNew ? "log_event" : "custom",
  );

  async function submit(values: WatcherEditValues) {
    if (busy.current) return;
    const name = values.name.trim();
    const pattern = values.pattern.trim();
    const intervalSeconds = Number(values.intervalSeconds);
    const timerIntervalSeconds = Number(values.timerIntervalSeconds);

    if (!name) {
      await showToast({
        style: Toast.Style.Failure,
        title: "Watcher name is required",
      });
      return;
    }
    if (!pattern && !values.triggerOnJobEnd) {
      await showToast({
        style: Toast.Style.Failure,
        title: "Pattern or job-end trigger is required",
      });
      return;
    }
    if (
      !Number.isInteger(intervalSeconds) ||
      intervalSeconds < 1 ||
      intervalSeconds > 3600
    ) {
      await showToast({
        style: Toast.Style.Failure,
        title: "Interval must be between 1 and 3600 seconds",
      });
      return;
    }
    if (
      values.timerModeEnabled &&
      (!Number.isInteger(timerIntervalSeconds) ||
        timerIntervalSeconds < 1 ||
        timerIntervalSeconds > 3600)
    ) {
      await showToast({
        style: Toast.Style.Failure,
        title: "Timer interval must be between 1 and 3600 seconds",
      });
      return;
    }

    let actions: WatcherAction[];
    try {
      const parsed = JSON.parse(values.actionsJson || "[]") as unknown;
      if (!Array.isArray(parsed))
        throw new Error("Actions JSON must be an array");
      actions =
        actionPreset === "custom"
          ? parsed.map(normalizeAction)
          : [
              {
                type: actionPreset,
                config:
                  actionPreset === "log_event"
                    ? {
                        message: values.actionMessage?.trim() || "Job finished",
                      }
                    : {},
              },
            ];
    } catch (error) {
      await showToast({
        style: Toast.Style.Failure,
        title: "Invalid actions JSON",
        message: error instanceof Error ? error.message : String(error),
      });
      return;
    }

    const update: WatcherUpdate = {
      name,
      pattern,
      interval_seconds: intervalSeconds,
      capture_groups: splitList(values.captures),
      condition: values.condition.trim() || null,
      actions,
      timer_mode_enabled: values.timerModeEnabled,
      timer_interval_seconds: values.timerModeEnabled
        ? timerIntervalSeconds
        : undefined,
      trigger_on_job_end: values.triggerOnJobEnd,
      trigger_job_states: splitList(values.triggerJobStates),
    };

    busy.current = true;
    setIsSaving(true);
    const toast = await showToast({
      style: Toast.Style.Animated,
      title: "Saving watcher",
    });
    try {
      if (isNew && job) await client.createWatcher(job, update);
      else await client.updateWatcher(watcher, update);
      toast.style = Toast.Style.Success;
      toast.title = isNew ? "Watcher created" : "Watcher updated";
      await onSaved();
      pop();
    } catch (error) {
      toast.style = Toast.Style.Failure;
      toast.title = "Failed to update watcher";
      toast.message = error instanceof Error ? error.message : String(error);
    } finally {
      busy.current = false;
      setIsSaving(false);
    }
  }

  return (
    <Form
      isLoading={isSaving}
      navigationTitle={isNew ? "Create Watcher" : `Edit · ${watcher.name}`}
      actions={
        <ActionPanel>
          <Action.SubmitForm
            title={isNew ? "Create Watcher" : "Save Watcher"}
            icon={Icon.CheckCircle}
            onSubmit={submit}
          />
        </ActionPanel>
      }
    >
      <Form.TextField id="name" title="Name" defaultValue={watcher.name} />
      <Form.TextArea
        id="pattern"
        title="Pattern"
        defaultValue={watcher.pattern || ""}
      />
      <Form.TextField
        id="intervalSeconds"
        title="Check Interval Seconds"
        defaultValue={String(watcher.interval_seconds || 30)}
      />
      <Form.TextField
        id="captures"
        title="Captures"
        defaultValue={(watcher.captures || []).join(", ")}
      />
      <Form.TextField
        id="condition"
        title="Condition"
        defaultValue={watcher.condition || ""}
      />
      <Form.Separator />
      <Form.Dropdown
        id="actionPreset"
        title="Then"
        value={actionPreset}
        onChange={setActionPreset}
      >
        <Form.Dropdown.Item value="log_event" title="Record an Event" />
        <Form.Dropdown.Item value="cancel_job" title="Cancel This Job" />
        <Form.Dropdown.Item value="custom" title="Custom Actions" />
      </Form.Dropdown>
      {actionPreset === "log_event" ? (
        <Form.TextField
          id="actionMessage"
          title="Event Message"
          defaultValue="Job finished"
        />
      ) : null}
      {actionPreset === "cancel_job" ? (
        <Form.Description text="Cancels this job automatically when the rule matches." />
      ) : null}
      {actionPreset === "custom" ? (
        <Form.TextArea
          id="actionsJson"
          title="Actions JSON"
          defaultValue={JSON.stringify(watcher.actions || [], null, 2)}
          info="Keep existing actions, including watcher resubmission, notifications, and captured variables."
        />
      ) : null}
      <Form.Separator />
      <Form.Checkbox
        id="timerModeEnabled"
        label="Enable timer mode"
        defaultValue={Boolean(watcher.timer_mode_enabled)}
      />
      <Form.TextField
        id="timerIntervalSeconds"
        title="Timer Interval Seconds"
        defaultValue={String(watcher.timer_interval_seconds || 30)}
      />
      <Form.Checkbox
        id="triggerOnJobEnd"
        label="Trigger on job end"
        defaultValue={Boolean(watcher.trigger_on_job_end)}
      />
      <Form.TextField
        id="triggerJobStates"
        title="Job-End States"
        defaultValue={(watcher.trigger_job_states || []).join(", ")}
      />
    </Form>
  );
}

function WatcherMetadata({ watcher }: { watcher: Watcher }) {
  return (
    <List.Item.Detail.Metadata>
      <List.Item.Detail.Metadata.Label
        title="State"
        text={watcher.state}
        icon={{ source: Icon.Eye, tintColor: watcherStateColor(watcher.state) }}
      />
      <List.Item.Detail.Metadata.Label
        title="Job"
        text={`${watcher.job_id} @ ${watcher.hostname}`}
      />
      <List.Item.Detail.Metadata.Separator />
      <List.Item.Detail.Metadata.Label
        title="Created"
        text={formatDate(watcher.created_at)}
      />
      <List.Item.Detail.Metadata.Label
        title="Last Check"
        text={formatDate(watcher.last_check)}
      />
      <List.Item.Detail.Metadata.Label
        title="Interval"
        text={`${watcher.interval_seconds}s`}
      />
      <List.Item.Detail.Metadata.Label
        title="Last Position"
        text={metadataText(watcher.last_position)}
      />
      <List.Item.Detail.Metadata.Separator />
      <List.Item.Detail.Metadata.Label
        title="Triggers"
        text={metadataText(watcher.trigger_count)}
      />
      <List.Item.Detail.Metadata.Label
        title="Failures"
        text={metadataText(watcher.failure_count)}
      />
      <List.Item.Detail.Metadata.Label
        title="Max Failures"
        text={metadataText(watcher.max_failures)}
      />
      <List.Item.Detail.Metadata.Separator />
      <List.Item.Detail.Metadata.Label
        title="Timer Mode"
        text={metadataText(watcher.timer_mode_enabled)}
      />
      <List.Item.Detail.Metadata.Label
        title="Timer Active"
        text={metadataText(watcher.timer_mode_active)}
      />
      <List.Item.Detail.Metadata.Label
        title="Trigger On Job End"
        text={metadataText(watcher.trigger_on_job_end)}
      />
      <List.Item.Detail.Metadata.Label
        title="Resubmits Left"
        text={metadataText(watcher.remaining_resubmits)}
      />
    </List.Item.Detail.Metadata>
  );
}

function EventMetadata({ event }: { event: WatcherEvent }) {
  return (
    <List.Item.Detail.Metadata>
      <List.Item.Detail.Metadata.Label
        title="Result"
        text={event.success ? "success" : "failed"}
        icon={{
          source: event.success ? Icon.CheckCircle : Icon.XmarkCircle,
          tintColor: event.success ? relay.success : relay.danger,
        }}
      />
      <List.Item.Detail.Metadata.Label
        title="Action"
        text={event.action_type}
      />
      <List.Item.Detail.Metadata.Label
        title="Watcher"
        text={event.watcher_name}
      />
      <List.Item.Detail.Metadata.Label
        title="Watcher ID"
        text={metadataText(event.watcher_id)}
      />
      <List.Item.Detail.Metadata.Separator />
      <List.Item.Detail.Metadata.Label
        title="Job"
        text={`${event.job_id} @ ${event.hostname}`}
      />
      <List.Item.Detail.Metadata.Label
        title="Timestamp"
        text={formatDate(event.timestamp)}
      />
      <List.Item.Detail.Metadata.Label
        title="Action Result"
        text={metadataText(event.action_result)}
      />
    </List.Item.Detail.Metadata>
  );
}

function watcherMarkdown(watcher: Watcher): string {
  const triggers = [];
  if (watcher.pattern)
    triggers.push("Output matches " + codeBlock(watcher.pattern));
  if (watcher.trigger_on_job_end)
    triggers.push(
      "Job ends" +
        (watcher.trigger_job_states?.length
          ? ": " + watcher.trigger_job_states.join(", ")
          : ""),
    );
  if (watcher.timer_mode_enabled)
    triggers.push(
      "Timer: " +
        (watcher.timer_interval_seconds || watcher.interval_seconds) +
        "s",
    );
  const lines = [
    "# " + escapeMarkdown(watcher.name),
    "",
    "## When",
    "",
    triggers.join("\n\n") || "Manual trigger",
  ];
  if (watcher.condition)
    lines.push("", "## If", "", codeBlock(watcher.condition));
  lines.push(
    "",
    "## Then",
    "",
    watcher.actions.length
      ? watcher.actions.map(actionMarkdown).join("\n\n")
      : "No actions configured.",
  );
  if (watcher.captures?.length)
    lines.push("", "## Captures", "", stringList(watcher.captures));
  if (Object.keys(watcher.variables || {}).length)
    lines.push("", "## Captured Variables", "", objectList(watcher.variables));
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
    "",
    "## Event Logs",
    "",
    event.action_result
      ? codeBlock(event.action_result, "text")
      : "_No event logs recorded._",
  ].join("\n");
}

function stringList(values?: string[]): string {
  if (!values || values.length === 0) return "_No captures configured._";
  return values.map((value) => `- ${escapeMarkdown(value)}`).join("\n");
}

function objectList(values?: Record<string, unknown>): string {
  const entries = Object.entries(values || {});
  if (entries.length === 0) return "_No values captured._";
  return entries
    .map(
      ([key, value]) =>
        `- **${escapeMarkdown(key)}:** ${escapeMarkdown(formatUnknown(value))}`,
    )
    .join("\n");
}

function actionMarkdown(action: WatcherAction, index: number): string {
  const lines = [`### ${index + 1}. ${escapeMarkdown(action.type)}`];
  if (action.condition)
    lines.push("", `**Condition:** ${escapeMarkdown(action.condition)}`);
  if (action.params && Object.keys(action.params).length > 0)
    lines.push("", "**Params**", "", objectList(action.params));
  if (action.config && Object.keys(action.config).length > 0)
    lines.push("", "**Config**", "", objectList(action.config));
  return lines.join("\n");
}

function formatUnknown(value: unknown): string {
  if (value === undefined || value === null || value === "") return "n/a";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return metadataText(value);
  return JSON.stringify(value);
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function normalizeAction(value: unknown): WatcherAction {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Each action must be an object");
  }
  const raw = value as Record<string, unknown>;
  if (typeof raw.type !== "string" || !raw.type.trim()) {
    throw new Error("Each action must include a type");
  }
  const config = raw.config ?? raw.params;
  return {
    type: raw.type.trim(),
    condition:
      typeof raw.condition === "string" && raw.condition.trim()
        ? raw.condition.trim()
        : undefined,
    config:
      isRecord(config) && Object.keys(config).length > 0 ? config : undefined,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function watcherStateColor(state: string): Color.ColorLike {
  switch (state) {
    case "active":
      return relay.running;
    case "paused":
      return relay.warning;
    case "failed":
      return relay.danger;
    case "completed":
      return relay.success;
    default:
      return Color.SecondaryText;
  }
}
