# ssync web UI v2: audit and product direction

22 September 2026. Pre-redesign audit and proposal. See [the implementation notes](web-ui-v2-implementation.md) for what was delivered.

**Recommendation**

Make v2 a coherent workspace for finding, understanding, launching, and following SLURM jobs. The largest gains come from fixing the theme foundation, preserving context during navigation, and giving each workflow an appropriate layout. The existing functionality is substantial; its presentation and interaction contracts have become inconsistent.

Keep the Svelte 5 foundation and useful API capabilities. Rebuild the shared UI system and page composition incrementally. A framework migration is not justified by the problems found in this audit.

**What was examined, and the limits of the evidence**

Reviewed the application shell, five routes, job state management, output streaming, theme and preferences, launch editor, watcher creation, shared controls, and relevant API capabilities. Inspected the UI in Chromium at 1440×1000 and 390×844 using simulated hosts, jobs, watcher events, and output. Tested all four combinations of explicit light/dark application theme and light/dark operating-system preference. Checked search/navigation, theme switching, dialogs, output success and stream failure, and an empty search.

The simulated data avoids contacting configured HPC hosts or triggering real jobs, watchers, or notifications. It verifies presentation and local interaction behavior, not production SSH performance or end-to-end execution. The stream failure was deliberately induced by the local fixture; it is evidence about error presentation, not evidence that production streaming is broken. A small performance badge in screenshots is development-only and is excluded from product findings.

`npm run check` passed with **0 errors and 0 warnings** from svelte-check. This demonstrates that type/component validation alone does not catch the visual and interaction defects below. This is an expert audit, not measured user research; impact and priorities are recommendations to validate against real workflows.

**Confirmed pain points**

| Area | Observed problem | Consequence |
| --- | --- | --- |
| Theme foundation | Manual dark mode produces bright table/section headers, dark host/job counts on a dark background, and pale text on white job-selection cards. | Basic readability changes unpredictably by component and OS preference. |
| Global layout | A 320px job sidebar remains on Jobs, Launch, Watchers, and Settings. Jobs also repeats jobs in the central table. | Duplicate content consumes width; the editor, forms, and watcher board compete for space. |
| Jobs hierarchy | Partition tables are expanded by default when there are up to eight partitions. With two hosts, the mobile job table starts more than halfway down the screen. | Capacity information takes precedence over checking jobs. |
| Navigation continuity | Searching for `embedding`, opening job 48122, and returning to Jobs clears the search. | Repeated inspections require reconstructing the same context. |
| Job detail | Status, runtime, CPU, memory, and other metadata are repeated across a summary and large cards. | A user must scan many equally prominent fields to answer what happened and what to do next. |
| Watchers | Each watcher appears in a wrapper and an inner card, repeating its name, job, host, interval, and state. State counts recur in chips, summary cards, and charts. | High visual density without proportional information gain; operational actions are tiny. |
| Launch | Global job navigation, editor, a long form, and separate Presets/Templates/History/Save Template entry points coexist. | The relationship between a reusable starting point, resource defaults, and the actual submission is hard to follow. |
| Settings | Tall columns leave unused space; the theme description wraps almost word by word at the audited desktop width. Low-level WebSocket tuning and cache controls sit alongside everyday preferences. | Routine changes feel more complicated than they should. |
| Mobile | Job names are heavily truncated, detail tabs lose visible labels, and the launch toolbar turns white in explicit dark mode. | The phone UI needs its own hierarchy and interaction treatment. |
| Keyboard access | Table rows and some sorting headers use click handlers without equivalent keyboard controls. The watcher editor opens with focus still on the background Create button and ignores Escape. | Mouse-free use is inconsistent and dialogs do not reliably behave as dialogs. |
| Error presentation | When a running-job output stream fails, the output panel switches to a centered error and Retry state, hiding the content area. | The last useful evidence disappears exactly when it is needed for diagnosis. |
| Feature discoverability | Manual relaunch is tucked into a menu; recipe catalog and job manifest endpoints exist, but the web UI has no corresponding integration. | Powerful ssync capabilities are difficult to find or unavailable through the main web workflow. |

Evidence screenshots: [Jobs](assets/web-ui-v2-audit/dark-jobs.png), [Launch](assets/web-ui-v2-audit/dark-launch.png), [Watchers](assets/web-ui-v2-audit/dark-watchers.png), [Settings](assets/web-ui-v2-audit/dark-settings.png), [watcher job selection](assets/web-ui-v2-audit/dark-create-watcher.png), [mobile Jobs](assets/web-ui-v2-audit/mobile-jobs.png), [mobile Launch](assets/web-ui-v2-audit/mobile-launch.png).

**1. Establish one visual and interaction system — first priority**

