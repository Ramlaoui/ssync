from types import SimpleNamespace

import pytest
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from ssync.web.api.host_settings import register_host_settings_routes
from ssync.web.lifecycle import build_slurm_manager_getter


@pytest.fixture
def settings(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "# keep this comment\n"
        "hosts:\n"
        "  - hostname: atlas\n"
        "    password: secret-that-must-stay-local\n"
        "    work_dir: /work\n"
        "    scratch_dir: /scratch\n"
        "    slurm_defaults:\n"
        "      cpus: 4\n"
        "      account: old\n"
        "      python_env: source private-env\n"
        "  # another host\n"
        "  - hostname: boreal\n"
        "    work_dir: /other\n"
        "    scratch_dir: /other/scratch\n"
        "\n# preserve global settings\n"
        "cache:\n"
        "  enabled: true # keep inline comment\n"
    )
    config = SimpleNamespace(config_path=path, get_overlay_paths=lambda: [])
    app = FastAPI()
    register_host_settings_routes(
        app, verify_api_key_dependency=lambda: True, config=config
    )
    return TestClient(app), config


@pytest.mark.unit
def test_get_returns_only_editable_defaults(settings):
    client, _ = settings
    response = client.get("/api/hosts/atlas/settings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["slurm_defaults"] == {"cpus": 4, "account": "old"}
    assert len(payload["revision"]) == 64
    assert "secret-that" not in response.text
    assert "private-env" not in response.text
    assert "/work" not in response.text


@pytest.mark.unit
def test_update_preserves_unrelated_yaml_and_defaults(settings):
    client, config = settings
    before = config.config_path.read_text()
    revision = client.get("/api/hosts/atlas/settings").json()["revision"]
    response = client.put(
        "/api/hosts/atlas/settings",
        json={
            "revision": revision,
            "slurm_defaults": {"cpus": 12, "account": None, "gpus_per_node": 0},
        },
    )
    assert response.status_code == 200
    assert response.json()["slurm_defaults"] == {"cpus": 12, "gpus_per_node": 0}
    after = config.config_path.read_text()
    assert (
        after[: after.index("    slurm_defaults:")]
        == before[: before.index("    slurm_defaults:")]
    )
    assert (
        after[after.index("  # another host") :]
        == before[before.index("  # another host") :]
    )
    assert (
        yaml.safe_load(after)["hosts"][0]["slurm_defaults"]["python_env"]
        == "source private-env"
    )
    assert "secret-that-must-stay-local" in after


@pytest.mark.unit
def test_creates_defaults_without_rewriting_other_hosts(settings):
    client, config = settings
    revision = client.get("/api/hosts/boreal/settings").json()["revision"]
    response = client.put(
        "/api/hosts/boreal/settings",
        json={
            "revision": revision,
            "slurm_defaults": {"partition": "gpu", "time": "02:30:00"},
        },
    )
    assert response.status_code == 200
    assert (
        yaml.safe_load(config.config_path.read_text())["hosts"][1]["slurm_defaults"][
            "partition"
        ]
        == "gpu"
    )
    assert "# preserve global settings" in config.config_path.read_text()


@pytest.mark.unit
def test_refuses_stale_save(settings):
    client, config = settings
    revision = client.get("/api/hosts/atlas/settings").json()["revision"]
    config.config_path.write_text(
        config.config_path.read_text() + "# edit made elsewhere\n"
    )
    before = config.config_path.read_text()
    response = client.put(
        "/api/hosts/atlas/settings",
        json={"revision": revision, "slurm_defaults": {"cpus": 8}},
    )
    assert response.status_code == 409
    assert config.config_path.read_text() == before


@pytest.mark.unit
@pytest.mark.parametrize(
    "defaults",
    [
        {"password": "no"},
        {"cpus": 0},
        {"nodes": -1},
        {"cpus": 1.5},
        {"mem": True},
        {"partition": "gpu\ninjected"},
    ],
)
def test_invalid_fields_cannot_modify_config(settings, defaults):
    client, config = settings
    before = config.config_path.read_text()
    revision = client.get("/api/hosts/atlas/settings").json()["revision"]
    response = client.put(
        "/api/hosts/atlas/settings",
        json={"revision": revision, "slurm_defaults": defaults},
    )
    assert response.status_code == 422
    assert config.config_path.read_text() == before


@pytest.mark.unit
def test_unknown_host_is_not_created(settings):
    client, config = settings
    before = config.config_path.read_text()
    assert client.get("/api/hosts/missing/settings").status_code == 404
    assert config.config_path.read_text() == before


@pytest.mark.unit
def test_edits_effective_overlay_and_detects_overlay_changes(settings, tmp_path):
    client, config = settings
    overlay = tmp_path / "local.yaml"
    overlay.write_text(
        "hosts:\n  - hostname: atlas\n    slurm_defaults:\n      cpus: 16\n"
    )
    config.get_overlay_paths = lambda: [overlay]
    before = config.config_path.read_text()
    state = client.get("/api/hosts/atlas/settings").json()
    assert state["slurm_defaults"]["cpus"] == 16
    response = client.put(
        "/api/hosts/atlas/settings",
        json={"revision": state["revision"], "slurm_defaults": {"cpus": 32}},
    )
    assert response.status_code == 200
    assert (
        yaml.safe_load(overlay.read_text())["hosts"][0]["slurm_defaults"]["cpus"] == 32
    )
    assert config.config_path.read_text() == before


@pytest.mark.unit
def test_rejects_shared_yaml_without_altering_it(settings):
    client, config = settings
    config.config_path.write_text(
        "hosts:\n  - &shared\n    hostname: atlas\n    slurm_defaults: {cpus: 2}\n  - *shared\n"
    )
    before = config.config_path.read_text()
    assert client.get("/api/hosts/atlas/settings").status_code == 409
    assert config.config_path.read_text() == before


@pytest.mark.unit
def test_authentication_is_required(settings):
    _, config = settings

    def reject():
        raise HTTPException(401, "Unauthorized")

    app = FastAPI()
    register_host_settings_routes(app, verify_api_key_dependency=reject, config=config)
    client = TestClient(app)
    assert client.get("/api/hosts/atlas/settings").status_code == 401
    assert (
        client.put(
            "/api/hosts/atlas/settings",
            json={"revision": "a" * 64, "slurm_defaults": {}},
        ).status_code
        == 401
    )


@pytest.mark.unit
def test_manager_reloads_when_overlay_changes(tmp_path):
    base, overlay = tmp_path / "config.yaml", tmp_path / "local.yaml"
    base.write_text("base")
    overlay.write_text("first")
    config = SimpleNamespace(
        config_path=base,
        get_overlay_paths=lambda: [overlay],
        load_config=lambda: [overlay.read_text()],
        connection_settings={},
    )

    class Manager:
        def __init__(self, hosts, **kwargs):
            self.hosts, self.closed = hosts, False

        def close_connections(self):
            self.closed = True

    get_manager = build_slurm_manager_getter(config, Manager)
    first = get_manager()
    assert get_manager() is first
    overlay.write_text("second")
    second = get_manager()
    assert second is not first and first.closed
    assert second.hosts == ["second"]
