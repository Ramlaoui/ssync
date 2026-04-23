"""Job detail, script, and output route registration."""

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request

from ...utils.logging import setup_logger
from ..models import (
    CompleteJobDataResponse,
    JobInfoWeb,
    JobOutputResponse,
    JobStatusResponse,
)
from ..security import InputSanitizer
from ..services.jobs import (
    build_complete_job_data_response,
    build_download_job_output_response,
    build_stream_job_output_response,
    get_job_data_with_optional_host_search,
    get_job_output_response,
    get_job_script_payload,
    mark_job_response_cached,
    queue_job_refresh,
)

logger = setup_logger(__name__)


def register_job_routes(
    app: FastAPI,
    *,
    verify_api_key_dependency,
    verify_api_key_flexible_dependency,
    get_slurm_manager,
    cache_middleware,
    job_manager,
    executor,
) -> None:
    """Register job data, detail, script, and output routes."""

    @app.get("/api/jobs/{job_id}/data", response_model=CompleteJobDataResponse)
    async def get_complete_job_data(
        job_id: str,
        host: Optional[str] = Query(None, description="Specific host to search"),
        include_outputs: bool = Query(
            True, description="Include stdout/stderr content"
        ),
        lines: Optional[int] = Query(
            None, description="Number of output lines to return (tail)"
        ),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Get complete job data (info + script + outputs) in a single request."""
        try:
            job_id = InputSanitizer.sanitize_job_id(job_id)
            if host:
                host = InputSanitizer.sanitize_hostname(host)
            complete_data, _ = await get_job_data_with_optional_host_search(
                job_id=job_id,
                host=host,
                get_slurm_manager=get_slurm_manager,
            )

            if not complete_data:
                raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

            return build_complete_job_data_response(
                job_id=job_id,
                complete_data=complete_data,
                include_outputs=include_outputs,
                lines=lines,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in get_complete_job_data: {e}")
            raise HTTPException(
                status_code=500, detail="Internal server error occurred"
            )

    @app.get("/api/jobs/{job_id}", response_model=JobInfoWeb)
    async def get_job_details(
        job_id: str,
        host: Optional[str] = Query(None, description="Specific host to search"),
        cache_first: bool = Query(
            True,
            description="Return cached data immediately if available, then refresh in background",
        ),
        force_refresh: bool = Query(
            False, description="Fetch directly from Slurm and skip cache fallback"
        ),
        force: bool = Query(
            False, description="Legacy alias for force_refresh", alias="force"
        ),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Get detailed information for a specific job."""
        try:
            job_id = InputSanitizer.sanitize_job_id(job_id)
            if host:
                host = InputSanitizer.sanitize_hostname(host)
            force_refresh = force_refresh or force

            cached_job = None
            if cache_first or force_refresh:
                cached_job = await cache_middleware.get_job_with_cache_fallback(
                    job_id,
                    host,
                    allow_stale_active=True,
                )
                if cached_job:
                    refresh_host = host or cached_job.hostname
                    refresh_queued = queue_job_refresh(
                        job_id=job_id,
                        host=refresh_host,
                        get_slurm_manager=get_slurm_manager,
                        cache_middleware=cache_middleware,
                        job_manager=job_manager,
                    )
                    logger.info(
                        "Returning cached job %s immediately "
                        "(cache_first=%s force_refresh=%s refresh_queued=%s)",
                        job_id,
                        cache_first,
                        force_refresh,
                        refresh_queued,
                    )
                    return mark_job_response_cached(
                        cached_job,
                        refresh_queued=refresh_queued,
                    )

            manager = get_slurm_manager()
            slurm_hosts = manager.slurm_hosts
            if host:
                slurm_hosts = [h for h in slurm_hosts if h.host.hostname == host]
                if not slurm_hosts:
                    raise HTTPException(status_code=404, detail="Host not found")

            loop = asyncio.get_running_loop()
            for slurm_host in slurm_hosts:
                try:
                    job_info = await loop.run_in_executor(
                        executor, manager.get_job_info, slurm_host, job_id
                    )
                    if job_info:
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
                                "source": "slurm",
                            },
                        )
                        return job_web
                except Exception:
                    continue

            if not force_refresh:
                cached_job = await cache_middleware.get_job_with_cache_fallback(
                    job_id, host
                )
                if cached_job:
                    logger.info(f"Returning cached job {job_id}")
                    return mark_job_response_cached(
                        cached_job,
                        refresh_queued=False,
                    )

            raise HTTPException(status_code=404, detail="Job not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in get_job_details: {e}")
            raise HTTPException(
                status_code=500, detail="Internal server error occurred"
            )

    @app.get("/api/jobs/{job_id}/output/stream")
    async def stream_job_output(
        request: Request,
        job_id: str,
        host: str = Query(..., description="Host where job is running"),
        output_type: str = Query("stdout", regex="^(stdout|stderr)$"),
        chunk_size: int = Query(default=8192, ge=1024, le=1048576),
        max_initial_bytes: int = Query(
            default=524288,
            ge=1024,
            le=4194304,
            description="Maximum initial tail window to stream",
        ),
        api_key: Optional[str] = Query(None, description="API key for EventSource"),
        _authenticated: bool = Depends(verify_api_key_flexible_dependency),
    ):
        """Stream compressed job output efficiently."""
        job_id = InputSanitizer.sanitize_job_id(job_id)
        host = InputSanitizer.sanitize_hostname(host)
        return await build_stream_job_output_response(
            request=request,
            job_id=job_id,
            host=host,
            output_type=output_type,
            chunk_size=chunk_size,
            max_initial_bytes=max_initial_bytes,
            get_slurm_manager=get_slurm_manager,
        )

    @app.get("/api/jobs/{job_id}/output/download")
    async def download_job_output(
        job_id: str,
        host: str = Query(..., description="Host where job is running"),
        output_type: str = Query("stdout", regex="^(stdout|stderr)$"),
        compressed: bool = Query(default=False, description="Download as gzip"),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Download job output file, optionally compressed."""
        job_id = InputSanitizer.sanitize_job_id(job_id)
        host = InputSanitizer.sanitize_hostname(host)
        return await build_download_job_output_response(
            job_id=job_id,
            host=host,
            output_type=output_type,
            compressed=compressed,
            get_slurm_manager=get_slurm_manager,
        )

    @app.get("/api/jobs/{job_id}/output", response_model=JobOutputResponse)
    async def get_job_output(
        job_id: str,
        host: Optional[str] = Query(None, description="Specific host to search"),
        output_type: str = Query(
            "both",
            regex="^(stdout|stderr|both)$",
            description="Which output stream to return",
        ),
        lines: Optional[int] = Query(
            None, description="Number of lines to return (tail)"
        ),
        max_bytes: Optional[int] = Query(
            524288,
            ge=1024,
            le=4194304,
            description="Maximum number of trailing bytes to return when lines is not set",
        ),
        metadata_only: bool = Query(
            False, description="Return only metadata about output files, not content"
        ),
        force_refresh: bool = Query(
            False, description="Force refresh from SSH even if cached"
        ),
        force: bool = Query(
            False, description="Legacy alias for force_refresh", alias="force"
        ),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Get output files content for a specific job."""
        try:
            job_id = InputSanitizer.sanitize_job_id(job_id)
            if host:
                host = InputSanitizer.sanitize_hostname(host)
            force_refresh = force_refresh or force
            return await get_job_output_response(
                job_id=job_id,
                host=host,
                lines=lines,
                output_type=output_type,
                max_bytes=max_bytes,
                metadata_only=metadata_only,
                force_refresh=force_refresh,
                get_slurm_manager=get_slurm_manager,
                cache_middleware=cache_middleware,
                job_manager=job_manager,
            )
        except HTTPException:
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Error in get_job_output for job {job_id} on {host}: {error_msg}"
            )
            cached_output = await cache_middleware.get_cached_job_output(job_id, host)
            if cached_output:
                logger.info(
                    f"Returning cached output for job {job_id} (fetch failed: {error_msg[:200]})"
                )
                return cached_output

            if "connection" in error_msg.lower() or "ssh" in error_msg.lower():
                detail = f"SSH connection failed to {host}: {error_msg}"
            elif "timeout" in error_msg.lower():
                detail = f"Operation timed out while fetching output: {error_msg}"
            elif (
                "not found" in error_msg.lower() or "no such file" in error_msg.lower()
            ):
                detail = f"Output file not found: {error_msg}"
            else:
                detail = f"Failed to read job output: {error_msg}"
            raise HTTPException(status_code=500, detail=detail)

    @app.get("/api/jobs/{job_id}/script")
    async def get_job_script(
        job_id: str,
        host: Optional[str] = Query(None, description="Specific host to search"),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Get the batch script content for a specific job."""
        try:
            job_id = InputSanitizer.sanitize_job_id(job_id)
            if host:
                host = InputSanitizer.sanitize_hostname(host)
            return await get_job_script_payload(
                job_id=job_id,
                host=host,
                get_slurm_manager=get_slurm_manager,
                cache_middleware=cache_middleware,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in get_job_script: {e}")
            raise HTTPException(
                status_code=500, detail="Internal server error occurred"
            )
