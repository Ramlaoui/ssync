import React, { useCallback, useEffect, useRef, useState } from "react";
import * as Clipboard from "expo-clipboard";
import PagerView from "react-native-pager-view";
import {
  Bell,
  CircleAlert,
  CircleDashed,
  ClipboardCheck,
  Database,
  Download,
  KeyRound,
  ClipboardPaste,
  RefreshCw,
  Shield,
  Smartphone,
  Upload,
  Wifi,
  WifiOff
} from "lucide-react-native";
import type { LucideIcon } from "lucide-react-native";
import { Alert, Pressable, ScrollView, StyleSheet, View } from "react-native";

import type { SsyncApiClient } from "../api/client";
import { AppText, Button, Card, SectionHeader, SegmentedControl, TextField, ToggleRow } from "../components/ui";
import type { Palette } from "../theme/colors";
import type { ApiSettings, UIPreferences } from "../types/settings";
import { backendPreferencesFromLocal, registerNativePushDevice, sendBackendTestNotification } from "../services/notifications";
import type { NotificationStateKey, ThemePreference } from "../types/settings";
import type { NotificationStatus } from "../types/api";
import { stateLabel } from "../utils/format";

type Section = "api" | "display" | "sync" | "notifications" | "cache" | "websocket" | "data";

const sections: Array<{ value: Section; label: string }> = [
  { value: "api", label: "API" },
  { value: "display", label: "Display" },
  { value: "sync", label: "Sync" },
  { value: "notifications", label: "Alerts" },
  { value: "cache", label: "Cache" },
  { value: "websocket", label: "Socket" },
  { value: "data", label: "Data" }
];

const notificationStates: NotificationStateKey[] = ["PD", "R", "CD", "F", "CA", "TO"];

