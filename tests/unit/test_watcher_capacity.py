import asyncio
import re
import threading

import pytest

from ssync.models.watcher import (
    ActionType,
    WatcherAction,
    WatcherDefinition,
    WatcherInstance,
)
from ssync.watchers import engine as engine_module


def _watcher(*, actions=None):
    return WatcherInstance(
        id=1,
        job_id="123",
        hostname="cluster",
        definition=WatcherDefinition(
            pattern=r"READY=(.+)",
            captures=["value"],
            actions=actions or [],
        ),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_pattern_scan_runs_in_output_worker(monkeypatch, test_cache):
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()
    watcher = _watcher()
    update_threads = []
    monkeypatch.setattr(
        engine,
        "_update_watcher_variables",
        lambda _watcher_id, _variables: update_threads.append(threading.get_ident()),
    )
    monkeypatch.setattr(engine, "_update_watcher_trigger_count", lambda *_args: None)

    loop_thread = threading.get_ident()
    assert await engine._check_patterns_async(watcher, "READY=done\n") is True

    assert update_threads
    assert update_threads[0] != loop_thread


@pytest.mark.unit
@pytest.mark.asyncio
async def test_output_worker_waits_for_action_admission_and_releases_tasks(
    monkeypatch, test_cache
):
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()
    engine._action_admission = asyncio.Semaphore(1)
    watcher = _watcher(actions=[WatcherAction(type=ActionType.LOG_EVENT, params={})])
    monkeypatch.setattr(engine, "_update_watcher_variables", lambda *_args: None)
    monkeypatch.setattr(engine, "_update_watcher_trigger_count", lambda *_args: None)

    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def fake_execute_action(_watcher, _action, matched_text, _variables):
        calls.append(matched_text)
        started.set()
        await release.wait()
        return True, "ok"

    monkeypatch.setattr(engine, "_execute_action", fake_execute_action)

    await engine._check_patterns_async(watcher, "READY=first\n")
    await asyncio.wait_for(started.wait(), timeout=1)

    second_scan = asyncio.create_task(
        engine._check_patterns_async(watcher, "READY=second\n")
    )
    await asyncio.sleep(0.05)
    assert second_scan.done() is False
    assert len(engine._action_tasks) == 1

    release.set()
    await asyncio.wait_for(second_scan, timeout=1)
    await asyncio.sleep(0)

    assert calls == ["READY=first", "READY=second"]
    assert engine._action_tasks == []


@pytest.mark.asyncio
async def test_pathological_pattern_times_out_without_blocking_loop(
    monkeypatch, test_cache
):
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    monkeypatch.setattr(engine_module, "PATTERN_TIMEOUT_SECONDS", 0.15)
    engine = engine_module.WatcherEngine()
    watcher = _watcher()
    watcher.definition.pattern = r"(a+)+$"
    states = []
    monkeypatch.setattr(
        engine, "_update_watcher_state", lambda _id, state: states.append(state)
    )
    scan = asyncio.create_task(
        engine._check_patterns_async(watcher, "a" * 100_000 + "!")
    )
    ticks = 0
    while not scan.done():
        await asyncio.sleep(0.01)
        ticks += 1
    with pytest.raises(RuntimeError, match="matching time limit"):
        await scan
    assert ticks >= 3
    assert states == [engine_module.WatcherState.DISABLED]


@pytest.mark.parametrize(
    "pattern, content",
    [
        (r"(?P<label>READY)=(.+)$", "skip\nREADY=café\nREADY=done\n"),
        (r"(?i)(a)\1", "aa AA Aa b"),
        (r"(?<=start:)(.*?)(?=:end)", "start:123:end"),
        (r"^|$", "one\ntwo\n"),
        (r"(?=a)|a", "aa"),
    ],
)
def test_bounded_patterns_preserve_standard_matches(
    pattern, content, monkeypatch, test_cache
):
    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()
    watcher = _watcher()
    watcher.definition.pattern = pattern
    monkeypatch.setattr(engine, "_update_watcher_variables", lambda *_: None)
    monkeypatch.setattr(engine, "_update_watcher_trigger_count", lambda *_: None)
    engine._check_patterns(watcher, content)
    expected = [
        (m.span(), m.group(), m.groups())
        for m in re.finditer(pattern, content, re.MULTILINE)
    ]
    actual = [
        (m.span(), m.group(), m.groups())
        for m in engine._pattern_cache[pattern].finditer(content, timeout=1)
    ]
    assert actual == expected
