import {
  Action,
  ActionPanel,
  Detail,
  Form,
  Icon,
  Keyboard,
  List,
  LocalStorage,
  Toast,
  showToast,
  useNavigation,
} from "@raycast/api";
import { useEffect, useRef, useState } from "react";
import { SsyncApiError, SsyncClient } from "../api/client";
import { useResource } from "../hooks/useResource";
import { connectionScope } from "../lib/connections";
import {
  emptyDraft,
  buildLaunchRequest,
  type LaunchDraft,
} from "../lib/launch";
import { codeBlock, escapeMarkdown } from "../lib/markdown";
import type {
  ConnectionSettings,
  HostInfo,
  JobInfo,
  LaunchRequest,
  LaunchResponse,
} from "../types/ssync";
import { JobDetail } from "./JobDetail";

export function LaunchView({
  connection,
  job,
  host,
}: {
  connection: ConnectionSettings;
  job?: JobInfo;
  host?: string;
}) {
  const scope = connectionScope(connection);
  const resource = useResource(
    scope + (job ? job.hostname + ":" + job.job_id : ""),
    async (signal) => {
      const client = new SsyncClient(connection, signal);
      const [hosts, script] = await Promise.all([
        client.getHosts(),
        job ? client.getScript(job) : undefined,
      ]);
      return { hosts, script };
    },
  );
  if (!resource.data)
    return (
      <List
        isLoading={resource.isLoading}
        navigationTitle={job ? "Relaunch Job" : "Launch Job"}
      >
        <List.EmptyView
          title={resource.error ? "Launch unavailable" : "Preparing launch"}
          description={resource.error}
          icon={Icon.Rocket}
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
    <LaunchForm
      connection={connection}
      hosts={resource.data.hosts}
      initial={{
        ...emptyDraft,
        host:
          host ||
          job?.hostname ||
          connection.defaultHost ||
          resource.data.hosts[0]?.hostname ||
          "",
        name: job?.name || "",
        script: resource.data.script?.script_content || emptyDraft.script,
        sourceDir: resource.data.script?.local_source_dir || "",
      }}
      relaunch={Boolean(job)}
    />
  );
}

