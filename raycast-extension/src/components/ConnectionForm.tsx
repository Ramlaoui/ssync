import {
  Action,
  ActionPanel,
  Form,
  Icon,
  Toast,
  showToast,
} from "@raycast/api";
import { useRef, useState } from "react";
import { SsyncClient } from "../api/client";
import { readLocalApiKey, saveConnection } from "../api/storage";
import {
  DEFAULT_API_URL,
  DEFAULT_HISTORY_WINDOW,
  DEFAULT_JOB_LIMIT,
  HISTORY_WINDOWS,
  isLoopback,
  normalizeApiUrl,
  validateJobLimit,
} from "../lib/connections";
import type { ConnectionSettings } from "../types/ssync";

export function ConnectionForm({
  initial,
  onConfigured,
}: {
  initial?: ConnectionSettings;
  onConfigured: (connection: ConnectionSettings) => void | Promise<void>;
}) {
  const [apiUrl, setApiUrl] = useState(initial?.apiUrl || DEFAULT_API_URL);
  const [apiKey, setApiKey] = useState(initial?.apiKey || "");
  const [name, setName] = useState(initial?.name || "");
  const [historyWindow, setHistory] = useState(
    initial?.historyWindow || DEFAULT_HISTORY_WINDOW,
  );
  const [jobLimit, setLimit] = useState(
    String(initial?.jobLimit || DEFAULT_JOB_LIMIT),
  );
  const [defaultHost, setHost] = useState(initial?.defaultHost || "");
  const [allowSelfSigned, setSelfSigned] = useState(
    initial?.allowSelfSigned || false,
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setSaving] = useState(false);

  const saving = useRef(false);
  const credentialOrigin = useRef(
    new URL(initial?.apiUrl || DEFAULT_API_URL).origin,
  );

  function changeUrl(value: string) {
    try {
      const origin = new URL(value).origin;
      if (origin !== credentialOrigin.current) {
        setApiKey("");
        setSelfSigned(false);
      }
      credentialOrigin.current = origin;
    } catch {
      /* Wait for a complete URL. */
    }
    setApiUrl(value);
  }

  async function submit() {
    if (saving.current) return;
    const nextErrors: Record<string, string> = {};
    let normalized = "";
    let limit = DEFAULT_JOB_LIMIT;
    try {
      normalized = normalizeApiUrl(apiUrl);
    } catch (error) {
      nextErrors.apiUrl = (error as Error).message;
    }
    try {
      limit = validateJobLimit(jobLimit);
    } catch (error) {
      nextErrors.jobLimit = (error as Error).message;
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    const candidate = {
      id: initial?.id,
      name: name.trim() || new URL(normalized).host,
      apiUrl: normalized,
      apiKey: apiKey.trim(),
      allowSelfSigned,
      historyWindow,
      jobLimit: limit,
      defaultHost: defaultHost.trim(),
    };
    const needsTest =
      !initial ||
      normalized !== initial.apiUrl ||
      candidate.apiKey !== initial.apiKey ||
      allowSelfSigned !== Boolean(initial.allowSelfSigned);
    saving.current = true;
    setSaving(true);
    const toast = await showToast({
      style: Toast.Style.Animated,
      title: needsTest ? "Testing ssync connection" : "Saving connection",
    });
    try {
      if (needsTest) await new SsyncClient(candidate).testConnection();
      const saved = await saveConnection(candidate);
      toast.style = Toast.Style.Success;
      toast.title = "Connection saved";
      await onConfigured(saved);
    } catch (failure) {
      toast.style = Toast.Style.Failure;
      toast.title = "Connection not saved";
      toast.message =
        failure instanceof Error ? failure.message : String(failure);
    } finally {
      saving.current = false;
      setSaving(false);
    }
  }

  async function useLocalKey() {
    if (!isLoopback(apiUrl)) return;
    const key = readLocalApiKey();
    if (key) {
      setApiKey(key);
      await showToast({
        style: Toast.Style.Success,
        title: "Local ssync API key filled",
      });
    } else
      await showToast({
        style: Toast.Style.Failure,
        title: "No local ssync API key found",
      });
  }
  return (
    <Form
      isLoading={isSaving}
      navigationTitle={initial ? "Edit Connection" : "Add Connection"}
      actions={
        <ActionPanel>
          <Action.SubmitForm
            title={initial ? "Save Changes" : "Connect"}
            icon={Icon.CheckCircle}
            onSubmit={submit}
          />
          {isLoopback(apiUrl) ? (
            <Action
              title="Use Local ssync API Key"
              icon={Icon.Key}
              onAction={useLocalKey}
            />
          ) : null}
        </ActionPanel>
      }
    >
      <Form.TextField
        id="name"
        title="Name"
        placeholder="Local ssync"
        value={name}
        onChange={setName}
      />
      <Form.TextField
        id="apiUrl"
        title="ssync API URL"
        value={apiUrl}
        onChange={changeUrl}
        error={errors.apiUrl}
        placeholder={DEFAULT_API_URL}
      />
      <Form.PasswordField
        id="apiKey"
        title="ssync API Key"
        value={apiKey}
        onChange={setApiKey}
        info="Stored in Raycast's encrypted credential store for this connection."
      />
      {!isLoopback(apiUrl) && apiUrl.startsWith("https:") ? (
        <Form.Checkbox
          id="allowSelfSigned"
          label="Trust a self-signed certificate for this connection"
          value={allowSelfSigned}
          onChange={setSelfSigned}
        />
      ) : null}
      <Form.Separator />
      <Form.Description
        title="Jobs"
        text="Defaults for this connection. Search and view filters stay local to Raycast."
      />
      <Form.TextField
        id="defaultHost"
        title="Default Host"
        placeholder="All hosts"
        value={defaultHost}
        onChange={setHost}
      />
      <Form.Dropdown
        id="historyWindow"
        title="Historical Job Window"
        value={historyWindow}
        onChange={setHistory}
      >
        {HISTORY_WINDOWS.map((value) => (
          <Form.Dropdown.Item
            key={value}
            value={value}
            title={value.slice(0, -1) + (value === "1d" ? " day" : " days")}
          />
        ))}
      </Form.Dropdown>
      <Form.TextField
        id="jobLimit"
        title="Jobs per Host"
        value={jobLimit}
        onChange={setLimit}
        error={errors.jobLimit}
        info="1–1,000 jobs per host."
      />
    </Form>
  );
}
