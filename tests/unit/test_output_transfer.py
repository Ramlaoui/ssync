import asyncio
import gzip
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from ssync.job_data_manager import CompleteJobData
from ssync.models.job import JobState
from ssync.web.models import FileMetadata, JobOutputResponse
from ssync.web.schemas import CompleteJobDataResponse
from ssync.web.services import jobs
from ssync.web.services.output_transfer import (
    complete_job_response,
    full_output_response,
)


async def _json_body(response):
    return json.loads(b"".join([chunk async for chunk in response.body_iterator]))


def _patch_complete_data(
    monkeypatch, sample_job_info, *, script_content="#!/bin/sh\necho ok\n"
):
    complete_data = CompleteJobData(
        job_info=sample_job_info,
        script_content=script_content,
        stdout_content=None,
        stderr_content=None,
    )

    async def get_data(**kwargs):
        assert kwargs["include_outputs"] is False
        return complete_data, sample_job_info.hostname

    monkeypatch.setattr(jobs, "get_job_data_with_optional_host_search", get_data)


@pytest.mark.asyncio
async def test_full_cached_json_stream_preserves_unicode_and_all_content(
    test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    text = ('é "quote" \\ slash\n' * 40000) + "END"
    test_cache.cache_job(sample_job_info)
    test_cache.update_job_outputs(
        sample_job_info.job_id,
        sample_job_info.hostname,
        stdout_content=text,
        stderr_content="error\n",
        mark_fetched_after_completion=True,
    )
    host = SimpleNamespace(host=SimpleNamespace(hostname=sample_job_info.hostname))
    manager = SimpleNamespace(slurm_hosts=[host], get_host_by_name=lambda _: host)
    response = await full_output_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        output_type="both",
        get_slurm_manager=lambda: manager,
        cache_middleware=SimpleNamespace(cache=test_cache),
        job_manager=None,
    )
    chunks = [chunk async for chunk in response.body_iterator]
    payload = json.loads(b"".join(chunks))
    assert payload["stdout"] == text
    assert payload["stderr"] == "error\n"
    assert payload["content_truncated"] is False
    assert payload["content_limit_bytes"] is None
    assert max(map(len, chunks)) < 6 * 64 * 1024


@pytest.mark.asyncio
async def test_complete_job_response_preserves_schema_and_full_cached_outputs(
    monkeypatch, test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    test_cache.cache_job(sample_job_info)
    stdout = 'header "quoted" \\ path\né line\n' * 200
    stderr = "stderr first\nfinal\n"
    test_cache.update_job_outputs(
        sample_job_info.job_id,
        sample_job_info.hostname,
        stdout_content=stdout,
        stderr_content=stderr,
        mark_fetched_after_completion=True,
    )
    _patch_complete_data(monkeypatch, sample_job_info)

    response = await complete_job_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        include_outputs=True,
        lines=None,
        get_slurm_manager=lambda: pytest.fail("complete response should use cache"),
        cache=test_cache,
    )
    payload = await _json_body(response)

    assert set(payload) == set(CompleteJobDataResponse.model_fields)
    assert payload["job_id"] == sample_job_info.job_id
    assert payload["hostname"] == sample_job_info.hostname
    assert payload["script_content"] == "#!/bin/sh\necho ok\n"
    assert payload["script_length"] == len("#!/bin/sh\necho ok\n")
    assert payload["stdout"] == stdout
    assert payload["stderr"] == stderr
    cached = test_cache.get_cached_job(
        sample_job_info.job_id, sample_job_info.hostname, include_outputs=False
    )
    assert payload["stdout_metadata"]["size_bytes"] == cached.stdout_size
    assert payload["stderr_metadata"]["size_bytes"] == cached.stderr_size
    assert payload["data_completeness"] == {
        "job_info": True,
        "script": True,
        "outputs": True,
    }


@pytest.mark.asyncio
async def test_complete_job_response_lines_uses_literal_newline_tail(
    monkeypatch, test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    test_cache.cache_job(sample_job_info)
    stdout = "zero\none\ntwo\nthree\n"
    stderr = "err-zero\nerr-one\nerr-two"
    test_cache.update_job_outputs(
        sample_job_info.job_id,
        sample_job_info.hostname,
        stdout_content=stdout,
        stderr_content=stderr,
        mark_fetched_after_completion=True,
    )
    _patch_complete_data(monkeypatch, sample_job_info)

    response = await complete_job_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        include_outputs=True,
        lines=2,
        get_slurm_manager=lambda: pytest.fail("complete response should use cache"),
        cache=test_cache,
    )
    payload = await _json_body(response)

    assert payload["stdout"] == "\n".join(stdout.split("\n")[-2:])
    assert payload["stderr"] == "\n".join(stderr.split("\n")[-2:])
    assert payload["stdout_metadata"]["size_bytes"] == len(stdout.encode())
    assert payload["stderr_metadata"]["size_bytes"] == len(stderr.encode())


