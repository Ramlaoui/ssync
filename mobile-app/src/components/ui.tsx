import React from "react";
import {
  ActivityIndicator,
  GestureResponderEvent,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TextStyle,
  View,
  ViewStyle
} from "react-native";
import { ArrowDownToLine } from "lucide-react-native";
import type { LucideIcon } from "lucide-react-native";

import type { Palette } from "../theme/colors";
import { stateLabel, stateTone } from "../utils/format";
import { jobStatusColors } from "../utils/statusColors";

function displayWeight(weight: TextStyle["fontWeight"]): TextStyle["fontWeight"] {
  if (weight === "900" || weight === "800") return "700";
  if (weight === "700") return "600";
  return weight;
}

export function Card({
  palette,
  children,
  style
}: {
  palette: Palette;
  children: React.ReactNode;
  style?: ViewStyle;
}) {
  return <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }, style]}>{children}</View>;
}

export function AppText({
  palette,
  children,
  muted = false,
  weight = "400",
  size = 14,
  style,
  numberOfLines
}: {
  palette: Palette;
  children: React.ReactNode;
  muted?: boolean;
  weight?: TextStyle["fontWeight"];
  size?: number;
  style?: TextStyle;
  numberOfLines?: number;
}) {
  return (
    <Text
      numberOfLines={numberOfLines}
      style={[
        {
          color: muted ? palette.muted : palette.text,
          fontSize: size,
          lineHeight: Math.round(size * 1.36),
          fontWeight: displayWeight(weight),
          letterSpacing: 0
        },
        style
      ]}
    >
      {children}
    </Text>
  );
}

export function IconButton({
  palette,
  icon: Icon,
  label,
  onPress,
  disabled,
  variant = "secondary",
  size = 40
}: {
  palette: Palette;
  icon: LucideIcon;
  label: string;
  onPress?: (event: GestureResponderEvent) => void;
  disabled?: boolean;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: number;
}) {
  const colors = buttonColors(palette, variant);
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="button"
      onPress={disabled ? undefined : onPress}
      style={({ pressed }) => [
        styles.iconButton,
        {
          width: size,
          height: size,
          borderColor: colors.border,
          backgroundColor: colors.background,
          opacity: disabled ? 0.45 : pressed ? 0.75 : 1
        }
      ]}
    >
      <Icon size={19} color={colors.text} strokeWidth={2.1} />
    </Pressable>
  );
}

export function Button({
  palette,
  title,
  icon: Icon,
  onPress,
  disabled,
  loading,
  variant = "primary",
  style
}: {
  palette: Palette;
  title: string;
  icon?: LucideIcon;
  onPress?: () => void;
  disabled?: boolean;
  loading?: boolean;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  style?: ViewStyle;
}) {
  const colors = buttonColors(palette, variant);
  return (
    <Pressable
      accessibilityRole="button"
      onPress={disabled || loading ? undefined : onPress}
      style={({ pressed }) => [
        styles.button,
        {
          backgroundColor: colors.background,
          borderColor: colors.border,
          opacity: disabled ? 0.45 : pressed ? 0.78 : 1
        },
        style
      ]}
    >
      {loading ? <ActivityIndicator color={colors.text} /> : Icon ? <Icon size={18} color={colors.text} /> : null}
      <Text style={[styles.buttonText, { color: colors.text }]} numberOfLines={1}>
        {title}
      </Text>
    </Pressable>
  );
}

function buttonColors(palette: Palette, variant: "primary" | "secondary" | "danger" | "ghost") {
  if (variant === "primary") {
    return { background: palette.text, border: palette.text, text: palette.background };
  }
  if (variant === "danger") {
    return { background: palette.danger, border: palette.danger, text: "#FFFFFF" };
  }
  if (variant === "ghost") {
    return { background: "transparent", border: "transparent", text: palette.text };
  }
  return { background: palette.surfaceAlt, border: palette.border, text: palette.text };
}

export function TextField({
  palette,
  label,
  value,
  onChangeText,
  placeholder,
  secureTextEntry,
  multiline,
  keyboardType,
  autoCapitalize = "none",
  textContentType,
  style
}: {
  palette: Palette;
  label?: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
  secureTextEntry?: boolean;
  multiline?: boolean;
  keyboardType?: "default" | "number-pad" | "numeric" | "url";
  autoCapitalize?: "none" | "sentences" | "words" | "characters";
  textContentType?: "none" | "password" | "oneTimeCode" | "URL";
  style?: ViewStyle;
}) {
  return (
    <View style={[styles.fieldWrap, style]}>
      {label ? <AppText palette={palette} size={12} weight="700" muted>{label}</AppText> : null}
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={palette.subtle}
        secureTextEntry={secureTextEntry}
        multiline={multiline}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
        autoCorrect={false}
        contextMenuHidden={false}
        selectTextOnFocus={false}
        textContentType={textContentType}
        style={[
          styles.input,
          {
            minHeight: multiline ? 128 : 46,
            color: palette.text,
            backgroundColor: palette.surface,
            borderColor: palette.border,
            textAlignVertical: multiline ? "top" : "center"
          }
        ]}
      />
    </View>
  );
}

