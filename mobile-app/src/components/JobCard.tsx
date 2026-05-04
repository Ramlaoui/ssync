import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { JobInfo } from '@/src/api/schemas';
import { formatDateTime, formatJobMeta } from '@/src/lib/format';
import { colors } from '@/src/theme/colors';
import { radius, spacing } from '@/src/theme/spacing';
import { StatusBadge } from '@/src/components/StatusBadge';

export function JobCard({ job, onPress }: { job: JobInfo; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
      <View style={styles.row}>
        <View style={styles.copy}>
          <Text style={styles.name}>{job.name}</Text>
          <Text style={styles.meta}>{formatJobMeta([job.hostname, job.partition, job.user])}</Text>
        </View>
        <StatusBadge label={job.state} />
      </View>
      <View style={styles.footer}>
        <Text style={styles.jobId}>#{job.job_id}</Text>
        <Text style={styles.time}>{formatDateTime(job.submit_time)}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    padding: spacing.md,
    gap: spacing.md,
  },
  pressed: {
    opacity: 0.84,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  copy: {
    flex: 1,
    gap: spacing.xs,
  },
  name: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '800',
  },
  meta: {
    color: colors.textMuted,
    fontSize: 14,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  jobId: {
    color: colors.primary,
    fontFamily: 'SpaceMono',
    fontSize: 13,
  },
  time: {
    color: colors.textDim,
    fontSize: 13,
  },
});
