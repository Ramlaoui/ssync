import type { JobNotificationConfig, UIPreferences } from "../types/settings";

export const DEFAULT_ALLOWED_STATES = {
  PD: false,
  R: true,
  CD: true,
  F: true,
  CA: true,
  TO: true
};

export const DEFAULT_JOB_NOTIFICATION_CONFIG: JobNotificationConfig = {
  mode: "inherit",
  allowedStates: { ...DEFAULT_ALLOWED_STATES },
  soundEnabled: true,
  requireInteractionOnFailure: true
};

export const DEFAULT_PREFERENCES: UIPreferences = {
  theme: "system",
  compactMode: false,
  autoRefresh: false,
  refreshInterval: 30,
  jobsPerPage: 50,
  defaultSince: "14d",
  groupArrayJobs: true,
  showCompletedJobs: true,
  sync: {
    exclude: ["*.log", "*.tmp", "__pycache__/"],
    include: [],
    noGitignore: false,
    abortOnSetupFailure: true
  },
  websocket: {
    autoReconnect: true,
    initialRetryDelay: 1000,
    maxRetryDelay: 30000,
    retryBackoffMultiplier: 1.5,
    timeout: 45000
  },
  notifications: {
    enabled: false,
    nativePushEnabled: false,
    soundEnabled: true,
    notifyNewJobs: false,
    allowedStates: { ...DEFAULT_ALLOWED_STATES },
    quietHoursEnabled: false,
    quietHoursStart: "22:00",
    quietHoursEnd: "07:00"
  }
};
