"""Focused capacity, cleanup, and lifecycle ownership checks for the web API."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from ssync.models.cluster import Host, SlurmHost
from ssync.utils.executors import WorkQueueFull
from ssync.web import lifecycle
from ssync.web.api import launch as launch_api
from ssync.web.schemas import LaunchJobRequest


def _slurm_host(hostname: str = "capacity.example.com") -> SlurmHost:
    return SlurmHost(
        host=Host(hostname=hostname, username="testuser"),
        work_dir=Path("/tmp"),
        scratch_dir=Path("/tmp"),
    )


def _route(app: FastAPI, path: str, method: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in route.methods:
            return route.endpoint
    raise AssertionError(f"Missing {method} {path}")


def _register_launch_routes(app: FastAPI, manager):
    launch_api.register_launch_routes(
        app,
        verify_api_key_dependency=lambda: True,
        verify_api_key_flexible_dependency=lambda: True,
        get_slurm_manager=lambda: manager,
        cache_middleware=SimpleNamespace(),
        cache_job_state_transition=lambda *args, **kwargs: None,
        broadcast_job_state=lambda *args, **kwargs: None,
        launch_event_manager=SimpleNamespace(),
        executor=None,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_route_propagates_remote_queue_full(monkeypatch):
    hostname = "capacity.example.com"
    manager = SimpleNamespace(
        slurm_hosts=[_slurm_host(hostname)],
        cancel_job=lambda *args, **kwargs: True,
    )
    app = FastAPI()
    _register_launch_routes(app, manager)

    async def fake_local(func, *args, **kwargs):
        if func.__name__ == "<lambda>":
            return manager
        return func(*args, **kwargs)

    async def saturated_remote(*args, **kwargs):
        raise WorkQueueFull("remote lane full")

    monkeypatch.setattr(launch_api, "run_local", fake_local)
    monkeypatch.setattr(launch_api, "run_remote", saturated_remote)

    cancel = _route(app, "/api/jobs/{job_id}/cancel", "POST")
    with pytest.raises(WorkQueueFull):
        await cancel("123", host=hostname, _authenticated=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_launch_admission_rejects_when_active_reservations_are_full():
    manager = SimpleNamespace(slurm_hosts=[_slurm_host()])
    app = FastAPI()
    _register_launch_routes(app, manager)
    launch = _route(app, "/api/jobs/launch", "POST")

    closure = {
        name: cell.cell_contents
        for name, cell in zip(launch.__code__.co_freevars, launch.__closure__ or ())
    }
    reservations = closure["active_launches"]
    reservations.update(object() for _ in range(6))
    try:
        request = LaunchJobRequest(
            script_content="#!/bin/bash\necho test\n", host="capacity.example.com"
        )
        with pytest.raises(WorkQueueFull):
            await launch(request, _authenticated=True)
    finally:
        reservations.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_temp_script_cleanup_falls_back_when_local_queue_is_full(
    monkeypatch, tmp_path
):
    script = tmp_path / "pending.sh"
    script.write_text("#!/bin/bash\n")

    async def saturated_local(*args, **kwargs):
        raise WorkQueueFull("local lane full")

    monkeypatch.setattr(launch_api, "run_local", saturated_local)
    await launch_api._cleanup_temp_script(script)
    assert not script.exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_temp_script_cleanup_survives_cancellation(monkeypatch, tmp_path):
    script = tmp_path / "cancelled.sh"
    script.write_text("#!/bin/bash\n")
    release = asyncio.Event()

    async def blocked_local(*args, **kwargs):
        await release.wait()

    monkeypatch.setattr(launch_api, "run_local", blocked_local)
    cleanup = asyncio.create_task(launch_api._cleanup_temp_script(script))
    await asyncio.sleep(0)
    cleanup.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cleanup
    assert not script.exists()
    release.set()
    await asyncio.sleep(0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lifecycle_cancels_health_and_waits_for_launch_before_disposable_pools(
    monkeypatch,
):
    class FakeApp:
        def __init__(self):
            self.handlers = {}

        def on_event(self, name):
            def decorator(handler):
                self.handlers[name] = handler
                return handler

            return decorator

    class FakeLaunchEvents:
        async def start(self):
            return None

        async def stop(self):
            return None

    class FakeCache:
        def close(self):
            return None

    app = FakeApp()
    launch_events = FakeLaunchEvents()
    cache_middleware = SimpleNamespace(cache=FakeCache())
    api_keys = SimpleNamespace(flush_usage_stats=lambda: None)
    executor = ThreadPoolExecutor(max_workers=1)
    shutdown_event = threading.Event()
    health_started = asyncio.Event()
    health_cancelled = asyncio.Event()
    launch_release = asyncio.Event()

    async def health_check():
        health_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            health_cancelled.set()
            raise

    async def fake_run_local(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def noop_async(*args, **kwargs):
        return None

    monkeypatch.setattr(lifecycle, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(lifecycle, "run_local", fake_run_local)
    monkeypatch.setattr(lifecycle, "start_cache_scheduler", noop_async)
    monkeypatch.setattr(lifecycle, "stop_cache_scheduler", noop_async)
    monkeypatch.setattr(lifecycle, "start_notification_monitor", noop_async)
    monkeypatch.setattr(lifecycle, "stop_notification_monitor", noop_async)
    monkeypatch.setattr("ssync.watchers.daemon.WatcherDaemon.stop_all", lambda: False)
    monkeypatch.setattr("ssync.watchers.service.start_watcher_service", noop_async)
    monkeypatch.setattr("ssync.watchers.service.stop_watcher_service", noop_async)

    from ssync import job_data_manager, request_coalescer
    from ssync.web import status_helpers
    from ssync.web.services import jobs as job_services

    monkeypatch.setattr(request_coalescer, "_coalescer", None)
    monkeypatch.setattr(job_data_manager, "_job_data_manager", None)
    monkeypatch.setattr(job_services, "_JOB_REFRESH_TASKS", {})
    monkeypatch.setattr(job_services, "_OUTPUT_REFRESH_TASKS", {})
    monkeypatch.setattr(status_helpers, "_STATUS_REFRESH_TASKS", {})
    monkeypatch.setattr(
        lifecycle,
        "run_background",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()),
    )

    launch_task = asyncio.create_task(launch_release.wait())
    launch_api._ACTIVE_LAUNCH_TASKS.add(launch_task)
    launch_task.add_done_callback(launch_api._forget_launch_task)
    try:
        lifecycle.register_lifecycle_events(
            app,
            thread_pool_size=1,
            launch_event_manager=launch_events,
            get_slurm_manager=lambda: object(),
            cache_middleware=cache_middleware,
            api_key_manager=api_keys,
            executors=[executor],
            shutdown_event=shutdown_event,
            periodic_connection_health_check=health_check,
        )
        await app.handlers["startup"]()
        await asyncio.wait_for(health_started.wait(), 1)

        shutdown = asyncio.create_task(app.handlers["shutdown"]())
        await asyncio.sleep(0)
        assert not shutdown.done()

        launch_release.set()
        await asyncio.wait_for(shutdown, 1)
        assert health_cancelled.is_set()
    finally:
        if not launch_task.done():
            launch_release.set()
        await asyncio.gather(launch_task, return_exceptions=True)
