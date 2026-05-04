from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ssync import cache as cache_module
from ssync.models.job import JobInfo, JobState
from ssync.watchers.actions import ActionExecutor
from ssync.web import app as app_module


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resubmit_uses_launch_manager_with_cached_job_context(monkeypatch):
    executor = ActionExecutor()

    cached_job = SimpleNamespace(
        script_content=(
            "#!/bin/bash\n"
            "python main.py ${resume_run_dir:+--resume ${resume_run_dir}}\n"
        ),
        local_source_dir="/home/aliramlaoui/work/triforces",
        job_info=JobInfo(
            job_id="12345",
            name="train",
            state=JobState.TIMEOUT,
            hostname="adastra",
            work_dir="/lus/work/CT10/cad16353/aramlaoui/triforces",
        ),
    )

    mock_cache = MagicMock()
    mock_cache.get_cached_job.return_value = cached_job
    monkeypatch.setattr(cache_module, "get_cache", lambda: mock_cache)

    mock_manager = MagicMock()
    mock_manager.get_host_by_name.return_value = SimpleNamespace(
        work_dir=Path("/lus/work/CT10/cad16353/aramlaoui"),
    )
    monkeypatch.setattr(app_module, "get_slurm_manager", lambda: mock_manager)

    launch_job_mock = AsyncMock(return_value=SimpleNamespace(job_id="67890"))
    monkeypatch.setattr(
        "ssync.watchers.actions.LaunchManager.launch_job",
        launch_job_mock,
    )

    success, message = await executor._resubmit_job(
        "12345",
        "adastra",
        {},
        {
            "resume_run_dir": "/lus/work/CT10/cad16353/aramlaoui/triforces/run-42",
            "job_end_state": "timeout",
        },
    )

    assert success is True
    assert message == "Resubmitted as job 67890"

    _, kwargs = launch_job_mock.await_args
    assert kwargs["script_path"] is None
    assert kwargs["script_content"] == cached_job.script_content
    assert kwargs["script_variables"]["resume_run_dir"].endswith("run-42")
    assert kwargs["source_dir"] == Path("/home/aliramlaoui/work/triforces")
    assert kwargs["host"] == "adastra"
    assert kwargs["sync_enabled"] is False
    assert kwargs["work_dir_override"] == cached_job.job_info.work_dir


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resubmit_falls_back_to_source_dir_layout_when_work_dir_missing(monkeypatch):
    executor = ActionExecutor()

    cached_job = SimpleNamespace(
        script_content="#!/bin/bash\npython main.py\n",
        local_source_dir="/home/aliramlaoui/work/triforces",
        job_info=JobInfo(
            job_id="12345",
            name="train",
            state=JobState.TIMEOUT,
            hostname="adastra",
            work_dir=None,
        ),
    )

    mock_cache = MagicMock()
    mock_cache.get_cached_job.return_value = cached_job
    monkeypatch.setattr(cache_module, "get_cache", lambda: mock_cache)

    mock_manager = MagicMock()
    mock_manager.get_host_by_name.return_value = SimpleNamespace(
        work_dir=Path("/lus/work/CT10/cad16353/aramlaoui"),
    )
    monkeypatch.setattr(app_module, "get_slurm_manager", lambda: mock_manager)

    launch_job_mock = AsyncMock(return_value=SimpleNamespace(job_id="67890"))
    monkeypatch.setattr(
        "ssync.watchers.actions.LaunchManager.launch_job",
        launch_job_mock,
    )

    success, _ = await executor._resubmit_job(
        "12345",
        "adastra",
        {},
        {"job_end_state": "timeout"},
    )

    assert success is True
    _, kwargs = launch_job_mock.await_args
    assert kwargs["work_dir_override"] == "/lus/work/CT10/cad16353/aramlaoui/triforces"
