import "react-native-gesture-handler";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator, type NativeStackScreenProps } from "@react-navigation/native-stack";
import { ActivityIndicator, StatusBar, StyleSheet, useColorScheme, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { BottomNav, RootTab } from "./src/components/Navigation";
import { JobNotificationSheet } from "./src/components/JobNotificationSheet";
import { AppText } from "./src/components/ui";
import { useJobs } from "./src/hooks/useJobs";
import { AppStateProvider, useAppState } from "./src/state/AppState";
import { paletteFor } from "./src/theme/colors";
import type { JobInfo } from "./src/types/api";
import type { LaunchDraft } from "./src/types/settings";
import { jobKey } from "./src/utils/format";
import { JobsScreen } from "./src/screens/JobsScreen";
import { JobDetailScreen } from "./src/screens/JobDetailScreen";
import { LaunchScreen } from "./src/screens/LaunchScreen";
import { WatchersScreen } from "./src/screens/WatchersScreen";
import { SettingsScreen } from "./src/screens/SettingsScreen";
import type { Palette } from "./src/theme/colors";

type RootStackParamList = {
  Tabs: undefined;
  Job: { jobId: string; hostname: string; seed?: JobInfo };
};
type AppContextValue = ReturnType<typeof useAppState>;
type JobsStateValue = ReturnType<typeof useJobs>;

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function App() {
  return (
    <SafeAreaProvider>
      <AppStateProvider>
        <SsyncMobileApp />
      </AppStateProvider>
    </SafeAreaProvider>
  );
}

function SsyncMobileApp() {
  const app = useAppState();
  const systemScheme = useColorScheme();
  const effectiveScheme = app.preferences.theme === "system" ? systemScheme : app.preferences.theme;
  const palette = useMemo(() => paletteFor(effectiveScheme), [effectiveScheme]);
  const [tab, setTab] = useState<RootTab>("jobs");
  const [notificationJob, setNotificationJob] = useState<JobInfo | null>(null);
  const [launchDraft, setLaunchDraft] = useState<LaunchDraft | null>(null);
  const [activeRoute, setActiveRoute] = useState<keyof RootStackParamList>("Tabs");
  const safeAreaBackground = activeRoute === "Job" && palette.isDark ? palette.background : palette.surface;

  const jobs = useJobs({
    api: app.api,
    preferences: app.preferences,
    jobNotifications: app.jobNotifications,
    authenticated: app.authenticated
  });

  const handleJobUpdated = useCallback((job: JobInfo) => {
    jobs.setJobsByKey((current) => {
      const next = new Map(current);
      next.set(jobKey(job.job_id, job.hostname), job);
      return next;
    });
  }, [jobs.setJobsByKey]);

  if (!app.ready) {
    return (
      <SafeAreaView style={[styles.safe, { backgroundColor: palette.background }]}>
        <StatusBar barStyle={palette.isDark ? "light-content" : "dark-content"} />
        <View style={styles.loading}>
          <ActivityIndicator color={palette.accent} />
          <AppText palette={palette} muted style={{ marginTop: 10 }}>Loading ssync mobile</AppText>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: safeAreaBackground }]}>
      <StatusBar barStyle={palette.isDark ? "light-content" : "dark-content"} backgroundColor={safeAreaBackground} />
      <NavigationContainer
        onStateChange={(state) => {
          const route = state?.routes[state.index];
          if (route?.name === "Tabs" || route?.name === "Job") setActiveRoute(route.name);
        }}
      >
        <Stack.Navigator
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: palette.background },
            gestureEnabled: true,
            animation: "slide_from_right"
          }}
        >
          <Stack.Screen name="Tabs">
            {(props) => (
              <TabsContent
                {...props}
                palette={palette}
                app={app}
                jobs={jobs}
                tab={tab}
                setTab={setTab}
                launchDraft={launchDraft}
                setLaunchDraft={setLaunchDraft}
                setActiveRoute={setActiveRoute}
                setNotificationJob={setNotificationJob}
              />
            )}
          </Stack.Screen>
          <Stack.Screen name="Job">
            {(props) => (
              <JobRouteContent
                {...props}
                palette={palette}
                app={app}
                jobs={jobs}
                setTab={setTab}
                setLaunchDraft={setLaunchDraft}
                setActiveRoute={setActiveRoute}
                setNotificationJob={setNotificationJob}
                onJobUpdated={handleJobUpdated}
              />
            )}
          </Stack.Screen>
        </Stack.Navigator>
      </NavigationContainer>

      <JobNotificationSheet
        palette={palette}
        visible={Boolean(notificationJob)}
        job={notificationJob}
        config={notificationJob ? app.jobNotifications[jobKey(notificationJob.job_id, notificationJob.hostname)] : undefined}
        onSave={(key, config) => void app.setJobNotification(key, config)}
        onReset={(key) => void app.resetJobNotification(key)}
        onClose={() => setNotificationJob(null)}
      />
    </SafeAreaView>
  );
}

