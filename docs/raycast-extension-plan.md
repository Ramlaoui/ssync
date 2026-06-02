# Raycast Extension Plan

## Scope

The first Raycast extension release is a monitoring surface for ssync jobs. It should make running and pending work easy to inspect without adding background load to the ssync API server.

## V1 Features

- Configure and test an ssync connection before first use.
- Load jobs cache-first, then revalidate when the cached snapshot is older than 60 seconds.
- Show the main Jobs command as lifecycle-first sections:
  - Running Jobs
  - Pending Jobs
  - Historical Jobs
- Default historical job window: `3d`.
- Default job limit: `50`.
- Search locally across the loaded job snapshot.
- Show a single Job Detail view with lazy secondary actions.
- Fetch Job Output only when requested.
- Default Job Output to stdout, tail-limited.
- Allow switching from stdout to stderr when needed.
- Fetch Job Script only when requested.
- Fetch Watchers and Watcher Events only when requested.
- Keep watchers read-only in v1.
- Include a menu-bar command with running jobs first and pending jobs second.
- Keep menu-bar background refresh conservative, defaulting to 5 minutes.
- Allow blank API keys when the ssync API server accepts the connection.
- Guard cancellation behind confirmation.

## Deferred

- Manual relaunch.
- Watcher edit, delete, attach, pause, resume, or trigger actions.
- WebSocket support.
- Launch recipe browsing or submission.
- Historical jobs in the menu-bar dropdown.

## Backend Load Rules

- Do not poll on every search keystroke.
- Do not fetch output, script, manifest, watchers, or watcher events while rendering the main Jobs list.
- Do not fetch both stdout and stderr by default.
- Do not force-refresh by default.
- Manual refresh may ask the ssync API server for fresh job status.
- Background menu-bar refresh must only fetch job status.

## Output And Script Views

- Job Output defaults to `output_type=stdout&lines=300`.
- Stderr is a secondary action, not loaded by default.
- Full output is a deliberate secondary action, not the default.
- Job Script opens as a separate formatted detail view.
- Output and script text should be displayed in a monospace code block with job metadata above it.
- Raycast action shortcuts may support view-level commands such as refresh, switch to stderr, copy, and load full output. Custom vim-style single-key scrolling is not assumed to be available inside Raycast extension views.
