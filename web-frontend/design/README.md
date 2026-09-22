# ssync web UI v2 proposal

An interactive, local Svelte prototype with sample data. The production app stays in `../src/`.

From `web-frontend/`:

```sh
npm run dev -- --host 127.0.0.1 --port 5180
```

Open **http://127.0.0.1:5180/design/**.

## Design

- `theme.ts` imports the same light/dark colors, radii, and motion timings as the production frontend from [`relay-tokens.json`](../src/lib/design/relay-tokens.json), mirrored from the iOS design system. The mark follows the iOS Relay SVG.
- Running is cobalt, completed is green, pending and timed out are amber, and failed is red. Text and symbols carry the same meaning without color.
- Maximizing a job collapses navigation to a rail, removes the page heading, and fills the remaining viewport. Overview becomes a two-column layout; output and scripts use the available height. Restore returns to the existing selection and filters.
- Hover and keyboard focus make rows, tabs, recipes, and controls easier to identify. Touch targets expand for coarse pointers; reduced motion disables transitions.

## Try it

- Search, filter, sort, select, and maximize jobs. Job links retain host and ID.
- Read output, search lines, pause sample output, copy content, and relaunch into an editable draft.
- Change resource directives without losing edits to the script body. Review a simulated launch to add a pending sample job.
- Create, edit, pause, and test watcher rules. Changes survive navigation within the preview.
- Switch light/dark/system appearance, adjust density, or use ⌘/Ctrl K to find jobs.

Theme, density, preferences, and the launch draft use browser-local storage under `ssync-design-*`. Jobs and watchers are in-memory sample state. Running stdout appends a sample line every four seconds while following. Host capacity, file listings, historical metrics, and initial logs are fixtures. No real jobs, syncs, notifications, or watcher actions run. The rule tester uses JavaScript regular expressions.

## Validation

```sh
./node_modules/.bin/svelte-check --tsconfig ./design/tsconfig.json
./node_modules/.bin/vite build --config design/vite.config.ts
```

The separate build writes to ignored `design/dist/`. It does not replace the production build. The prototype uses the frontend's token copy and can be built without the iOS project.

The earlier product audit is in [`docs/web-ui-v2-audit.md`](../../docs/web-ui-v2-audit.md).
