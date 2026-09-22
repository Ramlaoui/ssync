"""Tests for bounded cached-output decoding."""

import gzip
import io

import pytest

from ssync.utils.output_buffer import decode_output, iter_output_tail
from ssync.web.services.jobs import limit_output_bytes


class _BoundedReader:
    """Binary reader that rejects unbounded reads and records ownership."""

    def __init__(self, payload: bytes, *, chunk_size: int = 4093):
        self._stream = io.BytesIO(payload)
        self._chunk_size = chunk_size
        self.read_sizes: list[int] = []
        self.closed_by_decoder = False

    @property
    def closed(self) -> bool:
        return self._stream.closed

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise AssertionError("decoder requested an unbounded read")
        self.read_sizes.append(size)
        return self._stream.read(min(size, self._chunk_size))

    def close(self) -> None:
        self.closed_by_decoder = True
        self._stream.close()

    def tell(self) -> int:
        return self._stream.tell()

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._stream.seek(offset, whence)


@pytest.mark.unit
@pytest.mark.parametrize("compression", ["none", "gzip"])
def test_small_and_unlimited_output_is_decoded_exactly(compression):
    payload = "header\nβeta\nlatest output\n"
    encoded = payload.encode("utf-8")
    source = gzip.compress(encoded) if compression == "gzip" else encoded

    assert decode_output(source, compression, max_bytes=None, lines=None) == (
        payload,
        False,
    )
    assert decode_output(source, compression, max_bytes=len(encoded), lines=None) == (
        payload,
        False,
    )


@pytest.mark.unit
def test_large_limit_matches_existing_beginning_and_latest_window():
    payload = "header\n" + ("middle\n" * 4000) + "final metrics\n"
    source = gzip.compress(payload.encode("utf-8"))

    actual = decode_output(source, "gzip", max_bytes=16 * 1024, lines=None)
    expected = limit_output_bytes(payload, 16 * 1024)

    assert actual == expected


@pytest.mark.unit
def test_small_limit_keeps_latest_bytes_and_ignores_split_utf8():
    payload = "prefix\n" + ("é" * 100) + "\ntail\n"
    source = gzip.compress(payload.encode("utf-8"))

    actual = decode_output(source, "gzip", max_bytes=5, lines=None)
    expected = limit_output_bytes(payload, 5)

    assert actual == expected
    assert actual[0].endswith("tail\n")
    assert actual[1] is True


@pytest.mark.unit
def test_lines_only_preserves_splitlines_tail_semantics():
    payload = "one\nδύο\nthree\n"
    source = gzip.compress(payload.encode("utf-8"))

    assert decode_output(source, "gzip", max_bytes=None, lines=2) == (
        "δύο\nthree\n",
        True,
    )
    assert decode_output(source, "gzip", max_bytes=None, lines=5) == (
        payload,
        False,
    )
    assert decode_output(source, "gzip", max_bytes=None, lines=0) == ("", True)


@pytest.mark.unit
def test_utf8_split_at_decode_chunk_boundary_is_safe():
    # 65535 ASCII bytes place the first byte of ``é`` at the end of the first
    # read requested from GzipFile.
    payload = b"a" * 65535 + "é\nsecond\n".encode("utf-8")
    source = gzip.compress(payload)

    result, truncated = decode_output(source, "gzip", max_bytes=None, lines=1)

    assert result == "second\n"
    assert truncated is True


@pytest.mark.unit
def test_huge_compressible_gzip_retains_only_bounded_response_window():
    payload = b"START\n" + (b"x" * (8 * 1024 * 1024)) + b"\nEND\n"
    source = gzip.compress(payload, compresslevel=9)

    result, truncated = decode_output(source, "gzip", max_bytes=16 * 1024, lines=None)

    assert truncated is True
    assert len(result.encode("utf-8")) <= 16 * 1024
    assert result.startswith("START\n")
    assert "bytes omitted; showing beginning and latest output" in result
    assert result.endswith("\nEND\n")


@pytest.mark.unit
def test_lines_with_byte_limit_stays_bounded_and_keeps_latest_line():
    payload = "".join(f"line-{index}\n" for index in range(10_000))
    source = gzip.compress(payload.encode("utf-8"))

    result, truncated = decode_output(source, "gzip", max_bytes=8192, lines=2)

    assert truncated is True
    assert len(result.encode("utf-8")) <= 8192
    assert result.endswith("line-9999\n")


@pytest.mark.unit
def test_empty_and_corrupted_content_are_discarded_cleanly():
    assert decode_output(b"", "gzip", max_bytes=None, lines=None) == ("", False)
    assert decode_output(gzip.compress(b""), "gzip", max_bytes=32, lines=None) == (
        "",
        False,
    )

    corrupted = gzip.compress(b"valid output\n")[:-5]
    assert decode_output(corrupted, "gzip", max_bytes=32, lines=None) == ("", False)
    assert decode_output(b"\xff", "none", max_bytes=None, lines=None) == ("", False)


@pytest.mark.unit
@pytest.mark.parametrize("compression", ["none", "gzip"])
def test_readable_source_is_streamed_without_unbounded_reads_or_closing(compression):
    payload = ("début " + ("é" * 200_000) + "\nfinal line\n").encode("utf-8")
    encoded = gzip.compress(payload) if compression == "gzip" else payload
    source = _BoundedReader(encoded)

    expected = decode_output(encoded, compression, max_bytes=8192, lines=1)
    actual = decode_output(source, compression, max_bytes=8192, lines=1)

    assert actual == expected
    assert source.read_sizes
    assert all(0 < size <= 64 * 1024 for size in source.read_sizes)
    assert not source.closed
    assert not source.closed_by_decoder


@pytest.mark.unit
@pytest.mark.parametrize("compression", ["none", "gzip"])
def test_readable_source_preserves_unlimited_line_and_unicode_semantics(compression):
    payload = ("α" * 100_000) + "\ntrailer\n"
    encoded = (
        gzip.compress(payload.encode("utf-8"))
        if compression == "gzip"
        else payload.encode("utf-8")
    )
    source = _BoundedReader(encoded, chunk_size=127)

    assert decode_output(source, compression, max_bytes=None, lines=None) == (
        payload,
        False,
    )
    assert not source.closed
    assert all(0 < size <= 64 * 1024 for size in source.read_sizes)


@pytest.mark.unit
@pytest.mark.parametrize("compression", ["none", "gzip"])
def test_iter_output_tail_streams_giant_line_and_rewinds_without_closing(compression):
    payload = ("α" * 300_000) + "\nlast line\n"
    encoded = (
        gzip.compress(payload.encode("utf-8"))
        if compression == "gzip"
        else payload.encode("utf-8")
    )
    source = _BoundedReader(encoded, chunk_size=127)

    chunks, truncated = iter_output_tail(source, compression, lines=1)
    result = "".join(chunks)

    assert result == "last line\n"
    assert truncated is True
    assert source.read_sizes
    assert all(0 < size <= 64 * 1024 for size in source.read_sizes)
    assert not source.closed
    assert not source.closed_by_decoder


@pytest.mark.unit
def test_iter_output_tail_matches_splitlines_keepends_and_suppresses_extra_tail_line():
    text = "skip\r\nkeep\vnext\u2028last\r\n"
    chunks, truncated = iter_output_tail(text.encode("utf-8"), "none", lines=3)

    assert "".join(chunks) == "".join(text.splitlines(keepends=True)[-3:])
    assert truncated is True

    chunks, truncated = iter_output_tail(text.encode("utf-8"), "none", lines=10)
    assert "".join(chunks) == text
    assert truncated is False
