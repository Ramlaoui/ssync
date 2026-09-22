"""Bounded decoding helpers for cached job output.

The web output service stores output as either UTF-8 bytes or gzip-compressed
UTF-8 bytes.  ``gzip.decompress`` materialises the complete uncompressed
payload before a response limit can be applied, which is particularly costly
for highly compressible logs.  This module reads gzip members in small chunks
and retains only the response window when a byte limit is requested.
"""

from __future__ import annotations

import codecs
import gzip
import io
import zlib
from collections import deque
from collections.abc import Iterator
from typing import BinaryIO

_DECODE_CHUNK_SIZE = 64 * 1024
_LARGE_LIMIT = 8192
_BREAK_CHARS = frozenset("\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029")


def build_output_omission_marker(omitted_bytes: int) -> str:
    """Return the omission marker used by the job-output response service."""

    return (
        "\n\n"
        f"[... {max(0, omitted_bytes):,} bytes omitted; showing beginning and latest output ...]"
        "\n\n"
    )


def compute_bounded_output_window(
    *,
    total_bytes: int,
    max_bytes: int,
    min_head_bytes: int = 1,
    max_head_bytes: int | None = None,
) -> tuple[int, int, str]:
    """Split the response budget between its beginning, marker and latest bytes."""

    marker = build_output_omission_marker(total_bytes - max_bytes)
    for _ in range(2):
        available = max(1, max_bytes - len(marker.encode("utf-8")))
        head_cap = max_head_bytes if max_head_bytes is not None else available
        head_bytes = max(min_head_bytes, min(head_cap, available // 4))
        tail_bytes = max(1, available - head_bytes)
        marker = build_output_omission_marker(total_bytes - head_bytes - tail_bytes)
    return head_bytes, tail_bytes, marker


OutputSource = bytes | BinaryIO


def _iter_output_chunks(
    compressed_data: OutputSource, compression: str
) -> Iterator[bytes]:
    """Yield decoded bytes in chunks no larger than 64 KiB."""

    if compression == "gzip":
        # GzipFile does not close a caller-provided file object when its own
        # wrapper is closed.  This lets callers pass a sqlite Blob or another
        # streaming reader without transferring ownership of it.
        source = (
            io.BytesIO(compressed_data)
            if isinstance(compressed_data, bytes)
            else compressed_data
        )
        # The read size also bounds each decompressed chunk handed to the
        # retention logic.  It also avoids an unbounded read from a caller's
        # stream, including streams that reject read(-1).
        with gzip.GzipFile(fileobj=source, mode="rb") as stream:
            while True:
                chunk = stream.read(_DECODE_CHUNK_SIZE)
                if not chunk:
                    return
                yield chunk

    if isinstance(compressed_data, bytes):
        for offset in range(0, len(compressed_data), _DECODE_CHUNK_SIZE):
            yield compressed_data[offset : offset + _DECODE_CHUNK_SIZE]
        return

    while True:
        chunk = compressed_data.read(_DECODE_CHUNK_SIZE)
        if not chunk:
            return
        yield bytes(chunk)


def _iter_decoded_text_chunks(
    compressed_data: OutputSource, compression: str
) -> Iterator[str]:
    """Decode output incrementally without retaining the decoded stream."""

    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    for chunk in _iter_output_chunks(compressed_data, compression):
        text = decoder.decode(chunk, final=False)
        if text:
            yield text
    final_text = decoder.decode(b"", final=True)
    if final_text:
        yield final_text


def _count_splitlines(chunks: Iterator[str]) -> int:
    """Count ``str.splitlines(keepends=True)`` records without retaining them."""

    line_count = 0
    line_has_content = False
    pending_carriage_return = False
    for text in chunks:
        for char in text:
            if pending_carriage_return:
                if char == "\n":
                    line_count += 1
                    line_has_content = False
                    pending_carriage_return = False
                    continue
                line_count += 1
                line_has_content = False
                pending_carriage_return = False

            line_has_content = True
            if char == "\r":
                pending_carriage_return = True
            elif char in _BREAK_CHARS:
                line_count += 1
                line_has_content = False

    if line_has_content:
        line_count += 1
    return line_count


def _iter_tail_text_chunks(chunks: Iterator[str], skip_lines: int) -> Iterator[str]:
    """Discard complete splitlines records, then yield bounded text chunks."""

    if skip_lines <= 0:
        for text in chunks:
            for offset in range(0, len(text), _DECODE_CHUNK_SIZE):
                yield text[offset : offset + _DECODE_CHUNK_SIZE]
        return

    pending_carriage_return = False
    remaining = skip_lines
    for text in chunks:
        offset = 0
        while offset < len(text):
            char = text[offset]
            if pending_carriage_return:
                if char == "\n":
                    remaining -= 1
                    pending_carriage_return = False
                    offset += 1
                    if remaining == 0:
                        break
                    continue
                remaining -= 1
                pending_carriage_return = False
                if remaining == 0:
                    break

            if char == "\r":
                pending_carriage_return = True
                offset += 1
                continue
            if char in _BREAK_CHARS:
                remaining -= 1
                offset += 1
                if remaining == 0:
                    break
                continue
            offset += 1

        if remaining == 0:
            if offset < len(text):
                for chunk_offset in range(offset, len(text), _DECODE_CHUNK_SIZE):
                    yield text[chunk_offset : chunk_offset + _DECODE_CHUNK_SIZE]
            for remaining_text in chunks:
                for chunk_offset in range(0, len(remaining_text), _DECODE_CHUNK_SIZE):
                    yield remaining_text[
                        chunk_offset : chunk_offset + _DECODE_CHUNK_SIZE
                    ]
            return


def _rewind_output_source(compressed_data: OutputSource, position: int) -> None:
    if isinstance(compressed_data, bytes):
        return
    try:
        compressed_data.seek(position)
    except (AttributeError, OSError, ValueError) as exc:
        raise ValueError("line-limited output requires a seekable source") from exc


def iter_output_tail(
    compressed_data: OutputSource,
    compression: str,
    lines: int,
) -> tuple[Iterator[str], bool]:
    """Return bounded text fragments for the last ``lines`` splitlines records.

    A seekable stream is decoded twice: the first pass counts logical
    ``splitlines(keepends=True)`` records and the second pass skips the prefix
    without ever retaining a complete line.  The returned boolean indicates
    whether any records were omitted.  Caller-provided streams remain open.
    """

    if lines < 0:
        raise ValueError("lines must be non-negative")

    position = 0
    if not isinstance(compressed_data, bytes):
        try:
            position = compressed_data.tell()
        except (AttributeError, OSError, ValueError) as exc:
            raise ValueError("line-limited output requires a seekable source") from exc

    total_lines = _count_splitlines(
        _iter_decoded_text_chunks(compressed_data, compression)
    )
    _rewind_output_source(compressed_data, position)

    if lines == 0:
        return iter(()), bool(total_lines)

    skip_lines = max(0, total_lines - lines)
    return (
        _iter_tail_text_chunks(
            _iter_decoded_text_chunks(compressed_data, compression), skip_lines
        ),
        bool(skip_lines),
    )


class _ByteWindow:
    """Retain a bounded beginning/latest byte window from a byte stream."""

    def __init__(self, max_bytes: int):
        self.max_bytes = max(0, max_bytes)
        self.total_bytes = 0

        if self.max_bytes < _LARGE_LIMIT:
            self._head_capacity = 0
            self._tail_capacity = self.max_bytes
        else:
            # The final policy can never need more than one quarter of the
            # limit for the head.  Reserving that amount up front leaves room
            # for every possible final tail while retaining at most max_bytes
            # bytes in total.
            self._head_capacity = max(1, self.max_bytes // 4)
            self._tail_capacity = self.max_bytes - self._head_capacity

        # Keep the complete stream while it still fits.  If it crosses the
        # limit, convert it once to the split head/tail representation below.
        # This is needed to preserve the exact untruncated result for outputs
        # whose final size is just under max_bytes.
        self._full = bytearray()
        self._head = bytearray()
        self._tail = bytearray()
        self._overflowed = False

    def _append_tail(self, chunk: bytes) -> None:
        if not self._tail_capacity or not chunk:
            return
        if len(chunk) >= self._tail_capacity:
            self._tail[:] = chunk[-self._tail_capacity :]
            return

        overflow = len(self._tail) + len(chunk) - self._tail_capacity
        if overflow > 0:
            del self._tail[:overflow]
        self._tail.extend(chunk)

    def add(self, chunk: bytes) -> None:
        if not chunk:
            return
        next_total = self.total_bytes + len(chunk)
        if not self.max_bytes:
            self.total_bytes = next_total
            return

        if not self._overflowed and next_total <= self.max_bytes:
            self._full.extend(chunk)
            self.total_bytes = next_total
            return

        if not self._overflowed:
            self._overflowed = True
            self._head.extend(self._full[: self._head_capacity])
            self._append_tail(self._full[-self._tail_capacity :])
            self._full.clear()

        if self._head_capacity:
            remaining = self._head_capacity - len(self._head)
            if remaining > 0:
                self._head.extend(chunk[:remaining])

        self._append_tail(chunk)
        self.total_bytes = next_total

    def retained_bytes(self) -> bytes:
        """Return the complete retained data when it fits the limit."""

        if self.total_bytes <= self.max_bytes:
            return bytes(self._full)
        return b""


class _LineTail:
    """Keep the same last-line behavior as ``str.splitlines(keepends=True)``."""

    def __init__(self, lines: int):
        self._limit = lines
        self._lines: deque[str] = deque(maxlen=lines)
        self._current: list[str] = []
        self._pending_carriage_return = False
        self.dropped = False

    def _emit(self) -> None:
        if len(self._lines) == self._limit:
            self.dropped = True
        self._lines.append("".join(self._current))
        self._current.clear()

    def consume(self, text: str) -> None:
        for char in text:
            if self._pending_carriage_return:
                if char == "\n":
                    self._current.append(char)
                    self._emit()
                    self._pending_carriage_return = False
                    continue
                self._emit()
                self._pending_carriage_return = False

            self._current.append(char)
            if char == "\r":
                self._pending_carriage_return = True
            elif char in _BREAK_CHARS:
                self._emit()

    def finish(self) -> str:
        if self._current:
            self._emit()
        return "".join(self._lines)


def _limit_lines(content: str, lines: int) -> tuple[str, bool]:
    """Apply existing line-tail semantics to a bounded decoded string."""

    if lines <= 0:
        return "", bool(content)
    chunks = content.splitlines(keepends=True)
    if len(chunks) <= lines:
        return content, False
    return "".join(chunks[-lines:]), True


def _decode_retained_window(
    window: _ByteWindow,
    *,
    max_bytes: int,
    lines: int | None,
) -> tuple[str, bool]:
    """Decode a completed byte window and apply optional line limiting."""

    total_bytes = window.total_bytes
    if total_bytes <= max_bytes:
        content = window.retained_bytes().decode("utf-8")
        truncated = False
    elif max_bytes <= 0:
        content = ""
        truncated = True
    elif max_bytes < _LARGE_LIMIT:
        content = bytes(window._tail).decode("utf-8", errors="ignore")
        truncated = True
    else:
        head_bytes, tail_bytes, marker = compute_bounded_output_window(
            total_bytes=total_bytes,
            max_bytes=max_bytes,
        )
        marker_bytes = marker.encode("utf-8")
        if len(marker_bytes) >= max_bytes:
            content = bytes(window._tail[-max_bytes:]).decode("utf-8", errors="ignore")
        else:
            head = bytes(window._head[:head_bytes]).decode("utf-8", errors="ignore")
            tail = bytes(window._tail[-tail_bytes:]).decode("utf-8", errors="ignore")
            content = f"{head}{marker}{tail}"
        truncated = True

    if lines is None:
        return content, truncated
    limited, line_truncated = _limit_lines(content, lines)
    return limited, truncated or line_truncated


def decode_output(
    compressed_data: OutputSource,
    compression: str,
    *,
    max_bytes: int | None,
    lines: int | None,
) -> tuple[str, bool]:
    """Decode cached UTF-8 output and return ``(text, truncated)``.

    Gzip data is decompressed incrementally with 64 KiB output reads.  When
    ``max_bytes`` is provided, only a bounded beginning/latest byte window is
    retained.  The existing output policy is preserved: limits below 8192
    bytes return the latest bytes, while larger limits include the beginning,
    the exact omission marker, and the latest bytes.

    ``lines`` without ``max_bytes`` retains the latest requested lines, which
    preserves the old API's behavior.  That mode can remain unbounded for a
    single very long line; callers requiring a memory bound should provide
    ``max_bytes``.  With both options, the byte window is applied first and
    line limiting is then applied to the bounded result.

    Empty input and malformed gzip or UTF-8 input return ``("", False)``.
    Partial decoded data is discarded on an error, matching the service's
    previous failure behavior rather than presenting a misleading fragment.
    """

    if not compressed_data:
        return "", False

    limit = None if max_bytes is None else max(0, max_bytes)
    total_bytes = 0

    try:
        if limit is not None:
            window = _ByteWindow(limit)
            validator = codecs.getincrementaldecoder("utf-8")("strict")
            for chunk in _iter_output_chunks(compressed_data, compression):
                total_bytes += len(chunk)
                validator.decode(chunk, final=False)
                window.add(chunk)
            validator.decode(b"", final=True)
            # Keep the count from the source of truth on the window.
            window.total_bytes = total_bytes
            return _decode_retained_window(window, max_bytes=limit, lines=lines)

        if lines is None:
            decoded = bytearray()
            for chunk in _iter_output_chunks(compressed_data, compression):
                decoded.extend(chunk)
            return bytes(decoded).decode("utf-8"), False

        validator = codecs.getincrementaldecoder("utf-8")("strict")
        line_tail = _LineTail(lines) if lines > 0 else None
        for chunk in _iter_output_chunks(compressed_data, compression):
            total_bytes += len(chunk)
            text = validator.decode(chunk, final=False)
            if line_tail is not None:
                line_tail.consume(text)
        final_text = validator.decode(b"", final=True)
        if line_tail is not None:
            line_tail.consume(final_text)
            return line_tail.finish(), line_tail.dropped
        return "", bool(total_bytes)
    except (EOFError, OSError, UnicodeError, zlib.error):
        return "", False


def _read_output_range_once(
    compressed_data: OutputSource,
    compression: str,
    position: int,
    max_read_size: int,
) -> tuple[bytes, int]:
    """Read one bounded byte range and return ``(data, total_seen)``.

    The iterator stops as soon as the requested range is full.  ``total_seen``
    is therefore only the complete output size when the source reaches EOF;
    a stale cursor is detected from the bytes read, not legacy size metadata.
    """

    total_seen = 0
    retained = bytearray()
    for chunk in _iter_output_chunks(compressed_data, compression):
        chunk_end = total_seen + len(chunk)
        if chunk_end > position and len(retained) < max_read_size:
            start = max(0, position - total_seen)
            retained.extend(chunk[start : start + max_read_size - len(retained)])
        total_seen = chunk_end
        if len(retained) >= max_read_size:
            break
    return bytes(retained), total_seen


def read_output_from_position(
    compressed_data: OutputSource,
    compression: str,
    position: int,
    max_read_size: int,
) -> tuple[str | None, int]:
    """Read a bounded UTF-8 output range without materialising the full log.

    ``position`` and the returned cursor are offsets in the UTF-8 byte stream,
    matching :meth:`WatcherEngine._slice_output_from_position`.  If a cached
    output has been truncated and ``position`` is past its end, the cursor is
    reset to zero before reading. A seekable source is replayed only when
    EOF proves that the cursor was stale. Legacy size metadata stored
    character counts, so only the actual byte stream determines EOF.
    """

    original_position = position
    if compressed_data is None or compression not in {"none", "gzip"}:
        return None, original_position

    if max_read_size <= 0:
        return None, position

    source_start = None
    if not isinstance(compressed_data, bytes):
        try:
            source_start = compressed_data.tell()
        except (AttributeError, OSError, ValueError):
            pass

    try:
        retained, observed_total = _read_output_range_once(
            compressed_data, compression, position, max_read_size
        )
        if retained:
            return retained.decode("utf-8", "ignore"), position + len(retained)

        # An empty result at EOF means either the cursor is exactly at EOF or
        # it was beyond a non-empty output.  The latter resets to the start,
        # just as _slice_output_from_position does.
        if observed_total == 0 or position <= observed_total:
            return None, position
        position = 0

        if not isinstance(compressed_data, bytes):
            if source_start is None:
                return None, position
            compressed_data.seek(source_start)
        retained, _ = _read_output_range_once(
            compressed_data, compression, position, max_read_size
        )
        if not retained:
            return None, position
        return retained.decode("utf-8", "ignore"), position + len(retained)
    except (EOFError, OSError, ValueError, zlib.error):
        return None, original_position


__all__ = ["decode_output", "iter_output_tail", "read_output_from_position"]
