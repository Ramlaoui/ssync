<script lang="ts">
  import type { JobInfo } from "../types/api";
  import LoadingSpinner from "./LoadingSpinner.svelte";

  interface Props {
    job?: JobInfo | null;
  }

  type GpuEntry = {
    count: number;
    type: string | null;
    perNode?: boolean;
  };

  type DetailRow = {
    label: string;
    value: string;
    mono?: boolean;
  };

  type StatCard = {
    label: string;
    value: string;
    frame: string;
    labelTone: string;
    valueTone: string;
  };

  const NODE_PREVIEW_LIMIT = 8;

  let { job = null }: Props = $props();

  function hasValue(value: string | null | undefined): value is string {
    return Boolean(
      value &&
      value !== "N/A" &&
      value !== "Unknown" &&
      value !== "None" &&
      value !== "(null)"
    );
  }

  function formatTime(time: string | null | undefined): string {
    if (!hasValue(time)) return "N/A";

    const timestamp = Date.parse(time);
    if (Number.isNaN(timestamp)) {
      return time;
    }

    return new Date(timestamp).toLocaleString();
  }

  function parseDurationToSeconds(
    value: number | string | null | undefined,
  ): number | null {
    if (value == null) return null;
    if (typeof value === "number") return Number.isFinite(value) ? value : null;
    if (!hasValue(value)) return null;

    if (/^\d+(?:\.\d+)?$/.test(value)) {
      return Number(value);
    }

    const [dayPart, timePart] = value.includes("-")
      ? value.split("-", 2)
      : [null, value];
    const segments = timePart.split(":").map((segment) => Number(segment));

    if (segments.some((segment) => Number.isNaN(segment))) {
      return null;
    }

    let seconds = 0;
    if (segments.length === 3) {
      seconds = segments[0] * 3600 + segments[1] * 60 + segments[2];
    } else if (segments.length === 2) {
      seconds = segments[0] * 60 + segments[1];
    } else if (segments.length === 1) {
      seconds = segments[0];
    } else {
      return null;
    }

    if (dayPart && /^\d+$/.test(dayPart)) {
      seconds += Number(dayPart) * 86400;
    }

    return seconds;
  }

  function formatDuration(
    value: number | string | null | undefined,
    fallback = "N/A",
  ): string {
    if (!hasValue(typeof value === "string" ? value : String(value ?? ""))) {
      return fallback;
    }

    const totalSeconds = parseDurationToSeconds(value);
    if (totalSeconds == null) {
      return typeof value === "string" ? value : fallback;
    }

    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = Math.floor(totalSeconds % 60);

    const parts = [];
    if (days > 0) parts.push(`${days}d`);
    if (hours > 0 || days > 0) parts.push(`${hours}h`);
    if (minutes > 0 || hours > 0 || days > 0) parts.push(`${minutes}m`);
    parts.push(`${seconds}s`);

    return parts.join(" ");
  }

  function formatMemory(memory: string | null | undefined): string {
    if (!hasValue(memory)) return "N/A";

    const match = memory.match(/^(\d+(?:\.\d+)?)([KMGTP]?)([nc]?)$/i);
    if (!match) return memory;

    const value = Number(match[1]);
    const unit = (match[2] || "M").toUpperCase();
    const suffix = match[3]?.toLowerCase();
    const scope =
      suffix === "n" ? " per node" : suffix === "c" ? " per CPU" : "";

    switch (unit) {
      case "K":
        return `${(value / 1024).toFixed(1)} MB${scope}`;
      case "M":
        return `${value} MB${scope}`;
      case "G":
        return `${value} GB${scope}`;
      case "T":
        return `${value} TB${scope}`;
      case "P":
        return `${value} PB${scope}`;
      default:
        return memory;
    }
  }

  function formatState(state: string | null | undefined): string {
    switch (state) {
      case "R":
        return "Running";
      case "PD":
        return "Pending";
      case "CD":
        return "Completed";
      case "F":
        return "Failed";
      case "CA":
        return "Cancelled";
      case "TO":
        return "Timeout";
      default:
        return state || "Unknown";
    }
  }

  function statusTone(state: string | null | undefined): string {
    switch (state) {
      case "R":
        return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
      case "PD":
        return "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300";
      case "CD":
        return "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300";
      case "F":
      case "CA":
      case "TO":
        return "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300";
      default:
        return "border-border bg-secondary/70 text-foreground";
    }
  }

  function normalizeGpuType(value: string | null | undefined): string | null {
    if (!value) return null;
    const normalized = value.trim();
    if (!normalized || normalized === "gpu" || normalized === "unknown") {
      return null;
    }
    return normalized;
  }

  function parseTresGpuEntries(raw: string | null | undefined): GpuEntry[] {
    if (!hasValue(raw)) return [];

    return raw
      .split(",")
      .map((token) => token.trim())
      .flatMap((token) => {
        const match = token.match(/^gres\/gpu(?::([^=]+))?=(\d+)$/);
        if (!match) return [];
        return [
          {
            count: Number(match[2]),
            type: normalizeGpuType(match[1]),
          },
        ];
      });
  }

  function parseGenericGpuEntries(
    raw: string | null | undefined,
    perNode = false,
  ): GpuEntry[] {
    if (!hasValue(raw)) return [];

    return raw
      .split(",")
      .map((token) => token.trim())
      .flatMap((token) => {
        const normalized = token.startsWith("gres:")
          ? token.slice(5)
          : token;
        if (!normalized.startsWith("gpu")) return [];

        const parts = normalized.split(":").filter(Boolean);
        const countToken = parts[parts.length - 1];
        if (!countToken || !/^\d+$/.test(countToken)) return [];

        const type = normalizeGpuType(parts.slice(1, -1).join(":"));
        return [
          {
            count: Number(countToken),
            type,
            perNode,
          },
        ];
      });
  }

  function summarizeGpuEntries(
    entries: GpuEntry[],
    nodes: string | null | undefined,
  ): string | null {
    if (entries.length === 0) return null;

    const nodeCount = hasValue(nodes) ? Number.parseInt(nodes, 10) : Number.NaN;
    const perType = new Map<string, number>();
    let total = 0;
    let usedPerNodeMultiplier = false;

    for (const entry of entries) {
      const multiplier =
        entry.perNode && Number.isFinite(nodeCount) && nodeCount > 0
          ? nodeCount
          : 1;
      const effectiveCount = entry.count * multiplier;
      total += effectiveCount;
      const label = entry.type || "GPU";
      perType.set(label, (perType.get(label) || 0) + effectiveCount);
      if (multiplier > 1) {
        usedPerNodeMultiplier = true;
      }
    }

    if (!total) return null;

    const breakdown = Array.from(perType.entries()).map(([label, count]) =>
      label === "GPU" ? `${count}` : `${count} x ${label}`,
    );

    if (breakdown.length === 1) {
      return breakdown[0] + (usedPerNodeMultiplier ? " total" : "");
    }

    return breakdown.join(", ");
  }

  function getAllocatedGpuSummary(jobInfo: JobInfo): string | null {
    const allocEntries = parseTresGpuEntries(jobInfo.alloc_tres);
    const allocSummary = summarizeGpuEntries(allocEntries, jobInfo.nodes);
    if (allocSummary) return allocSummary;

    const genericSummary = summarizeGpuEntries(
      parseGenericGpuEntries(jobInfo.gres),
      jobInfo.nodes,
    );
    if (genericSummary) return genericSummary;

    return summarizeGpuEntries(
      parseGenericGpuEntries(jobInfo.tres_per_node, true),
      jobInfo.nodes,
    );
  }

  function getRequestedGpuSummary(jobInfo: JobInfo): string | null {
    const requestedEntries = parseTresGpuEntries(jobInfo.req_tres);
    const requestedSummary = summarizeGpuEntries(requestedEntries, jobInfo.nodes);
    if (requestedSummary) return requestedSummary;

    const genericSummary = summarizeGpuEntries(
      parseGenericGpuEntries(jobInfo.gres),
      jobInfo.nodes,
    );
    if (genericSummary) return genericSummary;

    return summarizeGpuEntries(
      parseGenericGpuEntries(jobInfo.tres_per_node, true),
      jobInfo.nodes,
    );
  }

  function buildRows(
    rows: Array<{
      label: string;
      value: string | null | undefined;
      format?: (value: string) => string;
      mono?: boolean;
    }>,
  ): DetailRow[] {
    return rows
      .filter((row) => hasValue(row.value))
      .map((row) => ({
        label: row.label,
        value: row.format ? row.format(row.value as string) : (row.value as string),
        mono: row.mono,
      }));
  }

  function buildStatCards(jobInfo: JobInfo): StatCard[] {
    const allocatedGpu = getAllocatedGpuSummary(jobInfo);

    return [
      {
        label: "Status",
        value: formatState(jobInfo.state),
        frame: "border-sky-200/80 bg-sky-50/90 dark:border-sky-900/55 dark:bg-sky-950/28",
        labelTone: "text-sky-700 dark:text-sky-300",
        valueTone: "text-sky-950 dark:text-sky-100",
      },
      {
        label: "Runtime",
        value: formatDuration(jobInfo.runtime),
        frame: "border-emerald-200/80 bg-emerald-50/90 dark:border-emerald-900/55 dark:bg-emerald-950/28",
        labelTone: "text-emerald-700 dark:text-emerald-300",
        valueTone: "text-emerald-950 dark:text-emerald-100",
      },
      {
        label: "Nodes",
        value: hasValue(jobInfo.nodes) ? jobInfo.nodes : "N/A",
        frame: "border-violet-200/80 bg-violet-50/90 dark:border-violet-900/55 dark:bg-violet-950/28",
        labelTone: "text-violet-700 dark:text-violet-300",
        valueTone: "text-violet-950 dark:text-violet-100",
      },
      {
        label: "CPUs",
        value: hasValue(jobInfo.cpus) ? jobInfo.cpus : "N/A",
        frame: "border-amber-200/80 bg-amber-50/90 dark:border-amber-900/55 dark:bg-amber-950/28",
        labelTone: "text-amber-700 dark:text-amber-300",
        valueTone: "text-amber-950 dark:text-amber-100",
      },
      {
        label: "Memory",
        value: formatMemory(jobInfo.memory),
        frame: "border-rose-200/80 bg-rose-50/90 dark:border-rose-900/55 dark:bg-rose-950/28",
        labelTone: "text-rose-700 dark:text-rose-300",
        valueTone: "text-rose-950 dark:text-rose-100",
      },
      {
        label: "GPUs",
        value: allocatedGpu || "N/A",
        frame: "border-cyan-200/80 bg-cyan-50/90 dark:border-cyan-900/55 dark:bg-cyan-950/28",
        labelTone: "text-cyan-700 dark:text-cyan-300",
        valueTone: "text-cyan-950 dark:text-cyan-100",
      },
    ];
  }

  function hasRows(rows: DetailRow[]): boolean {
    return rows.length > 0;
  }

  let allocatedGpuSummary = $derived(job ? getAllocatedGpuSummary(job) : null);
  let requestedGpuSummary = $derived(job ? getRequestedGpuSummary(job) : null);
  let statCards = $derived(job ? buildStatCards(job) : []);
  let identityRows = $derived(
    job
      ? buildRows([
          { label: "User", value: job.user },
          { label: "Cluster", value: job.hostname },
          { label: "Partition", value: job.partition },
          { label: "Account", value: job.account },
          { label: "QOS", value: job.qos },
          { label: "Batch Host", value: job.batch_host },
        ])
      : [],
  );
  let timingRows = $derived(
    job
      ? buildRows([
          { label: "Submitted", value: job.submit_time, format: formatTime },
          { label: "Started", value: job.start_time, format: formatTime },
          { label: "Ended", value: job.end_time, format: formatTime },
          { label: "Runtime", value: formatDuration(job.runtime, "N/A") },
          { label: "Time Limit", value: job.time_limit },
        ])
      : [],
  );
  let allocationRows = $derived(
    job
      ? buildRows([
          { label: "Node Count", value: job.nodes },
          { label: "CPU Count", value: job.cpus },
          { label: "Memory", value: formatMemory(job.memory) },
          { label: "Allocated GPUs", value: allocatedGpuSummary ?? undefined },
          {
            label: "Requested GPUs",
            value:
              requestedGpuSummary && requestedGpuSummary !== allocatedGpuSummary
                ? requestedGpuSummary
                : undefined,
          },
          { label: "Node Expression", value: job.node_list, mono: true },
        ])
      : [],
  );
  let fileRows = $derived(
    job
      ? buildRows([
          { label: "Working Directory", value: job.work_dir, mono: true },
          { label: "Stdout", value: job.stdout_file, mono: true },
          { label: "Stderr", value: job.stderr_file, mono: true },
        ])
      : [],
  );
  let metadataRows = $derived(
    job
      ? buildRows([
          { label: "Reason", value: job.reason !== job.node_list ? job.reason : undefined },
          { label: "Exit Code", value: job.exit_code },
          { label: "Priority", value: job.priority },
          {
            label: "Array",
            value: hasValue(job.array_job_id)
              ? `${job.array_job_id}${hasValue(job.array_task_id) ? ` / task ${job.array_task_id}` : ""}`
              : undefined,
          },
        ])
      : [],
  );
  let rawSchedulerRows = $derived(
    job
      ? buildRows([
          { label: "Allocated TRES", value: job.alloc_tres, mono: true },
          { label: "Requested TRES", value: job.req_tres, mono: true },
          { label: "GRES", value: job.gres, mono: true },
          { label: "TRES Per Node", value: job.tres_per_node, mono: true },
          { label: "Submit Command", value: job.submit_line, mono: true },
        ])
      : [],
  );
  let previewNodeHostnames = $derived(
    job?.node_hostnames?.slice(0, NODE_PREVIEW_LIMIT) ?? [],
  );
  let hiddenNodeCount = $derived(
    Math.max((job?.node_hostnames?.length ?? 0) - NODE_PREVIEW_LIMIT, 0),
  );
