import asyncio

import pytest

from ssync.watchers.engine import HostCommandThrottler


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_release_unacquired_host_slot():
    throttler = HostCommandThrottler(max_concurrent_per_host=1)
    holder_started = asyncio.Event()
    release_holder = asyncio.Event()

    async def hold_slot():
        async with throttler.throttle("host"):
            holder_started.set()
            await release_holder.wait()

    holder = asyncio.create_task(hold_slot())
    await asyncio.wait_for(holder_started.wait(), timeout=1)

    async def wait_for_slot():
        async with throttler.throttle("host"):
            return True

    waiter = asyncio.create_task(wait_for_slot())
    for _ in range(20):
        if throttler.get_stats()["host"]["pending"] == 1:
            break
        await asyncio.sleep(0)
    assert throttler.get_stats()["host"]["pending"] == 1

    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    stats = throttler.get_stats()["host"]
    assert stats["pending"] == 0
    assert stats["in_use"] == 1
    assert stats["available_slots"] == 0

    release_holder.set()
    await holder
    stats = throttler.get_stats()["host"]
    assert stats["in_use"] == 0
    assert stats["available_slots"] == 1


@pytest.mark.asyncio
async def test_cancelled_holder_releases_acquired_host_slot_once():
    throttler = HostCommandThrottler(max_concurrent_per_host=1)
    acquired = asyncio.Event()
    release = asyncio.Event()

    async def run_command():
        async with throttler.throttle("host"):
            acquired.set()
            await release.wait()

    task = asyncio.create_task(run_command())
    await asyncio.wait_for(acquired.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    stats = throttler.get_stats()["host"]
    assert stats["pending"] == 0
    assert stats["in_use"] == 0
    assert stats["available_slots"] == 1
