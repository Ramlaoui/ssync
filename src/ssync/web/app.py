import os
import threading
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .. import config
from ..manager import SlurmManager
from ..utils.logging import setup_logger
from ..utils.slurm_params import SlurmParams
from .cache_middleware import get_cache_middleware
from .cache_scheduler import start_cache_scheduler, stop_cache_scheduler
from .models import (
    FileMetadata,
    HostInfoWeb,
    JobInfoWeb,
    JobOutputResponse,
    JobStatusResponse,
    LaunchJobRequest,
    LaunchJobResponse,
    SlurmDefaultsWeb,
)

logger = setup_logger(__name__, "DEBUG")

app = FastAPI(
    title="SLURM Manager API",
    description="Web API for managing SLURM jobs across multiple clusters",
    version="1.0.0",
)

# Configure CORS using environment variables (safe defaults)
# SSYNC_ALLOWED_ORIGINS: comma-separated list, defaults to http://localhost:5173
# SSYNC_ALLOW_CREDENTIALS: "true"/"1" to allow credentials (default: false)
allowed_origins_env = os.getenv("SSYNC_ALLOWED_ORIGINS", "http://localhost:5173")
allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
allow_credentials = os.getenv("SSYNC_ALLOW_CREDENTIALS", "false").lower() in (
    "1",
    "true",
    "yes",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional API key enforcement. If SSYNC_API_KEY is set in the environment,
# require incoming requests to present that key as header `X-API-Key` or as
# a Bearer token in `Authorization: Bearer <key>`.
from fastapi.responses import JSONResponse

SSYNC_API_KEY = os.getenv("SSYNC_API_KEY")

if SSYNC_API_KEY:

    @app.middleware("http")
    async def _verify_api_key_middleware(request: Request, call_next):
        # Allow health checks or open endpoints if desired by path checks here.
        key = request.headers.get("x-api-key")
        if not key:
            auth = request.headers.get("authorization")
            if auth and auth.lower().startswith("bearer "):
                key = auth.split(" ", 1)[1].strip()

        if key != SSYNC_API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

        return await call_next(request)


# Global manager instance with connection pooling
_slurm_manager: Optional[SlurmManager] = None
_config_last_modified: Optional[float] = None
_shutdown_event = threading.Event()

# Global cache middleware
_cache_middleware = get_cache_middleware()


def get_slurm_manager() -> SlurmManager:
    """Get or create persistent SLURM manager instance with connection reuse."""
    global _slurm_manager, _config_last_modified

    config_path = config.config_path
    logger.debug(f"Using ssync config file: {config_path}")

    # Check if config file has been modified
    current_mtime = config_path.stat().st_mtime if config_path.exists() else 0
    config_changed = (
        _config_last_modified is None or current_mtime > _config_last_modified
    )

    # Create or recreate manager if needed
    if _slurm_manager is None or config_changed:
        # Close existing manager if it exists
        if _slurm_manager:
            logger.debug("Closing existing SlurmManager due to config change")
            _slurm_manager.close_connections()

        # Load config and create new manager
        slurm_hosts = config.load_config()
        _slurm_manager = SlurmManager(slurm_hosts)
        _config_last_modified = current_mtime
        logger.debug(f"Created new SlurmManager with {len(slurm_hosts)} hosts")
    else:
        logger.debug("Reusing existing SlurmManager")

    return _slurm_manager


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": "SLURM Manager API",
        "version": "1.0.0",
        "endpoints": [
            "/hosts",
            "/hosts/{hostname}/defaults",
            "/status",
            "/jobs/{job_id}",
            "/jobs/{job_id}/output",
            "/jobs/{job_id}/script",
            "/jobs/launch",
            "/connections/stats",
            "/cache/stats",
            "/cache/config",
            "/cache/cleanup",
            "/cache/export",
        ],
    }


