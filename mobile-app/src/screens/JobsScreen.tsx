import React, { useMemo, useState } from "react";
import * as Clipboard from "expo-clipboard";
import * as FileSystem from "expo-file-system";
import * as Sharing from "expo-sharing";
import JSZip from "jszip";
import { Bell, ChevronDown, ChevronRight, Copy, Download, Layers, RefreshCw, Search, Server, ShieldX, SlidersHorizontal } from "lucide-react-native";
import type { LucideIcon } from "lucide-react-native";
import { Alert, FlatList, Image, LayoutAnimation, Platform, Pressable, ScrollView, StyleSheet, TextInput, UIManager, View } from "react-native";

import type { SsyncApiClient } from "../api/client";
import { AppText, Button, Card, Chip, EmptyState, IconButton, SectionHeader, Sheet, StatusBadge } from "../components/ui";
import type { Palette } from "../theme/colors";
import type { ArrayJobGroup, HostInfo, JobInfo, PartitionStatusResponse } from "../types/api";
import { compactJobTitle, formatTimeAgo, jobKey, stateLabel, stateTone } from "../utils/format";
import { jobStatusColors } from "../utils/statusColors";
import type { JobNotificationConfig, LaunchDraft } from "../types/settings";

type JobsScreenProps = {
  palette: Palette;
  api: SsyncApiClient;
  hosts: HostInfo[];
  jobs: JobInfo[];
  arrayGroups: ArrayJobGroup[];
  partitions: PartitionStatusResponse[];
  loading: boolean;
  loadingPartitions: boolean;
  wsConnected: boolean;
  lastSyncAt: number | null;
  jobNotifications: Record<string, JobNotificationConfig>;
  onRefresh: (filters?: Record<string, unknown>, force?: boolean) => void;
  onHostFilterChange?: (host?: string) => void;
  onOpenJob: (job: JobInfo) => void;
  onResubmitDraft: (draft: LaunchDraft) => void;
  onConfigureJobNotifications: (job: JobInfo) => void;
};

const stateOptions = ["", "R", "PD", "CD", "F", "CA", "TO"];
type FeedbackTone = "neutral" | "success" | "warning" | "danger" | "info";
type JobsListItem =
  | { type: "array"; group: ArrayJobGroup }
  | { type: "empty" }
  | { type: "job"; job: JobInfo };

if (Platform.OS === "android") {
  UIManager.setLayoutAnimationEnabledExperimental?.(true);
}

function animateListLayout() {
  LayoutAnimation.configureNext({
    duration: 190,
    create: {
      type: LayoutAnimation.Types.easeInEaseOut,
      property: LayoutAnimation.Properties.opacity
    },
    update: {
      type: LayoutAnimation.Types.easeInEaseOut
    },
    delete: {
      type: LayoutAnimation.Types.easeInEaseOut,
      property: LayoutAnimation.Properties.opacity
    }
  });
}

function normalizeHost(hostname: string | null | undefined) {
  return String(hostname || "").trim().toLowerCase();
}

function toneColors(palette: Palette, tone: FeedbackTone) {
  if (tone === "success") return { background: palette.successSoft, border: palette.success, text: palette.success };
  if (tone === "warning") return { background: palette.warningSoft, border: palette.warning, text: palette.warning };
  if (tone === "danger") return { background: palette.dangerSoft, border: palette.danger, text: palette.danger };
  if (tone === "info") return { background: palette.infoSoft, border: palette.info, text: palette.info };
  return { background: palette.surfaceAlt, border: palette.border, text: palette.muted };
}

function resourceTone(used: number | null | undefined, total: number | null | undefined): FeedbackTone {
  if (used == null || total == null || total <= 0) return "neutral";
  const ratio = used / total;
  if (ratio >= 0.9) return "danger";
  if (ratio >= 0.7) return "warning";
  if (ratio >= 0.35) return "info";
  return "success";
}

function jobPriority(job: JobInfo) {
  if (job.state === "R") return 0;
  if (job.state === "PD") return 1;
  if (["F", "CA", "TO"].includes(String(job.state))) return 2;
  if (job.state === "CD") return 3;
  return 4;
}

function jobTime(job: JobInfo) {
  return Date.parse(job.submit_time || job.start_time || job.end_time || "0") || 0;
}

function arrayGroupPriority(group: ArrayJobGroup) {
  if (group.running_count > 0) return 0;
  if (group.pending_count > 0) return 1;
  if (group.failed_count + group.cancelled_count > 0) return 2;
  if (group.completed_count > 0) return 3;
  return 4;
}

function arrayGroupTime(group: ArrayJobGroup) {
  return group.tasks.reduce((latest, task) => Math.max(latest, jobTime(task)), 0);
}

function arrayGroupState(group: ArrayJobGroup) {
  if (group.failed_count > 0) return "F";
  if (group.cancelled_count > 0) return "CA";
  if (group.running_count > 0) return "R";
  if (group.pending_count > 0) return "PD";
  if (group.completed_count > 0) return "CD";
  return "UNKNOWN";
}

function jobMatchesTerm(job: JobInfo, term: string) {
  return [job.job_id, job.name, job.user, job.hostname, job.partition, job.state, job.array_job_id, job.array_task_id, job.node_list]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(term));
}

function arrayTaskKey(task: JobInfo, fallbackHostname: string) {
  return jobKey(task.job_id, task.hostname || fallbackHostname);
}

function arrayGroupKey(group: ArrayJobGroup) {
  return `${group.hostname}:${group.array_job_id}`;
}

function taskDisplayId(task: JobInfo) {
  return task.array_task_id || task.job_id.split("_").pop() || task.job_id;
}

function displayJobName(job: JobInfo) {
  return job.name && job.name !== job.job_id ? job.name : "Untitled job";
}

