import React, { useEffect, useState } from "react";
import { Plus, Save, Trash2 } from "lucide-react-native";
import { View } from "react-native";

import type { SsyncApiClient } from "../api/client";
import type { Palette } from "../theme/colors";
import type { WatcherAction } from "../types/api";
import { Button, Card, SectionHeader, SegmentedControl, Sheet, TextField, ToggleRow } from "./ui";

type ActionType = "log_event" | "store_metric" | "run_command" | "notify_email" | "notify_slack" | "cancel_job" | "resubmit" | "pause_watcher";

type LocalAction = {
  type: ActionType;
  params: Record<string, string>;
};

const actionOptions: Array<{ value: ActionType; label: string }> = [
  { value: "log_event", label: "Log" },
  { value: "store_metric", label: "Metric" },
  { value: "run_command", label: "Command" },
  { value: "notify_email", label: "Email" },
  { value: "notify_slack", label: "Slack" },
  { value: "cancel_job", label: "Cancel" },
  { value: "resubmit", label: "Resubmit" },
  { value: "pause_watcher", label: "Pause" }
];

const templates = [
  { name: "Error Detection", pattern: "(error|ERROR|Error)" },
  { name: "Progress Tracking", pattern: "(\\d+)% complete" },
  { name: "GPU Memory", pattern: "GPU memory: (\\d+)MB" },
  { name: "Loss Tracking", pattern: "loss: ([\\d\\.]+)" }
];

export function WatcherCreatorSheet({
  palette,
  api,
  visible,
  jobId,
  hostname,
  onClose,
  onCreated
}: {
  palette: Palette;
  api: SsyncApiClient;
  visible: boolean;
  jobId: string;
  hostname: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [pattern, setPattern] = useState("");
  const [interval, setIntervalValue] = useState("30");
  const [captures, setCaptures] = useState("");
  const [condition, setCondition] = useState("");
  const [timerMode, setTimerMode] = useState(false);
  const [timerInterval, setTimerInterval] = useState("30");
  const [triggerOnJobEnd, setTriggerOnJobEnd] = useState(false);
  const [terminalStates, setTerminalStates] = useState("CD,F,CA,TO");
  const [actions, setActions] = useState<LocalAction[]>([{ type: "log_event", params: { message: "Pattern matched in job output" } }]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (visible) {
      setName(`Watcher for Job ${jobId}`);
      setError(null);
    }
  }, [jobId, visible]);

  async function submit() {
    if (!name.trim()) {
      setError("Watcher name is required.");
      return;
    }
    if (!triggerOnJobEnd && !pattern.trim()) {
      setError("Pattern is required unless this watcher only triggers on job end.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.createWatcher({
        job_id: jobId,
        hostname,
        name: name.trim(),
        pattern: pattern.trim(),
        captures: captures.split(",").map((item) => item.trim()).filter(Boolean),
        interval_seconds: Number(interval) || 30,
        condition: condition.trim() || undefined,
        actions: actions.map((action) => ({
          type: action.type,
          params: cleanParams(action.params)
        })) satisfies WatcherAction[],
        timer_mode_enabled: timerMode,
        timer_interval_seconds: Number(timerInterval) || 30,
        trigger_on_job_end: triggerOnJobEnd,
        trigger_job_states: terminalStates.split(",").map((item) => item.trim()).filter(Boolean)
      });
      onCreated();
      onClose();
    } catch (createError) {
      setError((createError as Error).message || "Failed to create watcher");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Sheet palette={palette} visible={visible} title="Create Watcher" onClose={onClose}>
      <Card palette={palette}>
        <SectionHeader palette={palette} title="Target" subtitle={`Job #${jobId} on ${hostname}`} />
        <TextField palette={palette} label="Name" value={name} onChangeText={setName} />
        <TextField palette={palette} label="Pattern" value={pattern} onChangeText={setPattern} placeholder="Regex pattern" />
        <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
          {templates.map((template) => (
            <Button
              key={template.name}
              palette={palette}
              title={template.name}
              variant="secondary"
              onPress={() => {
                setName(`${template.name} - Job ${jobId}`);
                setPattern(template.pattern);
              }}
            />
          ))}
        </View>
        <TextField palette={palette} label="Interval seconds" value={interval} onChangeText={setIntervalValue} keyboardType="number-pad" />
        <TextField palette={palette} label="Captured variable names" value={captures} onChangeText={setCaptures} placeholder="loss, step, accuracy" />
        <TextField palette={palette} label="Condition" value={condition} onChangeText={setCondition} placeholder="Optional expression" />
      </Card>

      <Card palette={palette}>
        <SectionHeader palette={palette} title="Timing" />
        <ToggleRow palette={palette} title="Timer mode" subtitle="Let this watcher fire on a timer as well as pattern matches." value={timerMode} onValueChange={setTimerMode} />
        {timerMode ? <TextField palette={palette} label="Timer interval seconds" value={timerInterval} onChangeText={setTimerInterval} keyboardType="number-pad" /> : null}
        <ToggleRow palette={palette} title="Trigger on job end" subtitle="Run watcher actions when the job enters terminal states." value={triggerOnJobEnd} onValueChange={setTriggerOnJobEnd} />
        {triggerOnJobEnd ? <TextField palette={palette} label="Job end states" value={terminalStates} onChangeText={setTerminalStates} /> : null}
      </Card>

      <Card palette={palette}>
        <SectionHeader palette={palette} title="Actions" action={<Button palette={palette} title="Add" icon={Plus} variant="secondary" onPress={() => setActions([...actions, { type: "log_event", params: { message: "" } }])} />} />
        {actions.map((action, index) => (
          <Card key={`${index}:${action.type}`} palette={palette} style={{ padding: 10 }}>
            <SegmentedControl
              palette={palette}
              value={action.type}
              options={actionOptions}
              onChange={(value) => {
                const next = [...actions];
                next[index] = { type: value, params: defaultParams(value) };
                setActions(next);
              }}
            />
            {renderActionFields(palette, action, (params) => {
              const next = [...actions];
              next[index] = { ...next[index], params };
              setActions(next);
            })}
            <Button palette={palette} title="Remove action" icon={Trash2} variant="danger" onPress={() => setActions(actions.filter((_, actionIndex) => actionIndex !== index))} />
          </Card>
        ))}
      </Card>

      {error ? <Card palette={palette}><SectionHeader palette={palette} title="Error" subtitle={error} /></Card> : null}
      <Button palette={palette} title="Create watcher" icon={Save} loading={submitting} onPress={submit} />
    </Sheet>
  );
}

