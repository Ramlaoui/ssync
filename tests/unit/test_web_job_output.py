"""Unit tests for web job output response shaping."""

import asyncio
import base64
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


class _FakeRemoteResult:
    def __init__(self, stdout):
        self.stdout = stdout


class _FakeConnection:
    def __init__(self, stdout):
        self.stdout = stdout
        self.commands = []

    def run(self, command, **kwargs):
        self.commands.append((command, kwargs))
        return _FakeRemoteResult(self.stdout)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_live_stream_remote_chunk_decodes_base64_transport():
    payload = "Training Epoch 2: 7%\nValidation metrics: ok\n"
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    conn = _FakeConnection(encoded)

    decoded = await job_services.read_remote_file_chunk_text(
        conn,
        "/remote/slurm.out",
        start_offset=12,
        max_bytes=4096,
    )

    assert decoded == payload
    command, kwargs = conn.commands[0]
    assert "base64 -w0" in command
    assert "tail -c +13" in command
    assert kwargs["timeout"] == 30


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
        output_type="both",
        max_bytes=None,
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
        output_type="both",
        max_bytes=None,
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
        output_type="both",
        max_bytes=None,
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
async def test_cached_stdout_only_respects_requested_stream_and_max_bytes(
    monkeypatch, test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    test_cache.cache_job(sample_job_info)
    stdout_text = "0123456789"
    stderr_text = "stderr should stay untouched\n"
    test_cache.update_job_outputs(
        sample_job_info.job_id,
        sample_job_info.hostname,
        stdout_content=stdout_text,
        stderr_content=stderr_text,
        mark_fetched_after_completion=True,
    )

    original_decode = job_services.decode_cached_output

    def fail_decode_stderr(compressed_data, compression, output_type):
        if output_type == "stderr":
            raise AssertionError("stderr should not be decoded for stdout-only requests")
        return original_decode(compressed_data, compression, output_type)

    monkeypatch.setattr("ssync.web.services.jobs.decode_cached_output", fail_decode_stderr)

    response = await get_job_output_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        lines=None,
        output_type="stdout",
        max_bytes=4,
        metadata_only=False,
        force_refresh=False,
        get_slurm_manager=lambda: SimpleNamespace(slurm_hosts=[]),
        cache_middleware=_FakeCacheMiddleware(test_cache),
        job_manager=None,
    )

    assert response.output_type == "stdout"
    assert response.stdout == "6789"
    assert response.stderr is None
    assert response.stdout_metadata.size_bytes == len(stdout_text)
    assert response.stderr_metadata is None
    assert response.content_truncated is True
    assert response.content_limit_bytes == 4


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
