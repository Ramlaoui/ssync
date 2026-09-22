# Native implementation

Status as of 22 September 2026: the native app and WidgetKit extension build in Xcode 26.6 for iOS 26.0+. The shared core has 17 passing tests. The signed native build is installed and launches on an iPhone 16 Pro Max running iOS 26.6.2. The Jobs screen has been inspected in a device screenshot; simulator interaction has not yet been verified.

This is the first executable implementation of the [Relay design](DESIGN_SPEC.md). It uses SwiftUI, Observation, SwiftData, URLSession, Keychain, WidgetKit, ActivityKit, App Intents, and UIKit for notification registration and the share sheet. It has no Expo, React Native, CocoaPods, or third-party Swift dependencies.

## Implemented surfaces

| Surface | Behavior |
| --- | --- |
| Connect | Named server connections; API-key authentication; connectivity check; saved connections; labeled demo workspace. |
| Jobs | Running/queued/attention summary; host sections; active/all/pinned/history filters; local search; arrays; reviewed failures; per-host identities. |
| Job detail | State, elapsed wall time, allocation, partition link, pins, watchers, script/manifest inspection, relaunch preparation, confirmed cancellation. |
| Output | Authenticated SSE; stdout/stderr switching; bounded 512 KiB buffer; automatic reconnect and snapshot fallback; saved output for offline reading; search within loaded text; matching-line navigation; wrap control; local bookmarks and markers; full-file download and sharing. Scrolling pauses follow. |
| Hosts | Separate capacity and job observations; host/partition drill-down; CPU allocated/idle/other counts; GPU allocation and types; availability and aggregate node states; partition-specific job filters; launch prefill. |
| Watchers | State filtering; search; When/Using/Then composition; event history and captures; pause/resume; explicit manual execution and deletion; create/edit forms; structured common action parameters with a JSON escape hatch. Existing multi-action configurations remain editable as a complete JSON list. |
| Launch | Persistent drafts and reusable local recipes; script editing; server directory browsing; source-sync/ignore controls; resource fields; scheduler fields; exact-request review; explicit confirmation; operation polling and saved launch ID. Ambiguous submissions remain locked against an accidental retry. |
| Settings | Connections, notification permission, device registration, test delivery, shared server notification rules, widget privacy, and ending Live Activities. |
| Widgets | Job summary, selectable pinned job, selectable partition capacity. App Group snapshots, observation ages, host/job deep links. Widgets never receive the API key. |
| Live Activity | Explicitly follow one job per connection; stop following from the job page, Lock Screen, or expanded Dynamic Island; last-observed state and elapsed time; foreground updates; stale presentation; terminal ending. Dismissal targets one activity ID and never changes the cluster job. |
| Shortcuts | Show Jobs, Prepare Launch, and parameterized Open Job intents. Launch shortcuts never submit jobs. |

Main content uses the approved warm-paper/cobalt palette, state rails, count panels, custom glyphs, and Relay mark. Short handoff and numeric transitions respect Reduce Motion. Native navigation, sheets, selection, and controls provide platform behavior.

## Connection and persistence rules

- API keys live in Keychain with device-only accessibility. URLs and connection names are stored in preferences.
- Requests use an ephemeral URLSession without URL caching or cookies. API keys travel in headers, including WebSocket and SSE requests.
- TLS uses system trust. The app does not accept arbitrary self-signed certificates. Install the server’s CA on the device, or use a trusted HTTPS endpoint.
- Local networking is enabled in the transport configuration.
- Job identity is host + job number within a connection. Sessions, pins, drafts, and output snapshots are connection scoped.
- Draft operations retain their original connection when the user switches workspaces.
- Output cache files use hashed identities and iOS file protection; each saved text buffer is bounded. Forgetting a connection removes output, session, bookmarks, credentials, and drafts.
- Job status refreshes every 30 seconds while foregrounded; the jobs WebSocket supplements incoming changes. Backgrounding stops these loops.
- Capacity is scheduler allocation. The app does not invent hardware utilization, queue ETAs, individual node health, or additive capacity across overlapping partitions.
- Jobs use the current server-detected user, the last seven days, and at most 1,000 results per host. Search and counts are scoped to loaded data.
- Output line numbers describe the loaded buffer, not absolute remote offsets. Bookmarks retain excerpts, not stable remote line numbers after rotation.
- No real cluster cancellation, watcher execution, or launch was used during verification.

## Server contracts checked

- Status requires a relative range such as since=7d, not an ISO date.
- Partition query_time is a duration. Freshness comes from updated_at, stale, and cache_age_seconds.
- Array tasks are incorporated with host-qualified identities.
- Watcher actions can return parameters as config; editing normalizes to params while preserving values and action conditions.
- Development APNs entitlements use development; this backend expects registration environment sandbox.
- Blank allowed states submit null to retain the server’s terminal-state default.
- Launch can return an operation ID before a scheduler job ID exists.
- A network failure during launch is not treated as proof of failure.
- Notifications contain host/job but no connection ID. With multiple saved servers, opening a notification asks which server to use.

## System integration boundaries

