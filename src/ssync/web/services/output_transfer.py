"""Stream complete log responses without constructing a full JSON string in RAM."""

import asyncio
import codecs
import gzip
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from ...utils.executors import run_local, run_remote, run_transfer
from ...utils.output_buffer import iter_output_tail


@contextmanager
def _open_file(path):
    with path.open("rb") as raw:
        yield raw, "none", path.stat().st_size


def _iter_text(raw, compression, lines=None):
    """Decode fixed-size chunks, optionally skipping all but the last N lines."""
    skip_lines = 0
    if lines:
        reader = gzip.GzipFile(fileobj=raw) if compression == "gzip" else raw
        try:
            count = 0
            while chunk := reader.read(64 * 1024):
                count += chunk.count(b"\n")
            skip_lines = max(0, count + 1 - lines)
        finally:
            if reader is not raw:
                reader.close()
        raw.seek(0)
    reader = gzip.GzipFile(fileobj=raw) if compression == "gzip" else raw
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    try:
        while chunk := reader.read(64 * 1024):
            if skip_lines:
                breaks = chunk.count(b"\n")
                if breaks < skip_lines:
                    skip_lines -= breaks
                    continue
                offset = 0
                for _ in range(skip_lines):
                    offset = chunk.index(b"\n", offset) + 1
                chunk = chunk[offset:]
                skip_lines = 0
            yield decoder.decode(chunk)
        yield decoder.decode(b"", final=True)
    finally:
        if reader is not raw:
            reader.close()


def stream_output_json(
    response, sources, *, cleanup=lambda: None, lines=None, splitlines=False
):
    """Share the complete-output and complete-job JSON streaming policy."""

    cleaned = False

    def cleanup_once():
        nonlocal cleaned
        if not cleaned:
            cleaned = True
            cleanup()

    def generate():
        try:
            excluded = {"stdout", "stderr"}
            truncated = False
            if splitlines:
                excluded.add("content_truncated")
            metadata = response.model_dump(mode="json", exclude=excluded)
            yield json.dumps(metadata)[:-1].encode()
            for stream in ("stdout", "stderr"):
                yield f',"{stream}":'.encode()
                if stream not in sources:
                    yield b"null"
                    continue
                with sources[stream]() as opened:
                    if opened is None:
                        yield b"null"
                        continue
                    raw, compression, _ = opened
                    yield b'"'
                    if splitlines and lines is not None:
                        chunks, omitted = iter_output_tail(raw, compression, lines)
                        truncated = truncated or omitted
                    else:
                        chunks = _iter_text(raw, compression, lines)
                    for text in chunks:
                        yield json.dumps(text, ensure_ascii=False)[1:-1].encode()
                    yield b'"'
            if splitlines:
                yield b',"content_truncated":' + (b"true" if truncated else b"false")
            yield b"}"
        finally:
            cleanup_once()

    return StreamingResponse(
        generate(),
        media_type="application/json",
        background=BackgroundTask(cleanup_once),
    )


async def complete_job_response(
    *, job_id, host, include_outputs, lines, get_slurm_manager, cache
):
    from ...job_data_manager import get_job_data_manager
    from ...models.job import JobState
    from .jobs import (
        build_complete_job_data_response,
        build_output_metadata,
        get_job_data_with_optional_host_search,
    )

    data, host = await get_job_data_with_optional_host_search(
        job_id=job_id,
        host=host,
        get_slurm_manager=get_slurm_manager,
        include_outputs=False,
    )
    if data is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    cached = await run_local(cache.get_cached_job, job_id, host, include_outputs=False)
    if (
        include_outputs
        and cached is not None
        and data.job_info.state not in (JobState.PENDING, JobState.RUNNING)
        and not (cached.stdout_size or cached.stderr_size)
    ):
        await get_job_data_manager()._fetch_outputs_from_cached_paths(
            data.job_info, include_content=False
        )
        cached = await run_local(
            cache.get_cached_job, job_id, host, include_outputs=False
        )
    response = build_complete_job_data_response(
        job_id=job_id, complete_data=data, include_outputs=False, lines=None
    )
    response.data_completeness["outputs"] = bool(
        cached and (cached.stdout_size or cached.stderr_size)
    )
    if not include_outputs or cached is None:
        return response
    sources = {}
    for stream in ("stdout", "stderr"):
        if (
            getattr(cached, f"{stream}_size")
            or getattr(cached, f"{stream}_compression") == "gzip"
        ):
            sources[stream] = lambda stream=stream: cache.open_job_output(
                job_id, host, stream
            )
            metadata = build_output_metadata(
                job_id=job_id,
                host=host,
                output_type=stream,
                path=getattr(data.job_info, f"{stream}_file"),
                content=None,
                size_bytes=getattr(cached, f"{stream}_size"),
                exists=True,
            )
            setattr(response, f"{stream}_metadata", metadata)
    return stream_output_json(response, sources, lines=lines)


async def full_output_response(
    *,
    job_id,
    host,
    output_type,
    get_slurm_manager,
    cache_middleware,
    job_manager,
    force_refresh=False,
    lines=None,
):
    """Preserve full-output JSON and refresh semantics without full decoding.

    Cached gzip is decoded incrementally. Uncached files use the existing SCP
    transport to temporary files, retaining ControlMaster and host limits.
    """
    from .jobs import get_job_output_response

    response = await get_job_output_response(
        job_id=job_id,
        host=host,
        output_type=output_type,
        get_slurm_manager=get_slurm_manager,
        cache_middleware=cache_middleware,
        job_manager=job_manager,
        force_refresh=force_refresh,
        lines=None,
        max_bytes=None,
        metadata_only=True,
    )
    cached = await run_local(
        cache_middleware.cache.get_cached_job,
        job_id,
        response.hostname,
        include_outputs=False,
    )
    sources = {}
    temporary_paths = []

    def cleanup():
        for path in temporary_paths:
            path.unlink(missing_ok=True)

    try:
        for stream in ("stdout", "stderr"):
            if output_type not in {stream, "both"}:
                continue
            metadata = getattr(response, f"{stream}_metadata")
            if cached and (
                getattr(cached, f"{stream}_size")
                or getattr(cached, f"{stream}_compression") == "gzip"
            ):
                sources[stream] = (
                    lambda stream=stream: cache_middleware.cache.open_job_output(
                        job_id, response.hostname, stream
                    )
                )
                continue
            if metadata is not None and metadata.exists and metadata.path:
                remote_path = metadata.path
                manager = await run_local(get_slurm_manager)
                target = manager.get_host_by_name(response.hostname)
                conn = await run_remote(manager._get_connection, target.host)

                def download(connection=conn, remote=remote_path):
                    with tempfile.NamedTemporaryFile(
                        prefix="ssync-output-", delete=False
                    ) as temp:
                        path = Path(temp.name)
                    try:
                        connection.get(remote, local=str(path))
                        return path
                    except BaseException:
                        path.unlink(missing_ok=True)
                        raise

                transfer = asyncio.create_task(run_transfer(download))
                try:
                    path = await asyncio.shield(transfer)
                except asyncio.CancelledError:

                    def cleanup_abandoned(done):
                        if not done.cancelled() and done.exception() is None:
                            done.result().unlink(missing_ok=True)

                    transfer.add_done_callback(cleanup_abandoned)
                    raise
                temporary_paths.append(path)
                sources[stream] = lambda path=path: _open_file(path)
                metadata.size_bytes = await run_local(lambda: path.stat().st_size)
                response.cached = False
    except BaseException:
        cleanup()
        raise

    return stream_output_json(
        response, sources, cleanup=cleanup, lines=lines, splitlines=True
    )
