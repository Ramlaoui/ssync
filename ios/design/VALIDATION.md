# Design asset validation

Status: PASS

This validates source assets and document structure, not an iOS application build or live integration.

- Main specification: 18,856 words; 2,133 lines.
- SVG: 44; PNG: 27; GIF: 3; PDF: 3; JSON: 24.
- Screen concepts: 16.
- Semantic adaptive colors: 17.
- SF Symbol roles: 42; runtime availability still requires the shipping iOS SDK.
- App-icon PNGs checked for 1024 × 1024 size and opacity.
- SVG/XML, JSON, catalog references, local Markdown links and anchors checked.
- Motion demonstrations have static reduced-motion groups; behavior needs browser/device review.

## Solid-color text contrast

| Appearance | Foreground | Background | Ratio |
| --- | --- | --- | --- |
| light | Ink | Canvas | 14.44:1 |
| light | Ink | Surface | 15.90:1 |
| light | Ink | SurfaceSecondary | 13.70:1 |
| light | InkSecondary | Canvas | 5.29:1 |
| light | InkSecondary | Surface | 5.83:1 |
| light | InkSecondary | SurfaceSecondary | 5.02:1 |
| light | InkSecondary | CodeCanvas | 5.15:1 |
| light | Accent | Surface | 6.07:1 |
| light | Accent | Canvas | 5.51:1 |
| light | Accent | AccentSoft | 5.29:1 |
| light | Accent | SurfaceSecondary | 5.22:1 |
| light | OnAccent | Accent | 6.12:1 |
| light | Success | Surface | 5.91:1 |
| light | Success | SuccessSoft | 5.25:1 |
| light | Warning | Surface | 6.34:1 |
| light | Warning | WarningSoft | 5.77:1 |
| light | Danger | Surface | 5.87:1 |
| light | Danger | DangerSoft | 5.14:1 |
| dark | Ink | Canvas | 16.88:1 |
| dark | Ink | Surface | 14.95:1 |
| dark | Ink | SurfaceSecondary | 12.67:1 |
| dark | InkSecondary | Canvas | 9.01:1 |
| dark | InkSecondary | Surface | 7.98:1 |
| dark | InkSecondary | SurfaceSecondary | 6.76:1 |
| dark | InkSecondary | CodeCanvas | 8.69:1 |
| dark | Accent | Surface | 7.63:1 |
| dark | Accent | Canvas | 8.61:1 |
| dark | Accent | AccentSoft | 5.75:1 |
| dark | Accent | SurfaceSecondary | 6.46:1 |
| dark | OnAccent | Accent | 7.70:1 |
| dark | Success | Surface | 10.02:1 |
| dark | Success | SuccessSoft | 7.64:1 |
| dark | Warning | Surface | 10.59:1 |
| dark | Warning | WarningSoft | 8.29:1 |
| dark | Danger | Surface | 8.31:1 |
| dark | Danger | DangerSoft | 6.81:1 |

All listed pairs target at least 4.5:1. Separators are decorative and excluded. System materials, wallpaper, native fonts, actual controls, and extensions require on-device testing.
