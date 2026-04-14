"""Job-related orchestration helpers used by web routes."""

import asyncio
import base64
import gzip
import io
import json
import time
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from ...cache import get_cache
from ...models.job import JobState
from ...utils.logging import setup_logger
from ..models import (
    CompleteJobDataResponse,
    FileMetadata,
    JobInfoWeb,
    JobOutputResponse,
    JobStatusResponse,
)

logger = setup_logger(__name__)
_OUTPUT_THROTTLE_CACHE: dict[str, float] = {}


def build_output_metadata(
    *,
    job_id: str,
    host: str,
    output_type: str,
    path: Optional[str],
    content: Optional[str],
    size_bytes: Optional[int] = None,
    exists: Optional[bool] = None,
) -> Optional[FileMetadata]:
    if not path:
        return None
    return FileMetadata(
        path=path,
        size_bytes=size_bytes if size_bytes is not None else len(content) if content else 0,
        last_modified=None,
        exists=bool(content) if exists is None else exists,
        access_path=f"/api/jobs/{job_id}/output/download?host={host}&output_type={output_type}",
    )


def decode_cached_output(
    compressed_data: Optional[bytes], compression: str, output_type: str
) -> Optional[str]:
    if not compressed_data:
        return None

    try:
        if compression == "gzip":
            return gzip.decompress(compressed_data).decode("utf-8")
        return compressed_data.decode("utf-8")
    except Exception as exc:
        logger.error(f"Failed to decompress cached {output_type}: {exc}")
        return None


def get_cached_output_payload(
    cached_job, output_type: str
) -> tuple[Optional[bytes], str, int]:
    if output_type == "stdout":
        return (
            cached_job.stdout_compressed,
            cached_job.stdout_compression,
            cached_job.stdout_size,
        )
    return (
        cached_job.stderr_compressed,
        cached_job.stderr_compression,
        cached_job.stderr_size,
    )


def has_cached_output_payload(
    compressed_data: Optional[bytes], size_bytes: Optional[int]
) -> bool:
    return compressed_data is not None or size_bytes is not None


def limit_output_lines(content: Optional[str], lines: Optional[int]) -> Optional[str]:
    if content is None or lines is None:
        return content
    if lines <= 0:
        return ""

    chunks = content.splitlines(keepends=True)
    if len(chunks) <= lines:
        return content
    return "".join(chunks[-lines:])


def decode_cached_output_for_response(
    *,
    compressed_data: Optional[bytes],
    compression: str,
    output_type: str,
    lines: Optional[int],
    metadata_only: bool,
) -> Optional[str]:
    if metadata_only or compressed_data is None:
        return None

    content = decode_cached_output(compressed_data, compression, output_type)
    return limit_output_lines(content, lines)


def build_job_output_response(
    *,
    job_id: str,
    host: str,
    stdout_path: Optional[str],
    stderr_path: Optional[str],
    stdout_content: Optional[str],
    stderr_content: Optional[str],
    metadata_only: bool = False,
    stdout_size_bytes: Optional[int] = None,
    stderr_size_bytes: Optional[int] = None,
    stdout_exists: Optional[bool] = None,
    stderr_exists: Optional[bool] = None,
) -> JobOutputResponse:
    return JobOutputResponse(
        job_id=job_id,
        hostname=host,
        stdout=stdout_content if not metadata_only else None,
        stderr=stderr_content if not metadata_only else None,
        stdout_metadata=build_output_metadata(
            job_id=job_id,
            host=host,
            output_type="stdout",
            path=stdout_path,
            content=stdout_content,
            size_bytes=stdout_size_bytes,
            exists=stdout_exists,
        ),
        stderr_metadata=build_output_metadata(
            job_id=job_id,
            host=host,
            output_type="stderr",
            path=stderr_path,
            content=stderr_content,
            size_bytes=stderr_size_bytes,
            exists=stderr_exists,
        ),
    )


def iter_chunk_payloads(
    data: str, chunk_size: int, *, compressed: bool, start_index: int = 0
):
    for offset, chunk_start in enumerate(range(0, len(data), chunk_size)):
        yield {
            "type": "chunk",
            "index": start_index + offset,
            "data": data[chunk_start : chunk_start + chunk_size],
            "compressed": compressed,
        }