@pytest.mark.asyncio
async def test_complete_job_response_without_outputs_skips_decode_and_ssh(
    monkeypatch, test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    test_cache.cache_job(sample_job_info)
    test_cache.update_job_outputs(
        sample_job_info.job_id,
        sample_job_info.hostname,
        stdout_content="cached output\n",
        stderr_content="cached error\n",
        mark_fetched_after_completion=True,
    )
    _patch_complete_data(monkeypatch, sample_job_info)

    cached_calls = []
    original_get_cached_job = test_cache.get_cached_job

    def get_cached_job(*args, **kwargs):
        cached_calls.append(kwargs.get("include_outputs"))
        return original_get_cached_job(*args, **kwargs)

    def fail_open(*args, **kwargs):
        raise AssertionError("include_outputs=False must not open output blobs")

    monkeypatch.setattr(test_cache, "get_cached_job", get_cached_job)
    monkeypatch.setattr(test_cache, "open_job_output", fail_open)

    response = await complete_job_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        include_outputs=False,
        lines=None,
        get_slurm_manager=lambda: pytest.fail("SSH manager should not be used"),
        cache=test_cache,
    )

    assert response.stdout is None
    assert response.stderr is None
    assert response.data_completeness["outputs"] is True
    assert cached_calls == [False]


@pytest.mark.asyncio
async def test_complete_job_response_chunks_very_long_lines(
    monkeypatch, test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    test_cache.cache_job(sample_job_info)
    stdout = "x" * (2 * 1024 * 1024)
    test_cache.update_job_outputs(
        sample_job_info.job_id,
        sample_job_info.hostname,
        stdout_content=stdout,
        mark_fetched_after_completion=True,
    )
    _patch_complete_data(monkeypatch, sample_job_info)

    response = await complete_job_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        include_outputs=True,
        lines=None,
        get_slurm_manager=lambda: pytest.fail("complete response should use cache"),
        cache=test_cache,
    )
    chunks = [chunk async for chunk in response.body_iterator]
    payload = json.loads(b"".join(chunks))

    assert payload["stdout"] == stdout
    assert max(map(len, chunks)) <= 64 * 1024


@pytest.mark.asyncio
async def test_full_remote_json_removes_temporary_file(monkeypatch, tmp_path):
    created = []

    def copy(remote, local):
        assert remote == "/remote/log"
        created.append(Path(local))
        Path(local).write_bytes(b"full file\n")

    async def metadata(**kwargs):
        return JobOutputResponse(
            job_id="123",
            hostname="cluster",
            stdout_metadata=FileMetadata(path="/remote/log", exists=True),
        )

    monkeypatch.setattr(jobs, "get_job_output_response", metadata)
    conn = SimpleNamespace(get=copy)
    host = SimpleNamespace(host="cluster")
    manager = SimpleNamespace(
        get_host_by_name=lambda _: host, _get_connection=lambda _: conn
    )
    response = await full_output_response(
        job_id="123",
        host="cluster",
        output_type="stdout",
        get_slurm_manager=lambda: manager,
        cache_middleware=SimpleNamespace(
            cache=SimpleNamespace(get_cached_job=lambda *_, **__: None)
        ),
        job_manager=None,
    )
    assert created[0].exists()
    payload = json.loads(b"".join([chunk async for chunk in response.body_iterator]))
    assert payload["stdout"] == "full file\n"
    assert payload["stderr"] is None
    assert not created[0].exists()


