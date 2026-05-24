import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ssync.config_hosts import (
    ConfigHostError,
    add_host_from_ssh_alias,
    list_ssh_config_aliases,
    resolve_ssh_config_alias,
)
from ssync.utils.config import Config


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def fake_ssh_g(monkeypatch):
    def fake_run(command, **kwargs):
        assert command[:2] == ["ssh", "-G"]
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        alias = command[-1]
        return SimpleNamespace(
            returncode=0,
            stdout=(
                f"hostname {alias}.example.com\n"
                "user alice\n"
                "port 2222\n"
                "identityfile ~/.ssh/id_ed25519\n"
                "proxyjump jump-host\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("ssync.config_hosts.subprocess.run", fake_run)


@pytest.mark.unit
def test_config_hosts_import_does_not_require_existing_config(tmp_path):
    env = os.environ.copy()
    env["SSYNC_CONFIG_PATH"] = str(tmp_path / "missing.yaml")

    result = subprocess.run(
        [sys.executable, "-c", "import ssync.config_hosts"],
        cwd=Path(__file__).parents[2],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.unit
def test_list_ssh_config_aliases_reads_includes_and_skips_patterns(tmp_path):
    ssh_config = tmp_path / ".ssh" / "config"
    included_config = tmp_path / ".ssh" / "clusters.conf"
    _write(
        ssh_config,
        """
Host *
  ServerAliveInterval 60
Include clusters.conf
Host lab-gpu batch-login
  User alice
Host *.example.com !blocked
  User ignored
""",
    )
    _write(
        included_config,
        """
Host analysis-node
  HostName analysis.example.org
""",
    )

    aliases = list_ssh_config_aliases(ssh_config)

    assert [item.alias for item in aliases] == [
        "analysis-node",
        "batch-login",
        "lab-gpu",
    ]
    assert {item.alias: item.source_path for item in aliases}["analysis-node"] == (
        included_config
    ).resolve()


@pytest.mark.unit
def test_resolve_ssh_config_alias_uses_ssh_g_without_returning_identity_path(
    tmp_path, fake_ssh_g
):
    ssh_config = tmp_path / ".ssh" / "config"
    _write(ssh_config, "Host lab-gpu\n  HostName lab-gpu.example.org\n")

    resolved = resolve_ssh_config_alias("lab-gpu", config_path=ssh_config)

    assert resolved.alias == "lab-gpu"
    assert resolved.hostname == "lab-gpu.example.com"
    assert resolved.user == "alice"
    assert resolved.port == 2222
    assert resolved.proxyjump == "jump-host"
    assert resolved.has_identity_file is True
    assert "identityfile" not in resolved.options


@pytest.mark.unit
def test_resolve_ssh_config_alias_rejects_unknown_alias(tmp_path):
    ssh_config = tmp_path / ".ssh" / "config"
    _write(ssh_config, "Host lab-gpu\n  HostName lab-gpu.example.org\n")

    with pytest.raises(ConfigHostError, match="not found"):
        resolve_ssh_config_alias("missing", config_path=ssh_config)


@pytest.mark.unit
def test_add_host_from_ssh_alias_writes_minimal_alias_config(tmp_path, fake_ssh_g):
    ssh_config = tmp_path / ".ssh" / "config"
    target_config = tmp_path / "ssync.yaml"
    _write(ssh_config, "Host lab-gpu\n  HostName lab-gpu.example.org\n")

    preview = add_host_from_ssh_alias(
        "lab-gpu",
        work_dir="/gpfs/work/$USER/project",
        scratch_dir="/gpfs/scratch/$USER",
        slurm_defaults={"partition": "gpu", "time": "02:00:00"},
        config_path=target_config,
        ssh_config_path=ssh_config,
        dry_run=True,
    )

    assert preview.dry_run is True
    assert preview.created is True
    assert not target_config.exists()

    result = add_host_from_ssh_alias(
        "lab-gpu",
        work_dir="/gpfs/work/$USER/project",
        scratch_dir="/gpfs/scratch/$USER",
        slurm_defaults={"partition": "gpu", "time": "02:00:00"},
        config_path=target_config,
        ssh_config_path=ssh_config,
        expected_sha256=preview.before_sha256,
        expected_mtime_ns=preview.before_mtime_ns,
    )

    rendered = target_config.read_text()
    assert result.changed is True
    assert "hostname: lab-gpu\n" in rendered
    assert "use_ssh_config: true\n" in rendered
    assert "lab-gpu.example.com" not in rendered
    assert "identityfile" not in rendered.lower()
    assert "alice" not in rendered
    assert Config(config_path=target_config).config[0].host.hostname == "lab-gpu"


@pytest.mark.unit
def test_add_host_from_ssh_alias_guards_against_stale_preview(tmp_path, fake_ssh_g):
    ssh_config = tmp_path / ".ssh" / "config"
    target_config = tmp_path / "ssync.yaml"
    _write(ssh_config, "Host lab-gpu\n  HostName lab-gpu.example.org\n")
    _write(
        target_config,
        """
hosts:
  - hostname: old
    work_dir: /work
    scratch_dir: /scratch
""",
    )
    preview = add_host_from_ssh_alias(
        "lab-gpu",
        work_dir="/work",
        scratch_dir="/scratch",
        config_path=target_config,
        ssh_config_path=ssh_config,
        dry_run=True,
    )
    target_config.write_text(target_config.read_text() + "api:\n  port: 9000\n")

    with pytest.raises(ConfigHostError, match="changed since preview"):
        add_host_from_ssh_alias(
            "lab-gpu",
            work_dir="/work",
            scratch_dir="/scratch",
            config_path=target_config,
            ssh_config_path=ssh_config,
            expected_sha256=preview.before_sha256,
        )
