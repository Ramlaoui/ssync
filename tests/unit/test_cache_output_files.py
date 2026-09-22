"""Tests for incremental local output-file cache storage."""

import gzip
import hashlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest

from ssync.cache import JobDataCache


@pytest.mark.parametrize("repeats", [20, 1500])
def test_text_output_sizes_are_utf8_bytes(test_cache, sample_job_info, repeats):
    content = "café 🌍\n" * repeats
    test_cache.cache_job(sample_job_info)
    test_cache.update_job_outputs(
        sample_job_info.job_id,
        sample_job_info.hostname,
        stdout_content=content,
        stderr_content=content,
    )
    job = test_cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)
    assert job.stdout_size == len(content.encode("utf-8"))
    assert job.stderr_size == len(content.encode("utf-8"))


def _decompress_open_output(cache, job_id, hostname, output_type):
    with cache.open_job_output(job_id, hostname, output_type) as opened:
        assert opened is not None
        blob, compression, original_size = opened
        assert compression == "gzip"
        return gzip.decompress(blob.read()), original_size


@pytest.mark.unit
def test_update_job_output_file_round_trips_binary_and_unicode(
    tmp_path, sample_job_info
):
    cache = JobDataCache(cache_dir=tmp_path / "cache", max_age_days=30)
    cache.cache_job(sample_job_info)
    payload = "προβλήτα\nこんにちは\n".encode("utf-8") + b"\x00\xff\x01"
    source = tmp_path / "stdout.log"
    source.write_bytes(payload)

    metadata = cache.update_job_output_file(
        sample_job_info.job_id,
        sample_job_info.hostname,
        "stdout",
        source,
    )

    assert metadata is not None
    assert metadata["output_type"] == "stdout"
    assert metadata["original_size"] == len(payload)
    assert metadata["compressed_size"] > 0
    assert metadata["compression"] == "gzip"
    restored, original_size = _decompress_open_output(
        cache, sample_job_info.job_id, sample_job_info.hostname, "stdout"
    )
    assert restored == payload
    assert original_size == len(payload)
    cache.close()


@pytest.mark.unit
def test_update_job_output_file_handles_giant_line_in_fixed_chunks(
    tmp_path, sample_job_info
):
    cache = JobDataCache(cache_dir=tmp_path / "cache", max_age_days=30)
    cache.cache_job(sample_job_info)
    size = 2 * 1024 * 1024
    source = tmp_path / "stderr.log"
    with source.open("wb") as stream:
        for _ in range(size // (64 * 1024)):
            stream.write(b"x" * (64 * 1024))

    metadata = cache.update_job_output_file(
        sample_job_info.job_id,
        sample_job_info.hostname,
        "stderr",
        source,
    )

    assert metadata["original_size"] == size
    with cache.open_job_output(
        sample_job_info.job_id, sample_job_info.hostname, "stderr"
    ) as opened:
        assert opened is not None
        blob, compression, original_size = opened
        assert compression == "gzip"
        assert original_size == size
        digest = hashlib.sha256()
        restored_size = 0
        with gzip.GzipFile(fileobj=blob, mode="rb") as decompressed:
            while chunk := decompressed.read(64 * 1024):
                digest.update(chunk)
                restored_size += len(chunk)
        expected_digest = hashlib.sha256()
        for _ in range(size // (64 * 1024)):
            expected_digest.update(b"x" * (64 * 1024))
        assert restored_size == size
        assert digest.digest() == expected_digest.digest()
    cache.close()


@pytest.mark.unit
def test_update_job_output_file_preserves_other_stream_and_completion_flags(
    tmp_path, sample_job_info
):
    cache = JobDataCache(cache_dir=tmp_path / "cache", max_age_days=30)
    cache.cache_job(sample_job_info)
    stdout_source = tmp_path / "stdout.log"
    stderr_source = tmp_path / "stderr.log"
    stdout_source.write_bytes(b"new stdout")
    stderr_source.write_bytes(b"keep stderr")

    cache.update_job_output_file(
        sample_job_info.job_id,
        sample_job_info.hostname,
        "stderr",
        stderr_source,
        mark_fetched_after_completion=True,
    )
    before = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)
    assert before is not None
    stderr_before = (
        before.stderr_compressed,
        before.stderr_size,
        before.stderr_compression,
    )

    cache.update_job_output_file(
        sample_job_info.job_id,
        sample_job_info.hostname,
        "stdout",
        stdout_source,
        mark_fetched_after_completion=True,
    )
    cache.update_job_output_file(
        sample_job_info.job_id,
        sample_job_info.hostname,
        "stdout",
        stdout_source,
    )

    after = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)
    assert after is not None
    assert (
        after.stderr_compressed,
        after.stderr_size,
        after.stderr_compression,
    ) == stderr_before
    assert cache.check_outputs_fetched_after_completion(
        sample_job_info.job_id, sample_job_info.hostname
    ) == (True, True)
    cache.close()


