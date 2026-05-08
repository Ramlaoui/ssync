export type JobParameters = {
  jobName?: string;
  cpus?: number;
  memory?: number;
  timeLimit?: number;
  nodes?: number;
  partition?: string;
  account?: string;
  constraint?: string;
  ntasksPerNode?: number;
  gpusPerNode?: number;
  gres?: string;
  outputFile?: string;
  errorFile?: string;
  pythonEnv?: string;
  sourceDir?: string;
};

const DIRECTIVE_MAP: Array<[keyof JobParameters, string]> = [
  ["jobName", "--job-name"],
  ["cpus", "--cpus-per-task"],
  ["memory", "--mem"],
  ["timeLimit", "--time"],
  ["nodes", "--nodes"],
  ["partition", "--partition"],
  ["account", "--account"],
  ["constraint", "--constraint"],
  ["ntasksPerNode", "--ntasks-per-node"],
  ["gpusPerNode", "--gpus-per-node"],
  ["gres", "--gres"],
  ["outputFile", "--output"],
  ["errorFile", "--error"]
];

export function parseSbatchDirectives(script: string): JobParameters {
  const params: JobParameters = {};
  for (const line of script.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("#SBATCH")) continue;
    for (const [key, flag] of DIRECTIVE_MAP) {
      const pattern = new RegExp(`^#SBATCH\\s+${flag}(?:=|\\s+)(.+)$`);
      const match = trimmed.match(pattern);
      if (!match) continue;
      const raw = match[1].trim();
      if (["cpus", "memory", "timeLimit", "nodes", "ntasksPerNode", "gpusPerNode"].includes(key)) {
        const numeric = Number(raw.replace(/[A-Za-z:]/g, ""));
        if (!Number.isNaN(numeric)) {
          (params as Record<string, unknown>)[key] = numeric;
        }
      } else {
        (params as Record<string, unknown>)[key] = raw;
      }
    }
  }
  return params;
}

export function updateScriptWithParameters(script: string, params: JobParameters): string {
  const bodyLines = script.split("\n").filter((line) => {
    const trimmed = line.trim();
    if (!trimmed.startsWith("#SBATCH")) return true;
    return !DIRECTIVE_MAP.some(([, flag]) => trimmed.startsWith(`#SBATCH ${flag}`));
  });

  const shebang = bodyLines[0]?.startsWith("#!") ? bodyLines.shift() : "#!/bin/bash";
  const directives = DIRECTIVE_MAP.flatMap(([key, flag]) => {
    const value = params[key];
    if (value == null || value === "") return [];
    const formattedValue = key === "memory" && typeof value === "number" ? `${value}G` : String(value);
    return [`#SBATCH ${flag}=${formattedValue}`];
  });

  return [shebang, ...directives, "", ...bodyLines.filter((line, index) => index !== 0 || line.trim() !== "")].join("\n");
}

export function validateLaunchParameters(params: JobParameters): string | null {
  if (params.cpus != null && (params.cpus < 1 || params.cpus > 256)) return "CPUs must be between 1 and 256.";
  if (params.memory != null && (params.memory < 1 || params.memory > 1024)) return "Memory must be between 1 and 1024 GB.";
  if (params.nodes != null && (params.nodes < 1 || params.nodes > 100)) return "Nodes must be between 1 and 100.";
  if (params.gpusPerNode != null && params.gpusPerNode < 0) return "GPUs per node cannot be negative.";
  if (!params.sourceDir?.trim()) return "Choose or enter a source directory before launching.";
  return null;
}

export function defaultScript(): string {
  return `#!/bin/bash
#SBATCH --job-name=my_job
#SBATCH --time=60
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1

echo "Starting job..."
`;
}
