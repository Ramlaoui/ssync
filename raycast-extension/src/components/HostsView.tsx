import {
  Action,
  ActionPanel,
  Form,
  Icon,
  Keyboard,
  LaunchType,
  List,
  Toast,
  launchCommand,
  showToast,
  useNavigation,
} from "@raycast/api";
import { useRef, useState } from "react";
import { SsyncApiError, SsyncClient } from "../api/client";
import { saveConnection } from "../api/storage";
import { useResource } from "../hooks/useResource";
import { connectionScope } from "../lib/connections";
import { relay } from "../lib/design";
import { formatDate } from "../lib/format";
import { hostDefaultFields, parseHostDefaults } from "../lib/hosts";
import { escapeMarkdown } from "../lib/markdown";
import type {
  ConnectionSettings,
  HostInfo,
  HostSettings,
  JobsLaunchContext,
} from "../types/ssync";
import { ConnectionsView } from "./ConnectionsView";
import { LaunchView } from "./LaunchView";

export function HostsView({
  connection,
  onConnectionChanged,
}: {
  connection: ConnectionSettings;
  onConnectionChanged?: () => Promise<void>;
}) {
  const resource = useResource(
    "hosts:" + connectionScope(connection),
    (signal) => new SsyncClient(connection, signal).getHosts(),
  );
  return (
    <List
      isLoading={resource.isLoading}
      isShowingDetail
      navigationTitle={"Hosts · " + connection.name}
      searchBarPlaceholder="Find a host…"
      actions={
        <ActionPanel>
          <Action
            title="Refresh Hosts"
            icon={Icon.ArrowClockwise}
            shortcut={Keyboard.Shortcut.Common.Refresh}
            onAction={() => void resource.refresh()}
          />
          <Action.Push
            title="Manage Connections"
            icon={Icon.Plug}
            target={<ConnectionsView onChanged={onConnectionChanged} />}
          />
        </ActionPanel>
      }
    >
      <List.EmptyView
        title={resource.error ? "Hosts unavailable" : "No configured hosts"}
        description={
          resource.error || "Add a host to the ssync API server configuration."
        }
        icon={Icon.Desktop}
        actions={
          <ActionPanel>
            <Action
              title="Retry"
              icon={Icon.ArrowClockwise}
              onAction={() => void resource.refresh()}
            />
            <Action.Push
              title="Manage Connections"
              icon={Icon.Plug}
              target={<ConnectionsView onChanged={onConnectionChanged} />}
            />
          </ActionPanel>
        }
      />
      {resource.data?.map((host) => (
        <List.Item
          key={host.hostname}
          id={host.hostname}
          title={host.hostname}
          subtitle={host.slurm_defaults?.partition || undefined}
          icon={{ source: Icon.Desktop, tintColor: relay.accent }}
          detail={
            <List.Item.Detail
              markdown={"# " + escapeMarkdown(host.hostname)}
              metadata={<HostMetadata host={host} connection={connection} />}
            />
          }
          actions={
            <ActionPanel>
              <Action.Push
                title="Inspect Host"
                icon={Icon.Sidebar}
                target={<HostDetail connection={connection} host={host} />}
              />
              <Action.Push
                title="Edit Host Defaults"
                icon={Icon.Pencil}
                shortcut={Keyboard.Shortcut.Common.Edit}
                target={
                  <HostSettingsForm
                    connection={connection}
                    host={host.hostname}
                    onSaved={() => void resource.refresh()}
                  />
                }
              />
              <HostActions connection={connection} host={host.hostname} />
              <Action
                title="Use as Default Host"
                icon={Icon.Star}
                onAction={async () => {
                  await saveConnection({
                    ...connection,
                    defaultHost: host.hostname,
                  });
                  await onConnectionChanged?.();
                  await showToast({
                    style: Toast.Style.Success,
                    title: "Default host updated",
                    message: host.hostname,
                  });
                }}
              />
              <Action
                title="Refresh Hosts"
                icon={Icon.ArrowClockwise}
                shortcut={Keyboard.Shortcut.Common.Refresh}
                onAction={() => void resource.refresh()}
              />
              <Action.Push
                title="Manage Connections"
                icon={Icon.Plug}
                target={<ConnectionsView onChanged={onConnectionChanged} />}
              />
            </ActionPanel>
          }
        />
      ))}
    </List>
  );
}