function LaunchForm({
  connection,
  hosts,
  initial,
  relaunch,
}: {
  connection: ConnectionSettings;
  hosts: HostInfo[];
  initial: LaunchDraft;
  relaunch: boolean;
}) {
  const [draft, setDraft] = useState(initial);
  const { push } = useNavigation();
  const field = (key: keyof LaunchDraft, value: string | boolean) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const storageKey =
    "ssync.launch-draft.v2:" +
    connection.id +
    ":" +
    encodeURIComponent(connection.apiUrl);
  async function review() {
    try {
      push(
        <LaunchReview
          connection={connection}
          request={buildLaunchRequest(draft)}
        />,
      );
    } catch (error) {
      await showToast({
        style: Toast.Style.Failure,
        title: "Check launch details",
        message: (error as Error).message,
      });
    }
  }
  async function restore() {
    try {
      const saved = await LocalStorage.getItem<string>(storageKey);
      if (!saved) throw new Error("No draft saved for this connection.");
      const restored = { ...emptyDraft, ...JSON.parse(saved) } as LaunchDraft;
      if (!hosts.some((item) => item.hostname === restored.host))
        restored.host = hosts[0]?.hostname || "";
      setDraft(restored);
      await showToast({ style: Toast.Style.Success, title: "Draft restored" });
    } catch (error) {
      await showToast({
        style: Toast.Style.Failure,
        title: "Could not restore draft",
        message: (error as Error).message,
      });
    }
  }
  return (
    <Form
      navigationTitle={relaunch ? "Relaunch Job" : "Launch Job"}
      actions={
        <ActionPanel>
          <Action.SubmitForm
            title="Review Launch"
            icon={Icon.ArrowRight}
            onSubmit={review}
          />
          <Action
            title="Save Draft"
            icon={Icon.Document}
            shortcut={Keyboard.Shortcut.Common.Save}
            onAction={async () => {
              await LocalStorage.setItem(storageKey, JSON.stringify(draft));
              await showToast({
                style: Toast.Style.Success,
                title: "Draft saved on this Mac",
              });
            }}
          />
          <Action title="Restore Draft" icon={Icon.Clock} onAction={restore} />
        </ActionPanel>
      }
    >
      <Form.Dropdown
        id="host"
        title="Host"
        value={draft.host}
        onChange={(value) => field("host", value)}
      >
        {hosts.map((item) => (
          <Form.Dropdown.Item
            key={item.hostname}
            value={item.hostname}
            title={item.hostname}
          />
        ))}
      </Form.Dropdown>
      <Form.TextField
        id="name"
        title="Job Name"
        value={draft.name}
        onChange={(value) => field("name", value)}
      />
      <Form.TextArea
        id="script"
        title="Job Script"
        value={draft.script}
        onChange={(value) => field("script", value)}
      />
      <Form.Separator />
      <Form.Dropdown
        id="syncMode"
        title="Source"
        value={draft.sync ? "sync" : "script"}
        onChange={(value) => field("sync", value === "sync")}
      >
        <Form.Dropdown.Item value="sync" title="Synchronize Source Directory" />
        <Form.Dropdown.Item value="script" title="Script Only" />
      </Form.Dropdown>
      {draft.sync ? (
        <>
          <Form.TextField
            id="sourceDir"
            title="Source Directory"
            value={draft.sourceDir}
            onChange={(value) => field("sourceDir", value)}
            info="Directory on the ssync API server, not on the remote host."
          />
          <Form.Checkbox
            id="gitignore"
            label="Respect .gitignore"
            value={draft.respectGitignore}
            onChange={(value) => field("respectGitignore", value)}
          />
          <Form.TextArea
            id="exclude"
            title="Exclude Patterns"
            value={draft.exclude}
            onChange={(value) => field("exclude", value)}
            info="One pattern per line."
          />
          <Form.TextArea
            id="include"
            title="Include Patterns"
            value={draft.include}
            onChange={(value) => field("include", value)}
            info="One pattern per line."
          />
        </>
      ) : null}
      <Form.Separator />
      <Form.Description
        title="Resource Overrides"
        text="Leave blank to keep the script directives and host defaults."
      />
      {(
        [
          ["partition", "Partition"],
          ["account", "Account"],
          ["cpus", "CPUs"],
          ["memory", "Memory (GB)"],
          ["minutes", "Time (Minutes)"],
          ["nodes", "Nodes"],
          ["gpus", "GPUs per Node"],
        ] as const
      ).map(([key, title]) => (
        <Form.TextField
          key={key}
          id={key}
          title={title}
          value={draft[key]}
          onChange={(value) => field(key, value)}
          placeholder="From script or host"
        />
      ))}
    </Form>
  );
}

export function LaunchReview({
  connection,
  request,
}: {
  connection: ConnectionSettings;
  request: LaunchRequest;
}) {
  const [response, setResponse] = useState<LaunchResponse>();
  const [error, setError] = useState<string>();
  const [ambiguous, setAmbiguous] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const busy = useRef(false);
  async function submit() {
    if (busy.current || ambiguous) return;
    busy.current = true;
    setSubmitting(true);
    setError(undefined);
    try {
      const accepted = await new SsyncClient(connection).launchJob(request);
      if (!accepted.success) throw new Error(accepted.message);
      setResponse(accepted);
    } catch (failure) {
      // The launch API has no idempotency key. Never blindly repeat an uncertain POST.
      setAmbiguous(
        !(
          failure instanceof SsyncApiError &&
          failure.statusCode !== undefined &&
          failure.statusCode >= 400 &&
          failure.statusCode < 500 &&
          failure.statusCode !== 408
        ),
      );
      setError(failure instanceof Error ? failure.message : String(failure));
      busy.current = false;
    } finally {
      setSubmitting(false);
    }
  }
  if (response)
    return (
      <LaunchProgress
        connection={connection}
        response={response}
        name={request.job_name}
      />
    );
  const markdown =
    (error
      ? "**" +
        (ambiguous ? "Submission status unknown" : "Launch not accepted") +
        ":** " +
        escapeMarkdown(error) +
        "\n\n" +
        (ambiguous ? "Check Jobs before starting another launch.\n\n" : "")
      : "") +
    "# " +
    escapeMarkdown(request.job_name || "Review Launch") +
    "\n\n" +
    codeBlock(request.script_content, "bash") +
    (request.source_dir
      ? "\n\n## Sync Rules\n\n" +
        codeBlock(
          "Exclude: " +
            (request.exclude.join(", ") || "None") +
            "\nInclude: " +
            (request.include.join(", ") || "None"),
        )
      : "");
  return (
    <Detail
      isLoading={submitting}
      navigationTitle="Review Launch"
      markdown={markdown}
      metadata={
        <Detail.Metadata>
          <Detail.Metadata.Label title="Connection" text={connection.name} />
          <Detail.Metadata.Label title="Host" text={request.host} />
          <Detail.Metadata.Label
            title="Source"
            text={request.source_dir || "Script only"}
          />
          <Detail.Metadata.Label
            title=".gitignore"
            text={request.no_gitignore ? "Ignored" : "Respected"}
          />
          <Detail.Metadata.Separator />
          {(
            [
              "partition",
              "account",
              "cpus",
              "mem",
              "time",
              "nodes",
              "gpus_per_node",
            ] as const
          )
            .filter((key) => request[key] !== undefined)
            .map((key) => (
              <Detail.Metadata.Label
                key={key}
                title={key.replaceAll("_", " ")}
                text={String(request[key])}
              />
            ))}
        </Detail.Metadata>
      }
      actions={
        <ActionPanel>
          {!ambiguous && !submitting ? (
            <Action title="Launch Job" icon={Icon.Rocket} onAction={submit} />
          ) : null}
          <Action.OpenInBrowser
            title="Check Jobs in ssync Web"
            url={connection.apiUrl + "/#/"}
          />
          <Action.CopyToClipboard
            title="Copy Script"
            content={request.script_content}
          />
        </ActionPanel>
      }
    />
  );
}

