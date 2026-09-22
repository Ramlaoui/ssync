# Web UI v2 implementation

The production entry point is `web-frontend/src/App.svelte`. The approved reference remains in `web-frontend/design/`; the application uses the existing ssync API and live job manager.

## Delivered

- Shared workspace navigation, keyboard quick find, responsive navigation, and appearance controls.
- Job search, host/user filters, history windows, state views, array grouping, and incremental loading. Selection, filters, output tab, and list position survive navigation.
- A side inspector and a maximized job workspace with a collapsed navigation rail. Overview, stdout/stderr, script, watchers, and activity use real job data. Cancel requires confirmation; relaunch stages the existing script in the launcher.
- Launch presets, editable SBATCH configuration, a local draft, and a review step before the existing launch monitor submits the request. Script bodies and custom directives remain intact when resource inputs change.
- Watcher controls with activity beside the list, and host cards with reported partition capacity, errors, and cache freshness. Partitions are displayed individually because they can share nodes.
- Settings sections with light/dark/system previews, immediate density and refresh preferences, and the existing connection, sync, notification, cache, and import/export controls.

## Design and compatibility

`web-frontend/src/lib/design/relay-tokens.json` mirrors `ios/design/tokens.json`. The web copy lets standalone frontend and Python-package builds work without the iOS project. Update both token files together. Shared components live in `src/components/workspace/`; shared frame and interaction styles live in `src/workspace.css`.

Running jobs use Relay cobalt, successful jobs green, warnings amber, and failures red. System appearance follows OS changes. The code editor follows application appearance by default and preserves explicit editor preferences.

Existing `#/jobs/:id/:host` links and watcher deep links remain supported. The existing streaming output, array controls, launch monitor, watcher actions, and notification backend are retained. No backend schema changes or new runtime dependencies were required.

Vite's JavaScript entry delegates to the TypeScript configuration. Development proxies preserve `/api` and forward `/ws` to the CLI's default `https://localhost:8042`; set `SSYNC_BACKEND_URL` to use a different backend. The generated self-signed certificate is accepted only for a loopback backend. Launch, watchers, hosts, and settings load on demand.

## Verification

- `npm run check`: no errors or warnings.
- `npm run test:run`: 170 passing tests, one existing skipped test.
- `npm run build`: production assets build successfully.
- Added checks cover selection and maximize context, stale script responses, cancel confirmation and target, filtering and history, resource presentation, draft restoration, numeric SBATCH edits, launch review, appearance changes, and credentials used by retained API clients.
- Interaction tests use mocked cluster actions; no real job was launched or cancelled for validation. Browser visual QA was not performed.

For a local preview, run `npm run dev -- --host 127.0.0.1 --port 5180` from `web-frontend/` and open `http://127.0.0.1:5180/`. Live data requires starting ssync or pointing `SSYNC_BACKEND_URL` at an existing server. The standalone design prototype is available at `/design/`.
