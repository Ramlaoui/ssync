"""Secure version of the Slurm Manager API with enhanced security measures."""

import asyncio
import fnmatch
import hashlib
import ipaddress
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .. import config
from ..cache import get_cache
from ..manager import SlurmManager
from ..models.job import JobState
from ..notifications import get_notification_service
from ..notifications.monitor import (
    start_notification_monitor,
    stop_notification_monitor,
)
from ..slurm.params import SlurmParams
from ..utils.async_helpers import create_task
from ..utils.logging import setup_logger
from .cache_middleware import get_cache_middleware
from .cache_scheduler import start_cache_scheduler, stop_cache_scheduler
from .models import (
    ArrayJobGroup,
    CompleteJobDataResponse,
    FileMetadata,
    HostInfoWeb,
    JobInfoWeb,
    JobOutputResponse,
    JobStateWeb,
    JobStatusResponse,
    PartitionResourcesWeb,
    PartitionStatusResponse,
    LaunchJobRequest,
    LaunchJobResponse,
    NotificationDeviceRegistration,
    NotificationPreferences,
    NotificationPreferencesPatch,
    NotificationTestRequest,
    SlurmDefaultsWeb,
    WebPushSubscriptionRegistration,
    WebPushUnsubscribeRequest,
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


def group_array_job_tasks(
    jobs: List[JobInfoWeb], use_cache: bool = True
) -> tuple[List[JobInfoWeb], List[ArrayJobGroup]]:
    """Group array job tasks together using pre-computed cache stats when possible.

    Args:
        jobs: List of jobs to group
        use_cache: If True, use pre-computed stats from cache (much faster)

    Returns:
        - List of non-array jobs (excluding both array tasks and parent entries)
        - List of array job groups
    """
    from collections import defaultdict

    from ..cache import get_cache

    # Separate array tasks from regular jobs
    array_tasks = defaultdict(list)
    parent_jobs = {}  # Map array_job_id to parent job entry
    regular_jobs = []
    array_hostnames = {}  # Map array_job_id to hostname
    array_state_counts = defaultdict(lambda: defaultdict(int))

    for job in jobs:
        # Check if this is an array task (numeric task ID)
        if job.array_job_id and job.array_task_id and job.array_task_id.isdigit():
            # This is an individual array task - add to array_tasks
            array_tasks[job.array_job_id].append(job)
            array_hostnames[job.array_job_id] = job.hostname
            # Track state counts for accurate group status
            if job.state == JobStateWeb.PENDING:
                array_state_counts[job.array_job_id]["pending"] += 1
            elif job.state == JobStateWeb.RUNNING:
                array_state_counts[job.array_job_id]["running"] += 1
            elif job.state == JobStateWeb.COMPLETED:
                array_state_counts[job.array_job_id]["completed"] += 1
            elif job.state == JobStateWeb.FAILED:
                array_state_counts[job.array_job_id]["failed"] += 1
            elif job.state == JobStateWeb.CANCELLED:
                array_state_counts[job.array_job_id]["cancelled"] += 1
            # DO NOT add to regular_jobs - this is part of an array group
        # Check if this is a parent job entry (has brackets like [0-4])
        elif (
            job.array_job_id
            and job.array_task_id
            and "[" in job.array_task_id
            and "]" in job.array_task_id
        ):
            # This is a parent job entry - store it for metadata but don't include in regular jobs
            parent_jobs[job.array_job_id] = job
            array_hostnames[job.array_job_id] = job.hostname
            # DO NOT add to regular_jobs - this will be represented by the array group
        else:
            # Regular non-array job
            regular_jobs.append(job)

    # Create array job groups using the task list for authoritative state counts
    array_groups = []
    cache = get_cache() if use_cache else None

    for array_job_id, tasks in array_tasks.items():
        hostname = array_hostnames.get(array_job_id)
        if not hostname or not tasks:
            continue

        # Use cache for metadata only (name/user), not state counts
        metadata = (
            cache.get_array_job_metadata(array_job_id, hostname) if cache else None
        )
        counts = array_state_counts.get(array_job_id, {})

        first_task = tasks[0]
        group = ArrayJobGroup(
            array_job_id=array_job_id,
            job_name=(metadata.get("job_name") if metadata else None)
            or first_task.name,
            hostname=hostname,
            user=(metadata.get("user") if metadata else None) or first_task.user,
            total_tasks=len(tasks),
            tasks=tasks,
            pending_count=counts.get("pending", 0),
            running_count=counts.get("running", 0),
            completed_count=counts.get("completed", 0),
            failed_count=counts.get("failed", 0),
            cancelled_count=counts.get("cancelled", 0),
        )
        array_groups.append(group)

    return regular_jobs, array_groups


def deduplicate_array_jobs(jobs: List[JobInfoWeb]) -> List[JobInfoWeb]:
    """Remove duplicate array job entries when not grouping.

    When array jobs are NOT grouped, we should only show individual tasks,
    not the parent entry (with brackets like [0-4]).

    Args:
        jobs: List of jobs that may contain duplicates

    Returns:
        List of jobs with array job parent entries filtered out
    """
    deduplicated_jobs = []

    for job in jobs:
        # Skip parent array job entries (those with brackets like [0-4])
        if (
            job.array_job_id
            and job.array_task_id
            and "[" in job.array_task_id
            and "]" in job.array_task_id
        ):
            # This is a parent entry - skip it
            continue
        else:
            # Keep regular jobs and individual array tasks
            deduplicated_jobs.append(job)

    return deduplicated_jobs


def _parse_submit_time(value: Optional[str]) -> datetime:
    """Parse submit_time strings safely for sorting."""
    if not value:
        return datetime.fromtimestamp(0)
    try:
        return datetime.fromisoformat(value)
    except Exception:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return datetime.fromtimestamp(0)


def apply_grouped_limit(
    display_jobs: List[JobInfoWeb],
    array_groups: Optional[List[ArrayJobGroup]],
    limit: Optional[int],
) -> tuple[List[JobInfoWeb], Optional[List[ArrayJobGroup]]]:
    """Apply limit where each array group counts as one item."""
    if not limit or limit <= 0:
        return display_jobs, array_groups

    groups = array_groups or []

    items: list[tuple[datetime, str, object]] = []
    for job in display_jobs:
        items.append((_parse_submit_time(job.submit_time), "job", job))
    for group in groups:
        group_time = None
        if group.tasks:
            group_time = max(
                (_parse_submit_time(t.submit_time) for t in group.tasks if t),
                default=None,
            )
        items.append((group_time or datetime.fromtimestamp(0), "group", group))

    items.sort(key=lambda item: item[0], reverse=True)
    items = items[:limit]

    limited_jobs: List[JobInfoWeb] = []
    limited_groups: List[ArrayJobGroup] = []
    for _ts, kind, obj in items:
        if kind == "job":
            limited_jobs.append(obj)  # type: ignore[arg-type]
        else:
            limited_groups.append(obj)  # type: ignore[arg-type]

    return limited_jobs, limited_groups


def _compute_array_group_runtime(
    array_job_id: str, tasks: List[JobInfoWeb]
) -> List[ArrayJobGroup]:
    """Compute array job group statistics at runtime (fallback when cache unavailable)."""
    from collections import defaultdict

    # Count states by iterating through tasks
    state_counts = defaultdict(int)
    for task in tasks:
        if task.state == JobStateWeb.PENDING:
            state_counts["pending"] += 1
        elif task.state == JobStateWeb.RUNNING:
            state_counts["running"] += 1
        elif task.state == JobStateWeb.COMPLETED:
            state_counts["completed"] += 1
        elif task.state == JobStateWeb.FAILED:
            state_counts["failed"] += 1
        elif task.state == JobStateWeb.CANCELLED:
            state_counts["cancelled"] += 1

    # Use the first task's info for the group metadata
    first_task = tasks[0]

    group = ArrayJobGroup(
        array_job_id=array_job_id,
        job_name=first_task.name,
        hostname=first_task.hostname,
        user=first_task.user,
        total_tasks=len(tasks),
        tasks=tasks,
        pending_count=state_counts.get("pending", 0),
        running_count=state_counts.get("running", 0),
        completed_count=state_counts.get("completed", 0),
        failed_count=state_counts.get("failed", 0),
        cancelled_count=state_counts.get("cancelled", 0),
    )

    logger.debug(f"Computed runtime stats for array {array_job_id}: {len(tasks)} tasks")
    return [group]


# Check if docs should be enabled before creating the app
ENABLE_DOCS = os.getenv("SSYNC_ENABLE_DOCS", "false").lower() == "true"

# API Key security scheme for Swagger UI
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

app = FastAPI(
    title="Slurm Manager API",
    description="Secure Web API for managing Slurm jobs across multiple clusters",
    version="2.0.0",
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
)

THREAD_POOL_SIZE = int(os.getenv("SSYNC_THREAD_POOL_SIZE", str(os.cpu_count() + 4)))
executor = ThreadPoolExecutor(
    max_workers=THREAD_POOL_SIZE, thread_name_prefix="ssh-worker"
)
logger.info(f"Initialized thread pool with {THREAD_POOL_SIZE} workers")


@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    # Enable memory logging for API access
    from ..utils.logging import enable_memory_logging

    enable_memory_logging()

    logger.info(f"Starting Slurm Manager API with {THREAD_POOL_SIZE} worker threads")

    _ = get_slurm_manager()
    logger.info("Secure API started, manager initialized")

    # Start the watcher service
    try:
        from ..watchers.service import start_watcher_service

        await start_watcher_service()
        logger.info("Watcher service started")
    except Exception as e:
        logger.warning(f"Failed to start watcher service: {e}")

    try:
        await start_cache_scheduler()
        logger.info("Cache scheduler started")
    except Exception as e:
        logger.error(f"Failed to start cache scheduler: {e}")

    create_task(periodic_connection_health_check())
    logger.info("Started periodic connection health check")

    try:
        await start_notification_monitor()
        logger.info("Notification monitor started")
    except Exception as e:
        logger.warning(f"Failed to start notification monitor: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    global _slurm_manager

    logger.info("Shutting down Slurm Manager API...")

    _shutdown_event.set()

    # Stop the watcher service
    try:
        from ..watchers.service import stop_watcher_service

        await stop_watcher_service()
        logger.info("Watcher service stopped")
    except Exception:
        pass

    try:
        await stop_cache_scheduler()
        logger.info("Cache scheduler stopped")
    except Exception:
        pass

    try:
        await stop_notification_monitor()
        logger.info("Notification monitor stopped")
    except Exception:
        pass

    try:
        api_key_manager.flush_usage_stats()
    except Exception:
        pass

    executor.shutdown(wait=True, cancel_futures=True)
    logger.info("Thread pool shutdown complete")

    if _slurm_manager:
        _slurm_manager.close_connections()
        logger.info("Closed all SSH connections")

    # Cleanup cache
    try:
        _cache_middleware.cache.close()
        logger.info("Closed job cache")
    except Exception:
        pass

    logger.info("Shutdown complete")


# Handle trusted hosts - support both domain wildcards and IP ranges
trusted_hosts_env = os.getenv("SSYNC_TRUSTED_HOSTS", "localhost,127.0.0.1")
trusted_hosts_list = [h.strip() for h in trusted_hosts_env.split(",") if h.strip()]


# Custom trusted host middleware that supports IP ranges
class CustomTrustedHostMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_hosts=None, allowed_ip_patterns=None):
        super().__init__(app)
        self.allowed_hosts = allowed_hosts or []
        self.allowed_ip_patterns = allowed_ip_patterns or []

    def is_ip_allowed(self, ip: str) -> bool:
        """Check if IP matches any allowed patterns."""
        for pattern in self.allowed_ip_patterns:
            if fnmatch.fnmatch(ip, pattern):
                return True
        return False

    async def dispatch(self, request, call_next):
        host_header = request.headers.get("host", "")

        # Extract hostname/IP from host header (remove port if present)
        if ":" in host_header:
            host_part = host_header.split(":")[0]
        else:
            host_part = host_header

        # Check if host is allowed
        allowed = False

        # Check domain patterns
        for allowed_host in self.allowed_hosts:
            if allowed_host == "*":
                allowed = True
                break
            elif allowed_host.startswith("*."):
                if host_part.endswith(allowed_host[1:]):
                    allowed = True
                    break
            elif host_part == allowed_host:
                allowed = True
                break

        # Check IP patterns
        if not allowed and self.allowed_ip_patterns:
            try:
                # Try to parse as IP to handle both hostname and IP
                ipaddress.ip_address(host_part)
                allowed = self.is_ip_allowed(host_part)
            except ValueError:
                # Not an IP, could be hostname - check patterns anyway
                allowed = self.is_ip_allowed(host_part)

        if not allowed:
            logger.warning(
                f"Rejected host header: {host}, allowed_hosts: {self.allowed_hosts}, allowed_ip_patterns: {self.allowed_ip_patterns}"
            )
            return Response(f"Invalid host header: {host}", status_code=400)

        return await call_next(request)


# Parse trusted hosts into domain patterns and IP patterns
valid_patterns = []
ip_patterns = []

for host in trusted_hosts_list:
    if "*" in host and not host.startswith("*."):
        # This is an IP wildcard pattern
        ip_patterns.append(host)
    else:
        # Valid domain pattern or exact match
        valid_patterns.append(host)

# Use custom middleware that supports IP patterns
app.add_middleware(
    CustomTrustedHostMiddleware,
    allowed_hosts=valid_patterns,
    allowed_ip_patterns=ip_patterns,
)

ALLOWED_ORIGINS = os.getenv("SSYNC_ALLOWED_ORIGINS", "").split(",")
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS if o.strip()]

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["X-API-Key", "Content-Type"],
        max_age=3600,
    )

rate_limiter = RateLimiter(
    requests_per_minute=int(os.getenv("SSYNC_RATE_LIMIT_PER_MINUTE", "120")),
    requests_per_hour=int(os.getenv("SSYNC_RATE_LIMIT_PER_HOUR", "2000")),
    burst_size=int(os.getenv("SSYNC_BURST_SIZE", "50")),
)

api_key_manager = APIKeyManager()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
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

REQUIRE_API_KEY = os.getenv("SSYNC_REQUIRE_API_KEY", "false").lower() == "true"


async def verify_api_key(
    request: Request, api_key: Optional[str] = Depends(api_key_header)
):
    """Verify API key for protected endpoints."""
    if not REQUIRE_API_KEY:
        return True

    if request.url.path == "/health":
        return True

    if not api_key:
        raise HTTPException(
            status_code=401, detail="API key required. Please provide X-API-Key header."
        )

    if not api_key_manager.validate_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid or expired API key.")

    return True


async def get_api_key(
    request: Request, api_key: Optional[str] = Depends(api_key_header)
) -> str:
    """Return validated API key for endpoints that need to bind data to it."""
    if not REQUIRE_API_KEY:
        return ""

    if request.url.path == "/health":
        return ""

    if not api_key:
        raise HTTPException(
            status_code=401, detail="API key required. Please provide X-API-Key header."
        )

    if not api_key_manager.validate_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid or expired API key.")

    return api_key


async def verify_api_key_flexible(
    request: Request, api_key_query: Optional[str] = Query(None, alias="api_key")
):
    """Verify API key from headers or query params (for EventSource endpoints)."""
    if not REQUIRE_API_KEY:
        return True

    if request.url.path == "/health":
        return True

    # Check header first
    api_key = request.headers.get("x-api-key")

    # Fall back to query parameter (for EventSource which can't send headers)
    if not api_key:
        api_key = api_key_query

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Please provide X-API-Key header or api_key query parameter.",
        )

    if not api_key_manager.validate_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid or expired API key.")

    return True


async def verify_websocket_api_key(websocket: WebSocket):
    """Verify API key for WebSocket connections before accepting."""
    if not REQUIRE_API_KEY:
        return True

    # WebSocket clients can send API key via:
    # 1. Query parameter: ws://host/ws/endpoint?api_key=xxx
    # 2. Header: x-api-key (during handshake)

    # Check query parameters first
    api_key = websocket.query_params.get("api_key")
    logger.info(
        f"WebSocket auth: api_key from query params: {bool(api_key)}, path: {websocket.url.path}"
    )

    # Fall back to headers
    if not api_key:
        api_key = websocket.headers.get("x-api-key")
        logger.info(f"WebSocket auth: api_key from headers: {bool(api_key)}")

    if not api_key:
        logger.warning(
            f"WebSocket auth failed: no API key provided for {websocket.url.path}"
        )
        await websocket.close(code=1008, reason="API key required")
        return False

    if not api_key_manager.validate_key(api_key):
        logger.warning(
            f"WebSocket auth failed: invalid API key for {websocket.url.path}"
        )
        await websocket.close(code=1008, reason="Invalid or expired API key")
        return False

    logger.info(f"WebSocket auth successful for {websocket.url.path}")
    return True


def _normalize_device_token(token: str) -> str:
    token = re.sub(r"[^0-9a-fA-F]", "", token or "")
    if len(token) < 32:
        raise HTTPException(status_code=400, detail="Invalid device token")
    return token.lower()


