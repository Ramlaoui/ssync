import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { SsyncApiClient } from "../api/client";
import type { NotificationPreferences } from "../types/api";
import type { ApiSettings, JobNotificationConfig, ScriptTemplate, UIPreferences } from "../types/settings";
import { backendPreferencesWithJobRule, jobNotificationsFromBackend, mergeBackendPreferences } from "../services/notifications";
import { DEFAULT_JOB_NOTIFICATION_CONFIG, DEFAULT_PREFERENCES } from "./defaults";
import {
  loadApiSettings,
  loadJobNotifications,
  loadPreferences,
  loadTemplates,
  saveApiSettings,
  saveJobNotifications,
  savePreferences,
  saveTemplates
} from "./storage";

type AppStateValue = {
  ready: boolean;
  apiSettings: ApiSettings;
  preferences: UIPreferences;
  jobNotifications: Record<string, JobNotificationConfig>;
  templates: ScriptTemplate[];
  authenticated: boolean;
  authError: string | null;
  api: SsyncApiClient;
  setApiSettings: (settings: ApiSettings) => Promise<void>;
  setPreferences: (updater: UIPreferences | ((current: UIPreferences) => UIPreferences)) => Promise<void>;
  setJobNotification: (key: string, config: JobNotificationConfig) => Promise<void>;
  resetJobNotification: (key: string) => Promise<void>;
  addTemplate: (template: ScriptTemplate) => Promise<void>;
  deleteTemplate: (id: string) => Promise<void>;
  markTemplateUsed: (id: string) => Promise<void>;
  testConnection: () => Promise<boolean>;
  setAuthState: (authenticated: boolean, error?: string | null) => void;
  exportSettings: () => string;
  importSettings: (json: string) => Promise<void>;
};

