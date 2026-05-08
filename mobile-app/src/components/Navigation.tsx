import React from "react";
import { BlurView } from "expo-blur";
import { BriefcaseBusiness, Eye, Play, Settings } from "lucide-react-native";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";

import type { Palette } from "../theme/colors";

export type RootTab = "jobs" | "launch" | "watchers" | "settings";

const tabs = [
  { key: "jobs" as const, label: "Jobs", icon: BriefcaseBusiness },
  { key: "launch" as const, label: "Launch", icon: Play },
  { key: "watchers" as const, label: "Watchers", icon: Eye },
  { key: "settings" as const, label: "Settings", icon: Settings }
];

export function BottomNav({
  palette,
  activeTab,
  onTabChange
}: {
  palette: Palette;
  activeTab: RootTab;
  onTabChange: (tab: RootTab) => void;
}) {
  const navTint = palette.isDark ? "dark" : "light";
  const navFill = palette.isDark ? "rgba(8, 8, 8, 0.86)" : "rgba(255, 255, 255, 0.68)";

  return (
    <View pointerEvents="box-none" style={styles.host}>
      <View style={[styles.shadow, { shadowColor: palette.shadow }]}>
        <BlurView
          intensity={palette.isDark ? 38 : 76}
          tint={navTint}
          style={[styles.nav, { backgroundColor: navFill, borderColor: palette.isDark ? "rgba(255, 255, 255, 0.12)" : "rgba(255, 255, 255, 0.82)" }]}
        >
          {tabs.map((tab) => {
            const active = activeTab === tab.key;
            const Icon = tab.icon;
            return (
              <Pressable
                key={tab.key}
                accessibilityRole="tab"
                accessibilityState={{ selected: active }}
                onPress={() => onTabChange(tab.key)}
                style={[
                  styles.item,
                  {
                    backgroundColor: active ? (palette.isDark ? "rgba(255, 255, 255, 0.08)" : "rgba(255, 255, 255, 0.9)") : "transparent",
                    borderColor: active ? (palette.isDark ? "rgba(255, 255, 255, 0.14)" : "rgba(255, 255, 255, 0.95)") : "transparent"
                  }
                ]}
              >
                <Icon size={20} color={active ? palette.accent : palette.muted} strokeWidth={2.3} />
                <Text style={[styles.label, { color: active ? palette.text : palette.muted }]} numberOfLines={1}>
                  {tab.label}
                </Text>
              </Pressable>
            );
          })}
        </BlurView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  host: {
    position: "absolute",
    left: 14,
    right: 14,
    bottom: Platform.OS === "ios" ? 0 : 8,
    alignItems: "center"
  },
  shadow: {
    width: "100%",
    borderRadius: 30,
    shadowOpacity: Platform.OS === "ios" ? 0.18 : 0.22,
    shadowRadius: 22,
    shadowOffset: { width: 0, height: 12 },
    elevation: 14
  },
  nav: {
    minHeight: 60,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 30,
    overflow: "hidden",
    paddingHorizontal: 6,
    paddingVertical: 6,
    flexDirection: "row",
    gap: 4
  },
  item: {
    flex: 1,
    minHeight: 48,
    borderRadius: 24,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    minWidth: 0
  },
  label: {
    fontSize: 11,
    lineHeight: 14,
    fontWeight: "600",
    letterSpacing: 0
  }
});
