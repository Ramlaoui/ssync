import { type Application, Toast, getPreferenceValues, open, showToast } from "@raycast/api";
import { execFile } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { promisify } from "node:util";
import { SsyncClient } from "../api/client";
import type { JobInfo } from "../types/ssync";

type OutputType = "stdout" | "stderr";

type OutputEditor = "default" | "vscode" | "cursor" | "ghostty-nvim" | "custom";

type Preferences = {
  outputEditor?: OutputEditor;
  outputEditorApplication?: Application | string;
};

const execFileAsync = promisify(execFile);

export async function openJobOutputFile(options: {
  client: SsyncClient;
  job: JobInfo;
  outputType: OutputType;
}): Promise<void> {
  const toast = await showToast({
    style: Toast.Style.Animated,
    title: `Downloading ${options.outputType}`,
    message: "Refreshing the full output file",
  });

  try {
    const download = await options.client.downloadOutput({
      job: options.job,
      outputType: options.outputType,
      forceRefresh: true,
    });
    const filePath = await writeOutputFile({
      hostname: options.job.hostname,
      jobId: options.job.job_id,
      outputType: options.outputType,
      filename: download.filename,
      content: download.content,
    });

    toast.title = `Opening ${options.outputType}`;
    toast.message = filePath;
    await openWithConfiguredEditor(filePath);

    toast.style = Toast.Style.Success;
    toast.title = `${options.outputType} opened`;
    toast.message = filePath;
  } catch (error) {
    toast.style = Toast.Style.Failure;
    toast.title = `Failed to open ${options.outputType}`;
    toast.message = error instanceof Error ? error.message : String(error);
  }
}

async function writeOutputFile(options: {
  hostname: string;
  jobId: string;
  outputType: OutputType;
  filename: string;
  content: Buffer;
}): Promise<string> {
  const filePath = join(
    tmpdir(),
    "ssync-raycast-output",
    safePathSegment(options.hostname),
    safePathSegment(options.jobId),
    safeOutputFilename(options.filename, options.outputType),
  );
  await mkdir(dirname(filePath), { recursive: true });
  await writeFile(filePath, options.content);
  return filePath;
}

async function openWithConfiguredEditor(filePath: string): Promise<void> {
  const preferences = getPreferenceValues<Preferences>();
  switch (preferences.outputEditor || "default") {
    case "vscode":
      await open(filePath, "Visual Studio Code");
      return;
    case "cursor":
      await open(filePath, "Cursor");
      return;
    case "ghostty-nvim":
      await openInGhosttyNvim(filePath);
      return;
    case "custom":
      await open(filePath, preferences.outputEditorApplication || undefined);
      return;
    case "default":
    default:
      await open(filePath);
  }
}

async function openInGhosttyNvim(filePath: string): Promise<void> {
  if (process.platform === "darwin") {
    await execFileAsync("/usr/bin/open", ["-na", "Ghostty", "--args", "-e", "nvim", filePath]);
    return;
  }
  await execFileAsync("ghostty", ["-e", "nvim", filePath]);
}

function safePathSegment(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]/g, "_") || "unknown";
}

function safeOutputFilename(filename: string, outputType: OutputType): string {
  const safe = safePathSegment(filename);
  if (safe.endsWith(".log")) return safe;
  return `${safe || outputType}.log`;
}
