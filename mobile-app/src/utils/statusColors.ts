import type { Palette } from "../theme/colors";
import type { JobState } from "../types/api";

export type JobStatusColors = {
  background: string;
  border: string;
  text: string;
};

export function jobStatusColors(palette: Palette, state: JobState | null | undefined): JobStatusColors {
  const current = String(state || "").toUpperCase();
  const dark = palette.isDark;

  switch (current) {
    case "R":
      return {
        background: dark ? "rgba(16, 185, 129, 0.15)" : "#D1FAE5",
        border: dark ? "rgba(16, 185, 129, 0.3)" : "#10B981",
        text: dark ? "#6EE7B7" : "#065F46"
      };
    case "CG":
      return {
        background: dark ? "rgba(6, 182, 212, 0.15)" : "#CFFAFE",
        border: dark ? "rgba(6, 182, 212, 0.3)" : "#06B6D4",
        text: dark ? "#67E8F9" : "#155E75"
      };
    case "PD":
      return {
        background: dark ? "rgba(245, 158, 11, 0.15)" : "#FEF3C7",
        border: dark ? "rgba(245, 158, 11, 0.3)" : "#F59E0B",
        text: dark ? "#FBBF24" : "#78350F"
      };
    case "CD":
      return {
        background: dark ? "rgba(59, 130, 246, 0.15)" : "#DBEAFE",
        border: dark ? "rgba(59, 130, 246, 0.3)" : "#3B82F6",
        text: dark ? "#93C5FD" : "#1E3A8A"
      };
    case "F":
      return {
        background: dark ? "rgba(239, 68, 68, 0.15)" : "#FEE2E2",
        border: dark ? "rgba(239, 68, 68, 0.3)" : "#EF4444",
        text: dark ? "#FCA5A5" : "#7F1D1D"
      };
    case "NF":
      return {
        background: dark ? "rgba(220, 38, 38, 0.15)" : "#FEE2E2",
        border: dark ? "rgba(220, 38, 38, 0.3)" : "#DC2626",
        text: dark ? "#FCA5A5" : "#7F1D1D"
      };
    case "BF":
      return {
        background: dark ? "rgba(185, 28, 28, 0.15)" : "#FEE2E2",
        border: dark ? "rgba(185, 28, 28, 0.3)" : "#B91C1C",
        text: dark ? "#FCA5A5" : "#7F1D1D"
      };
    case "OOM":
      return {
        background: dark ? "rgba(190, 18, 60, 0.15)" : "#FFE4E6",
        border: dark ? "rgba(190, 18, 60, 0.3)" : "#BE123C",
        text: dark ? "#FDA4AF" : "#881337"
      };
    case "CA":
      return {
        background: dark ? "rgba(156, 163, 175, 0.15)" : "#F3F4F6",
        border: dark ? "rgba(156, 163, 175, 0.3)" : "#6B7280",
        text: dark ? "#D1D5DB" : "#1F2937"
      };
    case "TO":
      return {
        background: dark ? "rgba(249, 115, 22, 0.15)" : "#FED7AA",
        border: dark ? "rgba(249, 115, 22, 0.3)" : "#F97316",
        text: dark ? "#FDBA74" : "#7C2D12"
      };
    case "DL":
      return {
        background: dark ? "rgba(234, 88, 12, 0.15)" : "#FED7AA",
        border: dark ? "rgba(234, 88, 12, 0.3)" : "#EA580C",
        text: dark ? "#FDBA74" : "#7C2D12"
      };
    case "S":
      return {
        background: dark ? "rgba(139, 92, 246, 0.15)" : "#EDE9FE",
        border: dark ? "rgba(139, 92, 246, 0.3)" : "#8B5CF6",
        text: dark ? "#C4B5FD" : "#5B21B6"
      };
    case "PR":
      return {
        background: dark ? "rgba(168, 85, 247, 0.15)" : "#F3E8FF",
        border: dark ? "rgba(168, 85, 247, 0.3)" : "#A855F7",
        text: dark ? "#D8B4FE" : "#6B21A8"
      };
    default:
      return {
        background: palette.surfaceAlt,
        border: palette.border,
        text: palette.muted
      };
  }
}
