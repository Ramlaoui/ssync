# Watchers Guide

`ssync` watchers monitor job output, capture values with regexes, and run actions
when patterns match or when the job reaches a terminal state.

They are useful for:

- detecting failures early and cancelling bad runs
- capturing values such as output directories, loss values, or checkpoint paths
- resubmitting a job with captured values interpolated back into the script
- running lightweight follow-up commands when a job prints a marker
- monitoring array jobs with one watcher definition on the parent submission

This document covers the current implementation, with examples that match what
the code supports today.

## Mental Model

A watcher has:

- a regex `pattern`
- optional named `captures`
- an optional boolean `condition`
- one or more `actions`
- a polling interval

The watcher reads new job output, applies the regex, stores captured values, and
then either:

- runs actions immediately when the pattern matches, or
- stores the values and waits until the job ends if `trigger_on_job_end: true`

## How To Create Watchers

There are three practical ways to use watchers.

### 1. Embed watchers in the submitted script

This is the best option when the watcher is part of the job definition itself.

`ssync launch` and the submission flow extract watcher blocks from the script,
submit the job, then start the watcher automatically.

Block form:

```bash
#WATCHER_BEGIN
# name: error monitor
# pattern: "ERROR|Exception"
# interval: 30
# actions:
#   - cancel_job()
#WATCHER_END
```

Inline shorthand:

```bash
#WATCHER name="error monitor" pattern="ERROR|Exception" interval=30 action=cancel_job
```

### 2. Attach watchers to an existing running or pending job

Use this when the job is already in the queue and you want to add monitoring
after submission.

Simple CLI example:

```bash
ssync watchers attach 12345 --host cluster1 --pattern "ERROR|Exception" --action cancel_job
```

For anything non-trivial, use `--watcher-file` with JSON.

### 3. Create a static watcher for a finished job and trigger it manually

This is mainly useful from the web/API side when you want to test a pattern on
cached output from a completed job.

Static watchers do not run continuously. They run only when manually triggered.

## Supported Fields

Watchers are not configured through one single surface today. Some fields are
available in script syntax, while others are currently API/UI-only.

| Field | Script block | Inline `#WATCHER` | API / attached watcher |
| --- | --- | --- | --- |
| `name` | yes | yes | yes |
| `pattern` | yes | yes | yes, unless `trigger_on_job_end=true` |
| `interval` / `interval_seconds` | yes | yes | yes |
| `captures` | yes | yes | yes |
| `condition` | yes | yes | yes |
| `actions` | yes | single `action=` | yes |
| `trigger_on_job_end` | yes | yes | yes |
| `trigger_job_states` | yes | yes | yes |
| `timer_mode_enabled` / `timer_mode` | yes | no | yes |
| `timer_interval_seconds` / `timer_interval` | yes | no | yes |
| `output_type` (`stdout` / `stderr` / `both`) | no | no | yes |
| `max_triggers` | no | no | yes |
| per-action `condition` | no | no | partially via API/UI |

## Variables, Captures, and Conditions

When a regex matches:

- named captures are stored under the names from `captures`
- positional captures are also stored as `"1"`, `"2"`, ... so `$1`, `$2` work
- the full matched text is available as `$0` inside action parameters

Example:

```bash
#WATCHER_BEGIN
# name: loss tracker
# pattern: "Loss: ([0-9.]+), Step: ([0-9]+)"
# captures: [loss, step]
# condition: float(loss) > 5.0
# actions:
#   - log_event(message="loss crossed threshold")
#WATCHER_END
```

With output:

```text
Loss: 5.73, Step: 1200
```

the watcher stores:

- `loss=5.73`
- `step=1200`
- `"1"=5.73`
- `"2"=1200`

Conditions are Python expressions evaluated with a small safe context. The
useful built-ins are:

- `float`
- `int`
- `str`
- `len`
- `abs`
- `min`
- `max`

Typical conditions:

```python
float(loss) > 5.0
int(step) >= 1000
job_end_state == "failed"
```

## Actions

These are the built-in action types currently implemented.

### `log_event`

Logs a watcher event and records it in the watcher event history.

Example:

```bash
log_event(message="checkpoint saved")
```

### `cancel_job`

Runs `scancel` on the watched job.

Example:

```bash
cancel_job(reason="NaN detected")
```

### `resubmit`

