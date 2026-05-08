import React, { useImperativeHandle, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, FileText, FolderOpen, History, Play, RefreshCw, Save, Server, Trash2, Wand2 } from "lucide-react-native";
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";

import type { SsyncApiClient } from "../api/client";
import { FileBrowserSheet } from "../components/FileBrowserSheet";
import { AppText, Button, Card, SectionHeader, Sheet, TextField, ToggleRow } from "../components/ui";
import type { Palette } from "../theme/colors";
import type { HostInfo, LaunchEvent, LaunchJobResponse } from "../types/api";
import type { LaunchDraft, ScriptTemplate, SyncPreferences } from "../types/settings";
import { defaultScript, JobParameters, parseSbatchDirectives, updateScriptWithParameters, validateLaunchParameters } from "../utils/sbatch";

type LaunchScreenProps = {
  palette: Palette;
  api: SsyncApiClient;
  hosts: HostInfo[];
  sync: SyncPreferences;
  templates: ScriptTemplate[];
  draft?: LaunchDraft | null;
  onDraftApplied?: () => void;
  onAddTemplate: (template: ScriptTemplate) => void;
  onDeleteTemplate?: (id: string) => void;
  onMarkTemplateUsed: (id: string) => void;
  onOpenJob: (jobId: string, host: string) => void;
};

