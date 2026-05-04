import { PropsWithChildren, ReactNode } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors, gradients } from '@/src/theme/colors';
import { radius, spacing } from '@/src/theme/spacing';

type ScreenProps = PropsWithChildren<{
  eyebrow: string;
  title: string;
  subtitle: string;
  headerRight?: ReactNode;
  scrollable?: boolean;
}>;

export function Screen({ eyebrow, title, subtitle, headerRight, scrollable = true, children }: ScreenProps) {
  const content = (
    <View style={styles.body}>
      <LinearGradient colors={gradients.hero} style={styles.hero}>
        <View style={styles.heroCopy}>
          <Text style={styles.eyebrow}>{eyebrow}</Text>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>
        </View>
        {headerRight ? <View style={styles.headerRight}>{headerRight}</View> : null}
      </LinearGradient>
      <View style={styles.content}>{children}</View>
    </View>
  );

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      {scrollable ? <ScrollView style={styles.scrollView}>{content}</ScrollView> : content}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollView: {
    flex: 1,
  },
  body: {
    paddingBottom: spacing.xxl,
  },
  hero: {
    marginHorizontal: spacing.md,
    marginTop: spacing.sm,
    borderRadius: radius.xl,
    padding: spacing.lg,
    gap: spacing.md,
  },
  heroCopy: {
    gap: spacing.xs,
  },
  eyebrow: {
    color: colors.primary,
    textTransform: 'uppercase',
    letterSpacing: 1.6,
    fontSize: 12,
    fontWeight: '700',
  },
  title: {
    color: colors.text,
    fontSize: 30,
    lineHeight: 34,
    fontWeight: '800',
  },
  subtitle: {
    color: '#d7edf4',
    fontSize: 15,
    lineHeight: 22,
  },
  headerRight: {
    alignSelf: 'flex-start',
  },
  content: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.lg,
    gap: spacing.md,
  },
});
