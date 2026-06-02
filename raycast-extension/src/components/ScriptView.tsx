import { Action, ActionPanel, Detail, Icon, Keyboard, Toast, showToast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { SsyncClient } from "../api/client";
import { codeBlock, escapeMarkdown, kvTable } from "../lib/markdown";
import type { ConnectionSettings, JobInfo, JobScriptResponse } from "../types/ssync";

type Props = {
  connection: ConnectionSettings;
  job: JobInfo;
};

export function ScriptView({ connection, job }: Props) {
  const client = useMemo(() => new SsyncClient(connection), [connection]);
  const [script, setScript] = useState<JobScriptResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setIsLoading(true);
    setError(null);
    try {
      setScript(await client.getScript(job));
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
    await showToast({ style: Toast.Style.Success, title: "Script refreshed" });
  }

  const markdown = [
    `# Script for ${escapeMarkdown(job.name || job.job_id)}`,
    "",
    kvTable([
      ["Job", `${job.job_id} @ ${job.hostname}`],
      ["Content length", script?.content_length],
      ["Local source dir", script?.local_source_dir],
    ]),
    "",
    error ? `**Error:** ${escapeMarkdown(error)}` : codeBlock(script?.script_content, "bash"),
  ].join("\n");

  return (
    <Detail
      isLoading={isLoading}
      navigationTitle={`Script · ${job.job_id} @ ${job.hostname}`}
      markdown={markdown}
      actions={
        <ActionPanel>
          <ActionPanel.Section>
            <Action title="Refresh Script" icon={Icon.ArrowClockwise} shortcut={Keyboard.Shortcut.Common.Refresh} onAction={refresh} />
            <Action.CopyToClipboard title="Copy Script" content={script?.script_content || ""} />
            {script?.local_source_dir ? <Action.CopyToClipboard title="Copy Local Source Dir" content={script.local_source_dir} /> : null}
          </ActionPanel.Section>
        </ActionPanel>
      }
    />
  );
}
