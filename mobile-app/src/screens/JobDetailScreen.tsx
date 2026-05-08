import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as Clipboard from "expo-clipboard";
import { Alert, Pressable, ScrollView, StyleSheet, View } from "react-native";
import PagerView from "react-native-pager-view";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  FileCode2,
  Info,
  MoreHorizontal,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  Terminal,
  Trash2,
  TriangleAlert,
  XCircle,
  Zap
} from "lucide-react-native";
import type { LucideIcon } from "lucide-react-native";

import type { SsyncApiClient } from "../api/client";
import { WatcherCreatorSheet } from "../components/WatcherCreatorSheet";
import { AppText, Button, Card, Chip, CodeBlock, EmptyState, IconButton, SectionHeader, StatusBadge } from "../components/ui";
import type { Palette } from "../theme/colors";
import type { JobInfo, WatcherAction, JobOutputResponse, JobScriptResponse, Watcher, WatcherEvent } from "../types/api";
import type { LaunchDraft } from "../types/settings";
import { compactJobTitle, formatBytes, formatDateTime, formatMemory, formatTimeAgo, jobKey, linesCount, stateLabel } from "../utils/format";

type Tab = "details" | "output" | "errors" | "script" | "watchers";
type OutputStream = "stdout" | "stderr";
type OutputState = Record<OutputStream, JobOutputResponse | null>;
type OutputLoadingState = Record<OutputStream, boolean>;
type OutputErrorState = Record<OutputStream, string | null>;

function displayJobName(job: JobInfo) {
  return job.name && job.name !== job.job_id ? job.name : "Untitled job";
}

