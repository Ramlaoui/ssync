import AsyncStorage from "@react-native-async-storage/async-storage";

import type { ApiSettings, JobNotificationConfig, ScriptTemplate, UIPreferences } from "../types/settings";
import { DEFAULT_PREFERENCES } from "./defaults";

const KEYS = {
  api: "ssync_mobile_api_settings",
  preferences: "ssync_mobile_preferences",
  jobNotifications: "ssync_mobile_job_notifications",
  templates: "ssync_mobile_script_templates"
};

export async function loadApiSettings(): Promise<ApiSettings> {
  const value = await AsyncStorage.getItem(KEYS.api);
  if (!value) return { baseURL: "", apiKey: "" };
  try {
    return { baseURL: "", apiKey: "", ...JSON.parse(value) };
  } catch {
    return { baseURL: "", apiKey: "" };
  }
}

export async function saveApiSettings(settings: ApiSettings): Promise<void> {
  await AsyncStorage.setItem(KEYS.api, JSON.stringify(settings));
}

export async function loadPreferences(): Promise<UIPreferences> {
  const value = await AsyncStorage.getItem(KEYS.preferences);
  if (!value) return DEFAULT_PREFERENCES;
  try {
    const parsed = JSON.parse(value) as Partial<UIPreferences>;
    return {
      ...DEFAULT_PREFERENCES,
      ...parsed,
      sync: { ...DEFAULT_PREFERENCES.sync, ...parsed.sync },
      websocket: { ...DEFAULT_PREFERENCES.websocket, ...parsed.websocket },
      notifications: {
        ...DEFAULT_PREFERENCES.notifications,
        ...parsed.notifications,
        allowedStates: {
          ...DEFAULT_PREFERENCES.notifications.allowedStates,
          ...parsed.notifications?.allowedStates
        }
      }
    };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export async function savePreferences(preferences: UIPreferences): Promise<void> {
  await AsyncStorage.setItem(KEYS.preferences, JSON.stringify(preferences));
}

export async function loadJobNotifications(): Promise<Record<string, JobNotificationConfig>> {
  const value = await AsyncStorage.getItem(KEYS.jobNotifications);
  if (!value) return {};
  try {
    return JSON.parse(value) as Record<string, JobNotificationConfig>;
  } catch {
    return {};
  }
}

export async function saveJobNotifications(config: Record<string, JobNotificationConfig>): Promise<void> {
  await AsyncStorage.setItem(KEYS.jobNotifications, JSON.stringify(config));
}

export async function loadTemplates(): Promise<ScriptTemplate[]> {
  const value = await AsyncStorage.getItem(KEYS.templates);
  if (!value) return [];
  try {
    return JSON.parse(value) as ScriptTemplate[];
  } catch {
    return [];
  }
}

export async function saveTemplates(templates: ScriptTemplate[]): Promise<void> {
  await AsyncStorage.setItem(KEYS.templates, JSON.stringify(templates));
}
