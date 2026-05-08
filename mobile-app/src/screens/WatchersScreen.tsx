import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronRight, Copy, PauseCircle, PlayCircle, Plus, Radio, RefreshCw, Search, Trash2, Zap } from "lucide-react-native";
import { FlatList, Pressable, ScrollView, StyleSheet, View } from "react-native";

import type { SsyncApiClient } from "../api/client";
import { WatcherCreatorSheet } from "../components/WatcherCreatorSheet";
import { AppText, Button, Card, Chip, EmptyState, IconButton, SectionHeader, Sheet, TextField } from "../components/ui";
import type { Palette } from "../theme/colors";
import type { JobInfo, Watcher, WatcherEvent } from "../types/api";
import { formatTimeAgo } from "../utils/format";

type FilterState = "all" | "active" | "paused" | "static" | "completed";
type SortMode = "activity" | "recent" | "name";
type WatcherTone = "neutral" | "success" | "warning" | "danger" | "info";
type WatchersListItem = { type: "empty" } | { type: "watcher"; watcher: Watcher };

function watcherTone(state: string | null | undefined): WatcherTone {
  if (state === "active") return "success";
  if (state === "paused") return "warning";
  if (state === "completed") return "info";
  if (state === "error" || state === "failed") return "danger";
  if (state === "static") return "neutral";
  return "neutral";
}

function toneColors(palette: Palette, tone: WatcherTone) {
  if (tone === "success") return { background: palette.successSoft, border: palette.success, text: palette.success };
  if (tone === "warning") return { background: palette.warningSoft, border: palette.warning, text: palette.warning };
  if (tone === "danger") return { background: palette.dangerSoft, border: palette.danger, text: palette.danger };
  if (tone === "info") return { background: palette.infoSoft, border: palette.info, text: palette.info };
  return { background: palette.surfaceAlt, border: palette.border, text: palette.muted };
}