function HostMetadata({
  host,
  connection,
}: {
  host: HostInfo;
  connection: ConnectionSettings;
}) {
  return (
    <List.Item.Detail.Metadata>
      <List.Item.Detail.Metadata.Label
        title="Connection"
        text={connection.name}
      />
      {connection.defaultHost === host.hostname ? (
        <List.Item.Detail.Metadata.Label
          title="Default Host"
          text="Selected"
          icon={Icon.Star}
        />
      ) : null}
      <List.Item.Detail.Metadata.Separator />
      {hostDefaultFields
        .filter(([key]) => host.slurm_defaults?.[key] != null)
        .map(([key, label]) => (
          <List.Item.Detail.Metadata.Label
            key={key}
            title={label}
            text={String(host.slurm_defaults![key])}
          />
        ))}
    </List.Item.Detail.Metadata>
  );
}

export function HostActions({
  connection,
  host,
}: {
  connection: ConnectionSettings;
  host: string;
}) {
  return (
    <>
      <Action
        title="Show Jobs on Host"
        icon={Icon.List}
        onAction={() =>
          launchCommand({
            name: "jobs",
            type: LaunchType.UserInitiated,
            context: {
              connectionId: connection.id,
              host,
            } satisfies JobsLaunchContext,
          })
        }
      />
      <Action.Push
        title="Prepare Launch on Host"
        icon={Icon.Rocket}
        target={<LaunchView connection={connection} host={host} />}
      />
      <Action.CopyToClipboard title="Copy Host" content={host} />
    </>
  );
}

export function HostDetail({
  connection,
  host,
}: {
  connection: ConnectionSettings;
  host: HostInfo;
}) {
  const [force, setForce] = useState(false);
  const resource = useResource(
    "partitions:" +
      connectionScope(connection) +
      ":" +
      host.hostname +
      ":" +
      force,
    (signal) =>
      new SsyncClient(connection, signal).getPartitions(host.hostname, force),
  );
  const status = resource.data?.find((item) => item.hostname === host.hostname);
  const error = resource.error || status?.error;
  const refresh = () => {
    if (!force) setForce(true);
    else void resource.refresh();
  };
  const actions = (
    <ActionPanel>
      <Action
        title="Refresh Capacity"
        icon={Icon.ArrowClockwise}
        shortcut={Keyboard.Shortcut.Common.Refresh}
        onAction={refresh}
      />
      <Action.Push
        title="Edit Host Defaults"
        icon={Icon.Pencil}
        shortcut={Keyboard.Shortcut.Common.Edit}
        target={
          <HostSettingsForm connection={connection} host={host.hostname} />
        }
      />
      <HostActions connection={connection} host={host.hostname} />
    </ActionPanel>
  );
  return (
    <List
      isLoading={resource.isLoading}
      isShowingDetail
      navigationTitle={host.hostname}
      searchBarPlaceholder="Find a partition…"
      actions={actions}
    >
      <List.EmptyView
        title={error ? "Capacity unavailable" : "No partitions reported"}
        description={error || "This host has not reported partition capacity."}
        icon={Icon.Desktop}
        actions={actions}
      />
      {(error || status?.stale) && status?.partitions.length ? (
        <List.Item
          title={
            error ? "Could not refresh capacity" : "Showing cached capacity"
          }
          icon={{ source: Icon.Warning, tintColor: relay.warning }}
          subtitle={
            status.updated_at ? formatDate(status.updated_at) : undefined
          }
          detail={
            <List.Item.Detail
              markdown={escapeMarkdown(
                error || "The ssync API server marked this snapshot stale.",
              )}
            />
          }
          actions={actions}
        />
      ) : null}
      {status?.partitions.map((partition) => (
        <List.Item
          key={partition.partition}
          title={partition.partition}
          subtitle={partition.availability || undefined}
          icon={{ source: Icon.MemoryChip, tintColor: relay.accent }}
          detail={
            <List.Item.Detail
              markdown={
                "# " +
                escapeMarkdown(partition.partition) +
                "\n\n" +
                escapeMarkdown(host.hostname) +
                "\n\nCapacity reported for this partition. Partitions may share nodes."
              }
              metadata={
                <List.Item.Detail.Metadata>
                  <List.Item.Detail.Metadata.Label
                    title="Availability"
                    text={partition.availability || "Not reported"}
                  />
                  <List.Item.Detail.Metadata.Label
                    title="Nodes"
                    text={String(partition.nodes_total)}
                  />
                  <List.Item.Detail.Metadata.Label
                    title="CPUs Allocated / Total"
                    text={partition.cpus_alloc + " / " + partition.cpus_total}
                  />
                  <List.Item.Detail.Metadata.Label
                    title="CPUs Idle"
                    text={String(partition.cpus_idle)}
                  />
                  {partition.gpus_total != null ? (
                    <List.Item.Detail.Metadata.Label
                      title="GPUs Allocated / Total"
                      text={
                        (partition.gpus_used ?? "Not reported") +
                        " / " +
                        partition.gpus_total
                      }
                    />
                  ) : null}
                  <List.Item.Detail.Metadata.Separator />
                  <List.Item.Detail.Metadata.Label
                    title="Updated"
                    text={formatDate(status.updated_at)}
                  />
                  <List.Item.Detail.Metadata.Label
                    title="Source"
                    text={
                      status.stale
                        ? "Stale cache"
                        : status.cached
                          ? "ssync cache"
                          : "Host query"
                    }
                  />
                </List.Item.Detail.Metadata>
              }
            />
          }
          actions={actions}
        />
      ))}
    </List>
  );
}