def _normalize_environment(environment: Optional[str]) -> Optional[str]:
    if environment is None:
        return None
    env = environment.lower()
    if env not in {"sandbox", "production"}:
        raise HTTPException(status_code=400, detail="Invalid environment value")
    return env


def _sanitize_notification_preferences(data: dict) -> dict:
    allowed_states = data.get("allowed_states")
    if allowed_states is not None:
        valid_states = {state.value for state in JobState}
        for state in allowed_states:
            if state not in valid_states:
                raise HTTPException(
                    status_code=400, detail=f"Invalid job state: {state}"
                )

    def _sanitize_list(values, sanitizer):
        if values is None:
            return None
        return [sanitizer(value) for value in values]

    data["muted_job_ids"] = _sanitize_list(
        data.get("muted_job_ids"), InputSanitizer.sanitize_job_id
    )
    data["muted_hosts"] = _sanitize_list(
        data.get("muted_hosts"), InputSanitizer.sanitize_hostname
    )
    data["allowed_users"] = _sanitize_list(
        data.get("allowed_users"), InputSanitizer.sanitize_username
    )
    patterns = data.get("muted_job_name_patterns")
    if patterns is not None:
        data["muted_job_name_patterns"] = [
            InputSanitizer.sanitize_text(pattern, max_length=200)
            for pattern in patterns
        ]

    return data


_slurm_manager: Optional[SlurmManager] = None
_config_last_modified: Optional[float] = None
_shutdown_event = threading.Event()


async def periodic_connection_health_check():
    """Periodically check and clean up stale SSH connections."""
    check_interval = 600  # Check every 10 minutes (reduced frequency)

    while not _shutdown_event.is_set():
        try:
            await asyncio.sleep(check_interval)

            if _shutdown_event.is_set():
                break

            try:
                manager = get_slurm_manager()
                unhealthy_count = manager.check_connection_health()

                if unhealthy_count > 0:
                    logger.info(
                        f"Periodic health check: Removed {unhealthy_count} unhealthy connections"
                    )
                else:
                    pass
            except Exception as e:
                logger.error(f"Error during periodic connection health check: {e}")

        except asyncio.CancelledError:
            logger.info("Periodic connection health check cancelled")
            break
        except Exception as e:
            logger.error(f"Unexpected error in periodic health check: {e}")

    logger.info("Periodic connection health check stopped")


_cache_middleware = get_cache_middleware()

frontend_dist = Path(__file__).parent.parent.parent.parent / "web-frontend" / "dist"
if frontend_dist.exists():
    app.mount(
        "/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets"
    )

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

    @app.get("/")
    async def root(authenticated: bool = Depends(verify_api_key)):
        """API root endpoint."""
        return {
            "message": "Slurm Manager API",
            "version": "2.0.0",
            "security": "enhanced",
            "documentation": "/docs" if ENABLE_DOCS else "disabled",
            "frontend": "Not built. Run 'npm run build' in web-frontend directory.",
        }


def get_slurm_manager() -> SlurmManager:
    """Get or create persistent Slurm manager instance with connection reuse."""
    global _slurm_manager, _config_last_modified

    config_path = config.config_path

    # Check if config file has been modified
    current_mtime = config_path.stat().st_mtime if config_path.exists() else 0
    config_changed = (
        _config_last_modified is None or current_mtime > _config_last_modified
    )

    # Create or recreate manager if needed
    if _slurm_manager is None or config_changed:
        # Close existing manager if it exists
        if _slurm_manager:
            _slurm_manager.close_connections()

        # Load config and create new manager
        slurm_hosts = config.load_config()

        # Get connection timeout from environment or use default
        connection_timeout = int(os.environ.get("SSYNC_CONNECTION_TIMEOUT", "30"))

        _slurm_manager = SlurmManager(
            slurm_hosts, connection_timeout=connection_timeout
        )
        _config_last_modified = current_mtime
    else:
        pass
    return _slurm_manager


@app.get("/health")
async def health_check():
    """Health check endpoint (no auth required)."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.post("/api/shutdown")
async def shutdown_server(authenticated: bool = Depends(verify_api_key)):
    """Shutdown the API server gracefully."""
    import asyncio
    import os
    import signal

    logger.info("Shutdown requested via API")

    async def delayed_shutdown():
        """Shutdown after a brief delay to allow response to be sent."""
        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    create_task(delayed_shutdown())
    return {"status": "shutting_down", "message": "Server is shutting down"}


@app.get("/api/logs")
async def get_server_logs(
    lines: int = Query(default=50, ge=1, le=1000),
    authenticated: bool = Depends(verify_api_key),
):
    """Get recent server logs."""
    from ..utils.logging import get_memory_handler

    memory_handler = get_memory_handler()
    logs = memory_handler.get_logs(lines)
    return {"logs": logs, "count": len(logs)}


@app.get("/api/info")
async def api_info(authenticated: bool = Depends(verify_api_key)):
    """API info endpoint."""
    return {
        "message": "Slurm Manager API",
        "version": "2.0.0",
        "security": "enhanced",
        "documentation": "/docs" if ENABLE_DOCS else "disabled",
    }


@app.get("/api/connections/stats")
async def get_connection_stats(authenticated: bool = Depends(verify_api_key)):
    """Get current SSH connection statistics."""
    try:
        manager = get_slurm_manager()
        stats = manager.get_connection_stats()
        health_check_count = manager.check_connection_health()

        return {
            "stats": stats,
            "unhealthy_removed": health_check_count,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting connection stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get connection stats")


@app.post("/api/connections/refresh")
async def refresh_connections(authenticated: bool = Depends(verify_api_key)):
    """Refresh all SSH connections by closing and recreating them."""
    try:
        manager = get_slurm_manager()
        refreshed_count = manager.refresh_connections()

        logger.info(f"Manually refreshed {refreshed_count} SSH connections")

        return {
            "message": f"Refreshed {refreshed_count} connections",
            "refreshed_count": refreshed_count,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error refreshing connections: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh connections")


@app.get("/api/jobs/{job_id}/data", response_model=CompleteJobDataResponse)
async def get_complete_job_data(
    job_id: str,
    host: Optional[str] = Query(None, description="Specific host to search"),
    include_outputs: bool = Query(True, description="Include stdout/stderr content"),
    lines: Optional[int] = Query(
        None, description="Number of output lines to return (tail)"
    ),
    authenticated: bool = Depends(verify_api_key),
):
    """Get complete job data (info + script + outputs) in a single request."""
    try:
        job_id = InputSanitizer.sanitize_job_id(job_id)
        if host:
            host = InputSanitizer.sanitize_hostname(host)

        # Import here to avoid circular imports
        from ..job_data_manager import get_job_data_manager

        job_data_manager = get_job_data_manager()

        # Try to get from specific host if provided
        if host:
            complete_data = await job_data_manager.get_job_data(job_id, host)
        else:
            # Search all hosts
            manager = get_slurm_manager()
            complete_data = None

            for slurm_host in manager.slurm_hosts:
                complete_data = await job_data_manager.get_job_data(
                    job_id, slurm_host.host.hostname
                )
                if complete_data:
                    break

        if not complete_data:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        # Convert JobInfo to JobInfoWeb
        job_info_web = JobInfoWeb(
            job_id=complete_data.job_info.job_id,
            name=complete_data.job_info.name,
            state=complete_data.job_info.state,
            user=complete_data.job_info.user,
            partition=complete_data.job_info.partition,
            submit_time=complete_data.job_info.submit_time,
            start_time=complete_data.job_info.start_time,
            end_time=complete_data.job_info.end_time,
            runtime=complete_data.job_info.runtime,
            time_limit=complete_data.job_info.time_limit,
            nodes=complete_data.job_info.nodes,
            cpus=complete_data.job_info.cpus,
            memory=complete_data.job_info.memory,
            reason=complete_data.job_info.reason,
            hostname=complete_data.job_info.hostname,
            stdout_file=complete_data.job_info.stdout_file,
            stderr_file=complete_data.job_info.stderr_file,
            work_dir=complete_data.job_info.work_dir,
        )

        # Prepare response
        response = CompleteJobDataResponse(
            job_id=job_id,
            hostname=complete_data.job_info.hostname,
            job_info=job_info_web,
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

        # Add outputs if requested
        if include_outputs:
            stdout_content = complete_data.stdout_content
            stderr_content = complete_data.stderr_content

            # Apply line limit if specified
            if lines and stdout_content:
                stdout_lines = stdout_content.split("\n")
                if len(stdout_lines) > lines:
                    stdout_content = "\n".join(stdout_lines[-lines:])

            if lines and stderr_content:
                stderr_lines = stderr_content.split("\n")
                if len(stderr_lines) > lines:
                    stderr_content = "\n".join(stderr_lines[-lines:])

            response.stdout = stdout_content
            response.stderr = stderr_content

            # Basic metadata
            if stdout_content:
                response.stdout_metadata = FileMetadata(
                    size=len(stdout_content),
                    line_count=len(stdout_content.split("\n")),
                    last_modified=None,
                    access_path=complete_data.job_info.stdout_file,
                )

            if stderr_content:
                response.stderr_metadata = FileMetadata(
                    size=len(stderr_content),
                    line_count=len(stderr_content.split("\n")),
                    last_modified=None,
                    access_path=complete_data.job_info.stderr_file,
                )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_complete_job_data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


@app.get("/api/cache/stats")
async def get_cache_stats(authenticated: bool = Depends(verify_api_key)):
    """Get cache statistics including date range cache information."""
    try:
        stats = await _cache_middleware.get_cache_stats()

        # Clean up expired entries while we're at it
        _cache_middleware.cache.cleanup_expired_ranges()

        # Add request coalescer stats
        from ..request_coalescer import get_request_coalescer

        coalescer = get_request_coalescer()
        coalescer_stats = coalescer.get_stats()

        return {
            "status": "success",
            "statistics": {
                **stats,
                "request_coalescer": coalescer_stats,
            },
            "message": "Cache statistics retrieved successfully",
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve cache statistics"
        )


@app.post("/api/cache/clear")
async def clear_cache(authenticated: bool = Depends(verify_api_key)):
    """Clear all cache entries."""
    try:
        cache = get_cache()
        # Clear all cache tables
        cache.clear_all()

        return {"status": "success", "message": "Cache cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear cache")


@app.get("/api/cache/fetch-state")
async def get_fetch_state(
    host: Optional[str] = Query(None, description="Specific host to check"),
    authenticated: bool = Depends(verify_api_key),
):
    """Get the incremental fetch state for hosts."""
    try:
        cache = get_cache()
        manager = get_slurm_manager()

        fetch_states = {}

        # Get states for requested hosts
        hosts_to_check = []
        if host:
            # Sanitize host
            host = InputSanitizer.sanitize_hostname(host)
            hosts_to_check = [h for h in manager.slurm_hosts if h.host.hostname == host]
            if not hosts_to_check:
                raise HTTPException(status_code=404, detail=f"Host '{host}' not found")
        else:
            hosts_to_check = manager.slurm_hosts

        for slurm_host in hosts_to_check:
            hostname = slurm_host.host.hostname
            state = cache.get_host_fetch_state(hostname)

            if state:
                # Parse the times for better display
                last_fetch_utc = datetime.fromisoformat(state["last_fetch_time_utc"])
                time_since_fetch = datetime.now(timezone.utc) - last_fetch_utc.replace(
                    tzinfo=timezone.utc
                )

                fetch_states[hostname] = {
                    "last_fetch_time": state["last_fetch_time"],
                    "last_fetch_time_utc": state["last_fetch_time_utc"],
                    "cluster_timezone": state["cluster_timezone"],
                    "fetch_count": state["fetch_count"],
                    "updated_at": state["updated_at"],
                    "time_since_fetch_seconds": int(time_since_fetch.total_seconds()),
                    "time_since_fetch_human": _format_time_delta(time_since_fetch),
                }
            else:
                fetch_states[hostname] = {
                    "status": "never_fetched",
                    "message": "No incremental fetch performed yet for this host",
                }

        return {
            "status": "success",
            "fetch_states": fetch_states,
            "incremental_fetch_enabled": True,
            "message": "Fetch state retrieved successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting fetch state: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve fetch state")


def _format_time_delta(delta: timedelta) -> str:
    """Format a timedelta into a human-readable string."""
    total_seconds = int(delta.total_seconds())

    if total_seconds < 60:
        return f"{total_seconds} seconds"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    else:
        days = total_seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}"


async def _run_in_executor(func, *args, **kwargs):
    """Run blocking functions in the shared thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))


@app.get("/api/hosts", response_model=List[HostInfoWeb])
async def get_hosts(authenticated: bool = Depends(verify_api_key)):
    """Get list of configured Slurm hosts."""
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


@app.get("/api/partitions", response_model=List[PartitionStatusResponse])
async def get_partitions(
    host: Optional[str] = Query(None, description="Specific host to query"),
    force_refresh: bool = Query(
        False, description="Force refresh from Slurm, bypassing cache"
    ),
    authenticated: bool = Depends(verify_api_key),
):
    """Get partition resource state across hosts."""
    try:
        manager = get_slurm_manager()

        if host:
            host = InputSanitizer.sanitize_hostname(host)
            slurm_hosts = [h for h in manager.slurm_hosts if h.host.hostname == host]
            if not slurm_hosts:
                raise HTTPException(status_code=404, detail="Host not found")
        else:
            slurm_hosts = manager.slurm_hosts

        start = time.perf_counter()

        async def fetch_host_partitions(slurm_host):
            hostname = slurm_host.host.hostname
            try:
                conn = await _run_in_executor(
                    manager._get_connection, slurm_host.host
                )
                partitions, cached, cache_age, stale = await _run_in_executor(
                    manager.slurm_client.get_partition_state,
                    conn,
                    hostname,
                    force_refresh,
                )

                partition_web = []
                for partition in partitions:
                    gpu_types = None
                    if partition.gpu_types:
                        gpu_types = {
                            k: {"total": v["total"], "used": v["used"]}
                            for k, v in partition.gpu_types.items()
                        }

                    partition_web.append(
                        PartitionResourcesWeb(
                            partition=partition.name,
                            availability=partition.availability,
                            states=sorted(partition.states),
                            nodes_total=partition.nodes_total,
                            cpus_alloc=partition.cpus_alloc,
                            cpus_idle=partition.cpus_idle,
                            cpus_other=partition.cpus_other,
                            cpus_total=partition.cpus_total,
                            gpus_total=partition.gpus_total,
                            gpus_used=partition.gpus_used,
                            gpus_idle=partition.gpus_idle,
                            gpu_types=gpu_types,
                        )
                    )

                updated_at = None
                cache_age_seconds = None
                if cached:
                    cache_age_seconds = int(cache_age)
                    updated_at = (
                        datetime.now(timezone.utc) - timedelta(seconds=cache_age)
                    ).isoformat()
                else:
                    updated_at = datetime.now(timezone.utc).isoformat()

                return PartitionStatusResponse(
                    hostname=hostname,
                    partitions=partition_web,
                    query_time=f"{time.perf_counter() - start:.3f}s",
                    cached=cached,
                    stale=stale,
                    cache_age_seconds=cache_age_seconds,
                    updated_at=updated_at,
                )
            except Exception as e:
                logger.error(f"Failed to fetch partitions for {hostname}: {e}")
                return PartitionStatusResponse(
                    hostname=hostname,
                    partitions=[],
                    query_time=f"{time.perf_counter() - start:.3f}s",
                    error=sanitize_error_message(e),
                )

        tasks = [fetch_host_partitions(slurm_host) for slurm_host in slurm_hosts]
        return await asyncio.gather(*tasks)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting partition state: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve partition state"
        )


