import type { ColorSchemeName } from "react-native";

export type Palette = ReturnType<typeof paletteFor>;

export function paletteFor(scheme: ColorSchemeName) {
  const dark = scheme === "dark";

  return {
    isDark: dark,
    background: dark ? "#050505" : "#F7F8FA",
    surface: dark ? "#0C0C0C" : "#FFFFFF",
    surfaceAlt: dark ? "#171717" : "#EEF2F7",
    border: dark ? "#292929" : "#D9DEE7",
    text: dark ? "#F5F5F4" : "#151922",
    muted: dark ? "#A3A3A3" : "#667085",
    subtle: dark ? "#737373" : "#8B95A5",
    accent: dark ? "#2DD4BF" : "#2F6FED",
    accentSoft: dark ? "rgba(45, 212, 191, 0.14)" : "#DDE9FF",
    success: "#10B981",
    successSoft: dark ? "rgba(16, 185, 129, 0.15)" : "#D1FAE5",
    warning: "#F59E0B",
    warningSoft: dark ? "rgba(245, 158, 11, 0.15)" : "#FEF3C7",
    danger: "#EF4444",
    dangerSoft: dark ? "rgba(239, 68, 68, 0.15)" : "#FEE2E2",
    info: "#3B82F6",
    infoSoft: dark ? "rgba(59, 130, 246, 0.15)" : "#DBEAFE",
    shadow: dark ? "#000000" : "#1D2733"
  };
}
