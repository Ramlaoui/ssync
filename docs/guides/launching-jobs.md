---
description: Sync your project and submit Slurm jobs from your laptop, with login-node setup, resource overrides, and embedded watchers.
---

# Launching jobs

`ssync launch` does three things in one command: it syncs your project to the cluster, prepares your script, and submits it with `sbatch`.

```bash
ssync launch train.sh ./my-project --host gpu-cluster
```

The project is copied to `<work_dir>/my-project` on the host, and the job runs from there.

## What gets synced

ssync uses `rsync` and respects your `.gitignore` files, so virtual environments, datasets, checkpoints, and build artifacts stay on your machine.

```bash
ssync launch train.sh . --host gpu-cluster --exclude "*.ckpt" --exclude "wandb/"
ssync launch train.sh . --host gpu-cluster --include "data/small/**"   # force-include ignored paths
ssync launch train.sh . --host gpu-cluster --no-gitignore             # copy everything
```

To sync without submitting, use `ssync sync ./my-project --host gpu-cluster`.

## Override resources from the command line

Options override the matching `#SBATCH` values for this launch:

```bash
ssync launch train.sh . --host gpu-cluster \
  --job-name ablation-3 --partition gpu --gpus-per-node 4 \
  --cpus 32 --mem 128 --time 480 --account my-project --qos high
```

`--mem` is in GB and `--time` in minutes. `--dependency afterok:12345` chains jobs. See the [CLI reference](../reference/cli.md#launching) for every option.

## Run setup on the login node first

Compute nodes often have no internet access. Put commands that need it (installing dependencies, downloading a model, loading modules) between `#LOGIN_SETUP_BEGIN` and `#LOGIN_SETUP_END`. ssync runs them on the login node before submitting and removes them from the batch script:

```bash title="train.sh"
#!/bin/bash
#SBATCH --job-name=train
#SBATCH --gpus-per-node=1
#SBATCH --time=02:00:00

#LOGIN_SETUP_BEGIN
uv sync --frozen
huggingface-cli download my-org/my-model --local-dir models/
#LOGIN_SETUP_END

source .venv/bin/activate
python train.py
```

If setup fails, the job is not submitted. Pass `--no-abort-on-setup-failure` to submit anyway. `--python-env "source .venv/bin/activate"` adds one more setup command without editing the script.

## Attach watchers in the script

Watchers can travel with the script. This one records the latest checkpoint path from the output and resubmits the job whenever it hits the time limit. [Resubmitting from checkpoints](watcher-resubmit.md) shows how to pass the captured path back into the script so each run continues where the last one stopped:

```bash
#WATCHER_BEGIN
# name: Resume from checkpoint
# pattern: "checkpoint saved: (\S+)"
# captures: [checkpoint]
# trigger_on_job_end: true
# trigger_job_states: [timeout]
# actions:
#   - resubmit()
#WATCHER_END
```

ssync extracts watcher blocks at submission and starts them automatically. See [Watchers](watchers.md) and [Resubmitting from checkpoints](watcher-resubmit.md).

## Reusable launch recipes

For projects that launch the same kinds of jobs on several clusters, keep host profiles, environments, and run fragments in a `.ssync/` folder and launch a recipe by name:

```bash
ssync launch-recipe train --dry-run    # print the rendered script
ssync launch-recipe train              # sync and submit
ssync manifest 12345                   # what exactly was submitted
```

Read [Launch recipes](recipes.md) for the layout and override options.

## From the apps

The [web app](web-app.md#launch) and the [iPhone app](ios-app.md#launch-from-your-phone) can launch jobs too, and can relaunch any past job from its stored script. Both show a review of the exact request before anything is submitted.
