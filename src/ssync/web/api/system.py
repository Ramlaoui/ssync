"""System and admin route registration."""

import os
import signal
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query

from ...utils.async_helpers import create_task
from ...utils.logging import get_memory_handler, setup_logger

logger = setup_logger(__name__)


def register_system_routes(
    app: FastAPI,
    *,
    verify_api_key_dependency,
    get_slurm_manager,
    enable_docs: bool,
) -> None:
    """Register system and admin routes."""

    @app.get("/health")
    async def health_check():
        """Health check endpoint (no auth required)."""
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}

    @app.post("/api/shutdown")
    async def shutdown_server(
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Shutdown the API server gracefully."""
        logger.info("Shutdown requested via API")

        async def delayed_shutdown():
            """Shutdown after a brief delay to allow response to be sent."""
            import asyncio

            await asyncio.sleep(0.5)
            os.kill(os.getpid(), signal.SIGTERM)

        create_task(delayed_shutdown())
        return {"status": "shutting_down", "message": "Server is shutting down"}

    @app.get("/api/logs")
    async def get_server_logs(
        lines: int = Query(default=50, ge=1, le=1000),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Get recent server logs."""
        memory_handler = get_memory_handler()
        logs = memory_handler.get_logs(lines)
        return {"logs": logs, "count": len(logs)}

    @app.get("/api/info")
    async def api_info(_authenticated: bool = Depends(verify_api_key_dependency)):
        """API info endpoint."""
        return {
            "message": "Slurm Manager API",
            "version": "2.0.0",
            "security": "enhanced",
            "documentation": "/docs" if enable_docs else "disabled",
        }

    @app.get("/api/connections/stats")
    async def get_connection_stats(
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
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
            raise HTTPException(
                status_code=500, detail="Failed to get connection stats"
            )

    @app.post("/api/connections/refresh")
    async def refresh_connections(
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
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