def encode_cached_output_for_stream(
    compressed_data: bytes, compression: str
) -> tuple[str, bool]:
    if compression == "gzip":
        return base64.b64encode(compressed_data).decode("utf-8"), True
    return compressed_data.decode("utf-8", errors="replace"), False


async def fetch_and_cache_compressed_output(
    *,
    manager,
    cache,
    job_id: str,
    host: str,
    output_type: str,
):
    result = await asyncio.to_thread(
        lambda: manager.fetch_job_output_compressed(job_id, host, output_type)
    )
    if result:
        cache.update_job_outputs_compressed(
            job_id,
            host,
            stdout_data=result if output_type == "stdout" else None,
            stderr_data=result if output_type == "stderr" else None,
        )
    return result


def format_sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def decode_download_content(
    content: bytes, compression: str, compressed: bool
) -> tuple[bytes, str, str]:
    if compressed:
        if compression != "gzip":
            content = gzip.compress(content)
        return content, "application/gzip", ".log.gz"

    if compression == "gzip":
        content = gzip.decompress(content)
    return content, "text/plain", ".log"


def output_path_for(job_info, output_type: str) -> Optional[str]:
    if not job_info:
        return None
    return job_info.stderr_file if output_type == "stderr" else job_info.stdout_file


async def stat_remote_file_size(conn, file_path: Optional[str]) -> int:
    if not file_path:
        return 0
    result = await asyncio.to_thread(
        conn.run,
        f"stat -c %s '{file_path}' 2>/dev/null || echo 0",
        hide=True,
        warn=True,
    )
    try:
        return int((result.stdout or "0").strip() or "0")
    except ValueError:
        return 0


async def read_remote_file_chunk_base64(
    conn,
    file_path: Optional[str],
    start_offset: int,
    max_bytes: int,
) -> Optional[str]:
    if not file_path or max_bytes <= 0:
        return None
    result = await asyncio.to_thread(
        conn.run,
        (
            f"tail -c +{start_offset + 1} '{file_path}' 2>/dev/null | "
            f"head -c {max_bytes} | base64 -w0"
        ),
        hide=True,
        warn=True,
        timeout=30,
    )
    encoded = (result.stdout or "").strip()
    return encoded or None


