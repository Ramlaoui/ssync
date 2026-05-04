import { useDeferredValue } from 'react';
import { ActivityIndicator, FlatList, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';

import { Screen } from '@/src/components/Screen';
import { ConnectionBanner } from '@/src/components/ConnectionBanner';
import { EmptyState } from '@/src/components/EmptyState';
import { JobCard } from '@/src/components/JobCard';
import { PrimaryButton } from '@/src/components/PrimaryButton';
import { SectionCard } from '@/src/components/SectionCard';
import { TextField } from '@/src/components/TextField';
import { useFlattenedJobs } from '@/src/features/jobs/hooks';
import { useJobFiltersStore } from '@/src/features/jobs/job-preferences-store';
import { useJobsRealtime } from '@/src/features/live/useJobsRealtime';
import { useSessionStore } from '@/src/features/session/session-store';
import { colors } from '@/src/theme/colors';
import { spacing } from '@/src/theme/spacing';

export default function JobsScreen() {
  const search = useJobFiltersStore((state) => state.search);
  const host = useJobFiltersStore((state) => state.host);
  const state = useJobFiltersStore((value) => value.state);
  const user = useJobFiltersStore((value) => value.user);
  const setSearch = useJobFiltersStore((value) => value.setSearch);
  const baseUrl = useSessionStore((value) => value.baseUrl);
  const connection = useSessionStore((value) => ({
    source: value.connectionSource,
    websocketHealthy: value.websocketHealthy,
    lastSyncAt: value.lastSyncAt,
    lastError: value.lastError,
  }));

  const deferredSearch = useDeferredValue(search);
  const query = useFlattenedJobs({
    host,
    user,
    state,
    limit: 200,
  });

  useJobsRealtime(Boolean(baseUrl));

  const items = query.items.filter((job) => {
    const haystack = `${job.name} ${job.job_id} ${job.hostname} ${job.user ?? ''}`.toLowerCase();
    return haystack.includes(deferredSearch.trim().toLowerCase());
  });

  return (
    <Screen
      eyebrow="Ops Deck"
      title="Live Slurm jobs"
      subtitle="Track jobs across clusters, keep launch feedback visible, and fall back to polling cleanly when realtime drops."
      headerRight={
        <PrimaryButton
          label="Reload"
          tone="ghost"
          onPress={() => {
            query.refetch();
          }}
        />
      }
    >
      <ConnectionBanner
        source={connection.source}
        websocketHealthy={connection.websocketHealthy}
        lastSyncAt={connection.lastSyncAt}
        error={connection.lastError}
      />

      {!baseUrl ? (
        <EmptyState
          title="Connect the app first"
          body="Add the ssync server URL and API key in Settings before loading jobs."
        />
      ) : null}

      <SectionCard title="Filter" subtitle="Keep the query cheap, then use local search for quick narrowing.">
        <TextField label="Search" value={search} onChangeText={setSearch} placeholder="job id, name, host" />
      </SectionCard>

      <SectionCard title="Jobs" subtitle={`${items.length} visible items`} action={query.isFetching ? <ActivityIndicator color={colors.primary} /> : null}>
        {query.isLoading ? (
          <ActivityIndicator color={colors.primary} />
        ) : items.length === 0 ? (
          <EmptyState
            title="No matching jobs"
            body="Try broadening the search or verify that the server is reachable."
          />
        ) : (
          <View style={styles.listContainer}>
            <FlatList
              data={items}
              keyExtractor={(item) => `${item.hostname}:${item.job_id}`}
              renderItem={({ item }) => (
                <JobCard
                  job={item}
                  onPress={() =>
                    router.push({
                      pathname: '/job/[jobId]',
                      params: { jobId: item.job_id, hostname: item.hostname },
                    })
                  }
                />
              )}
              ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
            />
          </View>
        )}
      </SectionCard>

      {query.error ? <Text style={styles.error}>{`${query.error}`}</Text> : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  listContainer: {
    minHeight: 440,
  },
  error: {
    color: colors.danger,
  },
});