Resubmits the cached original script for the job. This is the main building
block for chained relaunch.

Useful parameters:

- `cancel_previous=true|false`
- `modifications=...` via API only for now

### `notify_email`

Sends email through the remote host if `mail` is available there.

Parameters:

- `to`
- `subject`
- `message`

Example:

```bash
notify_email(to="me@example.com", subject="training alert")
```

### `run_command`

Runs a limited allowlisted shell command on the remote host.

Good for:

- writing marker files
- copying small artifacts
- running `uv run ...` helpers in the job directory

Important: this is intentionally restricted. It is not a general arbitrary
remote shell escape hatch.

### `store_metric`

Stores a value in the watcher cache/database.

Example via API-style watcher:

```json
{
  "type": "store_metric",
  "params": {
    "name": "loss",
    "variable": "loss"
  }
}
```

### `notify_slack`

This action exists, but the current implementation only logs the notification.
Do not rely on it yet as a real Slack delivery mechanism.

## Example 1: Cancel A Job When It Prints An Error

```bash
#!/bin/bash
#SBATCH --job-name=watcher-demo

#WATCHER_BEGIN
# name: error monitor
# pattern: "ERROR|Exception|Traceback"
# interval: 20
# actions:
#   - cancel_job(reason="error detected in output")
#WATCHER_END

python train.py
```

Use this when:

- a long training job should stop as soon as a fatal error appears
- you do not want to wait for walltime expiration or external monitoring

## Example 2: Capture A Value And Use It In An Action

```bash
#!/bin/bash
#SBATCH --job-name=capture-demo

#WATCHER_BEGIN
# name: checkpoint logger
# pattern: "CHECKPOINT path=(.+) step=([0-9]+)"
# interval: 30
# captures: [checkpoint_path, step]
# actions:
#   - log_event(message="checkpoint at $checkpoint_path step $step")
#WATCHER_END

python train.py
```

If the job prints:

```text
CHECKPOINT path=/scratch/run-42/ckpt.pt step=900
```

the message becomes:

```text
checkpoint at /scratch/run-42/ckpt.pt step 900
```

## Example 3: Resubmit On Job End Using A Captured Hydra Output Directory

This is the most important relaunch pattern.

Script:

```bash
#!/bin/bash
#SBATCH --job-name=hydra-train

#WATCHER_BEGIN
# name: auto resubmit
# pattern: "HYDRA_OUTPUT_DIR=(.+)"
# captures: [resume_run_dir]
# trigger_on_job_end: true
# trigger_job_states: [completed, failed, timeout]
# actions:
#   - resubmit()
#WATCHER_END

python train.py \
  experiment=my_run \
  ${resume_run_dir:+ +checkpoint.config_dir=${resume_run_dir}}
```

What happens:

1. Early in the run, the job prints `HYDRA_OUTPUT_DIR=/scratch/...`.
2. The watcher captures `resume_run_dir`.
3. The watcher does nothing immediately because `trigger_on_job_end: true`.
4. When the job reaches `completed`, `failed`, or `timeout`, `resubmit()` runs.
5. `ssync` rewrites the cached script body, replacing:

```bash
${resume_run_dir:+ +checkpoint.config_dir=${resume_run_dir}}
```

with:

```bash
+checkpoint.config_dir=/scratch/...
```

For more detail on script interpolation, see
[`watcher-resubmit.md`](watcher-resubmit.md).

## Example 4: Timer Mode After The First Match

Timer mode is useful when one pattern establishes context, then you want to run
the same action repeatedly with the captured variables.

```bash
#!/bin/bash
#SBATCH --job-name=timer-demo

#WATCHER_BEGIN
# name: follow run dir
# pattern: "RUN_DIR=(.+)"
# captures: [run_dir]
# timer_mode: true
# timer_interval: 60
# actions:
#   - run_command(command="uv run --no-sync python tools/poll_metrics.py --run-dir $run_dir")
#WATCHER_END

python train.py
```

Behavior:

1. The watcher waits until `RUN_DIR=...` appears.
2. It captures `run_dir`.
3. It switches into timer mode.
4. Every 60 seconds it executes the action again using the stored variables.

## Example 5: Array Jobs

If the submitted script contains watchers and also uses `#SBATCH --array=...`,
`ssync` treats the watcher definitions as array templates.

Example:

