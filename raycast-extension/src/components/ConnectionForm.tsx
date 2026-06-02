import { Action, ActionPanel, Form, Icon, Toast, showToast } from "@raycast/api";
import { useMemo, useState } from "react";
import { SsyncClient } from "../api/client";
import {
  DEFAULT_API_URL,
  DEFAULT_HISTORY_WINDOW,
  DEFAULT_JOB_LIMIT,
  readLocalApiKey,
  saveConnection,
} from "../api/storage";
import type { ConnectionSettings } from "../types/ssync";

type Values = {
  apiUrl: string;
  apiKey: string;
  historyWindow: string;
  jobLimit: string;
};

type Props = {
  initial?: ConnectionSettings;
  onConfigured: (connection: ConnectionSettings) => void;
};

export function ConnectionForm({ initial, onConfigured }: Props) {
  const [isTesting, setIsTesting] = useState(false);
  const detectedKey = useMemo(() => readLocalApiKey(), []);

  async function submit(values: Values) {
    const apiUrl = values.apiUrl.trim().replace(/\/+$/, "");
    const apiKey = values.apiKey.trim();
    const jobLimit = Number(values.jobLimit || DEFAULT_JOB_LIMIT);

    if (!apiUrl) {
      await showToast({ style: Toast.Style.Failure, title: "ssync API URL is required" });
      return;
    }
    if (!Number.isFinite(jobLimit) || jobLimit <= 0) {
      await showToast({ style: Toast.Style.Failure, title: "Job limit must be a positive number" });
      return;
    }

    setIsTesting(true);
    const toast = await showToast({ style: Toast.Style.Animated, title: "Testing ssync connection" });
    try {
      const candidate = {
        apiUrl,
        apiKey,
        historyWindow: values.historyWindow || DEFAULT_HISTORY_WINDOW,
        jobLimit,
      };
      await new SsyncClient(candidate).testConnection();
      const saved = await saveConnection(candidate);
      toast.style = Toast.Style.Success;
      toast.title = "Connected to ssync";
      onConfigured(saved);
    } catch (error) {
      toast.style = Toast.Style.Failure;
      toast.title = "Connection failed";
      toast.message = error instanceof Error ? error.message : String(error);
    } finally {
      setIsTesting(false);
    }
  }

  const defaultKey = initial?.apiKey || detectedKey;

  return (
    <Form
      isLoading={isTesting}
      navigationTitle="Configure ssync Connection"
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Test Connection" icon={Icon.CheckCircle} onSubmit={submit} />
        </ActionPanel>
      }
    >
      <Form.Description text="Enter the ssync API URL and optional API key. The connection is saved only after the test succeeds." />
      <Form.TextField
        id="apiUrl"
        title="ssync API URL"
        defaultValue={initial?.apiUrl || DEFAULT_API_URL}
        placeholder={DEFAULT_API_URL}
      />
      <Form.PasswordField
        id="apiKey"
        title="ssync API Key"
        defaultValue={defaultKey}
        placeholder="Optional if the server allows unauthenticated access"
      />
      <Form.Dropdown id="historyWindow" title="Historical Job Window" defaultValue={initial?.historyWindow || DEFAULT_HISTORY_WINDOW}>
        <Form.Dropdown.Item value="1d" title="1 day" />
        <Form.Dropdown.Item value="3d" title="3 days" />
        <Form.Dropdown.Item value="7d" title="7 days" />
        <Form.Dropdown.Item value="14d" title="14 days" />
      </Form.Dropdown>
      <Form.TextField id="jobLimit" title="Job Limit" defaultValue={String(initial?.jobLimit || DEFAULT_JOB_LIMIT)} />
    </Form>
  );
}
