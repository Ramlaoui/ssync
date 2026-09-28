---
description: Use ssync from Raycast on macOS and from VS Code.
---

# Raycast and VS Code

Both extensions talk to the same ssync server as the web and iPhone apps, so start it first with `ssync web` or `ssync api`.

## Raycast

The Raycast extension brings your jobs to your keyboard on macOS.

| Command | What it does |
| --- | --- |
| **Jobs** | Browse jobs by host and state, search, pin, and open an inspector with output and the script. |
| **Job Summary** | A menu bar item with your pinned, running, and pending jobs. |
| **Hosts & Defaults** | Check partition capacity and edit each host's default Slurm settings. |
| **Watchers** | Browse watchers and their events; pause, resume, edit, or trigger one. |
| **Launch Job** | Edit a script, choose resources and source sync, review, and submit. |
| **Manage Connections** | Add and switch between ssync servers. |

Install it from the repository:

```bash
cd raycast-extension
npm ci
npm run dev
```

Then run **Manage Connections** in Raycast and enter your server URL (for example `https://localhost:8042`) and API key.

## VS Code

The VS Code extension adds commands to sync your workspace to a host, submit the current script, view logs, cancel a job, and start the ssync server. Build it from the `vscode-extension` folder in the repository.