export function WatchersScreen({
  palette,
  api,
  jobs
}: {
  palette: Palette;
  api: SsyncApiClient;
  jobs: JobInfo[];
}) {
  const [watchers, setWatchers] = useState<Watcher[]>([]);
  const [events, setEvents] = useState<WatcherEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<FilterState>("all");
  const [sort, setSort] = useState<SortMode>("activity");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [socketConnected, setSocketConnected] = useState(false);
  const [createPickerOpen, setCreatePickerOpen] = useState(false);
  const [creatorTarget, setCreatorTarget] = useState<{ jobId: string; hostname: string } | null>(null);
  const [actionWatcher, setActionWatcher] = useState<Watcher | null>(null);
  const [copySource, setCopySource] = useState<Watcher | null>(null);
  const [copyTargets, setCopyTargets] = useState<string[]>([]);
  const [copying, setCopying] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const refreshData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [watcherResponse, eventResponse] = await Promise.all([
        api.getWatchers(300),
        api.getWatcherEvents({ limit: 300 })
      ]);
      setWatchers(watcherResponse.watchers || []);
      setEvents(eventResponse.events || []);
    } catch (refreshError) {
      setError((refreshError as Error).message || "Failed to load watchers");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void refreshData();
  }, [refreshData]);

  useEffect(() => {
    if (!api.wsBaseURL) return;
    const ws = new WebSocket(api.buildWebSocketURL("/ws/watchers"));
    wsRef.current = ws;
    ws.onopen = () => setSocketConnected(true);
    ws.onclose = () => setSocketConnected(false);
    ws.onerror = () => setSocketConnected(false);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as Record<string, unknown>;
        if (data.type === "initial") {
          if (Array.isArray(data.watchers)) setWatchers(data.watchers as Watcher[]);
          if (Array.isArray(data.events)) setEvents(data.events as WatcherEvent[]);
        } else if (data.type === "watcher_update" && data.watcher) {
          const watcher = data.watcher as Watcher;
          setWatchers((current) => upsertWatcher(current, watcher));
        } else if (data.type === "watcher_deleted") {
          setWatchers((current) => current.filter((watcher) => watcher.id !== data.watcher_id));
        } else if (data.type === "watcher_event" && data.event) {
          setEvents((current) => [data.event as WatcherEvent, ...current.filter((item) => item.id !== (data.event as WatcherEvent).id)].slice(0, 300));
          if (data.watcher) setWatchers((current) => upsertWatcher(current, data.watcher as Watcher));
        } else if (data.type === "watcher_state_change") {
          setWatchers((current) => current.map((watcher) => watcher.id === data.watcher_id ? { ...watcher, state: String(data.state) } : watcher));
        }
      } catch {
        // Ignore malformed realtime messages.
      }
    };
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [api]);

  useEffect(() => {
    if (selectedId && !watchers.some((watcher) => watcher.id === selectedId)) {
      setSelectedId(null);
      setDetailOpen(false);
    }
  }, [selectedId, watchers]);

  const eventByWatcher = useMemo(() => {
    const summary = new Map<number, { count: number; latest?: WatcherEvent }>();
    for (const event of events) {
      const current = summary.get(event.watcher_id) || { count: 0 };
      current.count += 1;
      if (!current.latest || Date.parse(event.timestamp) > Date.parse(current.latest.timestamp)) {
        current.latest = event;
      }
      summary.set(event.watcher_id, current);
    }
    return summary;
  }, [events]);

  const filteredWatchers = useMemo(() => {
    const term = search.trim().toLowerCase();
    return watchers
      .filter((watcher) => filter === "all" || watcher.state === filter)
      .filter((watcher) => {
        if (!term) return true;
        const latest = eventByWatcher.get(watcher.id)?.latest;
        return [watcher.name, watcher.job_id, watcher.hostname, watcher.job_name, watcher.pattern, latest?.matched_text, latest?.action_result]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(term);
      })
      .sort((left, right) => {
        if (sort === "name") return left.name.localeCompare(right.name);
        if (sort === "recent") return Date.parse(right.created_at || "0") - Date.parse(left.created_at || "0");
        const leftActivity = eventByWatcher.get(left.id)?.latest?.timestamp || left.last_check || left.created_at || "0";
        const rightActivity = eventByWatcher.get(right.id)?.latest?.timestamp || right.last_check || right.created_at || "0";
        return Date.parse(rightActivity) - Date.parse(leftActivity);
      });
  }, [eventByWatcher, filter, search, sort, watchers]);

  const selectedWatcher = selectedId ? watchers.find((watcher) => watcher.id === selectedId) || null : null;
  const selectedEvents = selectedWatcher ? events.filter((event) => event.watcher_id === selectedWatcher.id).slice(0, 60) : [];
  const counts = {
    total: watchers.length,
    active: watchers.filter((watcher) => watcher.state === "active").length,
    paused: watchers.filter((watcher) => watcher.state === "paused").length,
    static: watchers.filter((watcher) => watcher.state === "static").length,
    completed: watchers.filter((watcher) => watcher.state === "completed").length
  };

  const activeJobs = useMemo(() => jobs.filter((job) => job.state === "R" || job.state === "PD"), [jobs]);
  const listItems = useMemo<WatchersListItem[]>(
    () => filteredWatchers.length > 0 ? filteredWatchers.map((watcher) => ({ type: "watcher", watcher })) : [{ type: "empty" }],
    [filteredWatchers]
  );
  const sortLabel = sort === "activity" ? "Activity" : sort === "recent" ? "Created" : "Name";

  function cycleSort() {
    setSort((current) => current === "activity" ? "recent" : current === "recent" ? "name" : "activity");
  }

  async function pauseResume(watcher: Watcher) {
    const nextState = watcher.state === "paused" ? "active" : "paused";
    setWatchers((current) => current.map((item) => item.id === watcher.id ? { ...item, state: nextState } : item));
    try {
      if (watcher.state === "paused") await api.resumeWatcher(watcher.id);
      else await api.pauseWatcher(watcher.id);
      void refreshData();
    } catch (actionError) {
      setError((actionError as Error).message || "Failed to update watcher");
      setWatchers((current) => current.map((item) => item.id === watcher.id ? watcher : item));
    }
  }

  async function deleteWatcher(watcher: Watcher) {
    setDetailOpen(false);
    setSelectedId(null);
    setWatchers((current) => current.filter((item) => item.id !== watcher.id));
    try {
      await api.deleteWatcher(watcher.id);
      void refreshData();
    } catch (deleteError) {
      setError((deleteError as Error).message || "Failed to delete watcher");
      setWatchers((current) => upsertWatcher(current, watcher));
    }
  }

  async function triggerWatcher(watcher: Watcher) {
    try {
      await api.triggerWatcher(watcher.id);
      void refreshData();
    } catch (triggerError) {
      setError((triggerError as Error).message || "Failed to trigger watcher");
    }
  }

  function openCopyTargets(watcher: Watcher) {
    setActionWatcher(null);
    setCopySource(watcher);
    setCopyTargets([]);
  }

  function toggleCopyTarget(key: string) {
    setCopyTargets((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]);
  }

  async function copyWatcherToTargets() {
    if (!copySource || copyTargets.length === 0) return;
    setCopying(true);
    setError(null);
    try {
      const targets = activeJobs.filter((job) => copyTargets.includes(jobKey(job)));
      await Promise.all(targets.map((job) => api.createWatcher(buildCopiedWatcherPayload(copySource, job))));
      setCopySource(null);
      setCopyTargets([]);
      void refreshData();
    } catch (copyError) {
      setError((copyError as Error).message || "Failed to copy watcher");
    } finally {
      setCopying(false);
    }
  }

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      <View style={[styles.header, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <View style={{ flex: 1 }}>
          <AppText palette={palette} size={22} weight="900">Watchers</AppText>
          <AppText palette={palette} muted size={12}>{counts.active} active - {events.length} events - {socketConnected ? "live" : "reconnecting"}</AppText>
        </View>
        <IconButton palette={palette} icon={RefreshCw} label="Refresh" onPress={refreshData} disabled={loading} />
        <Button
          palette={palette}
          title="Create"
          icon={Plus}
          onPress={() => setCreatePickerOpen(true)}
        />
      </View>

      <FlatList
        data={listItems}
        keyExtractor={(item) => item.type === "watcher" ? String(item.watcher.id) : "empty"}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={styles.content}
        initialNumToRender={12}
        maxToRenderPerBatch={12}
        windowSize={7}
        removeClippedSubviews
        ListHeaderComponent={
          <View style={styles.listHeader}>
            <Card palette={palette}>
              <View style={styles.searchRow}>
                <Search size={18} color={palette.muted} />
                <View style={{ flex: 1 }}>
                  <TextField palette={palette} value={search} onChangeText={setSearch} placeholder="Search watchers, actions, jobs, events" />
                </View>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`Sort watchers by ${sortLabel}`}
                  onPress={cycleSort}
                  style={({ pressed }) => [
                    styles.sortButton,
                    {
                      backgroundColor: palette.surfaceAlt,
                      borderColor: palette.border,
                      opacity: pressed ? 0.72 : 1
                    }
                  ]}
                >
                  <AppText palette={palette} size={11} weight="700" numberOfLines={1}>{sortLabel}</AppText>
                </Pressable>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
                {(["all", "active", "paused", "static", "completed"] as FilterState[]).map((state) => (
                  <Chip
                    key={state}
                    palette={palette}
                    label={`${state === "all" ? "All" : state} ${state === "all" ? counts.total : counts[state]}`}
                    active={filter === state}
                    tone={state === "all" ? "neutral" : watcherTone(state)}
                    onPress={() => setFilter(state)}
                  />
                ))}
              </ScrollView>
            </Card>

            {error ? <Card palette={palette}><SectionHeader palette={palette} title="Error" subtitle={error} /></Card> : null}
          </View>
        }
        renderItem={({ item }) => {
          if (item.type === "empty") {
            return <EmptyState palette={palette} title="No watchers" body="Create one from a running or pending job." icon={Zap} />;
          }
          const watcher = item.watcher;
          const summary = eventByWatcher.get(watcher.id);
          const colors = toneColors(palette, watcherTone(watcher.state));
          return (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Open watcher ${watcher.name}`}
              onPress={() => {
                setSelectedId(watcher.id);
                setDetailOpen(true);
              }}
              onLongPress={() => setActionWatcher(watcher)}
              style={[
                styles.watcherRow,
                {
                  borderColor: colors.border,
                  backgroundColor: colors.background
                }
              ]}
            >
              <View style={[styles.watcherRail, { backgroundColor: colors.text }]} />
              <View style={{ flex: 1 }}>
                <AppText palette={palette} weight="900">{watcher.name}</AppText>
                <AppText palette={palette} muted size={12}>Job #{watcher.job_id} on {watcher.hostname}</AppText>
                <AppText palette={palette} muted size={12} numberOfLines={1}>{watcher.trigger_on_job_end ? `job end: ${(watcher.trigger_job_states || []).join(", ")}` : watcher.pattern || "manual trigger"}</AppText>
              </View>
              <View style={{ alignItems: "flex-end", gap: 5 }}>
                <Chip palette={palette} label={watcher.state} active tone={watcherTone(watcher.state)} />
                <AppText palette={palette} muted size={12}>{summary?.count || 0} events</AppText>
                <ChevronRight size={18} color={palette.muted} />
              </View>
            </Pressable>
          );
        }}
      />

      <Sheet palette={palette} visible={createPickerOpen} title="Create Watcher" onClose={() => setCreatePickerOpen(false)}>
        <Card palette={palette}>
          <SectionHeader palette={palette} title="Create From Job" subtitle="Choose a running or pending job." />
          {activeJobs.length === 0 ? <AppText palette={palette} muted>No running or pending jobs are loaded.</AppText> : null}
          {activeJobs.slice(0, 40).map((job) => (
            <Pressable
              key={`${job.hostname}:${job.job_id}`}
              onPress={() => {
                setCreatePickerOpen(false);
                setCreatorTarget({ jobId: job.job_id, hostname: job.hostname });
              }}
              style={[styles.eventRow, { borderColor: palette.border }]}
            >
              <View style={{ flex: 1 }}>
                <AppText palette={palette} weight="700">{job.name || `Job ${job.job_id}`}</AppText>
                <AppText palette={palette} muted size={12}>#{job.job_id} on {job.hostname}</AppText>
              </View>
              <Plus size={18} color={palette.accent} />
            </Pressable>
          ))}
        </Card>

        <Card palette={palette}>
          <Button
            palette={palette}
            title="Create manually"
            icon={Plus}
            variant="secondary"
            onPress={() => {
              setCreatePickerOpen(false);
              setCreatorTarget({ jobId: "", hostname: "" });
            }}
          />
        </Card>
      </Sheet>

      {creatorTarget ? (
        <WatcherCreatorSheet
          palette={palette}
          api={api}
          visible={Boolean(creatorTarget)}
          jobId={creatorTarget.jobId}
          hostname={creatorTarget.hostname}
          onClose={() => setCreatorTarget(null)}
          onCreated={refreshData}
        />
      ) : null}

      {actionWatcher ? (
        <Sheet palette={palette} visible={Boolean(actionWatcher)} title="Watcher Options" onClose={() => setActionWatcher(null)}>
          <Card palette={palette}>
            <SectionHeader palette={palette} title={actionWatcher.name} subtitle={`Job #${actionWatcher.job_id} on ${actionWatcher.hostname}`} />
            <ActionRow
              palette={palette}
              icon={ChevronRight}
              title="Open details"
              onPress={() => {
                setSelectedId(actionWatcher.id);
                setDetailOpen(true);
                setActionWatcher(null);
              }}
            />
            <ActionRow
              palette={palette}
              icon={Copy}
              title="Copy to jobs"
              subtitle="Choose running or pending jobs to attach this watcher to"
              onPress={() => openCopyTargets(actionWatcher)}
            />
            <ActionRow
              palette={palette}
              icon={actionWatcher.state === "paused" ? PlayCircle : PauseCircle}
              title={actionWatcher.state === "paused" ? "Resume watcher" : "Pause watcher"}
              onPress={() => {
                const watcher = actionWatcher;
                setActionWatcher(null);
                void pauseResume(watcher);
              }}
            />
            <ActionRow
              palette={palette}
              icon={Zap}
              title="Trigger now"
              onPress={() => {
                const watcher = actionWatcher;
                setActionWatcher(null);
                void triggerWatcher(watcher);
              }}
            />
            <ActionRow
              palette={palette}
              icon={Trash2}
              title="Delete watcher"
              tone="danger"
              onPress={() => {
                const watcher = actionWatcher;
                setActionWatcher(null);
                void deleteWatcher(watcher);
              }}
            />
          </Card>
        </Sheet>
      ) : null}

      {copySource ? (
        <Sheet palette={palette} visible={Boolean(copySource)} title="Copy Watcher" onClose={() => setCopySource(null)}>
          <Card palette={palette}>
            <SectionHeader
              palette={palette}
              title={copySource.name}
              subtitle="Select running or pending jobs for the copied watcher."
            />
            {activeJobs.length === 0 ? <AppText palette={palette} muted>No running or pending jobs are loaded.</AppText> : null}
            {activeJobs.map((job) => {
              const key = jobKey(job);
              const selected = copyTargets.includes(key);
              return (
                <Pressable
                  key={key}
                  accessibilityRole="checkbox"
                  accessibilityState={{ checked: selected }}
                  onPress={() => toggleCopyTarget(key)}
                  style={({ pressed }) => [
                    styles.selectRow,
                    {
                      borderColor: selected ? palette.accent : palette.border,
                      backgroundColor: selected ? palette.accentSoft : palette.surface,
                      opacity: pressed ? 0.75 : 1
                    }
                  ]}
                >
                  <View style={[styles.checkBox, { borderColor: selected ? palette.accent : palette.border, backgroundColor: selected ? palette.accent : "transparent" }]}>
                    {selected ? <Check size={14} color={palette.background} strokeWidth={2.5} /> : null}
                  </View>
                  <View style={{ flex: 1 }}>
                    <AppText palette={palette} weight="700">{job.name || `Job ${job.job_id}`}</AppText>
                    <AppText palette={palette} muted size={12}>#{job.job_id} on {job.hostname}</AppText>
                  </View>
                  <Chip palette={palette} label={job.state} active tone={job.state === "R" ? "success" : "warning"} />
                </Pressable>
              );
            })}
          </Card>
          <Card palette={palette}>
            <View style={styles.actions}>
              <Button palette={palette} title="Cancel" variant="secondary" onPress={() => setCopySource(null)} style={styles.actionButton} />
              <Button
                palette={palette}
                title={copyTargets.length === 0 ? "Copy" : `Copy to ${copyTargets.length}`}
                icon={Copy}
                loading={copying}
                disabled={copyTargets.length === 0}
                onPress={copyWatcherToTargets}
                style={styles.actionButton}
              />
            </View>
          </Card>
        </Sheet>
      ) : null}

      {selectedWatcher ? (
        <WatcherDetailSheet
          palette={palette}
          visible={detailOpen}
          watcher={selectedWatcher}
          events={selectedEvents}
          onClose={() => setDetailOpen(false)}
          onPauseResume={() => pauseResume(selectedWatcher)}
          onTrigger={() => triggerWatcher(selectedWatcher)}
          onDelete={() => deleteWatcher(selectedWatcher)}
        />
      ) : null}
    </View>
  );
}

