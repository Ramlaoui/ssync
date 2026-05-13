from pathlib import Path

import pytest

from ssync.recipes import RecipeError, find_repo_root, render_launch_recipe


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.mark.unit
def test_render_launch_recipe_composes_fragments(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".ssync").mkdir(parents=True)
    _write(
        repo / ".ssync/fragments/env/activate.sh", 'source "$VENV_PATH/bin/activate"\n'
    )
    _write(repo / ".ssync/fragments/prepare/offline.sh", "export HF_HUB_OFFLINE=1\n")
    _write(
        repo / ".ssync/fragments/run/train.sh",
        'echo "RUN_OUTPUT_DIR=${RUN_DIR}"\nsrun python train.py "$CONFIG"\n',
    )
    recipe = repo / "experiments/demo/launch/train.yaml"
    _write(
        recipe,
        """
host: entalpic
job_name: demo-train
source_dir: .
vars:
  CONFIG: experiments/demo/train
  RUN_DIR: /scratch/runs/demo
env:
  scripts:
    - .ssync/fragments/env/activate.sh
prepare:
  scripts:
    - script: .ssync/fragments/prepare/offline.sh
      vars:
        DATA_OFFLINE_MODE: "true"
run:
  script: .ssync/fragments/run/train.sh
  vars:
    VENV_PATH: /scratch/venvs/demo
sbatch:
  partition: gpu
  cpus: 16
  mem: 64
  time: 60
  gpus_per_node: 1
""",
    )

    rendered = render_launch_recipe(recipe)

    assert rendered.repo_root == repo
    assert rendered.source_dir == repo
    assert rendered.host == "entalpic"
    assert rendered.job_name == "demo-train"
    assert rendered.partition == "gpu"
    assert rendered.cpus == 16
    assert rendered.mem == 64
    assert rendered.time == 60
    assert rendered.gpus_per_node == 1
    assert "export CONFIG=experiments/demo/train" in rendered.script_content
    assert "export DATA_OFFLINE_MODE=true" in rendered.script_content
    assert 'source "$VENV_PATH/bin/activate"' in rendered.script_content
    assert 'echo "RUN_OUTPUT_DIR=${RUN_DIR}"' in rendered.script_content
    assert rendered.vars["VENV_PATH"] == "/scratch/venvs/demo"
    assert rendered.fragments == [
        repo / ".ssync/fragments/env/activate.sh",
        repo / ".ssync/fragments/prepare/offline.sh",
        repo / ".ssync/fragments/run/train.sh",
    ]


@pytest.mark.unit
def test_render_launch_recipe_defaults_source_dir_to_repo_root(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".ssync").mkdir(parents=True)
    _write(repo / ".ssync/fragments/run/train.sh", "python train.py\n")
    recipe = repo / "experiments/demo/launch/train.yaml"
    _write(
        recipe,
        """
run:
  script: .ssync/fragments/run/train.sh
""",
    )

    rendered = render_launch_recipe(recipe)

    assert rendered.source_dir == repo


@pytest.mark.unit
def test_render_launch_recipe_composes_workflow_profiles_and_recipe_overrides(
    tmp_path,
):
    repo = tmp_path / "repo"
    (repo / ".ssync").mkdir(parents=True)
    _write(
        repo / ".ssync/fragments/env/activate.sh", 'source "$VENV_PATH/bin/activate"\n'
    )
    _write(repo / ".ssync/fragments/prepare/offline.sh", "export OFFLINE=1\n")
    _write(repo / ".ssync/fragments/prepare/prefetch.sh", "python prefetch.py\n")
    _write(repo / ".ssync/fragments/run/train.sh", "python train.py\n")
    _write(
        repo / ".ssync/hosts/entalpic.yaml",
        """
host: entalpic
vars:
  SCRATCH_ROOT: /scratch/shared
  MAX_STEPS: "host-default"
""",
    )
    _write(
        repo / ".ssync/partitions/entalpic-gpu.yaml",
        """
host: entalpic
sbatch:
  partition: gpu
  cpus: 24
  gpus_per_node: 1
vars:
  MAX_STEPS: "partition-default"
  VENV_ROOT: /scratch/venvs
""",
    )
    _write(
        repo / ".ssync/envs/project-default.yaml",
        """
vars:
  VENV_PATH: /scratch/venvs/project
scripts:
  - .ssync/fragments/env/activate.sh
""",
    )
    _write(
        repo / ".ssync/workflows/train_gpu.yaml",
        """
host_partition: entalpic-gpu
env: project-default
prepare:
  scripts:
    - .ssync/fragments/prepare/offline.sh
run:
  script: .ssync/fragments/run/train.sh
vars:
  MAX_STEPS: "workflow-default"
sbatch:
  time: 120
""",
    )
    recipe = repo / "experiments/demo/launch/train.yaml"
    _write(
        recipe,
        """
extends: .ssync/workflows/train_gpu.yaml
job_name: concrete-run
vars:
  MAX_STEPS: "5000"
prepare:
  scripts:
    - .ssync/fragments/prepare/prefetch.sh
sbatch:
  time: 30
""",
    )

    rendered = render_launch_recipe(recipe)

    assert rendered.host == "entalpic"
    assert rendered.job_name == "concrete-run"
    assert rendered.partition == "gpu"
    assert rendered.cpus == 24
    assert rendered.gpus_per_node == 1
    assert rendered.time == 30
    assert rendered.vars["SCRATCH_ROOT"] == "/scratch/shared"
    assert rendered.vars["VENV_ROOT"] == "/scratch/venvs"
    assert rendered.vars["VENV_PATH"] == "/scratch/venvs/project"
    assert rendered.vars["MAX_STEPS"] == "5000"
    assert rendered.script_content.index(
        "export OFFLINE=1"
    ) < rendered.script_content.index("python prefetch.py")
    assert 'source "$VENV_PATH/bin/activate"' in rendered.script_content