@app.get("/hosts", response_model=List[HostInfoWeb])
async def get_hosts():
    """Get list of configured SLURM hosts."""
    manager = get_slurm_manager()
    hosts = []
    for slurm_host in manager.slurm_hosts:
        slurm_defaults_web = None
        if slurm_host.slurm_defaults:
            slurm_defaults_web = SlurmDefaultsWeb(**slurm_host.slurm_defaults.__dict__)
        hosts.append(
            HostInfoWeb(
                hostname=slurm_host.host.hostname,
                work_dir=str(slurm_host.work_dir),
                scratch_dir=str(slurm_host.scratch_dir),
                slurm_defaults=slurm_defaults_web,
            )
        )
    return hosts


@app.get("/hosts/{hostname}/defaults", response_model=SlurmDefaultsWeb)
async def get_host_defaults(hostname: str):
    """Get SLURM default parameters for a specific host."""
    manager = get_slurm_manager()

    # Find the host
    slurm_host = None
    for host in manager.slurm_hosts:
        if host.host.hostname == hostname:
            slurm_host = host
            break

    if not slurm_host:
        raise HTTPException(status_code=404, detail=f"Host '{hostname}' not found")

    if not slurm_host.slurm_defaults:
        # Return empty defaults if none configured
        return SlurmDefaultsWeb()

    # Convert to web model
    return SlurmDefaultsWeb(**slurm_host.slurm_defaults.__dict__)


@app.get("/status", response_model=List[JobStatusResponse])
async def get_job_status(
    request: Request,
    host: Optional[str] = Query(None, description="Specific host to query"),
    user: Optional[str] = Query(None, description="User to filter jobs for"),
    since: Optional[str] = Query(
        None, description="Time range for completed jobs (e.g., 1h, 1d, 1w)"
    ),
    limit: Optional[int] = Query(None, description="Limit number of jobs returned"),
    job_ids: Optional[str] = Query(None, description="Comma-separated job IDs"),
    state: Optional[str] = Query(
        None, description="Filter by job state (PD, R, CD, F, CA, TO)"
    ),
    active_only: bool = Query(False, description="Show only running/pending jobs"),
    completed_only: bool = Query(False, description="Show only completed jobs"),
):
    """Get job status across hosts."""
    # Handle compact tokens like 'since1w' or 'limit20' which appear as keys with empty values
    expected = (
        "since",
        "limit",
        "host",
        "user",
        "state",
        "job_ids",
        "active_only",
        "completed_only",
    )
    for k, v in request.query_params.items():
        if k in expected:
            # already parsed normally
            continue
        for prefix in expected:
            if k.startswith(prefix) and (v == "" or v is None):
                token_val = k[len(prefix) :]
                if not token_val:
                    continue
                if prefix == "limit":
                    try:
                        limit = int(token_val)
                    except Exception:
                        pass
                elif prefix in ("active_only", "completed_only"):
                    if token_val.lower() in ("1", "true", "yes", "y"):
                        if prefix == "active_only":
                            active_only = True
                        else:
                            completed_only = True
                elif prefix == "job_ids":
                    job_ids = token_val
                elif prefix == "since":
                    since = token_val
                elif prefix == "host":
                    host = token_val
                elif prefix == "user":
                    user = token_val
                elif prefix == "state":
                    state = token_val

    manager = get_slurm_manager()

    # Filter hosts
    slurm_hosts = manager.slurm_hosts
    if host:
        slurm_hosts = [h for h in slurm_hosts if h.host.hostname == host]
        if not slurm_hosts:
            raise HTTPException(status_code=404, detail=f"Host '{host}' not found")

    # Parse job IDs
    job_id_list = None
    if job_ids:
        job_id_list = [jid.strip() for jid in job_ids.split(",")]

    results = []

    # Handle special user values
    query_user = user
    skip_user_detection = False

    if user == "*" or user == "all":
        query_user = None  # None with skip_user_detection=True means get all users
        skip_user_detection = True

    for slurm_host in slurm_hosts:
        try:
            jobs = manager.get_all_jobs(
                slurm_host=slurm_host,
                user=query_user,
                since=since,
                limit=limit,
                job_ids=job_id_list,
                state_filter=state,
                active_only=active_only,
                completed_only=completed_only,
                skip_user_detection=skip_user_detection,
            )

            web_jobs = [JobInfoWeb.from_job_info(job) for job in jobs]

            response = JobStatusResponse(
                hostname=slurm_host.host.hostname,
                jobs=web_jobs,
                total_jobs=len(web_jobs),
                query_time=datetime.now(),
            )
            results.append(response)

        except Exception as e:
            # Continue with other hosts even if one fails
            print(f"Error querying {slurm_host.host.hostname}: {e}")
            results.append(
                JobStatusResponse(
                    hostname=slurm_host.host.hostname,
                    jobs=[],
                    total_jobs=0,
                    query_time=datetime.now(),
                )
            )

    # Cache the results transparently
    cached_results = await _cache_middleware.cache_job_status_response(results)
    return cached_results