async def build_stream_job_output_response(
    *,
    request: Request,
    job_id: str,
    host: str,
    output_type: str,
    chunk_size: int,
    get_slurm_manager,
) -> StreamingResponse:
    manager = get_slurm_manager()
    slurm_host = manager.get_host_by_name(host)
    conn = await asyncio.to_thread(manager._get_connection, slurm_host.host)

    max_initial_bytes = 1024 * 1024
    max_live_chunk_bytes = min(chunk_size, 256 * 1024)

    async def generate():
        cache = get_cache()
        cached_job = cache.get_cached_job(job_id, host)

        async def resolve_job_info():
            nonlocal cached_job
            try:
                job_info = await asyncio.to_thread(
                    manager.slurm_client.get_job_details,
                    conn,
                    job_id,
                    host,
                )
                if job_info:
                    return job_info
            except Exception as exc:
                logger.debug(
                    f"Failed to refresh job info for output stream {job_id}: {exc}"
                )
            if cached_job and cached_job.job_info:
                return cached_job.job_info
            return None

        metadata = {
            "type": "metadata",
            "output_type": output_type,
            "job_id": job_id,
            "host": host,
        }
        job_info = await resolve_job_info()

        if job_info and job_info.state == JobState.RUNNING:
            file_path = output_path_for(job_info, output_type)
            current_size = await stat_remote_file_size(conn, file_path)
            start_offset = max(0, current_size - max_initial_bytes)
            chunk_index = 0
            position = current_size
            last_heartbeat_at = time.monotonic()
            last_refresh_at = 0.0

            metadata.update(
                {
                    "original_size": current_size,
                    "compression": "none",
                    "truncated": start_offset > 0,
                    "source": "live",
                }
            )
            yield format_sse_event(metadata)

            if start_offset > 0:
                yield format_sse_event(
                    {"type": "truncation_notice", "original_size": current_size}
                )

            initial_payload = await read_remote_file_chunk_base64(
                conn,
                file_path,
                start_offset,
                max_initial_bytes,
            )
            if initial_payload:
                for index in range(0, len(initial_payload), chunk_size):
                    yield format_sse_event(
                        {
                            "type": "chunk",
                            "index": chunk_index,
                            "data": initial_payload[index : index + chunk_size],
                            "compressed": False,
                        }
                    )
                    chunk_index += 1
                    await asyncio.sleep(0)

            while True:
                if await request.is_disconnected():
                    break

                now = time.monotonic()
                if now - last_refresh_at >= 2.0:
                    refreshed_job_info = await resolve_job_info()
                    if refreshed_job_info:
                        job_info = refreshed_job_info
                    last_refresh_at = now

                file_path = output_path_for(job_info, output_type)
                current_size = await stat_remote_file_size(conn, file_path)
                if current_size < position:
                    position = 0

                while file_path and current_size > position:
                    read_size = min(current_size - position, max_live_chunk_bytes)
                    payload = await read_remote_file_chunk_base64(
                        conn,
                        file_path,
                        position,
                        read_size,
                    )
                    if not payload:
                        break

                    for index in range(0, len(payload), chunk_size):
                        yield format_sse_event(
                            {
                                "type": "chunk",
                                "index": chunk_index,
                                "data": payload[index : index + chunk_size],
                                "compressed": False,
                            }
                        )
                        chunk_index += 1
                        await asyncio.sleep(0)

                    position += read_size
                    current_size = await stat_remote_file_size(conn, file_path)
                    last_heartbeat_at = now

                if (
                    job_info
                    and job_info.state != JobState.RUNNING
                    and current_size <= position
                ):
                    yield format_sse_event({"type": "complete"})
                    break

                if now - last_heartbeat_at >= 10.0:
                    yield format_sse_event(
                        {
                            "type": "chunk",
                            "index": chunk_index,
                            "data": "",
                            "compressed": False,
                        }
                    )
                    chunk_index += 1
                    last_heartbeat_at = now

                await asyncio.sleep(1)
            return

        if cached_job:
            compressed_data, compression, original_size = get_cached_output_payload(
                cached_job,
                output_type,
            )
            if compressed_data:
                encoded_data, is_compressed = encode_cached_output_for_stream(
                    compressed_data,
                    compression,
                )
                metadata.update(
                    {
                        "original_size": original_size,
                        "compression": compression,
                        "source": "cache",
                    }
                )
                yield format_sse_event(metadata)

                for chunk_payload in iter_chunk_payloads(
                    encoded_data,
                    chunk_size,
                    compressed=is_compressed,
                ):
                    yield format_sse_event(chunk_payload)
                    await asyncio.sleep(0)
                yield format_sse_event({"type": "complete"})
                return

        try:
            result = await fetch_and_cache_compressed_output(
                manager=manager,
                cache=cache,
                job_id=job_id,
                host=host,
                output_type=output_type,
            )
            if not result:
                yield format_sse_event(
                    {
                        "type": "error",
                        "message": "Output not found or not accessible",
                    }
                )
                return

            metadata.update(
                {
                    "original_size": result.get("original_size", 0),
                    "compression": "gzip" if result.get("compressed") else "none",
                    "truncated": result.get("truncated", False),
                    "source": "fresh",
                }
            )
            yield format_sse_event(metadata)

            for chunk_payload in iter_chunk_payloads(
                result["data"],
                chunk_size,
                compressed=result.get("compressed", False),
            ):
                yield format_sse_event(chunk_payload)
                await asyncio.sleep(0)

            if result.get("truncated"):
                yield format_sse_event(
                    {
                        "type": "truncation_notice",
                        "original_size": result["original_size"],
                    }
                )
            yield format_sse_event({"type": "complete"})
        except Exception as exc:
            logger.error(f"Error streaming output for job {job_id}: {exc}")
            yield format_sse_event({"type": "error", "message": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def build_download_job_output_response(
    *,
    job_id: str,
    host: str,
    output_type: str,
    compressed: bool,
    get_slurm_manager,
) -> StreamingResponse:
    cache = get_cache()
    manager = get_slurm_manager()
    cached_job = cache.get_cached_job(job_id, host)

    content = None
    compression = "none"
    original_size = 0
    if cached_job:
        content, compression, original_size = get_cached_output_payload(
            cached_job,
            output_type,
        )

    if content is None:
        result = await fetch_and_cache_compressed_output(
            manager=manager,
            cache=cache,
            job_id=job_id,
            host=host,
            output_type=output_type,
        )
        if result:
            content = base64.b64decode(result["data"])
            compression = result.get("compression", "none")
            original_size = result.get("original_size", 0)

    if content is None:
        raise HTTPException(status_code=404, detail="Output not found")

    content, media_type, filename_suffix = decode_download_content(
        content,
        compression,
        compressed,
    )
    filename = f"job_{job_id}_{output_type}{filename_suffix}"

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(len(content)),
            "X-Original-Size": str(original_size),
        },
    )


