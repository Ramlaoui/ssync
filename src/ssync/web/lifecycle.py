"""Lifecycle and Slurm manager wiring helpers for the web app."""

import asyncio
import os

from ..notifications.monitor import (
    start_notification_monitor,
    stop_notification_monitor,
)
from ..utils.async_helpers import create_task
from ..utils.logging import configure_logging, setup_logger
from .cache import start_cache_scheduler, stop_cache_scheduler

logger = setup_logger(__name__)


def build_slurm_manager_getter(config_module, slurm_manager_cls):
    """Create a closure-backed Slurm manager getter with config reload support."""
    slurm_manager = None
    config_last_modified = None

    def get_slurm_manager():
        nonlocal slurm_manager, config_last_modified

        config_path = config_module.config_path
        current_mtime = config_path.stat().st_mtime if config_path.exists() else 0
        config_changed = (
            config_last_modified is None or current_mtime > config_last_modified
        )

        if slurm_manager is None or config_changed:
            if slurm_manager:
                slurm_manager.close_connections()

            slurm_hosts = config_module.load_config()
            connection_timeout = int(os.environ.get("SSYNC_CONNECTION_TIMEOUT", "30"))
            slurm_manager = slurm_manager_cls(
                slurm_hosts, connection_timeout=connection_timeout
            )
            config_last_modified = current_mtime

        return slurm_manager

    return get_slurm_manager


def create_periodic_connection_health_check(*, get_slurm_manager, shutdown_event):
    """Create the periodic connection health check coroutine."""

    async def periodic_connection_health_check():
        check_interval = 600

        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(check_interval)
                if shutdown_event.is_set():
                    break

                try:
                    unhealthy_count = get_slurm_manager().check_connection_health()
                    if unhealthy_count > 0:
                        logger.info(
                            f"Periodic health check: Removed {unhealthy_count} unhealthy connections"
                        )
                except Exception as e:
                    logger.error(f"Error during periodic connection health check: {e}")
            except asyncio.CancelledError:
                logger.info("Periodic connection health check cancelled")
                break
            except Exception as e:
                logger.error(f"Unexpected error in periodic health check: {e}")

        logger.info("Periodic connection health check stopped")

    return periodic_connection_health_check


def register_lifecycle_events(
    app,
    *,
    thread_pool_size,
    launch_event_manager,
    get_slurm_manager,
    cache_middleware,
    api_key_manager,
    executor,
    shutdown_event,
    periodic_connection_health_check,
) -> None:
    """Register FastAPI startup and shutdown lifecycle handlers."""

    @app.on_event("startup")
    async def startup_event():
        configure_logging(memory=True)
        await launch_event_manager.start()

        logger.info(f"Starting Slurm Manager API with {thread_pool_size} worker threads")
        _ = get_slurm_manager()
        logger.info("Secure API started, manager initialized")

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
    async def shutdown_event_handler():
        logger.info("Shutting down Slurm Manager API...")
        shutdown_event.set()
        await launch_event_manager.stop()

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

        try:
            get_slurm_manager().close_connections()
            logger.info("Closed all SSH connections")
        except Exception:
            pass

        try:
            cache_middleware.cache.close()
            logger.info("Closed job cache")
        except Exception:
            pass

        logger.info("Shutdown complete")