@app.get("/jobs/{job_id}", response_model=JobInfoWeb)
async def get_job_details(
    job_id: str,
    host: Optional[str] = Query(None, description="Specific host to search"),
):
    """Get detailed information for a specific job."""
    manager = get_slurm_manager()

    # Filter hosts
    slurm_hosts = manager.slurm_hosts
    if host:
        slurm_hosts = [h for h in slurm_hosts if h.host.hostname == host]
        if not slurm_hosts:
            raise HTTPException(status_code=404, detail=f"Host '{host}' not found")

    # Search for job across hosts using get_job_info for better details
    for slurm_host in slurm_hosts:
        try:
            job_info = manager.get_job_info(slurm_host, job_id)
            if job_info:
                job_web = JobInfoWeb.from_job_info(job_info)
                # Cache the job data
                await _cache_middleware.cache_job_status_response(
                    [
                        JobStatusResponse(
                            hostname=slurm_host.host.hostname,
                            jobs=[job_web],
                            total_jobs=1,
                            query_time=datetime.now(),
                        )
                    ]
                )
                return job_web
        except Exception:
            continue

    # Try cache fallback
    cached_job = await _cache_middleware.get_job_with_cache_fallback(job_id, host)
    if cached_job:
        logger.info(f"Returning cached job {job_id} (not found in SLURM)")
        return cached_job

    raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


def _get_file_metadata_and_content(
    conn,
    file_path: str,
    file_type: str,
    job_id: str,
    hostname: str,
    lines: Optional[int] = None,
    metadata_only: bool = False,
) -> tuple[Optional[str], Optional[FileMetadata]]:
    """Helper function to get file metadata and content."""
    if not file_path or file_path == "N/A":
        return None, None

    try:
        metadata = FileMetadata(path=file_path)

        # Check if file exists
        file_check = conn.run(
            f"test -f {file_path} && echo 'exists' || echo 'not found'", hide=True
        )
        if "exists" not in file_check.stdout:
            return None, metadata

        metadata.exists = True

        # Get file metadata
        stat_result = conn.run(f"stat -c '%s %Y' {file_path}", hide=True)
        if stat_result.ok:
            size, mtime = stat_result.stdout.strip().split()
            metadata.size_bytes = int(size)
            metadata.last_modified = datetime.fromtimestamp(int(mtime)).isoformat()

        # Generate access path
        metadata.access_path = f"/api/jobs/{job_id}/files/{file_type}?host={hostname}"

        # Get content if requested
        content = None
        if not metadata_only:
            cmd = f"tail -n {lines} {file_path}" if lines else f"cat {file_path}"
            result = conn.run(cmd, hide=True)
            content = result.stdout

        return content, metadata

    except Exception as e:
        logger.error(f"Error reading {file_type} file {file_path}: {e}")
        return f"[Error reading {file_type} file: {str(e)}]", None