async def get_job_data_with_optional_host_search(
    *,
    job_id: str,
    host: Optional[str],
    get_slurm_manager,
):
    from ...job_data_manager import get_job_data_manager

    job_data_manager = get_job_data_manager()
    if host:
        return await job_data_manager.get_job_data(job_id, host), host

    manager = get_slurm_manager()
    for slurm_host in manager.slurm_hosts:
        resolved_host = slurm_host.host.hostname
        complete_data = await job_data_manager.get_job_data(job_id, resolved_host)
        if complete_data:
            return complete_data, resolved_host

    return None, host


async def fetch_outputs_for_job_info(job_info, *, force_fetch: bool = False):
    from ...job_data_manager import get_job_data_manager

    job_data_manager = get_job_data_manager()
    return await job_data_manager._fetch_outputs_from_cached_paths(
        job_info, force_fetch=force_fetch
    )


def build_complete_job_data_response(
    *,
    job_id: str,
    complete_data,
    include_outputs: bool,
    lines: Optional[int],
) -> CompleteJobDataResponse:
    response = CompleteJobDataResponse(
        job_id=job_id,
        hostname=complete_data.job_info.hostname,
        job_info=JobInfoWeb.from_job_info(complete_data.job_info),
        script_content=complete_data.script_content,
        script_length=len(complete_data.script_content)
        if complete_data.script_content
        else None,
        data_completeness={
            "job_info": True,
            "script": complete_data.script_content is not None,
            "outputs": (complete_data.stdout_content is not None)
            or (complete_data.stderr_content is not None),
        },
    )

    if not include_outputs:
        return response

    stdout_content = complete_data.stdout_content
    stderr_content = complete_data.stderr_content
    if lines and stdout_content:
        stdout_content = "\n".join(stdout_content.split("\n")[-lines:])
    if lines and stderr_content:
        stderr_content = "\n".join(stderr_content.split("\n")[-lines:])

    response.stdout = stdout_content
    response.stderr = stderr_content
    if stdout_content:
        response.stdout_metadata = build_output_metadata(
            job_id=complete_data.job_info.job_id,
            host=complete_data.job_info.hostname,
            output_type="stdout",
            path=complete_data.job_info.stdout_file,
            content=stdout_content,
        )
    if stderr_content:
        response.stderr_metadata = build_output_metadata(
            job_id=complete_data.job_info.job_id,
            host=complete_data.job_info.hostname,
            output_type="stderr",
            path=complete_data.job_info.stderr_file,
            content=stderr_content,
        )

    return response


def get_file_metadata_and_content(
    conn,
    file_path: str,
    file_type: str,
    job_id: str,
    hostname: str,
    lines: Optional[int] = None,
    metadata_only: bool = False,
) -> tuple[Optional[str], Optional[FileMetadata]]:
    """Return file content and metadata for a remote stdout/stderr path."""
    if not file_path or file_path == "N/A":
        return None, None

    try:
        metadata = FileMetadata(path=file_path)
        file_check = conn.run(
            f"test -f {file_path} && echo 'exists' || echo 'not found'", hide=True
        )
        if "exists" not in file_check.stdout:
            return None, metadata

        metadata.exists = True
        stat_result = conn.run(f"stat -c '%s %Y' {file_path}", hide=True)
        if stat_result.ok:
            size, mtime = stat_result.stdout.strip().split()
            metadata.size_bytes = int(size)
            metadata.last_modified = datetime.fromtimestamp(int(mtime)).isoformat()

        metadata.access_path = f"/api/jobs/{job_id}/files/{file_type}?host={hostname}"

        content = None
        if not metadata_only:
            cmd = f"tail -n {lines} {file_path}" if lines else f"cat {file_path}"
            result = conn.run(cmd, hide=True)
            content = result.stdout

        return content, metadata
    except Exception as exc:
        logger.error(f"Error reading {file_type} file {file_path}: {exc}")
        return f"[Error reading {file_type} file: {str(exc)}]", None


