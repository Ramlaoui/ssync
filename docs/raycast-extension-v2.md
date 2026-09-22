# Raycast v2 implementation

The extension extends the original monitoring surface into a native ssync workspace. See [the extension README](../raycast-extension/README.md) for setup, commands, shortcuts, and API compatibility.

## Design and behavior

- Reuse Relay's iOS icon and semantic light/dark colors through Raycast native components.
- Keep the main job list responsive: local search, host filters, lifecycle sections, attention and pinned views, immediate snapshot inspector.
- Make connection management and HPC host defaults separate, directly accessible commands.
- Keep job identity scoped to host and connection, including menu bar deep links and watcher events.
- Preserve cached information on refresh failures and cancel stale requests on navigation or scope changes.
- Fetch heavy job details, output, scripts, watchers, and partition capacity only when opened.
- Review launches before submission. Preserve custom script directives and explicit sync choice. Never automatically retry an uncertain launch POST.

## Host defaults API

Authenticated `GET` and `PUT /api/hosts/{hostname}/settings` return only editable submission defaults and a configuration revision. PUT requires that revision and rejects concurrent edits with HTTP 409.

The effective hosts list comes from the last base/overlay document that defines it, matching configuration list replacement semantics. Only the selected host's `slurm_defaults` block is rewritten. Unknown existing defaults are retained, unrelated YAML remains unchanged, and incompatible alias/compact layouts fail without writing. The existing atomic config writer preserves file permissions.

The manager's reload fingerprint now includes overlay files and nanosecond timestamps, so edits take effect on the next manager access.

## Storage and compatibility

Profiles use versioned LocalStorage metadata and Raycast's encrypted credential store. Updating a key publishes a new credential reference together with its endpoint. Failed publication leaves the previous profile usable. Existing v1 settings and credentials migrate automatically.

Caches are scoped to connection ID, endpoint, credential, history window, and result limit. Pins/view settings are scoped per connection and reset when its endpoint changes. Explicit launch drafts are scoped to the connection and endpoint.

Older API servers can still use the existing monitoring endpoints. Host editing specifically requires this backend revision. Host SSH endpoints and authentication are intentionally outside the submission-default editor.

## Verification

Run the commands in the extension README and:

```sh
UV_CACHE_DIR=/tmp/ssync-uv-cache uv run --no-sync pytest --no-cov \
  tests/unit/test_web_host_settings.py \
  tests/unit/test_config.py \
  tests/unit/test_config_hosts.py -q
```

Backend tests use temporary YAML and mocked manager instances. Raycast tests mock native components and the transport; they do not submit jobs, change live hosts, or execute watcher actions.

Validation: 56 Raycast tests and the host/config, API routing, output-transfer, and backend capacity checks pass. Type checking, source lint, formatting, and the six-command build pass; npm audit reports no vulnerabilities. Full publishing validation still needs a valid Raycast author account.

The development extension was loaded into Raycast and the Jobs list/inspector rendered against the configured API. Live host edits and submissions were not exercised.

Integration with current main preserves the bounded worker pools, thread-safe manager initialization, and file-streamed output downloads. Host settings use the bounded local worker pool. Forced output downloads refresh the selected stream before opening its cached file.
