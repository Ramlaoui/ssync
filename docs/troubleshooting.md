---
description: Fix common ssync problems with SSH, syncing, output, the web app, and the iPhone app.
---

# Troubleshooting

## Connecting to clusters

**ssync can't reach a host.** Check that plain SSH works with the same name ssync uses:

```bash
ssh my-cluster
```

If that asks for a password every time, set up keys (`ssh-copy-id my-cluster`), or add a `ControlMaster` section to `~/.ssh/config` so one login is reused. Slow or flaky networks may need a higher `connections.connect_timeout` in the [configuration](getting-started/configuration.md#connections).

**"Missing required field in host config".** Every host needs `hostname`, `work_dir`, and `scratch_dir`.

## Syncing

**Syncing is slow or copies too much.** Make sure large folders (datasets, checkpoints, virtual environments) are in `.gitignore`, or pass `--exclude`. `--max-depth` controls how deep ssync looks for nested `.gitignore` files.

**A file you need is ignored.** Force it in with `--include "path/**"`.

## Output

**No output yet.** Slurm only creates output files once the job starts. For queued jobs, check the reason and queue position in the web app or with `ssync status`.

**Output is from the wrong place.** ssync reads the paths Slurm reports for the job. If your script sets `--output` or `--error`, make sure those directories exist on the cluster.

## Web app

**The browser warns about the certificate.** The server uses a self-signed certificate. Accept it once, or use `ssync web --no-https` on a trusted machine.

**`ssync web` says the frontend is missing.** The web app needs the full install (a clone of the repository) and Node.js 18 or newer for its first build. See [Installation](getting-started/installation.md). To build manually: `cd web-frontend && npm install && npm run build`.

**Is the server running?** `ssync web --status`, and `ssync api --logs` for recent logs.

## iPhone app

**The app can't connect.** Your phone must be able to reach the server: by default `ssync web` listens only on your computer. See [Connect to your server](guides/ios-app.md#connect-to-your-server).

**"The certificate is not trusted".** iOS rejects self-signed certificates. Trust the certificate authority on the phone, or use a certificate issued for your hostname (for example from Tailscale).

**Widgets look out of date.** Widgets show what the app last saw. Open the app to refresh them.
