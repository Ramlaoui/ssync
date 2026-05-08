import type { ThemePreference } from "./api";

export type { ThemePreference } from "./api";

export type NotificationStateKey = "PD" | "R" | "CD" | "F" | "CA" | "TO";

export type JobNotificationMode = "inherit" | "custom" | "muted";

export type WebSocketConfig = {
  autoReconnect: boolean;
  initialRetryDelay: number;
  maxRetryDelay: number;
  retryBackoffMultiplier: number;
  timeout: number;
};

export type SyncPreferences = {
  exclude: string[];
  include: string[];
  noGitignore: boolean;
  abortOnSetupFailure: boolean;
};

export type GlobalNotificationSettings = {
  enabled: boolean;
  nativePushEnabled: boolean;
  soundEnabled: boolean;
  notifyNewJobs: boolean;
  allowedStates: Record<NotificationStateKey, boolean>;
  quietHoursEnabled: boolean;
  quietHoursStart: string;
  quietHoursEnd: string;
};

export type JobNotificationConfig = {
  mode: JobNotificationMode;
  allowedStates: Record<NotificationStateKey, boolean>;
  soundEnabled: boolean;
  requireInteractionOnFailure: boolean;
};

export type UIPreferences = {
  theme: ThemePreference;
  compactMode: boolean;
  autoRefresh: boolean;
  refreshInterval: number;
  jobsPerPage: number;
  defaultSince: string;
  groupArrayJobs: boolean;
  showCompletedJobs: boolean;
  sync: SyncPreferences;
  websocket: WebSocketConfig;
  notifications: GlobalNotificationSettings;
};

export type ApiSettings = {
  baseURL: string;
  apiKey: string;
};

export type ScriptTemplate = {
  id: string;
  name: string;
  description?: string;
  script_content: string;
  parameters: Record<string, unknown>;
  tags?: string[];
  created_at: string;
  last_used?: string;
  use_count: number;
};

export type LaunchDraft = {
  id: string;
  sourceJobId?: string;
  sourceJobName?: string | null;
  scriptContent: string;
  host: string;
  sourceDir?: string | null;
};
