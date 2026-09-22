"""Regression coverage for bounded work and responsive requests under load."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi import FastAPI

from ssync.utils import executors
from ssync.utils.executors import BoundedThreadPoolExecutor, WorkQueueFull
from ssync.web.admission import RequestAdmissionMiddleware
from ssync.web.app import worker_queue_full


def test_cancelled_queue_entries_remain_bounded_until_dequeued():
    started = threading.Event()
    release = threading.Event()
    called = []
    pool = BoundedThreadPoolExecutor(1, max_queue=1, thread_name_prefix="test")

    def blocking():
        started.set()
        assert release.wait(2)

    try:
        running = pool.submit(blocking)
        assert started.wait(1)
        queued = pool.submit(lambda: called.append(True))
        assert queued.cancel()
        for _ in range(100):
            with pytest.raises(WorkQueueFull):
                pool.submit(lambda: None)
        assert pool.stats()["outstanding"] == 2
        assert pool.stats()["rejected"] == 100
    finally:
        release.set()
        pool.shutdown(wait=True)
    running.result()
    assert called == []
    assert pool.stats()["outstanding"] == 0


def test_shutdown_cancels_queued_work_and_releases_all_reservations():
    release = threading.Event()
    started = threading.Event()
    pool = BoundedThreadPoolExecutor(1, max_queue=2, thread_name_prefix="test")

    def blocking():
        started.set()
        release.wait(2)

    running = pool.submit(blocking)
    assert started.wait(1)
    queued = pool.submit(lambda: None)
    pool.shutdown(wait=False, cancel_futures=True)
    assert queued.cancelled()
    release.set()
    running.result(timeout=1)
    pool.shutdown(wait=True)
    assert pool.stats()["outstanding"] == 0


@pytest.mark.asyncio
async def test_saturated_remote_workers_leave_local_and_health_requests_responsive(
    monkeypatch,
):
    pool = BoundedThreadPoolExecutor(1, max_queue=0, thread_name_prefix="test-remote")
    monkeypatch.setattr(executors, "interactive_executor", pool)
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    app = FastAPI()
    app.add_exception_handler(WorkQueueFull, worker_queue_full)

    def blocked_ssh():
        loop.call_soon_threadsafe(started.set)
        assert release.wait(3)
        return {"done": True}

    @app.get("/remote")
    async def remote():
        return await executors.run_remote(blocked_ssh)

    @app.get("/cached")
    async def cached():
        return await executors.run_local(lambda: {"cached": True})

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        heavy = asyncio.create_task(client.get("/remote"))
        try:
            await asyncio.wait_for(started.wait(), 1)
            replies = await asyncio.wait_for(
                asyncio.gather(
                    client.get("/health"), client.get("/cached"), client.get("/remote")
                ),
                1,
            )
            assert [reply.status_code for reply in replies] == [200, 200, 503]
            assert replies[2].headers["retry-after"] == "1"
            assert not heavy.done()
        finally:
            release.set()
            await heavy
            pool.shutdown(wait=True)


@pytest.mark.asyncio
async def test_admission_holds_stream_slot_until_response_finishes_and_recovers():
    started = asyncio.Event()
    release = asyncio.Event()

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        if scope["path"].endswith("/download"):
            started.set()
            await release.wait()
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestAdmissionMiddleware(app, stream_limit=1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=middleware), base_url="http://test"
    ) as client:
        first = asyncio.create_task(client.get("/output/download"))
        try:
            await asyncio.wait_for(started.wait(), 1)
            assert (await client.get("/output/download")).status_code == 503
            assert (await client.get("/health")).status_code == 200
            assert (await client.get("/api/hosts")).status_code == 200
        finally:
            release.set()
            await first
        assert (await client.get("/output/download")).status_code == 200
        assert middleware.active["stream"] == 0


def test_cache_metadata_reads_do_not_wait_for_writer(test_cache, sample_job_info):
    test_cache.cache_job(sample_job_info)
    with ThreadPoolExecutor(1) as pool:
        with test_cache._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            future = pool.submit(
                test_cache.get_cached_job, sample_job_info.job_id, include_outputs=False
            )
            # WAL permits this read while the write transaction is still open.
            assert future.result(timeout=1).job_id == sample_job_info.job_id


def test_metadata_refresh_preserves_outputs_and_completion_fetch_flags(
    test_cache, sample_job_info
):
    from ssync.models.job import JobState

    sample_job_info.state = JobState.COMPLETED
    test_cache.cache_job(sample_job_info, script_content="#!/bin/bash\necho test")
    test_cache.update_job_outputs(
        sample_job_info.job_id,
        sample_job_info.hostname,
        stdout_content="long log\n" * 10000,
        stderr_content="failure details",
        mark_fetched_after_completion=True,
    )
    original = test_cache.get_cached_job(
        sample_job_info.job_id, sample_job_info.hostname
    )
    test_cache.cache_jobs([sample_job_info])
    test_cache.cache_job(sample_job_info)
    updated = test_cache.get_cached_job(
        sample_job_info.job_id, sample_job_info.hostname
    )
    assert updated.stdout_compressed == original.stdout_compressed
    assert updated.stderr_compressed == original.stderr_compressed
    assert updated.script_content == original.script_content
    assert test_cache.check_outputs_fetched_after_completion(
        sample_job_info.job_id, sample_job_info.hostname
    ) == (True, True)
    metadata = test_cache.get_cached_jobs(include_outputs=False)[0]
    assert metadata.stdout_compressed is None
    assert metadata.stderr_compressed is None
    assert metadata.stdout_size == original.stdout_size


@pytest.mark.asyncio
async def test_output_fetch_survives_owner_disconnect(test_cache, sample_job_info):
    from ssync.job_data_manager import JobDataManager

    manager = JobDataManager()
    manager.cache = test_cache
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def fetch(*args, **kwargs):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        test_cache.cache_job(sample_job_info)
        test_cache.update_job_outputs(
            sample_job_info.job_id,
            sample_job_info.hostname,
            stdout_content="stdout",
            stderr_content="stderr",
        )

    manager._do_fetch_outputs = fetch
    owner = asyncio.create_task(
        manager._fetch_outputs_from_cached_paths(sample_job_info, True)
    )
    await started.wait()
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner
    follower = asyncio.create_task(
        manager._fetch_outputs_from_cached_paths(sample_job_info, True)
    )
    release.set()
    assert await asyncio.wait_for(follower, 1) == ("stdout", "stderr")
    assert calls == 1
    assert not manager._output_fetch_futures


@pytest.mark.asyncio
async def test_force_output_refresh_waits_for_then_upgrades_normal_fetch(
    test_cache, sample_job_info
):
    from ssync.job_data_manager import JobDataManager

    manager = JobDataManager()
    manager.cache = test_cache
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def fetch(job, force_fetch=False):
        calls.append(force_fetch)
        if not force_fetch:
            started.set()
            await release.wait()

    manager._do_fetch_outputs = fetch
    normal = asyncio.create_task(
        manager._fetch_outputs_from_cached_paths(sample_job_info, include_content=False)
    )
    await started.wait()
    forced = [
        asyncio.create_task(
            manager._fetch_outputs_from_cached_paths(
                sample_job_info, True, include_content=False
            )
        )
        for _ in range(4)
    ]
    await asyncio.sleep(0)
    assert calls == [False]
    release.set()
    await asyncio.gather(normal, *forced)
    assert calls == [False, True]


@pytest.mark.asyncio
async def test_rate_limiter_bounds_and_expires_client_identities(monkeypatch):
    from starlette.requests import Request

    from ssync.web.security import inputs

    now = 100000.0
    monkeypatch.setattr(inputs.time, "time", lambda: now)
    limiter = inputs.RateLimiter()

    def request(index):
        return Request({"type": "http", "headers": [], "client": (str(index), 80)})

    for index in range(1024):
        assert await limiter.check_rate_limit(request(index))
    assert not await limiter.check_rate_limit(request(1024))
    assert len(limiter._request_counts) == 1024
    now += 3601
    assert await limiter.check_rate_limit(request(1024))
    assert len(limiter._request_counts) == 1
    assert len(limiter._burst_tokens) <= 1
    assert len(limiter._last_refill) <= 1


@pytest.mark.asyncio
async def test_slow_transfers_leave_cached_output_workers_available(monkeypatch):
    from ssync.utils import executors

    transfer = executors.BoundedThreadPoolExecutor(
        1, max_queue=0, thread_name_prefix="test-transfer"
    )
    output = executors.BoundedThreadPoolExecutor(
        1, max_queue=0, thread_name_prefix="test-output"
    )
    monkeypatch.setattr(executors, "transfer_executor", transfer)
    monkeypatch.setattr(executors, "output_executor", output)
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()

    def slow_copy():
        loop.call_soon_threadsafe(started.set)
        assert release.wait(2)

    task = asyncio.create_task(executors.run_transfer(slow_copy))
    try:
        await asyncio.wait_for(started.wait(), 1)
        assert (
            await asyncio.wait_for(executors.run_output(lambda: "cached"), 0.5)
            == "cached"
        )
        with pytest.raises(executors.WorkQueueFull):
            await executors.run_transfer(lambda: None)
    finally:
        release.set()
        await task
        transfer.shutdown()
        output.shutdown()