function upsertWatcher(current: Watcher[], watcher: Watcher): Watcher[] {
  const index = current.findIndex((item) => item.id === watcher.id);
  if (index < 0) return [watcher, ...current];
  const next = [...current];
  next[index] = watcher;
  return next;
}

function jobKey(job: JobInfo) {
  return `${job.hostname}:${job.job_id}`;
}

function buildCopiedWatcherPayload(watcher: Watcher, job: JobInfo): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    job_id: job.job_id,
    hostname: job.hostname,
    name: watcher.name,
    pattern: watcher.pattern,
    captures: watcher.captures || [],
    interval_seconds: watcher.interval_seconds || 30,
    actions: watcher.actions || [],
    timer_mode_enabled: Boolean(watcher.timer_mode_enabled),
    timer_interval_seconds: watcher.timer_interval_seconds || 30,
    trigger_on_job_end: Boolean(watcher.trigger_on_job_end),
    trigger_job_states: watcher.trigger_job_states || []
  };
  if (watcher.condition) payload.condition = watcher.condition;
  if (watcher.variables) payload.variables = watcher.variables;
  if ((watcher as Watcher & { output_type?: string }).output_type) {
    payload.output_type = (watcher as Watcher & { output_type?: string }).output_type;
  }
  return payload;
}