export function JobDetailScreen({
  palette,
  api,
  seedJob,
  onBack,
  onOpenJob,
  onResubmitDraft,
  onConfigureNotifications,
  onJobUpdated
}: {
  palette: Palette;
  api: SsyncApiClient;
  seedJob: JobInfo;
  onBack: () => void;
  onOpenJob: (jobId: string, hostname: string) => void;
  onResubmitDraft: (draft: LaunchDraft) => void;
  onConfigureNotifications: (job: JobInfo) => void;
  onJobUpdated: (job: JobInfo) => void;
}) {
  const [job, setJob] = useState(seedJob);
  const [tab, setTab] = useState<Tab>("details");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [outputs, setOutputs] = useState<OutputState>({ stdout: null, stderr: null });
  const [outputLoading, setOutputLoading] = useState<OutputLoadingState>({ stdout: false, stderr: false });
  const [outputErrors, setOutputErrors] = useState<OutputErrorState>({ stdout: null, stderr: null });
  const [script, setScript] = useState<JobScriptResponse | null>(null);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const [watchers, setWatchers] = useState<Watcher[]>([]);
  const [events, setEvents] = useState<WatcherEvent[]>([]);
  const [watchersLoaded, setWatchersLoaded] = useState(false);
  const [creatorOpen, setCreatorOpen] = useState(false);
  const [resubmitting, setResubmitting] = useState(false);
  const pagerRef = useRef<PagerView>(null);
  const outputRequestsRef = useRef<Set<OutputStream>>(new Set());
  const outputRetryTimersRef = useRef<Record<OutputStream, ReturnType<typeof setTimeout> | null>>({ stdout: null, stderr: null });
  const outputRetryCountsRef = useRef<Record<OutputStream, number>>({ stdout: 0, stderr: 0 });
  const onJobUpdatedRef = useRef(onJobUpdated);
  const headerBackground = palette.isDark ? palette.background : palette.surface;

  const clearOutputRetry = useCallback((type?: OutputStream) => {
    const streams: OutputStream[] = type ? [type] : ["stdout", "stderr"];
    streams.forEach((stream) => {
      const timer = outputRetryTimersRef.current[stream];
      if (timer) clearTimeout(timer);
      outputRetryTimersRef.current[stream] = null;
      if (!type) outputRetryCountsRef.current[stream] = 0;
    });
  }, []);

  useEffect(() => {
    onJobUpdatedRef.current = onJobUpdated;
  }, [onJobUpdated]);

  useEffect(() => {
    setJob(seedJob);
    setOutputs({ stdout: null, stderr: null });
    setOutputLoading({ stdout: false, stderr: false });
    setOutputErrors({ stdout: null, stderr: null });
    setScript(null);
    setScriptError(null);
    setWatchers([]);
    setEvents([]);
    setWatchersLoaded(false);
    setError(null);
    outputRequestsRef.current.clear();
    clearOutputRetry();
  }, [clearOutputRetry, seedJob.hostname, seedJob.job_id]);

  useEffect(() => () => clearOutputRetry(), [clearOutputRetry]);

  const refreshJob = useCallback(async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const next = await api.getJob(seedJob.job_id, seedJob.hostname, force);
      setJob(next);
      onJobUpdatedRef.current(next);
    } catch (refreshError) {
      setError((refreshError as Error).message || "Failed to load job");
    } finally {
      setLoading(false);
    }
  }, [api, seedJob.hostname, seedJob.job_id]);

  const loadOutput = useCallback(async (type: OutputStream, force = false, backgroundRetry = false) => {
    if (outputRequestsRef.current.has(type)) return;
    if (!backgroundRetry) {
      clearOutputRetry(type);
      outputRetryCountsRef.current[type] = 0;
    }
    outputRequestsRef.current.add(type);
    if (!backgroundRetry) setOutputLoading((current) => ({ ...current, [type]: true }));
    setOutputErrors((current) => ({ ...current, [type]: null }));
    try {
      const response = await api.getJobOutput(seedJob.job_id, seedJob.hostname, type, force);
      setOutputs((current) => ({ ...current, [type]: response }));
      const content = type === "stderr" ? response.stderr : response.stdout;
      if (response.refresh_queued && !content && outputRetryCountsRef.current[type] < 5) {
        outputRetryCountsRef.current[type] += 1;
        clearOutputRetry(type);
        outputRetryTimersRef.current[type] = setTimeout(() => {
          void loadOutput(type, false, true);
        }, 1600);
      }
    } catch (outputError) {
      setOutputErrors((current) => ({ ...current, [type]: (outputError as Error).message || "Failed to load output" }));
    } finally {
      outputRequestsRef.current.delete(type);
      setOutputLoading((current) => ({ ...current, [type]: false }));
    }
  }, [api, clearOutputRetry, seedJob.hostname, seedJob.job_id]);

  const loadScript = useCallback(async () => {
    setLoading(true);
    setScriptError(null);
    try {
      setScript(await api.getJobScript(seedJob.job_id, seedJob.hostname));
    } catch (scriptError) {
      setScriptError((scriptError as Error).message || "Failed to load script");
    } finally {
      setLoading(false);
    }
  }, [api, seedJob.hostname, seedJob.job_id]);

  const loadWatchers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [watcherResponse, eventResponse] = await Promise.all([
        api.getJobWatchers(seedJob.job_id, seedJob.hostname),
        api.getWatcherEvents({ job_id: seedJob.job_id, limit: 1000 })
      ]);
      setWatchers(watcherResponse.watchers || []);
      setEvents(eventResponse.events || []);
      setWatchersLoaded(true);
    } catch (watcherError) {
      setError((watcherError as Error).message || "Failed to load watchers");
      setWatchersLoaded(true);
    } finally {
      setLoading(false);
    }
  }, [api, seedJob.hostname, seedJob.job_id]);

  useEffect(() => {
    void refreshJob(false);
  }, [refreshJob]);

  useEffect(() => {
    if (tab === "output" && !outputs.stdout && !outputErrors.stdout && !outputLoading.stdout) void loadOutput("stdout");
    if (tab === "errors" && !outputs.stderr && !outputErrors.stderr && !outputLoading.stderr) void loadOutput("stderr");
    if (tab === "script" && !script && !scriptError && !loading) void loadScript();
    if (tab === "watchers" && !watchersLoaded && !loading) void loadWatchers();
  }, [
    loadOutput,
    loadScript,
    loadWatchers,
    outputErrors.stderr,
    outputErrors.stdout,
    outputLoading.stderr,
    outputLoading.stdout,
    outputs.stderr,
    outputs.stdout,
    loading,
    script,
    scriptError,
    tab,
    watchersLoaded,
    watchers.length
  ]);

  const activeOutputType: OutputStream = tab === "errors" ? "stderr" : "stdout";
  const selectedTabIndex = Math.max(0, detailTabs.findIndex((item) => item.value === tab));
  const selectDetailTab = useCallback((nextTab: Tab) => {
    const nextIndex = detailTabs.findIndex((item) => item.value === nextTab);
    if (nextIndex < 0) return;
    setTab(nextTab);
    pagerRef.current?.setPage(nextIndex);
  }, []);

  function refreshCurrentTab() {
    void refreshJob(true);
    if (tab === "output" || tab === "errors") void loadOutput(activeOutputType, true);
    if (tab === "script") void loadScript();
    if (tab === "watchers") void loadWatchers();
  }

  async function cancelJob() {
    Alert.alert("Cancel job", `Cancel ${compactJobTitle(job)} on ${job.hostname}?`, [
      { text: "Keep running", style: "cancel" },
      {
        text: "Cancel job",
        style: "destructive",
        onPress: async () => {
          const previousJob = job;
          const cancelledJob = { ...job, state: "CA" };
          setJob(cancelledJob);
          onJobUpdatedRef.current(cancelledJob);
          try {
            await api.cancelJob(job.job_id, job.hostname);
            void refreshJob(true);
          } catch (cancelError) {
            setJob(previousJob);
            onJobUpdatedRef.current(previousJob);
            setError((cancelError as Error).message || "Failed to cancel job");
          }
        }
      }
    ]);
  }

  async function resubmitJob() {
    setResubmitting(true);
    setError(null);
    try {
      const jobScript = script || await api.getJobScript(seedJob.job_id, seedJob.hostname);
      if (!script) setScript(jobScript);
      onResubmitDraft({
        id: `${job.hostname}:${job.job_id}:${Date.now()}`,
        sourceJobId: job.job_id,
        sourceJobName: job.name,
        scriptContent: jobScript.script_content,
        host: job.hostname,
        sourceDir: jobScript.local_source_dir || job.work_dir || ""
      });
    } catch (resubmitError) {
      setError((resubmitError as Error).message || "Failed to load previous job script");
    } finally {
      setResubmitting(false);
    }
  }

  async function copyJobSummary() {
    await Clipboard.setStringAsync(`${compactJobTitle(job)} on ${job.hostname} is ${stateLabel(job.state)}`);
  }

  function openJobActions() {
    Alert.alert(compactJobTitle(job), `${job.hostname} - ${stateLabel(job.state)}`, [
      { text: "Notifications", onPress: () => onConfigureNotifications(job) },
      { text: "Copy summary", onPress: () => void copyJobSummary() },
      { text: "Resubmit", onPress: () => void resubmitJob() },
      ...(job.state === "R" || job.state === "PD" ? [{ text: "Cancel job", style: "destructive" as const, onPress: () => void cancelJob() }] : []),
      { text: "Close", style: "cancel" }
    ]);
  }

  return (
    <View
      style={[
        styles.screen,
        {
          backgroundColor: palette.background
        }
      ]}
    >
      <View style={[styles.header, { backgroundColor: headerBackground, borderColor: palette.border }]}>
        <IconButton palette={palette} icon={ArrowLeft} label="Back" size={34} onPress={onBack} />
        <View style={{ flex: 1 }}>
          <View style={styles.headerTitleRow}>
            <View style={styles.headerTitleBlock}>
              <AppText palette={palette} size={15} weight="800" numberOfLines={1}>{displayJobName(job)}</AppText>
              <View style={[styles.headerJobIdPill, { backgroundColor: palette.surfaceAlt, borderColor: palette.border }]}>
                <AppText palette={palette} muted size={11} weight="700">#{job.job_id}</AppText>
              </View>
            </View>
          </View>
          <AppText palette={palette} muted size={12}>{job.hostname} - {job.partition || "no partition"}</AppText>
        </View>
        <View style={styles.headerStatus}>
          <StatusBadge palette={palette} state={job.state} />
        </View>
        <IconButton palette={palette} icon={RefreshCw} label="Refresh" size={34} onPress={refreshCurrentTab} disabled={loading} />
        <IconButton palette={palette} icon={MoreHorizontal} label="Job actions" size={34} onPress={openJobActions} disabled={resubmitting} />
      </View>

      <PagerView
        ref={pagerRef}
        style={styles.pager}
        initialPage={selectedTabIndex}
        onPageSelected={(event) => {
          const nextTab = detailTabs[event.nativeEvent.position];
          if (nextTab) setTab(nextTab.value);
        }}
      >
        <DetailPage key="details" palette={palette} error={error}>
          <DetailsTab palette={palette} job={job} />
        </DetailPage>

        <DetailPage key="output" palette={palette} error={error}>
          <OutputTab
            palette={palette}
            loading={outputLoading.stdout}
            content={outputs.stdout?.stdout || ""}
            metadata={outputs.stdout?.stdout_metadata || null}
            truncated={Boolean(outputs.stdout?.content_truncated)}
            error={outputErrors.stdout}
            type="stdout"
            onRefresh={() => loadOutput("stdout", true)}
          />
        </DetailPage>

        <DetailPage key="errors" palette={palette} error={error}>
          <OutputTab
            palette={palette}
            loading={outputLoading.stderr}
            content={outputs.stderr?.stderr || ""}
            metadata={outputs.stderr?.stderr_metadata || null}
            truncated={Boolean(outputs.stderr?.content_truncated)}
            error={outputErrors.stderr}
            type="stderr"
            onRefresh={() => loadOutput("stderr", true)}
          />
        </DetailPage>

        <DetailPage key="script" palette={palette} error={error}>
          <Card palette={palette}>
            <SectionHeader
              palette={palette}
              title="Script"
              subtitle={script ? `${script.content_length.toLocaleString()} chars - ${linesCount(script.script_content)} lines` : scriptError ? "Unavailable" : "Loading script"}
            />
            {script ? (
              <CodeBlock palette={palette} content={script.script_content} />
            ) : scriptError ? (
              <EmptyState palette={palette} title="Script unavailable" body={scriptError} icon={FileCode2} />
            ) : (
              <EmptyState palette={palette} title="Loading script" icon={FileCode2} />
            )}
          </Card>
        </DetailPage>

        <DetailPage key="watchers" palette={palette} error={error}>
          <WatchersTab
            palette={palette}
            watchers={watchers}
            events={events}
            loading={loading}
            onRefresh={loadWatchers}
            onCreate={() => setCreatorOpen(true)}
            onPauseResume={async (watcher) => {
              const nextState = watcher.state === "paused" ? "active" : "paused";
              setWatchers((current) => current.map((item) => item.id === watcher.id ? { ...item, state: nextState } : item));
              try {
                if (watcher.state === "paused") await api.resumeWatcher(watcher.id);
                else await api.pauseWatcher(watcher.id);
                void loadWatchers();
              } catch (watcherError) {
                setWatchers((current) => current.map((item) => item.id === watcher.id ? watcher : item));
                setError((watcherError as Error).message || "Failed to update watcher");
              }
            }}
            onDelete={async (watcher) => {
              setWatchers((current) => current.filter((item) => item.id !== watcher.id));
              try {
                await api.deleteWatcher(watcher.id);
                void loadWatchers();
              } catch (deleteError) {
                setWatchers((current) => [watcher, ...current]);
                setError((deleteError as Error).message || "Failed to delete watcher");
              }
            }}
            onTrigger={async (watcher) => {
              try {
                await api.triggerWatcher(watcher.id);
                void loadWatchers();
              } catch (triggerError) {
                setError((triggerError as Error).message || "Failed to trigger watcher");
              }
            }}
          />
        </DetailPage>
      </PagerView>

      <View style={[styles.bottomTabRail, { backgroundColor: palette.background, borderColor: palette.border }]}>
        <DetailTabRail palette={palette} value={tab} onChange={selectDetailTab} />
      </View>

      <WatcherCreatorSheet
        palette={palette}
        api={api}
        visible={creatorOpen}
        jobId={job.job_id}
        hostname={job.hostname}
        onClose={() => setCreatorOpen(false)}
        onCreated={loadWatchers}
      />
    </View>
  );
}

