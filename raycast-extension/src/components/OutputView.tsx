import { Action, ActionPanel, Detail, Icon, Keyboard, Toast, showToast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { SsyncClient } from "../api/client";
import { bytesLabel, formatDate, metadataText } from "../lib/format";
import { codeBlock, escapeMarkdown } from "../lib/markdown";
import type { ConnectionSettings, JobInfo, JobOutputResponse } from "../types/ssync";

type Props = {
  connection: ConnectionSettings;
  job: JobInfo;
};

type OutputType = "stdout" | "stderr";

export function OutputView({ connection, job }: Props) {
  const client = useMemo(() => new SsyncClient(connection), [connection]);
  const [outputType, setOutputType] = useState<OutputType>("stdout");
  const [lines, setLines] = useState<number | undefined>(300);
  const [fullOutput, setFullOutput] = useState(false);
  const [output, setOutput] = useState<JobOutputResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load(next?: { outputType?: OutputType; lines?: number; fullOutput?: boolean; forceRefresh?: boolean }) {
    const requestedType = next?.outputType || outputType;
    const requestedFull = next?.fullOutput ?? fullOutput;
    const requestedLines = requestedFull ? undefined : next?.lines ?? lines;
    setOutputType(requestedType);
    setFullOutput(requestedFull);
    setLines(requestedLines);
    setIsLoading(true);
    setError(null);
    try {
      const data = await client.getOutput({
        job,
        outputType: requestedType,
        lines: requestedLines,
        fullOutput: requestedFull,
        forceRefresh: next?.forceRefresh,
      });
      setOutput(data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void load({ outputType: "stdout", lines: 300, fullOutput: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.job_id, job.hostname]);

  async function refresh() {
    await load({ forceRefresh: true });
    await showToast({ style: Toast.Style.Success, title: "Output refreshed" });
  }

  const content = outputType === "stdout" ? output?.stdout : output?.stderr;
  const metadata = outputType === "stdout" ? output?.stdout_metadata : output?.stderr_metadata;
  const title = `${outputType} · ${job.job_id} @ ${job.hostname}`;
  const markdown = error ? `# ${escapeMarkdown(outputType)}\n\n**Error:** ${escapeMarkdown(error)}` : codeBlock(content, "text");

  return (
    <Detail
      isLoading={isLoading}
      navigationTitle={title}
      markdown={markdown}
      metadata={
        <Detail.Metadata>
          <Detail.Metadata.Label title="Output" text={outputType} icon={Icon.Terminal} />
          <Detail.Metadata.Label title="Job" text={job.job_id} />
          <Detail.Metadata.Label title="Host" text={job.hostname} />
          <Detail.Metadata.Separator />
          <Detail.Metadata.Label title="Lines" text={fullOutput ? "full output" : lines ? `tail ${lines}` : "tail"} />
          <Detail.Metadata.Label title="Cached" text={metadataText(output?.cached)} />
          <Detail.Metadata.Label title="Truncated" text={metadataText(output?.content_truncated)} />
          <Detail.Metadata.Separator />
          <Detail.Metadata.Label title="Size" text={bytesLabel(metadata?.size_bytes)} />
          <Detail.Metadata.Label title="Last Modified" text={formatDate(metadata?.last_modified)} />
          <Detail.Metadata.Label title="Path" text={metadataText(metadata?.path)} />
        </Detail.Metadata>
      }
      actions={
        <ActionPanel>
          <ActionPanel.Section>
            <Action title="Refresh Output" icon={Icon.ArrowClockwise} shortcut={Keyboard.Shortcut.Common.Refresh} onAction={refresh} />
            <Action title={outputType === "stdout" ? "Show stderr" : "Show stdout"} icon={Icon.Terminal} onAction={() => load({ outputType: outputType === "stdout" ? "stderr" : "stdout", lines: 300, fullOutput: false })} />
            <Action title="Load 1,000 Lines" icon={Icon.Text} onAction={() => load({ lines: 1000, fullOutput: false })} />
            <Action title="Load Full Output" icon={Icon.TextDocument} onAction={() => load({ fullOutput: true })} />
          </ActionPanel.Section>
          <ActionPanel.Section>
            <Action.CopyToClipboard title={`Copy ${outputType}`} content={content || ""} />
            {metadata?.path ? <Action.CopyToClipboard title={`Copy ${outputType} Path`} content={metadata.path} /> : null}
          </ActionPanel.Section>
        </ActionPanel>
      }
    />
  );
}
