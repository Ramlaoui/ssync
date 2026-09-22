import os
from pathlib import Path

import pytest

from ssync.models.watcher import WatcherDefinition
from ssync.watchers import engine as engine_module
from ssync.watchers import service as service_module
from ssync.watchers.service import WatcherService


@pytest.mark.unit
def test_watcher_service_lock_allows_single_owner(tmp_path, monkeypatch):
    lock_file = tmp_path / "watcher-service.lock"
    monkeypatch.setattr(WatcherService, "LOCK_FILE", lock_file)

    first = WatcherService()
    second = WatcherService()

    assert first._acquire_lock() is True
    assert second._acquire_lock() is False

    first._release_lock()
    assert second._acquire_lock() is True
    second._release_lock()


@pytest.mark.unit
def test_watcher_service_releases_lock_cleanly(tmp_path, monkeypatch):
    lock_file = tmp_path / "watcher-service.lock"
    monkeypatch.setattr(WatcherService, "LOCK_FILE", lock_file)

    service = WatcherService()
    assert service._acquire_lock() is True
    assert Path(lock_file).read_text() == str(os.getpid())

    service._release_lock()
    assert service._lock_handle is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_watcher_service_replaces_task_bound_to_closed_loop(
    monkeypatch, test_cache
):
    class ClosedLoop:
        @staticmethod
        def is_closed():
            return True

    class StaleTask:
        cancelled = False

        @staticmethod
        def done():
            return False

        @staticmethod
        def get_loop():
            return ClosedLoop()

        def cancel(self):
            self.cancelled = True

    monkeypatch.setattr(service_module, "get_cache", lambda: test_cache)
    service = WatcherService()
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    service.engine = engine_module.WatcherEngine()
    watcher_id = service.engine._store_watcher(
        "12345",
        "cluster",
        WatcherDefinition(name="resume", pattern=r"OUTPUT=(.+)"),
    )
    stale_task = StaleTask()
    service.engine.active_tasks[watcher_id] = stale_task
    monitor_calls = []

    async def fake_monitor(watcher_id_arg, job_id, hostname):
        monitor_calls.append((watcher_id_arg, job_id, hostname))

    monkeypatch.setattr(service.engine, "_monitor_watcher", fake_monitor)

    await service._check_for_new_watchers()

    replacement = service.engine.active_tasks[watcher_id]
    assert replacement is not stale_task
    assert stale_task.cancelled is True
    await replacement
    assert monitor_calls == [(watcher_id, "12345", "cluster")]