Native APNs registration and notification handling are implemented. Delivery requires a signed build and server APNs configuration matching the bundle and environment. Simulator compilation cannot prove delivery.

Live Activities currently update from the foreground app. **Background ActivityKit push updates are not implemented in the current server or this build.** Activities show update time and become stale. Remote updates require a separate activity-token lifecycle, host/job association, expiry, and APNs liveactivity messages. Follow [Apple’s ActivityKit push contract](https://developer.apple.com/documentation/ActivityKit/starting-and-updating-live-activities-with-activitykit-push-notifications).

Widgets display snapshots captured while the app is open. Timeline refresh does not query the server; it preserves observation age.

Live Activity controls use a shared `LiveActivityIntent` to dismiss an individual activity immediately without opening the app. The job page observes ActivityKit lifecycle changes and reflects dismissals. Expanded Dynamic Island content uses 24-point side, 12-point top, and 18-point bottom margins; the job name and action row sit below the camera regions.

The server’s bare-job-ID mute behavior is not exposed as a per-job mute control because IDs can collide between hosts. Shared host/name/state/user rules are available.

The privacy manifest declares app-local UserDefaults access and device identifiers/user content transmitted to the selected server for app functionality. There is no analytics SDK or advertising tracking. Distribution still requires review against the actual deployed service and App Store disclosures. See [Apple’s required-reason API documentation](https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacyaccessedapitypes/nsprivacyaccessedapitype).

## Remaining design work

The full specification remains the longer-term acceptance target. This build does not yet provide:

- Remote ActivityKit push delivery or push-to-start.
- Server-side watcher dry-run previews, richer structured multi-action editing, and dedicated array-watcher/timer builders.
- Server repository/recipe catalog browsing or full launch-manifest rehydration. Relaunch starts from the stored script and preserves available manifest provenance; resources and sync settings need review.
- Server idempotency keys or durable server restart recovery for launch operations. The client retains operation IDs and blocks ambiguous retries.
- Exact output positions across source switches, cross-stream search, or search beyond loaded text.
- iPad split-column navigation, a VoiceOver walkthrough, an accessibility audit, or device performance traces.
- App Store signing and distribution configuration.

These are explicit gaps, not simulated completed features.

## Verification

| Check | Result |
| --- | --- |
| XcodeGen generation | Passed |
| App + widget extension, arm64/x86_64 Simulator compilation | Passed |
| iOS unit-test and UI-test target compilation | Passed |
| Shared core tests on macOS | 17 passed |
| URLSession contract tests | Passed using an in-process fixture protocol |
| Swift formatting | Applied with Xcode swift-format; DTO wire names intentionally retain snake_case |
| Simulator launch / visual inspection | Pending a booted simulator |
| UI test execution | Not run |
| Signed physical-device build and installation | Passed on iPhone 16 Pro Max, iOS 26.6.2; app and widget profiles include the shared App Group, and the app includes development APNs |
| Physical-device launch | Passed; updated build launched through CoreDevice |
| Jobs screen on physical device | Screenshot confirms the complete toolbar logo, rounded status-strip clipping, and removal of filler headlines |
| Elapsed-time text contrast | Uses OnAccent directly: 6.12:1 light and 7.70:1 dark; checked by the asset validator |
| Live Activity stop action on physical device | Passed: creates two test activities with identical host/job IDs on separate connections, stops only the selected activity, and safely repeats the stop intent; test activities cleaned up |
| Expanded Dynamic Island visual check | Layout compiles with explicit content margins; screenshot verification awaits the expanded activity on device |
| Native APNs delivery | Not tested |

Core tests cover duration parsing, nullable/unknown server fields, cross-host identities, arrays, GPU-absent partitions, watcher configuration, credential placement, URL encoding, errors, resource limits, launch persistence/retry guards, bounded Unicode output, scoped search, SSE framing, and route response decoding.

UI targets contain two flows: demo job → output → hosts, and launch review that cannot submit without explicit confirmation. They attach screenshots when executed.

A sandboxed Xcode invocation could not access CoreSimulator and Swift macro services. An elevated review timed out; the retry succeeded. Successful builds used Xcode’s normal simulator/compiler services.

The iOS Debugger skill requires asking before booting a simulator when none is running. Boot approval was requested and remained pending during this implementation pass. No simulator was booted automatically.

## Code map

- App/: entry, per-tab navigation, session state, refresh/WebSocket lifecycle.
- Core/Domain/: tolerant models, JSON preservation, launch validation, output buffer/SSE framing.
- Core/Networking/: API requests, errors, downloads and WebSocket construction.
- Core/Persistence/: Keychain, SwiftData drafts, protected snapshots/output cache.
- DesignSystem/: semantic colors, content components and event-driven motion.
- Features/: connection, jobs, output, hosts, watchers, launch and settings.
- Shared/: Relay mark, App Group snapshot contract, ActivityKit attributes.
- SystemIntegration/: notifications, activities and App Intents.
- Widgets/: three widgets and Lock Screen/Dynamic Island presentation.
- Tests/: core contracts and UI flows.
