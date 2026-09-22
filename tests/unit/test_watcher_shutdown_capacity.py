"""Shutdown and admission bounds for watcher background work."""

import asyncio
import threading

import pytest

from ssync.watchers import engine as engine_module
from ssync.watchers.service import WatcherService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_watcher_refresh_callbacks_are_precoalesced(monkeypatch, test_cache):
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()
    loop = asyncio.get_running_loop()
    callbacks = []
    queue_calls = []

    monkeypatch.setattr(
        loop,
        "call_soon_threadsafe",
        lambda callback, *args: callbacks.append((callback, args)),
    )
    monkeypatch.setattr(
        engine_module,
        "queue_task_once",
        lambda **kwargs: queue_calls.append(kwargs) or True,
    )

    for _ in range(1000):
        engine._schedule_watcher_refresh(7)

    assert len(callbacks) == 1
    callbacks[0][0](*callbacks[0][1])
    assert len(queue_calls) == 1
    callbacks.clear()
    for watcher_id in range(1000):
        engine._schedule_watcher_refresh(watcher_id)
    assert len(callbacks) == 64


@pytest.mark.unit
@pytest.mark.asyncio
async def test_watcher_stop_drops_refresh_callbacks_queued_by_finishing_action(
    monkeypatch, test_cache
):
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()
    refresh_release = asyncio.Event()

    async def blocked_refresh(_watcher_id):
        await refresh_release.wait()

    monkeypatch.setattr(engine, "_broadcast_watcher_snapshot", blocked_refresh)

    service = WatcherService.__new__(WatcherService)
    service.engine = engine
    service.running = True
    service._task = None
    service._lock_handle = None

    action_started = asyncio.Event()

    async def finishing_action():
        engine._schedule_watcher_refresh(7)
        action_started.set()

    action_task = asyncio.create_task(finishing_action())
    engine._action_tasks.append(action_task)
    await action_started.wait()

    await service.stop()
    await asyncio.sleep(0)

    assert engine._watcher_refresh_tasks == {}
    assert engine._watcher_refresh_pending == set()
    refresh_release.set()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_kind", ["shutdown", "scan"])
async def test_action_admission_releases_slot_after_late_cancellation(
    monkeypatch, test_cache, cancel_kind
):
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()
    engine._action_admission = asyncio.Semaphore(0)
    cancelled = threading.Event()
    executed = False

    async def execute_action(*_args):
        nonlocal executed
        executed = True
        return True, "unexpected"

    monkeypatch.setattr(engine, "_execute_action", execute_action)
    admission = asyncio.create_task(
        engine._admit_action(None, None, "match", {}, cancelled)
    )
    await asyncio.sleep(0)

    if cancel_kind == "shutdown":
        engine._shutdown = True
    else:
        cancelled.set()
    engine._action_admission.release()

    assert await asyncio.wait_for(admission, timeout=1) is None
    assert not executed
    assert engine._action_tasks == []
    assert engine._action_admission._value == 1
