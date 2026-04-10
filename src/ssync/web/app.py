"""Secure version of the Slurm Manager API with enhanced security measures."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    WebSocket,
)
from fastapi.security import APIKeyHeader

from .. import config
from ..launch_events import LaunchEventManager
from ..manager import SlurmManager
from ..utils.logging import setup_logger
from .api import (
    register_cluster_routes,
    register_job_routes,
    register_launch_routes,
    register_local_fs_routes,
    register_notification_routes,
    register_status_routes,
    register_system_routes,
    register_watcher_routes,
)
from .cache import cache_job_state_transition, get_cache_middleware
from .frontend import register_frontend_routes
from .lifecycle import (
    build_slurm_manager_getter,
    create_periodic_connection_health_check,
    register_lifecycle_events,
)
from .realtime import (
    broadcast_job_state as _broadcast_job_state,
)
from .realtime import (
    broadcast_launch_event_to_all_jobs as _broadcast_launch_event_to_all_jobs,
)
from .realtime import (
    job_manager,
    websocket_all_jobs_handler,
    websocket_job_handler,
    websocket_watchers_handler,
)
from .security import (
    APIKeyManager,
    configure_security_middleware,
    create_auth_dependencies,
)

logger = setup_logger(__name__, "INFO")


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
launch_event_manager = LaunchEventManager()
api_key_manager = APIKeyManager()
_shutdown_event = threading.Event()
_cache_middleware = get_cache_middleware()
get_slurm_manager = build_slurm_manager_getter(config, SlurmManager)
periodic_connection_health_check = create_periodic_connection_health_check(
    get_slurm_manager=get_slurm_manager,
    shutdown_event=_shutdown_event,
)
REQUIRE_API_KEY = os.getenv("SSYNC_REQUIRE_API_KEY", "false").lower() == "true"
verify_api_key, get_api_key, verify_api_key_flexible, verify_websocket_api_key = (
    create_auth_dependencies(
        api_key_manager=api_key_manager,
        api_key_header=api_key_header,
        require_api_key=REQUIRE_API_KEY,
        logger=logger,
    )
)
configure_security_middleware(app, logger)
register_lifecycle_events(
    app,
    thread_pool_size=THREAD_POOL_SIZE,
    launch_event_manager=launch_event_manager,
    get_slurm_manager=get_slurm_manager,
    cache_middleware=_cache_middleware,
    api_key_manager=api_key_manager,
    executor=executor,
    shutdown_event=_shutdown_event,
    periodic_connection_health_check=periodic_connection_health_check,
)
register_notification_routes(
    app,
    get_api_key_dependency=get_api_key,
    verify_api_key_dependency=verify_api_key,
    notification_settings=config.notification_settings,
)


frontend_dist = Path(__file__).parent.parent.parent.parent / "web-frontend" / "dist"
if not register_frontend_routes(app, frontend_dist):

    @app.get("/")
    async def root(_authenticated: bool = Depends(verify_api_key)):
        """API root endpoint."""
        return {
            "message": "Slurm Manager API",
            "version": "2.0.0",
            "security": "enhanced",
            "documentation": "/docs" if ENABLE_DOCS else "disabled",
            "frontend": "Not built. Run 'npm run build' in web-frontend directory.",
        }


register_watcher_routes(
    app,
    verify_api_key_dependency=verify_api_key,
    get_slurm_manager=get_slurm_manager,
)

register_cluster_routes(
    app,
    verify_api_key_dependency=verify_api_key,
    get_slurm_manager=get_slurm_manager,
    executor=executor,
)

register_system_routes(
    app,
    verify_api_key_dependency=verify_api_key,
    get_slurm_manager=get_slurm_manager,
    enable_docs=ENABLE_DOCS,
)

register_local_fs_routes(
    app,
    verify_api_key_dependency=verify_api_key,
)

register_job_routes(
    app,
    verify_api_key_dependency=verify_api_key,
    verify_api_key_flexible_dependency=verify_api_key_flexible,
    get_slurm_manager=get_slurm_manager,
    cache_middleware=_cache_middleware,
    job_manager=job_manager,
)

register_launch_routes(
    app,
    verify_api_key_dependency=verify_api_key,
    verify_api_key_flexible_dependency=verify_api_key_flexible,
    get_slurm_manager=get_slurm_manager,
    cache_middleware=_cache_middleware,
    cache_job_state_transition=cache_job_state_transition,
    broadcast_job_state=_broadcast_job_state,
    launch_event_manager=launch_event_manager,
    executor=executor,
)

register_status_routes(
    app,
    verify_api_key_dependency=verify_api_key,
    get_slurm_manager=get_slurm_manager,
    cache_middleware=_cache_middleware,
)
launch_event_manager.set_websocket_broadcaster(_broadcast_launch_event_to_all_jobs)


@app.websocket("/ws/jobs/{job_id}")
async def websocket_job(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time updates of a specific job."""
    await websocket_job_handler(
        websocket,
        job_id,
        verify_websocket_api_key=verify_websocket_api_key,
        get_slurm_manager=get_slurm_manager,
    )


@app.websocket("/ws/jobs")
async def websocket_all_jobs(websocket: WebSocket):
    """WebSocket endpoint for real-time updates of all jobs."""
    await websocket_all_jobs_handler(
        websocket,
        verify_websocket_api_key=verify_websocket_api_key,
        get_slurm_manager=get_slurm_manager,
        cache_middleware=_cache_middleware,
    )


@app.websocket("/ws/watchers")
async def websocket_watchers(websocket: WebSocket):
    """WebSocket endpoint for real-time watcher updates."""
    await websocket_watchers_handler(
        websocket,
        verify_websocket_api_key=verify_websocket_api_key,
    )


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