function ActionRow({
  palette,
  icon: Icon,
  title,
  subtitle,
  tone = "neutral",
  onPress
}: {
  palette: Palette;
  icon: typeof ChevronRight;
  title: string;
  subtitle?: string;
  tone?: "neutral" | "danger";
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [
        styles.optionRow,
        {
          borderColor: palette.border,
          opacity: pressed ? 0.72 : 1
        }
      ]}
    >
      <View style={[styles.optionIcon, { backgroundColor: tone === "danger" ? palette.dangerSoft : palette.surfaceAlt, borderColor: palette.border }]}>
        <Icon size={18} color={tone === "danger" ? palette.danger : palette.muted} />
      </View>
      <View style={{ flex: 1 }}>
        <AppText palette={palette} weight="700" style={tone === "danger" ? { color: palette.danger } : undefined}>{title}</AppText>
        {subtitle ? <AppText palette={palette} muted size={12}>{subtitle}</AppText> : null}
      </View>
      <ChevronRight size={17} color={palette.subtle} />
    </Pressable>
  );
}

function WatcherDetailSheet({
  palette,
  visible,
  watcher,
  events,
  onClose,
  onPauseResume,
  onTrigger,
  onDelete
}: {
  palette: Palette;
  visible: boolean;
  watcher: Watcher;
  events: WatcherEvent[];
  onClose: () => void;
  onPauseResume: () => void;
  onTrigger: () => void;
  onDelete: () => void;
}) {
  const colors = toneColors(palette, watcherTone(watcher.state));
  const trigger = watcher.trigger_on_job_end
    ? `Job end: ${(watcher.trigger_job_states || []).join(", ") || "terminal states"}`
    : watcher.pattern || "Manual trigger";

  const rows: Array<[string, string | number | null | undefined]> = [
    ["Job", `#${watcher.job_id}${watcher.job_name ? ` - ${watcher.job_name}` : ""}`],
    ["Host", watcher.hostname],
    ["Trigger", trigger],
    ["Interval", `${watcher.interval_seconds}s`],
    ["Trigger count", watcher.trigger_count],
    ["Last check", watcher.last_check ? formatTimeAgo(watcher.last_check) : "Never"],
    ["Created", watcher.created_at ? formatTimeAgo(watcher.created_at) : "Unknown"],
    ["Actions", watcher.actions?.map((action) => action.type).join(", ") || "None"]
  ];

  return (
    <Sheet palette={palette} visible={visible} title="Watcher Details" onClose={onClose}>
      <Card palette={palette} style={{ backgroundColor: colors.background, borderColor: colors.border }}>
        <View style={styles.detailHeading}>
          <View style={{ flex: 1 }}>
            <AppText palette={palette} size={18} weight="900" numberOfLines={1}>{watcher.name}</AppText>
            <AppText palette={palette} size={12} weight="800" style={{ color: colors.text }}>{watcher.state}</AppText>
          </View>
          <Chip palette={palette} label={`${events.length} events`} active tone={watcherTone(watcher.state)} />
        </View>
        <View style={styles.actions}>
          <Button
            palette={palette}
            title={watcher.state === "paused" ? "Resume" : "Pause"}
            icon={watcher.state === "paused" ? PlayCircle : PauseCircle}
            variant="secondary"
            onPress={onPauseResume}
            style={styles.actionButton}
          />
          <Button palette={palette} title="Trigger" icon={Zap} variant="secondary" onPress={onTrigger} style={styles.actionButton} />
          <Button palette={palette} title="Delete" icon={Trash2} variant="danger" onPress={onDelete} style={styles.actionButton} />
        </View>
      </Card>

      <Card palette={palette}>
        <SectionHeader palette={palette} title="Configuration" subtitle="Trigger, job target, and action setup" />
        {rows.map(([label, value]) => (
          <View key={label} style={[styles.detailRow, { borderColor: palette.border }]}>
            <AppText palette={palette} muted size={12}>{label}</AppText>
            <AppText palette={palette} weight="800" style={{ flex: 1, textAlign: "right" }}>
              {value === null || value === undefined || value === "" ? "N/A" : value}
            </AppText>
          </View>
        ))}
      </Card>

      <Card palette={palette}>
        <SectionHeader palette={palette} title="Recent Activity" subtitle={`${events.length} latest events`} />
        {events.length === 0 ? <EmptyState palette={palette} title="No activity yet" body="This watcher has not triggered recently." icon={Radio} /> : null}
        {events.map((event) => (
          <View key={event.id} style={[styles.eventRow, { borderColor: palette.border }]}>
            <View style={{ flex: 1 }}>
              <AppText palette={palette} weight="800">{event.action_type}</AppText>
              <AppText palette={palette} muted size={12} numberOfLines={3}>{event.matched_text || event.action_result || "No event payload"}</AppText>
            </View>
            <View style={{ alignItems: "flex-end", gap: 4 }}>
              <Chip palette={palette} label={event.success ? "ok" : "failed"} active tone={event.success ? "success" : "danger"} />
              <AppText palette={palette} muted size={12}>{formatTimeAgo(event.timestamp)}</AppText>
            </View>
          </View>
        ))}
      </Card>
    </Sheet>
  );
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
  content: {
    paddingHorizontal: 14,
    paddingTop: 10,
    paddingBottom: 126,
    gap: 10
  },
  listHeader: {
    gap: 10
  },
  searchRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  chips: {
    gap: 8,
    paddingVertical: 4
  },
  sortButton: {
    minWidth: 70,
    minHeight: 38,
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 9
  },
  watcherRow: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    paddingVertical: 11,
    paddingLeft: 15,
    paddingRight: 11,
    flexDirection: "row",
    gap: 10,
    marginBottom: 8,
    overflow: "hidden"
  },
  watcherRail: {
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    width: 4
  },
  actions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8
  },
  actionButton: {
    flex: 1,
    minWidth: 104
  },
  detailHeading: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10
  },
  detailRow: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: 9,
    flexDirection: "row",
    gap: 12,
    alignItems: "flex-start"
  },
  eventRow: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: 10,
    flexDirection: "row",
    gap: 10,
    alignItems: "center"
  },
  optionRow: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: 11,
    flexDirection: "row",
    alignItems: "center",
    gap: 10
  },
  optionIcon: {
    width: 34,
    height: 34,
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center"
  },
  selectRow: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginBottom: 8
  },
  checkBox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center"
  }
});