@pytest.mark.unit
def test_empty_file_and_missing_rows_have_explicit_results(tmp_path, sample_job_info):
    cache = JobDataCache(cache_dir=tmp_path / "cache", max_age_days=30)
    source = tmp_path / "empty.log"
    source.write_bytes(b"")

    assert (
        cache.update_job_output_file(
            sample_job_info.job_id,
            sample_job_info.hostname,
            "stdout",
            source,
        )
        is None
    )
    with cache.open_job_output(
        sample_job_info.job_id, sample_job_info.hostname, "stdout"
    ) as opened:
        assert opened is None

    cache.cache_job(sample_job_info)
    metadata = cache.update_job_output_file(
        sample_job_info.job_id,
        sample_job_info.hostname,
        "stdout",
        source,
    )
    assert metadata["original_size"] == 0
    restored, original_size = _decompress_open_output(
        cache, sample_job_info.job_id, sample_job_info.hostname, "stdout"
    )
    assert restored == b""
    assert original_size == 0
    cache.close()


@pytest.mark.unit
def test_open_job_output_blob_can_move_between_read_workers(tmp_path, sample_job_info):
    cache = JobDataCache(cache_dir=tmp_path / "cache", max_age_days=30)
    cache.cache_job(sample_job_info)
    source = tmp_path / "stdout.log"
    source.write_bytes(b"worker-safe output")
    cache.update_job_output_file(
        sample_job_info.job_id,
        sample_job_info.hostname,
        "stdout",
        source,
    )

    opened_context = cache.open_job_output(
        sample_job_info.job_id, sample_job_info.hostname, "stdout"
    )
    opened = opened_context.__enter__()
    try:
        assert opened is not None
        blob, _, _ = opened
        with ThreadPoolExecutor(max_workers=1) as executor:
            compressed = executor.submit(blob.read).result()
        assert gzip.decompress(compressed) == b"worker-safe output"
    finally:
        opened_context.__exit__(None, None, None)
        cache.close()


@pytest.mark.unit
def test_failed_compression_removes_temp_and_preserves_row(
    tmp_path, sample_job_info, monkeypatch
):
    cache = JobDataCache(cache_dir=tmp_path / "cache", max_age_days=30)
    cache.cache_job(sample_job_info)
    source = tmp_path / "stdout.log"
    source.write_bytes(b"will fail")

    def fail_write(self, chunk):
        raise RuntimeError("compression failed")

    monkeypatch.setattr(gzip.GzipFile, "write", fail_write)
    with pytest.raises(RuntimeError, match="compression failed"):
        cache.update_job_output_file(
            sample_job_info.job_id,
            sample_job_info.hostname,
            "stdout",
            source,
        )

    assert list(cache.cache_dir.glob(".ssync-output-*")) == []
    cached = cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)
    assert cached is not None
    assert cached.stdout_compressed is None
    cache.close()


@pytest.mark.unit
def test_blob_write_failure_rolls_back_and_removes_temp(
    tmp_path, sample_job_info, monkeypatch
):
    cache = JobDataCache(cache_dir=tmp_path / "cache", max_age_days=30)
    cache.cache_job(sample_job_info)
    old_source = tmp_path / "old.log"
    old_source.write_bytes(b"old output")
    cache.update_job_output_file(
        sample_job_info.job_id,
        sample_job_info.hostname,
        "stdout",
        old_source,
    )
    new_source = tmp_path / "new.log"
    new_source.write_bytes(b"new output")

    original_get_connection = cache._get_connection

    class BrokenBlobConnection:
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def blobopen(self, *args, **kwargs):
            raise RuntimeError("blob write failed")

    @contextmanager
    def broken_connection(*, read_only=False):
        with original_get_connection(read_only=read_only) as connection:
            yield (connection if read_only else BrokenBlobConnection(connection))

    monkeypatch.setattr(cache, "_get_connection", broken_connection)
    with pytest.raises(RuntimeError, match="blob write failed"):
        cache.update_job_output_file(
            sample_job_info.job_id,
            sample_job_info.hostname,
            "stdout",
            new_source,
        )

    assert list(cache.cache_dir.glob(".ssync-output-*")) == []
    restored, _ = _decompress_open_output(
        cache, sample_job_info.job_id, sample_job_info.hostname, "stdout"
    )
    assert restored == b"old output"
    cache.close()