@app.get("/api/status", response_model=List[JobStatusResponse])
async def get_job_status(
    request: Request,
    host: Optional[str] = Query(None, description="Specific host to query"),
    user: Optional[str] = Query(
        None, description="User to filter jobs for (use '*' or 'all' for all users)"
    ),
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
    group_array_jobs: bool = Query(False, description="Group array job tasks together"),
    force_refresh: bool = Query(
        False, description="Force refresh from Slurm, bypassing all caches"
    ),
    profile: bool = Query(
        False,
        description="Enable server-side timing profile logs for this request",
    ),
    authenticated: bool = Depends(verify_api_key),
):
    """Get job status across hosts."""
    try:
        if host:
            host = InputSanitizer.sanitize_hostname(host)

        # Check for special "all users" values
        skip_user_detection = False
        if user and user.lower() in ["*", "all"]:
            logger.warning(
                f"⚠️ SECURITY ALERT: Special user value '{user}' detected - attempting to fetch ALL users' jobs"
            )
            logger.warning(
                "This will fetch jobs from ALL users on the cluster, which may be slow and cause cache pollution"
            )
            logger.warning(
                f"Request from: {request.client.host if request and hasattr(request, 'client') else 'unknown'}"
            )
            user = None  # Don't filter by user
            skip_user_detection = True  # Skip auto-detection of current user
        elif user:
            logger.info(f"Filtering for specific user: {user}")
            user = InputSanitizer.sanitize_username(user)
        else:
            logger.info(
                "No user specified - will auto-detect current user for security"
            )

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

        # Get cache middleware
        cache_middleware = get_cache_middleware()

        # OPTIMIZATION: For multi-host queries, use JobDataManager directly for true concurrency
        if len(slurm_hosts) > 1 and not job_id_list:
            # Import here to avoid circular imports
            from ..job_data_manager import get_job_data_manager

            logger.info(
                f"Using optimized concurrent fetching for {len(slurm_hosts)} hosts"
            )
            logger.info(
                f"Parameters: user={user}, skip_user_detection={skip_user_detection}"
            )
            job_data_manager = get_job_data_manager()

            # Let JobDataManager handle all hosts concurrently in one call
            try:
                all_jobs = await job_data_manager.fetch_all_jobs(
                    hostname=None,  # Fetch from all hosts
                    user=user,
                    since=since,
                    limit=limit,
                    job_ids=job_id_list,
                    state_filter=state,
                    active_only=active_only,
                    completed_only=completed_only,
                    skip_user_detection=skip_user_detection,
                    force_refresh=force_refresh,
                    profile=profile,
                )

                # Group jobs by hostname and create responses
                jobs_by_host = {}
                for job in all_jobs:
                    hostname = job.hostname
                    if hostname not in jobs_by_host:
                        jobs_by_host[hostname] = []
                    jobs_by_host[hostname].append(job)

                # Apply search filter if provided
                if search:
                    search_lower = search.lower()
                    for hostname in jobs_by_host:
                        filtered_jobs = []
                        for job in jobs_by_host[hostname]:
                            web_job = JobInfoWeb.from_job_info(job)
                            if search_lower in job.job_id.lower() or (
                                job.name and search_lower in job.name.lower()
                            ):
                                filtered_jobs.append(web_job)
                        jobs_by_host[hostname] = filtered_jobs
                else:
                    # Convert to JobInfoWeb
                    for hostname in jobs_by_host:
                        jobs_by_host[hostname] = [
                            JobInfoWeb.from_job_info(job)
                            for job in jobs_by_host[hostname]
                        ]

                # Create responses for each host
                results = []
                for slurm_host in slurm_hosts:
                    hostname = slurm_host.host.hostname
                    host_jobs = jobs_by_host.get(hostname, [])

                    # Apply array job grouping if requested
                    array_groups = None
                    if group_array_jobs and host_jobs:
                        display_jobs, array_groups = group_array_job_tasks(host_jobs)
                        display_jobs, array_groups = apply_grouped_limit(
                            display_jobs, array_groups, limit
                        )
                    else:
                        # Even when not grouping, deduplicate array job parent entries
                        display_jobs = deduplicate_array_jobs(host_jobs)

                    response = JobStatusResponse(
                        hostname=hostname,
                        jobs=display_jobs,
                        total_jobs=(
                            len(display_jobs)
                            + (len(array_groups) if array_groups else 0)
                            if group_array_jobs
                            else len(host_jobs)
                        ),
                        query_time=datetime.now(),
                        group_array_jobs=group_array_jobs,
                        array_groups=array_groups,
                    )
                    results.append(response)

                logger.info(
                    f"Concurrent fetch completed: {sum(len(r.jobs) for r in results)} total jobs from {len(slurm_hosts)} hosts"
                )

                # Verify and update cache to mark completed jobs
                current_job_ids = {}
                for job in all_jobs:
                    if job.hostname not in current_job_ids:
                        current_job_ids[job.hostname] = []
                    current_job_ids[job.hostname].append(job.job_id)
                await cache_middleware._verify_and_update_cache(current_job_ids)

                # Cache results and return
                cached_results = await cache_middleware.cache_job_status_response(
                    results
                )
                return cached_results

            except Exception as e:
                logger.error(f"Error in optimized concurrent fetch: {e}")
                # Fall back to per-host fetching
                logger.info("Falling back to per-host fetching")

        # Define async function to fetch jobs from a single host
        async def fetch_host_jobs(slurm_host):
            hostname = slurm_host.host.hostname

            # Check date range cache first if we have a single host and since parameter
            # Skip cache if force_refresh is True
            if (
                host and since and not job_id_list and not force_refresh
            ):  # Only use cache for date-range queries
                # Build filters dict for cache key
                cache_filters = {
                    "user": user,
                    "state": state,
                    "active_only": active_only,
                    "completed_only": completed_only,
                }

                # Check cache
                cached_jobs = await cache_middleware.check_date_range_cache(
                    hostname=hostname, filters=cache_filters, since=since
                )

                if cached_jobs is not None:
                    # ⚡ FIX: Filter out jobs that are already marked as completed in cache
                    # This prevents showing stale completed jobs while background refresh runs
                    active_cached_jobs = []
                    for job in cached_jobs:
                        # Check if job is marked as completed in cache
                        cached = cache_middleware.cache.get_cached_jobs_by_ids(
                            [job.job_id], hostname
                        ).get(job.job_id)
                        if cached and not cached.is_active:
                            # Job is completed, skip it
                            logger.debug(
                                f"Filtering out completed job {job.job_id} from cache results"
                            )
                            continue
                        active_cached_jobs.append(job)

                    # ⚡ FIX: Trigger background cache refresh if cache is getting stale
                    # This fetches fresh data and properly marks completed jobs
                    cache_entry = cache_middleware.cache.check_date_range_cache_entry(
                        hostname, cache_filters, since
                    )
                    if cache_entry:
                        cache_age = (
                            datetime.now()
                            - cache_entry.get("cached_at", datetime.now())
                        ).total_seconds()
                        if cache_age > 60:  # If cache is older than 60 seconds
                            logger.info(
                                f"Cache for {hostname} is {cache_age:.0f}s old - triggering background refresh"
                            )
                            # Trigger async refresh without awaiting
                            asyncio.create_task(
                                fetch_host_jobs(slurm_host)
                            )

                    # Apply state filter if provided
                    # Note: State filter is applied here because cached jobs may have stale state data
                    if state:
                        active_cached_jobs = [
                            job for job in active_cached_jobs if job.state == state
                        ]

                    # Apply search filter if provided
                    web_jobs = active_cached_jobs
                    if search:
                        search_lower = search.lower()
                        filtered_jobs = []
                        for job in web_jobs:
                            if search_lower in job.job_id.lower() or (
                                job.name and search_lower in job.name.lower()
                            ):
                                filtered_jobs.append(job)
                        web_jobs = filtered_jobs

                    # Apply array job grouping if requested
                    array_groups = None
                    if group_array_jobs and web_jobs:
                        display_jobs, array_groups = group_array_job_tasks(web_jobs)
                        display_jobs, array_groups = apply_grouped_limit(
                            display_jobs, array_groups, limit
                        )
                    else:
                        # Even when not grouping, deduplicate array job parent entries
                        display_jobs = deduplicate_array_jobs(web_jobs)

                    response = JobStatusResponse(
                        hostname=slurm_host.host.hostname,
                        jobs=display_jobs,
                        total_jobs=(
                            len(display_jobs)
                            + (len(array_groups) if array_groups else 0)
                            if group_array_jobs
                            else len(web_jobs)
                        ),
                        query_time=datetime.now(),
                        group_array_jobs=group_array_jobs,
                        array_groups=array_groups,
                        cached=True,  # Mark as cached response
                    )
                    logger.info(
                        f"Served {len(web_jobs)} jobs from date range cache for {hostname} (grouping={group_array_jobs})"
                    )
                    return response

            # Cache miss or not a cacheable query - fetch from Slurm via JobDataManager
            try:
                # Use the async JobDataManager directly
                jobs = await manager.get_all_jobs(
                    slurm_host,
                    user,
                    since,
                    limit,
                    job_id_list,
                    state,
                    active_only,
                    completed_only,
                    skip_user_detection,
                    force_refresh,
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

                # Apply array job grouping if requested
                array_groups = None
                if group_array_jobs and web_jobs:
                    display_jobs, array_groups = group_array_job_tasks(web_jobs)
                    display_jobs, array_groups = apply_grouped_limit(
                        display_jobs, array_groups, limit
                    )
                else:
                    # Even when not grouping, deduplicate array job parent entries
                    display_jobs = deduplicate_array_jobs(web_jobs)

                response = JobStatusResponse(
                    hostname=slurm_host.host.hostname,
                    jobs=display_jobs,
                    total_jobs=(
                        len(display_jobs) + (len(array_groups) if array_groups else 0)
                        if group_array_jobs
                        else len(web_jobs)
                    ),
                    query_time=datetime.now(),
                    group_array_jobs=group_array_jobs,
                    array_groups=array_groups,
                )
                return response

            except Exception as e:
                logger.error(f"Error querying {slurm_host.host.hostname}: {e}")
                # Don't expose internal errors
                return JobStatusResponse(
                    hostname=slurm_host.host.hostname,
                    jobs=[],
                    total_jobs=0,
                    query_time=datetime.now(),
                )

        # Fetch from all hosts concurrently
        results = await asyncio.gather(
            *[fetch_host_jobs(slurm_host) for slurm_host in slurm_hosts]
        )

        # Verify and update cache to mark completed jobs
        current_job_ids = {}
        for response in results:
            if response.jobs:
                current_job_ids[response.hostname] = [
                    job.job_id for job in response.jobs
                ]
        await cache_middleware._verify_and_update_cache(current_job_ids)

        # Cache the results with date range info if applicable
        if host and since and not job_id_list:
            cache_filters = {
                "user": user,
                "state": state,
                "active_only": active_only,
                "completed_only": completed_only,
            }
            cached_results = await cache_middleware.cache_job_status_response(
                results, hostname=host, filters=cache_filters, since=since
            )
        else:
            cached_results = await cache_middleware.cache_job_status_response(results)

        return cached_results

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        logger.error(f"Error in get_job_status: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


async def _refresh_job_in_background(job_id: str, host: Optional[str]):
    """
    Background task to refresh job data from Slurm and broadcast updates via WebSocket.

    This allows cache-first requests to return immediately while still getting fresh data.
    """
    try:
        logger.debug(f"Background refresh started for job {job_id} on host {host}")

        manager = get_slurm_manager()

        # Filter hosts
        slurm_hosts = manager.slurm_hosts
        if host:
            slurm_hosts = [h for h in slurm_hosts if h.host.hostname == host]

        # Search for job across hosts
        for slurm_host in slurm_hosts:
            try:
                job_info = manager.get_job_info(slurm_host, job_id)
                if job_info:
                    job_web = JobInfoWeb.from_job_info(job_info)

                    # Cache the refreshed job data
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

                    # Broadcast update via WebSocket to all connected clients
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
            except Exception as e:
                logger.debug(
                    f"Failed to refresh job {job_id} from host {slurm_host.host.hostname}: {e}"
                )
                continue

        logger.debug(f"Background refresh: job {job_id} not found in Slurm")

    except Exception as e:
        logger.error(f"Background refresh failed for job {job_id}: {e}")


@app.get("/api/jobs/{job_id}", response_model=JobInfoWeb)
async def get_job_details(
    job_id: str,
    host: Optional[str] = Query(None, description="Specific host to search"),
    cache_first: bool = Query(
        False,
        description="Return cached data immediately if available, then refresh in background",
    ),
    authenticated: bool = Depends(verify_api_key),
):
    """Get detailed information for a specific job."""
    try:
        job_id = InputSanitizer.sanitize_job_id(job_id)
        if host:
            host = InputSanitizer.sanitize_hostname(host)

        # If cache_first is requested, return cached data immediately and trigger background refresh
        if cache_first:
            cached_job = await _cache_middleware.get_job_with_cache_fallback(
                job_id, host
            )
            if cached_job:
                logger.info(
                    f"Returning cached job {job_id} immediately (cache_first=true)"
                )
                # Trigger async refresh in background (don't await)
                create_task(_refresh_job_in_background(job_id, host))
                return cached_job

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

                    # Broadcast update via WebSocket
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


@app.get("/api/jobs/{job_id}/output/stream")
async def stream_job_output(
    request: Request,
    job_id: str,
    host: str = Query(..., description="Host where job is running"),
    output_type: str = Query("stdout", regex="^(stdout|stderr)$"),
    chunk_size: int = Query(default=8192, ge=1024, le=1048576),
    api_key: Optional[str] = Query(None, description="API key for EventSource"),
    authenticated: bool = Depends(verify_api_key_flexible),
):
    """Stream compressed job output efficiently."""
    import base64

    job_id = InputSanitizer.sanitize_job_id(job_id)
    host = InputSanitizer.sanitize_hostname(host)

    manager = get_slurm_manager()

    async def generate():
        """Generate Server-Sent Events stream."""
        import json

        # First check cache
        cache = get_cache()
        cached_job = cache.get_cached_job(job_id, host)

        # Send initial metadata event
        metadata = {
            "type": "metadata",
            "output_type": output_type,
            "job_id": job_id,
            "host": host,
        }

        if cached_job:
            # Stream from cache
            if output_type == "stdout":
                compressed_data = cached_job.stdout_compressed
                compression = cached_job.stdout_compression
                original_size = cached_job.stdout_size
            else:
                compressed_data = cached_job.stderr_compressed
                compression = cached_job.stderr_compression
                original_size = cached_job.stderr_size

            if compressed_data:
                # Send metadata
                metadata.update(
                    {
                        "original_size": original_size,
                        "compression": compression,
                        "source": "cache",
                    }
                )
                yield f"data: {json.dumps(metadata)}\n\n"

                if compression == "gzip":
                    # Return compressed data as base64 in chunks
                    # Frontend will decompress
                    chunk_index = 0
                    encoded_data = base64.b64encode(compressed_data).decode("utf-8")

                    # Send in chunks
                    for i in range(0, len(encoded_data), chunk_size):
                        chunk_data = {
                            "type": "chunk",
                            "index": chunk_index,
                            "data": encoded_data[i : i + chunk_size],
                            "compressed": True,
                        }
                        yield f"data: {json.dumps(chunk_data)}\n\n"
                        chunk_index += 1
                        await asyncio.sleep(0)  # Allow other tasks to run
                else:
                    # Uncompressed - send as text chunks
                    chunk_index = 0
                    text_data = compressed_data.decode("utf-8", errors="replace")

                    for i in range(0, len(text_data), chunk_size):
                        chunk_data = {
                            "type": "chunk",
                            "index": chunk_index,
                            "data": text_data[i : i + chunk_size],
                            "compressed": False,
                        }
                        yield f"data: {json.dumps(chunk_data)}\n\n"
                        chunk_index += 1
                        await asyncio.sleep(0)

                # Send completion event
                yield f"data: {json.dumps({'type': 'complete'})}\n\n"
            else:
                # No cached output
                yield f"data: {json.dumps({'type': 'error', 'message': 'No cached output available'})}\n\n"
        else:
            # Fetch fresh with compression
            try:
                # Get connection through thread pool
                result = await asyncio.to_thread(
                    lambda: manager.fetch_job_output_compressed(
                        job_id, host, output_type
                    )
                )

                if result:
                    # Cache the compressed data
                    cache.update_job_outputs_compressed(
                        job_id,
                        host,
                        stdout_data=result if output_type == "stdout" else None,
                        stderr_data=result if output_type == "stderr" else None,
                    )

                    # Send metadata
                    metadata.update(
                        {
                            "original_size": result.get("original_size", 0),
                            "compression": "gzip"
                            if result.get("compressed")
                            else "none",
                            "truncated": result.get("truncated", False),
                            "source": "fresh",
                        }
                    )
                    yield f"data: {json.dumps(metadata)}\n\n"

                    # Send compressed data as base64 chunks
                    chunk_index = 0
                    data = result["data"]  # Already base64 encoded

                    for i in range(0, len(data), chunk_size):
                        chunk_data = {
                            "type": "chunk",
                            "index": chunk_index,
                            "data": data[i : i + chunk_size],
                            "compressed": result.get("compressed", False),
                        }
                        yield f"data: {json.dumps(chunk_data)}\n\n"
                        chunk_index += 1
                        await asyncio.sleep(0)

                    if result.get("truncated"):
                        yield f"data: {json.dumps({'type': 'truncation_notice', 'original_size': result['original_size']})}\n\n"

                    # Send completion
                    yield f"data: {json.dumps({'type': 'complete'})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Output not found or not accessible'})}\n\n"

            except Exception as e:
                logger.error(f"Error streaming output for job {job_id}: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Connection": "keep-alive",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/jobs/{job_id}/output/download")
async def download_job_output(
    job_id: str,
    host: str = Query(..., description="Host where job is running"),
    output_type: str = Query("stdout", regex="^(stdout|stderr)$"),
    compressed: bool = Query(default=False, description="Download as gzip"),
    authenticated: bool = Depends(verify_api_key),
):
    """Download job output file, optionally compressed."""
    import base64
    import gzip
    import io

    job_id = InputSanitizer.sanitize_job_id(job_id)
    host = InputSanitizer.sanitize_hostname(host)

    cache = get_cache()
    manager = get_slurm_manager()

    # Try cache first
    cached_job = cache.get_cached_job(job_id, host)

    content = None
    compression = "none"
    original_size = 0

    if cached_job:
        if output_type == "stdout":
            content = cached_job.stdout_compressed
            compression = cached_job.stdout_compression
            original_size = cached_job.stdout_size
        else:
            content = cached_job.stderr_compressed
            compression = cached_job.stderr_compression
            original_size = cached_job.stderr_size

    # If not in cache, fetch
    if content is None:
        result = await asyncio.to_thread(
            lambda: manager.fetch_job_output_compressed(job_id, host, output_type)
        )

        if result:
            content = base64.b64decode(result["data"])
            compression = result.get("compression", "none")
            original_size = result.get("original_size", 0)

            # Cache it
            cache.update_job_outputs_compressed(
                job_id,
                host,
                stdout_data=result if output_type == "stdout" else None,
                stderr_data=result if output_type == "stderr" else None,
            )

    if content is None:
        raise HTTPException(status_code=404, detail="Output not found")

    # Prepare content for download
    if compressed:
        # User wants compressed
        if compression != "gzip":
            # Compress if not already
            content = gzip.compress(content)
        filename = f"job_{job_id}_{output_type}.log.gz"
        media_type = "application/gzip"
    else:
        # User wants uncompressed
        if compression == "gzip":
            # Decompress
            content = gzip.decompress(content)
        filename = f"job_{job_id}_{output_type}.log"
        media_type = "text/plain"

    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(len(content)),
            "X-Original-Size": str(original_size),
        },
    )


@app.get("/api/jobs/{job_id}/output", response_model=JobOutputResponse)
async def get_job_output(
    job_id: str,
    host: Optional[str] = Query(None, description="Specific host to search"),
    lines: Optional[int] = Query(None, description="Number of lines to return (tail)"),
    metadata_only: bool = Query(
        False, description="Return only metadata about output files, not content"
    ),
    force_refresh: bool = Query(
        False, description="Force refresh from SSH even if cached"
    ),
    authenticated: bool = Depends(verify_api_key),
):
    """Get output files content for a specific job."""
    try:
        job_id = InputSanitizer.sanitize_job_id(job_id)
        if host:
            host = InputSanitizer.sanitize_hostname(host)

        # Get cache middleware early as it's used in multiple branches
        cache_middleware = get_cache_middleware()

        # If force_refresh is True, skip cache and fetch directly
        if force_refresh:
            logger.info(f"Force refresh requested for job {job_id} outputs")
            # Import here to avoid circular imports
            from ..job_data_manager import get_job_data_manager

            job_data_manager = get_job_data_manager()

            # Find the job
            manager = get_slurm_manager()
            job_data = None

            if host:
                job_data = await job_data_manager.get_job_data(job_id, host)
            else:
                # Search all hosts
                for slurm_host in manager.slurm_hosts:
                    job_data = await job_data_manager.get_job_data(
                        job_id, slurm_host.host.hostname
                    )
                    if job_data:
                        host = slurm_host.host.hostname
                        break

            if job_data and job_data.job_info:
                # Force fetch outputs from SSH
                (
                    stdout_content,
                    stderr_content,
                ) = await job_data_manager._fetch_outputs_from_cached_paths(
                    job_data.job_info, force_fetch=True
                )

                # Update cache with fresh content (but don't mark as final for running jobs)
                is_running = job_data.job_info.state in ["R"]
                cache_middleware.cache.update_job_outputs(
                    job_id=job_id,
                    hostname=host,
                    stdout_content=stdout_content,
                    stderr_content=stderr_content,
                    mark_fetched_after_completion=not is_running,  # Only mark as final if job is not running
                )

                return JobOutputResponse(
                    job_id=job_id,
                    hostname=host,
                    stdout=stdout_content if not metadata_only else None,
                    stderr=stderr_content if not metadata_only else None,
                    stdout_metadata=FileMetadata(
                        path=job_data.job_info.stdout_file,
                        size=len(stdout_content) if stdout_content else 0,
                        modified=None,
                        exists=bool(stdout_content),
                    )
                    if job_data.job_info.stdout_file
                    else None,
                    stderr_metadata=FileMetadata(
                        path=job_data.job_info.stderr_file,
                        size=len(stderr_content) if stderr_content else 0,
                        modified=None,
                        exists=bool(stderr_content),
                    )
                    if job_data.job_info.stderr_file
                    else None,
                )

        # Normal cache check flow
        cached_job = (
            cache_middleware.cache.get_cached_job(job_id, host) if host else None
        )

        # If not in cache with specific host, search all hosts
        if not cached_job and not host:
            manager = get_slurm_manager()
            for slurm_host in manager.slurm_hosts:
                cached_job = cache_middleware.cache.get_cached_job(
                    job_id, slurm_host.host.hostname
                )
                if cached_job:
                    host = slurm_host.host.hostname
                    break

        # Check if we should fetch from SSH
        if cached_job and cached_job.job_info:
            is_running = cached_job.job_info.state in ["R"]  # Running jobs
            is_pending = cached_job.job_info.state in ["PD"]  # Pending jobs
            is_completed = cached_job.job_info.state not in ["PD", "R"]

            # Initialize output variables - will be set based on job state
            stdout_content = None
            stderr_content = None

            # Decompress cached outputs if available
            if cached_job.stdout_compressed:
                import gzip

                try:
                    if cached_job.stdout_compression == "gzip":
                        stdout_content = gzip.decompress(
                            cached_job.stdout_compressed
                        ).decode("utf-8")
                    else:
                        stdout_content = cached_job.stdout_compressed.decode("utf-8")
                except Exception as e:
                    logger.error(f"Failed to decompress cached stdout: {e}")

            if cached_job.stderr_compressed:
                import gzip

                try:
                    if cached_job.stderr_compression == "gzip":
                        stderr_content = gzip.decompress(
                            cached_job.stderr_compressed
                        ).decode("utf-8")
                    else:
                        stderr_content = cached_job.stderr_compressed.decode("utf-8")
                except Exception as e:
                    logger.error(f"Failed to decompress cached stderr: {e}")

            # For RUNNING jobs, ALWAYS fetch fresh output
            if is_running:
                logger.info(f"Job {job_id} is running, fetching fresh output")
                from ..job_data_manager import get_job_data_manager

                job_data_manager = get_job_data_manager()
                (
                    stdout_content,
                    stderr_content,
                ) = await job_data_manager._fetch_outputs_from_cached_paths(
                    cached_job.job_info,
                    force_fetch=True,  # Force fetch for running jobs
                )

                # Fresh content is already in stdout_content and stderr_content variables
                # They will be used in the response below

                # Also update the cache for running jobs (but don't mark as fetched after completion)
                cache_middleware.cache.update_job_outputs(
                    job_id=job_id,
                    hostname=host,
                    stdout_content=stdout_content,
                    stderr_content=stderr_content,
                    mark_fetched_after_completion=False,  # Don't mark as final fetch since job is still running
                )

            elif is_completed:
                # Check if outputs were already fetched after completion
                stdout_fetched_after, stderr_fetched_after = (
                    cache_middleware.cache.check_outputs_fetched_after_completion(
                        job_id, host
                    )
                )

                # If job is completed but we haven't fetched outputs after completion, fetch now
                if not stdout_fetched_after or not stderr_fetched_after:
                    logger.info(
                        f"Job {job_id} is completed but outputs not fetched after completion, fetching now"
                    )
                    from ..job_data_manager import get_job_data_manager

                    job_data_manager = get_job_data_manager()
                    (
                        stdout_content,
                        stderr_content,
                    ) = await job_data_manager._fetch_outputs_from_cached_paths(
                        cached_job.job_info
                    )

                    # Fresh content is already in stdout_content and stderr_content variables
                    # They will be used in the response below

            elif is_pending:
                # For PENDING jobs, return empty outputs (they haven't started yet)
                logger.debug(f"Job {job_id} is pending, no outputs available yet")
                return JobOutputResponse(
                    job_id=job_id,
                    hostname=host,
                    stdout=None,
                    stderr=None,
                    stdout_metadata=FileMetadata(
                        path=cached_job.job_info.stdout_file,
                        size=0,
                        modified=None,
                        exists=False,
                    )
                    if cached_job.job_info.stdout_file
                    else None,
                    stderr_metadata=FileMetadata(
                        path=cached_job.job_info.stderr_file,
                        size=0,
                        modified=None,
                        exists=False,
                    )
                    if cached_job.job_info.stderr_file
                    else None,
                )

        # Return outputs (either freshly fetched or cached)
        if cached_job:
            # Always return a response if we have a cached job, even if outputs are empty
            return JobOutputResponse(
                job_id=job_id,
                hostname=host,
                stdout=stdout_content if not metadata_only else None,
                stderr=stderr_content if not metadata_only else None,
                stdout_metadata=FileMetadata(
                    path=cached_job.job_info.stdout_file,
                    size=len(stdout_content) if stdout_content else 0,
                    modified=None,
                    exists=bool(stdout_content),
                )
                if cached_job.job_info.stdout_file
                else None,
                stderr_metadata=FileMetadata(
                    path=cached_job.job_info.stderr_file,
                    size=len(stderr_content) if stderr_content else 0,
                    modified=None,
                    exists=bool(stderr_content),
                )
                if cached_job.job_info.stderr_file
                else None,
            )

        # Fall back to original logic if not in cache
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
        error_msg = str(e)
        logger.error(f"Error in get_job_output for job {job_id} on {host}: {error_msg}")

        # Try cache fallback for output
        cached_output = await _cache_middleware.get_cached_job_output(job_id, host)
        if cached_output:
            # Include the error in the log message so we know why it fell back to cache
            logger.info(
                f"Returning cached output for job {job_id} (fetch failed: {error_msg[:200]})"
            )
            return cached_output

        # Provide more specific error messages
        if "connection" in error_msg.lower() or "ssh" in error_msg.lower():
            detail = f"SSH connection failed to {host}: {error_msg}"
        elif "timeout" in error_msg.lower():
            detail = f"Operation timed out while fetching output: {error_msg}"
        elif "not found" in error_msg.lower() or "no such file" in error_msg.lower():
            detail = f"Output file not found: {error_msg}"
        else:
            detail = f"Failed to read job output: {error_msg}"

        raise HTTPException(status_code=500, detail=detail)


@app.get("/api/jobs/{job_id}/script")
async def get_job_script(
    job_id: str,
    host: Optional[str] = Query(None, description="Specific host to search"),
    authenticated: bool = Depends(verify_api_key),
):
    """Get the batch script content for a specific job."""
    try:
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

        # Try to get from Slurm and cache it
        script_found_in_slurm = False
        for slurm_host in slurm_hosts:
            try:
                conn = manager._get_connection(slurm_host.host)
                script_content = manager.slurm_client.get_job_batch_script(
                    conn, job_id, slurm_host.host.hostname
                )

                if script_content is not None:
                    script_found_in_slurm = True

                    # Check if we have a cached local source dir for this job
                    local_source_dir = None
                    cached_job = _cache_middleware.cache.get_cached_job(
                        job_id, slurm_host.host.hostname
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

        # If we didn't find the script in Slurm, check cache again without host filter
        # This handles cases where the job moved hosts or host wasn't specified correctly
        if not script_found_in_slurm and host:
            cached_script = await _cache_middleware.get_cached_job_script(job_id, None)
            if cached_script:
                logger.info(
                    f"Returning cached script for job {job_id} (found without host filter)"
                )
                return cached_script

        # Script not found anywhere
        logger.warning(f"Script not found for job {job_id} in cache or Slurm")
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
            # Initialize launch manager with thread pool executor
            launch_manager = LaunchManager(manager, executor=executor)

            # Validate Slurm parameters
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
            job = await launch_manager.launch_job(
                script_path=script_path,
                source_dir=source_dir,
                host=request.host,
                slurm_params=slurm_params,
                python_env=request.python_env,
                exclude=request.exclude,
                include=request.include,
                no_gitignore=request.no_gitignore,
                sync_enabled=source_dir is not None,
                abort_on_setup_failure=request.abort_on_setup_failure,
            )

            if job:
                # Cache the script with local source directory
                try:
                    local_dir_str = str(source_dir) if source_dir else None
                    await _cache_middleware.cache_job_script(
                        job.job_id, request.host, request.script_content, local_dir_str
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
        # Include the actual error message for better debugging
        error_message = str(e)

        # Parse and enhance error messages based on common patterns
        if "Failed to submit job" in error_message:
            # Extract the specific Slurm errors if present
            if "Slurm Error:" in error_message:
                # The error already has detailed Slurm information
                raise HTTPException(status_code=500, detail=error_message)
            else:
                # Generic submission failure - add context
                raise HTTPException(
                    status_code=500,
                    detail=f"Job submission failed: {error_message}. Check cluster availability, Slurm configuration, and resource limits.",
                )
        elif "Connection" in error_message or "SSH" in error_message:
            raise HTTPException(
                status_code=503,
                detail=f"Cannot connect to cluster: {error_message}. Check network connectivity and SSH configuration.",
            )
        elif "Permission" in error_message:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: {error_message}. Verify your cluster credentials and account permissions.",
            )
        elif "Invalid partition" in error_message:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid partition specified: {error_message}. Check available partitions on the cluster.",
            )
        elif "Invalid account" in error_message:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid Slurm account: {error_message}. Verify your account is active and has access.",
            )
        elif "not found" in error_message.lower():
            raise HTTPException(
                status_code=404, detail=f"Resource not found: {error_message}"
            )
        elif "Timeout" in error_message:
            raise HTTPException(
                status_code=504,
                detail=f"Operation timed out: {error_message}. The cluster may be overloaded or unresponsive.",
            )
        elif "sbatch" in error_message.lower() and "not found" in error_message.lower():
            raise HTTPException(
                status_code=503,
                detail="Slurm commands not available on the cluster. Verify Slurm is installed and accessible.",
            )
        else:
            # For any other errors, return the full error message with a generic prefix
            raise HTTPException(
                status_code=500, detail=f"Job launch failed: {error_message}"
            )


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    host: Optional[str] = Query(None, description="Specific host"),
    authenticated: bool = Depends(verify_api_key),
):
    """Cancel a running job."""
    try:
        job_id = InputSanitizer.sanitize_job_id(job_id)
        if host:
            host = InputSanitizer.sanitize_hostname(host)

        manager = get_slurm_manager()

        # Get target hosts
        slurm_hosts = manager.slurm_hosts
        if host:
            slurm_hosts = [h for h in slurm_hosts if h.host.hostname == host]

        # Try to cancel on each host - scancel will fail gracefully if job doesn't exist
        for slurm_host in slurm_hosts:
            try:
                success = manager.cancel_job(slurm_host, job_id)
                if success:
                    logger.info(f"Cancelled job {job_id} on {slurm_host.host.hostname}")

                    # Try to stop any watchers for this job (don't fail the whole operation if this fails)
                    try:
                        from ..watchers import get_watcher_engine

                        engine = get_watcher_engine()
                        await engine.stop_watchers_for_job(
                            job_id, slurm_host.host.hostname
                        )
                        logger.info(f"Stopped watchers for job {job_id}")
                    except Exception as e:
                        logger.warning(f"Failed to stop watchers for job {job_id}: {e}")

                    return {"message": "Job cancelled successfully"}
                else:
                    logger.warning(
                        f"Failed to cancel job {job_id} on {slurm_host.host.hostname}: scancel returned false"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to cancel job {job_id} on {slurm_host.host.hostname}: {e}"
                )
                continue

        raise HTTPException(status_code=500, detail="Failed to cancel job on any host")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


