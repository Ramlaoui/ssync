"""Unit tests for immediate web job state updates."""

import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException

from ssync.models.cluster import Host, SlurmHost
from ssync.models.job import JobInfo, JobState
from ssync.web import app as web_app
from ssync.web.cache_middleware import CacheMiddleware


def _make_slurm_host(hostname: str) -> SlurmHost:
    return SlurmHost(
        host=Host(hostname=hostname, username="testuser"),
        work_dir=Path("/tmp"),
        scratch_dir=Path("/tmp"),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_job_updates_cache_and_broadcasts(monkeypatch, test_cache):
    hostname = "cluster-cancel.example.com"
    slurm_host = _make_slurm_host(hostname)

    cached_job = JobInfo(
        job_id="7001",
        name="cancel-me",
        state=JobState.RUNNING,
        hostname=hostname,
        user="testuser",
    )
    test_cache.cache_job(cached_job)

    class _FakeManager:
        def __init__(self):
            self.slurm_hosts = [slurm_host]

        def cancel_job(self, target_host, job_id: str) -> bool:
            assert target_host.host.hostname == hostname
            assert job_id == "7001"
            return True

    broadcasts = []

    async def fake_broadcast(job_id: str, host: str, message: dict):
        broadcasts.append((job_id, host, message))

    stop_calls = []

    class _FakeWatcherEngine:
        async def stop_watchers_for_job(self, job_id: str, host: str):
            stop_calls.append((job_id, host))

    fake_watchers = types.ModuleType("ssync.watchers")
    fake_watchers.get_watcher_engine = lambda: _FakeWatcherEngine()

    monkeypatch.setitem(sys.modules, "ssync.watchers", fake_watchers)
    monkeypatch.setattr(web_app, "get_slurm_manager", lambda: _FakeManager())
    monkeypatch.setattr(web_app._cache_middleware, "cache", test_cache)
    monkeypatch.setattr(web_app.job_manager, "broadcast_job_update", fake_broadcast)

    result = await web_app.cancel_job("7001", host=hostname, _authenticated=True)

    assert result == {"message": "Job cancelled successfully"}

    cached_after = test_cache.get_cached_job("7001", hostname)
    assert cached_after is not None
    assert cached_after.job_info.state == JobState.CANCELLED
    assert cached_after.is_active is False

    assert stop_calls == [("7001", hostname)]
    assert len(broadcasts) == 1
    assert broadcasts[0][0] == "7001"
    assert broadcasts[0][1] == hostname
    assert broadcasts[0][2]["type"] == "job_update"
    assert broadcasts[0][2]["new_state"] == "CA"
    assert broadcasts[0][2]["job"]["state"] == "CA"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_fallback_skips_stale_active_jobs(test_cache):
    hostname = "cluster-fallback.example.com"
    middleware = CacheMiddleware()
    middleware.cache = test_cache
    middleware._recent_active_cache_ttl_seconds = 60

    cached_job = JobInfo(
        job_id="7002",
        name="stale-running",
        state=JobState.RUNNING,
        hostname=hostname,
        user="testuser",
    )
    test_cache.cache_job(cached_job)

    stale_time = (datetime.now() - timedelta(minutes=10)).isoformat()
    with test_cache._get_connection() as conn:
        conn.execute(
            """
            UPDATE cached_jobs
            SET last_updated = ?
            WHERE job_id = ? AND hostname = ?
            """,
            (stale_time, "7002", hostname),
        )
        conn.commit()

    assert await middleware.get_job_with_cache_fallback("7002", hostname) is None

    cached = await middleware.get_job_with_cache_fallback(
        "7002", hostname, allow_stale_active=True
    )
    assert cached is not None
    assert cached.job_id == "7002"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_job_details_force_refresh_skips_cache_fallback(
    monkeypatch, test_cache
):
    hostname = "cluster-force-refresh.example.com"
    slurm_host = _make_slurm_host(hostname)

    cached_job = JobInfo(
        job_id="7003",
        name="stale-running",
        state=JobState.RUNNING,
        hostname=hostname,
        user="testuser",
    )
    test_cache.cache_job(cached_job)

    class _FakeManager:
        def __init__(self):
            self.slurm_hosts = [slurm_host]

        def get_job_info(self, target_host, job_id: str):
            assert target_host.host.hostname == hostname
            assert job_id == "7003"
            return None

    monkeypatch.setattr(web_app, "get_slurm_manager", lambda: _FakeManager())
    monkeypatch.setattr(web_app._cache_middleware, "cache", test_cache)

    with pytest.raises(HTTPException) as excinfo:
        await web_app.get_job_details(
            "7003",
            host=hostname,
            cache_first=False,
            force_refresh=True,
            force=False,
            _authenticated=True,
        )

    assert excinfo.value.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_active_snapshot_cache_includes_hosts_without_jobs(monkeypatch):
    host_a = _make_slurm_host("cluster-a.example.com")
    host_b = _make_slurm_host("cluster-b.example.com")

    class _FakeManager:
        def __init__(self):
            self.slurm_hosts = [host_a, host_b]

    captured = {}

    async def fake_verify(current_job_ids):
        captured.update(current_job_ids)

    monkeypatch.setattr(
        web_app._cache_middleware, "_verify_and_update_cache", fake_verify
    )

    await web_app._verify_active_snapshot_cache(
        [
            JobInfo(
                job_id="8001",
                name="active-job",
                state=JobState.RUNNING,
                hostname=host_a.host.hostname,
                user="testuser",
            )
        ],
        _FakeManager(),
        500,
    )

    assert captured == {
        host_a.host.hostname: ["8001"],
        host_b.host.hostname: [],
    }


@pytest.mark.unit
def test_cache_job_state_marks_array_submission_parent_placeholder(monkeypatch, test_cache):
    monkeypatch.setattr(web_app._cache_middleware, "cache", test_cache)

    job_info, previous_state = web_app._cache_job_state(
        "8002",
        "cluster-array.example.com",
        JobState.PENDING,
        job_name="array-launch",
        array_submission=True,
    )

    assert previous_state is None
    assert job_info.array_job_id == "8002"
    assert job_info.array_task_id == "[submission]"

    cached = test_cache.get_cached_job("8002", "cluster-array.example.com")
    assert cached is not None
    assert cached.job_info.array_job_id == "8002"
    assert cached.job_info.array_task_id == "[submission]"


@pytest.mark.unit
def test_filter_ws_initial_cached_jobs_skips_stale_placeholders(test_cache):
    hostname = "cluster-ws.example.com"

    real_job = JobInfo(
        job_id="8100",
        name="real-job",
        state=JobState.FAILED,
        hostname=hostname,
        user="testuser",
        partition="debug",
    )
    inactive_placeholder = JobInfo(
        job_id="8101",
        name="placeholder-inactive",
        state=JobState.UNKNOWN,
        hostname=hostname,
        user=None,
        submit_line="sbatch --job-name=array /tmp/job.slurm",
    )
    stale_active_placeholder = JobInfo(
        job_id="8102",
        name="placeholder-stale",
        state=JobState.PENDING,
        hostname=hostname,
        user=None,
        submit_line="sbatch --job-name=array /tmp/job.slurm",
    )
    recent_active_placeholder = JobInfo(
        job_id="8103",
        name="placeholder-recent",
        state=JobState.PENDING,
        hostname=hostname,
        user=None,
        submit_line="sbatch --job-name=array /tmp/job.slurm",
    )

    test_cache.cache_job(real_job)
    test_cache.cache_job(inactive_placeholder)
    test_cache.cache_job(stale_active_placeholder)
    test_cache.cache_job(recent_active_placeholder)

    stale_cached_at = (datetime.now() - timedelta(minutes=10)).isoformat()
    with test_cache._get_connection() as conn:
        conn.execute(
            """
            UPDATE cached_jobs
            SET is_active = 0
            WHERE job_id = ? AND hostname = ?
            """,
            ("8101", hostname),
        )
        conn.execute(
            """
            UPDATE cached_jobs
            SET cached_at = ?
            WHERE job_id = ? AND hostname = ?
            """,
            (stale_cached_at, "8102", hostname),
        )
        conn.commit()

    cached_rows = test_cache.get_cached_jobs(
        hostname=hostname,
        limit=20,
    )

    class _FakeJobDataManager:
        _placeholder_active_cache_ttl_seconds = 90

        @staticmethod
        def _is_launch_placeholder_job(job_info: JobInfo) -> bool:
            return (
                job_info.user is None
                and not job_info.partition
                and not job_info.nodes
                and not job_info.cpus
                and not job_info.memory
                and bool(job_info.submit_line)
            )

    filtered_jobs = web_app._filter_ws_initial_cached_jobs(
        _FakeJobDataManager(), cached_rows
    )
    filtered_ids = {job.job_id for job in filtered_jobs}

    assert filtered_ids == {"8100", "8103"}
