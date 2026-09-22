"""Lifecycle and Slurm manager wiring helpers for the web app."""

import asyncio
import os
import threading

from ..notifications.monitor import (
    start_notification_monitor,
    stop_notification_monitor,
)
from ..utils.async_helpers import create_task
from ..utils.executors import run_background, run_local
from ..utils.logging import configure_logging, setup_logger
from .cache import start_cache_scheduler, stop_cache_scheduler

logger = setup_logger(__name__)


def build_slurm_manager_getter(config_module, slurm_manager_cls):
    """Create a closure-backed Slurm manager getter with config reload support."""
    slurm_manager = None
    config_last_modified = None
    manager_lock = threading.Lock()

    def get_slurm_manager():
        nonlocal slurm_manager, config_last_modified

        with manager_lock:
            config_path = config_module.config_path
            current_mtime = config_path.stat().st_mtime if config_path.exists() else 0
            config_changed = (
                config_last_modified is None or current_mtime > config_last_modified
            )

            if slurm_manager is None or config_changed:
                if slurm_manager:
                    slurm_manager.close_connections()

                slurm_hosts = config_module.load_config()
                connection_timeout = int(
                    os.environ.get(
                        "SSYNC_CONNECTION_TIMEOUT",
                        config_module.connection_settings.get("connect_timeout", 30),
                    )
                )
                command_timeout = int(
                    os.environ.get(
                        "SSYNC_COMMAND_TIMEOUT",
                        config_module.connection_settings.get("command_timeout", 120),
                    )
                )
                slurm_manager = slurm_manager_cls(
                    slurm_hosts,
                    connection_timeout=connection_timeout,
                    command_timeout=command_timeout,
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
                    manager = await run_local(get_slurm_manager)
                    unhealthy_count = await run_background(
                        manager.check_connection_health
                    )
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
    executors,
    shutdown_event,
    periodic_connection_health_check,
) -> None:
    """Register FastAPI startup and shutdown lifecycle handlers."""

    periodic_task = None

    @app.on_event("startup")
    async def startup_event():
        configure_logging(memory=True)
        await launch_event_manager.start()

        logger.info(
            f"Starting Slurm Manager API with {thread_pool_size} worker threads"
        )
        shutdown_event.clear()
        _ = await run_local(get_slurm_manager)
        logger.info("Secure API started, manager initialized")

        try:
            from ..watchers.daemon import WatcherDaemon

            stopped = await run_local(WatcherDaemon.stop_all)
            if stopped:
                logger.info(
                    "Stopped standalone watcher runners because API watcher service owns monitoring"
                )
        except Exception as e:
            logger.warning(f"Failed to stop standalone watcher daemon: {e}")

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

        nonlocal periodic_task
        periodic_task = create_task(periodic_connection_health_check())
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

        if periodic_task is not None and not periodic_task.done():
            periodic_task.cancel()
            await asyncio.gather(periodic_task, return_exceptions=True)

        from .api.launch import wait_for_active_launch_tasks

        await wait_for_active_launch_tasks()
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
            await run_local(api_key_manager.flush_usage_stats)
        except Exception:
            pass

        from .. import job_data_manager, request_coalescer
        from ..notifications import service as notification_service
        from .services.jobs import _JOB_REFRESH_TASKS, _OUTPUT_REFRESH_TASKS
        from .status_helpers import _STATUS_REFRESH_TASKS

        if request_coalescer._coalescer is not None:
            await request_coalescer._coalescer.close()
        registries = [_JOB_REFRESH_TASKS, _OUTPUT_REFRESH_TASKS, _STATUS_REFRESH_TASKS]
        notifications = notification_service._notification_service
        if notifications is not None:
            # A claimed event must finish dispatch/marking: cancellation here
            # would strand its durable claim and suppress later delivery.
            await notifications.close()
        data_manager = job_data_manager._job_data_manager
        if data_manager is not None:
            registries.extend(
                [
                    data_manager._host_fetch_tasks,
                    data_manager._output_harvest_tasks,
                    data_manager._output_fetch_futures,
                ]
            )
        tasks = {task for registry in registries for task in registry.values()}
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        seen_executor_ids = set()
        for executor in executors:
            executor_id = id(executor)
            if executor_id in seen_executor_ids:
                continue
            seen_executor_ids.add(executor_id)
            await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=True)
        logger.info("Thread pools shutdown complete")

        try:
            await asyncio.to_thread(lambda: get_slurm_manager().close_connections())
            logger.info("Closed all SSH connections")
        except Exception:
            pass

        try:
            await asyncio.to_thread(cache_middleware.cache.close)
            logger.info("Closed job cache")
        except Exception:
            pass

        logger.info("Shutdown complete")
