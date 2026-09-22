import asyncio
from types import SimpleNamespace

import pytest

from ssync.request_coalescer import JobRequestCoalescer
from ssync.utils.executors import WorkQueueFull


def _job(job_id: str):
    return SimpleNamespace(job_id=job_id)


@pytest.mark.asyncio
async def test_arrivals_during_fetch_are_drained_by_same_worker():
    coalescer = JobRequestCoalescer(batch_window_ms=0, max_batch_size=10)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def fetch(hostname, job_ids):
        calls.append(job_ids)
        if len(calls) == 1:
            started.set()
            await release.wait()
        return [_job(job_id) for job_id in job_ids]

    first = asyncio.create_task(coalescer.fetch_job("1", "host", fetch))
    await asyncio.wait_for(started.wait(), timeout=1)
    second = asyncio.create_task(coalescer.fetch_job("2", "host", fetch))

    await asyncio.sleep(0)
    assert not second.done()
    release.set()
    assert [result.job_id for result in await asyncio.gather(first, second)] == [
        "1",
        "2",
    ]
    assert calls == [["1"], ["2"]]
    assert coalescer.get_stats()["outstanding_count"] == 0


@pytest.mark.asyncio
async def test_cancelling_one_waiter_does_not_cancel_shared_fetch():
    coalescer = JobRequestCoalescer(batch_window_ms=0)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetch(hostname, job_ids):
        started.set()
        await release.wait()
        return [_job(job_id) for job_id in job_ids]

    first = asyncio.create_task(coalescer.fetch_job("1", "host", fetch))
    await asyncio.wait_for(started.wait(), timeout=1)
    second = asyncio.create_task(coalescer.fetch_job("1", "host", fetch))
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    release.set()
    result = await asyncio.wait_for(second, timeout=1)
    assert result.job_id == "1"
    assert coalescer.get_stats()["outstanding_count"] == 0


@pytest.mark.asyncio
async def test_capacity_counts_unique_pending_and_in_flight_jobs():
    coalescer = JobRequestCoalescer(batch_window_ms=0, max_outstanding_jobs=1)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetch(hostname, job_ids):
        started.set()
        await release.wait()
        return [_job(job_id) for job_id in job_ids]

    first = asyncio.create_task(coalescer.fetch_job("1", "host", fetch))
    await asyncio.wait_for(started.wait(), timeout=1)

    with pytest.raises(WorkQueueFull):
        await coalescer.fetch_job("2", "host", fetch)

    release.set()
    await first

    # Completion releases capacity for a later unique job.
    result = await asyncio.wait_for(coalescer.fetch_job("2", "host", fetch), 1)
    assert result.job_id == "2"


@pytest.mark.asyncio
async def test_batch_fetch_failure_resolves_waiters_and_releases_capacity():
    coalescer = JobRequestCoalescer(batch_window_ms=0, max_outstanding_jobs=2)
    attempts = 0

    async def fetch(hostname, job_ids):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("offline")
        return [_job(job_id) for job_id in job_ids]

    first = asyncio.create_task(coalescer.fetch_job("1", "host", fetch))
    with pytest.raises(RuntimeError, match="offline"):
        await first
    assert coalescer.get_stats()["outstanding_count"] == 0

    result = await asyncio.wait_for(coalescer.fetch_job("1", "host", fetch), 1)
    assert result.job_id == "1"


@pytest.mark.asyncio
async def test_worker_cancellation_cleans_pending_and_in_flight_requests():
    coalescer = JobRequestCoalescer(batch_window_ms=0)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetch(hostname, job_ids):
        started.set()
        await release.wait()
        return [_job(job_id) for job_id in job_ids]

    waiter = asyncio.create_task(coalescer.fetch_job("1", "host", fetch))
    await asyncio.wait_for(started.wait(), timeout=1)
    worker = coalescer.batch_tasks["host"]
    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    with pytest.raises(asyncio.CancelledError):
        await worker

    assert coalescer.pending == {}
    assert coalescer.in_flight == {}
    assert coalescer.batch_tasks == {}
    assert coalescer.get_stats()["outstanding_count"] == 0


@pytest.mark.asyncio
async def test_close_cancels_workers_and_settles_waiters():
    coalescer = JobRequestCoalescer(batch_window_ms=0)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetch(hostname, job_ids):
        started.set()
        await release.wait()
        return [_job(job_id) for job_id in job_ids]

    waiter = asyncio.create_task(coalescer.fetch_job("1", "host", fetch))
    await asyncio.wait_for(started.wait(), timeout=1)
    await coalescer.close()

    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert coalescer.get_stats()["outstanding_count"] == 0
    assert not coalescer.batch_tasks