export function LaunchScreen({
  palette,
  api,
  hosts,
  sync,
  templates,
  draft,
  onDraftApplied,
  onAddTemplate,
  onDeleteTemplate,
  onMarkTemplateUsed,
  onOpenJob
}: LaunchScreenProps) {
  const [script, setScript] = useState(defaultScript());
  const [host, setHost] = useState(hosts[0]?.hostname || "");
  const [sourceDir, setSourceDir] = useState("");
  const [parameters, setParameters] = useState<JobParameters>(() => parseSbatchDirectives(defaultScript()));
  const [exclude, setExclude] = useState(sync.exclude.join("\n"));
  const [include, setInclude] = useState(sync.include.join("\n"));
  const [noGitignore, setNoGitignore] = useState(sync.noGitignore);
  const [abortOnSetupFailure, setAbortOnSetupFailure] = useState(sync.abortOnSetupFailure);
  const [launching, setLaunching] = useState(false);
  const [launchResponse, setLaunchResponse] = useState<LaunchJobResponse | null>(null);
  const [launchEvents, setLaunchEvents] = useState<LaunchEvent[]>([]);
  const [browserOpen, setBrowserOpen] = useState(false);
  const [hostPickerOpen, setHostPickerOpen] = useState(false);
  const [templatePickerOpen, setTemplatePickerOpen] = useState(false);
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [templateDescription, setTemplateDescription] = useState("");
  const [draftSourceJobId, setDraftSourceJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const editorRef = useRef<TextInput | null>(null);

  React.useEffect(() => {
    if (!host && hosts[0]?.hostname) setHost(hosts[0].hostname);
  }, [host, hosts]);

  React.useEffect(() => {
    if (!draft) return;
    const parsed = parseSbatchDirectives(draft.scriptContent);
    const nextParameters: JobParameters = {
      ...parsed,
      jobName: draft.sourceJobName || parsed.jobName,
      sourceDir: draft.sourceDir || ""
    };
    setScript(draft.scriptContent);
    setHost(draft.host);
    setSourceDir(draft.sourceDir || "");
    setParameters(nextParameters);
    setLaunchResponse(null);
    setLaunchEvents([]);
    setError(null);
    setDraftSourceJobId(draft.sourceJobId || null);
    onDraftApplied?.();
  }, [draft, onDraftApplied]);

  const selectedHost = useMemo(() => hosts.find((item) => item.hostname === host) || null, [host, hosts]);
  const selectedDefaults = selectedHost?.slurm_defaults;
  const sortedTemplates = useMemo(
    () => [...templates].sort((left, right) => {
      const leftUsed = left.last_used || left.created_at;
      const rightUsed = right.last_used || right.created_at;
      return Date.parse(rightUsed || "0") - Date.parse(leftUsed || "0");
    }),
    [templates]
  );
  const validation = validateLaunchParameters({ ...parameters, sourceDir }) || (!host ? "Choose a host before launching." : null);

  function setParam<K extends keyof JobParameters>(key: K, value: JobParameters[K]) {
    setParameters((current) => ({ ...current, [key]: value }));
  }

  function applyParameters(nextParameters = parameters) {
    setScript((current) => updateScriptWithParameters(current, { ...nextParameters, sourceDir }));
  }

  function applyDefaults() {
    if (!selectedDefaults) return;
    const next: JobParameters = {
      ...parameters,
      partition: selectedDefaults.partition || parameters.partition,
      account: selectedDefaults.account || parameters.account,
      constraint: selectedDefaults.constraint || parameters.constraint,
      cpus: selectedDefaults.cpus || parameters.cpus,
      memory: selectedDefaults.mem || parameters.memory,
      nodes: selectedDefaults.nodes || parameters.nodes,
      gpusPerNode: selectedDefaults.gpus_per_node || parameters.gpusPerNode,
      ntasksPerNode: selectedDefaults.ntasks_per_node || parameters.ntasksPerNode,
      gres: selectedDefaults.gres || parameters.gres,
      pythonEnv: selectedDefaults.python_env || parameters.pythonEnv,
      outputFile: selectedDefaults.output_pattern || parameters.outputFile,
      errorFile: selectedDefaults.error_pattern || parameters.errorFile,
      sourceDir
    };
    setParameters(next);
    setScript((current) => updateScriptWithParameters(current, next));
  }

  function applyTemplate(template: ScriptTemplate) {
    const next = template.parameters as JobParameters;
    setScript(template.script_content);
    setParameters({ ...parseSbatchDirectives(template.script_content), ...next });
    if (next.sourceDir) setSourceDir(String(next.sourceDir));
    onMarkTemplateUsed(template.id);
    setTemplatePickerOpen(false);
  }

  function saveTemplate() {
    const name = templateName.trim() || parameters.jobName || `Template ${new Date().toLocaleDateString()}`;
    onAddTemplate({
      id: `${Date.now()}`,
      name,
      description: templateDescription.trim() || undefined,
      script_content: script,
      parameters: { ...parameters, sourceDir },
      created_at: new Date().toISOString(),
      use_count: 0
    });
    setTemplateName("");
    setTemplateDescription("");
    setSaveTemplateOpen(false);
  }

  async function launch() {
    if (validation) {
      setError(validation);
      return;
    }

    setLaunching(true);
    setError(null);
    setLaunchEvents([]);
    try {
      const response = await api.launchJob({
        script_content: script,
        source_dir: sourceDir,
        host,
        job_name: parameters.jobName,
        cpus: parameters.cpus,
        mem: parameters.memory,
        time: parameters.timeLimit,
        partition: parameters.partition,
        ntasks_per_node: parameters.ntasksPerNode,
        n_tasks_per_node: parameters.ntasksPerNode,
        nodes: parameters.nodes,
        gpus_per_node: parameters.gpusPerNode,
        gres: parameters.gres,
        output: parameters.outputFile,
        error: parameters.errorFile,
        constraint: parameters.constraint,
        account: parameters.account,
        python_env: parameters.pythonEnv,
        exclude: exclude.split("\n").map((item) => item.trim()).filter(Boolean),
        include: include.split("\n").map((item) => item.trim()).filter(Boolean),
        no_gitignore: noGitignore,
        abort_on_setup_failure: abortOnSetupFailure
      });
      setLaunchResponse(response);
      if (response.job_id) {
        onOpenJob(response.job_id, response.hostname);
      } else if (response.launch_id) {
        void pollLaunch(response.launch_id);
      }
    } catch (launchError) {
      setError((launchError as Error).message || "Launch failed");
    } finally {
      setLaunching(false);
    }
  }

  async function pollLaunch(launchId: string) {
    for (let i = 0; i < 80; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, i < 3 ? 1000 : 2000));
      try {
        const status = await api.getLaunchStatus(launchId);
        setLaunchEvents(status.events);
        if (status.terminal) {
          if (status.success && status.job_id) onOpenJob(status.job_id, status.hostname);
          else if (!status.success) setError(status.message || "Launch failed");
          return;
        }
      } catch {
        return;
      }
    }
  }

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      <View style={[styles.header, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <View style={{ flex: 1 }}>
          <AppText palette={palette} size={22} weight="900">Launch</AppText>
          <AppText palette={palette} muted size={12}>
            {draftSourceJobId ? `Resubmit #${draftSourceJobId}` : host || "Choose host"} - {sourceDir || "source directory required"}
          </AppText>
        </View>
        <Button palette={palette} title="Launch" icon={Play} onPress={launch} loading={launching} disabled={Boolean(validation)} />
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Card palette={palette}>
          <SectionHeader
            palette={palette}
            title="Script"
            subtitle="Main sbatch editor"
            action={<Button palette={palette} title="Save" icon={Save} variant="secondary" onPress={() => setSaveTemplateOpen(true)} />}
          />
          <ScriptEditor ref={editorRef} palette={palette} value={script} onChangeText={setScript} />
          <View style={styles.actions}>
            <Button palette={palette} title="Parse directives" icon={RefreshCw} variant="secondary" onPress={() => setParameters((current) => ({ ...current, ...parseSbatchDirectives(script) }))} style={styles.actionButton} />
            <Button palette={palette} title="Apply fields" icon={Wand2} variant="secondary" onPress={() => applyParameters()} style={styles.actionButton} />
          </View>
        </Card>

        <Card palette={palette} style={styles.compactCard}>
          <SectionHeader palette={palette} title="Target" subtitle="Cluster and source directory" />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Choose host"
            onPress={() => setHostPickerOpen(true)}
            style={({ pressed }) => [
              styles.selectButton,
              { backgroundColor: palette.surfaceAlt, borderColor: host ? palette.accent : palette.border, opacity: pressed ? 0.78 : 1 }
            ]}
          >
            <View style={[styles.selectIcon, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <Server size={18} color={host ? palette.accent : palette.muted} />
            </View>
            <View style={{ flex: 1 }}>
              <AppText palette={palette} weight="800">{host || "Choose host"}</AppText>
              <AppText palette={palette} muted size={12} numberOfLines={1}>
                {selectedDefaults?.partition ? `Default partition ${selectedDefaults.partition}` : selectedHost?.work_dir || "No host selected"}
              </AppText>
            </View>
            <ChevronDown size={20} color={palette.muted} />
          </Pressable>
          <View style={styles.actions}>
            <Button palette={palette} title="Browse" icon={FolderOpen} variant="secondary" onPress={() => setBrowserOpen(true)} style={styles.actionButton} />
            <Button palette={palette} title="Defaults" icon={Wand2} variant="secondary" onPress={applyDefaults} disabled={!selectedDefaults} style={styles.actionButton} />
          </View>
          <TextField palette={palette} label="Source directory" value={sourceDir} onChangeText={setSourceDir} placeholder="/home/user/project" />
        </Card>

        <Card palette={palette} style={styles.compactCard}>
          <SectionHeader
            palette={palette}
            title="Templates"
            subtitle={templates.length ? `${templates.length} saved` : "No saved templates"}
          />
          <View style={styles.actions}>
            <Button palette={palette} title="Use template" icon={History} variant="secondary" onPress={() => setTemplatePickerOpen(true)} style={styles.actionButton} />
            <Button palette={palette} title="Save" icon={Save} variant="secondary" onPress={() => setSaveTemplateOpen(true)} style={styles.actionButton} />
          </View>
          {sortedTemplates.slice(0, 3).map((template) => (
            <Pressable
              key={template.id}
              accessibilityRole="button"
              onPress={() => applyTemplate(template)}
              style={({ pressed }) => [styles.templateRow, { borderColor: palette.border, opacity: pressed ? 0.78 : 1 }]}
            >
              <FileText size={17} color={palette.muted} />
              <View style={{ flex: 1 }}>
                <AppText palette={palette} weight="700" numberOfLines={1}>{template.name}</AppText>
                <AppText palette={palette} muted size={12}>Used {template.use_count} times</AppText>
              </View>
            </Pressable>
          ))}
        </Card>

        <Card palette={palette} style={styles.compactCard}>
          <SectionHeader
            palette={palette}
            title="Resources"
            subtitle="Fields that can update sbatch directives"
            action={<Button palette={palette} title="Apply" icon={RefreshCw} variant="secondary" onPress={() => applyParameters()} />}
          />
          <TextField palette={palette} label="Job name" value={parameters.jobName || ""} onChangeText={(value) => setParam("jobName", value)} />
          <View style={styles.grid}>
            <FieldRow palette={palette} label="CPUs" value={parameters.cpus} onChange={(value) => setParam("cpus", value)} />
            <FieldRow palette={palette} label="Memory GB" value={parameters.memory} onChange={(value) => setParam("memory", value)} />
            <FieldRow palette={palette} label="Time min" value={parameters.timeLimit} onChange={(value) => setParam("timeLimit", value)} />
            <FieldRow palette={palette} label="Nodes" value={parameters.nodes} onChange={(value) => setParam("nodes", value)} />
            <FieldRow palette={palette} label="Tasks/node" value={parameters.ntasksPerNode} onChange={(value) => setParam("ntasksPerNode", value)} />
            <FieldRow palette={palette} label="GPUs/node" value={parameters.gpusPerNode} onChange={(value) => setParam("gpusPerNode", value)} />
          </View>
          <TextField palette={palette} label="Partition" value={parameters.partition || ""} onChangeText={(value) => setParam("partition", value)} />
          <TextField palette={palette} label="Account" value={parameters.account || ""} onChangeText={(value) => setParam("account", value)} />
          <TextField palette={palette} label="Constraint" value={parameters.constraint || ""} onChangeText={(value) => setParam("constraint", value)} />
          <TextField palette={palette} label="GRES" value={parameters.gres || ""} onChangeText={(value) => setParam("gres", value)} />
          <TextField palette={palette} label="Python environment" value={parameters.pythonEnv || ""} onChangeText={(value) => setParam("pythonEnv", value)} />
          <TextField palette={palette} label="Output pattern" value={parameters.outputFile || ""} onChangeText={(value) => setParam("outputFile", value)} />
          <TextField palette={palette} label="Error pattern" value={parameters.errorFile || ""} onChangeText={(value) => setParam("errorFile", value)} />
        </Card>

        <Card palette={palette} style={styles.compactCard}>
          <SectionHeader palette={palette} title="Sync" subtitle="Include/exclude controls used before submission" />
          <TextField palette={palette} label="Exclude patterns" value={exclude} onChangeText={setExclude} multiline />
          <TextField palette={palette} label="Include patterns" value={include} onChangeText={setInclude} multiline />
          <ToggleRow palette={palette} title="Ignore .gitignore" value={noGitignore} onValueChange={setNoGitignore} />
          <ToggleRow palette={palette} title="Abort on setup failure" value={abortOnSetupFailure} onValueChange={setAbortOnSetupFailure} />
        </Card>

        {validation ? <Card palette={palette}><SectionHeader palette={palette} title="Required" subtitle={validation} /></Card> : null}
        {error ? <Card palette={palette}><SectionHeader palette={palette} title="Launch Error" subtitle={error} /></Card> : null}
        {launchResponse || launchEvents.length > 0 ? (
          <Card palette={palette}>
            <SectionHeader palette={palette} title="Launch Status" subtitle={launchResponse?.message || "Tracking background launch"} />
            {launchEvents.slice(-12).map((event) => (
              <AppText key={`${event.launch_id}:${event.sequence}`} palette={palette} muted size={12}>
                {event.stage || event.type}: {event.message || ""}
              </AppText>
            ))}
          </Card>
        ) : null}
      </ScrollView>

      <FileBrowserSheet
        palette={palette}
        api={api}
        visible={browserOpen}
        initialPath={sourceDir || selectedHost?.work_dir || "/home"}
        onSelect={setSourceDir}
        onClose={() => setBrowserOpen(false)}
      />

      <HostSheet palette={palette} visible={hostPickerOpen} hosts={hosts} value={host} onSelect={setHost} onClose={() => setHostPickerOpen(false)} />

      <Sheet palette={palette} visible={templatePickerOpen} title="Templates" onClose={() => setTemplatePickerOpen(false)}>
        <Card palette={palette}>
          <SectionHeader palette={palette} title="Saved Templates" subtitle={`${templates.length} available`} />
          {sortedTemplates.length === 0 ? <AppText palette={palette} muted>No saved templates yet.</AppText> : null}
          {sortedTemplates.map((template) => (
            <View key={template.id} style={[styles.templateCard, { borderColor: palette.border }]}>
              <Pressable accessibilityRole="button" onPress={() => applyTemplate(template)} style={{ flex: 1 }}>
                <AppText palette={palette} weight="800">{template.name}</AppText>
                {template.description ? <AppText palette={palette} muted size={12}>{template.description}</AppText> : null}
                <AppText palette={palette} muted size={12}>Used {template.use_count} times</AppText>
              </Pressable>
              {onDeleteTemplate ? (
                <Pressable accessibilityRole="button" onPress={() => onDeleteTemplate(template.id)} style={[styles.iconButton, { borderColor: palette.border, backgroundColor: palette.surfaceAlt }]}>
                  <Trash2 size={17} color={palette.danger} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </Card>
      </Sheet>

      <Sheet palette={palette} visible={saveTemplateOpen} title="Save Template" onClose={() => setSaveTemplateOpen(false)}>
        <Card palette={palette}>
          <SectionHeader palette={palette} title="Template Details" subtitle="Save script, resource fields, and source directory." />
          <TextField palette={palette} label="Name" value={templateName} onChangeText={setTemplateName} placeholder={parameters.jobName || "Template name"} />
          <TextField palette={palette} label="Description" value={templateDescription} onChangeText={setTemplateDescription} placeholder="Optional note" />
          <Button palette={palette} title="Save template" icon={Save} onPress={saveTemplate} />
        </Card>
      </Sheet>
    </View>
  );
}

const ScriptEditor = React.forwardRef<TextInput, { palette: Palette; value: string; onChangeText: (value: string) => void }>(
  function ScriptEditor({ palette, value, onChangeText }, ref) {
    const inputRef = useRef<TextInput | null>(null);
    const [mode, setMode] = useState<"insert" | "normal">("normal");
    const [selection, setSelection] = useState({ start: 0, end: 0 });
    useImperativeHandle(ref, () => inputRef.current as TextInput);

    function enterInsert() {
      setMode("insert");
      requestAnimationFrame(() => inputRef.current?.focus());
    }

    function leaveInsert(nextValue: string, cursor: number) {
      setMode("normal");
      onChangeText(nextValue);
      setCursor(cursor);
    }

    function setCursor(position: number) {
      const cursor = Math.max(0, Math.min(value.length, position));
      const nextSelection = { start: cursor, end: cursor };
      setSelection(nextSelection);
      requestAnimationFrame(() => {
        inputRef.current?.setNativeProps({ selection: nextSelection });
      });
    }

    function currentLineBounds(position = selection.start) {
      const start = value.lastIndexOf("\n", Math.max(0, position - 1)) + 1;
      const nextBreak = value.indexOf("\n", position);
      const end = nextBreak === -1 ? value.length : nextBreak;
      return { start, end };
    }

    function moveVertical(direction: -1 | 1) {
      const { start } = currentLineBounds();
      const column = selection.start - start;
      if (direction < 0) {
        if (start === 0) return;
        const previousEnd = start - 1;
        const previousStart = value.lastIndexOf("\n", Math.max(0, previousEnd - 1)) + 1;
        setCursor(Math.min(previousStart + column, previousEnd));
        return;
      }
      const lineEnd = value.indexOf("\n", selection.start);
      if (lineEnd === -1) return;
      const nextStart = lineEnd + 1;
      const nextEndBreak = value.indexOf("\n", nextStart);
      const nextEnd = nextEndBreak === -1 ? value.length : nextEndBreak;
      setCursor(Math.min(nextStart + column, nextEnd));
    }

    function deleteCurrentLine() {
      const { start, end } = currentLineBounds();
      const deleteEnd = end < value.length ? end + 1 : end;
      onChangeText(`${value.slice(0, start)}${value.slice(deleteEnd)}`);
      setCursor(start);
    }

    function handleNormalCommand(command: string) {
      if (command === "i") {
        enterInsert();
      } else if (command === "a") {
        setCursor(selection.start + 1);
        enterInsert();
      } else if (command === "h") {
        setCursor(selection.start - 1);
      } else if (command === "l") {
        setCursor(selection.start + 1);
      } else if (command === "j") {
        moveVertical(1);
      } else if (command === "k") {
        moveVertical(-1);
      } else if (command === "0") {
        setCursor(currentLineBounds().start);
      } else if (command === "$") {
        setCursor(currentLineBounds().end);
      } else if (command === "x") {
        onChangeText(`${value.slice(0, selection.start)}${value.slice(selection.start + 1)}`);
        setCursor(selection.start);
      } else if (command === "o") {
        const { end } = currentLineBounds();
        const cursor = end + 1;
        onChangeText(`${value.slice(0, end)}\n${value.slice(end)}`);
        setCursor(cursor);
        setMode("insert");
      } else if (command === "O") {
        const { start } = currentLineBounds();
        onChangeText(`${value.slice(0, start)}\n${value.slice(start)}`);
        setCursor(start);
        setMode("insert");
      } else if (command === "d") {
        deleteCurrentLine();
      }
    }

    function handleChange(next: string) {
      const lengthDelta = next.length - value.length;
      const cursor = Math.max(0, Math.min(next.length, selection.end + lengthDelta));
      if (mode === "normal") {
        const command = lengthDelta > 0 ? next.slice(Math.max(0, cursor - lengthDelta), cursor).slice(-1) : "";
        onChangeText(value);
        requestAnimationFrame(() => handleNormalCommand(command));
        return;
      }
      if (next.slice(0, cursor).endsWith("jj")) {
        leaveInsert(`${next.slice(0, cursor - 2)}${next.slice(cursor)}`, cursor - 2);
        return;
      }
      onChangeText(next);
    }

    return (
      <View>
        <View style={styles.editorToolbar}>
          <Pressable
            accessibilityRole="button"
            onPress={enterInsert}
            style={[
              styles.modePill,
              {
                borderColor: mode === "insert" ? palette.accent : palette.border,
                backgroundColor: mode === "insert" ? palette.accentSoft : palette.surfaceAlt
              }
            ]}
          >
            <AppText palette={palette} size={12} weight="700">{mode === "insert" ? "INSERT" : "NORMAL"}</AppText>
          </Pressable>
          <AppText palette={palette} muted size={12}>Normal: h j k l, 0, $, x, d, i, a, o, O. Insert: jj.</AppText>
        </View>
        <TextInput
          ref={inputRef}
          value={value}
          onChangeText={handleChange}
          onBlur={() => setMode("normal")}
          onSelectionChange={(event) => setSelection(event.nativeEvent.selection)}
          selection={selection}
          multiline
          autoCapitalize="none"
          autoCorrect={false}
          spellCheck={false}
          textAlignVertical="top"
          style={[
            styles.editor,
            {
              color: palette.text,
              backgroundColor: palette.surfaceAlt,
              borderColor: mode === "insert" ? palette.accent : palette.border
            }
          ]}
        />
      </View>
    );
  }
);

function HostSheet({
  palette,
  visible,
  hosts,
  value,
  onSelect,
  onClose
}: {
  palette: Palette;
  visible: boolean;
  hosts: HostInfo[];
  value: string;
  onSelect: (host: string) => void;
  onClose: () => void;
}) {
  return (
    <Sheet palette={palette} visible={visible} title="Choose Host" onClose={onClose}>
      <Card palette={palette}>
        <SectionHeader palette={palette} title="Cluster Target" subtitle={`${hosts.length} configured hosts`} />
        {hosts.length === 0 ? <AppText palette={palette} muted>No hosts are loaded yet.</AppText> : null}
        {hosts.map((item) => {
          const selected = item.hostname === value;
          return (
            <Pressable
              key={item.hostname}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              onPress={() => {
                onSelect(item.hostname);
                onClose();
              }}
              style={({ pressed }) => [
                styles.hostOption,
                {
                  backgroundColor: selected ? palette.accentSoft : palette.surface,
                  borderColor: selected ? palette.accent : palette.border,
                  opacity: pressed ? 0.78 : 1
                }
              ]}
            >
              <View style={{ flex: 1 }}>
                <AppText palette={palette} weight="800">{item.hostname}</AppText>
                <AppText palette={palette} muted size={12} numberOfLines={1}>
                  {item.slurm_defaults?.partition ? `Partition ${item.slurm_defaults.partition}` : item.work_dir || "No default partition"}
                </AppText>
              </View>
              {selected ? <Check size={20} color={palette.accent} strokeWidth={2.5} /> : null}
            </Pressable>
          );
        })}
      </Card>
    </Sheet>
  );
}

function FieldRow({
  palette,
  label,
  value,
  onChange
}: {
  palette: Palette;
  label: string;
  value?: number;
  onChange: (value: number | undefined) => void;
}) {
  return (
    <View style={styles.gridItem}>
      <TextField
        palette={palette}
        label={label}
        value={value == null ? "" : String(value)}
        onChangeText={(text) => {
          const numeric = Number(text);
          onChange(text.trim() === "" || Number.isNaN(numeric) ? undefined : numeric);
        }}
        keyboardType="number-pad"
      />
    </View>
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
    paddingHorizontal: 12,
    paddingTop: 10,
    paddingBottom: 126,
    gap: 10
  },
  compactCard: {
    gap: 8
  },
  selectButton: {
    minHeight: 52,
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 10
  },
  selectIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center"
  },
  actions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8
  },
  actionButton: {
    flex: 1,
    minWidth: 120
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    columnGap: 8
  },
  gridItem: {
    width: "48%"
  },
  editor: {
    minHeight: 560,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 12,
    fontFamily: "Courier",
    fontSize: 13,
    lineHeight: 18
  },
  editorToolbar: {
    minHeight: 30,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 8
  },
  modePill: {
    minWidth: 72,
    minHeight: 28,
    borderRadius: 6,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 8
  },
  templateRow: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 10
  },
  templateCard: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 10
  },
  iconButton: {
    width: 36,
    height: 36,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center"
  },
  hostOption: {
    minHeight: 58,
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginBottom: 8
  }
});