@app.get("/jobs/{job_id}/output", response_model=JobOutputResponse)
async def get_job_output(
    job_id: str,
    host: Optional[str] = Query(None, description="Specific host to search"),
    lines: Optional[int] = Query(None, description="Number of lines to return (tail)"),
    metadata_only: bool = Query(
        False, description="Return only metadata about output files, not content"
    ),
):
    """Get output files content for a specific job."""
    manager = get_slurm_manager()

    # Get job info
    slurm_hosts = [
        h for h in manager.slurm_hosts if not host or h.host.hostname == host
    ]
    if host and not slurm_hosts:
        raise HTTPException(status_code=404, detail=f"Host '{host}' not found")

    job_info = None
    target_host = None

    for slurm_host in slurm_hosts:
        try:
            job_info = manager.get_job_info(slurm_host, job_id)
            if job_info:
                target_host = slurm_host
                break
        except Exception as e:
            logger.debug(f"Error querying {slurm_host.host.hostname}: {e}")
            continue

    if not job_info or not target_host:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    try:
        # Get connection to target host
        conn = manager._get_connection(target_host.host)

        # If stdout/stderr files are missing, try to get them using scontrol
        if not job_info.stdout_file or not job_info.stderr_file:
            stdout_path, stderr_path = manager.slurm_client.get_job_output_files(
                conn, job_id, target_host.host.hostname
            )
            if stdout_path and not job_info.stdout_file:
                job_info.stdout_file = stdout_path
            if stderr_path and not job_info.stderr_file:
                job_info.stderr_file = stderr_path

        # Process stdout and stderr files
        stdout_content, stdout_metadata = _get_file_metadata_and_content(
            conn=conn,
            file_path=job_info.stdout_file,
            file_type="stdout",
            job_id=job_id,
            hostname=target_host.host.hostname,
            lines=lines,
            metadata_only=metadata_only,
        )

        stderr_content, stderr_metadata = _get_file_metadata_and_content(
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

        # Cache the output
        await _cache_middleware.cache_job_output(
            job_id, target_host.host.hostname, response
        )

        return response

    except Exception as e:
        # Try cache fallback for output
        cached_output = await _cache_middleware.get_cached_job_output(job_id, host)
        if cached_output:
            logger.info(
                f"Returning cached output for job {job_id} (SLURM query failed)"
            )
            return cached_output

        raise HTTPException(
            status_code=500, detail=f"Failed to read job output: {str(e)}"
        )


@app.get("/jobs/{job_id}/files/{file_type}")
async def get_job_file(
    job_id: str,
    file_type: str,
    host: Optional[str] = Query(None, description="Specific host to search"),
    download: bool = Query(
        False, description="Whether to download the file or view it"
    ),
    offset: Optional[int] = Query(
        None, description="Byte offset to start reading from"
    ),
    limit: Optional[int] = Query(None, description="Max number of bytes to read"),
):
    """Get a job's output or error file as a downloadable file or a stream.

    Args:
        job_id: ID of the job
        file_type: Type of file to download (stdout or stderr)
        host: Host to search for the job
        download: Whether to serve as attachment
        offset: Starting byte position (for large file streaming)
        limit: Maximum bytes to read (for large file streaming)
    """
    import io

    from fastapi.responses import StreamingResponse

    if file_type not in ["stdout", "stderr"]:
        raise HTTPException(
            status_code=400, detail="Invalid file type. Use 'stdout' or 'stderr'."
        )

    manager = get_slurm_manager()

    # First find the job to get file paths
    job_info = None
    target_host = None

    slurm_hosts = manager.slurm_hosts
    if host:
        slurm_hosts = [h for h in slurm_hosts if h.host.hostname == host]

    for slurm_host in slurm_hosts:
        try:
            job_info = manager.get_job_info(slurm_host, job_id)
            if job_info:
                target_host = slurm_host
                break
        except Exception:
            continue

    if not job_info or not target_host:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Get the appropriate file path, using scontrol as fallback
    file_path = job_info.stdout_file if file_type == "stdout" else job_info.stderr_file

    # If file path is missing, try scontrol
    if not file_path:
        conn = manager._get_connection(target_host.host)
        stdout_path, stderr_path = manager.slurm_client.get_job_output_files(
            conn, job_id, target_host.host.hostname
        )
        file_path = stdout_path if file_type == "stdout" else stderr_path

    if not file_path or file_path == "N/A":
        raise HTTPException(
            status_code=404,
            detail=f"{file_type.capitalize()} file not found for job {job_id}",
        )

    # Read output file
    conn = manager._get_connection(target_host.host)

    try:
        # Check if file exists
        check_cmd = f"test -f {file_path} && echo 'exists' || echo 'not found'"
        check_result = conn.run(check_cmd, hide=True)

        if "not found" in check_result.stdout:
            raise HTTPException(
                status_code=404,
                detail=f"File {file_path} not found on host {target_host.host.hostname}",
            )

        # Get file size
        stat_cmd = f"stat -c '%s' {file_path}"
        stat_result = conn.run(stat_cmd, hide=True)
        file_size = int(stat_result.stdout.strip())

        # Prepare for partial content if needed
        start_byte = offset if offset is not None else 0
        end_byte = (
            min(start_byte + limit, file_size) if limit is not None else file_size
        )
        content_length = end_byte - start_byte

        # Read the file content
        if limit is not None or offset is not None:
            cmd = f"dd if={file_path} bs=1 skip={start_byte} count={content_length} 2>/dev/null"
        else:
            cmd = f"cat {file_path}"

        result = conn.run(cmd, hide=True)
        content = result.stdout

        # Set filename
        job_name = job_info.name.replace(" ", "_")
        filename = f"{job_name}_{job_id}_{file_type}.txt"

        # Return as streaming response
        headers = {
            "Content-Disposition": f'{"attachment" if download else "inline"}; filename="{filename}"',
        }

        if offset is not None or limit is not None:
            headers["Content-Range"] = f"bytes {start_byte}-{end_byte - 1}/{file_size}"
            headers["Accept-Ranges"] = "bytes"

        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="text/plain",
            headers=headers,
        )

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


