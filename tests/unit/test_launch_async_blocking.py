"""Regression tests for launch-path blocking SSH connection acquisition."""

import asyncio
import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ssync.job_data_manager import JobDataManager
from ssync.launch import LaunchManager
from ssync.models.cluster import Host, SlurmHost
from ssync.models.job import JobInfo, JobState
from ssync.slurm.params import SlurmParams


def _make_slurm_host(hostname: str) -> SlurmHost:
    return SlurmHost(
        host=Host(hostname=hostname, username="testuser"),
        work_dir=Path("/remote/work"),
        scratch_dir=Path("/remote/scratch"),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_launch_job_offloads_connection_acquisition(monkeypatch, temp_dir):
    hostname = "cluster-launch.example.com"
    slurm_host = _make_slurm_host(hostname)
    script_path = temp_dir / "job.sh"
    script_path.write_text("#!/bin/bash\necho hello\n")

    call_thread = {}

    class _FakeConn:
        def run(self, _command, **_kwargs):
            return None

    class _FakeManager:
        def get_host_by_name(self, host: str):
            assert host == hostname
            return slurm_host

        def _get_connection(self, host):
            assert host.hostname == hostname
            call_thread["ident"] = threading.get_ident()
            call_thread["name"] = threading.current_thread().name
            return _FakeConn()

    def fake_submit(*_args, **_kwargs):
        return types.SimpleNamespace(job_id="12345")

    async def fake_capture_submission(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "ssync.launch.ScriptProcessor.prepare_script",
        lambda clean_script_path, _temp_dir, params=None: clean_script_path,
    )
    monkeypatch.setattr("ssync.launch.send_file", lambda *_args, **_kwargs: "/remote/work/scripts/job.sh")
    monkeypatch.setattr(LaunchManager, "_submit_script_in_workdir", fake_submit)
    monkeypatch.setattr(
        LaunchManager, "_capture_submission_in_background", fake_capture_submission
    )

    launch_manager = LaunchManager(_FakeManager(), executor=ThreadPoolExecutor(max_workers=2))
    try:
        job = await launch_manager.launch_job(
            script_path=script_path,
            source_dir=None,
            host=hostname,
            slurm_params=SlurmParams(),
            sync_enabled=False,
        )
    finally:
        launch_manager.executor.shutdown(wait=True, cancel_futures=True)

    assert job.job_id == "12345"
    assert call_thread["ident"] != threading.get_ident()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_launch_job_uses_unique_temp_directory(monkeypatch, temp_dir):
    hostname = "cluster-launch.example.com"
    slurm_host = _make_slurm_host(hostname)
    script_path = temp_dir / "job.sh"
    script_path.write_text("#!/bin/bash\necho hello\n")

    unique_temp_dir = temp_dir / "unique-launch-dir"
    unique_temp_dir.mkdir()
    uploaded = {}

    class _FakeConn:
        def run(self, _command, **_kwargs):
            return None

    class _FakeManager:
        def get_host_by_name(self, host: str):
            assert host == hostname
            return slurm_host

        def _get_connection(self, host):
            assert host.hostname == hostname
            return _FakeConn()

    def fake_prepare_script(clean_script_path, target_dir, params=None):
        prepared = target_dir / "clean_job.slurm"
        prepared.write_text(clean_script_path.read_text())
        return prepared

    def fake_send_file(_conn, local_path, *_args, **_kwargs):
        uploaded["local_path"] = local_path
        return "/remote/work/scripts/clean_job.slurm"

    def fake_submit(*_args, **_kwargs):
        return types.SimpleNamespace(job_id="12345")

    monkeypatch.setattr("ssync.launch.tempfile.mkdtemp", lambda prefix: str(unique_temp_dir))
    monkeypatch.setattr("ssync.launch.ScriptProcessor.prepare_script", fake_prepare_script)
    monkeypatch.setattr("ssync.launch.send_file", fake_send_file)
    monkeypatch.setattr(LaunchManager, "_submit_script_in_workdir", fake_submit)

    launch_manager = LaunchManager(_FakeManager(), executor=ThreadPoolExecutor(max_workers=2))
    try:
        job = await launch_manager.launch_job(
            script_path=script_path,
            source_dir=None,
            host=hostname,
            slurm_params=SlurmParams(),
            sync_enabled=False,
        )
    finally:
        launch_manager.executor.shutdown(wait=True, cancel_futures=True)

    assert job.job_id == "12345"
    assert uploaded["local_path"].startswith(str(unique_temp_dir))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_capture_job_submission_offloads_connection_acquisition(
    monkeypatch, test_cache
):
    hostname = "cluster-capture.example.com"
    slurm_host = _make_slurm_host(hostname)
    call_thread = {}
    executor = ThreadPoolExecutor(max_workers=2)

    class _FakeManager:
        slurm_client = types.SimpleNamespace(
            get_job_output_files=lambda _conn, _job_id, _hostname: (None, None)
        )

        def get_host_by_name(self, host: str):
            assert host == hostname
            return slurm_host

        def _get_connection(self, host):
            assert host.hostname == hostname
            call_thread["ident"] = threading.get_ident()
            call_thread["name"] = threading.current_thread().name
            return object()

        def get_job_info(self, _slurm_host, job_id: str, _user=None):
            return JobInfo(
                job_id=job_id,
                name="captured-job",
                state=JobState.PENDING,
                hostname=hostname,
                user="testuser",
            )

    fake_module = types.ModuleType("ssync.web.app")
    fake_module.get_slurm_manager = lambda: _FakeManager()
    fake_module.executor = executor
    fake_module.background_executor = executor
    monkeypatch.setitem(sys.modules, "ssync.web.app", fake_module)

    manager = JobDataManager()
    manager.cache = test_cache
    try:
        await manager.capture_job_submission("12345", hostname, "#!/bin/bash\necho hi\n")
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    assert call_thread["ident"] != threading.get_ident()