export function ToggleRow({
  palette,
  title,
  subtitle,
  value,
  onValueChange,
  disabled
}: {
  palette: Palette;
  title: string;
  subtitle?: string;
  value: boolean;
  onValueChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <View style={[styles.toggleRow, { opacity: disabled ? 0.5 : 1 }]}>
      <View style={{ flex: 1 }}>
        <AppText palette={palette} weight="700">{title}</AppText>
        {subtitle ? <AppText palette={palette} muted size={12} style={{ marginTop: 3 }}>{subtitle}</AppText> : null}
      </View>
      <Switch value={value} onValueChange={onValueChange} disabled={disabled} trackColor={{ false: palette.border, true: palette.accentSoft }} thumbColor={value ? palette.accent : palette.surfaceAlt} />
    </View>
  );
}

export function SegmentedControl<T extends string>({
  palette,
  value,
  options,
  onChange
}: {
  palette: Palette;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  return (
    <View style={[styles.segmented, { backgroundColor: palette.surfaceAlt, borderColor: palette.border }]}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <Pressable
            key={option.value}
            onPress={() => onChange(option.value)}
            style={[
              styles.segment,
              {
                backgroundColor: active ? palette.surface : "transparent",
                borderColor: active ? palette.border : "transparent"
              }
            ]}
          >
            <Text style={{ color: active ? palette.text : palette.muted, fontWeight: "600", fontSize: 12, lineHeight: 16 }}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Chip({
  palette,
  label,
  active,
  onPress,
  tone = "neutral"
}: {
  palette: Palette;
  label: string;
  active?: boolean;
  onPress?: () => void;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
}) {
  const toneColors = tonePalette(palette, tone);
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.chip,
        {
          borderColor: active ? toneColors.text : palette.border,
          backgroundColor: active ? toneColors.background : palette.surface,
          opacity: pressed ? 0.8 : 1
        }
      ]}
    >
      <Text style={{ color: active ? toneColors.text : palette.muted, fontSize: 12, lineHeight: 16, fontWeight: "600" }} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

export function StatusBadge({ palette, state }: { palette: Palette; state: string | undefined | null }) {
  const colors = jobStatusColors(palette, state);
  return (
    <View style={[styles.badge, { backgroundColor: colors.background, borderColor: colors.border }]}>
      <Text style={{ color: colors.text, fontWeight: "700", fontSize: 11, lineHeight: 15 }}>{stateLabel(state)}</Text>
    </View>
  );
}

function tonePalette(palette: Palette, tone: "neutral" | "success" | "warning" | "danger" | "info") {
  if (tone === "success") return { background: palette.successSoft, border: palette.success, text: palette.success };
  if (tone === "warning") return { background: palette.warningSoft, border: palette.warning, text: palette.warning };
  if (tone === "danger") return { background: palette.dangerSoft, border: palette.danger, text: palette.danger };
  if (tone === "info") return { background: palette.infoSoft, border: palette.info, text: palette.info };
  return { background: palette.surfaceAlt, border: palette.border, text: palette.muted };
}

export function SectionHeader({
  palette,
  title,
  subtitle,
  action
}: {
  palette: Palette;
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <View style={styles.sectionHeader}>
      <View style={{ flex: 1 }}>
        <AppText palette={palette} size={18} weight="800">{title}</AppText>
        {subtitle ? <AppText palette={palette} muted size={12} style={{ marginTop: 3 }}>{subtitle}</AppText> : null}
      </View>
      {action}
    </View>
  );
}

export function EmptyState({
  palette,
  title,
  body,
  icon: Icon
}: {
  palette: Palette;
  title: string;
  body?: string;
  icon?: LucideIcon;
}) {
  return (
    <View style={styles.empty}>
      {Icon ? <Icon size={34} color={palette.subtle} /> : null}
      <AppText palette={palette} weight="800" size={16} style={{ marginTop: 10 }}>{title}</AppText>
      {body ? <AppText palette={palette} muted style={{ textAlign: "center", marginTop: 6 }}>{body}</AppText> : null}
    </View>
  );
}

export function Sheet({
  palette,
  visible,
  title,
  onClose,
  children
}: {
  palette: Palette;
  visible: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: palette.background }}>
        <View style={[styles.sheetHeader, { borderColor: palette.border, backgroundColor: palette.surface }]}>
          <AppText palette={palette} size={18} weight="800">{title}</AppText>
          <Button palette={palette} title="Done" variant="secondary" onPress={onClose} />
        </View>
        <ScrollView contentContainerStyle={styles.sheetContent} keyboardShouldPersistTaps="handled">{children}</ScrollView>
      </View>
    </Modal>
  );
}