@app.get("/jobs/{job_id}/script")
async def get_job_script(
    job_id: str,
    host: Optional[str] = Query(None, description="Specific host to search"),
):
    """Get the batch script content for a specific job."""
    manager = get_slurm_manager()

    # Filter hosts
    slurm_hosts = manager.slurm_hosts
    if host:
        slurm_hosts = [h for h in slurm_hosts if h.host.hostname == host]
        if not slurm_hosts:
            raise HTTPException(status_code=404, detail=f"Host '{host}' not found")

    # Search for job across hosts
    for slurm_host in slurm_hosts:
        try:
            job_info = manager.get_job_info(slurm_host, job_id)
            if job_info:
                # Get connection and batch script
                conn = manager._get_connection(slurm_host.host)
                script_content = manager.slurm_client.get_job_batch_script(
                    conn, job_id, slurm_host.host.hostname
                )

                if script_content is not None:
                    response = {
                        "job_id": job_id,
                        "hostname": slurm_host.host.hostname,
                        "script_content": script_content,
                        "content_length": len(script_content),
                    }

                    # Cache the script
                    await _cache_middleware.cache_job_script(
                        job_id, slurm_host.host.hostname, script_content
                    )

                    return response
                else:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Batch script not available for job {job_id}",
                    )
        except Exception as e:
            logger.debug(
                f"Error getting script for job {job_id} on {slurm_host.host.hostname}: {e}"
            )
            continue

    # Try cache fallback for script
    cached_script = await _cache_middleware.get_cached_job_script(job_id, host)
    if cached_script:
        logger.info(f"Returning cached script for job {job_id} (not found in SLURM)")
        return cached_script

    raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str, host: Optional[str] = Query(None, description="Specific host")
):
    """Cancel a running job."""
    manager = get_slurm_manager()

    # Find the job first
    slurm_hosts = manager.slurm_hosts
    if host:
        slurm_hosts = [h for h in slurm_hosts if h.host.hostname == host]

    for slurm_host in slurm_hosts:
        try:
            jobs = manager.get_all_jobs(slurm_host=slurm_host, job_ids=[job_id])
            if jobs:
                success = manager.cancel_job(slurm_host, job_id)
                if success:
                    return {"message": f"Job {job_id} cancelled successfully"}
                else:
                    raise HTTPException(
                        status_code=500, detail=f"Failed to cancel job {job_id}"
                    )
        except Exception:
            continue

    raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


