import { StyleSheet, Text, View } from 'react-native';

import { stateColor } from '@/src/lib/format';
import { colors } from '@/src/theme/colors';
import { radius, spacing } from '@/src/theme/spacing';

export function StatusBadge({ label }: { label: string }) {
  const tint = stateColor(label);

  return (
    <View style={[styles.badge, { borderColor: tint, backgroundColor: `${tint}22` }]}>
      <Text style={[styles.label, { color: tint }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: 'flex-start',
    borderRadius: radius.sm,
    borderWidth: 1,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  label: {
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    color: colors.text,
  },
});