@pytest.mark.unit
def test_render_launch_recipe_detects_workflow_cycles(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".ssync").mkdir(parents=True)
    _write(repo / ".ssync/workflows/a.yaml", "extends: .ssync/workflows/b.yaml\n")
    _write(repo / ".ssync/workflows/b.yaml", "extends: .ssync/workflows/a.yaml\n")
    recipe = repo / "experiments/demo/launch/train.yaml"
    _write(recipe, "extends: .ssync/workflows/a.yaml\n")

    with pytest.raises(RecipeError, match="cycle"):
        render_launch_recipe(recipe)


@pytest.mark.unit
def test_render_launch_recipe_requires_single_run_script(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".ssync").mkdir(parents=True)
    recipe = repo / ".ssync/workflows/bad.yaml"
    _write(recipe, "vars:\n  A: B\n")

    with pytest.raises(RecipeError, match="exactly one run script"):
        render_launch_recipe(recipe)


@pytest.mark.unit
def test_render_launch_recipe_quotes_vars_without_shell_expansion(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".ssync").mkdir(parents=True)
    _write(repo / ".ssync/fragments/run/train.sh", "python train.py\n")
    recipe = repo / "experiments/demo/launch/train.yaml"
    _write(
        recipe,
        """
vars:
  DANGEROUS: "$(touch /tmp/nope) ${SCRATCHDIR} `whoami`"
run:
  script: .ssync/fragments/run/train.sh
""",
    )

    rendered = render_launch_recipe(recipe)

    assert "export DANGEROUS='$(touch /tmp/nope) ${SCRATCHDIR} `whoami`'" in (
        rendered.script_content
    )


@pytest.mark.unit
def test_render_launch_recipe_rejects_unknown_fields(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".ssync").mkdir(parents=True)
    _write(repo / ".ssync/fragments/run/train.sh", "python train.py\n")
    recipe = repo / "experiments/demo/launch/train.yaml"
    _write(
        recipe,
        """
surprise: true
run:
  script: .ssync/fragments/run/train.sh
""",
    )

    with pytest.raises(RecipeError, match="Unknown launch recipe field"):
        render_launch_recipe(recipe)


@pytest.mark.unit
def test_render_launch_recipe_rejects_missing_source_dir(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".ssync").mkdir(parents=True)
    _write(repo / ".ssync/fragments/run/train.sh", "python train.py\n")
    recipe = repo / "experiments/demo/launch/train.yaml"
    _write(
        recipe,
        """
source_dir: missing
run:
  script: .ssync/fragments/run/train.sh
""",
    )

    with pytest.raises(RecipeError, match="source_dir does not exist"):
        render_launch_recipe(recipe)


@pytest.mark.unit
def test_render_launch_recipe_validates_sbatch_integer_fields(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".ssync").mkdir(parents=True)
    _write(repo / ".ssync/fragments/run/train.sh", "python train.py\n")
    recipe = repo / "experiments/demo/launch/train.yaml"
    _write(
        recipe,
        """
run:
  script: .ssync/fragments/run/train.sh
sbatch:
  cpus: "many"
""",
    )

    with pytest.raises(RecipeError, match="cpus"):
        render_launch_recipe(recipe)


@pytest.mark.unit
def test_find_repo_root_uses_nearest_ssync_directory(tmp_path):
    repo = tmp_path / "repo"
    nested = repo / "a/b"
    (repo / ".ssync").mkdir(parents=True)
    nested.mkdir(parents=True)

    assert find_repo_root(nested) == repo
