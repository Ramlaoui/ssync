"""Secure version of the SLURM Manager API with enhanced security measures."""

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

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
from .security import (
    APIKeyManager,
    InputSanitizer,
    PathValidator,
    RateLimiter,
    ScriptValidator,
    sanitize_error_message,
)

logger = setup_logger(__name__, "INFO")

app = FastAPI(
    title="SLURM Manager API",
    description="Secure Web API for managing SLURM jobs across multiple clusters",
    version="2.0.0",
    docs_url=None,  # Disable interactive docs in production
    redoc_url=None,  # Disable ReDoc in production
)

# Security Configuration
ENABLE_DOCS = os.getenv("SSYNC_ENABLE_DOCS", "false").lower() == "true"
if ENABLE_DOCS:
    app.docs_url = "/docs"
    app.redoc_url = "/redoc"

# Trusted hosts middleware (prevent host header injection)
TRUSTED_HOSTS = os.getenv("SSYNC_TRUSTED_HOSTS", "localhost,127.0.0.1").split(",")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)

# Configure CORS with strict settings
ALLOWED_ORIGINS = os.getenv("SSYNC_ALLOWED_ORIGINS", "").split(",")
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS if o.strip()]

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,  # Disable credentials by default
        allow_methods=["GET", "POST"],  # Only allow necessary methods
        allow_headers=["X-API-Key", "Content-Type"],  # Restrict headers
        max_age=3600,  # Cache preflight requests
    )

# Initialize security components
rate_limiter = RateLimiter(
    requests_per_minute=int(os.getenv("SSYNC_RATE_LIMIT_PER_MINUTE", "60")),
    requests_per_hour=int(os.getenv("SSYNC_RATE_LIMIT_PER_HOUR", "1000")),
    burst_size=int(os.getenv("SSYNC_BURST_SIZE", "10")),
)

api_key_manager = APIKeyManager()


# Rate limiting middleware
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path == "/health":
            return await call_next(request)

        if not await rate_limiter.check_rate_limit(request):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers={"Retry-After": "60"},
            )

        return await call_next(request)


app.add_middleware(RateLimitMiddleware)

# API Key Authentication - Optional by default for personal use
# Set SSYNC_REQUIRE_API_KEY=true for production/shared deployments
REQUIRE_API_KEY = os.getenv("SSYNC_REQUIRE_API_KEY", "false").lower() == "true"


async def verify_api_key(request: Request):
    """Verify API key for protected endpoints."""
    if not REQUIRE_API_KEY:
        return True

    # Allow health endpoint without auth
    if request.url.path == "/health":
        return True

    api_key = request.headers.get("x-api-key")
    if not api_key:
        raise HTTPException(
            status_code=401, detail="API key required. Please provide X-API-Key header."
        )

    if not api_key_manager.validate_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid or expired API key.")

    return True


# Global manager instance with connection pooling
_slurm_manager: Optional[SlurmManager] = None
_config_last_modified: Optional[float] = None
_shutdown_event = threading.Event()

# Global cache middleware
_cache_middleware = get_cache_middleware()

# Serve static frontend files if they exist
frontend_dist = Path(__file__).parent.parent.parent.parent / "web-frontend" / "dist"
if frontend_dist.exists():
    # Mount static files for assets
    app.mount(
        "/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets"
    )

    # Serve index.html for root and any unmatched routes (for client-side routing)
    @app.get("/", response_class=FileResponse)
    async def serve_frontend():
        """Serve the frontend application."""
        return FileResponse(str(frontend_dist / "index.html"))

    # Serve favicon
    @app.get("/favicon.ico", response_class=FileResponse)
    async def serve_favicon():
        """Serve favicon."""
        return FileResponse(str(frontend_dist / "favicon.ico"))

    @app.get("/favicon.svg", response_class=FileResponse)
    async def serve_favicon_svg():
        """Serve SVG favicon."""
        return FileResponse(str(frontend_dist / "favicon.svg"))
else:
    # If no frontend built, just return API info
    @app.get("/")
    async def root(authenticated: bool = Depends(verify_api_key)):
        """API root endpoint."""
        return {
            "message": "SLURM Manager API",
            "version": "2.0.0",
            "security": "enhanced",
            "documentation": "/docs" if ENABLE_DOCS else "disabled",
            "frontend": "Not built. Run 'npm run build' in web-frontend directory.",
        }


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


