from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ssync.models.cluster import Host, SlurmHost
from ssync.web.api.catalog import register_catalog_routes


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n")


class _FakeManager:
    def __init__(self, slurm_hosts):
        self.slurm_hosts = slurm_hosts


def _client(manager: _FakeManager, *, cache_ttl_seconds: float = 5.0) -> TestClient:
    app = FastAPI()
    register_catalog_routes(
        app,
        verify_api_key_dependency=lambda: True,
        get_slurm_manager=lambda: manager,
        cache_ttl_seconds=cache_ttl_seconds,
    )
    return TestClient(app)


@pytest.mark.unit
def test_launch_catalog_route_returns_static_profiles_and_safe_hosts(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".ssync").mkdir(parents=True)
    _write(
        repo / ".ssync/recipes/train.yaml",
        """
job_name: train
host_partition: gpu
sbatch:
  time: "24:00:00"
""",
    )
    _write(repo / ".ssync/partitions/gpu.yaml", "host: cluster\n")
    manager = _FakeManager(
        [
            SlurmHost(
                host=Host(hostname="cluster", username="alice", password="secret"),
                work_dir=Path("/work/alice"),
                scratch_dir=Path("/scratch/alice"),
            )
        ]
    )

    response = _client(manager).get(
        "/api/launch-catalog",
        params={"repo_root": str(repo), "include_user_config": "false"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["repo_root"] == str(repo)
    assert payload["include_user_config"] is False
    assert payload["hosts"][0]["hostname"] == "cluster"
    assert payload["hosts"][0]["requires_password"] is True
    assert payload["hosts"][0]["work_dir"] == "[CONFIGURED]"
    assert payload["recipes"][0]["id"] == "train"
    assert payload["recipes"][0]["sbatch"]["time"] == "24:00:00"
    assert "secret" not in str(payload)


@pytest.mark.unit
def test_launch_catalog_route_caches_and_force_refreshes(tmp_path):
    repo = tmp_path / "repo"
    recipe = repo / ".ssync/recipes/train.yaml"
    _write(recipe, "job_name: first\n")
    client = _client(_FakeManager([]), cache_ttl_seconds=60.0)

    first = client.get(
        "/api/launch-catalog",
        params={"repo_root": str(repo), "include_user_config": "false"},
    )
    _write(recipe, "job_name: second\n")
    cached = client.get(
        "/api/launch-catalog",
        params={"repo_root": str(repo), "include_user_config": "false"},
    )
    refreshed = client.get(
        "/api/launch-catalog",
        params={
            "repo_root": str(repo),
            "include_user_config": "false",
            "force_refresh": "true",
        },
    )

    assert first.status_code == 200
    assert first.json()["cached"] is False
    assert cached.status_code == 200
    assert cached.json()["cached"] is True
    assert cached.json()["recipes"][0]["label"] == "first"
    assert refreshed.status_code == 200
    assert refreshed.json()["cached"] is False
    assert refreshed.json()["recipes"][0]["label"] == "second"


@pytest.mark.unit
def test_launch_catalog_route_rejects_missing_repo_root(tmp_path):
    manager = _FakeManager([])
    response = _client(manager).get(
        "/api/launch-catalog",
        params={"repo_root": str(tmp_path / "missing")},
    )

    assert response.status_code == 404
