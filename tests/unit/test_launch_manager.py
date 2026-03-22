from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ssync.launch import LaunchManager
from ssync.models.cluster import Host, SlurmHost
from ssync.slurm.params import SlurmParams


@pytest.mark.unit
def test_submit_script_in_workdir_reuses_existing_connection(monkeypatch):
    slurm_host = SlurmHost(
        host=Host(hostname="entalpic", username=""),
        work_dir=Path("/tmp"),
        scratch_dir=Path("/tmp"),
    )

    fake_conn = Mock()
    fake_conn.run.return_value = SimpleNamespace(stdout="#!/bin/bash\n", stderr="")

    fake_submit = Mock(
        return_value=(
            SimpleNamespace(stdout="Submitted batch job 4242", stderr=""),
            "cd /tmp && sbatch /tmp/job.slurm",
            ["sbatch", "/tmp/job.slurm"],
            "sbatch /tmp/job.slurm",
        )
    )

    class _FakeManager:
        def __init__(self):
            self.slurm_client = SimpleNamespace(
                submit=SimpleNamespace(run_sbatch=fake_submit)
            )

        def _get_connection(self, _host, force_refresh=False):
            raise AssertionError("launch submission should reuse the existing connection")

    monkeypatch.setattr("ssync.launch.looks_like_array_submission", lambda *_: False)

    manager = _FakeManager()
    launch_manager = LaunchManager(manager)
    params = SlurmParams()

    job = launch_manager._submit_script_in_workdir(
        fake_conn,
        slurm_host,
        params,
        "/tmp/job.slurm",
        Path("/tmp"),
    )

    assert job is not None
    assert job.job_id == "4242"
    args, kwargs = fake_submit.call_args
    assert args == (fake_conn, params, "/tmp/job.slurm")
    assert kwargs == {"work_dir": "/tmp", "warn": True}
