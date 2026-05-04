import { useMemo, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Screen } from '@/src/components/Screen';
import { EmptyState } from '@/src/components/EmptyState';
import { PrimaryButton } from '@/src/components/PrimaryButton';
import { SectionCard } from '@/src/components/SectionCard';
import { TextField } from '@/src/components/TextField';
import { useLaunchJob, useLaunchStatus } from '@/src/features/launch/hooks';
import { useLaunchEventStream } from '@/src/features/live/useLaunchEventStream';
import { useLaunchDraftStore } from '@/src/features/launch/launch-draft-store';
import { useSessionStore } from '@/src/features/session/session-store';
import { colors } from '@/src/theme/colors';
import { radius, spacing } from '@/src/theme/spacing';

function parseOptionalInt(value: string) {
  const trimmed = value.trim();
  return trimmed ? Number.parseInt(trimmed, 10) : undefined;
}

export default function LaunchScreen() {
  const baseUrl = useSessionStore((state) => state.baseUrl);
  const host = useLaunchDraftStore((state) => state.host);
  const sourceDir = useLaunchDraftStore((state) => state.sourceDir);
  const scriptContent = useLaunchDraftStore((state) => state.scriptContent);
  const jobName = useLaunchDraftStore((state) => state.jobName);
  const partition = useLaunchDraftStore((state) => state.partition);
  const cpus = useLaunchDraftStore((state) => state.cpus);
  const mem = useLaunchDraftStore((state) => state.mem);
  const time = useLaunchDraftStore((state) => state.time);
  const setField = useLaunchDraftStore((state) => state.setField);
  const resetDraft = useLaunchDraftStore((state) => state.reset);
  const [lastLaunchId, setLastLaunchId] = useState<string | null>(null);

  const launchJob = useLaunchJob();
  const launchStatus = useLaunchStatus(lastLaunchId);

  useLaunchEventStream(lastLaunchId);

  const launchDisabled = useMemo(
    () => !host.trim() || !scriptContent.trim(),
    [host, scriptContent],
  );

  return (
    <Screen
      eyebrow="Submitter"
      title="Launch from a phone without losing the thread"
      subtitle="V1 keeps launch input lean: host, script, optional source directory, and just enough Slurm fields to stay useful."
    >
      {!baseUrl ? (
        <EmptyState
          title="Server setup required"
          body="Configure the ssync server URL first. Launching from mobile assumes the server can resolve the source directory path."
        />
      ) : null}

      <SectionCard title="Launch request" subtitle="Keep mobile launch focused on the fields that materially change execution.">
        <TextField label="Host" value={host} onChangeText={(value) => setField('host', value)} placeholder="cluster-a" />
        <TextField
          label="Source dir"
          value={sourceDir}
          onChangeText={(value) => setField('sourceDir', value)}
          placeholder="/path/on-the-ssync-host"
          hint="Optional. Leave empty to submit script-only jobs without sync."
        />
        <TextField label="Job name" value={jobName} onChangeText={(value) => setField('jobName', value)} placeholder="train-run" />
        <View style={styles.row}>
          <View style={styles.field}>
            <TextField label="Partition" value={partition} onChangeText={(value) => setField('partition', value)} placeholder="gpu" />
          </View>
          <View style={styles.field}>
            <TextField label="CPUs" value={cpus} onChangeText={(value) => setField('cpus', value)} placeholder="4" keyboardType="numeric" />
          </View>
        </View>
        <View style={styles.row}>
          <View style={styles.field}>
            <TextField label="Memory GB" value={mem} onChangeText={(value) => setField('mem', value)} placeholder="16" keyboardType="numeric" />
          </View>
          <View style={styles.field}>
            <TextField label="Time min" value={time} onChangeText={(value) => setField('time', value)} placeholder="60" keyboardType="numeric" />
          </View>
        </View>
        <TextField
          label="Script"
          value={scriptContent}
          onChangeText={(value) => setField('scriptContent', value)}
          multiline
          autoCapitalize="none"
          autoCorrect={false}
        />
        <View style={styles.row}>
          <View style={styles.field}>
            <PrimaryButton
              label="Launch job"
              loading={launchJob.isPending}
              disabled={launchDisabled}
              onPress={async () => {
                const result = await launchJob.mutateAsync({
                  host: host.trim(),
                  source_dir: sourceDir.trim() || undefined,
                  script_content: scriptContent,
                  job_name: jobName.trim() || undefined,
                  partition: partition.trim() || undefined,
                  cpus: parseOptionalInt(cpus),
                  mem: parseOptionalInt(mem),
                  time: parseOptionalInt(time),
                  exclude: [],
                  include: [],
                  no_gitignore: false,
                });

                setLastLaunchId(result.launch_id ?? null);
              }}
            />
          </View>
          <View style={styles.field}>
            <PrimaryButton label="Reset draft" tone="ghost" onPress={resetDraft} />
          </View>
        </View>
        {launchJob.error ? <Text style={styles.error}>{`${launchJob.error}`}</Text> : null}
      </SectionCard>

      <SectionCard
        title="Launch state"
        subtitle={lastLaunchId ? `Tracking ${lastLaunchId}` : 'No active launch yet.'}
        action={launchStatus.isFetching ? <ActivityIndicator color={colors.primary} /> : null}
      >
        {!lastLaunchId ? (
          <EmptyState
            title="Nothing in flight"
            body="Once a launch starts, stage transitions and logs will appear here."
          />
        ) : (
          <>
            <View style={styles.statusHero}>
              <Text style={styles.statusStage}>{launchStatus.data?.stage ?? 'accepted'}</Text>
              <Text style={styles.statusMessage}>{launchStatus.data?.message ?? 'Waiting for launch events...'}</Text>
            </View>
            <View style={styles.eventList}>
              {(launchStatus.data?.events ?? []).slice(-10).reverse().map((event) => (
                <View key={`${event.sequence}-${event.timestamp}`} style={styles.eventRow}>
                  <Text style={styles.eventType}>{event.type}</Text>
                  <Text style={styles.eventMessage}>{event.message ?? event.stage ?? 'No message'}</Text>
                </View>
              ))}
            </View>
          </>
        )}
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  field: {
    flex: 1,
  },
  statusHero: {
    borderRadius: radius.md,
    backgroundColor: colors.surfaceElevated,
    padding: spacing.md,
    gap: spacing.xs,
  },
  statusStage: {
    color: colors.primary,
    fontSize: 20,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  statusMessage: {
    color: colors.text,
    fontSize: 14,
    lineHeight: 20,
  },
  eventList: {
    gap: spacing.sm,
  },
  eventRow: {
    borderLeftWidth: 2,
    borderLeftColor: colors.border,
    paddingLeft: spacing.md,
    gap: 2,
  },
  eventType: {
    color: colors.textDim,
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  eventMessage: {
    color: colors.text,
    lineHeight: 20,
  },
  error: {
    color: colors.danger,
  },
});