</script>

{#if job}
  <div class="p-4 md:p-6 w-full">
    <div class="space-y-4">
      <section class="rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
        <div class="px-5 py-5 md:px-6 md:py-6 bg-card">
          <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div class="min-w-0 space-y-3">
              <div class="flex flex-wrap items-center gap-2">
                <span class={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${statusTone(job.state)}`}>
                  {formatState(job.state)}{job.state ? ` (${job.state})` : ""}
                </span>
                {#if hasValue(job.partition)}
                  <span class="inline-flex items-center rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-medium text-muted-foreground">
                    {job.partition}
                  </span>
                {/if}
                <span class="inline-flex items-center rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-medium text-muted-foreground">
                  {job.hostname}
                </span>
              </div>

              <div class="space-y-1 min-w-0">
                <h2 class="text-xl md:text-2xl font-semibold tracking-tight text-foreground truncate">
                  {hasValue(job.name) ? job.name : `Job ${job.job_id}`}
                </h2>
                <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                  <span class="font-mono text-foreground">#{job.job_id}</span>
                  {#if hasValue(job.user)}
                    <span>{job.user}</span>
                  {/if}
                  {#if hasValue(job.account)}
                    <span>{job.account}</span>
                  {/if}
                </div>
              </div>
            </div>

            <div class="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3 w-full xl:w-auto">
              {#each statCards as card}
                <div class={`rounded-2xl border px-4 py-3 min-w-0 shadow-sm ${card.frame}`}>
                  <div class={`text-[11px] font-semibold uppercase tracking-[0.14em] ${card.labelTone}`}>
                    {card.label}
                  </div>
                  <div class={`mt-1 text-sm font-semibold break-words ${card.valueTone}`}>
                    {card.value}
                  </div>
                </div>
              {/each}
            </div>
          </div>
        </div>
      </section>

      <section class="grid grid-cols-1 items-stretch md:grid-cols-2 xl:grid-cols-12 gap-4">
        {#if hasRows(identityRows)}
          <section class="h-full rounded-2xl border border-border bg-card shadow-sm p-5 xl:col-span-4">
            <h3 class="mb-5 text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
              Identity
            </h3>
            <div class="space-y-2">
              {#each identityRows as row}
                <div class="flex items-start justify-between gap-3 rounded-xl px-3 py-2.5">
                  <span class="text-[13px] text-muted-foreground">{row.label}</span>
                  <span class={`text-[13px] font-medium text-right text-foreground ${row.mono ? "font-mono break-all" : ""}`}>
                    {row.value}
                  </span>
                </div>
              {/each}
            </div>
          </section>
        {/if}

        {#if hasRows(timingRows)}
          <section class="h-full rounded-2xl border border-border bg-card shadow-sm p-5 xl:col-span-4">
            <h3 class="mb-5 text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
              Timing
            </h3>
            <div class="space-y-2">
              {#each timingRows as row}
                <div class="flex items-start justify-between gap-3 rounded-xl px-3 py-2.5">
                  <span class="text-[13px] text-muted-foreground">{row.label}</span>
                  <span class="text-[13px] font-medium text-right text-foreground">
                    {row.value}
                  </span>
                </div>
              {/each}
            </div>
          </section>
        {/if}

        {#if hasRows(allocationRows) || (job.node_hostnames && job.node_hostnames.length > 0)}
          <section class="h-full rounded-2xl border border-border bg-card shadow-sm p-5 md:col-span-2 xl:col-span-4">
            <div class="flex items-center justify-between gap-3 mb-3">
              <h3 class="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                Allocation
              </h3>
              {#if job.node_hostnames && job.node_hostnames.length > 0}
                <span class="text-xs font-medium text-muted-foreground">
                  {job.node_hostnames.length} nodes
                </span>
              {/if}
            </div>

            {#if hasRows(allocationRows)}
              <div class="space-y-2">
                {#each allocationRows as row}
                  <div class="flex items-start justify-between gap-3 rounded-xl px-3 py-2.5">
                    <span class="text-[13px] text-muted-foreground">{row.label}</span>
                    <span class={`text-[13px] font-medium text-right text-foreground ${row.mono ? "font-mono break-all" : ""}`}>
                      {row.value}
                    </span>
                  </div>
                {/each}
              </div>
            {/if}

            {#if job.node_hostnames && job.node_hostnames.length > 0}
              <div class="mt-4 rounded-xl border border-border bg-background/40 p-3.5">
                <div class="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  Allocated Nodes
                </div>
                <div class="flex flex-wrap gap-2">
                  {#each previewNodeHostnames as nodeHostname}
                    <span class="rounded-lg border border-border bg-background/70 px-2.5 py-1.5 text-xs font-mono text-foreground">
                      {nodeHostname}
                    </span>
                  {/each}
                  {#if hiddenNodeCount > 0}
                    <span class="rounded-lg border border-dashed border-border bg-background/70 px-2.5 py-1.5 text-xs font-medium text-muted-foreground">
                      +{hiddenNodeCount} more
                    </span>
                  {/if}
                </div>
              </div>
            {/if}
          </section>
        {/if}

        {#if hasRows(metadataRows)}
          <section class="h-full rounded-2xl border border-border bg-card shadow-sm p-5 md:col-span-2 xl:col-span-12">
            <h3 class="mb-5 text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
              Key Metadata
            </h3>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-2">
              {#each metadataRows as row}
                <div class="flex items-start justify-between gap-3 rounded-xl px-3 py-2.5">
                  <span class="text-[13px] text-muted-foreground">{row.label}</span>
                  <span class={`text-[13px] font-medium text-right text-foreground ${row.mono ? "font-mono break-all" : ""}`}>
                    {row.value}
                  </span>
                </div>
              {/each}
            </div>
          </section>
        {/if}
      </section>

      {#if hasRows(fileRows) || hasRows(rawSchedulerRows)}
        <section class="grid grid-cols-1 items-stretch xl:grid-cols-2 gap-4">
          {#if hasRows(fileRows)}
            <section class="h-full rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
              <div class="px-5 py-4">
                <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                  Files & Paths
                </div>
                <div class="mt-1 text-sm text-muted-foreground">
                  Working directory and output locations
                </div>
              </div>
              <div class="border-t border-border px-5 py-4 space-y-3 bg-transparent">
                {#each fileRows as row}
                  <div class="rounded-xl border border-border bg-background/40 px-4 py-3">
                    <div class="text-sm text-muted-foreground mb-2">{row.label}</div>
                    <div class="text-sm font-mono text-foreground break-all">{row.value}</div>
                  </div>
                {/each}
              </div>
            </section>
          {/if}

          {#if hasRows(rawSchedulerRows)}
            <section class="h-full rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
              <div class="px-5 py-4">
                <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                  Raw Scheduler Data
                </div>
                <div class="mt-1 text-sm text-muted-foreground">
                  Low-level SLURM allocation fields and submit line
                </div>
              </div>
              <div class="border-t border-border px-5 py-4 space-y-3 bg-transparent">
                {#each rawSchedulerRows as row}
                  <div class="rounded-xl border border-border bg-background/40 px-4 py-3">
                    <div class="text-sm text-muted-foreground mb-2">{row.label}</div>
                    <div class={`text-sm text-foreground ${row.mono ? "font-mono break-all" : "font-medium"}`}>
                      {row.value}
                    </div>
                  </div>
                {/each}
              </div>
            </section>
          {/if}
        </section>
      {/if}
    </div>
  </div>
{:else}
  <div class="h-64">
    <LoadingSpinner message="Loading job details..." />
  </div>
{/if}
