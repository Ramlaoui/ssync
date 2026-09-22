# Asset manifest

All ssync artwork in this directory is original editable vector work generated for this project. Native SF Symbols are referenced by name and are not redistributed as an icon pack. Screen text uses system/fallback fonts; the brand wordmark is outlined geometry.

## Brand

Nine SVG files in [assets/brand](../assets/brand): Relay mark, wordmark, and horizontal lockup, each in cobalt, ink, and white. Transparent backgrounds. Preserve proportions and clear space.

## App icon

[assets/app-icon](../assets/app-icon) contains default, dark, and tinted SVG masters and opaque 1024 × 1024 PNGs. The platform applies its own outer mask.

The [layer directory](../assets/app-icon/layers) provides background and transparent foreground SVGs for Icon Composer. These are source layers; a layered .icon document has not been created.

## Xcode assets

[Resources/Assets.xcassets](../Resources/Assets.xcassets) contains:

- AppIcon with three 1024 px appearance variants.
- Seventeen semantic color sets with light and dark values.
- Three custom glyph image sets using vector PDF, preserve-vector-representation, and template rendering.

These are prepared assets. Compile them with the actual app target before production use.

## Icons

[Symbol inventory](symbols.json) maps native icon names to roles, selected variants, and accessible labels.

Three custom 24 × 24 glyphs: [job array](../assets/icons/job-array.svg), [watcher rule](../assets/icons/watcher-rule.svg), and [launch recipe](../assets/icons/launch-recipe.svg). They are intended for explanatory/domain content, while standard controls use SF Symbols.

The self-contained screen concepts use schematic glyphs; they do not replace the runtime symbol inventory.

## Illustrations

[assets/illustrations](../assets/illustrations): empty jobs, empty watchers, and API-server connection. Each is a 240 × 200 SVG. Use in explanatory/empty states with nearby accessible text.

## Screens

Each screen has an editable SVG and a rendered PNG in [design/screens](screens).

| File stem | Scenario |
| --- | --- |
| 01-jobs-light | Jobs, warm light appearance, four-tab navigation |
| 01-jobs-dark | Jobs, dark appearance |
| 02-job-detail | Focused running job and time-limit usage |
| 03-output-dark | Revised output workspace, local markers, paused following |
| 04-launch-library | Drafts, templates, and manual relaunch |
| 05-launch-review | Submission review |
| 06-watchers | Watcher list and rule summaries |
| 07-watcher-detail | Custom connected rule diagram and events |
| 08-connect | Connection onboarding |
| 09-job-array | Array summary and task results |
| 10-settings | Settings sheet composition |
| 11-partial-offline | One unavailable host and one current host |
| 12-hosts | Cross-host partition capacity and user job scope |
| 13-host-detail | Host partitions and availability |
| 14-partition-detail | Allocation and jobs within a partition |
| 15-output-search | Search results scoped to loaded output |

All are 390 × 844 composition studies with illustrative data. They are not device screenshots. Labels, hit targets, native material behavior, Dynamic Type, scroll areas, and tab geometry must be resolved using actual SwiftUI and device validation.

## Boards

[design/boards](boards) contains SVG and PNG versions of:

1. Brand.
2. ssync-specific components.
3. System surfaces.
4. Selected screens.
5. Motion choreography.

## Motion

[assets/motion](../assets/motion) contains three 640 × 320 animated SVGs and GIF previews:

- Job state arrival.
- Watcher event.
- Launch handoff.

SVGs include a static presentation selected by prefers-reduced-motion. GIFs loop for review and cannot adapt to that preference; use the SVG or static storyboard for an accessible review.

The diagrams demonstrate visual timing. They do not simulate network availability or execute actions.

## Tokens, generation, and validation

- [tokens.json](tokens.json): semantic colors, type roles, spacing, shape, and timing.
- [Asset generator](../scripts/generate_design_assets.py): deterministic vector geometry, screens, catalog, and preview rendering.
- [Validator](../scripts/validate_design_assets.py): parsing, references, image dimensions/opacity, color consistency, links, and contrast.
- [Validation report](VALIDATION.md): generated results and boundaries.
- [Full specification](../DESIGN_SPEC.md): behavior and implementation requirements.

No credentials, real user output, or external image dependencies are embedded in these assets.