@app.get("/api/jobs/{job_id}/watchers")
async def get_job_watchers(
    job_id: str,
    host: Optional[str] = Query(None, description="Filter by hostname"),
    authenticated: bool = Depends(verify_api_key),
):
    """Get watchers for a specific job."""
    try:
        import json

        job_id = InputSanitizer.sanitize_job_id(job_id)
        if host:
            host = InputSanitizer.sanitize_hostname(host)

        cache = get_cache()
        watchers = []

        with cache._get_connection() as conn:
            query = """
                SELECT id, job_id, hostname, name, pattern, interval_seconds,
                       captures_json, condition, actions_json, state,
                       trigger_count, last_check, last_position, created_at,
                       timer_mode_enabled, timer_interval_seconds, timer_mode_active,
                       is_array_template, array_spec, parent_watcher_id,
                       discovered_task_count, expected_task_count
                FROM job_watchers
                WHERE job_id = ?
            """
            params = [job_id]

            if host:
                query += " AND hostname = ?"
                params.append(host)

            cursor = conn.execute(query, params)

            watcher_ids = []
            for row in cursor.fetchall():
                watcher = {
                    "id": row["id"],
                    "job_id": row["job_id"],
                    "hostname": row["hostname"],
                    "name": row["name"] or f"watcher_{row['id']}",
                    "pattern": row["pattern"],
                    "interval_seconds": row["interval_seconds"],
                    "captures": json.loads(row["captures_json"] or "[]"),
                    "condition": row["condition"],
                    "actions": json.loads(row["actions_json"] or "[]"),
                    "state": row["state"],
                    "trigger_count": row["trigger_count"],
                    "last_check": row["last_check"],
                    "last_position": row["last_position"],
                    "created_at": row["created_at"],
                }

                # Add timer fields with safe fallbacks for older databases
                row_dict = dict(row)
                if "timer_mode_enabled" in row_dict:
                    watcher["timer_mode_enabled"] = bool(row_dict["timer_mode_enabled"])
                else:
                    watcher["timer_mode_enabled"] = False

                if "timer_interval_seconds" in row_dict:
                    watcher["timer_interval_seconds"] = row_dict[
                        "timer_interval_seconds"
                    ]
                else:
                    watcher["timer_interval_seconds"] = 30

                if "timer_mode_active" in row_dict:
                    watcher["timer_mode_active"] = bool(row_dict["timer_mode_active"])
                else:
                    watcher["timer_mode_active"] = False

                # Add array template fields with safe fallbacks
                if "is_array_template" in row_dict:
                    watcher["is_array_template"] = bool(row_dict["is_array_template"])
                else:
                    watcher["is_array_template"] = False

                if "array_spec" in row_dict:
                    watcher["array_spec"] = row_dict["array_spec"]
                else:
                    watcher["array_spec"] = None

                if "parent_watcher_id" in row_dict:
                    watcher["parent_watcher_id"] = row_dict["parent_watcher_id"]
                else:
                    watcher["parent_watcher_id"] = None

                if "discovered_task_count" in row_dict:
                    watcher["discovered_task_count"] = row_dict["discovered_task_count"]
                else:
                    watcher["discovered_task_count"] = 0

                if "expected_task_count" in row_dict:
                    watcher["expected_task_count"] = row_dict["expected_task_count"]
                else:
                    watcher["expected_task_count"] = None

                watchers.append(watcher)
                watcher_ids.append(row["id"])

            # Fetch captured variables for all watchers
            if watcher_ids:
                placeholders = ",".join("?" * len(watcher_ids))
                var_cursor = conn.execute(
                    f"""
                    SELECT watcher_id, variable_name, variable_value
                    FROM watcher_variables
                    WHERE watcher_id IN ({placeholders})
                    """,
                    watcher_ids,
                )

                # Group variables by watcher_id
                variables_by_watcher = {}
                for var_row in var_cursor.fetchall():
                    watcher_id = var_row["watcher_id"]
                    if watcher_id not in variables_by_watcher:
                        variables_by_watcher[watcher_id] = {}
                    variables_by_watcher[watcher_id][var_row["variable_name"]] = (
                        var_row["variable_value"]
                    )

                # Add variables to each watcher
                for watcher in watchers:
                    watcher["variables"] = variables_by_watcher.get(watcher["id"], {})

        return {"job_id": job_id, "watchers": watchers, "count": len(watchers)}

    except Exception as e:
        logger.error(f"Error getting watchers for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get watchers")