function LaunchProgress({
  connection,
  response,
  name,
}: {
  connection: ConnectionSettings;
  response: LaunchResponse;
  name?: string;
}) {
  const status = useResource("launch:" + response.launch_id, (signal) =>
    response.launch_id
      ? new SsyncClient(connection, signal).getLaunchStatus(response.launch_id)
      : Promise.resolve({
          launch_id: "",
          hostname: response.hostname,
          stage: response.success ? "submitted" : "failed",
          terminal: true,
          success: response.success,
          job_id: response.job_id,
          message: response.message,
          events: [],
        }),
  );
  const { data, isLoading, error, refresh } = status;
  const started = useRef(Date.now());
  useEffect(() => {
    if (
      isLoading ||
      error ||
      data?.terminal ||
      Date.now() - started.current > 300_000
    )
      return;
    const timer = setTimeout(() => void refresh(), 2000);
    return () => clearTimeout(timer);
  }, [data, isLoading, error, refresh]);
  const jobId = status.data?.job_id || response.job_id;
  const job: JobInfo | undefined = jobId
    ? {
        job_id: jobId,
        hostname: response.hostname,
        name: name || jobId,
        state: "PD",
      }
    : undefined;
  return (
    <Detail
      isLoading={status.isLoading}
      navigationTitle="Launch Progress"
      markdown={
        "# " +
        escapeMarkdown(status.data?.stage || "Launch accepted") +
        "\n\n" +
        escapeMarkdown(
          status.error || status.data?.message || response.message,
        ) +
        "\n\n" +
        codeBlock(
          status.data?.events
            .map((event) => event.message || event.stage || "")
            .join("\n"),
        )
      }
      metadata={
        <Detail.Metadata>
          <Detail.Metadata.Label title="Host" text={response.hostname} />
          {response.launch_id ? (
            <Detail.Metadata.Label title="Launch" text={response.launch_id} />
          ) : null}
          {jobId ? <Detail.Metadata.Label title="Job" text={jobId} /> : null}
        </Detail.Metadata>
      }
      actions={
        <ActionPanel>
          {job ? (
            <Action.Push
              title="Open Job"
              icon={Icon.Sidebar}
              target={<JobDetail connection={connection} job={job} />}
            />
          ) : null}
          <Action
            title="Refresh Progress"
            icon={Icon.ArrowClockwise}
            shortcut={Keyboard.Shortcut.Common.Refresh}
            onAction={() => void status.refresh()}
          />
          <Action.OpenInBrowser
            title="Open ssync Web"
            url={connection.apiUrl + "/#/"}
          />
        </ActionPanel>
      }
    />
  );
}