export function JobsScreen({
  palette,
  api,
  hosts,
  jobs,
  arrayGroups,
  partitions,
  loading,
  loadingPartitions,
  wsConnected,
  lastSyncAt,
  jobNotifications,
  onRefresh,
  onHostFilterChange,
  onOpenJob,
  onResubmitDraft,
  onConfigureJobNotifications
}: JobsScreenProps) {
  const [search, setSearch] = useState("");
  const [host, setHost] = useState("");
  const [state, setState] = useState("");
  const [scope, setScope] = useState<"all" | "active" | "completed">("all");
  const [showFilters, setShowFilters] = useState(false);
  const [showPartitions, setShowPartitions] = useState(false);
  const [arraysExpanded, setArraysExpanded] = useState(true);
  const [expandedArrayGroups, setExpandedArrayGroups] = useState<Set<string>>(new Set());
  const [arrayTaskLimits, setArrayTaskLimits] = useState<Record<string, number>>({});
  const [actionJob, setActionJob] = useState<JobInfo | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const selectedHost = normalizeHost(host);

  const arrayTaskKeys = useMemo(() => {
    const keys = new Set<string>();
    arrayGroups.forEach((group) => {
      group.tasks.forEach((task) => {
        if (task.job_id) keys.add(arrayTaskKey(task, group.hostname));
      });
    });
    return keys;
  }, [arrayGroups]);

  const hostOptions = useMemo(() => {
    const names = new Set<string>();
    const counts = new Map<string, number>();

    hosts.forEach((item) => {
      if (item.hostname) names.add(item.hostname);
    });
    jobs.forEach((job) => {
      if (!job.hostname) return;
      if (arrayTaskKeys.has(jobKey(job.job_id, job.hostname))) return;
      names.add(job.hostname);
      counts.set(job.hostname, (counts.get(job.hostname) || 0) + 1);
    });
    arrayGroups.forEach((group) => {
      if (!group.hostname) return;
      names.add(group.hostname);
      counts.set(group.hostname, (counts.get(group.hostname) || 0) + group.total_tasks);
    });
    partitions.forEach((partition) => {
      if (partition.hostname) names.add(partition.hostname);
    });

    return Array.from(names)
      .sort((left, right) => left.localeCompare(right))
      .map((hostname) => ({ hostname, count: counts.get(hostname) || 0 }));
  }, [arrayGroups, arrayTaskKeys, hosts, jobs, partitions]);

  function matchesSelectedHost(hostname: string | null | undefined) {
    return !selectedHost || normalizeHost(hostname) === selectedHost;
  }

  const filteredJobs = useMemo(() => {
    const term = search.trim().toLowerCase();
    return jobs
      .filter((job) => {
        if (arrayTaskKeys.has(jobKey(job.job_id, job.hostname))) return false;
        if (!matchesSelectedHost(job.hostname)) return false;
        if (state && job.state !== state) return false;
        if (scope === "active" && job.state !== "R" && job.state !== "PD") return false;
        if (scope === "completed" && !["CD", "F", "CA", "TO"].includes(String(job.state))) return false;
        if (!term) return true;
        return jobMatchesTerm(job, term);
      })
      .sort((left, right) => {
        const priority = jobPriority(left) - jobPriority(right);
        return priority || jobTime(right) - jobTime(left) || right.job_id.localeCompare(left.job_id);
      });
  }, [arrayTaskKeys, jobs, scope, search, selectedHost, state]);

  const filteredArrays = useMemo(() => {
    const term = search.trim().toLowerCase();
    return arrayGroups
      .filter((group) => {
        if (!matchesSelectedHost(group.hostname)) return false;
        if (state && !group.tasks.some((job) => job.state === state)) return false;
        if (scope === "active" && group.pending_count + group.running_count === 0) return false;
        if (scope === "completed" && group.completed_count + group.failed_count + group.cancelled_count === 0) return false;
        if (!term) return true;
        return (
          [group.array_job_id, group.job_name, group.user, group.hostname].filter(Boolean).some((value) =>
            String(value).toLowerCase().includes(term)
          ) || group.tasks.some((task) => jobMatchesTerm(task, term))
        );
      })
      .sort((left, right) => {
        const priority = arrayGroupPriority(left) - arrayGroupPriority(right);
        return priority || arrayGroupTime(right) - arrayGroupTime(left) || right.array_job_id.localeCompare(left.array_job_id);
      });
  }, [arrayGroups, scope, search, selectedHost, state]);

  const filteredPartitions = useMemo(
    () => partitions.filter((partition) => matchesSelectedHost(partition.hostname)),
    [partitions, selectedHost]
  );

  const totalJobs = filteredJobs.length + filteredArrays.reduce((sum, group) => sum + group.total_tasks, 0);
  const totalPartitions = filteredPartitions.reduce((sum, item) => sum + item.partitions.length, 0);
  const activeArrayCount = filteredArrays.filter((group) => group.running_count + group.pending_count > 0).length;
  const visibleHostCount = selectedHost ? 1 : hostOptions.length;
  const hostLabel = selectedHost ? hostOptions.find((item) => normalizeHost(item.hostname) === selectedHost)?.hostname || host : "all hosts";
  const activeFilters: Array<{ label: string; tone: FeedbackTone }> = [
    ...(selectedHost ? [{ label: hostLabel, tone: "info" as const }] : []),
    ...(scope !== "all" ? [{ label: scope === "active" ? "Active" : "Completed", tone: scope === "active" ? "success" as const : "info" as const }] : []),
    ...(state ? [{ label: stateLabel(state), tone: stateTone(state) }] : [])
  ];
  const listItems = useMemo<JobsListItem[]>(() => {
    if (loading && filteredJobs.length === 0 && filteredArrays.length === 0) return [{ type: "empty" }];
    if (filteredJobs.length === 0 && filteredArrays.length === 0) return [{ type: "empty" }];
    return [
      ...(arraysExpanded ? filteredArrays.map((group) => ({ type: "array" as const, group })) : []),
      ...filteredJobs.map((job) => ({ type: "job" as const, job }))
    ];
  }, [arraysExpanded, filteredArrays, filteredJobs, loading]);

  function currentFilters() {
    return {
      host: host || undefined,
      state: state || undefined,
      search: search.trim() || undefined,
      activeOnly: scope === "active" || undefined,
      completedOnly: scope === "completed" || undefined
    };
  }

  function selectHost(nextHost: string) {
    const selected = normalizeHost(nextHost) === selectedHost ? "" : nextHost;
    setHost(selected);
    onHostFilterChange?.(selected || undefined);
  }

  function clearHost() {
    setHost("");
    onHostFilterChange?.(undefined);
  }

  function resetFilters() {
    setScope("all");
    setState("");
    clearHost();
  }

  function toggleArrayGroup(group: ArrayJobGroup) {
    const key = arrayGroupKey(group);
    animateListLayout();
    setExpandedArrayGroups((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function showMoreArrayTasks(group: ArrayJobGroup, total: number) {
    const key = arrayGroupKey(group);
    setArrayTaskLimits((current) => ({
      ...current,
      [key]: Math.min((current[key] || 50) + 50, total)
    }));
  }

  function closeJobActions() {
    if (actionLoading) return;
    setActionJob(null);
  }

  async function resubmitJob(job: JobInfo) {
    setActionLoading("resubmit");
    try {
      const script = await api.getJobScript(job.job_id, job.hostname);
      setActionJob(null);
      onResubmitDraft({
        id: `${job.hostname}:${job.job_id}:${Date.now()}`,
        sourceJobId: job.job_id,
        sourceJobName: job.name,
        scriptContent: script.script_content,
        host: job.hostname,
        sourceDir: script.local_source_dir || job.work_dir || ""
      });
    } catch (error) {
      Alert.alert("Resubmit unavailable", (error as Error).message || "Failed to load the previous job script.");
    } finally {
      setActionLoading(null);
    }
  }

  function confirmCancelJob(job: JobInfo) {
    Alert.alert("Cancel job", `Cancel ${compactJobTitle(job)} on ${job.hostname}?`, [
      { text: "Keep running", style: "cancel" },
      {
        text: "Cancel job",
        style: "destructive",
        onPress: async () => {
          setActionLoading("cancel");
          try {
            await api.cancelJob(job.job_id, job.hostname);
            setActionJob(null);
            onRefresh(currentFilters(), true);
          } catch (error) {
            Alert.alert("Cancel failed", (error as Error).message || "Failed to cancel job.");
          } finally {
            setActionLoading(null);
          }
        }
      }
    ]);
  }

  async function shareOutput(job: JobInfo, type: "stdout" | "stderr") {
    setActionLoading(type);
    try {
      const response = await api.getJobOutput(job.job_id, job.hostname, type, true);
      const content = type === "stdout" ? response.stdout : response.stderr;
      if (!content) {
        Alert.alert(type === "stdout" ? "No output" : "No errors", "No content is available for this stream.");
        return;
      }
      const safeJobId = job.job_id.replace(/[^a-zA-Z0-9_.-]/g, "_");
      const file = new FileSystem.File(FileSystem.Paths.cache, `ssync-${safeJobId}-${type}.txt`);
      file.write(content);
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(file.uri, {
          mimeType: "text/plain",
          dialogTitle: `${compactJobTitle(job)} ${type}`
        });
      } else {
        await Clipboard.setStringAsync(content);
        Alert.alert("Copied", `${type} content was copied to the clipboard.`);
      }
    } catch (error) {
      Alert.alert("Output unavailable", (error as Error).message || `Failed to load ${type}.`);
    } finally {
      setActionLoading(null);
    }
  }

  async function shareJobBundle(job: JobInfo) {
    setActionLoading("bundle");
    try {
      const zip = new JSZip();
      const safeJobId = job.job_id.replace(/[^a-zA-Z0-9_.-]/g, "_");
      const bundleName = `ssync-${safeJobId}-${job.hostname}`;

      zip.file("summary.txt", jobSummaryText(job));
      zip.file("metadata.json", JSON.stringify(job, null, 2));

      const notes: string[] = [];
      const [scriptResult, outputResult] = await Promise.allSettled([
        api.getJobScript(job.job_id, job.hostname),
        api.getJobOutput(job.job_id, job.hostname, "both", true)
      ]);

      if (scriptResult.status === "fulfilled") {
        zip.file("script.sh", scriptResult.value.script_content || "");
      } else {
        notes.push(`script.sh unavailable: ${readError(scriptResult.reason)}`);
      }

      if (outputResult.status === "fulfilled") {
        const output = outputResult.value;
        zip.file("stdout.txt", output.stdout || "");
        zip.file("stderr.txt", output.stderr || "");
        zip.file(
          "output-metadata.json",
          JSON.stringify(
            {
              stdout: output.stdout_metadata,
              stderr: output.stderr_metadata,
              truncated: output.content_truncated,
              limit_bytes: output.content_limit_bytes,
              cached: output.cached,
              stale: output.stale
            },
            null,
            2
          )
        );
      } else {
        notes.push(`stdout.txt/stderr.txt unavailable: ${readError(outputResult.reason)}`);
      }

      if (notes.length > 0) {
        zip.file("export-notes.txt", notes.join("\n"));
      }

      const bytes = await zip.generateAsync({ type: "uint8array", compression: "DEFLATE" });
      const file = new FileSystem.File(FileSystem.Paths.cache, `${bundleName}.zip`);
      file.write(bytes);

      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(file.uri, {
          mimeType: "application/zip",
          dialogTitle: `${compactJobTitle(job)} bundle`
        });
      } else {
        await Clipboard.setStringAsync(jobSummaryText(job));
        Alert.alert("Sharing unavailable", "The job summary was copied to the clipboard instead.");
      }
    } catch (error) {
      Alert.alert("Export failed", (error as Error).message || "Failed to export job bundle.");
    } finally {
      setActionLoading(null);
    }
  }

  async function copyJobSummary(job: JobInfo) {
    await Clipboard.setStringAsync(jobSummaryText(job));
    setActionJob(null);
  }

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      <View style={[styles.header, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <Image source={require("../../assets/brand/icon.png")} style={styles.appIcon} />
        <View style={{ flex: 1 }}>
          <AppText palette={palette} size={22} weight="900">Jobs</AppText>
          <AppText palette={palette} muted size={12}>
            {visibleHostCount} {visibleHostCount === 1 ? "host" : "hosts"} - {totalJobs} jobs - {wsConnected ? "live" : "polling"}
          </AppText>
        </View>
        <IconButton
          palette={palette}
          icon={Layers}
          label="Partition resources"
          variant={totalPartitions > 0 ? "secondary" : "ghost"}
          onPress={() => setShowPartitions(true)}
        />
        <IconButton
          palette={palette}
          icon={SlidersHorizontal}
          label="Filters"
          variant={activeFilters.length > 0 ? "primary" : "secondary"}
          onPress={() => setShowFilters(true)}
        />
        <IconButton palette={palette} icon={RefreshCw} label="Refresh" onPress={() => onRefresh(currentFilters(), true)} disabled={loading} />
      </View>

      <FlatList
        data={listItems}
        keyExtractor={(item) => {
          if (item.type === "array") return `array:${arrayGroupKey(item.group)}`;
          if (item.type === "job") return `job:${jobKey(item.job.job_id, item.job.hostname)}`;
          return "empty";
        }}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={styles.content}
        initialNumToRender={10}
        maxToRenderPerBatch={10}
        windowSize={7}
        removeClippedSubviews
        ListHeaderComponent={
          <View style={styles.listHeader}>
            <View style={[styles.compactSearch, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <View style={[styles.searchBox, { backgroundColor: palette.surfaceAlt, borderColor: palette.border }]}>
                <Search size={18} color={palette.muted} />
                <TextInput
                  value={search}
                  onChangeText={setSearch}
                  placeholder="Search jobs"
                  placeholderTextColor={palette.subtle}
                  autoCapitalize="none"
                  style={[styles.searchInput, { color: palette.text }]}
                />
              </View>
              {activeFilters.length > 0 ? (
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.activeFilterRow}>
                  {activeFilters.map((filter, index) => (
                    <Chip key={`${filter.label}-${index}`} palette={palette} label={filter.label} active tone={filter.tone} onPress={() => setShowFilters(true)} />
                  ))}
                </ScrollView>
              ) : null}
              <AppText palette={palette} muted size={11}>
                {lastSyncAt ? `Updated ${formatTimeAgo(new Date(lastSyncAt).toISOString())}` : "Waiting for first sync"}
              </AppText>
            </View>

            {filteredArrays.length > 0 ? (
              <View style={[styles.arrayHeaderCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ expanded: arraysExpanded }}
                  onPress={() => {
                    animateListLayout();
                    setArraysExpanded((value) => !value);
                  }}
                  style={styles.collapsibleHeader}
                >
                  <View style={[styles.collapseIcon, { backgroundColor: palette.surfaceAlt, borderColor: palette.border }]}>
                    {arraysExpanded ? <ChevronDown size={16} color={palette.text} /> : <ChevronRight size={16} color={palette.text} />}
                  </View>
                  <View style={{ flex: 1 }}>
                    <AppText palette={palette} size={14} weight="800">Array jobs</AppText>
                    {arraysExpanded ? (
                      <AppText palette={palette} muted size={11} style={{ marginTop: 1 }}>
                        {filteredArrays.length} grouped submissions - {activeArrayCount} active
                      </AppText>
                    ) : null}
                  </View>
                  {!arraysExpanded ? (
                    <AppText palette={palette} muted size={11} style={styles.arrayHeaderRight}>
                      {activeArrayCount} active / {filteredArrays.length} total
                    </AppText>
                  ) : null}
                </Pressable>
              </View>
            ) : null}
          </View>
        }
        renderItem={({ item }) => {
          if (item.type === "empty") {
            return loading ? (
              <EmptyState palette={palette} title="Loading jobs" body="Fetching cached and live Slurm status." />
            ) : (
              <EmptyState palette={palette} title="No jobs found" body="Adjust filters or refresh from the toolbar." icon={Server} />
            );
          }
          if (item.type === "array") {
            return (
              <ArrayGroupRow
                palette={palette}
                group={item.group}
                expanded={expandedArrayGroups.has(arrayGroupKey(item.group))}
                taskLimit={arrayTaskLimits[arrayGroupKey(item.group)] || 50}
                onToggle={() => toggleArrayGroup(item.group)}
                onShowMoreTasks={(total) => showMoreArrayTasks(item.group, total)}
                onOpenJob={onOpenJob}
                onOpenActions={setActionJob}
              />
            );
          }
          return (
            <JobRow
              palette={palette}
              job={item.job}
              notificationConfig={jobNotifications[jobKey(item.job.job_id, item.job.hostname)]}
              onPress={() => onOpenJob(item.job)}
              onLongPress={() => setActionJob(item.job)}
              onConfigureNotifications={() => onConfigureJobNotifications(item.job)}
            />
          );
        }}
      />

      <Sheet palette={palette} visible={showPartitions} title="Resources" onClose={() => setShowPartitions(false)}>
        <PartitionResources palette={palette} partitions={filteredPartitions} loading={loadingPartitions} />
        {!loadingPartitions && totalPartitions === 0 ? (
          <EmptyState palette={palette} title="No partition data" body="Refresh jobs or choose another host filter." icon={Layers} />
        ) : null}
      </Sheet>

      <Sheet palette={palette} visible={showFilters} title="Job Filters" onClose={() => setShowFilters(false)}>
        <Card palette={palette}>
          <SectionHeader
            palette={palette}
            title="Host"
            subtitle={selectedHost ? hostLabel : "All configured hosts"}
            action={<Button palette={palette} title="Reset" variant="secondary" onPress={resetFilters} />}
          />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
            <Chip palette={palette} label="All hosts" active={!host} onPress={clearHost} />
            {hostOptions.map((item) => (
              <Chip
                key={item.hostname}
                palette={palette}
                label={`${item.hostname}${item.count ? ` ${item.count}` : ""}`}
                active={normalizeHost(item.hostname) === selectedHost}
                onPress={() => selectHost(item.hostname)}
              />
            ))}
          </ScrollView>
        </Card>

        <Card palette={palette}>
          <SectionHeader palette={palette} title="Scope" subtitle={`${totalJobs} matching jobs`} />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
            <Chip palette={palette} label="All" active={scope === "all"} onPress={() => setScope("all")} />
            <Chip palette={palette} label="Active" active={scope === "active"} tone="success" onPress={() => setScope("active")} />
            <Chip palette={palette} label="Completed" active={scope === "completed"} tone="info" onPress={() => setScope("completed")} />
          </ScrollView>
        </Card>

        <Card palette={palette}>
          <SectionHeader palette={palette} title="State" subtitle={state ? stateLabel(state) : "Any Slurm state"} />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
            {stateOptions.map((option) => (
              <Chip
                key={option || "any"}
                palette={palette}
                label={option ? stateLabel(option) : "Any state"}
                active={state === option}
                onPress={() => setState(option)}
              />
            ))}
          </ScrollView>
        </Card>
      </Sheet>

      {actionJob ? (
        <JobActionsSheet
          palette={palette}
          job={actionJob}
          loadingAction={actionLoading}
          onClose={closeJobActions}
          onOpen={() => {
            const jobToOpen = actionJob;
            setActionJob(null);
            onOpenJob(jobToOpen);
          }}
          onResubmit={() => void resubmitJob(actionJob)}
          onCancel={() => confirmCancelJob(actionJob)}
          onShareBundle={() => void shareJobBundle(actionJob)}
          onShareStdout={() => void shareOutput(actionJob, "stdout")}
          onShareStderr={() => void shareOutput(actionJob, "stderr")}
          onNotifications={() => {
            const selected = actionJob;
            setActionJob(null);
            onConfigureJobNotifications(selected);
          }}
          onCopy={() => void copyJobSummary(actionJob)}
        />
      ) : null}
    </View>
  );
}

function ArrayGroupRow({
  palette,
  group,
  expanded,
  taskLimit,
  onToggle,
  onShowMoreTasks,
  onOpenJob,
  onOpenActions
}: {
  palette: Palette;
  group: ArrayJobGroup;
  expanded: boolean;
  taskLimit: number;
  onToggle: () => void;
  onShowMoreTasks: (total: number) => void;
  onOpenJob: (job: JobInfo) => void;
  onOpenActions: (job: JobInfo) => void;
}) {
  const accent = jobStatusColors(palette, arrayGroupState(group));
  const runningColors = jobStatusColors(palette, "R");
  const pendingColors = jobStatusColors(palette, "PD");
  const completedColors = jobStatusColors(palette, "CD");
  const failedColors = jobStatusColors(palette, "F");
  const cancelledColors = jobStatusColors(palette, "CA");
  const visibleCounts = [
    { color: runningColors.text, value: group.running_count, label: "R", always: true },
    { color: pendingColors.text, value: group.pending_count, label: "PD", always: true },
    { color: completedColors.text, value: group.completed_count, label: "CD", always: true },
    { color: failedColors.text, value: group.failed_count, label: "F", always: false },
    { color: cancelledColors.text, value: group.cancelled_count, label: "CA", always: false }
  ].filter((item) => item.always || item.value > 0);
  const tasks = [...group.tasks].sort((left, right) => {
    const priority = jobPriority(left) - jobPriority(right);
    const leftTask = Number(left.array_task_id ?? Number.NaN);
    const rightTask = Number(right.array_task_id ?? Number.NaN);
    const taskOrder = Number.isFinite(leftTask) && Number.isFinite(rightTask) ? leftTask - rightTask : 0;
    return priority || taskOrder || jobTime(right) - jobTime(left) || left.job_id.localeCompare(right.job_id);
  });
  const visibleTasks = tasks.slice(0, taskLimit);

  return (
    <View style={[styles.arrayGroup, { borderColor: palette.border, backgroundColor: palette.surface }]}>
      <View style={[styles.arrayRail, { backgroundColor: accent.text }]} />
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        onPress={onToggle}
        style={({ pressed }) => [styles.arrayGroupHeader, { opacity: pressed ? 0.74 : 1 }]}
      >
          <View style={[styles.smallCollapseIcon, { backgroundColor: palette.surface, borderColor: accent.border }]}>
          {expanded ? <ChevronDown size={14} color={accent.text} /> : <ChevronRight size={14} color={accent.text} />}
        </View>
        <View style={{ flex: 1 }}>
          <View style={styles.arrayTitleRow}>
            <View style={{ flex: 1, minWidth: 0 }}>
              <AppText palette={palette} weight="800" size={14} numberOfLines={1}>{group.job_name || `Array ${group.array_job_id}`}</AppText>
            </View>
          </View>
          <AppText palette={palette} muted size={11} numberOfLines={1}>
            {group.hostname} - {group.user || "unknown user"} - {group.total_tasks} tasks
          </AppText>
        </View>
        <View style={styles.arrayCounts}>
          {visibleCounts.map((item) => (
            <ArrayCount key={item.label} palette={palette} color={item.color} value={item.value} label={item.label} />
          ))}
        </View>
      </Pressable>

      {expanded && tasks.length > 0 ? (
        <View style={styles.arrayTaskList}>
          {visibleTasks.map((task) => {
            const taskWithHost = { ...task, hostname: task.hostname || group.hostname };
            return (
              <ArrayTaskRow
                key={arrayTaskKey(task, group.hostname)}
                palette={palette}
                task={taskWithHost}
                onPress={() => onOpenJob(taskWithHost)}
                onLongPress={() => onOpenActions(taskWithHost)}
              />
            );
          })}
          {visibleTasks.length < tasks.length ? (
            <Button
              palette={palette}
              title={`Show ${Math.min(50, tasks.length - visibleTasks.length)} more tasks`}
              variant="secondary"
              onPress={() => onShowMoreTasks(tasks.length)}
            />
          ) : null}
        </View>
      ) : expanded ? (
          <AppText palette={palette} muted size={11}>No task details available.</AppText>
      ) : (
        <View style={styles.collapsedArrayHint}>
          <AppText palette={palette} muted size={12}>{tasks.length} tasks hidden</AppText>
          <ChevronDown size={15} color={palette.subtle} />
        </View>
      )}
    </View>
  );
}

function ArrayCount({
  palette,
  color,
  value,
  label
}: {
  palette: Palette;
  color: string;
  value: number;
  label: string;
}) {
  return (
    <View style={styles.arrayCountItem}>
      <AppText palette={palette} size={10} weight="700" style={{ color }}>{value}</AppText>
      <AppText palette={palette} muted size={9} weight="600">{label}</AppText>
    </View>
  );
}

function ArrayTaskRow({
  palette,
  task,
  onPress,
  onLongPress
}: {
  palette: Palette;
  task: JobInfo;
  onPress: () => void;
  onLongPress: () => void;
}) {
  const colors = jobStatusColors(palette, task.state);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Open array task ${taskDisplayId(task)}`}
      onPress={onPress}
      onLongPress={onLongPress}
      style={({ pressed }) => [
        styles.arrayTaskRow,
        {
          backgroundColor: palette.surface,
          borderColor: palette.border,
          opacity: pressed ? 0.72 : 1
        }
      ]}
    >
      <View style={styles.arrayTaskBody}>
        <View style={[styles.taskDotInline, { backgroundColor: colors.text }]} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <AppText palette={palette} weight="800" size={12} numberOfLines={1}>Task {taskDisplayId(task)}</AppText>
          <AppText palette={palette} muted size={10} numberOfLines={1}>
            {task.runtime || "No runtime"} - CPU {task.cpus || "N/A"} - {task.node_list || task.partition || task.job_id}
          </AppText>
        </View>
        <CompactStatusBadge palette={palette} state={task.state} />
      </View>
    </Pressable>
  );
}

function CompactStatusBadge({ palette, state }: { palette: Palette; state: string | undefined | null }) {
  const colors = jobStatusColors(palette, state);
  return (
    <View style={[styles.compactStatusBadge, { backgroundColor: colors.background, borderColor: colors.border }]}>
      <AppText palette={palette} size={10} weight="700" style={{ color: colors.text }}>{stateLabel(state)}</AppText>
    </View>
  );
}

function PartitionResources({
  palette,
  partitions,
  loading
}: {
  palette: Palette;
  partitions: PartitionStatusResponse[];
  loading: boolean;
}) {
  const total = partitions.reduce((sum, host) => sum + host.partitions.length, 0);
  if (!loading && total === 0) return null;
  return (
    <Card palette={palette}>
      <SectionHeader palette={palette} title="Partition Resources" subtitle={loading ? "Loading cluster resources" : `${total} partitions`} />
      {partitions.map((host) => (
        <View key={host.hostname} style={{ gap: 8 }}>
          <View style={styles.hostHeading}>
            <Layers size={16} color={palette.muted} />
            <AppText palette={palette} weight="800">{host.hostname}</AppText>
            {host.cached ? <Chip palette={palette} label={host.stale ? "stale" : "cached"} active tone={host.stale ? "warning" : "neutral"} /> : null}
          </View>
          {host.error ? <AppText palette={palette} muted>{host.error}</AppText> : null}
          {host.partitions.slice(0, 8).map((partition) => (
            <PartitionRow key={`${host.hostname}:${partition.partition}`} palette={palette} partition={partition} />
          ))}
        </View>
      ))}
    </Card>
  );
}

function PartitionRow({
  palette,
  partition
}: {
  palette: Palette;
  partition: PartitionStatusResponse["partitions"][number];
}) {
  const cpuTone = resourceTone(partition.cpus_alloc, partition.cpus_total);
  const gpuTone = resourceTone(partition.gpus_used, partition.gpus_total);
  const dominantTone = cpuTone === "danger" || gpuTone === "danger" ? "danger" : cpuTone === "warning" || gpuTone === "warning" ? "warning" : gpuTone !== "neutral" ? gpuTone : cpuTone;
  const dominant = toneColors(palette, dominantTone);
  const cpu = toneColors(palette, cpuTone);
  const gpu = toneColors(palette, gpuTone);

  return (
    <View style={[styles.partitionRow, { borderColor: dominant.border, backgroundColor: dominant.background }]}>
      <View style={[styles.partitionRail, { backgroundColor: dominant.text }]} />
      <View style={{ flex: 1 }}>
        <AppText palette={palette} weight="800">{partition.partition}</AppText>
        <AppText palette={palette} muted size={12}>{partition.states.join(", ") || partition.availability || "available"}</AppText>
      </View>
      <AppText palette={palette} size={12} weight="900" style={{ color: cpu.text }}>
        CPU {partition.cpus_alloc}/{partition.cpus_total}
      </AppText>
      <AppText palette={palette} size={12} weight="900" style={{ color: gpu.text }}>
        GPU {partition.gpus_used ?? "-"}/{partition.gpus_total ?? "-"}
      </AppText>
    </View>
  );
}

function JobRow({
  palette,
  job,
  notificationConfig,
  onPress,
  onLongPress,
  onConfigureNotifications
}: {
  palette: Palette;
  job: JobInfo;
  notificationConfig?: JobNotificationConfig;
  onPress: () => void;
  onLongPress: () => void;
  onConfigureNotifications: () => void;
}) {
  const colors = jobStatusColors(palette, job.state);
  const notificationTone =
    notificationConfig?.mode === "custom"
      ? { background: palette.accentSoft, border: palette.accent, icon: palette.accent, opacity: 1 }
      : notificationConfig?.mode === "muted"
        ? { background: palette.dangerSoft, border: palette.danger, icon: palette.danger, opacity: 0.86 }
        : { background: "transparent", border: colors.border, icon: palette.subtle, opacity: 0.72 };

  return (
    <Pressable
      onPress={onPress}
      onLongPress={onLongPress}
      style={({ pressed }) => [
        styles.jobRow,
        {
          backgroundColor: palette.surface,
          borderColor: palette.border,
          opacity: pressed ? 0.78 : 1
        }
      ]}
    >
      <View style={[styles.jobRail, { backgroundColor: colors.text }]} />
      <View style={{ flex: 1, gap: 4 }}>
        <View style={styles.jobTop}>
          <View style={styles.jobTitleBlock}>
            <View style={styles.jobTitleLine}>
              <AppText palette={palette} weight="800" size={14} numberOfLines={1} style={{ flex: 1 }}>{displayJobName(job)}</AppText>
              <View style={[styles.jobIdPill, { backgroundColor: palette.surfaceAlt, borderColor: palette.border }]}>
                <AppText palette={palette} muted size={10} weight="700">#{job.job_id}</AppText>
              </View>
            </View>
            <AppText palette={palette} muted size={11} numberOfLines={1}>
              {job.hostname} - {job.user || "unknown user"} - {job.partition || "no partition"}
            </AppText>
          </View>
          <CompactStatusBadge palette={palette} state={job.state} />
        </View>
        <View style={styles.jobFooter}>
          <View style={styles.jobMeta}>
            <AppText palette={palette} muted size={11}>Runtime {job.runtime || "N/A"}</AppText>
            <AppText palette={palette} muted size={11}>CPU {job.cpus || "N/A"}</AppText>
            <AppText palette={palette} muted size={11}>Mem {job.memory || "N/A"}</AppText>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Configure job notifications"
            onPress={(event) => {
              event.stopPropagation();
              onConfigureNotifications();
            }}
            style={({ pressed }) => [
              styles.notifyButton,
              {
                backgroundColor: notificationTone.background,
                borderColor: notificationTone.border,
                opacity: pressed ? 0.58 : notificationTone.opacity
              }
            ]}
          >
            <Bell size={13} color={notificationTone.icon} strokeWidth={2.2} />
          </Pressable>
        </View>
      </View>
    </Pressable>
  );
}

function JobActionsSheet({
  palette,
  job,
  loadingAction,
  onClose,
  onOpen,
  onResubmit,
  onCancel,
  onShareBundle,
  onShareStdout,
  onShareStderr,
  onNotifications,
  onCopy
}: {
  palette: Palette;
  job: JobInfo;
  loadingAction: string | null;
  onClose: () => void;
  onOpen: () => void;
  onResubmit: () => void;
  onCancel: () => void;
  onShareBundle: () => void;
  onShareStdout: () => void;
  onShareStderr: () => void;
  onNotifications: () => void;
  onCopy: () => void;
}) {
  const canCancel = job.state === "R" || job.state === "PD";
  return (
    <Sheet palette={palette} visible title={compactJobTitle(job)} onClose={onClose}>
      <Card palette={palette}>
        <View style={styles.actionSheetHeading}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <AppText palette={palette} weight="800" numberOfLines={1}>#{job.job_id} on {job.hostname}</AppText>
            <AppText palette={palette} muted size={12} numberOfLines={1}>{job.partition || "no partition"} - {job.user || "unknown user"}</AppText>
          </View>
          <StatusBadge palette={palette} state={job.state} />
        </View>
      </Card>

      <Card palette={palette}>
        <ActionRow palette={palette} icon={ChevronRight} title="Open details" onPress={onOpen} />
        <ActionRow palette={palette} icon={RefreshCw} title="Resubmit job" subtitle="Open Launch with this job prefilled" loading={loadingAction === "resubmit"} onPress={onResubmit} />
        <ActionRow palette={palette} icon={Download} title="Export job bundle" subtitle="Zip metadata, script, stdout, and stderr" loading={loadingAction === "bundle"} onPress={onShareBundle} />
        <ActionRow palette={palette} icon={Download} title="Share stdout only" subtitle="Fetch output and open the native share sheet" loading={loadingAction === "stdout"} onPress={onShareStdout} />
        <ActionRow palette={palette} icon={Download} title="Share stderr only" subtitle="Fetch error output and open the native share sheet" loading={loadingAction === "stderr"} onPress={onShareStderr} />
        <ActionRow palette={palette} icon={Bell} title="Notification settings" onPress={onNotifications} />
        <ActionRow palette={palette} icon={Copy} title="Copy summary" onPress={onCopy} />
        {canCancel ? (
          <ActionRow palette={palette} icon={ShieldX} title="Cancel job" tone="danger" loading={loadingAction === "cancel"} onPress={onCancel} />
        ) : null}
      </Card>
    </Sheet>
  );
}

function ActionRow({
  palette,
  icon: Icon,
  title,
  subtitle,
  tone = "neutral",
  loading,
  onPress
}: {
  palette: Palette;
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  tone?: "neutral" | "danger";
  loading?: boolean;
  onPress: () => void;
}) {
  const color = tone === "danger" ? palette.danger : palette.text;
  return (
    <Pressable
      accessibilityRole="button"
      disabled={loading}
      onPress={onPress}
      style={({ pressed }) => [
        styles.actionRow,
        {
          borderColor: palette.border,
          opacity: loading ? 0.55 : pressed ? 0.72 : 1
        }
      ]}
    >
      <View style={[styles.actionIcon, { backgroundColor: tone === "danger" ? palette.dangerSoft : palette.surfaceAlt, borderColor: palette.border }]}>
        <Icon size={18} color={tone === "danger" ? palette.danger : palette.muted} />
      </View>
      <View style={{ flex: 1 }}>
        <AppText palette={palette} weight="700" style={{ color }}>{loading ? `${title}...` : title}</AppText>
        {subtitle ? <AppText palette={palette} muted size={12}>{subtitle}</AppText> : null}
      </View>
      <ChevronRight size={17} color={palette.subtle} />
    </Pressable>
  );
}

function jobSummaryText(job: JobInfo) {
  return [
    `${compactJobTitle(job)} on ${job.hostname}`,
    `Job ID: ${job.job_id}`,
    `State: ${stateLabel(job.state)}`,
    `User: ${job.user || "unknown"}`,
    `Partition: ${job.partition || "N/A"}`,
    `Runtime: ${job.runtime || "N/A"}`,
    `CPUs: ${job.cpus || "N/A"}`,
    `Memory: ${job.memory || "N/A"}`,
    `Work dir: ${job.work_dir || "N/A"}`,
    `Stdout: ${job.stdout_file || "N/A"}`,
    `Stderr: ${job.stderr_file || "N/A"}`,
    `Submitted: ${job.submit_time || "N/A"}`
  ].join("\n");
}

function readError(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

const styles = StyleSheet.create({
  header: {
    minHeight: 62,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    alignItems: "center",
    gap: 10
  },
  appIcon: {
    width: 32,
    height: 32,
    borderRadius: 8
  },
  content: {
    paddingHorizontal: 10,
    paddingTop: 8,
    paddingBottom: 126,
    gap: 8
  },
  listHeader: {
    gap: 8
  },
  compactSearch: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 7,
    gap: 5
  },
  searchBox: {
    minHeight: 36,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    paddingHorizontal: 9,
    flexDirection: "row",
    alignItems: "center",
    gap: 7
  },
  searchInput: {
    flex: 1,
    minHeight: 34,
    paddingVertical: 0,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: "500",
    letterSpacing: 0
  },
  activeFilterRow: {
    gap: 6,
    paddingTop: 2
  },
  chipRow: {
    gap: 6,
    paddingVertical: 3
  },
  arrayHeaderCard: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    paddingHorizontal: 9,
    paddingVertical: 7,
    gap: 6
  },
  collapsibleHeader: {
    minHeight: 34,
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  collapseIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center"
  },
  arrayHeaderRight: {
    textAlign: "right",
    minWidth: 88
  },
  arrayGroup: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    paddingVertical: 6,
    paddingLeft: 10,
    paddingRight: 8,
    gap: 5,
    overflow: "hidden"
  },
  arrayGroupHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  smallCollapseIcon: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center"
  },
  arrayTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  collapsedArrayHint: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    paddingLeft: 28
  },
  arrayTaskList: {
    gap: 4,
    paddingLeft: 28
  },
  arrayTaskRow: {
    minHeight: 40,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    paddingVertical: 5,
    paddingLeft: 8,
    paddingRight: 8,
    overflow: "hidden"
  },
  arrayTaskBody: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8
  },
  taskDotInline: {
    width: 5,
    height: 28,
    borderRadius: 999
  },
  hostHeading: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  partitionRow: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    paddingVertical: 10,
    paddingLeft: 14,
    paddingRight: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    overflow: "hidden"
  },
  partitionRail: {
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    width: 4
  },
  arrayRail: {
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    width: 4
  },
  arrayCounts: {
    width: 74,
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "flex-end",
    rowGap: 1,
    columnGap: 5
  },
  arrayCountItem: {
    minHeight: 13,
    flexDirection: "row",
    alignItems: "baseline",
    gap: 1
  },
  jobRow: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    paddingVertical: 8,
    paddingLeft: 13,
    paddingRight: 9,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    overflow: "hidden"
  },
  jobRail: {
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    width: 5
  },
  jobTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 7
  },
  jobTitleBlock: {
    flex: 1,
    minWidth: 0,
    gap: 2
  },
  jobTitleLine: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6
  },
  jobIdPill: {
    alignSelf: "flex-start",
    minHeight: 18,
    borderRadius: 6,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 6,
    justifyContent: "center"
  },
  jobFooter: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6
  },
  jobMeta: {
    flex: 1,
    flexDirection: "row",
    gap: 8,
    flexWrap: "wrap"
  },
  notifyButton: {
    width: 26,
    height: 26,
    borderRadius: 13,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center"
  },
  compactStatusBadge: {
    alignSelf: "flex-start",
    minWidth: 34,
    minHeight: 20,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 999,
    paddingHorizontal: 6,
    alignItems: "center",
    justifyContent: "center"
  },
  actionSheetHeading: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 12
  },
  actionRow: {
    minHeight: 58,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingVertical: 10
  },
  actionIcon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center"
  }
});
