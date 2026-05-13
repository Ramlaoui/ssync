# Repo-Local Launch Recipes

`ssync launch-recipe` renders a project-owned YAML recipe into a concrete batch
script, syncs the selected source directory, submits it through the existing
launch API, and stores the resolved manifest for later inspection or watcher
resubmits.

Use regular `ssync launch SCRIPT SOURCE_DIR --host HOST` for handwritten shell
scripts. Use `ssync launch-recipe RECIPE.yaml` when the project has a `.ssync/`
control-plane folder.

## Layout

```text
repo/
  .ssync/
    hosts/cluster.yaml
    partitions/cluster-gpu.yaml
    envs/project.yaml
    workflows/train.yaml
    fragments/
      env/activate.sh
      prepare/offline.sh
      run/train.sh
  experiments/demo/launch/train.yaml
```

YAML composes reusable pieces. Executable project logic stays in `.sh`
fragments so Bash remains shellcheckable and easy to patch.

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
    - .ssync/fragments/prepare/offline.sh
run:
  script: .ssync/fragments/run/train.sh
vars:
  MAX_STEPS: "100000"
```

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

```yaml
# .ssync/envs/project.yaml
vars:
  VENV_PATH: "${VENV_ROOT}/project"
scripts:
  - .ssync/fragments/env/activate.sh
```

```bash
# .ssync/fragments/env/activate.sh
source "${VENV_PATH}/bin/activate"
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
```

The manifest records the recipe path, repo root, source directory, selected
profiles, fragments, resolved variables, rendered script, script hash, and
sbatch metadata. Watcher-driven resubmits use this frozen manifest by default
so automatic relaunches do not silently pick up unrelated local repo changes.

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
```

`--var` values are exported as shell-safe strings. `--set` currently accepts
`sbatch.*` fields only, including `partition`, `account`, `constraint`, `gres`,
`output`, `error`, `cpus`, `mem`, `time`, `nodes`, `ntasks_per_node`, and
`gpus_per_node`.

## Validation

`launch-recipe` validates before submit:

- unknown top-level recipe fields fail fast
- `source_dir` must exist and be a directory
- `sbatch` must be a mapping
- integer sbatch fields such as `cpus`, `mem`, `time`, `nodes`,
  `ntasks_per_node`, and `gpus_per_node` must be positive integers
- exactly one `run` script must resolve
- referenced fragments must exist
