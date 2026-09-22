# ssync for Raycast

A native companion to the ssync web and iOS apps: inspect jobs, manage connections, change host defaults, follow output, and prepare launches without leaving Raycast.

## Commands

| Command                | What it does                                                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------ |
| **Jobs**               | Host and lifecycle sections, local search, pinned jobs, attention view, and a collapsible inspector.   |
| **Hosts & Defaults**   | Inspect partition capacity, edit submission defaults, choose your default host, and launch on a host.  |
| **Manage Connections** | Add, edit, test, and switch named ssync API connections.                                               |
| **Watchers**           | Browse rules and events across jobs; inspect failures, edit, pause, resume, trigger, or delete a rule. |
| **Launch Job**         | Edit a script, select source synchronization and resource overrides, review, and submit.               |
| **Job Summary**        | A menu bar view of pinned, running, pending, and attention jobs, with connection switching.            |

The Relay icon and light/dark status colors match the iOS design tokens. Raycast owns window layout, typography, backgrounds, selection, and accessibility contrast.

## Setup and development

Use Raycast on macOS and Node 24 LTS (or Node 22.22.2+ on the supported Node 22 line).

```sh
cd raycast-extension
npm ci
npm run dev
```

Open **Manage Connections** in Raycast. Enter your ssync API URL and key, then connect. New endpoints and credential changes are tested before saving. A blank key works only if the server accepts it. For localhost, **Use Local ssync API Key** explicitly fills the locally configured key.

Existing single-connection settings migrate automatically. Each profile has separate encrypted credentials, a job cache, pinned jobs, and view preferences. Changing the server clears that profile's old job identities. Changing a connection's origin clears the form's old key and certificate-trust choice.

Remote HTTPS certificates are verified. Self-signed remote certificates require opting in for that profile. Local loopback HTTPS supports ssync's local certificate. HTTP and reverse-proxy URL prefixes are supported.

## Hosts and defaults

Select a host and use **Edit Host Defaults** (`⌘E`). Editable defaults include partition, account, CPUs, memory in GB, time, nodes, tasks/GPUs per node, QoS, constraints, and generic resources. Blank fields remove that host override. Edits affect future launches.

**This feature requires the ssync API server from this revision.** Restart/update that server before using host editing. Older servers continue to support the other existing endpoints; the editor explains when its endpoint is unavailable.

The authenticated API edits only the selected host's submission defaults in the effective configuration file, including local overlays. A revision check rejects stale forms. Unrelated host configuration and credentials are preserved. Complex shared YAML that cannot be safely edited is rejected with an explanation.

## Daily shortcuts

Open the action panel with `⌘K` for all available commands.

| Context                       | Shortcut | Action                                  |
| ----------------------------- | -------- | --------------------------------------- |
| Jobs                          | `↵`      | Open the full job inspector             |
| Jobs                          | `⌘O`     | View output                             |
| Jobs                          | `⌘⇧S`    | View script                             |
| Jobs                          | `⌘⇧W`    | View watchers for the job               |
| Jobs                          | `⌘⇧P`    | Pin/unpin                               |
| Jobs                          | `⌘⇧D`    | Show/hide the inspector                 |
| Jobs                          | `⌘⇧F`    | Filter by host                          |
| Jobs                          | `⌘⇧H`    | Hosts & Defaults                        |
| Jobs                          | `⌘⇧,`    | Manage Connections                      |
| Jobs                          | `⌘⇧L`    | Prepare manual relaunch                 |
| Jobs                          | `⌘N`     | Prepare a new launch                    |
| Views                         | `⌘R`     | Refresh the current view                |
| Output                        | `⌘T`     | Switch stdout/stderr                    |
| Output                        | `⌘F`     | Search loaded output                    |
| Output                        | `⌘⇧P`    | Follow/pause output                     |
| Output                        | `⌘O`     | Open the selected stream in your editor |
| Job watchers                  | `⌘N`     | Create a watcher                        |
| Host/connection/watcher lists | `⌘E`     | Edit the selected item                  |

Job cancellation and watcher deletion require confirmation. Manually triggering a watcher also confirms because its actions may resubmit or cancel jobs.

Output initially loads 300 lines of stdout. Stderr, larger tails, and full output are explicit actions. Following polls every 10 seconds while the view is open; full previews stay bounded, and full files can open in the configured external editor. Search covers the loaded text, up to its last 2,000 lines. Refresh failures preserve the last useful content.

## Launch and automation

A manual relaunch starts with the original script, including custom directives. Resource fields are optional overrides. Source directories refer to the machine running the **ssync API server**. Choose **Script Only** to omit synchronization.

**Review Launch** displays the script, host, source, sync rules, and overrides before submission. Duplicate presses cannot submit twice. If a response is ambiguous, check Jobs before starting another launch. Accepted launches display progress, with automatic reads for up to five minutes and manual refresh afterward. Save/restore drafts is explicit and local to the connection's endpoint.

Create a watcher from a job's watcher view. Common actions have native choices; **Custom Actions** preserves support for notifications, captured variables, and watcher resubmission. Existing rules keep their custom action configuration. Watcher resubmission remains distinct from manual relaunch.

## Validation

```sh
npm run check
npm test
npm run lint:code
npm run build
```

Full `npm run lint` additionally validates the manifest and author against Raycast's online directory. The inherited author value must match your actual Raycast account before publishing.

Tests cover profile migration and credential isolation, transport/TLS behavior, host/job identity, stale response races, output recovery, form validation, watcher creation, cancellation confirmation, and reviewed launch submission. Python tests for the host editor live in `tests/unit/test_web_host_settings.py`.

Search and selection do not query the server. Job snapshots revalidate after 60 seconds, menu bar updates remain at five minutes, and output/script/watcher/capacity requests are lazy.