@app.get("/connections/stats")
async def get_connection_stats():
    """Get SSH connection pool statistics."""
    manager = get_slurm_manager()
    try:
        stats = manager.get_connection_stats()
        return {"connection_stats": stats, "status": "healthy"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get connection stats: {str(e)}"
        )


@app.get("/cache/stats")
async def get_cache_stats():
    """Get job cache statistics."""
    try:
        stats = await _cache_middleware.get_cache_stats()
        return {"cache_stats": stats, "status": "healthy"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get cache stats: {str(e)}"
        )


@app.post("/cache/cleanup")
async def cleanup_cache(
    max_age_days: Optional[int] = Query(
        None, description="Max age in days (0=never, -1=force all)"
    ),
    preserve_scripts: bool = Query(True, description="Preserve entries with scripts"),
    force: bool = Query(
        False, description="Force cleanup ignoring preservation settings"
    ),
):
    """Clean up old cache entries with preservation controls."""
    try:
        from .cache_scheduler import get_cache_scheduler

        if max_age_days == -1 and force:
            # Nuclear option - clean everything
            cleaned_count = _cache_middleware.cache.cleanup_old_entries(
                max_age_days=1,  # Very aggressive
                preserve_scripts=False,
                force_cleanup=True,
            )
            message = f"⚠️  FORCE CLEANUP: Removed ALL {cleaned_count} cache entries (including scripts)!"
        else:
            scheduler = await get_cache_scheduler()
            cleaned_count = await scheduler.force_cleanup(
                max_age_days=max_age_days, preserve_scripts=preserve_scripts
            )
            if max_age_days == 0:
                message = "No cleanup performed (preservation mode: max_age_days=0)"
            else:
                preserve_msg = " (preserving scripts)" if preserve_scripts else ""
                message = f"Cache cleanup completed. Removed {cleaned_count} entries{preserve_msg}."

        return {
            "message": message,
            "entries_removed": cleaned_count,
            "preservation_mode": max_age_days == 0,
            "scripts_preserved": preserve_scripts and not force,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to clean up cache: {str(e)}"
        )


@app.post("/cache/export")
async def export_cache(
    output_filename: str = Query("cache_export.json", description="Output filename"),
    job_ids: Optional[str] = Query(
        None, description="Comma-separated job IDs to export"
    ),
):
    """Export cache data to JSON for backup/archival."""
    try:
        export_path = _cache_middleware.cache.cache_dir / output_filename

        job_id_list = None
        if job_ids:
            job_id_list = [jid.strip() for jid in job_ids.split(",")]

        exported_count = _cache_middleware.cache.export_cache_data(
            export_path, job_id_list
        )

        return {
            "message": f"Cache export completed. Exported {exported_count} jobs.",
            "export_file": str(export_path),
            "jobs_exported": exported_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export cache: {str(e)}")


@app.get("/cache/config")
async def get_cache_config_info():
    """Get current cache configuration and recommendations."""
    try:
        from ..cache_config import get_cache_config

        config = get_cache_config()
        stats = await _cache_middleware.get_cache_stats()

        # Generate recommendations
        recommendations = []

        if config.max_age_days > 0 and config.max_age_days < 365:
            recommendations.append(
                "⚠️  Consider increasing max_age_days - SLURM data may be permanently lost after cleanup"
            )

        if not config.auto_cleanup_enabled and stats["db_size_mb"] > 500:
            recommendations.append(
                "💾 Cache is large and auto-cleanup disabled. Consider manual cleanup or size limits."
            )

        if config.max_age_days == 0:
            recommendations.append(
                "✅ Preservation mode enabled - cache never expires (recommended for job archival)"
            )

        return {
            "config": {
                "enabled": config.enabled,
                "cache_dir": str(config.cache_dir),
                "max_age_days": config.max_age_days,
                "script_max_age_days": config.script_max_age_days,
                "auto_cleanup_enabled": config.auto_cleanup_enabled,
                "max_cache_size_mb": config.max_cache_size_mb,
                "cleanup_interval_hours": config.cleanup_interval_hours,
            },
            "stats": stats,
            "recommendations": recommendations,
            "preservation_mode": config.max_age_days == 0,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get cache config: {str(e)}"
        )


@app.get("/local/list")
async def list_local_path(
    path: str = Query("/", description="Local filesystem path to list"),
    limit: int = Query(100, description="Maximum number of entries to return"),
    show_hidden: bool = Query(False, description="Include hidden files/directories"),
    dirs_only: bool = Query(False, description="Show directories only"),
):
    """List entries in a local filesystem path to help the web UI pick a source_dir.

    NOTE: This exposes the server's filesystem to the UI. Ensure proper deployment and
    access controls if enabling in production. The endpoint resolves and returns
    name, path, and is_dir for entries under the given path.
    """
    from pathlib import Path

    try:
        base = Path(path).expanduser().resolve()
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid path: {path}")

    # Security: prevent path traversal attacks
    # Allow reasonable root directories for local development
    ALLOWED_ROOT_PATHS = ["/home", "/Users", "/opt", "/mnt", "/tmp", "/var/tmp"]
    if not any(str(base).startswith(allowed) for allowed in ALLOWED_ROOT_PATHS):
        # For localhost development, allow current user's home area

        user_home = Path.home()
        if not base.is_relative_to(user_home):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Path must be under {ALLOWED_ROOT_PATHS} or {user_home}",
            )

    # Basic safety: ensure path exists and is a directory
    if not base.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if not base.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")

    entries = []
    try:
        all_children = sorted(
            base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
        )
        count = 0
        for child in all_children:
            # Skip hidden files unless requested
            if not show_hidden and child.name.startswith("."):
                continue
            # Skip files if dirs_only is True
            if dirs_only and not child.is_dir():
                continue

            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "is_dir": child.is_dir(),
                }
            )

            count += 1
            if limit and count >= limit:
                break

        return {"path": str(base), "entries": entries}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to read directory: {str(e)}"
        )


