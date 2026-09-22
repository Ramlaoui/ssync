"""Uncached output routes use incremental SCP/cache storage."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import ssync.job_data_manager as job_data_manager_module
import ssync.web.app as app_module
from ssync.job_data_manager import JobDataManager
from ssync.models.job import JobState
from ssync.web.services import jobs


class _FakeConnection:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.get_calls = []

    def get(self, remote, *, local):
        self.get_calls.append((remote, local))
        Path(local).write_bytes(self.payload)


def _fake_manager(job_info, payload):
    connection = _FakeConnection(payload)

    class _SlurmClient:
        def get_job_details(self, conn, job_id, hostname):
            assert job_id == job_info.job_id
            assert hostname == job_info.hostname
            return job_info

        def read_job_output_compressed(self, *args, **kwargs):
            raise AssertionError("legacy whole-output base64 fetch was used")

    host = SimpleNamespace(host="cluster-host")
    manager = SimpleNamespace(
        slurm_client=_SlurmClient(),
        get_host_by_name=lambda hostname: host,
        _get_connection=lambda host_name: connection,
        fetch_job_output_compressed=lambda *args: (_ for _ in ()).throw(
            AssertionError("legacy whole-output base64 fetch was used")
        ),
    )
    return manager, connection


def _install_job_data_manager(monkeypatch, test_cache):
    data_manager = JobDataManager()
    data_manager.cache = test_cache
    monkeypatch.setattr(
        job_data_manager_module,
        "get_job_data_manager",
        lambda: data_manager,
    )
    return data_manager


@pytest.mark.asyncio
async def test_uncached_download_transfers_to_sqlite_and_streams_full_log(
    monkeypatch, test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    sample_job_info.stderr_file = None
    payload = b"header\n" + (b"x" * (2 * 1024 * 1024)) + b"\nEND\n"
    manager, connection = _fake_manager(sample_job_info, payload)
    _install_job_data_manager(monkeypatch, test_cache)
    monkeypatch.setattr(jobs, "get_cache", lambda: test_cache)
    monkeypatch.setattr(app_module, "get_slurm_manager", lambda: manager)

    response = await jobs.build_download_job_output_response(
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        output_type="stdout",
        compressed=False,
        get_slurm_manager=lambda: manager,
    )
    chunks = [chunk async for chunk in response.body_iterator]

    assert b"".join(chunks) == payload
    assert max(map(len, chunks)) <= 64 * 1024
    assert len(connection.get_calls) == 1
    assert response.headers["x-original-size"] == str(len(payload))


@pytest.mark.asyncio
async def test_uncached_terminal_stream_uses_bounded_cached_window(
    monkeypatch, test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    sample_job_info.stderr_file = None
    payload = b"header\n" + (b"x" * (2 * 1024 * 1024)) + b"\nEND\n"
    manager, connection = _fake_manager(sample_job_info, payload)
    _install_job_data_manager(monkeypatch, test_cache)
    monkeypatch.setattr(jobs, "get_cache", lambda: test_cache)
    monkeypatch.setattr(app_module, "get_slurm_manager", lambda: manager)

    request = SimpleNamespace(is_disconnected=lambda: asyncio.sleep(0, result=False))
    response = await jobs.build_stream_job_output_response(
        request=request,
        job_id=sample_job_info.job_id,
        host=sample_job_info.hostname,
        output_type="stdout",
        chunk_size=128,
        max_initial_bytes=1024,
        get_slurm_manager=lambda: manager,
    )
    events = [
        json.loads(line[6:])
        for chunk in [chunk async for chunk in response.body_iterator]
        for line in chunk.splitlines()
        if line.startswith("data: ")
    ]

    metadata = events[0]
    assert metadata == {
        "type": "metadata",
        "output_type": "stdout",
        "job_id": sample_job_info.job_id,
        "host": sample_job_info.hostname,
        "original_size": len(payload),
        "compression": "none",
        "source": "fresh",
        "truncated": True,
    }
    chunks = [event["data"] for event in events if event["type"] == "chunk"]
    assert len("".join(chunks).encode()) <= 1024
    assert "".join(chunks).endswith("END\n")
    assert any(event["type"] == "truncation_notice" for event in events)
    assert events[-1] == {"type": "complete"}
    assert len(connection.get_calls) == 1


@pytest.mark.asyncio
async def test_uncached_fetch_reports_missing_selected_output(
    monkeypatch, test_cache, sample_job_info
):
    sample_job_info.state = JobState.COMPLETED
    sample_job_info.stdout_file = None
    sample_job_info.stderr_file = None
    manager, _ = _fake_manager(sample_job_info, b"")
    _install_job_data_manager(monkeypatch, test_cache)
    monkeypatch.setattr(jobs, "get_cache", lambda: test_cache)
    monkeypatch.setattr(app_module, "get_slurm_manager", lambda: manager)

    assert (
        await jobs.fetch_and_cache_compressed_output(
            manager=manager,
            cache=test_cache,
            job_id=sample_job_info.job_id,
            host=sample_job_info.hostname,
            output_type="stdout",
            job_info=sample_job_info,
        )
        is None
    )
