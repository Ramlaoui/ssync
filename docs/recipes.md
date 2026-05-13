# Repo-Local Launch Recipes

`ssync launch-recipe` renders a project-owned YAML recipe into a concrete batch
script, syncs the selected source directory, submits it through the existing
launch API, and stores the resolved manifest for later inspection or watcher
resubmits.

Use regular `ssync launch SCRIPT SOURCE_DIR --host HOST` for handwritten shell
scripts. Use `ssync launch-recipe RECIPE.yaml`, or a bare recipe name such as
`ssync launch-recipe train`, when the project has a `.ssync/` control-plane
folder.

## Layout

```text
repo/
  .ssync/
    hosts/cluster.yaml
    partitions/cluster-gpu.yaml
    envs/project.yaml
    watchers/timeout_resume.yaml
    workflows/train.yaml
    recipes/train.yaml
    fragments/
      env/activate.sh
      env/offline.sh
      login/prefetch_dataset.sh
      run/train.sh
  experiments/demo/launch/train.yaml
```

YAML composes reusable pieces. Executable project logic stays in `.sh`
fragments so Bash remains shellcheckable and easy to patch.

Named profiles are resolved from the project first, then from the user ssync
config directory:

```text
repo/.ssync/
~/.config/ssync/
```

For example, `env: project` checks `repo/.ssync/envs/project.yaml` before
falling back to `~/.config/ssync/envs/project.yaml`. The same lookup applies to
`hosts`, `partitions`, `watchers`, and `workflows`. Bare recipe names are also
resolved through `recipes/`, so `ssync launch-recipe train` checks
`repo/.ssync/recipes/train.yaml` before `~/.config/ssync/recipes/train.yaml`.
Explicit paths keep their existing path behavior.

## Recipe

```yaml
extends: .ssync/workflows/train.yaml
job_name: demo-train
source_dir: .
vars:
  CONFIG: experiments/demo/train
  EXPERIMENT_NAME: demo-train
sbatch:
  time: 60
```

## Workflow

```yaml
host_partition: cluster-gpu
env: project
prepare:
  scripts:
    - .ssync/fragments/login/prefetch_dataset.sh
run:
  script: .ssync/fragments/run/train.sh
vars:
  MAX_STEPS: "100000"
watchers:
  - timeout_resume
```

## Watcher Policies

Reusable watcher policies live in `.ssync/watchers/` and are rendered into
ordinary `#WATCHER_BEGIN` blocks before submit, so they reuse the existing
watcher extraction and daemon path.

```yaml
# .ssync/watchers/timeout_resume.yaml
name: timeout_resume
pattern: "RUN_OUTPUT_DIR=(.+)"
captures:
  - resume_run_dir
trigger_on_job_end: true
trigger_job_states:
  - timeout
remaining_resubmits: 2
actions:
  - resubmit()
```

The policy above standardizes the resume contract: the run fragment prints
`RUN_OUTPUT_DIR=...`, the watcher captures it as `resume_run_dir`, and a
watcher-driven resubmit injects that capture into the frozen manifest relaunch.

## Host and Partition Profiles

```yaml
# .ssync/hosts/cluster.yaml
host: cluster
vars:
  SCRATCH_ROOT: "${SCRATCHDIR}"
  HAS_COMPUTE_INTERNET: "false"
```

```yaml
# .ssync/partitions/cluster-gpu.yaml
host: cluster
sbatch:
  partition: gpu
  cpus: 24
  mem: 64
  gpus_per_node: 1
vars:
  VENV_ROOT: "${SCRATCHDIR}/venvs"
```

Remote cluster variables such as `${SCRATCHDIR}` are preserved for Bash on the
cluster. `ssync` only renders recipe variables into shell-safe `export` lines;
it does not eagerly expand remote runtime variables.

## Environment and Fragments

