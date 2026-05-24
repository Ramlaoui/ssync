from pathlib import Path

import pytest

from ssync.catalog import discover_launch_catalog
from ssync.models.cluster import Host, SlurmDefaults, SlurmHost


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n")


@pytest.mark.unit
def test_discover_launch_catalog_summarizes_profiles_and_redacts_secrets(
    monkeypatch, tmp_path
):
    repo = tmp_path / "repo"
    user_config = tmp_path / "xdg" / "ssync"
    (repo / ".ssync").mkdir(parents=True)
    _write(
        repo / ".ssync/hosts/cluster.yaml",
        """
host: cluster
password: super-secret
key_file: /tmp/private-key.pem
vars:
  API_TOKEN: super-secret-token
""",
    )
    _write(
        repo / ".ssync/partitions/gpu.yaml",
        """
host: cluster
sbatch:
  partition: gpu
  cpus: 8
  time: "24:00:00"
""",
    )
    _write(
        repo / ".ssync/envs/project.yaml",
        """
vars:
  VENV_PATH: /scratch/venvs/project
scripts:
  - .ssync/fragments/env/activate.sh
""",
    )
    _write(repo / ".ssync/watchers/timeout.yaml", 'name: timeout\npattern: "TIMEOUT"\n')
    _write(
        repo / ".ssync/workflows/train.yaml",
        """
host_partition: gpu
env: project
watchers:
  - timeout
run:
  script: .ssync/fragments/run/train.sh
vars:
  MAX_STEPS: "100"
""",
    )
    _write(
        repo / ".ssync/recipes/train.yaml",
        """
extends: train
job_name: train
source_dir: .
vars:
  DATASET: demo
sbatch:
  time: "24:00:00"
""",
    )
    _write(
        user_config / "recipes/train.yaml",
        """
job_name: user-train
run:
  script: user.sh
""",
    )
    _write(user_config / "watchers/bad.yaml", "[")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    slurm_host = SlurmHost(
        host=Host(
            hostname="cluster",
            username="alice",
            password="configured-secret",
            key_file="/tmp/configured-key.pem",
        ),
        work_dir=Path("/work/alice"),
        scratch_dir=Path("/scratch/alice"),
        slurm_defaults=SlurmDefaults(partition="gpu", time="01:00:00"),
    )

    catalog = discover_launch_catalog(repo, slurm_hosts=[slurm_host])
    payload = catalog.to_dict()

    assert catalog.repo_root == str(repo)
    assert catalog.hosts[0].requires_password is True
    assert catalog.hosts[0].has_key_file is True
    assert catalog.hosts[0].work_dir == "[CONFIGURED]"
    assert catalog.hosts[0].slurm_defaults == {
        "partition": "gpu",
        "time": "01:00:00",
    }

    train_recipes = [recipe for recipe in catalog.recipes if recipe.id == "train"]
    assert len(train_recipes) == 2
    assert [recipe.source for recipe in train_recipes] == ["repo", "user"]
    assert train_recipes[0].active is True
    assert train_recipes[1].active is False
    assert train_recipes[1].shadowed_by == str(repo / ".ssync/recipes/train.yaml")
    assert train_recipes[0].sbatch["time"] == "24:00:00"

    env_profile = next(profile for profile in catalog.envs if profile.id == "project")
    assert env_profile.variable_names == ["VENV_PATH"]
    assert env_profile.scripts == [".ssync/fragments/env/activate.sh"]

    assert any("Invalid YAML" in warning.message for warning in catalog.warnings)
    serialized = str(payload)
    assert "super-secret" not in serialized
    assert "configured-secret" not in serialized
    assert "/tmp/private-key.pem" not in serialized
    assert "/tmp/configured-key.pem" not in serialized


@pytest.mark.unit
def test_discover_launch_catalog_can_exclude_user_config(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    user_config = tmp_path / "xdg" / "ssync"
    (repo / ".ssync").mkdir(parents=True)
    _write(repo / ".ssync/recipes/train.yaml", "job_name: repo\n")
    _write(user_config / "recipes/train.yaml", "job_name: user\n")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    catalog = discover_launch_catalog(repo, include_user_config=False)

    assert [root.source for root in catalog.roots] == ["repo"]
    assert [(recipe.id, recipe.source) for recipe in catalog.recipes] == [
        ("train", "repo")
    ]
