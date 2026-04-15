"""Regression tests for blocking web handlers and request coalescing."""

import asyncio
import sys
import threading
import types
from pathlib import Path

import pytest

from ssync.models.cluster import Host, SlurmHost
from ssync.models.job import JobInfo, JobState
from ssync.request_coalescer import JobRequestCoalescer
from ssync.web.models import JobInfoWeb
from ssync.web import app as web_app


def _make_slurm_host(hostname: str) -> SlurmHost:
    return SlurmHost(
        host=Host(hostname=hostname, username="testuser"),
        work_dir=Path("/tmp"),
        scratch_dir=Path("/tmp"),
    )


def _make_job(
    job_id: str, hostname: str, state: JobState = JobState.RUNNING
) -> JobInfo:
    return JobInfo(
        job_id=job_id,
        name=f"job-{job_id}",
        state=state,
        hostname=hostname,
        user="testuser",
    )


def _get_route_endpoint(path: str, method: str):
    for route in web_app.app.routes:
        if getattr(route, "path", None) != path:
            continue
        if method.upper() not in getattr(route, "methods", set()):
            continue
        return route.endpoint
    raise AssertionError(f"Route {method} {path} not found")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_job_offloads_blocking_manager_call(monkeypatch, test_cache):
    hostname = "cluster-cancel.example.com"
    slurm_host = _make_slurm_host(hostname)
    main_thread = threading.main_thread()
    call_thread = {}
    manager = web_app.get_slurm_manager()

    def fake_cancel_job(target_host, job_id: str) -> bool:
        assert target_host.host.hostname == hostname
        assert job_id == "7001"
        call_thread["name"] = threading.current_thread().name
        call_thread["ident"] = threading.get_ident()
        return True

    async def fake_broadcast(_job_id: str, _host: str, _message: dict):
        return None

    class _FakeWatcherEngine:
        async def stop_watchers_for_job(self, _job_id: str, _host: str):
            return None

    fake_watchers = types.ModuleType("ssync.watchers")
    fake_watchers.get_watcher_engine = lambda: _FakeWatcherEngine()

    monkeypatch.setitem(sys.modules, "ssync.watchers", fake_watchers)
    monkeypatch.setattr(manager, "slurm_hosts", [slurm_host])
    monkeypatch.setattr(manager, "cancel_job", fake_cancel_job)
    monkeypatch.setattr(web_app._cache_middleware, "cache", test_cache)
    monkeypatch.setattr(web_app.job_manager, "broadcast_job_update", fake_broadcast)

    cancel_job = _get_route_endpoint("/api/jobs/{job_id}/cancel", "POST")
    result = await cancel_job("7001", host=hostname, _authenticated=True)

    assert result == {"message": "Job cancelled successfully"}
    assert call_thread["ident"] != threading.get_ident()
    assert call_thread["name"] != main_thread.name


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_job_details_offloads_blocking_manager_call(
    monkeypatch, test_cache
):
    hostname = "cluster-details.example.com"
    slurm_host = _make_slurm_host(hostname)
    job = _make_job("7002", hostname)
    call_thread = {}
    manager = web_app.get_slurm_manager()

    def fake_get_job_info(target_host, job_id: str):
        assert target_host.host.hostname == hostname
        assert job_id == "7002"
        call_thread["ident"] = threading.get_ident()
        call_thread["name"] = threading.current_thread().name
        return job

    async def fake_cache_job_status_response(results, verify_active_jobs=False):
        return results

    async def fake_broadcast(_job_id: str, _host: str, _message: dict):
        return None

    monkeypatch.setattr(manager, "slurm_hosts", [slurm_host])
    monkeypatch.setattr(manager, "get_job_info", fake_get_job_info)
    monkeypatch.setattr(
        web_app._cache_middleware,
        "cache_job_status_response",
        fake_cache_job_status_response,
    )
    monkeypatch.setattr(web_app.job_manager, "broadcast_job_update", fake_broadcast)

    get_job_details = _get_route_endpoint("/api/jobs/{job_id}", "GET")
    result = await get_job_details(
        "7002",
        host=hostname,
        cache_first=False,
        force_refresh=False,
        force=False,
        _authenticated=True,
    )

    assert result.job_id == "7002"
    assert call_thread["ident"] != threading.get_ident()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_job_details_force_refresh_returns_cached_job_immediately(
    monkeypatch
):
    hostname = "cluster-cache-first.example.com"
    cached_job = _make_job("7003", hostname)

    queue_calls = []

    def fake_queue_job_refresh(**kwargs):
        queue_calls.append(kwargs)
        return True

    def fail_get_job_info(*args, **kwargs):
        raise AssertionError("cached force_refresh should not block on get_job_info")

    async def fake_get_job_with_cache_fallback(*args, **kwargs):
        return JobInfoWeb.from_job_info(cached_job)

    manager = web_app.get_slurm_manager()
    monkeypatch.setattr(manager, "slurm_hosts", [_make_slurm_host(hostname)])
    monkeypatch.setattr(manager, "get_job_info", fail_get_job_info)
    monkeypatch.setattr(
        web_app._cache_middleware,
        "get_job_with_cache_fallback",
        fake_get_job_with_cache_fallback,
    )
    monkeypatch.setattr("ssync.web.api.job.queue_job_refresh", fake_queue_job_refresh)

    get_job_details = _get_route_endpoint("/api/jobs/{job_id}", "GET")
    result = await get_job_details(
        "7003",
        host=hostname,
        cache_first=False,
        force_refresh=True,
        force=False,
        _authenticated=True,
    )

    assert result.job_id == "7003"
    assert result.cached is True
    assert result.stale is True
    assert result.refresh_queued is True
    assert queue_calls and queue_calls[0]["host"] == hostname


@pytest.mark.unit
@pytest.mark.asyncio
async def test_request_coalescer_duplicate_request_does_not_deadlock():
    hostname = "cluster-coalesce.example.com"
    job = _make_job("8001", hostname)
    coalescer = JobRequestCoalescer(batch_window_ms=10, max_batch_size=50)
    fetch_calls = {"count": 0}

    async def fetch_func(target_host: str, job_ids: list[str]):
        assert target_host == hostname
        assert job_ids == ["8001"]
        fetch_calls["count"] += 1
        await asyncio.sleep(0)
        return [job]

    first_request = asyncio.create_task(
        coalescer.fetch_job("8001", hostname, fetch_func)
    )
    await asyncio.sleep(0)
    second_request = asyncio.create_task(
        coalescer.fetch_job("8001", hostname, fetch_func)
    )

    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first_request, second_request),
        timeout=1.0,
    )

    assert fetch_calls["count"] == 1
    assert first_result.job_id == "8001"
    assert second_result.job_id == "8001"