`prepare` is pre-submit preparation. Its fragments are rendered inside
`#LOGIN_SETUP_BEGIN/#LOGIN_SETUP_END`, so existing ssync launch handling runs
them on the login node before `sbatch`. Use this for dataset prefetching,
remote path creation, and checks that cannot run on compute nodes.

`env` is optional. It is a reusable compute-side setup profile for commands
that must run inside the Slurm job before `run`, such as activating a virtual
environment, exporting offline/cache variables, or loading modules. Small
projects can skip `env` and put those commands directly in the run fragment.

```yaml
# .ssync/envs/project.yaml
vars:
  VENV_PATH: "${VENV_ROOT}/project"
scripts:
  - .ssync/fragments/env/activate.sh
  - .ssync/fragments/env/offline.sh
```

```bash
# .ssync/fragments/env/activate.sh
source "${VENV_PATH}/bin/activate"
```

```bash
# .ssync/fragments/login/prefetch_dataset.sh
if [ "${PREFETCH_DATASET:-false}" = "true" ]; then
  uv run --no-sync python tools/prefetch_dataset.py "$CONFIG"
fi
```

```bash
# .ssync/fragments/run/train.sh
RUN_STAMP="${RUN_STAMP:-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="${PWD}/run-outputs/${EXPERIMENT_NAME}/${RUN_STAMP}"
echo "RUN_OUTPUT_DIR=${RUN_DIR}"

srun python main.py \
  "$CONFIG" \
  run.dir="${RUN_DIR}" \
  ${resume_run_dir:+ +checkpoint.config_dir=${resume_run_dir}}
```

The run fragment is project-specific. `ssync` does not parse model names,
dataset names, config framework overrides, or Python entrypoints.

## Dry Run and Manifests

```bash
ssync launch-recipe experiments/demo/launch/train.yaml --dry-run
ssync launch-recipe experiments/demo/launch/train.yaml --dry-run --json
```

Dry-run output includes the resolved source directory, submit host, sbatch
fields, fragments, variables, script hash, and rendered script.

Submitted recipe jobs store a manifest in the local ssync cache:

```bash
ssync manifest 12345 --host cluster
ssync manifest 12345 --host cluster --json
ssync rerender 12345 --host cluster
ssync rerender 12345 --host cluster --from-current-repo
```

The manifest records the recipe path, repo root, source directory, selected
profiles, fragments, resolved variables, rendered script, script hash, and
sbatch metadata. Watcher-driven resubmits use this frozen manifest by default
so automatic relaunches do not silently pick up unrelated local repo changes.
`ssync rerender` follows the same rule: it shows the frozen script unless
`--from-current-repo` is passed explicitly.

## Overrides

Recipe overrides are schema-aware. They modify the resolved recipe before
rendering and are written into the manifest.

```bash
ssync launch-recipe experiments/demo/launch/train.yaml \
  --workflow .ssync/workflows/debug.yaml

ssync launch-recipe experiments/demo/launch/train.yaml \
  --host-partition cluster-debug-gpu \
  --env project-debug

ssync launch-recipe experiments/demo/launch/train.yaml \
  --var MAX_STEPS=5000 \
  --set sbatch.time=30 \
  --set sbatch.partition=debug

ssync launch-recipe experiments/demo/launch/train.yaml \
  --add-watcher timeout_resume \
  --remove-watcher tracker_sync
```

`--var` values are exported as shell-safe strings. `--set` currently accepts
`sbatch.*` fields only, including `partition`, `account`, `constraint`, `gres`,
`output`, `error`, `cpus`, `mem`, `time`, `nodes`, `ntasks_per_node`, and
`gpus_per_node`.

Watcher list edits accept policy names, policy paths, or path stems.

## Validation

`launch-recipe` validates before submit:

- unknown top-level recipe fields fail fast
- `source_dir` must exist and be a directory
- `sbatch` must be a mapping
- integer sbatch fields such as `cpus`, `mem`, `time`, `nodes`,
  `ntasks_per_node`, and `gpus_per_node` must be positive integers
- exactly one `run` script must resolve
- referenced fragments must exist
