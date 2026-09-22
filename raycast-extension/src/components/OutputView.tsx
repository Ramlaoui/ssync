import {
  Action,
  ActionPanel,
  Detail,
  Icon,
  Keyboard,
  List,
  Toast,
  showToast,
} from "@raycast/api";
import { useEffect, useRef, useState } from "react";
import { SsyncClient } from "../api/client";
import { useResource } from "../hooks/useResource";
import { connectionScope } from "../lib/connections";
import { bytesLabel, formatDate, webJobUrl } from "../lib/format";
import { jobKey } from "../lib/jobs";
import { codeBlock, escapeMarkdown } from "../lib/markdown";
import { openJobOutputFile } from "../lib/output-file";
import type { ConnectionSettings, JobInfo } from "../types/ssync";

export function OutputView({
  connection,
  job,
  initialOutputType = "stdout",
}: {
  connection: ConnectionSettings;
  job: JobInfo;
  initialOutputType?: "stdout" | "stderr";
}) {
  const [outputType, setOutputType] = useState(initialOutputType);
  const [lines, setLines] = useState(300);
  const [full, setFull] = useState(false);
  const [following, setFollowing] = useState(false);
  const force = useRef(true);
  const followQueued = useRef(true);
  const resource = useResource(
    connectionScope(connection) + jobKey(job) + outputType + lines + full,
    async (signal) => {
      const result = await new SsyncClient(connection, signal).getOutput({
        job,
        outputType,
        lines,
        fullOutput: full,
        forceRefresh: force.current,
      });
      if (!signal.aborted) force.current = false;
      return result;
    },
  );
  const { isLoading, error, refresh: refreshResource } = resource;
  const output =
    resource.data?.output_type === outputType ? resource.data : undefined;
  useEffect(() => {
    if (isLoading || error) return;
    let delay: number | undefined;
    if (output?.refresh_queued && followQueued.current) {
      delay = 2500;
      followQueued.current = false;
    } else if (following && !full) delay = 10000;
    if (!delay) return;
    const timer = setTimeout(() => void refreshResource(), delay);
    return () => clearTimeout(timer);
  }, [output, isLoading, error, refreshResource, following, full]);
  async function refresh() {
    force.current = true;
    followQueued.current = true;
    const ok = await resource.refresh();
    await showToast({
      style: ok ? Toast.Style.Success : Toast.Style.Failure,
      title: ok ? "Output refreshed" : "Could not refresh output",
    });
  }
  function switchStream() {
    force.current = true;
    followQueued.current = true;
    setOutputType((current) => (current === "stdout" ? "stderr" : "stdout"));
    setFull(false);
    setLines(300);
  }
  const content =
    (outputType === "stdout" ? output?.stdout : output?.stderr) || "";
  const metadata =
    outputType === "stdout" ? output?.stdout_metadata : output?.stderr_metadata;
  const display = content.slice(-120_000);
  const truncated =
    display.length < content.length || output?.content_truncated;
  const markdown =
    (resource.error
      ? "**Refresh failed:** " + escapeMarkdown(resource.error) + "\n\n"
      : "") +
    (truncated
      ? "_Showing a bounded preview. Open in your editor for the complete file._\n\n"
      : "") +
    codeBlock(display, "text");
  return (
    <Detail
      isLoading={resource.isLoading}
      navigationTitle={outputType + " · " + job.job_id + " · " + job.hostname}
      markdown={markdown}
      metadata={
        <Detail.Metadata>
          <Detail.Metadata.Label title="Job" text={job.name || job.job_id} />
          <Detail.Metadata.Label title="Host" text={job.hostname} />
          <Detail.Metadata.Label
            title="Output"
            text={outputType}
            icon={Icon.Terminal}
          />
          <Detail.Metadata.Separator />
          <Detail.Metadata.Label
            title="View"
            text={full ? "Full output preview" : "Last " + lines + " lines"}
          />
          <Detail.Metadata.Label
            title="Updates"
            text={
              following && !full && !resource.error
                ? "Following · every 10s"
                : "Paused"
            }
          />
          {output?.stale || resource.error ? (
            <Detail.Metadata.Label
              title="Snapshot"
              text="Last received content"
              icon={Icon.Warning}
            />
          ) : null}
          {output?.refresh_queued ? (
            <Detail.Metadata.Label
              title="Refresh"
              text="Queued by ssync API server"
            />
          ) : null}
          {metadata ? (
            <>
              <Detail.Metadata.Separator />
              <Detail.Metadata.Label
                title="Size"
                text={bytesLabel(metadata.size_bytes)}
              />
              <Detail.Metadata.Label
                title="Modified"
                text={formatDate(metadata.last_modified)}
              />
              <Detail.Metadata.Label title="Path" text={metadata.path} />
            </>
          ) : null}
        </Detail.Metadata>
      }
      actions={
        <ActionPanel>
          <Action
            title="Refresh Output"
            icon={Icon.ArrowClockwise}
            shortcut={Keyboard.Shortcut.Common.Refresh}
            onAction={refresh}
          />
          <Action
            title={
              following && !error && !full ? "Pause Following" : "Follow Output"
            }
            icon={following && !error && !full ? Icon.Pause : Icon.Play}
            shortcut={{ modifiers: ["cmd", "shift"], key: "p" }}
            onAction={() => {
              setFull(false);
              if (error) {
                setFollowing(true);
                void refresh();
              } else setFollowing((value) => !value || full);
            }}
          />
          <Action
            title={outputType === "stdout" ? "Show stderr" : "Show stdout"}
            icon={Icon.Switch}
            shortcut={{ modifiers: ["cmd"], key: "t" }}
            onAction={switchStream}
          />
          <Action.Push
            title="Search Loaded Output"
            icon={Icon.MagnifyingGlass}
            shortcut={{ modifiers: ["cmd"], key: "f" }}
            target={<OutputSearch content={content} />}
          />
          <ActionPanel.Section>
            <Action
              title="Load 1,000 Lines"
              icon={Icon.Text}
              onAction={() => {
                followQueued.current = true;
                setFull(false);
                setLines(1000);
              }}
            />
            <Action
              title="Load Full Output"
              icon={Icon.TextDocument}
              onAction={() => {
                followQueued.current = true;
                setFollowing(false);
                setFull(true);
              }}
            />
            <Action
              title={"Open " + outputType + " in Editor"}
              icon={Icon.Pencil}
              shortcut={Keyboard.Shortcut.Common.Open}
              onAction={() =>
                openJobOutputFile({
                  client: new SsyncClient(connection),
                  job,
                  outputType,
                })
              }
            />
            <Action.OpenInBrowser
              title="Open in ssync Web"
              url={webJobUrl(connection.apiUrl, job) + "?tab=" + outputType}
            />
          </ActionPanel.Section>
          <ActionPanel.Section>
            {content ? (
              <Action.CopyToClipboard
                title="Copy Loaded Output"
                content={content}
              />
            ) : null}
            {metadata?.path ? (
              <Action.CopyToClipboard
                title="Copy Output Path"
                content={metadata.path}
              />
            ) : null}
          </ActionPanel.Section>
        </ActionPanel>
      }
    />
  );
}

function OutputSearch({ content }: { content: string }) {
  const lines = content.split("\n");
  const offset = Math.max(0, lines.length - 2000);
  return (
    <List
      isShowingDetail
      navigationTitle="Search Loaded Output"
      searchBarPlaceholder={
        offset ? "Search the last 2,000 loaded lines…" : "Search loaded lines…"
      }
    >
      <List.EmptyView
        title="No matching lines"
        description="Search covers the loaded output only."
        icon={Icon.MagnifyingGlass}
      />
      {lines.slice(offset).map((line, index) => (
        <List.Item
          key={offset + index}
          title={line.slice(0, 180) || " "}
          subtitle={"Loaded line " + (offset + index + 1)}
          keywords={[line]}
          detail={<List.Item.Detail markdown={codeBlock(line)} />}
          actions={
            <ActionPanel>
              <Action.CopyToClipboard title="Copy Line" content={line} />
            </ActionPanel>
          }
        />
      ))}
    </List>
  );
}
