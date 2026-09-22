import {
  Action,
  ActionPanel,
  Alert,
  Icon,
  Keyboard,
  List,
  Toast,
  confirmAlert,
  openExtensionPreferences,
  showToast,
  useNavigation,
} from "@raycast/api";
import { useState } from "react";
import {
  getConnection,
  getConnections,
  removeConnection,
  setActiveConnection,
  clearJobCache,
} from "../api/storage";
import { SsyncClient } from "../api/client";
import { useResource } from "../hooks/useResource";
import { connectionLabel } from "../lib/connections";
import { relay } from "../lib/design";
import { escapeMarkdown } from "../lib/markdown";
import { ConnectionForm } from "./ConnectionForm";

export function ConnectionsView({
  onChanged,
}: {
  onChanged?: () => Promise<void>;
}) {
  const [version, setVersion] = useState(0);
  const resource = useResource("connections:" + version, () =>
    getConnections(),
  );
  const { push, pop } = useNavigation();
  async function changed() {
    setVersion((value) => value + 1);
    await onChanged?.();
  }
  async function edit(id: string) {
    const connection = await getConnection(id);
    if (connection)
      push(
        <ConnectionForm
          initial={connection}
          onConfigured={async () => {
            await changed();
            pop();
          }}
        />,
      );
  }
  async function activate(id: string) {
    await setActiveConnection(id);
    await changed();
    await showToast({
      style: Toast.Style.Success,
      title: "Connection selected",
    });
  }
  async function remove(id: string, name: string) {
    if (
      !(await confirmAlert({
        title: "Remove " + name + "?",
        message:
          "Removes this saved connection and its local cache. Jobs and host settings are unchanged.",
        primaryAction: {
          title: "Remove Connection",
          style: Alert.ActionStyle.Destructive,
        },
      }))
    )
      return;
    await removeConnection(id);
    await changed();
  }
  async function test(id: string) {
    const connection = await getConnection(id);
    if (!connection) return;
    const toast = await showToast({
      style: Toast.Style.Animated,
      title: "Testing connection",
    });
    try {
      await new SsyncClient(connection).testConnection();
      toast.style = Toast.Style.Success;
      toast.title = "Connection ready";
    } catch (error) {
      toast.style = Toast.Style.Failure;
      toast.title = "Connection unavailable";
      toast.message = error instanceof Error ? error.message : String(error);
    }
  }
  const add = (
    <Action.Push
      title="Add Connection"
      icon={Icon.Plus}
      shortcut={Keyboard.Shortcut.Common.New}
      target={
        <ConnectionForm
          onConfigured={async () => {
            await changed();
            pop();
          }}
        />
      }
    />
  );
  return (
    <List
      isLoading={resource.isLoading}
      isShowingDetail
      navigationTitle="ssync Connections"
      searchBarPlaceholder="Find a saved connection…"
      actions={
        <ActionPanel>
          {add}
          <Action
            title="Extension Preferences"
            icon={Icon.Gear}
            onAction={openExtensionPreferences}
          />
        </ActionPanel>
      }
    >
      <List.EmptyView
        icon={Icon.Plug}
        title={resource.error ? "Connections unavailable" : "Connect to ssync"}
        description={
          resource.error ||
          "Save your ssync API connections and switch between them here."
        }
        actions={
          <ActionPanel>
            {add}
            <Action
              title="Retry"
              icon={Icon.ArrowClockwise}
              onAction={resource.refresh}
            />
          </ActionPanel>
        }
      />
      {resource.data?.profiles.map((profile) => (
        <List.Item
          key={profile.id}
          id={profile.id}
          icon={{
            source:
              resource.data?.activeId === profile.id
                ? Icon.CheckCircle
                : Icon.Plug,
            tintColor: relay.accent,
          }}
          title={connectionLabel(profile)}
          subtitle={new URL(profile.apiUrl).host}
          detail={
            <List.Item.Detail
              markdown={
                "# " +
                escapeMarkdown(connectionLabel(profile)) +
                "\n\n" +
                (resource.data?.activeId === profile.id
                  ? "Selected connection"
                  : "Saved connection")
              }
              metadata={
                <List.Item.Detail.Metadata>
                  <List.Item.Detail.Metadata.Label
                    title="ssync API URL"
                    text={profile.apiUrl}
                  />
                  <List.Item.Detail.Metadata.Label
                    title="Default Host"
                    text={profile.defaultHost || "All hosts"}
                  />
                  <List.Item.Detail.Metadata.Separator />
                  <List.Item.Detail.Metadata.Label
                    title="Historical Job Window"
                    text={profile.historyWindow}
                  />
                  <List.Item.Detail.Metadata.Label
                    title="Jobs per Host"
                    text={String(profile.jobLimit)}
                  />
                </List.Item.Detail.Metadata>
              }
            />
          }
          actions={
            <ActionPanel>
              <Action
                title={
                  resource.data?.activeId === profile.id
                    ? "Edit Connection"
                    : "Use Connection"
                }
                icon={
                  resource.data?.activeId === profile.id
                    ? Icon.Pencil
                    : Icon.CheckCircle
                }
                onAction={() =>
                  resource.data?.activeId === profile.id
                    ? edit(profile.id)
                    : activate(profile.id)
                }
              />
              {resource.data?.activeId !== profile.id ? (
                <Action
                  title="Edit Connection"
                  icon={Icon.Pencil}
                  shortcut={Keyboard.Shortcut.Common.Edit}
                  onAction={() => edit(profile.id)}
                />
              ) : null}
              {add}
              <ActionPanel.Section>
                <Action
                  title="Test Connection"
                  icon={Icon.Bolt}
                  onAction={() => test(profile.id)}
                />
                <Action
                  title="Clear Cached Jobs"
                  icon={Icon.Trash}
                  onAction={async () => {
                    await clearJobCache(profile.id);
                    await showToast({
                      style: Toast.Style.Success,
                      title: "Cached jobs cleared",
                    });
                  }}
                />
                <Action
                  title="Extension Preferences"
                  icon={Icon.Gear}
                  onAction={openExtensionPreferences}
                />
              </ActionPanel.Section>
              <ActionPanel.Section>
                <Action
                  title="Remove Connection"
                  icon={Icon.Trash}
                  style={Action.Style.Destructive}
                  onAction={() => remove(profile.id, connectionLabel(profile))}
                />
              </ActionPanel.Section>
            </ActionPanel>
          }
        />
      ))}
    </List>
  );
}