export function HostSettingsForm({
  connection,
  host,
  onSaved,
}: {
  connection: ConnectionSettings;
  host: string;
  onSaved?: () => void;
}) {
  const resource = useResource(
    "host-settings:" + connectionScope(connection) + ":" + host,
    async (signal) => {
      try {
        return await new SsyncClient(connection, signal).getHostSettings(host);
      } catch (error) {
        if (error instanceof SsyncApiError && error.statusCode === 404)
          throw new Error(
            "Host editing requires an updated ssync API server with the host settings endpoint.",
          );
        throw error;
      }
    },
  );
  if (!resource.data)
    return (
      <List isLoading={resource.isLoading} navigationTitle="Edit Host Defaults">
        <List.EmptyView
          title={
            resource.error
              ? "Host settings unavailable"
              : "Loading host settings"
          }
          description={resource.error}
          icon={Icon.Gear}
          actions={
            <ActionPanel>
              <Action
                title="Retry"
                icon={Icon.ArrowClockwise}
                onAction={() => void resource.refresh()}
              />
            </ActionPanel>
          }
        />
      </List>
    );
  return (
    <HostDefaultsEditor
      connection={connection}
      settings={resource.data}
      onSaved={onSaved}
    />
  );
}

function HostDefaultsEditor({
  connection,
  settings,
  onSaved,
}: {
  connection: ConnectionSettings;
  settings: HostSettings;
  onSaved?: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const busy = useRef(false);
  const { pop } = useNavigation();
  async function save(values: Record<string, string>) {
    if (busy.current) return;
    let defaults;
    try {
      defaults = parseHostDefaults(values);
    } catch (error) {
      await showToast({
        style: Toast.Style.Failure,
        title: "Check host defaults",
        message: (error as Error).message,
      });
      return;
    }
    busy.current = true;
    setSaving(true);
    const toast = await showToast({
      style: Toast.Style.Animated,
      title: "Saving host defaults",
    });
    try {
      await new SsyncClient(connection).updateHostSettings(settings.hostname, {
        revision: settings.revision,
        slurm_defaults: defaults,
      });
      toast.style = Toast.Style.Success;
      toast.title = "Host defaults saved";
      onSaved?.();
      pop();
    } catch (error) {
      toast.style = Toast.Style.Failure;
      toast.title = "Host defaults not saved";
      toast.message = error instanceof Error ? error.message : String(error);
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }
  return (
    <Form
      isLoading={saving}
      navigationTitle={"Defaults · " + settings.hostname}
      actions={
        <ActionPanel>
          <Action.SubmitForm
            title="Save Host Defaults"
            icon={Icon.CheckCircle}
            onSubmit={save}
          />
        </ActionPanel>
      }
    >
      <Form.Description
        title={settings.hostname}
        text={
          "Applies to future launches through " +
          connection.name +
          ". Leave a field blank to remove its host default."
        }
      />
      {hostDefaultFields.map(([key, label]) => (
        <Form.TextField
          key={key}
          id={key}
          title={label}
          defaultValue={
            settings.slurm_defaults[key] == null
              ? ""
              : String(settings.slurm_defaults[key])
          }
          placeholder={
            key === "time" ? "HH:MM:SS or minutes" : "No host default"
          }
        />
      ))}
    </Form>
  );
}