@app.get("/health")
async def health_check():
    """Health check endpoint (no auth required)."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/info")
async def api_info(authenticated: bool = Depends(verify_api_key)):
    """API info endpoint."""
    return {
        "message": "SLURM Manager API",
        "version": "2.0.0",
        "security": "enhanced",
        "documentation": "/docs" if ENABLE_DOCS else "disabled",
    }


@app.get("/api/hosts", response_model=List[HostInfoWeb])
async def get_hosts(authenticated: bool = Depends(verify_api_key)):
    """Get list of configured SLURM hosts."""
    try:
        manager = get_slurm_manager()
        hosts = []
        for slurm_host in manager.slurm_hosts:
            slurm_defaults_web = None
            if slurm_host.slurm_defaults:
                slurm_defaults_web = SlurmDefaultsWeb(
                    **slurm_host.slurm_defaults.__dict__
                )

            # Don't expose sensitive path information
            hosts.append(
                HostInfoWeb(
                    hostname=slurm_host.host.hostname,
                    work_dir="[CONFIGURED]",  # Don't expose actual paths
                    scratch_dir="[CONFIGURED]",
                    slurm_defaults=slurm_defaults_web,
                )
            )
        return hosts
    except Exception as e:
        logger.error(f"Error getting hosts: {e}")
        raise HTTPException(status_code=500, detail=sanitize_error_message(e))


@app.get("/api/status", response_model=List[JobStatusResponse])
async def get_job_status(
    request: Request,
    host: Optional[str] = Query(None, description="Specific host to query"),
    user: Optional[str] = Query(None, description="User to filter jobs for"),
    since: Optional[str] = Query(
        None,
        description="Time range for completed jobs",
        regex="^[0-9]+[hdwm]$",  # Validate format
    ),
    limit: Optional[int] = Query(
        None,
        description="Limit number of jobs returned",
        ge=1,
        le=1000,  # Enforce reasonable limits
    ),
    job_ids: Optional[str] = Query(None, description="Comma-separated job IDs"),
    state: Optional[str] = Query(
        None,
        description="Filter by job state",
        regex="^(PD|R|CD|F|CA|TO)$",  # Validate state values
    ),
    active_only: bool = Query(False, description="Show only running/pending jobs"),
    completed_only: bool = Query(False, description="Show only completed jobs"),
    search: Optional[str] = Query(None, description="Search for jobs by name or ID"),
    authenticated: bool = Depends(verify_api_key),
):
    """Get job status across hosts."""
    try:
        # Sanitize inputs
        if host:
            host = InputSanitizer.sanitize_hostname(host)
        if user:
            user = InputSanitizer.sanitize_username(user)
        if search:
            search = InputSanitizer.sanitize_text(search)
        if job_ids:
            job_id_list = [
                InputSanitizer.sanitize_job_id(jid.strip())
                for jid in job_ids.split(",")
            ]
        else:
            job_id_list = None

        manager = get_slurm_manager()

        # Filter hosts
        slurm_hosts = manager.slurm_hosts
        if host:
            slurm_hosts = [h for h in slurm_hosts if h.host.hostname == host]
            if not slurm_hosts:
                raise HTTPException(status_code=404, detail="Host not found")

        results = []

        for slurm_host in slurm_hosts:
            try:
                jobs = manager.get_all_jobs(
                    slurm_host=slurm_host,
                    user=user,
                    since=since,
                    limit=limit,
                    job_ids=job_id_list,
                    state_filter=state,
                    active_only=active_only,
                    completed_only=completed_only,
                )

                web_jobs = [JobInfoWeb.from_job_info(job) for job in jobs]

                # Apply search filter if provided
                if search:
                    search_lower = search.lower()
                    filtered_jobs = []
                    for job in web_jobs:
                        # Search in job ID and job name
                        if search_lower in job.job_id.lower() or (
                            job.name and search_lower in job.name.lower()
                        ):
                            filtered_jobs.append(job)
                    web_jobs = filtered_jobs

                response = JobStatusResponse(
                    hostname=slurm_host.host.hostname,
                    jobs=web_jobs,
                    total_jobs=len(web_jobs),
                    query_time=datetime.now(),
                )
                results.append(response)

            except Exception as e:
                logger.error(f"Error querying {slurm_host.host.hostname}: {e}")
                # Don't expose internal errors
                results.append(
                    JobStatusResponse(
                        hostname=slurm_host.host.hostname,
                        jobs=[],
                        total_jobs=0,
                        query_time=datetime.now(),
                    )
                )

        # Cache the results
        cached_results = await _cache_middleware.cache_job_status_response(results)
        return cached_results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_job_status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


@app.get("/api/jobs/{job_id}", response_model=JobInfoWeb)
async def get_job_details(
    job_id: str,
    host: Optional[str] = Query(None, description="Specific host to search"),
    authenticated: bool = Depends(verify_api_key),
):
    """Get detailed information for a specific job."""
    try:
        # Sanitize inputs
        job_id = InputSanitizer.sanitize_job_id(job_id)
        if host:
            host = InputSanitizer.sanitize_hostname(host)

        manager = get_slurm_manager()

        # Filter hosts
        slurm_hosts = manager.slurm_hosts
        if host:
            slurm_hosts = [h for h in slurm_hosts if h.host.hostname == host]
            if not slurm_hosts:
                raise HTTPException(status_code=404, detail="Host not found")

        # Search for job across hosts
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
            logger.info(f"Returning cached job {job_id}")
            return cached_job

        raise HTTPException(status_code=404, detail="Job not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_job_details: {e}")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


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
    from .models import FileMetadata

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


@app.get("/api/jobs/{job_id}/output", response_model=JobOutputResponse)
async def get_job_output(
    job_id: str,
    host: Optional[str] = Query(None, description="Specific host to search"),
    lines: Optional[int] = Query(None, description="Number of lines to return (tail)"),
    metadata_only: bool = Query(
        False, description="Return only metadata about output files, not content"
    ),
    authenticated: bool = Depends(verify_api_key),
):
    """Get output files content for a specific job."""
    try:
        # Sanitize inputs
        job_id = InputSanitizer.sanitize_job_id(job_id)
        if host:
            host = InputSanitizer.sanitize_hostname(host)

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

    except HTTPException:
        raise
    except Exception as e:
        # Try cache fallback for output
        cached_output = await _cache_middleware.get_cached_job_output(job_id, host)
        if cached_output:
            logger.info(
                f"Returning cached output for job {job_id} (SLURM query failed)"
            )
            return cached_output

        logger.error(f"Error in get_job_output: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to read job output: {str(e)}"
        )


@app.get("/api/jobs/{job_id}/script")
async def get_job_script(
    job_id: str,
    host: Optional[str] = Query(None, description="Specific host to search"),
    authenticated: bool = Depends(verify_api_key),
):
    """Get the batch script content for a specific job."""
    try:
        # Sanitize inputs
        job_id = InputSanitizer.sanitize_job_id(job_id)
        if host:
            host = InputSanitizer.sanitize_hostname(host)

        manager = get_slurm_manager()

        # Filter hosts
        slurm_hosts = manager.slurm_hosts
        if host:
            slurm_hosts = [h for h in slurm_hosts if h.host.hostname == host]
            if not slurm_hosts:
                raise HTTPException(status_code=404, detail="Host not found")

        # Check cache first - this should be our primary source
        cached_script = await _cache_middleware.get_cached_job_script(job_id, host)
        if cached_script:
            logger.info(f"Returning cached script for job {job_id}")
            return cached_script

        # Try to get from SLURM and cache it
        script_found_in_slurm = False
        for slurm_host in slurm_hosts:
            try:
                conn = manager._get_connection(slurm_host.host)
                script_content = manager.slurm_client.get_job_batch_script(
                    conn, job_id, slurm_host.host.hostname
                )

                if script_content is not None:
                    script_found_in_slurm = True
                    response = {
                        "job_id": job_id,
                        "hostname": slurm_host.host.hostname,
                        "script_content": script_content,
                        "content_length": len(script_content),
                    }

                    # Cache the script for future use
                    await _cache_middleware.cache_job_script(
                        job_id, slurm_host.host.hostname, script_content
                    )

                    return response

            except Exception as e:
                logger.debug(
                    f"Error getting script from {slurm_host.host.hostname}: {e}"
                )
                continue

        # If we didn't find the script in SLURM, check cache again without host filter
        # This handles cases where the job moved hosts or host wasn't specified correctly
        if not script_found_in_slurm and host:
            cached_script = await _cache_middleware.get_cached_job_script(job_id, None)
            if cached_script:
                logger.info(
                    f"Returning cached script for job {job_id} (found without host filter)"
                )
                return cached_script

        # Script not found anywhere
        logger.warning(f"Script not found for job {job_id} in cache or SLURM")
        raise HTTPException(status_code=404, detail="Script not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_job_script: {e}")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


@app.post("/api/jobs/launch", response_model=LaunchJobResponse)
async def launch_job(
    request: LaunchJobRequest, authenticated: bool = Depends(verify_api_key)
):
    """Launch a job by syncing source directory and submitting script."""
    import tempfile

    from ..launch import LaunchManager

    try:
        # Validate and sanitize script
        request.script_content = ScriptValidator.validate_script(request.script_content)

        # Sanitize host
        request.host = InputSanitizer.sanitize_hostname(request.host)

        manager = get_slurm_manager()

        # Validate host exists
        try:
            _ = manager.get_host_by_name(request.host)
        except ValueError:
            raise HTTPException(status_code=400, detail="Host not found")

        # Apply defaults from host configuration if needed
        # Note: Currently defaults are applied at the manager level
        # This could be used for frontend defaults display if needed

        # Validate source directory if provided
        source_dir = None
        if request.source_dir:
            source_dir = PathValidator.validate_path(
                request.source_dir, base_type="local", user_home=Path.home()
            )

            if not source_dir.exists():
                raise HTTPException(
                    status_code=400, detail="Source directory not found"
                )

            if not source_dir.is_dir():
                raise HTTPException(
                    status_code=400, detail="Source path is not a directory"
                )

        # Create temporary script file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False
        ) as tmp_script:
            tmp_script.write(request.script_content)
            script_path = Path(tmp_script.name)

        try:
            # Initialize launch manager
            launch_manager = LaunchManager(manager)

            # Validate SLURM parameters
            slurm_params = SlurmParams(
                job_name=request.job_name[:64]
                if request.job_name
                else None,  # Limit length
                time_min=request.time,
                cpus_per_task=min(request.cpus, 256)
                if request.cpus
                else None,  # Reasonable limit
                mem_gb=min(request.mem, 1024) if request.mem else None,  # 1TB max
                partition=request.partition,
                output=request.output,
                error=request.error,
                constraint=request.constraint,
                account=request.account,
                nodes=min(request.nodes, 100)
                if request.nodes
                else None,  # Reasonable limit
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
                sync_enabled=source_dir is not None,
            )

            if job:
                # Cache the script
                try:
                    await _cache_middleware.cache_job_script(
                        job.job_id, request.host, request.script_content
                    )
                except Exception as e:
                    logger.warning(f"Failed to cache script: {e}")

                return LaunchJobResponse(
                    success=True,
                    job_id=job.job_id,
                    message="Job launched successfully",
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error launching job: {e}")
        raise HTTPException(status_code=500, detail="Failed to launch job")


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    host: Optional[str] = Query(None, description="Specific host"),
    authenticated: bool = Depends(verify_api_key),
):
    """Cancel a running job."""
    try:
        # Sanitize inputs
        job_id = InputSanitizer.sanitize_job_id(job_id)
        if host:
            host = InputSanitizer.sanitize_hostname(host)

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
                        return {"message": "Job cancelled successfully"}
                    else:
                        raise HTTPException(
                            status_code=500, detail="Failed to cancel job"
                        )
            except Exception:
                continue

        raise HTTPException(status_code=404, detail="Job not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


@app.get("/api/local/list")
async def list_local_path(
    path: str = Query("/", description="Local filesystem path to list"),
    limit: int = Query(100, description="Maximum number of entries to return"),
    show_hidden: bool = Query(False, description="Include hidden files/directories"),
    dirs_only: bool = Query(False, description="Show directories only"),
    authenticated: bool = Depends(verify_api_key),
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


@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    # Initialize manager
    _ = get_slurm_manager()
    logger.info("Secure API started, manager initialized")

    # Start cache scheduler
    try:
        await start_cache_scheduler()
        logger.info("Cache scheduler started")
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
        logger.info("Cache scheduler stopped")
    except Exception:
        pass

    # Close connections
    if _slurm_manager:
        _slurm_manager.close_connections()
        logger.info("Closed all SSH connections")

    # Cleanup cache
    try:
        _cache_middleware.cache.close()
        logger.info("Closed job cache")
    except Exception:
        pass


def main():
    """Run the secure web server."""
    import uvicorn

    # Show authentication status
    if REQUIRE_API_KEY:
        print("🔐 Starting SLURM Manager API with authentication enabled")
        print("   API key required for all requests")
    else:
        print("🚀 Starting SLURM Manager API in open mode (no authentication)")
        print("   To enable authentication: export SSYNC_REQUIRE_API_KEY=true")
        print("   To generate API key: ssync auth setup")

    print("📡 Server starting at http://127.0.0.1:8042")

    # Production settings
    uvicorn.run(
        app,
        host="127.0.0.1",  # Only bind to localhost
        port=int(os.getenv("SSYNC_PORT", "8042")),
        log_level=os.getenv("SSYNC_LOG_LEVEL", "info").lower(),
        access_log=False,  # Disable access logs for security
        server_header=False,  # Don't expose server info
        date_header=False,  # Don't expose date
    )


if __name__ == "__main__":
    main()
