"""Unit tests for SyncManager gitignore translation."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ssync.models.cluster import Host, SlurmHost
from ssync.sync import SyncManager


def _make_sync_manager(source_dir: Path) -> SyncManager:
    return SyncManager(slurm_manager=None, source_dir=source_dir)


@pytest.mark.unit
def test_collect_rsync_filter_rules_preserves_root_anchored_patterns(temp_dir):
    source_dir = temp_dir / "workspace"
    source_dir.mkdir()
    (source_dir / ".gitignore").write_text("/datasets/\n")

    sync_manager = _make_sync_manager(source_dir)

    assert sync_manager._collect_rsync_filter_rules() == ["- /datasets/***"]


@pytest.mark.unit
def test_collect_rsync_filter_rules_keeps_unanchored_patterns_unanchored(temp_dir):
    source_dir = temp_dir / "workspace"
    source_dir.mkdir()
    (source_dir / ".gitignore").write_text("datasets/\n")

    sync_manager = _make_sync_manager(source_dir)

    assert sync_manager._collect_rsync_filter_rules() == ["- datasets/***"]


@pytest.mark.unit
def test_collect_rsync_filter_rules_anchors_nested_gitignore_patterns_to_subdir(
    temp_dir,
):
    source_dir = temp_dir / "workspace"
    nested_dir = source_dir / "src"
    nested_dir.mkdir(parents=True)
    (nested_dir / ".gitignore").write_text("/generated/\n")

    sync_manager = _make_sync_manager(source_dir)

    assert sync_manager._collect_rsync_filter_rules() == ["- /src/generated/***"]


@pytest.mark.unit
@patch("ssync.sync.NativeSSH.ensure_control_master", return_value="/tmp/control.sock")
def test_sync_to_host_reuses_control_master_for_password_auth(
    mock_control_master,
    tmp_path,
):
    source_dir = tmp_path / "workspace"
    source_dir.mkdir()
    conn = Mock()
    conn.host_config = {
        "hostname": "example.com",
        "user": "alice",
        "connect_kwargs": {"password": "secret"},
    }
    conn.host_id = "alice@example.com"
    slurm_manager = Mock()
    slurm_manager._get_connection.return_value = conn
    sync_manager = SyncManager(
        slurm_manager=slurm_manager,
        source_dir=source_dir,
        use_gitignore=False,
    )
    sync_manager._check_directory_size = Mock(return_value=(0, True, ""))
    sync_manager._run_streaming_subprocess = Mock(return_value=0)
    slurm_host = SlurmHost(
        host=Host(hostname="example.com", username="alice", password="secret"),
        work_dir=Path("/work/alice"),
        scratch_dir=Path("/scratch/alice"),
    )

    assert sync_manager.sync_to_host(slurm_host) is True

    conn.run.assert_called_once_with("mkdir -p /work/alice/workspace")
    mock_control_master.assert_called_once_with(conn.host_config, conn.host_id)
    sync_manager._run_streaming_subprocess.assert_called_once_with(
        [
            "rsync",
            "-avz",
            "-e",
            "ssh -S /tmp/control.sock -o ControlMaster=no",
            f"{source_dir}/",
            "alice@example.com:/work/alice/workspace/",
        ]
    )


@pytest.mark.unit
@patch("ssync.sync.NativeSSH.ensure_control_master", return_value=None)
def test_sync_to_host_keeps_sshpass_fallback_for_password_auth(
    _mock_control_master,
    tmp_path,
):
    source_dir = tmp_path / "workspace"
    source_dir.mkdir()
    conn = Mock()
    conn.host_config = {
        "hostname": "example.com",
        "user": "alice",
        "connect_kwargs": {"password": "secret"},
    }
    conn.host_id = "alice@example.com"
    slurm_manager = Mock()
    slurm_manager._get_connection.return_value = conn
    sync_manager = SyncManager(
        slurm_manager=slurm_manager,
        source_dir=source_dir,
        use_gitignore=False,
    )
    sync_manager._check_directory_size = Mock(return_value=(0, True, ""))
    sync_manager._run_streaming_subprocess = Mock(return_value=0)
    slurm_host = SlurmHost(
        host=Host(hostname="example.com", username="alice", password="secret"),
        work_dir=Path("/work/alice"),
        scratch_dir=Path("/scratch/alice"),
    )

    assert sync_manager.sync_to_host(slurm_host) is True

    args, kwargs = sync_manager._run_streaming_subprocess.call_args
    assert args[0] == [
        "sshpass",
        "-e",
        "rsync",
        "-avz",
        f"{source_dir}/",
        "alice@example.com:/work/alice/workspace/",
    ]
    assert kwargs["env"]["SSHPASS"] == "secret"