The theme issue has a concrete implementation cause. The project uses Tailwind 4, but its semantic colors and `darkMode: 'class'` live in a JavaScript config that the CSS entry point does not load. The application toggles `.dark`, while generated `dark:` utilities respond to the operating system. Browser probes showed `bg-background` and `bg-input` remaining transparent and `text-muted-foreground` inheriting the body color. A `text-slate-900 dark:text-slate-100` element changed with the OS preference rather than the explicit application setting.

This matches Tailwind's documented v4 behavior: JavaScript configuration requires explicit loading, and manual dark mode requires a selector-based variant. See the [v4 configuration guidance](https://tailwindcss.com/docs/upgrade-guide#using-a-javascript-config-file) and [dark mode guidance](https://tailwindcss.com/docs/dark-mode#toggling-dark-mode-manually). Local evidence: [CSS entry point](../web-frontend/src/app.css), [theme configuration](../web-frontend/tailwind.config.js), [theme store](../web-frontend/src/stores/theme.ts), and [global styles](../web-frontend/src/global.css).

V2 should define semantic tokens for canvas, panel, elevated panel, input, border, primary/secondary text, focus, selection, and each job state. Build both themes from those tokens, including code editors, output, menus, dialogs, and disabled states. Avoid redefining literal colors such as white and gray to mean different things in different themes.

My proposed visual direction is restrained and technical: a light neutral canvas or graphite dark canvas, clear panel separation, readable typography, monospace where IDs/code benefit, and one accent color. Reserve stronger colors for status, selection, and action feedback. Replace the rainbow resource tiles and nested decorative cards with a consistent hierarchy.

Standardize buttons, fields, menus, tooltips, tabs, dialogs, drawers, tables, empty states, and feedback. Include focus, keyboard behavior, loading, errors, and reduced motion in those components. Ordinary text should meet the [WCAG 4.5:1 contrast requirement](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html). Dialogs should move focus inside, contain tab navigation, close with Escape where appropriate, and return focus on dismissal, following the [WAI dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/).

Why it matters: this repairs the shared cause of many defects and makes every later redesign more predictable.

**2. Give the application a consistent shell with contextual panels**

Use compact primary navigation for Jobs, Launch, Watchers, and Hosts, with Settings and connection health as secondary destinations. Hosts is a proposed home for partition capacity and host-specific diagnostics; it can initially be a panel rather than a new top-level page.

The full job list belongs in the Jobs workspace. On desktop, selecting a job can open a resizable inspector while preserving the table, filters, and scroll. Support an explicit full-page view for output-heavy work and a real URL for every selected job. A recent-jobs switcher can be available elsewhere on demand. Launch and Settings should have the width their tasks need.

Keep one predictable page header with a clear title, relevant scope, and primary action. Current generic Back labels can reflect unrelated previous destinations; use breadcrumbs or explicit contextual return links instead.

Why it matters: users keep their place, screens gain usable space, and navigation behaves consistently.

**3. Make Jobs a workspace for deciding what needs attention**

Provide visible views such as Running, Pending, Needs attention, and Historical. Needs attention should explain its membership: failed/timed-out jobs, failed watcher actions, or unavailable hosts, rather than an opaque score. Permit host grouping and keep running, pending, and historical jobs clearly distinguished.

Put host, state, user, search, and historical window filters in one discoverable toolbar. Show active filters as removable chips; persist search, sort, filters, selected job, and scroll through navigation. Put shareable filter state in the URL. Saved views such as “My GPU jobs on atlas” make repeated checks immediate.

Use configurable columns with sensible defaults: name/ID, host, state, runtime, and pending reason or failure information when available. Keep resource details available without making every row enormous. Offer comfortable and compact density. Use row selection and a contextual toolbar for applicable bulk operations, with explicit target counts and per-job results.

Move detailed partition capacity out of the initial job list. A compact host-health/capacity summary can link to the full view. Give arrays a useful aggregate row with running/pending/failed counts and expandable tasks.

Why it matters: the default screen helps answer “Which jobs need me?” and supports inspecting several jobs without repeated setup.

**4. Make Job Detail explain the job and support the next action**

Lead with job name, host, state, and the most relevant explanation: pending reason, runtime and time limit, or terminal state and exit code. Distinguish reported scheduler facts from missing data; do not infer a failure cause from an exit code alone.

Then provide Summary, Output, Script & launch context, and Watchers/Activity. A unified activity timeline can connect scheduler transitions, launch progress, watcher events, and relaunches when the underlying history exists. Put raw scheduler fields and file paths behind clearly labeled secondary sections.

Make actions state-dependent and visible: inspect output, manual relaunch, attach watcher, cancel when applicable, and copy a link. Manual relaunch should show what will be reused and what changed. Preserve host plus job ID as the identity throughout.

Why it matters: job detail becomes a useful diagnosis and action surface while retaining expert access to scheduler metadata.

**5. Develop Output into a dependable working surface**