@app.post("/connections/health-check")
async def manual_health_check():
    """Manually trigger connection health check."""
    manager = get_slurm_manager()
    try:
        unhealthy_count = manager.check_connection_health()
        stats = manager.get_connection_stats()
        return {
            "message": f"Health check completed. Cleaned up {unhealthy_count} unhealthy connections.",
            "unhealthy_connections_removed": unhealthy_count,
            "current_stats": stats,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to perform health check: {str(e)}"
        )


def apply_slurm_defaults(
    request: LaunchJobRequest, defaults: Optional[SlurmDefaultsWeb]
) -> LaunchJobRequest:
    """Apply SLURM defaults to launch request, with request values taking precedence."""
    if not defaults:
        return request

    # Create a dict with defaults, then overlay with request values
    merged_params = {}

    # Copy defaults to merged params (excluding None values)
    defaults_dict = defaults.model_dump(exclude_none=True)
    for key, value in defaults_dict.items():
        merged_params[key] = value

    # Handle special mappings and transformations
    if defaults.job_name_prefix and not request.job_name:
        # Auto-generate job name with prefix if none provided
        import time

        timestamp = int(time.time())
        merged_params["job_name"] = f"{defaults.job_name_prefix}-{timestamp}"

    if defaults.output_pattern and not request.output:
        merged_params["output"] = defaults.output_pattern

    if defaults.error_pattern and not request.error:
        merged_params["error"] = defaults.error_pattern

    if defaults.python_env and not request.python_env:
        merged_params["python_env"] = defaults.python_env

    # Copy request values, overriding defaults (excluding None values)
    request_dict = request.model_dump(exclude_none=True)
    for key, value in request_dict.items():
        if key in ["job_name_prefix", "output_pattern", "error_pattern"]:
            # Skip these default-only fields
            continue
        merged_params[key] = value

    # Create new request with merged parameters
    try:
        return LaunchJobRequest(**merged_params)
    except Exception as e:
        logger.warning(f"Error merging defaults with request: {e}")
        return request  # Fallback to original request


