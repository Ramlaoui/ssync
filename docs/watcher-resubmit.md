# Watcher-Driven Resubmission

For a broader guide to watcher syntax, actions, timer mode, array-job behavior,
manual/static watchers, and attach-via-CLI usage, see
[`watchers.md`](watchers.md).

`ssync` watchers can resubmit a finished job by rewriting the original cached
submission script before sending it back through `sbatch`.

This is useful for long-running training jobs that should continue from the
latest checkpoint without maintaining a second hand-written "continue" script
for each hop.

## How It Works

1. The job emits a watcher-friendly marker line in stdout or stderr.
2. A watcher captures values from that line, such as the Hydra run directory.
3. The watcher triggers the built-in `resubmit` action.
4. Before submitting the new job, `ssync` interpolates captured variables into
   the cached script body.

The interpolation happens in `src/ssync/watchers/actions.py` and supports:

- `${var}`
- `${var:-default}`
- `${var:+word}`

The last form is the important one for chained resumes. It means:

- On the original shell launch, if `var` is unset, expand to an empty string.
- On watcher resubmit, if `var` was captured, replace the whole expression with
  `word`, after also expanding any `${var}` references inside `word`.

Example:

```bash
${resume_run_dir:+ +checkpoint.config_dir=${resume_run_dir}}
```

On the first launch, nothing is inserted.

On a resubmission where the watcher captured
`resume_run_dir=/scratch/me/outputs/2026-04-10/12-00-00`, `ssync` rewrites the
script to:

```bash
+checkpoint.config_dir=/scratch/me/outputs/2026-04-10/12-00-00
```

## Recommended Pattern

If the first launch should start from a known older run, but later resubmits
should continue from the newest run created by the current script, use the
default-value form:

```bash
+checkpoint.config_dir=${resume_run_dir:-/path/to/original/run}
```

That gives:

- first launch: `/path/to/original/run`
- watcher resubmit: the captured `resume_run_dir`

## Important Limitation

For script-body interpolation during `resubmit`, use named captures such as
`resume_run_dir`.

Do not rely on numeric-only captures like `$1` for rewriting the script body.
Numeric captures work well inside action parameters, but `resubmit` skips
numeric variable names when interpolating the cached script.

Good:

```yaml
captures: [resume_run_dir, step, max_steps]
```

Less useful for script rewriting:

```yaml
captures: []
```

with only `$1`, `$2`, ... references.

## Trigger On Job End

Watchers can also capture variables while the job is still running, but defer
their actions until the job reaches a terminal state.

This is useful for chained resubmission:

- match `HYDRA_OUTPUT_DIR=...` near the start of the run
- store `resume_run_dir`
- only run `resubmit()` once the job finishes

Example:

```bash
#WATCHER_BEGIN
# name: auto resubmit
# pattern: "HYDRA_OUTPUT_DIR=(.+)"
# captures: [resume_run_dir]
# trigger_on_job_end: true
# trigger_job_states: [completed, failed, timeout]
# actions:
#   - resubmit()
#WATCHER_END
```

With the launch command:

```bash
python main.py ... ${resume_run_dir:+ +checkpoint.config_dir=${resume_run_dir}}
```

In this mode, regex matches still update watcher variables during the run, but
the actions are deferred until the terminal-state branch executes.

If `trigger_job_states` is omitted, the default is:

```yaml
[completed, failed, timeout]
```

so `cancelled` jobs do not fire by default.

## Final Marker Pattern

The older workaround is still valid when you want a script-controlled explicit
end marker:

```bash
echo "SSYNC_RESUBMIT resume_run_dir=${run_dir} step=${saved_step} max_steps=${max_steps} exit_status=${run_status}"
```

## Practical Notes

- `resubmit` uses the cached original script content, not the currently running
  shell state.
- `cancel_previous` defaults to true. If the job has already finished, the
  cancel attempt is harmless and resubmission still proceeds.
- This pattern is best paired with a deliberate final marker line rather than a
  checkpoint-save regex that may appear many times during training.
