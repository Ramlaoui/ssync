from pathlib import Path

import pytest

from ssync.models.cluster import Host
from ssync.utils.config import Config, ConfigError, get_user_config_dir


def _write_config(path: Path, body: str) -> None:
    path.write_text(body)


@pytest.mark.unit
def test_config_uses_ssync_config_path(monkeypatch, tmp_path):
    config_path = tmp_path / "ssync.yaml"
    _write_config(
        config_path,
        """
hosts:
  - hostname: cluster.example.com
    work_dir: /work/user
    scratch_dir: /scratch/user
""",
    )

    monkeypatch.setenv("SSYNC_CONFIG_PATH", str(config_path))

    cfg = Config()

    assert cfg.config_path == config_path
    assert cfg.config[0].host.hostname == "cluster.example.com"


@pytest.mark.unit
def test_user_config_dir_uses_canonical_xdg_path(monkeypatch, tmp_path):
    xdg_home = tmp_path / "xdg"

    monkeypatch.delenv("SSYNC_CONFIG_PATH", raising=False)
    monkeypatch.delenv("SSYNC_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))

    assert get_user_config_dir() == xdg_home / "ssync"


@pytest.mark.unit
def test_config_discovers_repo_local_ssync_config(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    nested = repo / "experiments" / "demo"
    config_dir = repo / ".ssync"
    nested.mkdir(parents=True)
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    _write_config(
        config_path,
        """
hosts:
  - hostname: project-cluster.example.com
    work_dir: /work/project
    scratch_dir: /scratch/project
""",
    )

    monkeypatch.delenv("SSYNC_CONFIG_PATH", raising=False)
    monkeypatch.delenv("SSYNC_CONFIG", raising=False)
    monkeypatch.chdir(nested)

    cfg = Config()

    assert cfg.config_path == config_path
    assert cfg.config[0].host.hostname == "project-cluster.example.com"


@pytest.mark.unit
def test_config_merges_repo_local_user_overlay(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    config_dir = repo / ".ssync"
    config_dir.mkdir(parents=True)
    _write_config(
        config_dir / "config.yaml",
        """
hosts:
  - hostname: project-cluster.example.com
    work_dir: /work/shared
    scratch_dir: /scratch/shared
api:
  host: 127.0.0.1
  port: 8000
cache:
  enabled: true
""",
    )
    _write_config(
        repo / ".ssync.local.yaml",
        """
api:
  port: 9000
cache:
  max_age_days: 3
""",
    )

    monkeypatch.delenv("SSYNC_CONFIG_PATH", raising=False)
    monkeypatch.delenv("SSYNC_CONFIG", raising=False)
    monkeypatch.chdir(repo)

    cfg = Config()

    assert cfg.api_settings.host == "127.0.0.1"
    assert cfg.api_settings.port == 9000
    assert cfg.cache_settings.enabled is True
    assert cfg.cache_settings.max_age_days == 3


@pytest.mark.unit
def test_explicit_repo_config_path_still_applies_repo_local_overlay(
    monkeypatch, tmp_path
):
    repo = tmp_path / "repo"
    config_dir = repo / ".ssync"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    _write_config(
        config_path,
        """
hosts:
  - hostname: project-cluster.example.com
    work_dir: /work/shared
    scratch_dir: /scratch/shared
api:
  port: 8000
""",
    )
    _write_config(
        repo / ".ssync.local.yaml",
        """
api:
  port: 9000
""",
    )

    monkeypatch.setenv("SSYNC_CONFIG_PATH", str(config_path))
    monkeypatch.chdir(repo)

    cfg = Config()

    assert cfg.api_settings.port == 9000
    assert cfg.overlay_paths == [repo / ".ssync.local.yaml"]


@pytest.mark.unit
def test_config_preserves_remote_shell_variables(tmp_path):
    config_path = tmp_path / "ssync.yaml"
    _write_config(
        config_path,
        """
hosts:
  - hostname: cluster.example.com
    work_dir: /remote/work/${USER}/project
    scratch_dir: ${SCRATCHDIR}
    slurm_defaults:
      python_env: source ${SCRATCHDIR}/venvs/project/bin/activate
      output_pattern: logs/${SLURM_JOB_ID}.out
""",
    )

    cfg = Config(config_path=config_path)
    host = cfg.config[0]

    assert str(host.work_dir) == "/remote/work/${USER}/project"
    assert str(host.scratch_dir) == "${SCRATCHDIR}"
    assert (
        host.slurm_defaults.python_env
        == "source ${SCRATCHDIR}/venvs/project/bin/activate"
    )
    assert host.slurm_defaults.output_pattern == "logs/${SLURM_JOB_ID}.out"


@pytest.mark.unit
def test_config_resolves_whole_env_secret_reference(monkeypatch, tmp_path):
    config_path = tmp_path / "ssync.yaml"
    _write_config(
        config_path,
        """
hosts:
  - hostname: cluster.example.com
    password: ${CLUSTER_PASSWORD}
    work_dir: /work/user
    scratch_dir: /scratch/user
api_key: ${LOCAL_SSYNC_API_KEY}
""",
    )
    monkeypatch.setenv("CLUSTER_PASSWORD", "secret-password")
    monkeypatch.setenv("LOCAL_SSYNC_API_KEY", "secret-api-key")

    cfg = Config(config_path=config_path)

    assert cfg.config[0].host.password == "secret-password"
    assert cfg.api_key == "secret-api-key"


@pytest.mark.unit
def test_connection_settings_load_command_timeout(monkeypatch, tmp_path):
    config_path = tmp_path / "ssync.yaml"
    _write_config(
        config_path,
        """
hosts:
  - hostname: cluster.example.com
    work_dir: /work/user
    scratch_dir: /scratch/user
connections:
  connect_timeout: 7
  command_timeout: 300
""",
    )

    monkeypatch.delenv("SSYNC_CONNECT_TIMEOUT", raising=False)
    monkeypatch.delenv("SSYNC_COMMAND_TIMEOUT", raising=False)

    cfg = Config(config_path=config_path)

    assert cfg.connection_settings["connect_timeout"] == 7
    assert cfg.connection_settings["command_timeout"] == 300


@pytest.mark.unit
def test_connection_settings_command_timeout_env_override(monkeypatch, tmp_path):
    config_path = tmp_path / "ssync.yaml"
    _write_config(
        config_path,
        """
hosts:
  - hostname: cluster.example.com
    work_dir: /work/user
    scratch_dir: /scratch/user
connections:
  command_timeout: 300
""",
    )

    monkeypatch.setenv("SSYNC_COMMAND_TIMEOUT", "900")

    cfg = Config(config_path=config_path)

    assert cfg.connection_settings["command_timeout"] == 900


@pytest.mark.unit
def test_config_rejects_non_mapping_yaml(tmp_path):
    config_path = tmp_path / "ssync.yaml"
    _write_config(config_path, "- not\n- a\n- mapping\n")

    with pytest.raises(ConfigError, match="YAML mapping"):
        Config(config_path=config_path)


@pytest.mark.unit
def test_host_key_file_normalizes_with_frozen_dataclass(tmp_path):
    key_file = tmp_path / "id_ed25519"

    host = Host(hostname="cluster.example.com", username="user", key_file=str(key_file))

    assert host.key_file == key_file.resolve()


@pytest.mark.unit
def test_host_proxy_jump_accepts_existing_host_instance():
    proxy = Host(hostname="jump.example.com", username="user")

    host = Host(hostname="cluster.example.com", username="user", ProxyJump=proxy)

    assert host.ProxyJump is proxy
