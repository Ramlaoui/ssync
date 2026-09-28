---
description: Connect a cluster, list your jobs, launch one, and open the web app in five minutes.
---

# Quickstart

This walks you from a fresh install to launching a job and watching it in the web app. It assumes ssync is [installed](installation.md) and that you can already `ssh` into your cluster.

## 1. Describe your cluster

ssync reads `~/.config/ssync/config.yaml`. The simplest entry reuses an alias from your `~/.ssh/config`, so keys, jump hosts, and usernames keep working as they do today:

```yaml title="~/.config/ssync/config.yaml"
hosts:
  - hostname: my-cluster              # an alias from ~/.ssh/config
    work_dir: /home/your-username/work     # where projects are synced
    scratch_dir: /scratch/your-username    # required: fast storage for caches
    slurm_defaults:                    # optional: this host's usual settings, shown in the apps
      partition: gpu
      account: my-project
      time: "02:00:00"
```

Add one entry per cluster. See [Configuration](configuration.md) for every option.

## 2. See your jobs everywhere

```bash
ssync status
```

ssync queries every configured host in parallel and prints one table. Useful variations:

```bash
ssync status --active-only       # only running and pending jobs
ssync status --since 1d          # include jobs that finished in the last day
ssync status --host my-cluster   # a single cluster
```

## 3. Launch a job from your laptop

Write a normal Slurm script:

```bash title="train.sh"
#!/bin/bash
#SBATCH --job-name=train
#SBATCH --gpus-per-node=1
#SBATCH --time=01:00:00

python train.py
```

Then sync your project and submit it in one step:

```bash
ssync launch train.sh . --host my-cluster
```

ssync copies the current directory to the cluster (skipping anything in `.gitignore`) and submits the script. Read [Launching jobs](../guides/launching-jobs.md) for login-node setup, overrides, and recipes.

## 4. Follow it

```bash
ssync output 12345 --lines 50    # last 50 lines of stdout
ssync output 12345 --stderr      # stderr instead
```

## 5. Open the web app

```bash
ssync web
```

This starts a local server at `https://localhost:8042` and opens your browser. The first start builds the web app, which takes a minute. Your browser warns about the self-signed certificate the first time; accept it to continue.

![The ssync web app](../assets/screenshots/web-jobs.webp){ .ss-shot }

## Where to go next

<div class="grid cards" markdown>

-   :material-monitor-dashboard: __[Tour the web app](../guides/web-app.md)__

    Inspect jobs, stream output, and relaunch from the browser.

-   :material-robot-outline: __[Automate with watchers](../guides/watchers.md)__

    Cancel bad runs or resubmit from a checkpoint automatically.

-   :material-cellphone: __[Get the iPhone app](../guides/ios-app.md)__

    Follow jobs from anywhere, with Live Activities and widgets.

-   :material-console: __[CLI reference](../reference/cli.md)__

    Every command and option.

</div>
