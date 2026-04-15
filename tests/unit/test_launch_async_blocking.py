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
            return types.SimpleNamespace(
                return_code=0,
                stdout="",
                stderr="",
                ok=True,
            )

        def cd(self, _path):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

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

        def cd(self, _path):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

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
async def test_launch_job_caches_prepared_template_and_uploads_rendered_script(
    monkeypatch, test_cache
):
    hostname = "cluster-launch.example.com"
    slurm_host = _make_slurm_host(hostname)
    uploaded = {}
    captured = {}
    executor = ThreadPoolExecutor(max_workers=2)

    class _FakeConn:
        def run(self, _command, **_kwargs):
            return types.SimpleNamespace(
                return_code=0,
                stdout="",
                stderr="",
                ok=True,
            )

        def cd(self, _path):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeManager:
        def get_host_by_name(self, host: str):
            assert host == hostname
            return slurm_host

        def _get_connection(self, host):
            assert host.hostname == hostname
            return _FakeConn()

    def fake_send_file(_conn, local_path, remote_path, _is_remote_dir):
        uploaded["local_path"] = local_path
        uploaded["content"] = Path(local_path).read_text()
        return remote_path

    def fake_submit(
        _self,
        _conn,
        _slurm_host,
        _slurm_params,
        _remote_script_path,
        _work_dir,
        template_script_content,
        watchers,
        _launch_event_emitter=None,
    ):
        uploaded["template_script_content"] = template_script_content
        uploaded["watcher_count"] = len(watchers)
        return types.SimpleNamespace(job_id="12345")

    async def fake_capture_submission(
        self, job_id, host, script_content, local_source_dir=None
    ):
        captured["job_id"] = job_id
        captured["host"] = host
        captured["script_content"] = script_content
        captured["local_source_dir"] = local_source_dir

    monkeypatch.setattr("ssync.cache.get_cache", lambda: test_cache)
    monkeypatch.setattr("ssync.launch.send_file", fake_send_file)
    monkeypatch.setattr(LaunchManager, "_submit_script_in_workdir", fake_submit)
    monkeypatch.setattr(
        LaunchManager, "_capture_submission_in_background", fake_capture_submission
    )

    script_content = """#!/bin/bash
#LOGIN_SETUP_BEGIN
module load cuda
#LOGIN_SETUP_END
#WATCHER_BEGIN
# name: auto resubmit
# pattern: "HYDRA_OUTPUT_DIR=(.+)"
# captures: [resume_run_dir]
# trigger_on_job_end: true
# actions:
#   - resubmit()
#WATCHER_END
python train.py ${resume_run_dir:+--resume ${resume_run_dir}}
"""

    launch_manager = LaunchManager(_FakeManager(), executor=executor)
    try:
        job = await launch_manager.launch_job(
            script_path=None,
            script_content=script_content,
            source_dir=None,
            host=hostname,
            slurm_params=SlurmParams(job_name="templated-job"),
            sync_enabled=False,
            script_variables={"resume_run_dir": "/scratch/run-42"},
        )
        await asyncio.sleep(0)
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    cached_job = test_cache.get_cached_job("12345", hostname)

    assert job.job_id == "12345"
    assert cached_job is not None
    assert "#SBATCH --job-name=templated-job" in cached_job.script_content
    assert "#LOGIN_SETUP_BEGIN" in cached_job.script_content
    assert "#WATCHER_BEGIN" in cached_job.script_content
    assert "${resume_run_dir:+--resume ${resume_run_dir}}" in cached_job.script_content
    assert "/scratch/run-42" not in cached_job.script_content

    assert "#LOGIN_SETUP_BEGIN" not in uploaded["content"]
    assert "#WATCHER_BEGIN" in uploaded["content"]
    assert "--resume /scratch/run-42" in uploaded["content"]
    assert "${resume_run_dir:+--resume ${resume_run_dir}}" not in uploaded["content"]

    assert "#WATCHER_BEGIN" in uploaded["template_script_content"]
    assert "${resume_run_dir:+--resume ${resume_run_dir}}" in uploaded[
        "template_script_content"
    ]
    assert "/scratch/run-42" not in uploaded["template_script_content"]
    assert uploaded["watcher_count"] == 1

    assert captured["job_id"] == "12345"
    assert captured["host"] == hostname
    assert captured["script_content"] == cached_job.script_content
    assert captured["local_source_dir"] is None


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