const AppStateContext = createContext<AppStateValue | null>(null);

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [apiSettings, setApiSettingsState] = useState<ApiSettings>({ baseURL: "", apiKey: "" });
  const [preferences, setPreferencesState] = useState<UIPreferences>(DEFAULT_PREFERENCES);
  const [jobNotifications, setJobNotifications] = useState<Record<string, JobNotificationConfig>>({});
  const [templates, setTemplates] = useState<ScriptTemplate[]>([]);
  const [authenticated, setAuthenticated] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const preferencesRef = useRef(preferences);
  const jobNotificationsRef = useRef(jobNotifications);
  const templatesRef = useRef(templates);
  const backendNotificationPreferencesRef = useRef<NotificationPreferences | null>(null);
  const autoConnectAttemptRef = useRef("");

  const api = useMemo(
    () => new SsyncApiClient(() => apiSettings.baseURL, () => apiSettings.apiKey),
    [apiSettings.baseURL, apiSettings.apiKey]
  );

  useEffect(() => {
    let active = true;
    Promise.all([loadApiSettings(), loadPreferences(), loadJobNotifications(), loadTemplates()])
      .then(([apiValue, prefValue, jobNotifValue, templateValue]) => {
        if (!active) return;
        setApiSettingsState(apiValue);
        setPreferencesState(prefValue);
        preferencesRef.current = prefValue;
        setJobNotifications(jobNotifValue);
        jobNotificationsRef.current = jobNotifValue;
        setTemplates(templateValue);
        templatesRef.current = templateValue;
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const setApiSettings = useCallback(async (settings: ApiSettings) => {
    setApiSettingsState(settings);
    setAuthenticated(false);
    setAuthError(null);
    await saveApiSettings(settings);
  }, []);

  const setPreferences = useCallback(async (updater: UIPreferences | ((current: UIPreferences) => UIPreferences)) => {
    const nextValue = typeof updater === "function" ? (updater as (current: UIPreferences) => UIPreferences)(preferencesRef.current) : updater;
    preferencesRef.current = nextValue;
    setPreferencesState(nextValue);
    await savePreferences(nextValue);
  }, []);

  const setJobNotification = useCallback(async (key: string, config: JobNotificationConfig) => {
    const next = { ...jobNotificationsRef.current, [key]: config };
    jobNotificationsRef.current = next;
    setJobNotifications(next);
    await saveJobNotifications(next);
    if (backendNotificationPreferencesRef.current) {
      const updated = await api.patchNotificationPreferences(
        backendPreferencesWithJobRule(backendNotificationPreferencesRef.current, key, config)
      );
      backendNotificationPreferencesRef.current = updated;
      const backendJobs = jobNotificationsFromBackend(updated);
      jobNotificationsRef.current = backendJobs;
      setJobNotifications(backendJobs);
      await saveJobNotifications(backendJobs);
    }
  }, [api]);

  const resetJobNotification = useCallback(async (key: string) => {
    const next = { ...jobNotificationsRef.current };
    delete next[key];
    jobNotificationsRef.current = next;
    setJobNotifications(next);
    await saveJobNotifications(next);
    if (backendNotificationPreferencesRef.current) {
      const updated = await api.patchNotificationPreferences(
        backendPreferencesWithJobRule(backendNotificationPreferencesRef.current, key)
      );
      backendNotificationPreferencesRef.current = updated;
      const backendJobs = jobNotificationsFromBackend(updated);
      jobNotificationsRef.current = backendJobs;
      setJobNotifications(backendJobs);
      await saveJobNotifications(backendJobs);
    }
  }, [api]);

  const addTemplate = useCallback(async (template: ScriptTemplate) => {
    const next = [template, ...templatesRef.current.filter((item) => item.id !== template.id)];
    templatesRef.current = next;
    setTemplates(next);
    await saveTemplates(next);
  }, []);

  const deleteTemplate = useCallback(async (id: string) => {
    const next = templatesRef.current.filter((item) => item.id !== id);
    templatesRef.current = next;
    setTemplates(next);
    await saveTemplates(next);
  }, []);

  const markTemplateUsed = useCallback(async (id: string) => {
    const next = templatesRef.current.map((template) =>
      template.id === id
        ? { ...template, last_used: new Date().toISOString(), use_count: template.use_count + 1 }
        : template
    );
    templatesRef.current = next;
    setTemplates(next);
    await saveTemplates(next);
  }, []);

  const testConnection = useCallback(async () => {
    try {
      await api.testConnection();
      setAuthenticated(true);
      setAuthError(null);
      return true;
    } catch (error) {
      setAuthenticated(false);
      setAuthError((error as Error).message || "Connection failed");
      return false;
    }
  }, [api]);

  useEffect(() => {
    if (!ready) return;
    const baseURL = apiSettings.baseURL.trim();
    const apiKey = apiSettings.apiKey.trim();
    if (!baseURL || !apiKey) return;

    const attemptKey = `${baseURL}::${apiKey}`;
    if (autoConnectAttemptRef.current === attemptKey) return;
    autoConnectAttemptRef.current = attemptKey;

    let active = true;
    api.testConnection()
      .then(() => {
        if (!active) return;
        setAuthenticated(true);
        setAuthError(null);
      })
      .catch((error) => {
        if (!active) return;
        setAuthenticated(false);
        setAuthError((error as Error).message || "Connection failed");
      });

    return () => {
      active = false;
    };
  }, [api, apiSettings.apiKey, apiSettings.baseURL, ready]);

  useEffect(() => {
    if (!ready || !authenticated) return;
    let active = true;
    api.getNotificationPreferences()
      .then(async (backendPreferences) => {
        if (!active) return;
        backendNotificationPreferencesRef.current = backendPreferences;

        const nextPreferences = {
          ...preferencesRef.current,
          notifications: mergeBackendPreferences(preferencesRef.current.notifications, backendPreferences)
        };
        preferencesRef.current = nextPreferences;
        setPreferencesState(nextPreferences);
        await savePreferences(nextPreferences);

        if (!active) return;
        const nextJobNotifications = jobNotificationsFromBackend(backendPreferences);
        jobNotificationsRef.current = nextJobNotifications;
        setJobNotifications(nextJobNotifications);
        await saveJobNotifications(nextJobNotifications);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [api, authenticated, ready]);

  const setAuthState = useCallback((nextAuthenticated: boolean, error: string | null = null) => {
    setAuthenticated(nextAuthenticated);
    setAuthError(error);
  }, []);

  const exportSettings = useCallback(() => {
    return JSON.stringify(
      {
        preferences,
        jobNotifications,
        templates,
        api: { baseURL: apiSettings.baseURL, apiKey: apiSettings.apiKey ? "***" : "" },
        exportedAt: new Date().toISOString()
      },
      null,
      2
    );
  }, [apiSettings.baseURL, apiSettings.apiKey, jobNotifications, preferences, templates]);

  const importSettings = useCallback(async (json: string) => {
    const parsed = JSON.parse(json) as {
      preferences?: Partial<UIPreferences>;
      jobNotifications?: Record<string, JobNotificationConfig>;
      templates?: ScriptTemplate[];
    };
    if (parsed.preferences) {
      const nextPreferences = {
        ...DEFAULT_PREFERENCES,
        ...parsed.preferences,
        sync: { ...DEFAULT_PREFERENCES.sync, ...parsed.preferences.sync },
        websocket: { ...DEFAULT_PREFERENCES.websocket, ...parsed.preferences.websocket },
        notifications: {
          ...DEFAULT_PREFERENCES.notifications,
          ...parsed.preferences.notifications,
          allowedStates: {
            ...DEFAULT_PREFERENCES.notifications.allowedStates,
            ...parsed.preferences.notifications?.allowedStates
          }
        }
      };
      preferencesRef.current = nextPreferences;
      setPreferencesState(nextPreferences);
      await savePreferences(nextPreferences);
    }
    if (parsed.jobNotifications) {
      jobNotificationsRef.current = parsed.jobNotifications;
      setJobNotifications(parsed.jobNotifications);
      await saveJobNotifications(parsed.jobNotifications);
    }
    if (parsed.templates) {
      templatesRef.current = parsed.templates;
      setTemplates(parsed.templates);
      await saveTemplates(parsed.templates);
    }
  }, []);

  const value = useMemo<AppStateValue>(
    () => ({
      ready,
      apiSettings,
      preferences,
      jobNotifications,
      templates,
      authenticated,
      authError,
      api,
      setApiSettings,
      setPreferences,
      setJobNotification,
      resetJobNotification,
      addTemplate,
      deleteTemplate,
      markTemplateUsed,
      testConnection,
      setAuthState,
      exportSettings,
      importSettings
    }),
    [
      addTemplate,
      api,
      apiSettings,
      authError,
      authenticated,
      deleteTemplate,
      exportSettings,
      importSettings,
      jobNotifications,
      markTemplateUsed,
      preferences,
      ready,
      resetJobNotification,
      setApiSettings,
      setAuthState,
      setJobNotification,
      setPreferences,
      templates,
      testConnection
    ]
  );

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState(): AppStateValue {
  const value = useContext(AppStateContext);
  if (!value) {
    throw new Error("useAppState must be used inside AppStateProvider");
  }
  return value;
}

export function jobNotificationOrDefault(config?: JobNotificationConfig): JobNotificationConfig {
  return config ? { ...DEFAULT_JOB_NOTIFICATION_CONFIG, ...config } : DEFAULT_JOB_NOTIFICATION_CONFIG;
}