@app.get("/api/watchers")
async def get_all_watchers(
    state: Optional[str] = Query(
        None, description="Filter by state (active, paused, completed, failed)"
    ),
    limit: int = Query(100, description="Maximum number of watchers to return"),
    authenticated: bool = Depends(verify_api_key),
):
    """Get all watchers across all jobs."""
    try:
        cache = get_cache()

        with cache._get_connection() as conn:
            query = """
                SELECT w.*, j.hostname
                FROM job_watchers w
                LEFT JOIN cached_jobs j ON w.job_id = j.job_id
                WHERE 1=1
            """
            params = []

            if state:
                query += " AND w.state = ?"
                params.append(state)

            query += " ORDER BY w.created_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            columns = [desc[0] for desc in cursor.description]

            watchers = []
            for row in cursor.fetchall():
                watcher_dict = dict(zip(columns, row))

                # Parse JSON fields
                if watcher_dict.get("actions_json"):
                    watcher_dict["actions"] = json.loads(watcher_dict["actions_json"])
                    del watcher_dict["actions_json"]
                else:
                    watcher_dict["actions"] = []

                if watcher_dict.get("captures_json"):
                    watcher_dict["captures"] = json.loads(watcher_dict["captures_json"])
                    del watcher_dict["captures_json"]
                else:
                    watcher_dict["captures"] = []

                # Set a default name if it's None
                if watcher_dict.get("name") is None:
                    watcher_dict["name"] = f"Watcher {watcher_dict['id']}"

                # Add timer fields if they exist
                if "timer_mode_enabled" in watcher_dict:
                    watcher_dict["timer_mode_enabled"] = bool(
                        watcher_dict["timer_mode_enabled"]
                    )
                else:
                    watcher_dict["timer_mode_enabled"] = False

                if "timer_mode_active" in watcher_dict:
                    watcher_dict["timer_mode_active"] = bool(
                        watcher_dict["timer_mode_active"]
                    )
                else:
                    watcher_dict["timer_mode_active"] = False

                watchers.append(watcher_dict)

            return {"watchers": watchers}

    except Exception as e:
        logger.error(f"Error getting all watchers: {e}")
        raise HTTPException(status_code=500, detail="Failed to get watchers")


@app.get("/api/watchers/events")
async def get_watcher_events(
    job_id: Optional[str] = Query(None, description="Filter by job ID"),
    watcher_id: Optional[int] = Query(None, description="Filter by watcher ID"),
    limit: int = Query(50, description="Maximum number of events to return"),
    authenticated: bool = Depends(verify_api_key),
):
    """Get recent watcher events."""
    try:
        import json

        if job_id:
            job_id = InputSanitizer.sanitize_job_id(job_id)

        cache = get_cache()
        events = []

        with cache._get_connection() as conn:
            query = """
                SELECT e.*, w.name as watcher_name, w.pattern
                FROM watcher_events e
                LEFT JOIN job_watchers w ON e.watcher_id = w.id
                WHERE 1=1
            """
            params = []

            if job_id:
                query += " AND e.job_id = ?"
                params.append(job_id)

            if watcher_id:
                query += " AND e.watcher_id = ?"
                params.append(watcher_id)

            query += f" ORDER BY e.timestamp DESC LIMIT {min(limit, 500)}"

            cursor = conn.execute(query, params)

            for row in cursor.fetchall():
                event = {
                    "id": row["id"],
                    "watcher_id": row["watcher_id"],
                    "watcher_name": row["watcher_name"]
                    or f"watcher_{row['watcher_id']}",
                    "job_id": row["job_id"],
                    "hostname": row["hostname"],
                    "timestamp": row["timestamp"],
                    "matched_text": row["matched_text"],
                    "captured_vars": json.loads(row["captured_vars_json"] or "{}"),
                    "action_type": row["action_type"],
                    "action_result": row["action_result"],
                    "success": bool(row["success"]),
                }
                events.append(event)

        return {"events": events, "count": len(events)}

    except Exception as e:
        logger.error(f"Error getting watcher events: {e}")
        raise HTTPException(status_code=500, detail="Failed to get watcher events")


