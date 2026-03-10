"""Unit tests for immediate web job state updates."""

import sys
import types
from pathlib import Path

import pytest

from ssync.models.cluster import Host, SlurmHost
from ssync.models.job import JobInfo, JobState
from ssync.web import app as web_app


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

    result = await web_app.cancel_job("7001", host=hostname, authenticated=True)

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