function DetailPage({
  palette,
  error,
  children
}: {
  palette: Palette;
  error: string | null;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.page}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {error ? <Card palette={palette}><SectionHeader palette={palette} title="Error" subtitle={error} /></Card> : null}
        {children}
      </ScrollView>
    </View>
  );
}

function DetailsTab({ palette, job }: { palette: Palette; job: JobInfo }) {
  const rows = useMemo(
    () => [
      ["Job ID", job.job_id],
      ["Name", job.name],
      ["User", job.user],
      ["Partition", job.partition],
      ["Runtime", job.runtime],
      ["Time limit", job.time_limit],
      ["Nodes", job.nodes],
      ["CPUs", job.cpus],
      ["Memory", formatMemory(job.memory)],
      ["Account", job.account],
      ["QOS", job.qos],
      ["Reason", job.reason],
      ["Work dir", job.work_dir],
      ["Stdout", job.stdout_file],
      ["Stderr", job.stderr_file],
      ["Submitted", formatDateTime(job.submit_time)],
      ["Started", formatDateTime(job.start_time)],
      ["Ended", formatDateTime(job.end_time)],
      ["Node list", job.node_list],
      ["Exit code", job.exit_code],
      ["Alloc TRES", job.alloc_tres],
      ["Req TRES", job.req_tres],
      ["Max RSS", job.max_rss],
      ["Ave RSS", job.ave_rss],
      ["Max disk read", job.max_disk_read],
      ["Max disk write", job.max_disk_write],
      ["Energy", job.consumed_energy]
    ],
    [job]
  );

  return (
    <Card palette={palette}>
      <SectionHeader palette={palette} title="Details" subtitle="Scheduler metadata, paths, and resource usage" />
      {rows.map(([label, value]) => (
        <View key={label || ""} style={[styles.detailRow, { borderColor: palette.border }]}>
          <AppText palette={palette} muted size={12}>{label}</AppText>
          <AppText palette={palette} weight="700" style={{ flex: 1, textAlign: "right" }}>{value || "N/A"}</AppText>
        </View>
      ))}
    </Card>
  );
}