@app.get("/api/watchers/stats")
async def get_watcher_stats(
    authenticated: bool = Depends(verify_api_key),
):
    """Get watcher statistics."""
    try:
        cache = get_cache()

        with cache._get_connection() as conn:
            # Total watchers
            cursor = conn.execute("SELECT COUNT(*) as count FROM job_watchers")
            total_watchers = cursor.fetchone()["count"]

            # Watchers by state
            cursor = conn.execute("""
                SELECT state, COUNT(*) as count 
                FROM job_watchers 
                GROUP BY state
            """)
            watchers_by_state = {
                row["state"]: row["count"] for row in cursor.fetchall()
            }

            # Total events
            cursor = conn.execute("SELECT COUNT(*) as count FROM watcher_events")
            total_events = cursor.fetchone()["count"]

            # Events by action type
            cursor = conn.execute("""
                SELECT action_type, COUNT(*) as count, 
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count
                FROM watcher_events 
                GROUP BY action_type
            """)
            events_by_action = {}
            for row in cursor.fetchall():
                events_by_action[row["action_type"]] = {
                    "total": row["count"],
                    "success": row["success_count"],
                    "failed": row["count"] - row["success_count"],
                }

            # Recent activity
            one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count 
                FROM watcher_events 
                WHERE timestamp > ?
            """,
                (one_hour_ago,),
            )
            events_last_hour = cursor.fetchone()["count"]

            # Most triggered watchers
            cursor = conn.execute("""
                SELECT w.id, w.job_id, w.name, COUNT(e.id) as event_count
                FROM job_watchers w
                LEFT JOIN watcher_events e ON w.id = e.watcher_id
                GROUP BY w.id
                HAVING event_count > 0
                ORDER BY event_count DESC
                LIMIT 10
            """)
            top_watchers = []
            for row in cursor.fetchall():
                top_watchers.append(
                    {
                        "watcher_id": row["id"],
                        "job_id": row["job_id"],
                        "name": row["name"] or f"watcher_{row['id']}",
                        "event_count": row["event_count"],
                    }
                )

        return {
            "total_watchers": total_watchers,
            "watchers_by_state": watchers_by_state,
            "total_events": total_events,
            "events_by_action": events_by_action,
            "events_last_hour": events_last_hour,
            "top_watchers": top_watchers,
        }

    except Exception as e:
        logger.error(f"Error getting watcher stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get watcher statistics")


@app.post("/api/notifications/devices")
async def register_notification_device(
    payload: NotificationDeviceRegistration,
    api_key: str = Depends(get_api_key),
):
    """Register or update a device token for push notifications."""
    try:
        token = _normalize_device_token(payload.token)
        platform = payload.platform.lower()
        if platform not in {"ios"}:
            raise HTTPException(status_code=400, detail="Unsupported platform")

        environment = _normalize_environment(payload.environment)
        api_key_hash = (
            hashlib.sha256(api_key.encode()).hexdigest() if api_key else "public"
        )

        cache = get_cache()
        cache.upsert_notification_device(
            api_key_hash=api_key_hash,
            device_token=token,
            platform=platform,
            bundle_id=payload.bundle_id
            or config.notification_settings.apns_bundle_id
            or None,
            environment=environment,
            device_id=payload.device_id,
            enabled=payload.enabled,
        )

        return {"success": True, "token": token}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to register notification device: {e}")
        raise HTTPException(status_code=500, detail="Failed to register device")


@app.delete("/api/notifications/devices/{token}")
async def unregister_notification_device(
    token: str,
    api_key: str = Depends(get_api_key),
):
    """Unregister a device token."""
    try:
        normalized_token = _normalize_device_token(token)
        api_key_hash = (
            hashlib.sha256(api_key.encode()).hexdigest() if api_key else "public"
        )
        cache = get_cache()
        deleted = cache.remove_notification_device(
            api_key_hash=api_key_hash, device_token=normalized_token
        )
        return {"success": True, "deleted": deleted}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unregister device: {e}")
        raise HTTPException(status_code=500, detail="Failed to unregister device")


@app.post("/api/notifications/test")
async def test_notification(
    payload: NotificationTestRequest,
    authenticated: bool = Depends(verify_api_key),
):
    """Send a test notification to registered devices or a specific token."""
    service = get_notification_service()
    if not service.enabled:
        raise HTTPException(status_code=400, detail="Notifications not configured")

    token = _normalize_device_token(payload.token) if payload.token else None
    sent = await service.send_test_notification(
        title=payload.title, body=payload.body, token=token
    )
    return {"success": True, "sent": sent}


@app.get("/api/notifications/preferences")
async def get_notification_preferences(
    api_key: str = Depends(get_api_key),
):
    """Get notification preferences for the current API key."""
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest() if api_key else "public"
    cache = get_cache()
    preferences = cache.get_notification_preferences(api_key_hash=api_key_hash)
    return NotificationPreferences(**preferences)


@app.patch("/api/notifications/preferences")
async def update_notification_preferences(
    payload: NotificationPreferencesPatch,
    api_key: str = Depends(get_api_key),
):
    """Update notification preferences for the current API key."""
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest() if api_key else "public"
    cache = get_cache()
    current = cache.get_notification_preferences(api_key_hash=api_key_hash)
    updates = payload.model_dump(exclude_unset=True)
    updates = _sanitize_notification_preferences(updates)

    merged = {**current, **updates}
    cache.upsert_notification_preferences(api_key_hash=api_key_hash, preferences=merged)
    return NotificationPreferences(**merged)


@app.get("/api/notifications/webpush/vapid")
async def get_webpush_vapid(authenticated: bool = Depends(verify_api_key)):
    """Return Web Push VAPID public key for browser registration."""
    settings = config.notification_settings
    return {
        "enabled": settings.webpush_enabled,
        "public_key": settings.webpush_vapid_public_key,
    }


@app.post("/api/notifications/webpush/subscribe")
async def register_webpush_subscription(
    payload: WebPushSubscriptionRegistration,
    api_key: str = Depends(get_api_key),
):
    """Register a Web Push subscription."""
    endpoint = InputSanitizer.sanitize_text(payload.endpoint, max_length=2048)
    if not endpoint.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid endpoint")

    p256dh = InputSanitizer.sanitize_text(payload.keys.p256dh, max_length=512)
    auth = InputSanitizer.sanitize_text(payload.keys.auth, max_length=512)

    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest() if api_key else "public"
    cache = get_cache()
    cache.upsert_webpush_subscription(
        api_key_hash=api_key_hash,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
        user_agent=payload.user_agent,
        enabled=payload.enabled,
    )
    return {"success": True, "endpoint": endpoint}


@app.post("/api/notifications/webpush/unsubscribe")
async def unregister_webpush_subscription(
    payload: WebPushUnsubscribeRequest,
    api_key: str = Depends(get_api_key),
):
    """Unregister a Web Push subscription."""
    endpoint = InputSanitizer.sanitize_text(payload.endpoint, max_length=2048)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest() if api_key else "public"
    cache = get_cache()
    deleted = cache.remove_webpush_subscription(
        api_key_hash=api_key_hash, endpoint=endpoint
    )
    return {"success": True, "deleted": deleted}


@app.post("/api/watchers/cleanup")
async def cleanup_orphaned_watchers(
    dry_run: bool = Query(default=False, description="Only list what would be cleaned"),
    authenticated: bool = Depends(verify_api_key),
):
    """Clean up watchers for completed or non-existent jobs."""
    try:
        from ..watchers import get_watcher_engine

        engine = get_watcher_engine()

        if dry_run:
            # Just list active watchers that might be orphaned
            cache = get_cache()
            with cache._get_connection() as conn:
                cursor = conn.execute(
                    """SELECT w.id, w.job_id, w.hostname, w.state, w.name
                       FROM job_watchers w
                       WHERE w.state = 'active'"""
                )
                active_watchers = [
                    {
                        "id": row["id"],
                        "job_id": row["job_id"],
                        "hostname": row["hostname"],
                        "state": row["state"],
                        "name": row["name"],
                    }
                    for row in cursor.fetchall()
                ]

            return {
                "dry_run": True,
                "active_watchers": active_watchers,
                "count": len(active_watchers),
            }
        else:
            await engine.cleanup_orphaned_watchers()
            return {"message": "Cleanup completed", "dry_run": False}

    except Exception as e:
        logger.error(f"Error cleaning up watchers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup watchers: {e}")


@app.post("/api/watchers/{watcher_id}/pause")
async def pause_watcher(
    watcher_id: int,
    authenticated: bool = Depends(verify_api_key),
):
    """Pause a watcher."""
    try:
        cache = get_cache()

        with cache._get_connection() as conn:
            # First check if watcher exists and is active
            cursor = conn.execute(
                "SELECT state FROM job_watchers WHERE id = ?", (watcher_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Watcher not found")

            if row["state"] != "active":
                return {
                    "message": f"Watcher {watcher_id} is not active (current state: {row['state']})"
                }

            # Update state to paused
            conn.execute(
                "UPDATE job_watchers SET state = 'paused' WHERE id = ?", (watcher_id,)
            )
            conn.commit()

        # Try to cancel the async task if engine is available
        try:
            from ..watchers import get_watcher_engine

            engine = get_watcher_engine()

            if hasattr(engine, "active_tasks") and watcher_id in engine.active_tasks:
                try:
                    engine.active_tasks[watcher_id].cancel()
                    del engine.active_tasks[watcher_id]
                except Exception as task_error:
                    logger.debug(
                        f"Could not cancel task for watcher {watcher_id}: {task_error}"
                    )
        except Exception as engine_error:
            logger.debug(f"Watcher engine not available: {engine_error}")

        return {"message": f"Watcher {watcher_id} paused successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing watcher {watcher_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to pause watcher")


@app.post("/api/watchers/{watcher_id}/trigger")
async def trigger_watcher_manually(
    watcher_id: int,
    test_text: str = Body(None, description="Optional test text to match against"),
    authenticated: bool = Depends(verify_api_key),
):
    """Manually trigger a watcher for testing purposes."""
    try:
        from ..models.watcher import WatcherState
        from ..watchers.engine import get_watcher_engine

        engine = get_watcher_engine()
        cache = get_cache()

        # Get watcher details
        with cache._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT w.*
                FROM job_watchers w
                WHERE w.id = ?
                """,
                (watcher_id,),
            )
            watcher_row = cursor.fetchone()

            if not watcher_row:
                raise HTTPException(status_code=404, detail="Watcher not found")

        # Get watcher instance from database
        watcher = engine._get_watcher(watcher_id)
        if not watcher:
            raise HTTPException(status_code=404, detail="Watcher not found in database")

        # Check if watcher is active or static
        if watcher.state not in [WatcherState.ACTIVE, WatcherState.STATIC]:
            raise HTTPException(
                status_code=400,
                detail=f"Watcher is in {watcher.state.value} state. It must be ACTIVE or STATIC to trigger manually.",
            )

        # Check if watcher is in timer mode
        if watcher.timer_mode_active:
            # Execute timer mode actions directly
            logger.info(
                f"Watcher {watcher_id} is in timer mode, executing timer actions"
            )
            success, message = await engine.execute_timer_actions(watcher_id)

            return {
                "success": success,
                "message": message,
                "matches": success,  # For UI compatibility
                "timer_mode": True,
            }

        # Regular pattern matching mode
        # If test_text is provided, use it; otherwise fetch latest output from cache or Slurm
        if test_text:
            content = test_text
            logger.info(f"Manually triggering watcher {watcher_id} with test text")
        else:
            # Try to get output from cache first
            cache = get_cache()
            cached_job = cache.get_cached_job(
                watcher_row["job_id"], watcher_row["hostname"]
            )

            stdout_content = ""
            stderr_content = ""

            if cached_job and (
                cached_job.stdout_compressed or cached_job.stderr_compressed
            ):
                import gzip

                # Decompress cached outputs
                if cached_job.stdout_compressed:
                    try:
                        if cached_job.stdout_compression == "gzip":
                            stdout_content = gzip.decompress(
                                cached_job.stdout_compressed
                            ).decode("utf-8")
                        else:
                            stdout_content = cached_job.stdout_compressed.decode(
                                "utf-8"
                            )
                    except Exception as e:
                        logger.warning(f"Failed to decompress cached stdout: {e}")

                if cached_job.stderr_compressed:
                    try:
                        if cached_job.stderr_compression == "gzip":
                            stderr_content = gzip.decompress(
                                cached_job.stderr_compressed
                            ).decode("utf-8")
                        else:
                            stderr_content = cached_job.stderr_compressed.decode(
                                "utf-8"
                            )
                    except Exception as e:
                        logger.warning(f"Failed to decompress cached stderr: {e}")

                logger.info(
                    f"Using cached output for watcher {watcher_id} - stdout: {len(stdout_content)} chars, stderr: {len(stderr_content)} chars"
                )

            # If cache is empty, try to fetch from Slurm directly
            if not stdout_content and not stderr_content:
                try:
                    logger.info(
                        f"Cache empty, fetching output from Slurm for job {watcher_row['job_id']}"
                    )
                    manager = get_slurm_manager()
                    job_info = manager.get_job_info(
                        watcher_row["hostname"], watcher_row["job_id"]
                    )

                    if job_info:
                        # Get connection to the host
                        try:
                            slurm_host = manager.get_host_by_name(
                                watcher_row["hostname"]
                            )
                            conn = manager._get_connection(slurm_host.host)
                        except Exception as e:
                            logger.warning(
                                f"Failed to get connection for {watcher_row['hostname']}: {e}"
                            )
                            conn = None

                        if conn:
                            # Try to get output from Slurm paths
                            if job_info.stdout_file:
                                try:
                                    result = conn.run(
                                        f"cat '{job_info.stdout_file}'",
                                        warn=True,
                                        hide=True,
                                    )
                                    if result.ok:
                                        stdout_content = result.stdout
                                        logger.info(
                                            f"Fetched stdout from Slurm: {len(stdout_content)} chars"
                                        )
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to fetch stdout from Slurm: {e}"
                                    )

                            if job_info.stderr_file:
                                try:
                                    result = conn.run(
                                        f"cat '{job_info.stderr_file}'",
                                        warn=True,
                                        hide=True,
                                    )
                                    if result.ok:
                                        stderr_content = result.stdout
                                        logger.info(
                                            f"Fetched stderr from Slurm: {len(stderr_content)} chars"
                                        )
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to fetch stderr from Slurm: {e}"
                                    )
                except Exception as e:
                    logger.warning(f"Failed to fetch output from Slurm: {e}")

            # Combine outputs based on watcher output_type
            output_type = (
                watcher.definition.output_type
                if hasattr(watcher.definition, "output_type")
                else "stdout"
            )

            if output_type == "stdout":
                content = stdout_content
            elif output_type == "stderr":
                content = stderr_content
            else:  # both
                content = stdout_content + "\n" + stderr_content

            if content:
                lines = content.split("\n")
                logger.info(
                    f"Triggering watcher {watcher_id} with job output ({len(lines)} lines, {len(content)} chars)"
                )
            else:
                # No output available at all
                content = ""
                logger.warning(
                    f"No output found for job {watcher_row['job_id']} on {watcher_row['hostname']} (cache and Slurm both empty)"
                )

        # Run pattern matching and actions
        if not content:
            return {
                "success": False,
                "message": f"No output available for job {watcher_row['job_id']}. The job output may not be cached yet or the output files may not be accessible.",
                "matches": False,
                "timer_mode": False,
            }

        matches_found = engine._check_patterns(watcher, content)

        if matches_found:
            # Count how many matches
            pattern = watcher.definition.pattern
            if pattern in engine._pattern_cache:
                regex = engine._pattern_cache[pattern]
                match_count = len(list(regex.finditer(content)))
            else:
                match_count = 1

            return {
                "success": True,
                "message": f"✓ Found {match_count} match(es) and executed actions",
                "matches": True,
                "match_count": match_count,
                "timer_mode": False,
            }
        else:
            lines = content.split("\n")
            return {
                "success": True,
                "message": f"✗ No matches found (searched {len(lines)} lines, {len(content)} chars)",
                "matches": False,
                "timer_mode": False,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to manually trigger watcher {watcher_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to trigger watcher: {str(e)}"
        )


@app.post("/api/watchers/{watcher_id}/resume")
async def resume_watcher(
    watcher_id: int,
    authenticated: bool = Depends(verify_api_key),
):
    """Resume a paused watcher."""
    try:
        cache = get_cache()

        # Get watcher details
        with cache._get_connection() as conn:
            cursor = conn.execute(
                "SELECT job_id, hostname, state FROM job_watchers WHERE id = ?",
                (watcher_id,),
            )
            row = cursor.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Watcher not found")

            if row["state"] != "paused":
                return {
                    "message": f"Watcher {watcher_id} is not paused (current state: {row['state']})"
                }

            job_id = row["job_id"]
            hostname = row["hostname"]

            # Update state
            conn.execute(
                "UPDATE job_watchers SET state = 'active' WHERE id = ?", (watcher_id,)
            )
            conn.commit()

        # Try to restart the monitoring task if engine is available
        try:
            from ..watchers import get_watcher_engine

            engine = get_watcher_engine()

            # Only try to create task if the engine has an event loop
            if hasattr(engine, "active_tasks"):
                try:
                    task = create_task(
                        engine._monitor_watcher(watcher_id, job_id, hostname)
                    )
                    engine.active_tasks[watcher_id] = task
                except Exception as task_error:
                    logger.debug(
                        f"Could not restart monitoring task for watcher {watcher_id}: {task_error}"
                    )
        except Exception as engine_error:
            logger.debug(f"Watcher engine not available: {engine_error}")

        return {"message": f"Watcher {watcher_id} resumed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming watcher {watcher_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to resume watcher")


@app.post("/api/watchers/{watcher_id}/discover-array-tasks")
async def discover_array_tasks(
    watcher_id: int,
    authenticated: bool = Depends(verify_api_key),
):
    """
    Manually trigger array task discovery for a template watcher.

    This endpoint discovers array tasks (e.g., job_12345_0, job_12345_1)
    for array job watchers and spawns child watchers for each discovered task.
    """
    try:
        from ..watchers import get_watcher_engine

        engine = get_watcher_engine()

        # Get watcher details
        watcher = engine._get_watcher(watcher_id)
        if not watcher:
            raise HTTPException(status_code=404, detail="Watcher not found")

        # Check if this is an array template watcher
        if not watcher.definition.is_array_template:
            return {
                "success": False,
                "message": "This watcher is not an array template watcher",
                "is_array_template": False,
            }

        # Discover and spawn array tasks
        new_tasks_count = await engine.discover_and_spawn_array_tasks(watcher_id)

        # Get updated counts
        updated_watcher = engine._get_watcher(watcher_id)

        return {
            "success": True,
            "message": f"Discovered {new_tasks_count} new array task(s)",
            "new_tasks_discovered": new_tasks_count,
            "total_discovered": updated_watcher.discovered_task_count
            if updated_watcher
            else 0,
            "expected_tasks": updated_watcher.expected_task_count
            if updated_watcher
            else None,
            "is_array_template": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error discovering array tasks for watcher {watcher_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to discover array tasks: {str(e)}"
        )


@app.post("/api/watchers")
async def create_watcher(
    watcher_config: Dict[str, Any] = Body(...),
    authenticated: bool = Depends(verify_api_key),
):
    """Create a new watcher."""
    try:
        import json
        from datetime import datetime

        cache = get_cache()

        # Validate required fields
        required_fields = ["job_id", "hostname", "name", "pattern"]
        for field in required_fields:
            if field not in watcher_config:
                raise HTTPException(
                    status_code=400, detail=f"Missing required field: {field}"
                )

        with cache._get_connection() as conn:
            # Prepare watcher data
            name = watcher_config["name"]
            pattern = watcher_config["pattern"]
            job_id = watcher_config["job_id"]
            hostname = watcher_config["hostname"]
            interval_seconds = watcher_config.get("interval_seconds", 30)
            # Handle both 'captures' and 'capture_groups' field names for compatibility
            captures_list = watcher_config.get(
                "captures", watcher_config.get("capture_groups", [])
            )
            captures_json = json.dumps(captures_list)
            condition = watcher_config.get("condition")
            timer_mode_enabled = watcher_config.get("timer_mode_enabled", False)

            # Determine state: check if job is completed/canceled
            # If so, create as STATIC watcher (runs on manual trigger only)
            state = watcher_config.get("state", "active")

            # Check job state to auto-determine if this should be a static watcher
            try:
                manager = get_slurm_manager()
                job_info = manager.get_job_info(hostname, job_id)

                logger.info(
                    f"Checking job {job_id} state for watcher creation - job_info: {job_info}, state: {job_info.state if job_info else 'None'}"
                )

                if job_info:
                    # If job is in a terminal/finished state, create as static watcher
                    if job_info.state in [
                        JobState.COMPLETED,
                        JobState.FAILED,
                        JobState.CANCELLED,
                        JobState.TIMEOUT,
                        JobState.UNKNOWN,
                    ]:
                        state = "static"
                        logger.info(
                            f"Creating STATIC watcher for finished job {job_id} (state: {job_info.state.value})"
                        )
                    else:
                        logger.info(
                            f"Creating ACTIVE watcher for running job {job_id} (state: {job_info.state.value})"
                        )
                else:
                    # Job not found - likely completed and purged from queue
                    # Create as static watcher since we can still access cached output
                    state = "static"
                    logger.info(
                        f"Job {job_id} not found in queue - creating STATIC watcher (job likely completed)"
                    )
            except Exception as e:
                # If we can't get job info, assume static for safety
                logger.warning(
                    f"Could not determine job state for {job_id}: {e} - defaulting to STATIC"
                )
                state = "static"
            # Use the same interval for timer mode by default unless explicitly specified
            timer_interval_seconds = watcher_config.get(
                "timer_interval_seconds", interval_seconds
            )

            # Format actions for storage
            actions = watcher_config.get("actions", [])
            formatted_actions = []
            for action in actions:
                formatted_action = {
                    "type": action["type"],
                }
                if action.get("condition"):
                    formatted_action["condition"] = action["condition"]
                # Accept both 'params' and 'config' for backward compatibility
                if action.get("params"):
                    formatted_action["params"] = action["params"]
                elif action.get("config"):
                    formatted_action["params"] = action["config"]
                formatted_actions.append(formatted_action)
            actions_json = json.dumps(formatted_actions)

            # Insert the watcher
            cursor = conn.execute(
                """
                INSERT INTO job_watchers (
                    job_id, hostname, name, pattern, interval_seconds,
                    captures_json, condition, actions_json, state,
                    last_check, last_position, trigger_count, created_at,
                    timer_mode_enabled, timer_interval_seconds, timer_mode_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    hostname,
                    name,
                    pattern,
                    interval_seconds,
                    captures_json,
                    condition,
                    actions_json,
                    state,
                    None,
                    0,
                    0,
                    datetime.now().isoformat(),
                    1 if timer_mode_enabled else 0,
                    timer_interval_seconds,
                    0,  # timer_mode_active starts as 0
                ),
            )
            watcher_id = cursor.lastrowid
            conn.commit()

            # Start monitoring if active (but not for static watchers)
            if state == "active":
                try:
                    from ..watchers import get_watcher_engine

                    engine = get_watcher_engine()

                    if hasattr(engine, "active_tasks"):
                        task = create_task(
                            engine._monitor_watcher(watcher_id, job_id, hostname)
                        )
                        engine.active_tasks[watcher_id] = task
                except Exception as engine_error:
                    logger.debug(f"Could not start watcher monitoring: {engine_error}")
            elif state == "static":
                logger.info(
                    f"Created static watcher {watcher_id} - will only run on manual trigger"
                )

            # Return the created watcher
            cursor = conn.execute(
                "SELECT * FROM job_watchers WHERE id = ?", (watcher_id,)
            )
            created_row = cursor.fetchone()

            # Convert Row to dict for easier access
            row_dict = dict(created_row)

            response = {
                "id": row_dict["id"],
                "job_id": row_dict["job_id"],
                "hostname": row_dict["hostname"],
                "name": row_dict["name"],
                "pattern": row_dict["pattern"],
                "interval_seconds": row_dict["interval_seconds"],
                "state": row_dict["state"],
                "last_check": row_dict["last_check"],
                "last_position": row_dict["last_position"],
                "trigger_count": row_dict["trigger_count"],
                "created_at": row_dict["created_at"],
                "timer_mode_enabled": bool(row_dict.get("timer_mode_enabled", 0)),
                "timer_mode_active": bool(row_dict.get("timer_mode_active", 0)),
                "timer_interval_seconds": row_dict.get("timer_interval_seconds", 30),
            }

            # Parse JSON fields
            if row_dict.get("captures_json"):
                response["captures"] = json.loads(row_dict["captures_json"])

            if row_dict.get("condition"):
                response["condition"] = row_dict["condition"]

            if row_dict.get("actions_json"):
                actions = json.loads(row_dict["actions_json"])
                # Convert from internal format to API format
                formatted_actions = []
                for action in actions:
                    formatted_action = {
                        "type": action["type"],
                    }
                    if action.get("condition"):
                        formatted_action["condition"] = action["condition"]
                    if action.get("params"):
                        formatted_action["config"] = action["params"]
                    formatted_actions.append(formatted_action)
                response["actions"] = formatted_actions

            return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating watcher: {e}")
        logger.error(f"Watcher config received: {json.dumps(watcher_config)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create watcher: {str(e)}"
        )


@app.put("/api/watchers/{watcher_id}")
async def update_watcher(
    watcher_id: int,
    watcher_update: Dict[str, Any] = Body(...),
    authenticated: bool = Depends(verify_api_key),
):
    """Update a watcher configuration."""
    try:
        import json

        cache = get_cache()

        with cache._get_connection() as conn:
            # First check if watcher exists
            cursor = conn.execute(
                "SELECT * FROM job_watchers WHERE id = ?", (watcher_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Watcher not found")

            # Convert Row to dict for easier access
            row_dict = dict(row)

            # Prepare update fields
            update_fields = []
            update_values = []

            # Handle each field that can be updated
            if "name" in watcher_update:
                update_fields.append("name = ?")
                update_values.append(watcher_update["name"])

            if "pattern" in watcher_update:
                update_fields.append("pattern = ?")
                update_values.append(watcher_update["pattern"])

            if "interval_seconds" in watcher_update:
                update_fields.append("interval_seconds = ?")
                update_values.append(watcher_update["interval_seconds"])

            if "capture_groups" in watcher_update:
                update_fields.append("captures_json = ?")
                update_values.append(json.dumps(watcher_update["capture_groups"]))

            if "condition" in watcher_update:
                update_fields.append("condition = ?")
                update_values.append(watcher_update["condition"])

            if "actions" in watcher_update:
                # Format actions for storage
                formatted_actions = []
                for action in watcher_update["actions"]:
                    formatted_action = {
                        "type": action["type"],
                    }
                    if action.get("condition"):
                        formatted_action["condition"] = action["condition"]
                    # Accept both 'params' and 'config' for backward compatibility
                    if action.get("params"):
                        formatted_action["params"] = action["params"]
                    elif action.get("config"):
                        formatted_action["params"] = action["config"]
                    formatted_actions.append(formatted_action)
                update_fields.append("actions_json = ?")
                update_values.append(json.dumps(formatted_actions))

            if "timer_mode_enabled" in watcher_update:
                # Update timer_mode_enabled field
                update_fields.append("timer_mode_enabled = ?")
                update_values.append(1 if watcher_update["timer_mode_enabled"] else 0)

            if "timer_interval_seconds" in watcher_update:
                update_fields.append("timer_interval_seconds = ?")
                update_values.append(watcher_update["timer_interval_seconds"])

            # Perform the update if there are fields to update
            if update_fields:
                update_values.append(watcher_id)  # Add watcher_id for WHERE clause
                query = (
                    f"UPDATE job_watchers SET {', '.join(update_fields)} WHERE id = ?"
                )
                conn.execute(query, update_values)
                conn.commit()

            # Fetch updated watcher
            cursor = conn.execute(
                "SELECT * FROM job_watchers WHERE id = ?", (watcher_id,)
            )
            updated_row = cursor.fetchone()

            # Convert Row to dict for consistent access
            updated_row_dict = dict(updated_row)

            # Format response
            response = {
                "id": updated_row_dict["id"],
                "job_id": updated_row_dict["job_id"],
                "hostname": updated_row_dict["hostname"],
                "name": updated_row_dict["name"],
                "pattern": updated_row_dict["pattern"],
                "interval_seconds": updated_row_dict["interval_seconds"],
                "state": updated_row_dict["state"],
                "last_check": updated_row_dict["last_check"],
                "last_position": updated_row_dict["last_position"],
                "trigger_count": updated_row_dict["trigger_count"],
            }

            # Handle optional fields that might not exist in older database schemas
            # Now we can use .get() since we converted to dict
            response["timer_mode_enabled"] = bool(
                updated_row_dict.get("timer_mode_enabled", 0)
            )
            response["timer_mode_active"] = bool(
                updated_row_dict.get("timer_mode_active", 0)
            )
            response["timer_interval_seconds"] = updated_row_dict.get(
                "timer_interval_seconds", 30
            )

            # Parse JSON fields
            if updated_row_dict.get("captures_json"):
                response["captures"] = json.loads(updated_row_dict["captures_json"])

            if updated_row_dict.get("condition"):
                response["condition"] = updated_row_dict["condition"]

            if updated_row_dict.get("actions_json"):
                actions = json.loads(updated_row_dict["actions_json"])
                # Convert from internal format to API format
                formatted_actions = []
                for action in actions:
                    formatted_action = {
                        "type": action["type"],
                    }
                    if action.get("condition"):
                        formatted_action["condition"] = action["condition"]
                    if action.get("params"):
                        formatted_action["config"] = action["params"]
                    formatted_actions.append(formatted_action)
                response["actions"] = formatted_actions

            # If the watcher state was changed, update the monitoring task
            if row_dict["state"] != updated_row_dict["state"]:
                try:
                    from ..watchers import get_watcher_engine

                    engine = get_watcher_engine()

                    # Handle state changes
                    if (
                        updated_row_dict["state"] == "active"
                        and row_dict["state"] == "paused"
                    ):
                        # Restart monitoring
                        if hasattr(engine, "active_tasks"):
                            task = create_task(
                                engine._monitor_watcher(
                                    watcher_id,
                                    updated_row_dict["job_id"],
                                    updated_row_dict["hostname"],
                                )
                            )
                            engine.active_tasks[watcher_id] = task
                    elif (
                        updated_row_dict["state"] == "paused"
                        and row_dict["state"] == "active"
                    ):
                        # Stop monitoring
                        if (
                            hasattr(engine, "active_tasks")
                            and watcher_id in engine.active_tasks
                        ):
                            engine.active_tasks[watcher_id].cancel()
                            del engine.active_tasks[watcher_id]
                except Exception as engine_error:
                    logger.debug(f"Could not update watcher engine: {engine_error}")

            return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating watcher {watcher_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update watcher")


@app.delete("/api/watchers/{watcher_id}")
async def delete_watcher(
    watcher_id: int,
    authenticated: bool = Depends(verify_api_key),
):
    """Delete a watcher."""
    try:
        cache = get_cache()

        with cache._get_connection() as conn:
            # Check if watcher exists
            cursor = conn.execute(
                "SELECT state FROM job_watchers WHERE id = ?", (watcher_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Watcher not found")

            # Cancel the monitoring task if active
            if row["state"] == "active":
                try:
                    from ..watchers import get_watcher_engine

                    engine = get_watcher_engine()

                    if (
                        hasattr(engine, "active_tasks")
                        and watcher_id in engine.active_tasks
                    ):
                        engine.active_tasks[watcher_id].cancel()
                        del engine.active_tasks[watcher_id]
                except Exception as engine_error:
                    logger.debug(f"Could not cancel watcher task: {engine_error}")

            # Delete the watcher and its events
            conn.execute(
                "DELETE FROM watcher_events WHERE watcher_id = ?", (watcher_id,)
            )
            conn.execute("DELETE FROM job_watchers WHERE id = ?", (watcher_id,))
            conn.commit()

        return {"message": f"Watcher {watcher_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting watcher {watcher_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete watcher")


@app.post("/api/jobs/{job_id}/watchers")
async def attach_watchers_to_job(
    job_id: str,
    host: str = Query(..., description="Hostname where job is running"),
    watchers: List[Dict[str, Any]] = Body(
        ..., description="List of watcher definitions"
    ),
    authenticated: bool = Depends(verify_api_key),
):
    """Attach watchers to an existing running job."""
    try:
        # Validate job exists and is running
        manager = get_slurm_manager()

        # Get the slurm host
        try:
            slurm_host = manager.get_host_by_name(host)
        except Exception as e:
            logger.error(f"Error getting host {host}: {e}")
            raise HTTPException(status_code=400, detail=f"Unknown host: {host}")

        # Check job status
        try:
            job_info = manager.get_job_info(slurm_host, job_id)
            if not job_info:
                raise HTTPException(
                    status_code=404, detail=f"Job {job_id} not found on {host}"
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting job info for {job_id}: {e}")
            raise HTTPException(
                status_code=500, detail=f"Error checking job status: {str(e)}"
            )

        # Only allow attaching watchers to running or pending jobs
        if job_info.state not in [JobState.RUNNING, JobState.PENDING]:
            raise HTTPException(
                status_code=400,
                detail=f"Can only attach watchers to running or pending jobs. Job {job_id} is in state: {job_info.state}",
            )

        # Parse watcher definitions
        from ..models.watcher import ActionType, WatcherAction, WatcherDefinition

        watcher_defs = []
        for w in watchers:
            # Parse actions
            actions = []
            for a in w.get("actions", []):
                # Handle action type - could be string or enum name
                action_type_str = (
                    a["type"].upper() if isinstance(a["type"], str) else a["type"]
                )
                try:
                    action_type = ActionType[action_type_str]
                except KeyError:
                    # Try with the value instead of name
                    action_type = ActionType(action_type_str.lower())

                action = WatcherAction(type=action_type, params=a.get("params", {}))
                actions.append(action)

            # Create watcher definition
            watcher_def = WatcherDefinition(
                name=w.get("name", f"watcher_{job_id}"),
                pattern=w.get("pattern", ""),
                interval_seconds=w.get(
                    "interval_seconds", 60
                ),  # Default 60s instead of 30s
                # Handle both 'captures' and 'capture_groups' field names for compatibility
                captures=w.get("captures", w.get("capture_groups", [])),
                condition=w.get("condition"),
                actions=actions,
                max_triggers=w.get("max_triggers", 10),
                output_type=w.get("output_type", "stdout"),
                timer_mode_enabled=w.get("timer_mode_enabled", False),
                timer_interval_seconds=w.get(
                    "timer_interval_seconds", 60
                ),  # Default 60s instead of 30s
            )
            watcher_defs.append(watcher_def)

        # Start watchers using the engine
        from ..watchers import get_watcher_engine

        engine = get_watcher_engine()

        # Start watchers for the job
        watcher_ids = await engine.start_watchers_for_job(job_id, host, watcher_defs)

        logger.info(f"Attached {len(watcher_ids)} watchers to job {job_id} on {host}")

        return {
            "message": f"Successfully attached {len(watcher_ids)} watchers to job {job_id}",
            "watcher_ids": watcher_ids,
            "job_id": job_id,
            "hostname": host,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to attach watchers to job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


# WebSocket connection manager for watchers
class WatcherConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Connection might be closed
                pass


watcher_manager = WatcherConnectionManager()


# WebSocket connection manager for jobs
class JobConnectionManager:
    def __init__(self):
        self.active_connections: Dict[
            str, List[WebSocket]
        ] = {}  # job_id -> [websockets]
        self.all_jobs_connections: List[WebSocket] = []  # connections watching all jobs

    async def connect(self, websocket: WebSocket, job_id: Optional[str] = None):
        await websocket.accept()
        if job_id:
            if job_id not in self.active_connections:
                self.active_connections[job_id] = []
            self.active_connections[job_id].append(websocket)
        else:
            self.all_jobs_connections.append(websocket)

    def disconnect(self, websocket: WebSocket, job_id: Optional[str] = None):
        if job_id and job_id in self.active_connections:
            if websocket in self.active_connections[job_id]:
                self.active_connections[job_id].remove(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
        elif websocket in self.all_jobs_connections:
            self.all_jobs_connections.remove(websocket)

    async def send_to_job(self, job_id: str, message: dict):
        """Send message to all connections watching a specific job."""
        if job_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[job_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)
            # Clean up disconnected connections
            for conn in disconnected:
                self.disconnect(conn, job_id)

    async def broadcast_job_update(self, job_id: str, hostname: str, message: dict):
        """Broadcast job update to specific job watchers and all-jobs watchers."""
        # Send to specific job watchers
        await self.send_to_job(job_id, message)

        # Send to all-jobs watchers with job_id and hostname context
        message_with_context = {**message, "job_id": job_id, "hostname": hostname}
        disconnected = []
        for connection in self.all_jobs_connections:
            try:
                await connection.send_json(message_with_context)
            except Exception:
                disconnected.append(connection)
        # Clean up disconnected connections
        for conn in disconnected:
            self.disconnect(conn)


job_manager = JobConnectionManager()


async def monitor_job_updates(
    websocket: WebSocket, job_id: str, hostname: str, actual_job_id: str
):
    """Monitor a specific job for state changes and send updates via WebSocket."""
    try:
        from ..job_data_manager import get_job_data_manager

        get_slurm_manager()
        job_data_manager = get_job_data_manager()
        last_state = None
        last_output_size = 0

        while True:
            await asyncio.sleep(15)  # Poll every 15 seconds

            try:
                # Fetch current job info
                jobs = await job_data_manager.fetch_all_jobs(
                    hostname=hostname, job_ids=[actual_job_id], limit=1
                )
                job_info = jobs[0] if jobs else None

                if not job_info:
                    # Job disappeared or completed - stop any watchers
                    try:
                        from ..watchers import get_watcher_engine

                        engine = get_watcher_engine()
                        await engine.stop_watchers_for_job(actual_job_id, hostname)
                        logger.debug(
                            f"Stopped watchers for disappeared job {actual_job_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Error stopping watchers for disappeared job {actual_job_id}: {e}"
                        )

                    await websocket.send_json(
                        {
                            "type": "job_completed",
                            "job_id": actual_job_id,
                            "hostname": hostname,
                        }
                    )
                    break

                # Check for state change
                if job_info.state != last_state:
                    await websocket.send_json(
                        {
                            "type": "state_change",
                            "job_id": actual_job_id,
                            "hostname": hostname,
                            "old_state": last_state.value if last_state else None,
                            "new_state": job_info.state.value,
                            "job": JobInfoWeb.from_job_info(job_info).model_dump(
                                mode="json"
                            ),
                        }
                    )
                    last_state = job_info.state

                    # Stop watchers when job enters terminal state
                    if job_info.state in [
                        JobState.COMPLETED,
                        JobState.FAILED,
                        JobState.CANCELLED,
                        JobState.TIMEOUT,
                        JobState.UNKNOWN,
                    ]:
                        try:
                            from ..watchers import get_watcher_engine

                            engine = get_watcher_engine()
                            await engine.stop_watchers_for_job(actual_job_id, hostname)
                            logger.info(
                                f"Stopped watchers for job {actual_job_id} (state: {job_info.state.value})"
                            )
                        except Exception as e:
                            logger.error(
                                f"Error stopping watchers for job {actual_job_id}: {e}"
                            )

                    # Also broadcast to all-jobs watchers
                    await job_manager.broadcast_job_update(
                        job_id,
                        hostname,
                        {
                            "type": "state_change",
                            "old_state": last_state.value if last_state else None,
                            "new_state": job_info.state.value,
                            "job": JobInfoWeb.from_job_info(job_info).model_dump(
                                mode="json"
                            ),
                        },
                    )

                # For running jobs, check for new output
                if job_info.state == JobState.RUNNING and job_info.stdout_file:
                    try:
                        output_path = Path(job_info.stdout_file)
                        if output_path.exists():
                            current_size = output_path.stat().st_size
                            if current_size > last_output_size:
                                # Read new content
                                with open(output_path, "r") as f:
                                    f.seek(last_output_size)
                                    new_content = f.read(10000)  # Read up to 10KB
                                    if new_content:
                                        await websocket.send_json(
                                            {
                                                "type": "output_update",
                                                "job_id": actual_job_id,
                                                "hostname": hostname,
                                                "content": new_content,
                                                "truncated": len(new_content) == 10000,
                                            }
                                        )
                                last_output_size = current_size
                    except Exception as e:
                        logger.debug(
                            f"Could not read output for job {actual_job_id}: {e}"
                        )

            except Exception as e:
                logger.error(f"Error monitoring job {actual_job_id}: {e}")

    except asyncio.CancelledError:
        logger.debug(f"Job monitoring cancelled for {actual_job_id}")
    except Exception as e:
        logger.error(f"Fatal error in job monitoring for {actual_job_id}: {e}")


async def send_job_output(websocket: WebSocket, hostname: str, job_id: str):
    """Send current job output to the WebSocket."""
    try:
        manager = get_slurm_manager()
        slurm_host = manager.get_host_by_name(hostname)

        # Get job output
        output_result = await asyncio.to_thread(
            slurm_host.slurm_client.get_job_output, job_id
        )

        if output_result.success:
            await websocket.send_json(
                {
                    "type": "output",
                    "job_id": job_id,
                    "hostname": hostname,
                    "stdout": output_result.stdout,
                    "stderr": output_result.stderr,
                }
            )
        else:
            await websocket.send_json(
                {
                    "type": "output_error",
                    "job_id": job_id,
                    "hostname": hostname,
                    "error": output_result.error,
                }
            )

    except Exception as e:
        logger.error(f"Error sending job output: {e}")
        await websocket.send_json(
            {
                "type": "output_error",
                "job_id": job_id,
                "hostname": hostname,
                "error": str(e),
            }
        )


@app.websocket("/ws/jobs/{job_id}")
async def websocket_job(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time updates of a specific job."""
    try:
        # Verify API key before accepting connection
        if not await verify_websocket_api_key(websocket):
            return

        # Parse job_id to extract hostname if present (format: hostname:job_id)
        if ":" in job_id:
            hostname, actual_job_id = job_id.split(":", 1)
        else:
            # Try to find the job across all hosts
            hostname = None
            actual_job_id = job_id

        # Accept the connection
        await job_manager.connect(websocket, job_id)

        # Send initial job data
        try:
            from ..job_data_manager import get_job_data_manager
            from ..request_coalescer import get_request_coalescer

            manager = get_slurm_manager()
            job_data_manager = get_job_data_manager()
            coalescer = get_request_coalescer()

            # ⚡ PERFORMANCE FIX: Use request coalescer to batch individual job fetches
            # When many WebSocket connections open simultaneously (e.g., user viewing
            # 30 jobs), this batches them into a few bulk queries instead of 30 individual
            # SSH operations, preventing thread pool saturation.

            # Fetch current job info
            if hostname:
                # Define batch fetch function
                async def fetch_batch(host: str, job_ids: List[str]):
                    return await job_data_manager.fetch_all_jobs(
                        hostname=host, job_ids=job_ids, limit=len(job_ids)
                    )

                # Use coalescer to batch with other concurrent requests
                job_info = await coalescer.fetch_job(
                    actual_job_id, hostname, fetch_batch
                )
            else:
                # Search across all hosts (less common, no coalescing for now)
                all_jobs = await job_data_manager.fetch_all_jobs(
                    hostname=None, job_ids=[actual_job_id], limit=1
                )
                job_info = all_jobs[0] if all_jobs else None
                if job_info:
                    hostname = job_info.hostname

            if job_info:
                # Send initial job state
                await websocket.send_json(
                    {
                        "type": "initial",
                        "job": JobInfoWeb.from_job_info(job_info).model_dump(
                            mode="json"
                        ),
                        "hostname": hostname,
                    }
                )

                # Only start monitoring for active jobs (running/pending)
                if job_info.state in [JobState.RUNNING, JobState.PENDING]:
                    # Start background task to monitor job changes
                    monitor_task = create_task(
                        monitor_job_updates(websocket, job_id, hostname, actual_job_id)
                    )
                else:
                    # For completed jobs, just send the final state
                    logger.info(
                        f"Job {actual_job_id} is already in state {job_info.state}, not starting monitor"
                    )
            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Job {actual_job_id} not found"}
                )
        except Exception as e:
            logger.error(f"Error fetching initial job data: {e}", exc_info=True)
            try:
                await websocket.send_json({"type": "error", "message": str(e)})
            except Exception:
                # WebSocket may already be closed
                pass

        # Keep connection alive and wait for messages
        while True:
            try:
                data = await websocket.receive_text()

                if data == "ping":
                    await websocket.send_text("pong")
                elif data == "get_output":
                    # Client requests current output
                    await send_job_output(websocket, hostname, actual_job_id)

            except WebSocketDisconnect:
                job_manager.disconnect(websocket, job_id)
                if "monitor_task" in locals():
                    monitor_task.cancel()
                break
            except Exception:
                job_manager.disconnect(websocket, job_id)
                if "monitor_task" in locals():
                    monitor_task.cancel()
                break

    except Exception as e:
        logger.error(f"WebSocket job error: {e}")
        job_manager.disconnect(websocket, job_id)


# Global task to track single monitoring instance
_all_jobs_monitor_task: Optional[asyncio.Task] = None
_all_jobs_websockets: Set[WebSocket] = set()
_all_jobs_monitor_lock = asyncio.Lock()


async def monitor_all_jobs_singleton():
    """Single background task that broadcasts to all connected WebSocket clients."""
    global _all_jobs_websockets
    import copy  # For deep copying job dicts to avoid object reuse

    try:
        from ..job_data_manager import get_job_data_manager

        get_slurm_manager()
        job_data_manager = get_job_data_manager()
        job_states = {}
        # ⚡ PERFORMANCE: Use different intervals for different update types
        last_full_update = 0
        FAST_INTERVAL = 15  # Fast updates for running jobs every 15 seconds
        FULL_INTERVAL = 60  # Full updates including completed jobs every 60 seconds

        while True:
            await asyncio.sleep(FAST_INTERVAL)

            # If no clients are connected, stop the task
            if not _all_jobs_websockets:
                logger.info("No WebSocket clients connected, stopping monitor task")
                break

            try:
                # ⚡ DIAGNOSTIC: Log monitoring task activity
                logger.debug(
                    f"Monitor task running - {len(_all_jobs_websockets)} clients connected"
                )

                current_time = asyncio.get_event_loop().time()
                time_since_full = current_time - last_full_update
                # Determine if we should do a full update (including completed jobs)
                # or just active jobs (faster)
                if time_since_full >= FULL_INTERVAL:
                    # Full update every 60 seconds: fetch all recent jobs
                    logger.debug(
                        "Performing full job update (active + recent completed)"
                    )
                    all_jobs = await job_data_manager.fetch_all_jobs(
                        hostname=None,
                        limit=500,
                        active_only=False,
                        since="1d",  # Only check jobs from last day
                    )
                    last_full_update = current_time
                else:
                    # Fast update every 15 seconds: only fetch active jobs
                    logger.debug("Performing fast job update (active only)")
                    all_jobs = await job_data_manager.fetch_all_jobs(
                        hostname=None,
                        limit=500,
                        active_only=True,  # ⚡ Only fetch running/pending jobs for speed
                    )

                logger.debug(f"Monitor task fetched {len(all_jobs)} jobs")

                current_job_ids = set()
                updates = []

                for job in all_jobs:
                    job_key = f"{job.hostname}:{job.job_id}"
                    current_job_ids.add(job_key)

                    # Validate job object consistency
                    if not job.job_id:
                        logger.error(f"Job object missing job_id: {job}")
                        continue

                    # ⚡ PERFORMANCE FIX: Send updates when:
                    # 1. Job is new (not in job_states)
                    # 2. Job state changed
                    # 3. Job is RUNNING (to update elapsed_time in UI)
                    is_new = job_key not in job_states
                    state_changed = not is_new and job_states[job_key] != job.state
                    is_running = job.state == "R"

                    if is_new or state_changed or is_running:
                        old_state = job_states.get(job_key)
                        job_states[job_key] = job.state
                        new_state_value = (
                            job.state.value
                            if hasattr(job.state, "value")
                            else job.state
                        )
                        old_state_value = (
                            old_state.value
                            if old_state is not None and hasattr(old_state, "value")
                            else old_state
                        )

                        # Capture job_id BEFORE any processing to detect mutations
                        original_job_id = job.job_id
                        original_hostname = job.hostname

                        # Create job dict and validate consistency
                        # IMPORTANT: Create a fresh JobInfoWeb object for each update
                        web_job = JobInfoWeb.from_job_info(job)
                        job_dict = web_job.model_dump(mode="json")

                        # Make a deep copy to ensure no dict reuse across updates
                        # This prevents the same dict object from being shared across multiple updates
                        job_dict_copy = copy.deepcopy(job_dict)

                        # Verify job_id didn't change during processing
                        if job.job_id != original_job_id:
                            logger.error(
                                f"Job object MUTATED during processing: was {original_job_id}, now {job.job_id}"
                            )
                            continue

                        # Verify job_id consistency before adding to updates
                        if job_dict_copy["job_id"] != original_job_id:
                            logger.error(
                                f"Job ID mismatch in batch_update: original_job_id={original_job_id} vs job_dict['job_id']={job_dict_copy['job_id']}, hostname={original_hostname}"
                            )
                            logger.error(f"Full job object: {job}")
                            logger.error(f"Full job_dict: {job_dict_copy}")
                            continue  # Skip this update to prevent cache corruption

                        updates.append(
                            {
                                "type": "job_update",
                                "job_id": original_job_id,  # Use captured value
                                "hostname": original_hostname,  # Use captured value
                                "old_state": old_state_value,
                                "new_state": new_state_value,
                                "job": job_dict_copy,
                            }
                        )

                # Detect jobs that disappeared from the list (completed/removed)
                completed_jobs = set(job_states.keys()) - current_job_ids
                for job_key in completed_jobs:
                    hostname, job_id = job_key.split(":", 1)

                    try:
                        completed_job_data = await job_data_manager.fetch_all_jobs(
                            hostname=hostname, job_ids=[job_id], limit=1
                        )
                        if completed_job_data:
                            completed_job = completed_job_data[0]

                            updates.append(
                                {
                                    "type": "job_completed",
                                    "job_id": job_id,
                                    "hostname": hostname,
                                    "job": JobInfoWeb.from_job_info(
                                        completed_job
                                    ).model_dump(mode="json"),
                                }
                            )

                        else:
                            # Skip sending update if we can't get job data
                            # Frontend will handle job removal via periodic sync
                            logger.debug(
                                f"Skipping job_completed update for {job_id} - no job data available"
                            )
                    except Exception as e:
                        # Skip sending update if fetch fails
                        # Frontend will handle job removal via periodic sync
                        logger.debug(
                            f"Skipping job_completed update for {job_id} - fetch failed: {e}"
                        )

                    del job_states[job_key]

                # Broadcast to all connected clients
                if updates:
                    # ⚡ DIAGNOSTIC: Count update types
                    new_jobs = sum(
                        1
                        for u in updates
                        if u["type"] == "job_update"
                        and not any(
                            j for j in job_states if j.split(":")[1] == u["job_id"]
                        )
                    )
                    state_changes = sum(
                        1 for u in updates if u["type"] == "state_change"
                    )
                    running_refreshes = len(updates) - new_jobs - state_changes

                    logger.info(
                        f"Broadcasting {len(updates)} updates ({new_jobs} new, {state_changes} state changes, {running_refreshes} running refreshes) to {len(_all_jobs_websockets)} clients"
                    )

                    message = {
                        "type": "batch_update",
                        "updates": updates,
                        "timestamp": datetime.now().isoformat(),
                    }

                    disconnected = set()
                    for ws in _all_jobs_websockets:
                        try:
                            await ws.send_json(message)
                        except Exception as e:
                            logger.debug(f"Failed to send to WebSocket: {e}")
                            disconnected.add(ws)

                    # Remove disconnected clients
                    _all_jobs_websockets -= disconnected

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")

    except asyncio.CancelledError:
        logger.info("Monitor task cancelled")
    except Exception as e:
        logger.error(f"Fatal error in monitor task: {e}")


@app.websocket("/ws/jobs")
async def websocket_all_jobs(websocket: WebSocket):
    """WebSocket endpoint for real-time updates of all jobs."""
    global _all_jobs_monitor_task, _all_jobs_websockets

    try:
        # Verify API key before accepting connection
        if not await verify_websocket_api_key(websocket):
            return

        # Accept the connection
        await job_manager.connect(websocket)

        # Send initial job list
        try:
            from ..cache import get_cache
            from ..job_data_manager import get_job_data_manager

            manager = get_slurm_manager()
            job_data_manager = get_job_data_manager()
            cache = get_cache()

            # ⚡ FIX: First try to get jobs from cache to avoid blocking on concurrent fetches
            # If cache is empty or stale, fetch from Slurm
            all_jobs = []

            # Try to get recent jobs from cache first (only from last day)
            from datetime import datetime, timedelta

            since_dt = datetime.now() - timedelta(days=1)
            cached_job_data = cache.get_cached_jobs(
                hostname=None, limit=500, since=since_dt
            )

            if cached_job_data and len(cached_job_data) > 0:
                # Convert CachedJobData to JobInfo
                logger.info(
                    f"Using {len(cached_job_data)} cached jobs (since {since_dt}) for WebSocket initial data"
                )
                all_jobs = [
                    cached_data.job_info
                    for cached_data in cached_job_data
                    if cached_data.job_info
                ]
            else:
                # No cache available, fetch from Slurm (may return empty if hosts are locked)
                logger.info(
                    "No cache available, fetching jobs for WebSocket initial data"
                )
                all_jobs = await job_data_manager.fetch_all_jobs(
                    hostname=None,
                    limit=500,  # Increased from 100 to 500 for more complete initial data
                    active_only=False,  # Include completed jobs to show accurate states
                    since="1d",  # Only fetch jobs from last day to avoid overwhelming the UI
                )

            # Convert to web format and group by host
            # Keep both object and dict versions - objects for grouping, dicts for JSON
            # ⚡ FIX: Initialize with ALL configured hosts, not just hosts with jobs
            jobs_by_host = {}
            jobs_by_host_objects = {}  # Keep JobInfoWeb objects for grouping

            # Initialize all configured hosts with empty arrays
            for slurm_host in manager.slurm_hosts:
                hostname = slurm_host.host.hostname
                jobs_by_host[hostname] = []
                jobs_by_host_objects[hostname] = []

            # Now add jobs to their respective hosts
            for job in all_jobs:
                if job.hostname not in jobs_by_host:
                    # This shouldn't happen since we initialized all hosts above,
                    # but handle it just in case
                    jobs_by_host[job.hostname] = []
                    jobs_by_host_objects[job.hostname] = []

                web_job = JobInfoWeb.from_job_info(job)
                jobs_by_host[job.hostname].append(web_job.model_dump(mode="json"))
                jobs_by_host_objects[job.hostname].append(web_job)

            # ⚡ NEW: Compute array job groups for each host for instant display
            array_groups_by_host = {}
            for hostname, host_jobs in jobs_by_host_objects.items():
                if host_jobs:
                    _, array_groups = group_array_job_tasks(host_jobs)
                    if array_groups:
                        # Convert to dict format for JSON serialization
                        # Use model_dump() which handles all fields correctly
                        array_groups_by_host[hostname] = [
                            g.model_dump(mode="json") for g in array_groups
                        ]

            # ⚡ PERFORMANCE: Log initial data size for monitoring
            logger.info(
                f"Sending initial WebSocket data: {len(all_jobs)} jobs from {len(jobs_by_host)} hosts with {len(array_groups_by_host)} hosts having array groups"
            )

            await websocket.send_json(
                {
                    "type": "initial",
                    "jobs": jobs_by_host,
                    "total": len(all_jobs),
                    "array_groups": array_groups_by_host,
                }
            )

            # Add this WebSocket to the set of connected clients
            async with _all_jobs_monitor_lock:
                _all_jobs_websockets.add(websocket)

                # Start singleton monitoring task if not already running
                if _all_jobs_monitor_task is None or _all_jobs_monitor_task.done():
                    logger.info("Starting singleton all-jobs monitor task")
                    _all_jobs_monitor_task = create_task(monitor_all_jobs_singleton())

        except WebSocketDisconnect:
            # Client disconnected - this is normal, don't log as error
            logger.debug("WebSocket client disconnected during initial data fetch")
            _all_jobs_websockets.discard(websocket)
            return
        except Exception as e:
            # Only log actual errors, not disconnections
            if not isinstance(e, WebSocketDisconnect):
                logger.error(f"Error fetching initial jobs data: {e}", exc_info=True)
            _all_jobs_websockets.discard(websocket)
            try:
                await websocket.send_json({"type": "error", "message": str(e)})
            except WebSocketDisconnect:
                # WebSocket closed, can't send error - this is fine
                pass

        # Keep connection alive and wait for messages
        while True:
            try:
                data = await websocket.receive_text()

                # ⚡ PERFORMANCE: Handle both JSON and text ping messages
                try:
                    import json

                    parsed = json.loads(data)
                    if parsed.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                        logger.debug("Received JSON ping, sent pong response")
                except json.JSONDecodeError:
                    # Handle old-style text ping for backward compatibility
                    if data == "ping":
                        await websocket.send_text("pong")
                        logger.debug("Received text ping, sent pong response")

            except WebSocketDisconnect:
                job_manager.disconnect(websocket)
                _all_jobs_websockets.discard(websocket)
                break
            except Exception:
                job_manager.disconnect(websocket)
                _all_jobs_websockets.discard(websocket)
                break

    except Exception as e:
        logger.error(f"WebSocket all jobs error: {e}")
        job_manager.disconnect(websocket)
        _all_jobs_websockets.discard(websocket)


@app.websocket("/ws/watchers")
async def websocket_watchers(websocket: WebSocket):
    """WebSocket endpoint for real-time watcher updates."""
    try:
        # Verify API key before accepting connection
        if not await verify_websocket_api_key(websocket):
            return

        # Accept the connection
        await watcher_manager.connect(websocket)

        # Send initial data
        cache = get_cache()
        with cache._get_connection() as conn:
            # Get recent events
            cursor = conn.execute("""
                SELECT * FROM watcher_events 
                ORDER BY timestamp DESC 
                LIMIT 10
            """)
            columns = [desc[0] for desc in cursor.description]
            events = []
            for row in cursor.fetchall():
                event_dict = dict(zip(columns, row))
                if event_dict.get("captured_vars"):
                    event_dict["captured_vars"] = json.loads(
                        event_dict["captured_vars"]
                    )
                events.append(event_dict)

            await websocket.send_json({"type": "initial", "events": events})

        # Keep connection alive and wait for messages
        while True:
            try:
                # Wait for any message from client (can be ping/pong)
                data = await websocket.receive_text()

                # If client sends "ping", respond with "pong"
                if data == "ping":
                    await websocket.send_text("pong")

            except WebSocketDisconnect:
                watcher_manager.disconnect(websocket)
                break
            except Exception:
                # Any other error, disconnect
                watcher_manager.disconnect(websocket)
                break

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in watcher_manager.active_connections:
            watcher_manager.disconnect(websocket)


def main():
    """Run the secure web server."""
    import uvicorn

    # Show authentication status
    if REQUIRE_API_KEY:
        logger.info("🔐 Starting Slurm Manager API with authentication enabled")
        logger.info("   API key required for all requests")
    else:
        logger.info("🚀 Starting Slurm Manager API in open mode (no authentication)")
        logger.info("   To enable authentication: export SSYNC_REQUIRE_API_KEY=true")
        logger.info("   To generate API key: ssync auth setup")

    logger.info("📡 Server starting at http://127.0.0.1:8042")

    # Production settings
    uvicorn.run(
        app,
        host=os.getenv(
            "SSYNC_HOST", "127.0.0.1"
        ),  # Default to localhost, allow override
        port=int(os.getenv("SSYNC_PORT", "8042")),
        log_level=os.getenv("SSYNC_LOG_LEVEL", "info").lower(),
        access_log=False,  # Disable access logs for security
        server_header=False,  # Don't expose server info
        date_header=False,  # Don't expose date
    )


if __name__ == "__main__":
    main()
