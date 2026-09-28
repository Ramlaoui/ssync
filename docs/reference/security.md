---
description: Protect the ssync server with API keys, HTTPS, and safe network exposure.
---

# Security

The ssync server can read your job output and submit or cancel jobs on your clusters with your SSH identity. Treat access to it like access to your SSH keys.

## The defaults

- The server listens on `127.0.0.1` only, so only your own computer can reach it.
- It serves over HTTPS with a self-signed certificate stored in `~/.config/ssync/certs/`.
- API keys are **not** required by default. That is fine while the server is reachable only from your computer.

## Require an API key

Do this before letting any other device (your phone, another computer) reach the server.

```bash
ssync auth setup                  # generates a key and saves it to ~/.config/ssync/.api_key
export SSYNC_REQUIRE_API_KEY=true # enforce it for the server you start next
ssync web
```

Clients send the key in the `X-API-Key` header; the web app exchanges it for a browser session. Enter the same key in the iPhone app and the Raycast extension.

Other `ssync auth` commands:

| Command | Description |
| --- | --- |
| `ssync auth show` | Show where the key comes from, masked. |
| `ssync auth test` | Check that the running server accepts the key. |
| `ssync auth setup --force` | Replace the key. |

You can also provide the key through the `SSYNC_API_KEY` environment variable instead of the key file.

## Reaching the server from another device

Prefer a private network over exposing a port publicly:

- **Tailscale or a VPN (recommended).** Bind the server with `ssync web --host 0.0.0.0` and connect over the private network. Tailscale can also issue a certificate trusted by iOS for your machine's `ts.net` name.
- **SSH tunnel.** From another computer: `ssh -L 8042:127.0.0.1:8042 your-machine`, then open `https://localhost:8042`.

Avoid exposing ssync directly to the internet. If you must, put it behind a reverse proxy with a trusted certificate, keep `SSYNC_REQUIRE_API_KEY=true`, and restrict source addresses.

## What is stored locally

| Location | Contents |
| --- | --- |
| `~/.config/ssync/config.yaml` | Hosts and settings. Reference passwords as `${ENV_VAR}` rather than writing them in. |
| `~/.config/ssync/.api_key` | The API key, readable only by you. |
| `~/.config/ssync/certs/` | The self-signed HTTPS certificate and key. |
| `~/.cache/ssync/` | Cached job metadata, scripts, and outputs. |

The iPhone app keeps its API key in the iOS Keychain, and its widgets never receive the key.