function defaultParams(type: ActionType): Record<string, string> {
  if (type === "log_event") return { message: "" };
  if (type === "store_metric") return { metric_name: "", value: "" };
  if (type === "run_command") return { command: "" };
  if (type === "notify_email") return { to: "", subject: "", message: "" };
  if (type === "notify_slack") return { webhook: "", message: "" };
  if (type === "cancel_job") return { reason: "" };
  if (type === "resubmit") return { delay: "0" };
  return {};
}

function cleanParams(params: Record<string, string>): Record<string, string | number> {
  const clean: Record<string, string | number> = {};
  Object.entries(params).forEach(([key, value]) => {
    if (value.trim() === "") return;
    clean[key] = /^\d+$/.test(value) ? Number(value) : value;
  });
  return clean;
}

function renderActionFields(
  palette: Palette,
  action: LocalAction,
  onChange: (params: Record<string, string>) => void
) {
  const setParam = (key: string, value: string) => onChange({ ...action.params, [key]: value });
  if (action.type === "store_metric") {
    return (
      <>
        <TextField palette={palette} label="Metric name" value={action.params.metric_name || ""} onChangeText={(value) => setParam("metric_name", value)} />
        <TextField palette={palette} label="Value expression" value={action.params.value || ""} onChangeText={(value) => setParam("value", value)} />
      </>
    );
  }
  if (action.type === "run_command") {
    return <TextField palette={palette} label="Command" value={action.params.command || ""} onChangeText={(value) => setParam("command", value)} multiline />;
  }
  if (action.type === "notify_email") {
    return (
      <>
        <TextField palette={palette} label="To" value={action.params.to || ""} onChangeText={(value) => setParam("to", value)} />
        <TextField palette={palette} label="Subject" value={action.params.subject || ""} onChangeText={(value) => setParam("subject", value)} />
        <TextField palette={palette} label="Message" value={action.params.message || ""} onChangeText={(value) => setParam("message", value)} multiline />
      </>
    );
  }
  if (action.type === "notify_slack") {
    return (
      <>
        <TextField palette={palette} label="Webhook" value={action.params.webhook || ""} onChangeText={(value) => setParam("webhook", value)} />
        <TextField palette={palette} label="Message" value={action.params.message || ""} onChangeText={(value) => setParam("message", value)} multiline />
      </>
    );
  }
  if (action.type === "cancel_job") {
    return <TextField palette={palette} label="Reason" value={action.params.reason || ""} onChangeText={(value) => setParam("reason", value)} />;
  }
  if (action.type === "resubmit") {
    return <TextField palette={palette} label="Delay seconds" value={action.params.delay || "0"} onChangeText={(value) => setParam("delay", value)} keyboardType="number-pad" />;
  }
  if (action.type === "pause_watcher") {
    return null;
  }
  return <TextField palette={palette} label="Message" value={action.params.message || ""} onChangeText={(value) => setParam("message", value)} />;
}