export function CodeBlock({
  palette,
  content,
  minHeight = 220,
  maxHeight = 560,
  wrapLines = true
}: {
  palette: Palette;
  content: string;
  minHeight?: number;
  maxHeight?: number;
  wrapLines?: boolean;
}) {
  const scrollRef = React.useRef<ScrollView>(null);

  function scrollToBottom() {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollToEnd({ animated: true });
    });
  }

  if (wrapLines) {
    return (
      <View style={[styles.codeBlock, { backgroundColor: palette.surfaceAlt, borderColor: palette.border, minHeight, maxHeight }]}>
        <ScrollView ref={scrollRef} nestedScrollEnabled contentContainerStyle={styles.codeBlockWrapped}>
          <Text selectable style={[styles.codeText, { color: palette.text }]}>{content || ""}</Text>
        </ScrollView>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Scroll to bottom"
          hitSlop={10}
          onPress={scrollToBottom}
          style={({ pressed }) => [
            styles.scrollBottomButton,
            {
              backgroundColor: palette.surface,
              borderColor: palette.border,
              opacity: pressed ? 0.72 : 0.96
            }
          ]}
        >
          <ArrowDownToLine size={17} color={palette.text} strokeWidth={2.3} />
        </Pressable>
      </View>
    );
  }

  return (
    <View style={[styles.codeBlock, { backgroundColor: palette.surfaceAlt, borderColor: palette.border, minHeight, maxHeight }]}>
      <ScrollView ref={scrollRef} nestedScrollEnabled>
        <ScrollView horizontal contentContainerStyle={styles.codeBlockWrapped}>
          <Text selectable style={[styles.codeText, { color: palette.text }]}>{content || ""}</Text>
        </ScrollView>
      </ScrollView>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Scroll to bottom"
        hitSlop={10}
        onPress={scrollToBottom}
        style={({ pressed }) => [
          styles.scrollBottomButton,
          {
            backgroundColor: palette.surface,
            borderColor: palette.border,
            opacity: pressed ? 0.72 : 0.96
          }
        ]}
      >
        <ArrowDownToLine size={17} color={palette.text} strokeWidth={2.3} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 14,
    gap: 10
  },
  iconButton: {
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth
  },
  button: {
    minHeight: 42,
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 14,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 8
  },
  buttonText: {
    fontWeight: "600",
    fontSize: 13,
    lineHeight: 18,
    letterSpacing: 0
  },
  fieldWrap: {
    gap: 7
  },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14
  },
  toggleRow: {
    minHeight: 56,
    flexDirection: "row",
    alignItems: "center",
    gap: 12
  },
  segmented: {
    flexDirection: "row",
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 3,
    gap: 3
  },
  segment: {
    flex: 1,
    minHeight: 34,
    borderRadius: 6,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 8
  },
  chip: {
    minHeight: 34,
    paddingHorizontal: 12,
    borderRadius: 999,
    borderWidth: StyleSheet.hairlineWidth,
    justifyContent: "center"
  },
  badge: {
    alignSelf: "flex-start",
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 4
  },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginBottom: 10
  },
  empty: {
    alignItems: "center",
    justifyContent: "center",
    padding: 28
  },
  sheetHeader: {
    minHeight: 68,
    borderBottomWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 10,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12
  },
  sheetContent: {
    padding: 16,
    gap: 14
  },
  codeBlock: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    overflow: "hidden"
  },
  codeBlockWrapped: {
    padding: 12,
    paddingBottom: 62
  },
  codeText: {
    fontFamily: "Courier",
    fontSize: 12,
    lineHeight: 18,
    flexShrink: 1
  },
  scrollBottomButton: {
    position: "absolute",
    right: 12,
    bottom: 12,
    width: 38,
    height: 38,
    borderRadius: 19,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center"
  }
});