function TabsContent({
  navigation,
  palette,
  app,
  jobs,
  tab,
  setTab,
  launchDraft,
  setLaunchDraft,
  setActiveRoute,
  setNotificationJob
}: NativeStackScreenProps<RootStackParamList, "Tabs"> & {
  palette: Palette;
  app: AppContextValue;
  jobs: JobsStateValue;
  tab: RootTab;
  setTab: (tab: RootTab) => void;
  launchDraft: LaunchDraft | null;
  setLaunchDraft: (draft: LaunchDraft | null) => void;
  setActiveRoute: (route: keyof RootStackParamList) => void;
  setNotificationJob: (job: JobInfo | null) => void;
}) {
  const openJob = (job: JobInfo) => {
    setActiveRoute("Job");
    navigation.navigate("Job", { jobId: job.job_id, hostname: job.hostname, seed: job });
  };
  const openJobById = (jobId: string, hostname: string) => {
    const seed = jobs.jobsByKey.get(jobKey(jobId, hostname));
    setActiveRoute("Job");
    navigation.navigate("Job", { jobId, hostname, seed });
  };

  function renderTab() {
    if (tab === "jobs") {
      return (
        <JobsScreen
          palette={palette}
          api={app.api}
          hosts={jobs.hosts}
          jobs={jobs.jobs}
          arrayGroups={jobs.arrayGroups}
          partitions={jobs.partitions}
          loading={jobs.loadingJobs}
          loadingPartitions={jobs.loadingPartitions}
          wsConnected={jobs.wsConnected}
          lastSyncAt={jobs.lastSyncAt}
          jobNotifications={app.jobNotifications}
          onRefresh={(filters, force) => void jobs.refreshJobs(filters, force)}
          onHostFilterChange={(selectedHost) => {
            void jobs.refreshJobs({ host: selectedHost }, false);
            void jobs.refreshPartitions(selectedHost, false);
          }}
          onOpenJob={openJob}
          onResubmitDraft={(draft) => {
            setLaunchDraft(draft);
            setTab("launch");
          }}
          onConfigureJobNotifications={setNotificationJob}
        />
      );
    }
    if (tab === "launch") {
      return (
        <LaunchScreen
          palette={palette}
          api={app.api}
          hosts={jobs.hosts}
          sync={app.preferences.sync}
          templates={app.templates}
          draft={launchDraft}
          onDraftApplied={() => setLaunchDraft(null)}
          onAddTemplate={(template) => void app.addTemplate(template)}
          onDeleteTemplate={(id) => void app.deleteTemplate(id)}
          onMarkTemplateUsed={(id) => void app.markTemplateUsed(id)}
          onOpenJob={openJobById}
        />
      );
    }
    if (tab === "watchers") {
      return <WatchersScreen palette={palette} api={app.api} jobs={jobs.jobs} />;
    }
    return (
      <SettingsScreen
        palette={palette}
        api={app.api}
        apiSettings={app.apiSettings}
        preferences={app.preferences}
        authenticated={app.authenticated}
        authError={app.authError}
        setApiSettings={app.setApiSettings}
        setPreferences={app.setPreferences}
        testConnection={app.testConnection}
        exportSettings={app.exportSettings}
        importSettings={app.importSettings}
      />
    );
  }

  return (
    <>
      <View style={styles.tabFrame}>{renderTab()}</View>
      <BottomNav palette={palette} activeTab={tab} onTabChange={setTab} />
    </>
  );
}

function JobRouteContent({
  navigation,
  route,
  palette,
  app,
  jobs,
  setTab,
  setLaunchDraft,
  setActiveRoute,
  setNotificationJob,
  onJobUpdated
}: NativeStackScreenProps<RootStackParamList, "Job"> & {
  palette: Palette;
  app: AppContextValue;
  jobs: JobsStateValue;
  setTab: (tab: RootTab) => void;
  setLaunchDraft: (draft: LaunchDraft | null) => void;
  setActiveRoute: (route: keyof RootStackParamList) => void;
  setNotificationJob: (job: JobInfo | null) => void;
  onJobUpdated: (job: JobInfo) => void;
}) {
  useEffect(() => {
    setActiveRoute("Job");
    return navigation.addListener("beforeRemove", () => setActiveRoute("Tabs"));
  }, [navigation, setActiveRoute]);

  const selectedJob =
    jobs.jobsByKey.get(jobKey(route.params.jobId, route.params.hostname)) ||
    route.params.seed ||
    placeholderJob(route.params.jobId, route.params.hostname);

  return (
    <JobDetailScreen
      palette={palette}
      api={app.api}
      seedJob={selectedJob}
      onBack={() => {
        setActiveRoute("Tabs");
        navigation.goBack();
      }}
      onOpenJob={(jobId, hostname) => {
        setActiveRoute("Job");
        navigation.replace("Job", { jobId, hostname });
      }}
      onResubmitDraft={(draft) => {
        setLaunchDraft(draft);
        setTab("launch");
        setActiveRoute("Tabs");
        navigation.goBack();
      }}
      onConfigureNotifications={setNotificationJob}
      onJobUpdated={onJobUpdated}
    />
  );
}

function placeholderJob(jobId: string, hostname: string): JobInfo {
  return {
    job_id: jobId,
    hostname,
    name: `Job ${jobId}`,
    state: "UNKNOWN",
    user: null,
    partition: null,
    nodes: null,
    cpus: null,
    memory: null,
    time_limit: null,
    runtime: null,
    reason: null,
    work_dir: null,
    stdout_file: null,
    stderr_file: null,
    submit_time: null,
    submit_line: null,
    start_time: null,
    end_time: null,
    node_list: null,
    alloc_tres: null,
    req_tres: null,
    cpu_time: null,
    total_cpu: null,
    user_cpu: null,
    system_cpu: null,
    ave_cpu: null,
    ave_cpu_freq: null,
    req_cpu_freq_min: null,
    req_cpu_freq_max: null,
    max_rss: null,
    ave_rss: null,
    max_vmsize: null,
    ave_vmsize: null,
    max_disk_read: null,
    max_disk_write: null,
    ave_disk_read: null,
    ave_disk_write: null,
    consumed_energy: null
  };
}

const styles = StyleSheet.create({
  safe: {
    flex: 1
  },
  tabFrame: {
    flex: 1
  },
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center"
  }
});
