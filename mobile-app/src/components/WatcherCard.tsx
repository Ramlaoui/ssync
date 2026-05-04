import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Watcher } from '@/src/api/schemas';
import { colors } from '@/src/theme/colors';
import { radius, spacing } from '@/src/theme/spacing';
import { StatusBadge } from '@/src/components/StatusBadge';

export function WatcherCard({
  watcher,
  onPrimaryAction,
  primaryLabel,
  onSecondaryAction,
  secondaryLabel,
}: {
  watcher: Watcher;
  onPrimaryAction?: () => void;
  primaryLabel?: string;
  onSecondaryAction?: () => void;
  secondaryLabel?: string;
}) {
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.copy}>
          <Text style={styles.name}>{watcher.name}</Text>
          <Text style={styles.pattern}>{watcher.pattern}</Text>
        </View>
        <StatusBadge label={watcher.state} />
      </View>
      <View style={styles.metaRow}>
        <Text style={styles.meta}>#{watcher.id}</Text>
        <Text style={styles.meta}>{watcher.hostname}</Text>
        <Text style={styles.meta}>{watcher.trigger_count} hits</Text>
      </View>
      <View style={styles.actions}>
        {primaryLabel && onPrimaryAction ? (
          <Pressable onPress={onPrimaryAction} style={styles.action}>
            <Text style={styles.actionLabel}>{primaryLabel}</Text>
          </Pressable>
        ) : null}
        {secondaryLabel && onSecondaryAction ? (
          <Pressable onPress={onSecondaryAction} style={styles.action}>
            <Text style={styles.actionLabel}>{secondaryLabel}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    padding: spacing.md,
    gap: spacing.sm,
  },
  header: {
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
    fontSize: 16,
    fontWeight: '800',
  },
  pattern: {
    color: colors.textMuted,
    fontFamily: 'SpaceMono',
    fontSize: 12,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  meta: {
    color: colors.textDim,
    fontSize: 12,
  },
  actions: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  action: {
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceElevated,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  actionLabel: {
    color: colors.primary,
    fontWeight: '700',
  },
});
