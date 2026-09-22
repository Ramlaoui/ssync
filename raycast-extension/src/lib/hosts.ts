import type { SlurmDefaults } from "../types/ssync";
export const hostDefaultFields = [
  ["partition", "Partition"],
  ["account", "Account"],
  ["constraint", "Constraint"],
  ["qos", "Quality of Service"],
  ["cpus", "CPUs"],
  ["mem", "Memory (GB)"],
  ["time", "Time Limit"],
  ["nodes", "Nodes"],
  ["ntasks_per_node", "Tasks per Node"],
  ["gpus_per_node", "GPUs per Node"],
  ["gres", "Generic Resources"],
] as const;
const numeric = new Set([
  "cpus",
  "mem",
  "nodes",
  "ntasks_per_node",
  "gpus_per_node",
]);
export function parseHostDefaults(
  values: Record<string, string>,
): SlurmDefaults {
  const defaults: Record<string, string | number | null> = {};
  for (const [key, label] of hostDefaultFields) {
    const value = (values[key] || "").trim();
    if (!value) {
      defaults[key] = null;
      continue;
    }
    if (numeric.has(key)) {
      const parsed = Number(value);
      if (
        !Number.isSafeInteger(parsed) ||
        parsed < (key === "gpus_per_node" ? 0 : 1)
      )
        throw new Error(label + " must be a valid whole number.");
      defaults[key] = parsed;
    } else {
      if (value.length > 256 || /[\r\n\0]/.test(value))
        throw new Error(label + " must be one line of at most 256 characters.");
      defaults[key] = value;
    }
  }
  return defaults as SlurmDefaults;
}
