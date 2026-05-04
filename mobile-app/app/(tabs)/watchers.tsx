import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Screen } from '@/src/components/Screen';
import { EmptyState } from '@/src/components/EmptyState';
import { MetricPill } from '@/src/components/MetricPill';
import { SectionCard } from '@/src/components/SectionCard';
import { WatcherCard } from '@/src/components/WatcherCard';
import {
  useDeleteWatcher,
  usePauseWatcher,
  useResumeWatcher,
  useTriggerWatcher,
  useWatcherEvents,
  useWatcherStats,
  useWatchersList,
} from '@/src/features/watchers/hooks';
import { useWatchersRealtime } from '@/src/features/live/useWatchersRealtime';
import { useSessionStore } from '@/src/features/session/session-store';
import { colors } from '@/src/theme/colors';

export default function WatchersScreen() {
  const baseUrl = useSessionStore((state) => state.baseUrl);
  const watchers = useWatchersList();
  const watcherEvents = useWatcherEvents();
  const watcherStats = useWatcherStats();
  const pauseWatcher = usePauseWatcher();
  const resumeWatcher = useResumeWatcher();
  const triggerWatcher = useTriggerWatcher();
  const deleteWatcher = useDeleteWatcher();

  useWatchersRealtime(Boolean(baseUrl));

  return (
    <Screen
      eyebrow="Automation"
      title="Watchers, events, and quick interventions"
      subtitle="Keep automated reactions visible, but make the manual control path obvious when things start drifting."
    >
      <SectionCard title="Stats" subtitle="Live counts from the watcher service" action={watcherStats.isFetching ? <ActivityIndicator color={colors.primary} /> : null}>
        {watcherStats.data ? (
          <View style={styles.metrics}>
            <MetricPill label="Watchers" value={`${watcherStats.data.total_watchers}`} />
            <MetricPill label="Events" value={`${watcherStats.data.total_events}`} />
            <MetricPill label="Last hour" value={`${watcherStats.data.events_last_hour}`} />
          </View>
        ) : (
          <EmptyState title="No watcher metrics yet" body="Once watchers begin tracking output, aggregate numbers appear here." />
        )}
      </SectionCard>

      <SectionCard title="Active watchers" subtitle={`${watchers.data?.length ?? 0} loaded`} action={watchers.isFetching ? <ActivityIndicator color={colors.primary} /> : null}>
        {!watchers.data?.length ? (
          <EmptyState title="No watchers loaded" body="Attach a watcher from a job detail screen or verify the API connection." />
        ) : (
          <View style={styles.cards}>
            {watchers.data.map((watcher) => (
              <WatcherCard
                key={watcher.id}
                watcher={watcher}
                primaryLabel={watcher.state === 'active' ? 'Pause' : 'Resume'}
                onPrimaryAction={() =>
                  watcher.state === 'active'
                    ? pauseWatcher.mutate(watcher.id)
                    : resumeWatcher.mutate(watcher.id)
                }
                secondaryLabel="Trigger"
                onSecondaryAction={() => triggerWatcher.mutate(watcher.id)}
              />
            ))}
          </View>
        )}
      </SectionCard>

      <SectionCard title="Recent events" subtitle="Most recent trigger log across all watchers">
        {!watcherEvents.data?.length ? (
          <EmptyState title="No events yet" body="Event history appears once a watcher matches output or fires an action." />
        ) : (
          <ScrollView nestedScrollEnabled style={styles.eventScroll}>
            {watcherEvents.data.slice(0, 12).map((event) => (
              <View key={event.id} style={styles.eventRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.eventName}>{event.watcher_name}</Text>
                  <Text style={styles.eventMeta}>
                    {event.hostname} • {event.action_type} • {event.success ? 'success' : 'failed'}
                  </Text>
                  {event.action_result ? <Text style={styles.eventResult}>{event.action_result}</Text> : null}
                </View>
                <Text style={styles.delete} onPress={() => deleteWatcher.mutate(event.watcher_id)}>
                  delete
                </Text>
              </View>
            ))}
          </ScrollView>
        )}
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  metrics: {
    flexDirection: 'row',
    gap: 12,
  },
  cards: {
    gap: 12,
  },
  eventScroll: {
    maxHeight: 360,
  },
  eventRow: {
    flexDirection: 'row',
    gap: 12,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  eventName: {
    color: colors.text,
    fontWeight: '700',
  },
  eventMeta: {
    color: colors.textMuted,
    fontSize: 12,
    lineHeight: 18,
  },
  eventResult: {
    color: colors.textDim,
    fontSize: 12,
    lineHeight: 18,
  },
  delete: {
    color: colors.danger,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
});
