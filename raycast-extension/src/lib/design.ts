import { Color, Icon } from "@raycast/api";
import tokens from "../design/relay-tokens.json";

const tint = (name: keyof typeof tokens.colors): Color.Dynamic => ({
  ...tokens.colors[name],
  adjustContrast: true,
});
export const relay = {
  accent: tint("Accent"),
  running: tint("Running"),
  success: tint("Success"),
  warning: tint("Warning"),
  danger: tint("Danger"),
  muted: Color.SecondaryText,
};
export const relayIcon = { source: "relay-mark.svg", tintColor: relay.accent };
export const statusIcons = {
  running: Icon.Play,
  pending: Icon.Clock,
  completed: Icon.CheckCircle,
  failed: Icon.XmarkCircle,
};
