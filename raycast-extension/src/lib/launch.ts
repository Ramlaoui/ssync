import type { LaunchRequest } from "../types/ssync";
export interface LaunchDraft {
  host: string;
  name: string;
  script: string;
  sourceDir: string;
  sync: boolean;
  partition: string;
  account: string;
  cpus: string;
  memory: string;
  minutes: string;
  nodes: string;
  gpus: string;
  exclude: string;
  include: string;
  respectGitignore: boolean;
}
export const emptyDraft: LaunchDraft = {
  host: "",
  name: "",
  script: "#!/bin/bash\n\n",
  sourceDir: "",
  sync: true,
  partition: "",
  account: "",
  cpus: "",
  memory: "",
  minutes: "",
  nodes: "",
  gpus: "",
  exclude: "",
  include: "",
  respectGitignore: true,
};
export function buildLaunchRequest(draft: LaunchDraft): LaunchRequest {
  if (!draft.host.trim()) throw new Error("Select a host.");
  if (!draft.script.trim() || draft.script.trim() === "#!/bin/bash")
    throw new Error("Enter a job script.");
  if (draft.sync && !draft.sourceDir.trim())
    throw new Error(
      "Enter the source directory on the ssync API server, or select Script Only.",
    );
  const request: LaunchRequest = {
    host: draft.host,
    script_content: draft.script,
    exclude: draft.exclude
      .split("\n")
      .map((v) => v.trim())
      .filter(Boolean),
    include: draft.include
      .split("\n")
      .map((v) => v.trim())
      .filter(Boolean),
    no_gitignore: !draft.respectGitignore,
  };
  if (draft.sync) request.source_dir = draft.sourceDir.trim();
  if (draft.name.trim()) request.job_name = draft.name.trim();
  if (draft.partition.trim()) request.partition = draft.partition.trim();
  if (draft.account.trim()) request.account = draft.account.trim();
  const fields = [
    ["cpus", "cpus", "CPUs", 1, 256],
    ["memory", "mem", "Memory", 1, 1024],
    ["minutes", "time", "Time limit", 1, Number.MAX_SAFE_INTEGER],
    ["nodes", "nodes", "Nodes", 1, 100],
    ["gpus", "gpus_per_node", "GPUs", 0, 256],
  ] as const;
  for (const [field, key, label, min, max] of fields) {
    if (!draft[field].trim()) continue;
    const value = Number(draft[field]);
    if (!Number.isSafeInteger(value) || value < min || value > max)
      throw new Error(
        label + " must be a whole number from " + min + " to " + max + ".",
      );
    request[key] = value;
  }
  return request;
}