Preserve the existing strengths: search, line navigation, wrapping, font size, line numbers, bounded rendering, and streaming. Integrate them into one compact toolbar with an explicit Follow latest control, paused-reading state, unread/new-line indicator, copy selection, and download options.

Offer stdout and stderr as a clear selector or side-by-side view. Calling stderr “Errors” can mislead because programs also write warnings and progress there. A combined chronological view is only appropriate when ordering/timestamps are actually available.

Show actual stream health and the last update separately from job state. A running job does not prove that its output connection is live. On failure, retain received content, mark it stale, and show a local reconnect action. Keep search position and reading position stable during updates. State clearly when content is truncated or search only covers loaded text.

Useful extensions include linking an output selection to watcher creation and displaying captured metric trends where real history exists.

Why it matters: output is central to troubleshooting; stability and trustworthy feedback matter more than decoration.

**6. Reorganize Launch around a repeatable submission**

Start with a clear choice: new script, saved template, repository recipe, or manual relaunch. Keep resource presets as defaults that can be applied to any compatible starting point; explain how they differ from whole scripts/templates.

On desktop, use an editor and configuration split with an adjustable divider. On smaller screens, use labeled Script, Resources, Files, and Review sections. Maintain one shared draft and a persistent submission summary: host, partition, resource request, time limit, source directory, and synchronization scope.

Preserve direct script editing, Vim mode, SBATCH parsing, and form/script synchronization. Make precedence visible when a host default, preset, form field, or script changes a value. Show a focused review of changes for manual relaunch. Autosave drafts and restore them after navigation or refresh.

Make validation actionable beside the field and in the summary. Host-aware partition/account choices should use known capabilities and allow manual values where discovery is incomplete. A sync preview should explain destination, includes/excludes, and file volume when the API can provide those facts.

Retain launch progress and show intelligible stages such as preparing, synchronizing, submitting, and submitted. On success, link to the new job while keeping a durable launch result. Failures should identify the failed stage and preserve the draft.

Why it matters: users gain confidence about what will be submitted and can reuse previous work without navigating several loosely related panels.

**7. Make Watchers readable rules with explainable outcomes**

Use one compact row/card per watcher: name, attached job/host, trigger summary, state, last outcome, and relevant actions. Select it to inspect configuration, captured variables, and event history in a consistent panel. Reduce repeated summary counts and move secondary aggregate charts out of the primary work area.

Express rules as “When this happens → if this condition is met → perform these actions.” Offer common starting points: notify on terminal state, capture a metric, or continue from a checkpoint. Keep advanced regex and timer controls available.

Pattern testing already exists and should be retained. Extend it into a preview of captures, evaluated conditions, interpolated values, and planned actions, without executing those actions. Accurate parity with the watcher engine may need a server-side preview endpoint. Explain timer activation, terminal-state triggers, and watcher resubmission limits in context.

For events, expose trigger → captured values → action → result → resulting job where available. Put failed actions and paused/problematic watchers in a readily accessible view. Use names consistent with CONTEXT.md, including the distinction between manual relaunch and watcher resubmission.

Why it matters: users can understand and trust automation rather than interpreting regex strings and event fragments across several cards.

**8. Make interaction feel immediate and discoverable**

Add a command palette for finding jobs and navigating to common actions, with visible shortcut hints and a help list. Support keyboard row navigation, accessible sorting, Enter to inspect, and Escape to dismiss. Keep destructive actions explicit and identify their targets.

Use consistent progress indicators and outcomes: an action is pending, succeeded, or failed with a recovery path. Optimistically update reversible preferences where appropriate, but wait for API confirmation before reporting scheduler operations as successful. Undo applies to genuinely reversible changes; cancelling a job has no general undo.

Use short transitions to explain panel opening and small highlights to identify changed data. Preserve selection and reading position during live updates. Respect reduced motion. New information should not unexpectedly move the row a user is acting on.

Why it matters: useful interactivity reduces effort and uncertainty. Animation alone will not repair the workflows.

**9. Separate connection health and everyday settings from diagnostics**

Provide a clear ssync Connection view with the ssync API URL, authentication state, and connection test. Distinguish unreachable API, rejected API key, unavailable host, stale data, and output-stream interruption. The global Connected badge currently reflects successful API authentication/connection testing, not the health of every host or stream.

Organize settings into Appearance, Job defaults, Notifications, Connection, and Advanced. Show where settings are stored and what they affect. Remove disabled “Coming soon” controls from the normal settings path. Consolidate the separate preference storage mechanisms so there is one clear owner for each setting.

Keep cache statistics, reconnect backoff, and low-level tuning in diagnostics. Preserve cached job information during transient outages and make its age visible. Empty states should distinguish no configured hosts, no jobs in the historical window, no matching filters, and failed loading.

Why it matters: users can recover from problems without learning the transport and cache implementation.