def validate_script_content(script_content: str) -> None:
    """Basic validation for script content to prevent obviously dangerous commands."""
    # Check for obviously dangerous patterns (not comprehensive, just basic safety)
    dangerous_patterns = [
        "rm -rf /",
        "chmod 777",
        "sudo ",
        "> /etc/",
        "curl http",  # Prevent data exfiltration
        "wget http",
        "nc -l",  # Prevent backdoors
        "& sleep",  # Prevent infinite loops/DOS
    ]

    script_lower = script_content.lower()
    for pattern in dangerous_patterns:
        if pattern in script_lower:
            raise HTTPException(
                status_code=400,
                detail=f"Script contains potentially dangerous command: {pattern}",
            )


@app.post("/jobs/launch", response_model=LaunchJobResponse)
async def launch_job(request: LaunchJobRequest):
    """Launch a job by syncing source directory and submitting script."""
    import os
    import tempfile
    from pathlib import Path

    from ..launch import LaunchManager

    # Basic script validation for safety
    validate_script_content(request.script_content)

    manager = get_slurm_manager()

    # Validate host exists and get defaults
    try:
        slurm_host = manager.get_host_by_name(request.host)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Host '{request.host}' not found in configuration"
        )

    # Apply defaults from host configuration
    defaults = None
    if slurm_host.slurm_defaults:
        defaults = SlurmDefaultsWeb(**slurm_host.slurm_defaults.__dict__)

    # Merge defaults with request parameters
    request = apply_slurm_defaults(request, defaults)

    # Validate source directory exists
    source_dir = Path(request.source_dir).expanduser().resolve()
    if not source_dir.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Source directory '{request.source_dir}' does not exist",
        )

    if not source_dir.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Source path '{request.source_dir}' is not a directory",
        )

    try:
        # Create temporary script file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False
        ) as tmp_script:
            tmp_script.write(request.script_content)
            script_path = Path(tmp_script.name)

        try:
            # Initialize launch manager
            launch_manager = LaunchManager(manager)

            slurm_params = SlurmParams(
                job_name=request.job_name,
                time_min=request.time,
                cpus_per_task=request.cpus,
                mem_gb=request.mem,
                partition=request.partition,
                output=request.output,
                error=request.error,
                constraint=request.constraint,
                account=request.account,
                nodes=request.nodes,
                n_tasks_per_node=request.n_tasks_per_node,
                gpus_per_node=request.gpus_per_node,
                gres=request.gres,
            )

            # Launch the job
            job = launch_manager.launch_job(
                script_path=script_path,
                source_dir=source_dir,
                host=request.host,
                slurm_params=slurm_params,
                python_env=request.python_env,
                exclude=request.exclude,
                include=request.include,
                no_gitignore=request.no_gitignore,
            )

            if job:
                return LaunchJobResponse(
                    success=True,
                    job_id=job.job_id,
                    message=f"Job launched successfully with ID: {job.job_id}",
                    hostname=request.host,
                )
            else:
                return LaunchJobResponse(
                    success=False, message="Failed to launch job", hostname=request.host
                )

        finally:
            # Clean up temporary script file
            try:
                os.unlink(script_path)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error launching job: {e}")
        return LaunchJobResponse(
            success=False,
            message=f"Error launching job: {str(e)}",
            hostname=request.host,
        )


@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    # Initialize manager
    manager = get_slurm_manager()
    print("API started, manager initialized")

    # Start cache scheduler
    try:
        await start_cache_scheduler()
        print("Cache scheduler started")
    except Exception as e:
        logger.error(f"Failed to start cache scheduler: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections and background tasks on shutdown."""
    global _slurm_manager

    # Signal shutdown to background tasks
    _shutdown_event.set()

    # Stop cache scheduler
    try:
        await stop_cache_scheduler()
        print("Cache scheduler stopped")
    except Exception as e:
        print(f"Error stopping cache scheduler: {e}")

    # Close connections
    if _slurm_manager:
        _slurm_manager.close_connections()
        print("Closed all SSH connections")

    # Cleanup cache
    try:
        _cache_middleware.cache.close()
        print("Closed job cache")
    except Exception as e:
        print(f"Error closing cache: {e}")


def main():
    """Run the web server."""
    import uvicorn

    # Avoid exposing the API
    # to the local network
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