```bash
#!/bin/bash
#SBATCH --job-name=array-demo
#SBATCH --array=0-7

#WATCHER_BEGIN
# name: array failure monitor
# pattern: "ERROR|Traceback"
# interval: 20
# actions:
#   - cancel_job(reason="array task failed")
#WATCHER_END

python train.py --task-id "$SLURM_ARRAY_TASK_ID"
```

What happens:

1. The parent submission gets a template watcher.
2. While the array is active, `ssync` discovers task jobs such as `12345_0`.
3. It spawns child watchers for those task jobs automatically.

This lets you define the watcher once at the array submission level.

## Example 6: Attach A Watcher To An Existing Job

Simple one-liner:

```bash
ssync watchers attach 12345 --host cluster1 --pattern "ERROR|Exception" --action cancel_job
```

For more control, use JSON:

```json
[
  {
    "name": "stderr error monitor",
    "pattern": "ERROR|Exception|Traceback",
    "interval_seconds": 20,
    "output_type": "stderr",
    "actions": [
      {
        "type": "cancel_job",
        "params": {
          "reason": "error detected in stderr"
        }
      }
    ]
  }
]
```

and attach it with:

```bash
ssync watchers attach 12345 --host cluster1 --watcher-file watchers.json
```

This path is useful for:

- attaching to a long-running job that was submitted without embedded watchers
- choosing `stderr` or `both`
- using fields that script syntax does not currently expose

## Example 7: Pattern-Less Job-End Watcher Via JSON

The backend supports job-end watchers that have no regex at all.

Example watcher file:

```json
[
  {
    "name": "notify on terminal state",
    "trigger_on_job_end": true,
    "trigger_job_states": ["failed", "timeout"],
    "actions": [
      {
        "type": "notify_email",
        "params": {
          "to": "me@example.com",
          "subject": "job ended badly",
          "message": "job $JOB_ID ended with state $job_end_state on $HOSTNAME"
        }
      }
    ]
  }
]
```

This works well through JSON/API and in script blocks.

## Manual Triggering And Static Watchers

Useful commands:

```bash
ssync watchers list
ssync watchers events --watcher-id 12
ssync watchers trigger 12
ssync watchers pause 12
ssync watchers resume 12
```

Manual trigger is especially useful for:

- testing a regex against existing cached output
- running a static watcher on a completed job
- kicking off timer-mode actions immediately

## What Watchers Are Not

Watchers are not currently a general dependency-job orchestrator.

In particular:

- there is no first-class watcher action that submits a new job with Slurm
  `--dependency=...`
- `resubmit()` replays the cached original script with plain `sbatch`
- `run_command` is restricted and does not currently serve as a generic
  `sbatch --dependency` escape hatch

If you need a real DAG or dependency pipeline, you currently need a separate
workflow layer or explicit submission logic outside the watcher action system.

## Current Limitations And Gotchas

- For script-body interpolation during `resubmit`, prefer named captures such as
  `resume_run_dir`. Positional-only captures like `$1` are not used when
  rewriting the cached script body.
- If `trigger_job_states` is omitted, the default is
  `[completed, failed, timeout]`. `cancelled` does not trigger by default.
- Inline `#WATCHER ...` syntax is convenient, but it exposes fewer fields than
  block syntax. Use block syntax for timer mode or more complex watchers.
- `output_type` and `max_triggers` are currently API/attach-level features, not
  script-parser features.
- `notify_slack` is not a full Slack integration yet.
- `pause_watcher` appears in some UI surfaces, but it is not a watcher action to
  rely on yet.
- The current web UI is still pattern-first. Pattern-less job-end watchers are
  better defined in scripts or JSON/API for now.

## Recommended Starting Point

If you want one pattern to copy and adapt, start with this:

```bash
#!/bin/bash
#SBATCH --job-name=training

#WATCHER_BEGIN
# name: auto relaunch
# pattern: "HYDRA_OUTPUT_DIR=(.+)"
# captures: [resume_run_dir]
# trigger_on_job_end: true
# trigger_job_states: [completed, failed, timeout]
# actions:
#   - resubmit()
#WATCHER_END

python train.py \
  ${resume_run_dir:+ +checkpoint.config_dir=${resume_run_dir}}
```

Then add:

- `condition` when only some matches should count
- timer mode if you want repeated follow-up actions
- JSON/API attachment when you need `stderr`, `both`, or other API-only fields
