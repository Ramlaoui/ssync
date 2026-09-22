"""Bounded reads for terminal watcher output cached in SQLite blobs."""

import gzip
import io
import tracemalloc
from dataclasses import replace
from types import SimpleNamespace

import pytest

import ssync.job_data_manager as job_data_manager_module
import ssync.watchers.engine as engine_module
import ssync.web.app as app_module
from ssync.models.job import JobState
from ssync.utils.output_buffer import read_output_from_position
from ssync.watchers.engine import OutputReadResult


class _BoundedReader:
    """Readable binary source that records and bounds decoder reads."""

    def __init__(self, payload: bytes):
        self._stream = io.BytesIO(payload)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise AssertionError("decoder requested an unbounded read")
        self.read_sizes.append(size)
        return self._stream.read(size)

    def tell(self) -> int:
        return self._stream.tell()

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._stream.seek(offset, whence)


@pytest.mark.unit
def test_large_compressed_log_reads_only_bounded_chunks_and_memory(
    monkeypatch,
):
    payload = b"begin\n" + (b"x" * (32 * 1024 * 1024)) + b"\nend\n"
    compressed = gzip.compress(payload, compresslevel=9)
    source = _BoundedReader(compressed)

    # Keep the assertion tied to the helper's fixed streaming chunk contract.
    import ssync.utils.output_buffer as output_buffer

    monkeypatch.setattr(output_buffer, "_DECODE_CHUNK_SIZE", 64 * 1024)
    tracemalloc.start()
    try:
        result = read_output_from_position(
            source,
            "gzip",
            0,
            32,
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert result == ("begin\n" + ("x" * 26), 32)
    assert source.read_sizes
    assert all(0 < size <= 64 * 1024 for size in source.read_sizes)
    # A 32 MiB decompressed stream must not be retained by an incremental scan.
    assert peak < 4 * 1024 * 1024


@pytest.mark.unit
@pytest.mark.parametrize("compression", ["none", "gzip"])
def test_cached_range_preserves_utf8_cursor_and_truncation_reset(compression):
    payload = "αβγδε".encode("utf-8")
    encoded = gzip.compress(payload) if compression == "gzip" else payload

    # This matches _slice_output_from_position: the final byte cuts into γ,
    # so decode(ignore) drops that incomplete character while the cursor still
    # advances over all three source bytes.
    assert read_output_from_position(io.BytesIO(encoded), compression, 2, 3) == ("β", 5)

    assert read_output_from_position(
        io.BytesIO(encoded), compression, len(payload), 8
    ) == (None, len(payload))

    # A stale cursor after truncation starts reading the replacement output.
    assert read_output_from_position(
        io.BytesIO(encoded), compression, len(payload) + 1, 4
    ) == ("αβ", 4)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_terminal_watcher_reads_cached_blob_without_full_text_fallback(
    monkeypatch, test_cache, tmp_path, sample_job_info
):
    job_info = replace(
        sample_job_info,
        state=JobState.COMPLETED,
        stdout_file=None,
        stderr_file=None,
    )
    test_cache.cache_job(job_info)
    source = tmp_path / "stdout.log"
    source.write_bytes("first α line\nsecond β line\n".encode("utf-8"))
    test_cache.update_job_output_file(
        job_info.job_id,
        job_info.hostname,
        "stdout",
        source,
    )

    monkeypatch.setattr(engine_module, "get_cache", lambda: test_cache)
    engine = engine_module.WatcherEngine()

    manager = SimpleNamespace(
        get_host_by_name=lambda hostname: SimpleNamespace(host=hostname),
        _get_connection=lambda host: object(),
    )
    monkeypatch.setattr(app_module, "get_slurm_manager", lambda: manager)
    data_manager = SimpleNamespace(
        cache=test_cache,
        _get_cached_output_content=lambda *args: pytest.fail(
            "watcher should read the cached blob incrementally"
        ),
    )
    monkeypatch.setattr(
        job_data_manager_module,
        "get_job_data_manager",
        lambda: data_manager,
    )

    # Old cache rows recorded character counts rather than UTF-8 bytes.
    # A cursor equal to that value is not necessarily at EOF.
    with test_cache._get_connection() as conn:
        conn.execute("UPDATE cached_jobs SET stdout_size = 6")
        conn.commit()
    result = await engine._get_new_output(job_info, "stdout", 6)

    assert result == OutputReadResult(
        content="α line\nsecond β line\n",
        next_position=len("first α line\nsecond β line\n".encode("utf-8")),
        file_path=None,
    )
