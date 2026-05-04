import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';

import { PrimaryButton } from '@/src/components/PrimaryButton';
import { Screen } from '@/src/components/Screen';
import { SectionCard } from '@/src/components/SectionCard';
import { SegmentedControl } from '@/src/components/SegmentedControl';
import { StatusBadge } from '@/src/components/StatusBadge';
import { TextField } from '@/src/components/TextField';
import { WatcherCard } from '@/src/components/WatcherCard';
import { useOutputStream } from '@/src/features/live/useOutputStream';
import { useCancelJob, useJobDetail, useJobOutput, useJobScript } from '@/src/features/jobs/hooks';
import {
  useAttachWatcher,
  useDeleteWatcher,
  useJobWatchers,
  usePauseWatcher,
  useResumeWatcher,
  useTriggerWatcher,
} from '@/src/features/watchers/hooks';
import { formatBytes, formatDateTime, formatJobMeta } from '@/src/lib/format';
import { colors } from '@/src/theme/colors';
import { radius, spacing } from '@/src/theme/spacing';

export default function JobDetailScreen() {
  const params = useLocalSearchParams<{ jobId: string; hostname?: string }>();
  const jobId = typeof params.jobId === 'string' ? params.jobId : '';
  const hostname = typeof params.hostname === 'string' ? params.hostname : undefined;
  const [watcherName, setWatcherName] = useState('');
  const [watcherPattern, setWatcherPattern] = useState('');
  const [outputType, setOutputType] = useState<'stdout' | 'stderr'>('stdout');

  const job = useJobDetail(jobId, hostname);
  const script = useJobScript(jobId, hostname);
  const output = useJobOutput(jobId, hostname ?? '', outputType);
  const liveOutput = useOutputStream(jobId, hostname ?? '', outputType);
  const jobWatchers = useJobWatchers(jobId, hostname);
  const cancelJob = useCancelJob();
  const attachWatcher = useAttachWatcher();
  const pauseWatcher = usePauseWatcher();
  const resumeWatcher = useResumeWatcher();
  const triggerWatcher = useTriggerWatcher();
  const deleteWatcher = useDeleteWatcher();

  const jobData = job.data;

  return (
    <Screen
      eyebrow="Job detail"
      title={jobData?.name ?? `Job ${jobId}`}
      subtitle={jobData ? formatJobMeta([jobData.hostname, jobData.partition, jobData.user]) : 'Loading job metadata'}
      headerRight={
        jobData ? (
          <View style={{ alignItems: 'flex-end', gap: 8 }}>
            <StatusBadge label={jobData.state} />
            <PrimaryButton
              label="Cancel"
              tone="danger"
              loading={cancelJob.isPending}
              onPress={() => cancelJob.mutate({ jobId, host: hostname })}
            />
          </View>
        ) : undefined
      }
    >
      <SectionCard title="Overview" subtitle={`Job #${jobId}`} action={job.isFetching ? <ActivityIndicator color={colors.primary} /> : null}>
        {jobData ? (
          <>
            <View style={styles.metrics}>
              <View style={styles.metricCard}>
                <Text style={styles.metricValue}>{jobData.runtime ?? 'n/a'}</Text>
                <Text style={styles.metricLabel}>Runtime</Text>
              </View>
              <View style={styles.metricCard}>
                <Text style={styles.metricValue}>{jobData.nodes ?? 'n/a'}</Text>
                <Text style={styles.metricLabel}>Nodes</Text>
              </View>
              <View style={styles.metricCard}>
                <Text style={styles.metricValue}>{jobData.cpus ?? 'n/a'}</Text>
                <Text style={styles.metricLabel}>CPUs</Text>
              </View>
            </View>
            <Text style={styles.metaLine}>Submitted {formatDateTime(jobData.submit_time)}</Text>
            {jobData.reason ? <Text style={styles.metaLine}>Reason: {jobData.reason}</Text> : null}
            {jobData.stdout_file ? <Text style={styles.metaLine}>stdout: {jobData.stdout_file}</Text> : null}
            {jobData.stderr_file ? <Text style={styles.metaLine}>stderr: {jobData.stderr_file}</Text> : null}
          </>
        ) : null}
      </SectionCard>

      <SectionCard title="Output" subtitle="Stream live output first and keep the last snapshot underneath as a fallback.">
        <SegmentedControl
          value={outputType}
          onChange={(value) => setOutputType(value as 'stdout' | 'stderr')}
          options={[
            { label: 'stdout', value: 'stdout' },
            { label: 'stderr', value: 'stderr' },
          ]}
        />
        <View style={styles.outputCard}>
          {liveOutput.loading && !liveOutput.text ? <ActivityIndicator color={colors.primary} /> : null}
          <ScrollView nestedScrollEnabled style={styles.outputScroll}>
            <Text style={styles.outputText}>
              {liveOutput.text ||
                (outputType === 'stdout' ? output.data?.stdout : output.data?.stderr) ||
                'No output available.'}
            </Text>
          </ScrollView>
          <Text style={styles.outputHint}>
            {liveOutput.error
              ? liveOutput.error
              : `Source: ${liveOutput.source}. Snapshot size ${
                  formatBytes(
                    outputType === 'stdout'
                      ? output.data?.stdout_metadata?.size_bytes
                      : output.data?.stderr_metadata?.size_bytes,
                  )
                }`}
          </Text>
        </View>
      </SectionCard>

      <SectionCard title="Script" subtitle="Read-only in v1 to avoid pretending mobile is a full editor.">
        <ScrollView nestedScrollEnabled style={styles.scriptScroll}>
          <Text style={styles.outputText}>{script.data?.script_content ?? 'No script content available.'}</Text>
        </ScrollView>
      </SectionCard>

      <SectionCard title="Watchers" subtitle={`${jobWatchers.data?.length ?? 0} attached to this job`}>
        <TextField label="Watcher name" value={watcherName} onChangeText={setWatcherName} placeholder="OOM guard" />
        <TextField label="Pattern" value={watcherPattern} onChangeText={setWatcherPattern} placeholder="CUDA out of memory" />
        <PrimaryButton
          label="Attach watcher"
          loading={attachWatcher.isPending}
          disabled={!hostname || !watcherName.trim() || !watcherPattern.trim()}
          onPress={async () => {
            if (!hostname) {
              return;
            }
            await attachWatcher.mutateAsync({
              jobId,
              host: hostname,
              name: watcherName.trim(),
              pattern: watcherPattern.trim(),
            });
            setWatcherName('');
            setWatcherPattern('');
          }}
        />
        <View style={styles.watchersList}>
          {jobWatchers.data?.map((watcher) => (
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
        {jobWatchers.data?.length ? (
          <Text style={styles.deleteAll} onPress={() => jobWatchers.data?.forEach((watcher) => deleteWatcher.mutate(watcher.id))}>
            Delete all attached watchers
          </Text>
        ) : null}
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  metrics: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  metricCard: {
    flex: 1,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceElevated,
    padding: spacing.md,
    gap: 2,
  },
  metricValue: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '800',
  },
  metricLabel: {
    color: colors.textDim,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    fontSize: 12,
  },
  metaLine: {
    color: colors.textMuted,
    lineHeight: 20,
  },
  outputCard: {
    gap: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.chip,
    padding: spacing.md,
  },
  outputScroll: {
    maxHeight: 260,
  },
  outputText: {
    color: colors.text,
    fontFamily: 'SpaceMono',
    fontSize: 12,
    lineHeight: 20,
  },
  outputHint: {
    color: colors.textDim,
    fontSize: 12,
  },
  scriptScroll: {
    maxHeight: 260,
    borderRadius: radius.md,
    backgroundColor: colors.chip,
    padding: spacing.md,
  },
  watchersList: {
    gap: spacing.sm,
  },
  deleteAll: {
    color: colors.danger,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
});