async def get_job_output_response(
    *,
    job_id: str,
    host: Optional[str],
    lines: Optional[int],
    metadata_only: bool,
    force_refresh: bool,
    get_slurm_manager,
    cache_middleware,
) -> JobOutputResponse:
    try:
        if force_refresh:
            logger.info(f"Force refresh requested for job {job_id} outputs")
            job_data, host = await get_job_data_with_optional_host_search(
                job_id=job_id,
                host=host,
                get_slurm_manager=get_slurm_manager,
            )

            if job_data and job_data.job_info:
                stdout_content, stderr_content = await fetch_outputs_for_job_info(
                    job_data.job_info,
                    force_fetch=True,
                )
                is_running = job_data.job_info.state == JobState.RUNNING
                cache_middleware.cache.update_job_outputs(
                    job_id=job_id,
                    hostname=host,
                    stdout_content=stdout_content,
                    stderr_content=stderr_content,
                    mark_fetched_after_completion=not is_running,
                )
                return build_job_output_response(
                    job_id=job_id,
                    host=host,
                    stdout_path=job_data.job_info.stdout_file,
                    stderr_path=job_data.job_info.stderr_file,
                    stdout_content=limit_output_lines(stdout_content, lines),
                    stderr_content=limit_output_lines(stderr_content, lines),
                    metadata_only=metadata_only,
                    stdout_size_bytes=len(stdout_content)
                    if stdout_content is not None
                    else None,
                    stderr_size_bytes=len(stderr_content)
                    if stderr_content is not None
                    else None,
                    stdout_exists=stdout_content is not None,
                    stderr_exists=stderr_content is not None,
                )

        cached_job = (
            cache_middleware.cache.get_cached_job(job_id, host) if host else None
        )
        if not cached_job and not host:
            manager = get_slurm_manager()
            for slurm_host in manager.slurm_hosts:
                cached_job = cache_middleware.cache.get_cached_job(
                    job_id,
                    slurm_host.host.hostname,
                )
                if cached_job:
                    host = slurm_host.host.hostname
                    break

        if cached_job and cached_job.job_info:
            is_running = cached_job.job_info.state == JobState.RUNNING
            is_pending = cached_job.job_info.state == JobState.PENDING
            is_completed = cached_job.job_info.state not in [
                JobState.PENDING,
                JobState.RUNNING,
            ]
            stdout_payload, stdout_compression, stdout_size = get_cached_output_payload(
                cached_job, "stdout"
            )
            stderr_payload, stderr_compression, stderr_size = get_cached_output_payload(
                cached_job, "stderr"
            )
            stdout_exists = has_cached_output_payload(stdout_payload, stdout_size)
            stderr_exists = has_cached_output_payload(stderr_payload, stderr_size)

            stdout_content = decode_cached_output_for_response(
                compressed_data=stdout_payload,
                compression=stdout_compression,
                output_type="stdout",
                lines=lines,
                metadata_only=metadata_only,
            )
            stderr_content = decode_cached_output_for_response(
                compressed_data=stderr_payload,
                compression=stderr_compression,
                output_type="stderr",
                lines=lines,
                metadata_only=metadata_only,
            )

            if is_running:
                throttle_key = f"output:{host}:{job_id}"
                min_interval = 10
                now = time.time()
                last_fetch = _OUTPUT_THROTTLE_CACHE.get(throttle_key, 0)
                if now - last_fetch >= min_interval or not stdout_exists:
                    logger.info(f"Job {job_id} is running, fetching fresh output")
                    stdout_content, stderr_content = await fetch_outputs_for_job_info(
                        cached_job.job_info,
                        force_fetch=True,
                    )
                    cache_middleware.cache.update_job_outputs(
                        job_id=job_id,
                        hostname=host,
                        stdout_content=stdout_content,
                        stderr_content=stderr_content,
                        mark_fetched_after_completion=False,
                    )
                    stdout_size = (
                        len(stdout_content) if stdout_content is not None else stdout_size
                    )
                    stderr_size = (
                        len(stderr_content) if stderr_content is not None else stderr_size
                    )
                    stdout_exists = stdout_content is not None
                    stderr_exists = stderr_content is not None
                    _OUTPUT_THROTTLE_CACHE[throttle_key] = now
                else:
                    logger.debug(
                        f"Job {job_id} output throttled, serving cached "
                        f"({now - last_fetch:.1f}s since last fetch)"
                    )
            elif is_completed:
                stdout_fetched_after, stderr_fetched_after = (
                    cache_middleware.cache.check_outputs_fetched_after_completion(
                        job_id,
                        host,
                    )
                )
                if not stdout_fetched_after or not stderr_fetched_after:
                    logger.info(
                        "Job %s is completed but outputs not fetched after completion, "
                        "fetching now",
                        job_id,
                    )
                    stdout_content, stderr_content = await fetch_outputs_for_job_info(
                        cached_job.job_info
                    )
                    stdout_size = (
                        len(stdout_content) if stdout_content is not None else stdout_size
                    )
                    stderr_size = (
                        len(stderr_content) if stderr_content is not None else stderr_size
                    )
                    stdout_exists = stdout_content is not None
                    stderr_exists = stderr_content is not None
            elif is_pending:
                logger.debug(f"Job {job_id} is pending, no outputs available yet")
                return build_job_output_response(
                    job_id=job_id,
                    host=host,
                    stdout_path=cached_job.job_info.stdout_file,
                    stderr_path=cached_job.job_info.stderr_file,
                    stdout_content=None,
                    stderr_content=None,
                    stdout_exists=False,
                    stderr_exists=False,
                )

            return build_job_output_response(
                job_id=job_id,
                host=host,
                stdout_path=cached_job.job_info.stdout_file,
                stderr_path=cached_job.job_info.stderr_file,
                stdout_content=limit_output_lines(stdout_content, lines),
                stderr_content=limit_output_lines(stderr_content, lines),
                metadata_only=metadata_only,
                stdout_size_bytes=stdout_size,
                stderr_size_bytes=stderr_size,
                stdout_exists=stdout_exists,
                stderr_exists=stderr_exists,
            )

        manager = get_slurm_manager()
        slurm_hosts = [
            slurm_host
            for slurm_host in manager.slurm_hosts
            if not host or slurm_host.host.hostname == host
        ]
        if host and not slurm_hosts:
            raise HTTPException(status_code=404, detail=f"Host '{host}' not found")

        job_info = None
        target_host = None
        for slurm_host in slurm_hosts:
            try:
                job_info = await asyncio.to_thread(
                    manager.get_job_info, slurm_host, job_id
                )
                if job_info:
                    target_host = slurm_host
                    break
            except Exception as exc:
                logger.debug(f"Error querying {slurm_host.host.hostname}: {exc}")
                continue

        if not job_info or not target_host:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        conn = await asyncio.to_thread(manager._get_connection, target_host.host)
        if not job_info.stdout_file or not job_info.stderr_file:
            stdout_path, stderr_path = await asyncio.to_thread(
                manager.slurm_client.get_job_output_files,
                conn,
                job_id,
                target_host.host.hostname,
            )
            if stdout_path and not job_info.stdout_file:
                job_info.stdout_file = stdout_path
            if stderr_path and not job_info.stderr_file:
                job_info.stderr_file = stderr_path

        stdout_content, stdout_metadata = await asyncio.to_thread(
            get_file_metadata_and_content,
            conn=conn,
            file_path=job_info.stdout_file,
            file_type="stdout",
            job_id=job_id,
            hostname=target_host.host.hostname,
            lines=lines,
            metadata_only=metadata_only,
        )
        stderr_content, stderr_metadata = await asyncio.to_thread(
            get_file_metadata_and_content,
            conn=conn,
            file_path=job_info.stderr_file,
            file_type="stderr",
            job_id=job_id,
            hostname=target_host.host.hostname,
            lines=lines,
            metadata_only=metadata_only,
        )

        response = JobOutputResponse(
            job_id=job_id,
            hostname=target_host.host.hostname,
            stdout=stdout_content,
            stderr=stderr_content,
            stdout_metadata=stdout_metadata,
            stderr_metadata=stderr_metadata,
        )
        await cache_middleware.cache_job_output(
            job_id,
            target_host.host.hostname,
            response,
        )
        return response
    except HTTPException:
        raise
    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Error in get_job_output for job {job_id} on {host}: {error_msg}")
        cached_output = await cache_middleware.get_cached_job_output(job_id, host)
        if cached_output:
            logger.info(
                f"Returning cached output for job {job_id} "
                f"(fetch failed: {error_msg[:200]})"
            )
            return cached_output

        if "connection" in error_msg.lower() or "ssh" in error_msg.lower():
            detail = f"SSH connection failed to {host}: {error_msg}"
        elif "timeout" in error_msg.lower():
            detail = f"Operation timed out while fetching output: {error_msg}"
        elif "not found" in error_msg.lower() or "no such file" in error_msg.lower():
            detail = f"Output file not found: {error_msg}"
        else:
            detail = f"Failed to read job output: {error_msg}"
        raise HTTPException(status_code=500, detail=detail)