@pytest.mark.asyncio
async def test_cancelled_remote_copy_cleans_up_after_worker_finishes(monkeypatch):
    created = []
    release = threading.Event()
    started = asyncio.Event()
    finished = asyncio.Event()
    loop = asyncio.get_running_loop()

    def copy(remote, local):
        created.append(Path(local))
        loop.call_soon_threadsafe(started.set)
        assert release.wait(2)
        Path(local).write_bytes(b"late result")
        loop.call_soon_threadsafe(finished.set)

    async def metadata(**kwargs):
        return JobOutputResponse(
            job_id="123",
            hostname="cluster",
            stdout_metadata=FileMetadata(path="/remote/log", exists=True),
        )

    monkeypatch.setattr(jobs, "get_job_output_response", metadata)
    host = SimpleNamespace(host="cluster")
    manager = SimpleNamespace(
        get_host_by_name=lambda _: host,
        _get_connection=lambda _: SimpleNamespace(get=copy),
    )
    task = asyncio.create_task(
        full_output_response(
            job_id="123",
            host="cluster",
            output_type="stdout",
            get_slurm_manager=lambda: manager,
            cache_middleware=SimpleNamespace(
                cache=SimpleNamespace(get_cached_job=lambda *_, **__: None)
            ),
            job_manager=None,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        await asyncio.wait_for(finished.wait(), 1)
    for _ in range(100):
        if not created[0].exists():
            break
        await asyncio.sleep(0.001)
    assert not created[0].exists()


@pytest.mark.asyncio
async def test_cached_download_streams_fixed_chunks(
    monkeypatch, test_cache, sample_job_info
):
    raw = b"x" * (2 * 1024 * 1024)  # One giant line must not be one response chunk.
    test_cache.cache_job(sample_job_info)
    test_cache.update_job_outputs(
        sample_job_info.job_id, sample_job_info.hostname, stdout_content=raw.decode()
    )
    monkeypatch.setattr(jobs, "get_cache", lambda: test_cache)
    response = await jobs.build_download_job_output_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        output_type="stdout",
        compressed=False,
        get_slurm_manager=lambda: None,
    )
    chunks = [chunk async for chunk in response.body_iterator]
    assert max(map(len, chunks)) <= 64 * 1024
    assert b"".join(chunks) == raw

    response = await jobs.build_download_job_output_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        output_type="stdout",
        compressed=True,
        get_slurm_manager=lambda: None,
    )
    assert (
        gzip.decompress(b"".join([chunk async for chunk in response.body_iterator]))
        == raw
    )


@pytest.mark.asyncio
async def test_full_output_line_limit_streams_giant_line_with_exact_delimiters(
    test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    text = "skipped\r\n" + "é" * (1024 * 1024) + "\r\nlast\n"
    test_cache.cache_job(sample_job_info)
    test_cache.update_job_outputs(
        sample_job_info.job_id,
        sample_job_info.hostname,
        stdout_content=text,
        mark_fetched_after_completion=True,
    )
    response = await full_output_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        output_type="stdout",
        get_slurm_manager=lambda: pytest.fail("cached output needs no host"),
        cache_middleware=SimpleNamespace(cache=test_cache),
        job_manager=None,
        lines=2,
    )
    chunks = [chunk async for chunk in response.body_iterator]
    payload = json.loads(b"".join(chunks))
    assert payload["stdout"] == "".join(text.splitlines(keepends=True)[-2:])
    assert payload["content_truncated"] is True
    assert payload["content_limit_bytes"] is None
    assert max(map(len, chunks)) < 6 * 64 * 1024


@pytest.mark.asyncio
@pytest.mark.parametrize("force_refresh", [False, True])
async def test_download_refresh_preserves_streamed_cache_behavior(
    monkeypatch, test_cache, sample_job_info, force_refresh
):
    test_cache.cache_job(sample_job_info)
    test_cache.update_job_outputs(
        sample_job_info.job_id, sample_job_info.hostname, stdout_content="old output"
    )
    refreshed = []

    async def fetch(**kwargs):
        refreshed.append(kwargs["output_type"])
        test_cache.update_job_outputs(
            sample_job_info.job_id,
            sample_job_info.hostname,
            stdout_content="fresh output",
        )
        return test_cache.get_cached_job(
            sample_job_info.job_id, sample_job_info.hostname, include_outputs=False
        )

    monkeypatch.setattr(jobs, "get_cache", lambda: test_cache)
    monkeypatch.setattr(jobs, "fetch_and_cache_compressed_output", fetch)
    response = await jobs.build_download_job_output_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        output_type="stdout",
        compressed=False,
        force_refresh=force_refresh,
        get_slurm_manager=lambda: None,
    )
    body = b"".join([chunk async for chunk in response.body_iterator])
    assert body == (b"fresh output" if force_refresh else b"old output")
    assert refreshed == (["stdout"] if force_refresh else [])
