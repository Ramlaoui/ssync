"""Unit tests for web job output response shaping."""

import asyncio
from types import SimpleNamespace

import pytest

from ssync.models.job import JobState
from ssync.web.services import jobs as job_services
from ssync.web.services.jobs import get_job_output_response


class _FakeCacheMiddleware:
    def __init__(self, cache):
        self.cache = cache

    async def get_cached_job_output(self, job_id, host):
        return None

    async def cache_job_output(self, job_id, host, response):
        return None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cached_metadata_only_skips_output_decode(
    monkeypatch, test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    test_cache.cache_job(sample_job_info)
    test_cache.update_job_outputs(
        sample_job_info.job_id,
        sample_job_info.hostname,
        stdout_content="alpha\nbeta\n",
        stderr_content="err\n",
        mark_fetched_after_completion=True,
    )

    def fail_decode(*args, **kwargs):
        raise AssertionError("cached output should not be decoded for metadata_only")

    monkeypatch.setattr("ssync.web.services.jobs.decode_cached_output", fail_decode)

    response = await get_job_output_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        lines=None,
        metadata_only=True,
        force_refresh=False,
        get_slurm_manager=lambda: SimpleNamespace(slurm_hosts=[]),
        cache_middleware=_FakeCacheMiddleware(test_cache),
        job_manager=None,
    )

    assert response.stdout is None
    assert response.stderr is None
    assert response.stdout_metadata.size_bytes == len("alpha\nbeta\n")
    assert response.stderr_metadata.size_bytes == len("err\n")
    assert response.stdout_metadata.exists is True
    assert response.stderr_metadata.exists is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cached_lines_returns_tail_without_losing_file_size(
    test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    test_cache.cache_job(sample_job_info)
    stdout_text = "one\ntwo\nthree\nfour\n"
    stderr_text = "err1\nerr2\nerr3\n"
    test_cache.update_job_outputs(
        sample_job_info.job_id,
        sample_job_info.hostname,
        stdout_content=stdout_text,
        stderr_content=stderr_text,
        mark_fetched_after_completion=True,
    )

    response = await get_job_output_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        lines=2,
        metadata_only=False,
        force_refresh=False,
        get_slurm_manager=lambda: SimpleNamespace(slurm_hosts=[]),
        cache_middleware=_FakeCacheMiddleware(test_cache),
        job_manager=None,
    )

    assert response.stdout == "three\nfour\n"
    assert response.stderr == "err2\nerr3\n"
    assert response.stdout_metadata.size_bytes == len(stdout_text)
    assert response.stderr_metadata.size_bytes == len(stderr_text)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_force_refresh_returns_cached_output_and_queues_background_refresh(
    monkeypatch, test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    test_cache.cache_job(sample_job_info)
    test_cache.update_job_outputs(
        sample_job_info.job_id,
        sample_job_info.hostname,
        stdout_content="alpha\nbeta\n",
        stderr_content="err\n",
        mark_fetched_after_completion=True,
    )

    def fail_fetch(*args, **kwargs):
        raise AssertionError("force_refresh should not fetch outputs inline")

    monkeypatch.setattr("ssync.web.services.jobs.fetch_outputs_for_job_info", fail_fetch)
    monkeypatch.setattr(
        "ssync.web.services.jobs.queue_job_output_refresh",
        lambda **_: True,
    )

    response = await get_job_output_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        lines=None,
        metadata_only=False,
        force_refresh=True,
        get_slurm_manager=lambda: SimpleNamespace(slurm_hosts=[]),
        cache_middleware=_FakeCacheMiddleware(test_cache),
        job_manager=None,
    )

    assert response.stdout == "alpha\nbeta\n"
    assert response.stderr == "err\n"
    assert response.cached is True
    assert response.stale is True
    assert response.refresh_queued is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_queue_job_output_refresh_reuses_existing_background_task(
    monkeypatch, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    key = (sample_job_info.hostname, sample_job_info.job_id)
    created = []
    started = asyncio.Event()
    release = asyncio.Event()

    def fake_refresh_job_output_in_background(**kwargs):
        created.append(kwargs)

        async def _runner():
            started.set()
            await release.wait()

        return _runner()

    job_services._OUTPUT_REFRESH_TASKS.pop(key, None)
    monkeypatch.setattr(
        "ssync.web.services.jobs.refresh_job_output_in_background",
        fake_refresh_job_output_in_background,
    )

    try:
        assert job_services.queue_job_output_refresh(
            job_info=sample_job_info,
            cache_middleware=None,
            job_manager=None,
            force_fetch=False,
            refresh_reason="test",
        )
        assert job_services.queue_job_output_refresh(
            job_info=sample_job_info,
            cache_middleware=None,
            job_manager=None,
            force_fetch=False,
            refresh_reason="test",
        )

        await asyncio.wait_for(started.wait(), timeout=1.0)
        assert len(created) == 1
        assert key in job_services._OUTPUT_REFRESH_TASKS
    finally:
        release.set()
        task = job_services._OUTPUT_REFRESH_TASKS.get(key)
        if task is not None:
            await task
        await asyncio.sleep(0)
        job_services._OUTPUT_REFRESH_TASKS.pop(key, None)