async def get_job_script_payload(
    *,
    job_id: str,
    host: Optional[str],
    get_slurm_manager,
    cache_middleware,
) -> dict[str, Any]:
    manager = get_slurm_manager()
    slurm_hosts = manager.slurm_hosts
    if host:
        slurm_hosts = [entry for entry in slurm_hosts if entry.host.hostname == host]
        if not slurm_hosts:
            raise HTTPException(status_code=404, detail="Host not found")

    cached_script = await cache_middleware.get_cached_job_script(job_id, host)
    if cached_script:
        logger.info(f"Returning cached script for job {job_id}")
        return cached_script

    script_found_in_slurm = False
    for slurm_host in slurm_hosts:
        try:
            conn = await asyncio.to_thread(manager._get_connection, slurm_host.host)
            script_content = await asyncio.to_thread(
                manager.slurm_client.get_job_batch_script,
                conn,
                job_id,
                slurm_host.host.hostname,
            )
            if script_content is None:
                continue

            script_found_in_slurm = True
            local_source_dir = None
            cached_job = cache_middleware.cache.get_cached_job(
                job_id,
                slurm_host.host.hostname,
            )
            if cached_job:
                local_source_dir = cached_job.local_source_dir

            response = {
                "job_id": job_id,
                "hostname": slurm_host.host.hostname,
                "script_content": script_content,
                "content_length": len(script_content),
                "local_source_dir": local_source_dir,
            }
            await cache_middleware.cache_job_script(
                job_id,
                slurm_host.host.hostname,
                script_content,
            )
            return response
        except Exception as exc:
            logger.debug(f"Error getting script from {slurm_host.host.hostname}: {exc}")
            continue

    if not script_found_in_slurm and host:
        cached_script = await cache_middleware.get_cached_job_script(job_id, None)
        if cached_script:
            logger.info(
                f"Returning cached script for job {job_id} (found without host filter)"
            )
            return cached_script

    logger.warning(f"Script not found for job {job_id} in cache or Slurm")
    raise HTTPException(status_code=404, detail="Script not found")


