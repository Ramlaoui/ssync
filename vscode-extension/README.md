# ssync for VS Code

Submit SLURM scripts, monitor jobs across clusters, and inspect their output inside VS Code. The extension talks to your existing ssync server; it does not install software on clusters.

## Try the rebuild

```sh
cd vscode-extension
npm install
npm run check
npm test
npm run test:host
npm run test:package
npm run package
code --install-extension ssync-vscode-0.2.0.vsix
```

`test:host` requires the `code` command on PATH and opens an isolated VS Code profile. It uses a fake server and performs no cluster operations. Development and DOM tests require Node.js 22 or newer.

Start your server with `ssync web --foreground --no-browser`. In VS Code, run **ssync: Configure Connection**, then **ssync: Open Jobs Dashboard**, or select the ssync activity bar icon.

For an isolated UI demo, run `npm run demo` and open `http://127.0.0.1:8052`. This preview uses the packaged UI assets with fake jobs. To test native commands, point an Extension Development Host at this server. The demo server never submits or cancels real jobs. Stop it with Ctrl+C.

Open this directory in VS Code and press F5 to launch an Extension Development Host. Its launch configuration builds the extension automatically.

## Workflow

- **Dashboard:** state totals, search, cluster/state filters, active jobs first, and connection recovery actions. Filters persist while the panel is open.
- **Sidebar:** native cluster/job entries with stable identities, themed status icons, runtime, queue reasons in tooltips, and log/cancel actions.
- **Inspector:** job resources, queue reasons, stdout/stderr tabs, keyboard tab navigation, follow/wrap controls, copy, and a retained view during refresh failures. It fetches the last 500 lines per stream; active jobs refresh every five seconds while visible.
- **Submit:** select a script, cluster, and sync choice, then review the submission. Unsaved editor contents are used. The extension follows background launch progress until the server returns a job ID. Cancelling progress stops watching; it does not cancel the server launch.
- **Sync:** executes the local ssync CLI as a VS Code task, with platform-safe argument quoting. Submission selects the script's own workspace folder in multi-root projects. Local folders and a local server are required for syncing; remote servers and Remote SSH scripts support script-only submission.

## Connection and settings

New API keys are stored per server in VS Code SecretStorage. The legacy `ssync.apiKey` setting still works. Local connections can also read `~/.config/ssync/.api_key` in either plain-text or JSON format. The local key file is not automatically used for remote server URLs.

| Setting | Default | Purpose |
| --- | --- | --- |
| `ssync.apiUrl` | `https://localhost:8042` | Server address; an optional reverse-proxy base path is supported |
| `ssync.pollInterval` | `120` | HTTP history reconciliation and polling fallback, in seconds |
| `ssync.showCompletedJobs` | `true` | Include finished jobs |
| `ssync.completedJobsWindow` | `3d` | Completed history window, e.g. `1h`, `3d`, `1w` |
| `ssync.requestTimeout` | `30` | Wall-clock request deadline, in seconds |
| `ssync.trustLocalCertificate` | `true` | Allow self-signed certificates on loopback addresses only |

Realtime updates use WebSocket header authentication, heartbeats, and reconnect backoff. HTTP reconciles history periodically and remains available when WebSocket is unavailable. Failed refreshes preserve the last known jobs and show their timestamp. Configuration changes discard old responses and close inspectors connected to the old server.

Remote HTTPS servers always require valid certificates. Monitoring works in untrusted workspaces; submitting, syncing, and starting the local server require workspace trust. The extension runs on the UI machine, including when a remote workspace is open.

## Code structure

The extension uses plain TypeScript and vanilla webview JS/CSS. `ws` is its only runtime dependency.

| Module | Responsibility |
| --- | --- |
| `client.ts` | Bounded HTTP requests, response validation, authentication, WebSocket transport |
| `model.ts` | Shared job types, state labels, sorting, and host/job identity |
| `jobStore.ts` | One job snapshot, reconciliation, visibility lifecycle, reconnects, race protection |
| `extension.ts` | Activation, settings, commands, status bar, and surface wiring |
| `workflows.ts` | Host selection, submission, sync tasks, cancellation |
| `jobsTree.ts` | Native sidebar rendering |
| `dashboard.ts`, `logPanel.ts` | Webview lifecycle and validated message routing |
| `webview.ts`, `media/` | Packaged UI, nonce-based CSP, themed styles, incremental rendering |

`npm test` runs transport/store tests against real local HTTP/WebSocket sockets and DOM tests of the shipped UI scripts. `npm run test:host` verifies activation, command registration, webview startup, and distinct log panels for identical job IDs on different hosts. `npm run test:package` repeats those host checks using the exact packaged VSIX. Fake servers, previews, and test bundles are excluded from the VSIX.

## Revamp direction

This first pass concentrates on submit → monitor → inspect, with explicit connection state and one shared data store. The dashboard handles comparisons and filtering; the sidebar provides fast native navigation. Job data is inserted as text, and log polling updates the existing page instead of rebuilding it.

Next candidates are launch recipes, partition/resource discovery, array grouping, and watcher management. Add those through the server's existing APIs after the core workflow has been exercised against real clusters. They should reuse this store and command layer rather than create another client or UI framework.

Visual review checklist: dark/light/high-contrast themes, a narrow editor split, long job names and queue reasons, outage/recovery, keyboard focus, and scroll position with Follow disabled. The browser demo supports `?theme=light` and `?theme=contrast` for previewing palette changes.