**10. Design mobile for checking and acting quickly**

Use compact cards or purpose-built rows that prioritize name, host, state, and one timely detail. Put filters in a sheet. Keep detailed host capacity out of the first viewport. Use labeled navigation and tabs, reachable action sheets, and controls sized for touch.

A mobile job view should quickly expose status, output, and the relevant next action. Launch should support resuming a draft or a simple relaunch through labeled stages, while keeping script editing available. Verify focus and layout with the software keyboard, safe-area insets, landscape, long names, and narrow widths.

Why it matters: responsive widths alone do not create a usable phone workflow.

**Larger opportunities worth exploring after the core redesign**

| Opportunity | Why it could be a substantial improvement | Dependency / scope |
| --- | --- | --- |
| Repository recipes and profiles in Launch | Makes web launches reproducible and aligns the UI with capabilities already present in ssync. | Catalog and manifest endpoints exist. Review recipe rendering, validation, and submission contracts before assuming the whole flow is ready. |
| Job comparison | Compare scripts, resource requests, exit states, durations, and captured metrics to investigate why one job differed. | Some data already exists; meaningful metrics comparison requires compatible names, units, and retained history. |
| Relaunch and watcher lineage | Follow an original job through manual relaunches and watcher resubmissions instead of searching disconnected IDs. | Requires reliable parent/child relationships; do not derive lineage from similar names. |
| Project-oriented saved workspaces | Group jobs, recipes, source directories, and watchers around a project; restore the user's working context. | Agree on project identity, ideally from repository/manifest metadata rather than name heuristics. Start with saved filters. |
| Actionable activity inbox | See failures, completed jobs, watcher outcomes, and launch problems since the last check. | Durable events, read/dismiss state, grouping, and notification preferences may need API work. |
| Array exploration | Quickly find failed tasks, compare parameters, inspect task output, and target supported actions within a large array. | Build on existing array groups; confirm scheduler/API support before offering subset relaunch or cancellation. |
| Resource insight | Show requested versus measured resources and capacity by host/partition to inform the next launch. | Label allocation, accounting, and live utilization distinctly. CPU/GPU telemetry should only be shown when actually collected. Avoid unsupported queue-time predictions. |

These are candidate product investments, not required additions to ship a coherent v2. Choose based on the workflows used most frequently.

**Recommended delivery order**

| Stage | Scope | Value / effort assessment | Completion evidence |
| --- | --- | --- | --- |
| 1. Shared foundation | Theme contract, controls, typography, feedback, accessible dialogs, application shell. | Very high leverage; medium scope across many screens. | Light/dark/system combinations render correctly; common controls behave consistently by keyboard and touch. |
| 2. Daily monitoring | Jobs views/filters, context-preserving inspector, job summary, output resilience, host freshness. | Highest daily workflow value; medium-to-large scope. | Search → inspect output → return preserves context; transient failures retain useful data. |
| 3. Launch and Watchers | Draft-based launch, visible review, reusable sources, compact watcher list and event inspector. | High value for active operation; large scope. | A manual relaunch and a watcher configuration can be understood before submission, with clear results afterward. |
| 4. Selected extensions | Recipes, comparison, lineage, projects, or inbox based on validated demand. | Potentially high value; API/data dependencies vary. | Each feature is backed by an explicit data contract and a validated user task. |

Develop the foundation and the Jobs → Job Detail → Output flow as the first complete slice. Then apply the same system to Launch, Watchers, and Settings. Preserve existing capabilities during migration; use a capability inventory so array grouping, watcher metrics, pattern testing, source synchronization, and editor features are not accidentally lost.

The code supports this approach: Svelte 5 is already in use and type validation is clean. The maintenance challenge is large components with mixed responsibilities: JobLauncher is about 5,858 lines, SettingsPage 1,652, WatchersPage 1,649, and JobSidebar 1,400. Split them by workflow responsibility as their screens are redesigned. Consolidate overlapping primitives and preference stores rather than creating another competing layer.

**How to decide whether v2 is better**

Measure representative tasks against a baseline: finding a failed job, understanding its available failure evidence, returning to the same filtered list, preparing a manual relaunch, and explaining a watcher's last action. Compare completion time, navigation steps, mistakes, and recoverability; do not invent improvement percentages in advance.

Make visual checks cover desktop and mobile, explicit themes against both OS preferences, long names/paths, empty and large lists, arrays, partial host failures, stale data, and output interruption. Use focused interaction checks for preserved filters, restored drafts, keyboard dialogs, successful/failed operations, and live updates while reading. Treat visual snapshots and real task walkthroughs as necessary alongside type checks.

The immediate design deliverable should be connected prototypes for three journeys: **find a problem job and inspect output; prepare and review a manual relaunch; understand and edit a watcher**. These will reveal whether the proposed navigation, density, and panels work together before a full implementation begins.