const detailTabs: Array<{ value: Tab; label: string; icon: LucideIcon }> = [
  { value: "details", label: "Details", icon: Info },
  { value: "output", label: "Output", icon: Terminal },
  { value: "errors", label: "Errors", icon: TriangleAlert },
  { value: "script", label: "Script", icon: FileCode2 },
  { value: "watchers", label: "Watchers", icon: Eye }
];

function DetailTabRail({
  palette,
  value,
  onChange
}: {
  palette: Palette;
  value: Tab;
  onChange: (tab: Tab) => void;
}) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      style={[styles.tabRail, { backgroundColor: palette.surfaceAlt, borderColor: palette.border }]}
      contentContainerStyle={styles.tabRailContent}
    >
      {detailTabs.map((tab) => {
        const active = value === tab.value;
        const Icon = tab.icon;
        return (
          <Pressable
            key={tab.value}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            onPress={() => onChange(tab.value)}
            style={({ pressed }) => [
              styles.detailTab,
              {
                backgroundColor: active ? palette.surface : "transparent",
                borderColor: active ? palette.accent : "transparent",
                opacity: pressed ? 0.74 : 1
              }
            ]}
          >
            <Icon size={16} color={active ? palette.accent : palette.muted} strokeWidth={2.2} />
            <AppText palette={palette} size={12} weight="800" style={{ color: active ? palette.accent : palette.muted }}>
              {tab.label}
            </AppText>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

function OutputTab({
  palette,
  loading,
  content,
  metadata,
  truncated,
  error,
  type,
  onRefresh
}: {
  palette: Palette;
  loading: boolean;
  content: string;
  metadata: JobOutputResponse["stdout_metadata"];
  truncated: boolean;
  error: string | null;
  type: "stdout" | "stderr";
  onRefresh: () => void;
}) {
  const emptyOutputBody = outputEmptyMessage(type, metadata);
  return (
    <Card palette={palette}>
      <SectionHeader
        palette={palette}
        title={type === "stdout" ? "Output" : "Errors"}
        subtitle={metadata ? `${formatBytes(metadata.size_bytes)} - ${metadata.path || "no file"}` : loading ? "Loading" : "No metadata"}
        action={<IconButton palette={palette} icon={RefreshCw} label="Refresh output" variant="secondary" onPress={onRefresh} disabled={loading} />}
      />
      {truncated ? <Chip palette={palette} label="tail view" active tone="neutral" /> : null}
      {content ? (
        <CodeBlock palette={palette} content={content} minHeight={360} />
      ) : error ? (
        <EmptyState palette={palette} title={type === "stdout" ? "Output unavailable" : "Errors unavailable"} body={error} icon={TriangleAlert} />
      ) : metadata ? (
        <EmptyState
          palette={palette}
          title={type === "stdout" ? "Output is empty" : "Error stream is empty"}
          body={emptyOutputBody}
          icon={type === "stdout" ? Terminal : TriangleAlert}
        />
      ) : (
        <EmptyState palette={palette} title={loading ? "Loading output" : "No output loaded"} icon={type === "stdout" ? Terminal : TriangleAlert} />
      )}
    </Card>
  );
}

function outputEmptyMessage(type: "stdout" | "stderr", metadata: JobOutputResponse["stdout_metadata"]) {
  if (!metadata) return undefined;
  if (!metadata.exists) return `${type} file was not found at ${metadata.path || "the configured path"}.`;
  if (metadata.size_bytes === 0) return `${type} file exists but is empty: ${metadata.path || "unknown path"}.`;
  if (metadata.size_bytes && metadata.size_bytes > 0) {
    return `${type} metadata reports ${formatBytes(metadata.size_bytes)}, but no text content was returned. Try refresh; the file may be binary, inaccessible, or temporarily rate-limited.`;
  }
  return `${type} file has no text content yet${metadata.path ? `: ${metadata.path}` : "."}`;
}

function WatchersTab({
  palette,
  watchers,
  events,
  loading,
  onRefresh,
  onCreate,
  onPauseResume,
  onDelete,
  onTrigger
}: {
  palette: Palette;
  watchers: Watcher[];
  events: WatcherEvent[];
  loading: boolean;
  onRefresh: () => void;
  onCreate: () => void;
  onPauseResume: (watcher: Watcher) => void;
  onDelete: (watcher: Watcher) => void;
  onTrigger: (watcher: Watcher) => void;
}) {
  const [expandedWatcherIds, setExpandedWatcherIds] = useState<Set<number>>(new Set());
  const [expandedEventIds, setExpandedEventIds] = useState<Set<number>>(new Set());
  const [visibleEventCount, setVisibleEventCount] = useState(80);
  const sortedEvents = useMemo(
    () => [...events].sort((left, right) => Date.parse(right.timestamp || "0") - Date.parse(left.timestamp || "0")),
    [events]
  );
  const visibleEvents = sortedEvents.slice(0, visibleEventCount);
  const totalTriggers = watchers.reduce((sum, watcher) => sum + (watcher.trigger_count || 0), 0);
  const latestEvent = sortedEvents[0];

  useEffect(() => {
    setVisibleEventCount(80);
    setExpandedEventIds(new Set());
  }, [events.length]);

  function toggleWatcher(id: number) {
    setExpandedWatcherIds((current) => toggleSetValue(current, id));
  }

  function toggleEvent(id: number) {
    setExpandedEventIds((current) => toggleSetValue(current, id));
  }

  return (
    <View style={styles.watchersLayout}>
      <Card palette={palette}>
        <SectionHeader
          palette={palette}
          title="Watchers"
          subtitle={`${watchers.length} attached, ${sortedEvents.length} loaded events`}
          action={<Button palette={palette} title="Create" icon={Eye} onPress={onCreate} />}
        />
        <View style={styles.watcherSummaryGrid}>
          <WatcherMetric palette={palette} label="Triggers" value={totalTriggers} tone="success" />
          <WatcherMetric palette={palette} label="Events" value={sortedEvents.length} tone="info" />
          <WatcherMetric palette={palette} label="Actions" value={watchers.reduce((sum, watcher) => sum + (watcher.actions?.length || 0), 0)} tone="neutral" />
        </View>
        <Button palette={palette} title="Refresh watchers" icon={RefreshCw} variant="secondary" onPress={onRefresh} loading={loading} />
        {latestEvent ? (
          <AppText palette={palette} muted size={12}>
            Latest activity {formatTimeAgo(latestEvent.timestamp)} by {latestEvent.watcher_name || `watcher ${latestEvent.watcher_id}`}
          </AppText>
        ) : null}
      </Card>

      {watchers.length === 0 ? (
        <Card palette={palette}>
          <EmptyState palette={palette} title="No watchers" body="Create a watcher to monitor output patterns or terminal states." icon={Eye} />
        </Card>
      ) : (
        watchers.map((watcher) => {
          const expanded = expandedWatcherIds.has(watcher.id);
          const watcherEvents = sortedEvents.filter((event) => event.watcher_id === watcher.id);
          return (
            <WatcherInspector
              key={watcher.id}
              palette={palette}
              watcher={watcher}
              events={watcherEvents}
              expanded={expanded}
              onToggle={() => toggleWatcher(watcher.id)}
              onPauseResume={() => onPauseResume(watcher)}
              onTrigger={() => onTrigger(watcher)}
              onDelete={() => onDelete(watcher)}
            />
          );
        })
      )}

      <Card palette={palette}>
        <SectionHeader palette={palette} title="Watcher Events" subtitle={`${sortedEvents.length} events loaded for this job`} />
        {sortedEvents.length === 0 ? (
          <EmptyState palette={palette} title="No watcher events" body="Events will appear here when attached watchers trigger." icon={Zap} />
        ) : (
          visibleEvents.map((event) => (
            <WatcherEventRow
              key={event.id}
              palette={palette}
              event={event}
              expanded={expandedEventIds.has(event.id)}
              onToggle={() => toggleEvent(event.id)}
            />
          ))
        )}
        {visibleEvents.length < sortedEvents.length ? (
          <View style={styles.actions}>
            <Button
              palette={palette}
              title={`Show ${Math.min(80, sortedEvents.length - visibleEvents.length)} more`}
              variant="secondary"
              onPress={() => setVisibleEventCount((count) => Math.min(count + 80, sortedEvents.length))}
            />
            <Button
              palette={palette}
              title="Show all"
              variant="ghost"
              onPress={() => setVisibleEventCount(sortedEvents.length)}
            />
          </View>
        ) : null}
      </Card>
    </View>
  );
}

function toggleSetValue<T>(current: Set<T>, value: T) {
  const next = new Set(current);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

function WatcherMetric({
  palette,
  label,
  value,
  tone
}: {
  palette: Palette;
  label: string;
  value: number;
  tone: "success" | "info" | "neutral";
}) {
  const colors =
    tone === "success"
      ? { background: palette.successSoft, border: palette.success, text: palette.success }
      : tone === "info"
        ? { background: palette.infoSoft, border: palette.info, text: palette.info }
        : { background: palette.surfaceAlt, border: palette.border, text: palette.muted };
  return (
    <View style={[styles.watcherMetric, { backgroundColor: colors.background, borderColor: colors.border }]}>
      <AppText palette={palette} size={18} weight="900" style={{ color: colors.text }}>{value}</AppText>
      <AppText palette={palette} size={11} weight="800" style={{ color: colors.text }}>{label}</AppText>
    </View>
  );
}

function WatcherInspector({
  palette,
  watcher,
  events,
  expanded,
  onToggle,
  onPauseResume,
  onTrigger,
  onDelete
}: {
  palette: Palette;
  watcher: Watcher;
  events: WatcherEvent[];
  expanded: boolean;
  onToggle: () => void;
  onPauseResume: () => void;
  onTrigger: () => void;
  onDelete: () => void;
}) {
  const mode = watcher.trigger_on_job_end
    ? "Terminal-state trigger"
    : watcher.timer_mode_enabled
      ? "Pattern + timer"
      : "Pattern monitor";
  const trigger = watcher.trigger_on_job_end
    ? `Job end: ${(watcher.trigger_job_states || []).join(", ") || "terminal states"}`
    : watcher.pattern || "Manual trigger";
  const rows: Array<[string, string | number | null | undefined]> = [
    ["Mode", mode],
    ["Trigger", trigger],
    ["Interval", `${watcher.interval_seconds}s`],
    ["Trigger count", watcher.trigger_count],
    ["Last check", watcher.last_check ? `${formatTimeAgo(watcher.last_check)} (${formatDateTime(watcher.last_check)})` : "Never"],
    ["Created", formatDateTime(watcher.created_at)],
    ["Last position", watcher.last_position],
    ["Condition", watcher.condition],
    ["Captures", watcher.captures?.join(", ")],
    ["Variables", formatRecordInline(watcher.variables)],
    ["Array template", watcher.is_array_template ? `${watcher.discovered_task_count || 0}/${watcher.expected_task_count || "?"} tasks` : null]
  ];

  return (
    <Card palette={palette}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded }} onPress={onToggle} style={styles.watcherHeader}>
        <View style={[styles.smallIconButton, { borderColor: palette.border, backgroundColor: palette.surfaceAlt }]}>
          {expanded ? <ChevronDown size={16} color={palette.text} /> : <ChevronRight size={16} color={palette.text} />}
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <AppText palette={palette} weight="900" numberOfLines={1}>{watcher.name}</AppText>
          <AppText palette={palette} muted size={12} numberOfLines={1}>Job #{watcher.job_id} on {watcher.hostname}</AppText>
        </View>
        <View style={{ alignItems: "flex-end", gap: 4 }}>
          <Chip palette={palette} label={watcher.state} active />
          <AppText palette={palette} muted size={11}>{events.length} events</AppText>
        </View>
      </Pressable>

      <AppText palette={palette} muted size={12} numberOfLines={expanded ? undefined : 2}>{trigger}</AppText>

      {expanded ? (
        <>
          <View style={styles.actions}>
            <Button palette={palette} title={watcher.state === "paused" ? "Resume" : "Pause"} icon={watcher.state === "paused" ? PlayCircle : PauseCircle} variant="secondary" onPress={onPauseResume} />
            <Button palette={palette} title="Trigger" icon={Zap} variant="secondary" onPress={onTrigger} />
            <Button palette={palette} title="Delete" icon={Trash2} variant="danger" onPress={onDelete} />
          </View>

          <View style={styles.detailList}>
            {rows.map(([label, value]) => (
              <View key={label} style={[styles.detailRow, { borderColor: palette.border }]}>
                <AppText palette={palette} muted size={12}>{label}</AppText>
                <AppText palette={palette} weight="700" style={{ flex: 1, textAlign: "right" }}>{formatDetailValue(value)}</AppText>
              </View>
            ))}
          </View>

          <View style={styles.actionList}>
            <AppText palette={palette} weight="900">Actions</AppText>
            {watcher.actions?.length ? watcher.actions.map((action, index) => (
              <WatcherActionBlock key={`${action.type}-${index}`} palette={palette} action={action} index={index} />
            )) : <AppText palette={palette} muted size={12}>No actions configured.</AppText>}
          </View>
        </>
      ) : null}
    </Card>
  );
}

function WatcherActionBlock({
  palette,
  action,
  index
}: {
  palette: Palette;
  action: WatcherAction;
  index: number;
}) {
  return (
    <View style={[styles.actionBlock, { borderColor: palette.border, backgroundColor: palette.surfaceAlt }]}>
      <View style={styles.titleRow}>
        <AppText palette={palette} weight="900">Action {index + 1}</AppText>
        <Chip palette={palette} label={action.type} active tone="info" />
      </View>
      {action.condition ? <AppText palette={palette} muted size={12}>Condition: {action.condition}</AppText> : null}
      {action.params ? <KeyValueRows palette={palette} title="Params" values={action.params} /> : null}
      {action.config ? <KeyValueRows palette={palette} title="Config" values={action.config} /> : null}
    </View>
  );
}

function WatcherEventRow({
  palette,
  event,
  expanded,
  onToggle
}: {
  palette: Palette;
  event: WatcherEvent;
  expanded: boolean;
  onToggle: () => void;
}) {
  const EventIcon = event.success ? CheckCircle2 : XCircle;
  const tone = event.success
    ? { background: palette.successSoft, border: palette.success, text: palette.success }
    : { background: palette.dangerSoft, border: palette.danger, text: palette.danger };
  const capturedEntries = Object.entries(event.captured_vars || {});

  return (
    <View style={[styles.eventCard, { borderColor: tone.border, backgroundColor: tone.background }]}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded }} onPress={onToggle} style={styles.eventHeader}>
        <EventIcon size={18} color={tone.text} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <AppText palette={palette} weight="900" numberOfLines={1}>{event.action_type}</AppText>
          <AppText palette={palette} muted size={12} numberOfLines={1}>
            {event.watcher_name || `Watcher ${event.watcher_id}`} - {formatTimeAgo(event.timestamp)}
          </AppText>
        </View>
        <View style={{ alignItems: "flex-end", gap: 4 }}>
          <Chip palette={palette} label={event.success ? "ok" : "failed"} active tone={event.success ? "success" : "danger"} />
          {expanded ? <ChevronDown size={16} color={tone.text} /> : <ChevronRight size={16} color={tone.text} />}
        </View>
      </Pressable>

      {!expanded && event.matched_text ? (
        <AppText palette={palette} muted size={12} numberOfLines={2}>{event.matched_text}</AppText>
      ) : null}

      {expanded ? (
        <View style={styles.eventDetails}>
          <View style={styles.eventMetaRow}>
            <Chip palette={palette} label={`Job #${event.job_id}`} active tone="neutral" />
            <Chip palette={palette} label={event.hostname} active tone="neutral" />
            <Chip palette={palette} label={formatDateTime(event.timestamp)} active tone="neutral" />
          </View>

          {event.matched_text ? (
            <View style={styles.detailSection}>
              <AppText palette={palette} weight="900">Pattern Match</AppText>
              <CodeBlock palette={palette} content={event.matched_text} minHeight={120} maxHeight={220} />
            </View>
          ) : null}

          {capturedEntries.length > 0 ? (
            <View style={styles.detailSection}>
              <AppText palette={palette} weight="900">Captured Variables</AppText>
              <KeyValueRows palette={palette} values={event.captured_vars} />
            </View>
          ) : null}

          {event.action_result ? (
            <View style={styles.detailSection}>
              <AppText palette={palette} weight="900">Action Result</AppText>
              <CodeBlock palette={palette} content={event.action_result} minHeight={120} maxHeight={260} />
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

function KeyValueRows({
  palette,
  title,
  values
}: {
  palette: Palette;
  title?: string;
  values?: Record<string, unknown> | null;
}) {
  const entries = Object.entries(values || {});
  if (entries.length === 0) return null;
  return (
    <View style={styles.keyValueBlock}>
      {title ? <AppText palette={palette} muted size={12}>{title}</AppText> : null}
      {entries.map(([key, value]) => (
        <View key={key} style={[styles.keyValueRow, { borderColor: palette.border }]}>
          <AppText palette={palette} muted size={12}>{key}</AppText>
          <AppText palette={palette} weight="800" style={{ flex: 1, textAlign: "right" }}>{formatUnknown(value)}</AppText>
        </View>
      ))}
    </View>
  );
}

function formatDetailValue(value: string | number | null | undefined) {
  return value === null || value === undefined || value === "" ? "N/A" : String(value);
}

function formatRecordInline(values?: Record<string, unknown> | null) {
  const entries = Object.entries(values || {});
  if (entries.length === 0) return null;
  return entries.map(([key, value]) => `${key}=${formatUnknown(value)}`).join(", ");
}

function formatUnknown(value: unknown) {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

const styles = StyleSheet.create({
  screen: {
    flex: 1
  },
  header: {
    minHeight: 62,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    alignItems: "center",
    gap: 10
  },
  content: {
    padding: 14,
    gap: 14
  },
  pager: {
    flex: 1
  },
  page: {
    flex: 1
  },
  bottomTabRail: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 14,
    paddingTop: 8,
    paddingBottom: 10
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10
  },
  headerTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  headerTitleBlock: {
    flex: 1,
    minWidth: 0,
    gap: 4
  },
  headerStatus: {
    minHeight: 34,
    justifyContent: "center"
  },
  headerJobIdPill: {
    alignSelf: "flex-start",
    minHeight: 19,
    borderRadius: 6,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 7,
    justifyContent: "center"
  },
  tabRail: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8
  },
  tabRailContent: {
    minHeight: 44,
    padding: 4,
    gap: 4
  },
  detailTab: {
    minWidth: 92,
    minHeight: 36,
    borderRadius: 7,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 10,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6
  },
  actions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8
  },
  watchersLayout: {
    gap: 14
  },
  watcherSummaryGrid: {
    flexDirection: "row",
    gap: 8
  },
  watcherMetric: {
    flex: 1,
    minHeight: 62,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 10,
    justifyContent: "center",
    gap: 3
  },
  watcherHeader: {
    minHeight: 48,
    flexDirection: "row",
    alignItems: "center",
    gap: 10
  },
  smallIconButton: {
    width: 30,
    height: 30,
    borderRadius: 15,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center"
  },
  detailList: {
    gap: 0
  },
  detailRow: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: 9,
    flexDirection: "row",
    gap: 12,
    alignItems: "flex-start"
  },
  actionList: {
    gap: 8
  },
  actionBlock: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 10,
    gap: 8
  },
  eventCard: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 10,
    gap: 8,
    marginBottom: 8
  },
  eventHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10
  },
  eventDetails: {
    gap: 12
  },
  eventMetaRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8
  },
  detailSection: {
    gap: 7
  },
  keyValueBlock: {
    gap: 0
  },
  keyValueRow: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: 8,
    flexDirection: "row",
    gap: 12,
    alignItems: "flex-start"
  }
});
