import { StyleSheet, Text, View } from 'react-native';

import { formatRelativeTimestamp } from '@/src/lib/format';
import { colors } from '@/src/theme/colors';
import { radius, spacing } from '@/src/theme/spacing';

type ConnectionBannerProps = {
  source: 'idle' | 'polling' | 'websocket';
  websocketHealthy: boolean;
  lastSyncAt: string | null;
  error: string | null;
};

export function ConnectionBanner({ source, websocketHealthy, lastSyncAt, error }: ConnectionBannerProps) {
  const label = source === 'websocket' ? 'Live websocket' : source === 'polling' ? 'Polling fallback' : 'Not configured';
  const tone = source === 'websocket' && websocketHealthy ? colors.success : source === 'polling' ? colors.warning : colors.textDim;

  return (
    <View style={[styles.banner, { borderColor: tone }]}>
      <Text style={[styles.title, { color: tone }]}>{label}</Text>
      <Text style={styles.subtitle}>
        {error ? error : `Last sync ${formatRelativeTimestamp(lastSyncAt)}`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    borderRadius: radius.md,
    borderWidth: 1,
    backgroundColor: colors.surfaceElevated,
    padding: spacing.md,
    gap: spacing.xs,
  },
  title: {
    fontSize: 14,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  subtitle: {
    color: colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
  },
});
