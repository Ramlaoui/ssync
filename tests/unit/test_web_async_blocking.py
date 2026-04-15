"""Regression tests for blocking web handlers and request coalescing."""

import asyncio
import json
import sys
import threading
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import WebSocketDisconnect

from ssync.models.cluster import Host, SlurmHost
from ssync.models.job import JobInfo, JobState
from ssync.request_coalescer import JobRequestCoalescer
from ssync.web.models import JobInfoWeb
from ssync.web import app as web_app
from ssync.web.realtime import handlers as realtime_handlers
from ssync.web.realtime import monitor as realtime_monitor
from ssync.web.realtime.state import all_jobs_state
from ssync.web.services import jobs as job_services


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


class _FakeAllJobsWebSocket:
    def __init__(self):
        self.accepted = False
        self.messages = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        self.messages.append(message)

    async def receive_text(self):
        raise WebSocketDisconnect()


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_queue_job_refresh_reuses_existing_background_task(monkeypatch):
    hostname = "cluster-refresh.example.com"
    job_id = "8002"
    key = (hostname, job_id)
    created = []
    started = asyncio.Event()
    release = asyncio.Event()

    def fake_refresh_job_in_background(**kwargs):
        created.append(kwargs)

        async def _runner():
            started.set()
            await release.wait()

        return _runner()

    job_services._JOB_REFRESH_TASKS.pop(key, None)
    monkeypatch.setattr(
        "ssync.web.services.jobs.refresh_job_in_background",
        fake_refresh_job_in_background,
    )

    try:
        assert job_services.queue_job_refresh(
            job_id=job_id,
            host=hostname,
            get_slurm_manager=lambda: None,
            cache_middleware=None,
            job_manager=None,
        )
        assert job_services.queue_job_refresh(
            job_id=job_id,
            host=hostname,
            get_slurm_manager=lambda: None,
            cache_middleware=None,
            job_manager=None,
        )

        await asyncio.wait_for(started.wait(), timeout=1.0)
        assert len(created) == 1
        assert key in job_services._JOB_REFRESH_TASKS
    finally:
        release.set()
        task = job_services._JOB_REFRESH_TASKS.get(key)
        if task is not None:
            await task
        await asyncio.sleep(0)
        job_services._JOB_REFRESH_TASKS.pop(key, None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_job_status_single_host_uses_cached_snapshot(monkeypatch, test_cache):
    hostname = "cluster-status.example.com"
    slurm_host = _make_slurm_host(hostname)
    cached_job = _make_job("9001", hostname)
    test_cache.cache_job(cached_job)
    test_cache.update_host_fetch_state(
        hostname=hostname,
        fetch_time=datetime.now(),
        fetch_time_utc=datetime.now(timezone.utc),
    )

    manager = web_app.get_slurm_manager()

    async def fail_get_all_jobs(*args, **kwargs):
        raise AssertionError("single-host status cache hit should not fetch inline")

    monkeypatch.setattr(manager, "slurm_hosts", [slurm_host])
    monkeypatch.setattr(manager, "get_all_jobs", fail_get_all_jobs)
    monkeypatch.setattr(web_app._cache_middleware, "cache", test_cache)
    manager.slurm_client.query._username_cache[hostname] = cached_job.user

    get_job_status = _get_route_endpoint("/api/status", "GET")
    request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
    result = await get_job_status(
        request=request,
        host=hostname,
        user=None,
        since=None,
        limit=None,
        job_ids=None,
        state=None,
        active_only=False,
        completed_only=False,
        search=None,
        group_array_jobs=True,
        force_refresh=False,
        profile=False,
        _authenticated=True,
    )

    payload = json.loads(result.body)

    assert result.media_type == "application/json"
    assert len(payload) == 1
    assert payload[0]["hostname"] == hostname
    assert payload[0]["cached"] is True
    assert [job["job_id"] for job in payload[0]["jobs"]] == ["9001"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_all_jobs_websocket_sends_empty_initial_without_inline_fetch(
    monkeypatch,
):
    websocket = _FakeAllJobsWebSocket()
    manager = types.SimpleNamespace(
        slurm_hosts=[_make_slurm_host("adastra"), _make_slurm_host("jz")]
    )
    fetch_calls = {"count": 0}

    class _FakeJobDataManager:
        async def fetch_all_jobs(self, **kwargs):
            fetch_calls["count"] += 1
            raise AssertionError("WebSocket bootstrap should not fetch inline")

    async def fake_verify(_websocket):
        return True

    async def fake_monitor_all_jobs_singleton(**kwargs):
        return None

    monkeypatch.setattr(
        "ssync.job_data_manager.get_job_data_manager",
        lambda: _FakeJobDataManager(),
    )
    monkeypatch.setattr(
        realtime_handlers,
        "get_cache",
        lambda: types.SimpleNamespace(get_cached_jobs=lambda **kwargs: []),
    )
    monkeypatch.setattr(
        realtime_handlers,
        "monitor_all_jobs_singleton",
        fake_monitor_all_jobs_singleton,
    )

    previous_monitor_task = all_jobs_state.monitor_task
    previous_websockets = set(all_jobs_state.websockets)
    all_jobs_state.monitor_task = None
    all_jobs_state.websockets.clear()

    try:
        await realtime_handlers.websocket_all_jobs_handler(
            websocket,
            verify_websocket_api_key=fake_verify,
            get_slurm_manager=lambda: manager,
            cache_middleware=types.SimpleNamespace(),
        )
    finally:
        if all_jobs_state.monitor_task is not None:
            await all_jobs_state.monitor_task
        all_jobs_state.monitor_task = previous_monitor_task
        all_jobs_state.websockets = previous_websockets

    assert websocket.accepted is True
    assert fetch_calls["count"] == 0
    assert websocket.messages[0] == {
        "type": "initial",
        "jobs": {"adastra": [], "jz": []},
        "total": 0,
        "array_groups": {},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_all_jobs_monitor_uses_cache_only_on_first_cycle(monkeypatch):
    fetch_calls = {"count": 0}
    cached_job = _make_job("9100", "adastra")
    broadcasts = []

    class _FakeJobDataManager:
        _placeholder_active_cache_ttl_seconds = 90

        def _is_launch_placeholder_job(self, _job):
            return False

        async def fetch_all_jobs(self, **kwargs):
            fetch_calls["count"] += 1
            return []

    async def fake_sleep(_seconds, *args, **kwargs):
        all_jobs_state.websockets.clear()

    async def fake_broadcast(_websockets, message):
        broadcasts.append(message)
        return set()

    monkeypatch.setattr(
        "ssync.job_data_manager.get_job_data_manager",
        lambda: _FakeJobDataManager(),
    )
    monkeypatch.setattr(
        realtime_monitor,
        "get_cache",
        lambda: types.SimpleNamespace(
            get_cached_jobs=lambda **kwargs: [
                types.SimpleNamespace(
                    job_info=cached_job,
                    is_active=True,
                    cached_at=datetime.now(),
                )
            ]
        ),
    )
    monkeypatch.setattr(realtime_monitor.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        realtime_monitor,
        "broadcast_json_to_websockets",
        fake_broadcast,
    )
    async def fake_completed_updates(*args, **kwargs):
        return []

    monkeypatch.setattr(
        realtime_monitor,
        "_fetch_completed_job_updates",
        fake_completed_updates,
    )

    previous_monitor_task = all_jobs_state.monitor_task
    previous_websockets = set(all_jobs_state.websockets)
    all_jobs_state.monitor_task = None
    all_jobs_state.websockets = {object()}

    try:
        await realtime_monitor.monitor_all_jobs_singleton(
            get_slurm_manager=lambda: types.SimpleNamespace(slurm_hosts=[]),
            cache_middleware=types.SimpleNamespace(),
        )
    finally:
        all_jobs_state.monitor_task = previous_monitor_task
        all_jobs_state.websockets = previous_websockets

    assert fetch_calls["count"] == 0
    assert broadcasts
    assert broadcasts[0]["type"] == "batch_update"
    assert broadcasts[0]["updates"][0]["job_id"] == "9100"
