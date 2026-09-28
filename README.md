<p align="center">
  <img src="docs/assets/brand/mark.svg" alt="ssync" width="72" height="72">
</p>

<h1 align="center">ssync</h1>

<p align="center">
  <strong>Your Slurm jobs, on every cluster, in one place.</strong><br>
  Sync your code, submit jobs, stream their output, and relaunch them when they time out,<br>
  across all your HPC clusters, from your terminal, your browser, or your iPhone.
</p>

<p align="center">
  <a href="https://ssync.ramlaoui.org/"><strong>Documentation</strong></a> ·
  <a href="https://ssync.ramlaoui.org/en/latest/getting-started/quickstart/">Quickstart</a> ·
  <a href="https://ssync.ramlaoui.org/en/latest/guides/web-app/">Web app</a> ·
  <a href="https://ssync.ramlaoui.org/en/latest/guides/ios-app/">iPhone app</a>
</p>

<p align="center">
  <img src="docs/assets/screenshots/web-jobs.webp" alt="The ssync web app showing running, queued, and finished jobs across three clusters" width="900">
</p>

## Why ssync

Running experiments on several clusters usually means a dozen SSH sessions: `squeue` in one, `tail -f` in another, an `rsync` you hope skipped the virtualenv, and a 3 a.m. resubmit because a job hit its time limit one checkpoint short.

ssync runs on your own machine, talks to your clusters over SSH, and gives you one workspace for all of it. Nothing needs to be installed on the clusters.

- **Every cluster at a glance.** Running, queued, and finished jobs from all hosts in one view, with array jobs grouped and live updates.
- **Launch from your laptop.** `ssync launch` syncs your project (respecting `.gitignore`) and submits in one command, with login-node setup for clusters without internet on compute nodes.
- **Live output anywhere.** Stream stdout and stderr, search them, and read them from your phone.
- **Watchers that act for you.** Cancel diverging runs, capture metrics, or resubmit from the last checkpoint when a job times out.
- **Know where you are in the queue.** Queued jobs show their priority rank and the number of jobs ahead of them.
- **Reproducible.** Submitted scripts and launch manifests are cached, so you can inspect or relaunch a job after Slurm has forgotten it.
- **Where you work.** A CLI, a web app, a native iPhone app with Live Activities and widgets, and Raycast and VS Code extensions.

<p align="center">
  <img src="docs/assets/screenshots/ios-jobs.webp" alt="Jobs on iPhone" width="220">
  &nbsp;
  <img src="docs/assets/screenshots/ios-job-detail.webp" alt="A running job on iPhone" width="220">
  &nbsp;
  <img src="docs/assets/screenshots/ios-output-dark.webp" alt="Live output on iPhone" width="220">
</p>

## Quickstart

> [!WARNING]
> The `ssync` package on PyPI is an unrelated project. Install ssync from this repository.

```bash
# Install (the editable install includes the web app)
git clone https://github.com/Ramlaoui/ssync.git && cd ssync
uv tool install --editable .
```

Describe your clusters in `~/.config/ssync/config.yaml`, reusing aliases from `~/.ssh/config`:

```yaml
hosts:
  - hostname: my-cluster              # an alias from ~/.ssh/config
    work_dir: /home/your-username/work
    scratch_dir: /scratch/your-username
```

Then:

```bash
ssync status                              # every job on every cluster
ssync launch train.sh . --host my-cluster # sync this project and submit
ssync output 12345 --lines 50             # follow a job's output
ssync web                                 # open the web app at https://localhost:8042
```

The web app's first start builds the frontend, which needs Node.js 18 or newer. Read the [quickstart](https://ssync.ramlaoui.org/en/latest/getting-started/quickstart/) for a guided tour.

## Documentation

Full documentation lives at **[ssync.ramlaoui.org](https://ssync.ramlaoui.org/)**:

- [Installation](https://ssync.ramlaoui.org/en/latest/getting-started/installation/) and [configuration](https://ssync.ramlaoui.org/en/latest/getting-started/configuration/)
- [Web app](https://ssync.ramlaoui.org/en/latest/guides/web-app/) and [iPhone app](https://ssync.ramlaoui.org/en/latest/guides/ios-app/) tours
- [Launching jobs](https://ssync.ramlaoui.org/en/latest/guides/launching-jobs/), [watchers](https://ssync.ramlaoui.org/en/latest/guides/watchers/), and [launch recipes](https://ssync.ramlaoui.org/en/latest/guides/recipes/)
- [CLI](https://ssync.ramlaoui.org/en/latest/reference/cli/) and [API](https://ssync.ramlaoui.org/en/latest/reference/api/) references, and [security](https://ssync.ramlaoui.org/en/latest/reference/security/)

To preview the documentation locally:

```bash
uvx --from zensical==0.0.65 zensical serve
```

## Development

```bash
uv sync                          # Python environment
uv run pytest                    # backend tests

cd web-frontend
npm install
npm run dev                      # web app with hot reload
npm run test:run                 # frontend tests
```

The iPhone app lives in [`ios/`](ios/) and opens in Xcode 26. Documentation screenshots are generated from sample data: `web-frontend/scripts/docs-screenshots.mjs` for the web app and the `testDocumentationScreenshots` UI test for iOS.

## Contributing

Issues and pull requests are welcome.

## License

Apache 2.0. See [LICENSE](LICENSE).
