import {
  ActivityIndicator,
  Pressable,
  PressableProps,
  StyleProp,
  StyleSheet,
  Text,
  ViewStyle,
} from 'react-native';

import { colors } from '@/src/theme/colors';
import { radius, spacing } from '@/src/theme/spacing';

type PrimaryButtonProps = PressableProps & {
  label: string;
  loading?: boolean;
  tone?: 'primary' | 'danger' | 'ghost';
  buttonStyle?: StyleProp<ViewStyle>;
};

export function PrimaryButton({
  label,
  loading,
  tone = 'primary',
  disabled,
  buttonStyle,
  ...props
}: PrimaryButtonProps) {
  const backgroundColor =
    tone === 'danger' ? colors.danger : tone === 'ghost' ? 'transparent' : colors.primary;
  const textColor = tone === 'ghost' ? colors.text : colors.background;

  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor, opacity: pressed || disabled ? 0.82 : 1, borderWidth: tone === 'ghost' ? 1 : 0 },
        tone === 'ghost' && { borderColor: colors.border },
        buttonStyle,
      ]}
      {...props}
    >
      {loading ? <ActivityIndicator color={textColor} /> : <Text style={[styles.label, { color: textColor }]}>{label}</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 50,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
  },
  label: {
    fontSize: 16,
    fontWeight: '700',
  },
});
