import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import type { SsyncApiClient } from "../api/client";
import type { NotificationPreferences } from "../types/api";
import type {
  GlobalNotificationSettings,
  JobNotificationConfig
} from "../types/settings";
import { DEFAULT_ALLOWED_STATES, DEFAULT_JOB_NOTIFICATION_CONFIG } from "../state/defaults";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false
  })
});

export type NativePushRegistrationResult = {
  granted: boolean;
  registered: boolean;
  token?: string;
  message: string;
};

export type BackendNotificationSync = {
  preferences: GlobalNotificationSettings;
  jobNotifications: Record<string, JobNotificationConfig>;
};

export async function ensureNotificationPermission(): Promise<boolean> {
  const existing = await Notifications.getPermissionsAsync();
  if (existing.granted) return true;
  const requested = await Notifications.requestPermissionsAsync();
  return requested.granted;
}

export async function registerNativePushDevice(api: SsyncApiClient): Promise<NativePushRegistrationResult> {
  const granted = await ensureNotificationPermission();
  if (!granted) {
    return {
      granted: false,
      registered: false,
      message: "Notification permission was denied."
    };
  }

  if (!Device.isDevice) {
    return {
      granted: true,
      registered: false,
      message: "Backend push registration requires a physical device."
    };
  }

  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ||
    Constants.easConfig?.projectId ||
    Constants.expoConfig?.extra?.projectId;
  const tokenResponse = await Notifications.getExpoPushTokenAsync(projectId ? { projectId: String(projectId) } : undefined);
  const token = String(tokenResponse.data);

  await api.registerNotificationDevice({
    token,
    platform: Platform.OS === "ios" || Platform.OS === "android" ? Platform.OS : "expo",
    token_type: "expo",
    client_type: "expo",
    payload_format: "expo",
    bundle_id: Constants.expoConfig?.ios?.bundleIdentifier,
    environment: String(Constants.expoConfig?.extra?.notificationEnvironment || "development"),
    device_id: Constants.sessionId || undefined,
    enabled: true
  });

  return {
    granted: true,
    registered: true,
    token,
    message: "This device is registered for backend Expo push notifications."
  };
}

export function backendPreferencesFromLocal(settings: GlobalNotificationSettings): Partial<NotificationPreferences> {
  return {
    enabled: settings.enabled,
    allowed_states: Object.entries(settings.allowedStates)
      .filter(([, enabled]) => enabled)
      .map(([state]) => state)
  };
}

export function mergeBackendPreferences(
  current: GlobalNotificationSettings,
  backend: NotificationPreferences
): GlobalNotificationSettings {
  const allowed = backend.allowed_states;
  return {
    ...current,
    enabled: backend.enabled,
    allowedStates: {
      ...DEFAULT_ALLOWED_STATES,
      ...(allowed === null
        ? {}
        : Object.fromEntries(Object.keys(DEFAULT_ALLOWED_STATES).map((state) => [state, allowed.includes(state)])))
    }
  };
}

export function jobNotificationsFromBackend(backend: NotificationPreferences): Record<string, JobNotificationConfig> {
  const muted: Record<string, JobNotificationConfig> = {};
  for (const key of backend.muted_job_ids || []) {
    muted[key] = { ...DEFAULT_JOB_NOTIFICATION_CONFIG, mode: "muted", allowedStates: { ...DEFAULT_ALLOWED_STATES } };
  }
  return muted;
}

export function backendPreferencesWithJobRule(
  backend: NotificationPreferences,
  key: string,
  config?: JobNotificationConfig
): Partial<NotificationPreferences> {
  const muted = new Set(backend.muted_job_ids || []);
  if (config?.mode === "muted") muted.add(key);
  else muted.delete(key);
  return { muted_job_ids: Array.from(muted) };
}

export async function sendBackendTestNotification(api: SsyncApiClient, token?: string): Promise<number> {
  const response = await api.sendTestNotification({
    title: "ssync notification test",
    body: "Backend job notifications are configured for this device.",
    token,
    token_type: token ? "expo" : undefined
  });
  return response.sent;
}

export function defaultJobNotificationConfig(): JobNotificationConfig {
  return {
    ...DEFAULT_JOB_NOTIFICATION_CONFIG,
    allowedStates: { ...DEFAULT_JOB_NOTIFICATION_CONFIG.allowedStates }
  };
}