export function SettingsScreen({
  palette,
  api,
  apiSettings,
  preferences,
  authenticated,
  authError,
  setApiSettings,
  setPreferences,
  testConnection,
  exportSettings,
  importSettings
}: {
  palette: Palette;
  api: SsyncApiClient;
  apiSettings: ApiSettings;
  preferences: UIPreferences;
  authenticated: boolean;
  authError: string | null;
  setApiSettings: (settings: ApiSettings) => Promise<void>;
  setPreferences: (updater: UIPreferences | ((current: UIPreferences) => UIPreferences)) => Promise<void>;
  testConnection: () => Promise<boolean>;
  exportSettings: () => string;
  importSettings: (json: string) => Promise<void>;
}) {
  const [section, setSection] = useState<Section>("api");
  const pagerRef = useRef<PagerView>(null);
  const [baseURL, setBaseURL] = useState(apiSettings.baseURL);
  const [apiKey, setApiKey] = useState(apiSettings.apiKey);
  const [testing, setTesting] = useState(false);
  const [cacheStats, setCacheStats] = useState<{ size: string; entries: number }>({ size: "0 MB", entries: 0 });
  const [cacheLoading, setCacheLoading] = useState(false);
  const [notificationMessage, setNotificationMessage] = useState<string | null>(null);
  const [notificationStatus, setNotificationStatus] = useState<NotificationStatus | null>(null);
  const [registeredExpoToken, setRegisteredExpoToken] = useState<string | undefined>();
  const [registeringPush, setRegisteringPush] = useState(false);
  const [importText, setImportText] = useState("");

  useEffect(() => {
    setBaseURL(apiSettings.baseURL);
    setApiKey(apiSettings.apiKey);
  }, [apiSettings.apiKey, apiSettings.baseURL]);

  async function saveApi() {
    await setApiSettings({ baseURL: baseURL.trim(), apiKey: apiKey.trim() });
  }

  async function pasteApiKey() {
    const text = await Clipboard.getStringAsync();
    if (text) setApiKey(text.trim());
  }

  async function runConnectionTest() {
    setTesting(true);
    try {
      const ok = await testConnection();
      if (!ok) Alert.alert("Connection failed", authError || "The API could not be reached.");
    } finally {
      setTesting(false);
    }
  }

  async function loadCacheStats() {
    setCacheLoading(true);
    try {
      const data = await api.getCacheStats();
      const stats = data.statistics || {};
      const size = `${Number(stats.db_size_mb || 0).toFixed(1)} MB`;
      const entries = Number(stats.total_jobs || 0) + Number((stats.date_range_cache as { active_ranges?: number } | undefined)?.active_ranges || 0);
      setCacheStats({ size, entries });
    } catch {
      // Cache stats are non-critical.
    } finally {
      setCacheLoading(false);
    }
  }

  useEffect(() => {
    if (authenticated && section === "cache") void loadCacheStats();
  }, [authenticated, section]);

  useEffect(() => {
    if (!authenticated || section !== "notifications") return;
    let active = true;
    api.getNotificationStatus()
      .then((status) => {
        if (active) setNotificationStatus(status);
      })
      .catch(() => {
        if (active) setNotificationStatus(null);
      });
    return () => {
      active = false;
    };
  }, [api, authenticated, section]);

  function updatePreferences(patch: Partial<UIPreferences>) {
    void setPreferences((current) => ({ ...current, ...patch }));
  }

  function updateNotificationPreferences(nextNotifications: UIPreferences["notifications"]) {
    void setPreferences((current) => ({ ...current, notifications: nextNotifications }));
    void api.patchNotificationPreferences(backendPreferencesFromLocal(nextNotifications)).catch(() => undefined);
  }

  const apiStatus = getApiStatus({
    authenticated,
    authError,
    apiKey: apiSettings.apiKey,
    baseURL: apiSettings.baseURL,
    testing
  });

  function updateNotificationState(state: NotificationStateKey, enabled: boolean) {
    updateNotificationPreferences({
      ...preferences.notifications,
      allowedStates: { ...preferences.notifications.allowedStates, [state]: enabled }
    });
  }

  const selectSection = useCallback((nextSection: Section) => {
    const nextIndex = sections.findIndex((item) => item.value === nextSection);
    if (nextIndex < 0) return;
    setSection(nextSection);
    pagerRef.current?.setPage(nextIndex);
  }, []);

  async function registerPushForNotifications() {
    setRegisteringPush(true);
    try {
      const result = await registerNativePushDevice(api);
      setNotificationMessage(result.message);
      setRegisteredExpoToken(result.token);
      const nextNotifications = { ...preferences.notifications, enabled: result.granted, nativePushEnabled: result.registered };
      await setPreferences((current) => ({ ...current, notifications: nextNotifications }));
      await api.patchNotificationPreferences(backendPreferencesFromLocal(nextNotifications)).catch(() => undefined);
    } catch (error) {
      setNotificationMessage((error as Error).message || "Failed to register device");
    } finally {
      setRegisteringPush(false);
    }
  }

  async function setNotificationsEnabled(enabled: boolean) {
    if (!enabled) {
      const nextNotifications = { ...preferences.notifications, enabled: false };
      updateNotificationPreferences(nextNotifications);
      setNotificationMessage("Backend job notifications are disabled.");
      return;
    }

    await registerPushForNotifications();
  }

  async function sendBackendTest() {
    try {
      const sent = await sendBackendTestNotification(api, registeredExpoToken);
      setNotificationMessage(sent > 0 ? `Backend sent ${sent} test notification${sent === 1 ? "" : "s"}.` : "Backend accepted the test, but no registered devices were sent to.");
    } catch (error) {
      setNotificationMessage((error as Error).message || "Failed to send backend test notification");
    }
  }

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      <View style={[styles.header, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <View style={{ flex: 1 }}>
          <AppText palette={palette} size={22} weight="900">Settings</AppText>
          <AppText palette={palette} muted size={12}>{apiStatus.summary}</AppText>
        </View>
        <ConnectionPill palette={palette} status={apiStatus} />
      </View>

      <View style={styles.sectionRailWrap}>
        <SettingsSectionRail palette={palette} value={section} onChange={selectSection} />
      </View>

      <PagerView
        ref={pagerRef}
        style={styles.pager}
        initialPage={0}
        onPageSelected={(event) => {
          const nextSection = sections[event.nativeEvent.position];
          if (nextSection) setSection(nextSection.value);
        }}
      >
        <SettingsPage key="api">
          <Card palette={palette}>
            <SectionHeader palette={palette} title="API Authentication" subtitle="Connect the app to your running ssync web API." />
            <ConnectionStatusBanner palette={palette} status={apiStatus} />
            <TextField palette={palette} label="API URL" value={baseURL} onChangeText={setBaseURL} placeholder="http://localhost:8000" keyboardType="url" />
            <View style={styles.apiKeyRow}>
              <TextField palette={palette} label="API key" value={apiKey} onChangeText={setApiKey} secureTextEntry textContentType="none" placeholder="ssync API key" style={{ flex: 1 }} />
              <Button palette={palette} title="Paste" icon={ClipboardPaste} variant="secondary" onPress={pasteApiKey} style={styles.pasteButton} />
            </View>
            <View style={styles.actions}>
              <Button palette={palette} title="Save" icon={KeyRound} onPress={saveApi} />
              <Button palette={palette} title="Test" icon={RefreshCw} variant="secondary" onPress={runConnectionTest} loading={testing} />
            </View>
            <AppText palette={palette} muted size={12}>Generate a key with `ssync auth setup` on the machine running the API.</AppText>
          </Card>
        </SettingsPage>

        <SettingsPage key="display">
          <Card palette={palette}>
            <SectionHeader palette={palette} title="Display Preferences" subtitle="Theme, density, refresh behavior, and job list defaults." />
            <SegmentedControl
              palette={palette}
              value={preferences.theme}
              options={[
                { value: "light", label: "Light" },
                { value: "dark", label: "Dark" },
                { value: "system", label: "System" }
              ]}
              onChange={(theme: ThemePreference) => updatePreferences({ theme })}
            />
            <ToggleRow palette={palette} title="Compact mode" value={preferences.compactMode} onValueChange={(compactMode) => updatePreferences({ compactMode })} />
            <ToggleRow palette={palette} title="Auto refresh" value={preferences.autoRefresh} onValueChange={(autoRefresh) => updatePreferences({ autoRefresh })} />
            <TextField palette={palette} label="Refresh interval seconds" value={String(preferences.refreshInterval)} onChangeText={(value) => updatePreferences({ refreshInterval: Number(value) || 30 })} keyboardType="number-pad" />
            <TextField palette={palette} label="Jobs per page" value={String(preferences.jobsPerPage)} onChangeText={(value) => updatePreferences({ jobsPerPage: Number(value) || 50 })} keyboardType="number-pad" />
            <TextField palette={palette} label="Default history window" value={preferences.defaultSince} onChangeText={(defaultSince) => updatePreferences({ defaultSince })} />
            <ToggleRow palette={palette} title="Group array jobs" value={preferences.groupArrayJobs} onValueChange={(groupArrayJobs) => updatePreferences({ groupArrayJobs })} />
          </Card>
        </SettingsPage>

        <SettingsPage key="sync">
          <Card palette={palette}>
            <SectionHeader palette={palette} title="Sync Settings" subtitle="Defaults used by the native launch form." />
            <TextField palette={palette} label="Exclude patterns" value={preferences.sync.exclude.join("\n")} multiline onChangeText={(text) => void setPreferences((current) => ({ ...current, sync: { ...current.sync, exclude: text.split("\n").map((item) => item.trim()).filter(Boolean) } }))} />
            <TextField palette={palette} label="Include patterns" value={preferences.sync.include.join("\n")} multiline onChangeText={(text) => void setPreferences((current) => ({ ...current, sync: { ...current.sync, include: text.split("\n").map((item) => item.trim()).filter(Boolean) } }))} />
            <ToggleRow palette={palette} title="Ignore .gitignore" value={preferences.sync.noGitignore} onValueChange={(noGitignore) => void setPreferences((current) => ({ ...current, sync: { ...current.sync, noGitignore } }))} />
            <ToggleRow palette={palette} title="Abort on setup failure" value={preferences.sync.abortOnSetupFailure} onValueChange={(abortOnSetupFailure) => void setPreferences((current) => ({ ...current, sync: { ...current.sync, abortOnSetupFailure } }))} />
          </Card>
        </SettingsPage>

        <SettingsPage key="notifications">
          <Card palette={palette}>
            <SectionHeader palette={palette} title="Notifications" subtitle="Global defaults, native registration, and status transitions." />
            <ToggleRow
              palette={palette}
              title="Enable job notifications"
              subtitle={preferences.notifications.nativePushEnabled ? "This device is registered for backend Expo push alerts." : "Requests permission and registers this device for backend alerts."}
              value={preferences.notifications.enabled}
              onValueChange={(enabled) => void setNotificationsEnabled(enabled)}
            />
            {notificationStates.map((state) => (
              <ToggleRow
                key={state}
                palette={palette}
                title={`Notify when ${stateLabel(state)}`}
                value={preferences.notifications.allowedStates[state]}
                onValueChange={(enabled) => updateNotificationState(state, enabled)}
                disabled={!preferences.notifications.enabled}
              />
            ))}
            <View style={styles.actions}>
              <Button palette={palette} title={preferences.notifications.nativePushEnabled ? "Register again" : "Register Expo push"} icon={Smartphone} variant="secondary" onPress={registerPushForNotifications} loading={registeringPush} />
              <Button palette={palette} title="Test backend alert" icon={Bell} variant="secondary" onPress={sendBackendTest} />
            </View>
            {notificationStatus ? (
              <AppText palette={palette} muted size={12}>
                Backend providers: Expo {notificationStatus.providers.expo ? "ready" : "off"}, APNs {notificationStatus.providers.apns ? "ready" : "off"}, Web Push {notificationStatus.providers.webpush ? "ready" : "off"}
              </AppText>
            ) : null}
            {notificationMessage ? <AppText palette={palette} muted>{notificationMessage}</AppText> : null}
          </Card>
        </SettingsPage>

        <SettingsPage key="cache">
          <Card palette={palette}>
            <SectionHeader palette={palette} title="Cache Management" subtitle={`${cacheStats.size}, ${cacheStats.entries} cached items`} />
            <View style={styles.actions}>
              <Button palette={palette} title="Refresh stats" icon={Database} variant="secondary" loading={cacheLoading} onPress={loadCacheStats} />
              <Button
                palette={palette}
                title="Clear cache"
                icon={RefreshCw}
                variant="danger"
                onPress={() => {
                  Alert.alert("Clear cache", "Remove all cached job data on the API server?", [
                    { text: "Cancel", style: "cancel" },
                    { text: "Clear", style: "destructive", onPress: () => void api.clearCache().then(loadCacheStats) }
                  ]);
                }}
              />
            </View>
          </Card>
        </SettingsPage>

        <SettingsPage key="websocket">
          <Card palette={palette}>
            <SectionHeader palette={palette} title="WebSocket Connection" subtitle="Realtime update retry behavior." />
            <ToggleRow palette={palette} title="Auto reconnect" value={preferences.websocket.autoReconnect} onValueChange={(autoReconnect) => void setPreferences((current) => ({ ...current, websocket: { ...current.websocket, autoReconnect } }))} />
            <NumberPreference palette={palette} label="Initial retry delay ms" value={preferences.websocket.initialRetryDelay} onChange={(initialRetryDelay) => void setPreferences((current) => ({ ...current, websocket: { ...current.websocket, initialRetryDelay } }))} />
            <NumberPreference palette={palette} label="Maximum retry delay ms" value={preferences.websocket.maxRetryDelay} onChange={(maxRetryDelay) => void setPreferences((current) => ({ ...current, websocket: { ...current.websocket, maxRetryDelay } }))} />
            <NumberPreference palette={palette} label="Backoff multiplier" value={preferences.websocket.retryBackoffMultiplier} onChange={(retryBackoffMultiplier) => void setPreferences((current) => ({ ...current, websocket: { ...current.websocket, retryBackoffMultiplier } }))} />
            <NumberPreference palette={palette} label="Timeout ms" value={preferences.websocket.timeout} onChange={(timeout) => void setPreferences((current) => ({ ...current, websocket: { ...current.websocket, timeout } }))} />
          </Card>
        </SettingsPage>

        <SettingsPage key="data">
          <Card palette={palette}>
            <SectionHeader palette={palette} title="Data & Privacy" subtitle="Move settings between devices. API keys are masked in exports." />
            <View style={styles.actions}>
              <Button
                palette={palette}
                title="Copy export"
                icon={Download}
                variant="secondary"
                onPress={() => Clipboard.setStringAsync(exportSettings())}
              />
              <Button
                palette={palette}
                title="Paste import"
                icon={ClipboardCheck}
                variant="secondary"
                onPress={async () => setImportText(await Clipboard.getStringAsync())}
              />
            </View>
            <TextField palette={palette} label="Import JSON" value={importText} onChangeText={setImportText} multiline />
            <Button
              palette={palette}
              title="Import settings"
              icon={Upload}
              onPress={async () => {
                try {
                  await importSettings(importText);
                  setImportText("");
                } catch {
                  Alert.alert("Import failed", "The JSON payload could not be imported.");
                }
              }}
              disabled={!importText.trim()}
            />
            <View style={styles.privacyRow}>
              <Shield size={18} color={palette.muted} />
              <AppText palette={palette} muted style={{ flex: 1 }}>Exports include local notification rules and templates. API keys are not exported.</AppText>
            </View>
          </Card>
        </SettingsPage>
      </PagerView>
    </View>
  );
}

function SettingsPage({ children }: { children: React.ReactNode }) {
  return (
    <View style={styles.page}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        {children}
      </ScrollView>
    </View>
  );
}

type ApiStatusTone = "success" | "danger" | "warning" | "info";

type ApiStatus = {
  title: string;
  summary: string;
  detail: string;
  tone: ApiStatusTone;
  icon: LucideIcon;
};

function getApiStatus({
  authenticated,
  authError,
  apiKey,
  baseURL,
  testing
}: {
  authenticated: boolean;
  authError: string | null;
  apiKey: string;
  baseURL: string;
  testing: boolean;
}): ApiStatus {
  const target = baseURL.trim() || "API server";
  if (testing) {
    return {
      title: "Checking",
      summary: "Testing API connection",
      detail: `Trying to reach ${target} with the saved credentials.`,
      tone: "info",
      icon: RefreshCw
    };
  }
  if (authenticated) {
    return {
      title: "Connected",
      summary: "API connected",
      detail: `${target} is reachable and the API key is accepted.`,
      tone: "success",
      icon: Wifi
    };
  }
  if (authError) {
    return {
      title: "Connection failed",
      summary: "API connection failed",
      detail: authError,
      tone: "danger",
      icon: WifiOff
    };
  }
  if (!apiKey.trim()) {
    return {
      title: "Needs API key",
      summary: "API key missing",
      detail: "Enter the API URL and key, then save and test the connection.",
      tone: "warning",
      icon: CircleAlert
    };
  }
  return {
    title: "Not verified",
    summary: "API not tested yet",
    detail: "Credentials are saved locally. Run a test to confirm the server and key are valid.",
    tone: "info",
    icon: CircleDashed
  };
}

function statusTone(palette: Palette, tone: ApiStatusTone) {
  if (tone === "success") return { background: palette.successSoft, border: palette.success, text: palette.success };
  if (tone === "danger") return { background: palette.dangerSoft, border: palette.danger, text: palette.danger };
  if (tone === "warning") return { background: palette.warningSoft, border: palette.warning, text: palette.warning };
  return { background: palette.infoSoft, border: palette.info, text: palette.info };
}

function ConnectionPill({ palette, status }: { palette: Palette; status: ApiStatus }) {
  const colors = statusTone(palette, status.tone);
  const Icon = status.icon;
  return (
    <View style={[styles.statusPill, { backgroundColor: colors.background, borderColor: colors.border }]}>
      <Icon size={15} color={colors.text} strokeWidth={2.4} />
      <AppText palette={palette} size={12} weight="800" style={{ color: colors.text }}>{status.title}</AppText>
    </View>
  );
}

function ConnectionStatusBanner({ palette, status }: { palette: Palette; status: ApiStatus }) {
  const colors = statusTone(palette, status.tone);
  const Icon = status.icon;
  return (
    <View style={[styles.statusBanner, { backgroundColor: colors.background, borderColor: colors.border }]}>
      <View style={[styles.statusIcon, { backgroundColor: palette.surface, borderColor: colors.border }]}>
        <Icon size={21} color={colors.text} strokeWidth={2.4} />
      </View>
      <View style={{ flex: 1 }}>
        <AppText palette={palette} weight="900" style={{ color: colors.text }}>{status.title}</AppText>
        <AppText palette={palette} size={12} style={{ color: colors.text, marginTop: 3 }}>{status.detail}</AppText>
      </View>
    </View>
  );
}

function SettingsSectionRail({
  palette,
  value,
  onChange
}: {
  palette: Palette;
  value: Section;
  onChange: (section: Section) => void;
}) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.sectionRailContent}
      style={[styles.sectionRail, { backgroundColor: palette.surfaceAlt, borderColor: palette.border }]}
    >
      {sections.map((item) => {
        const active = item.value === value;
        return (
          <Pressable
            key={item.value}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            onPress={() => onChange(item.value)}
            style={({ pressed }) => [
              styles.sectionTab,
              {
                backgroundColor: active ? palette.surface : "transparent",
                borderColor: active ? palette.accent : "transparent",
                opacity: pressed ? 0.75 : 1
              }
            ]}
          >
            <AppText palette={palette} size={12} weight="800" style={{ color: active ? palette.accent : palette.muted }}>
              {item.label}
            </AppText>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

function NumberPreference({
  palette,
  label,
  value,
  onChange
}: {
  palette: Palette;
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <TextField
      palette={palette}
      label={label}
      value={String(value)}
      onChangeText={(text) => onChange(Number(text) || value)}
      keyboardType="numeric"
    />
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
    paddingTop: 14,
    paddingBottom: 126,
    gap: 14
  },
  pager: {
    flex: 1
  },
  page: {
    flex: 1
  },
  sectionRailWrap: {
    paddingHorizontal: 14,
    paddingTop: 12
  },
  actions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8
  },
  apiKeyRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 8
  },
  pasteButton: {
    minHeight: 46,
    paddingHorizontal: 10
  },
  sectionRail: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8
  },
  sectionRailContent: {
    minHeight: 42,
    padding: 4,
    gap: 4
  },
  sectionTab: {
    minWidth: 74,
    minHeight: 34,
    borderRadius: 7,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 12,
    alignItems: "center",
    justifyContent: "center"
  },
  statusPill: {
    minHeight: 32,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 999,
    paddingHorizontal: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 6
  },
  statusBanner: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 12,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10
  },
  statusIcon: {
    width: 38,
    height: 38,
    borderRadius: 19,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center"
  },
  privacyRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10
  }
});
