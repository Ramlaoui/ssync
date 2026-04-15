import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_run_watchers_module():
    module_path = Path(__file__).resolve().parents[2] / "utils" / "run_watchers.py"
    spec = importlib.util.spec_from_file_location("test_run_watchers_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shutdown_engine_tasks_cancels_active_and_action_tasks():
    module = _load_run_watchers_module()

    async def worker():
        await asyncio.sleep(3600)

    active_task = asyncio.create_task(worker())
    action_task = asyncio.create_task(worker())
    engine = SimpleNamespace(active_tasks={1: active_task}, _action_tasks=[action_task])

    await module._shutdown_engine_tasks(engine, timeout_seconds=0.05)

    assert engine.active_tasks == {}
    assert engine._action_tasks == []
    assert active_task.done()
    assert action_task.done()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shutdown_engine_tasks_times_out_for_stubborn_tasks(caplog):
    module = _load_run_watchers_module()
    release = asyncio.Event()

    async def stubborn_worker():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await release.wait()
            raise

    task = asyncio.create_task(stubborn_worker())
    engine = SimpleNamespace(active_tasks={1: task}, _action_tasks=[])

    await asyncio.wait_for(
        module._shutdown_engine_tasks(engine, timeout_seconds=0.01),
        timeout=0.2,
    )

    assert engine.active_tasks == {}
    assert engine._action_tasks == []
    assert "Timed out waiting" in caplog.text

    if not task.done():
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