async def refresh_job_in_background(
    *,
    job_id: str,
    host: Optional[str],
    get_slurm_manager,
    cache_middleware,
    job_manager,
) -> None:
    """Refresh job data from Slurm and broadcast updates via websocket."""
    try:
        logger.debug(f"Background refresh started for job {job_id} on host {host}")
        manager = get_slurm_manager()
        slurm_hosts = manager.slurm_hosts
        if host:
            slurm_hosts = [
                entry for entry in slurm_hosts if entry.host.hostname == host
            ]

        for slurm_host in slurm_hosts:
            try:
                job_info = await asyncio.to_thread(
                    manager.get_job_info, slurm_host, job_id
                )
                if not job_info:
                    continue

                job_web = JobInfoWeb.from_job_info(job_info)
                await cache_middleware.cache_job_status_response(
                    [
                        JobStatusResponse(
                            hostname=slurm_host.host.hostname,
                            jobs=[job_web],
                            total_jobs=1,
                            query_time=datetime.now(),
                        )
                    ]
                )
                await job_manager.broadcast_job_update(
                    job_id,
                    slurm_host.host.hostname,
                    {
                        "type": "job_update",
                        "job": job_web.model_dump(mode="json"),
                        "source": "background_refresh",
                    },
                )
                logger.debug(
                    f"Background refresh completed for job {job_id}, broadcasted update"
                )
                return
            except Exception as exc:
                logger.debug(
                    f"Failed to refresh job {job_id} from host {slurm_host.host.hostname}: {exc}"
                )

        logger.debug(f"Background refresh: job {job_id} not found in Slurm")
    except Exception as exc:
        logger.error(f"Background refresh failed for job {job_id}: {exc}")
