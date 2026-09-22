"""
Watcher service that runs continuously to monitor jobs.
Can be run as a standalone service or integrated with the web server.
"""

import asyncio
import fcntl
import logging
import os
from pathlib import Path
from typing import Optional

from ..cache import get_cache
from ..utils.async_helpers import create_task
from ..utils.executors import run_local
from .engine import get_watcher_engine

logger = logging.getLogger(__name__)


class WatcherService:
    """Service to continuously run watchers."""

    LOCK_FILE = Path.home() / ".config" / "ssync" / "watcher-service.lock"

    def __init__(self):
        self.engine = get_watcher_engine()
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._lock_handle = None

    async def start(self):
        """Start the watcher service."""
        if self.running:
            logger.info("Watcher service already running")
            return

        if not self._acquire_lock():
            logger.info("Another watcher service instance already owns monitoring")
            return

        self.running = True
        self.engine._shutdown = False
        self._task = create_task(self._run())
        logger.info("Watcher service started")

    async def stop(self):
        """Stop the watcher service."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Stop monitors first, then let actions that were already admitted
        # finish while the remote/local worker pools are still available.
        self.engine._shutdown = True
        active_tasks = tuple(self.engine.active_tasks.values())
        for task in active_tasks:
            if not task.done():
                task.cancel()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)
        self.engine.active_tasks.clear()

        while True:
            action_tasks = tuple(
                task
                for task in getattr(self.engine, "_action_tasks", [])
                if not task.done()
            )
            if not action_tasks:
                break
            await asyncio.gather(*action_tasks, return_exceptions=True)

        # Actions can schedule websocket refreshes while they finish. Cancel
        # refresh tasks only after the action drain so no late refresh is left
        # behind when the service releases its lock.
        refresh_tasks = tuple(
            task
            for task in getattr(self.engine, "_watcher_refresh_tasks", {}).values()
            if not task.done()
        )
        for task in refresh_tasks:
            task.cancel()
        if refresh_tasks:
            await asyncio.gather(*refresh_tasks, return_exceptions=True)
        getattr(self.engine, "_watcher_refresh_tasks", {}).clear()
        refresh_pending = getattr(self.engine, "_watcher_refresh_pending", None)
        refresh_lock = getattr(self.engine, "_watcher_refresh_lock", None)
        if refresh_pending is not None:
            if refresh_lock is None:
                refresh_pending.clear()
            else:
                with refresh_lock:
                    refresh_pending.clear()

        self._release_lock()
        logger.info("Watcher service stopped")

    async def _run(self):
        """Main service loop."""
        while self.running:
            try:
                # Check for new watchers every 60 seconds (reduced from 30s)
                await self._check_for_new_watchers()
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in watcher service: {e}")
                await asyncio.sleep(5)

    async def _check_for_new_watchers(self):
        """Check for new watchers to start."""
        cache = get_cache()

        def load_active_watchers():
            with cache._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT id, job_id, hostname
                    FROM job_watchers
                    WHERE state = 'active'
                """)
                return cursor.fetchall()

        watchers = await run_local(load_active_watchers)

        for watcher_id, job_id, hostname in watchers:
            existing_task = self.engine.active_tasks.get(watcher_id)
            task_loop_closed = False
            if existing_task is not None and not existing_task.done():
                try:
                    task_loop_closed = existing_task.get_loop().is_closed()
                except (AttributeError, RuntimeError):
                    pass

            if existing_task is None or existing_task.done() or task_loop_closed:
                if task_loop_closed:
                    logger.warning(
                        f"Replacing watcher {watcher_id} task bound to a closed loop"
                    )
                    existing_task.cancel()
                logger.info(f"Starting monitor for watcher {watcher_id} (job {job_id})")
                task = create_task(
                    self.engine._monitor_watcher(watcher_id, job_id, hostname)
                )
                if task is not None:
                    self.engine.active_tasks[watcher_id] = task

        # Clean up completed tasks
        completed = []
        for watcher_id, task in self.engine.active_tasks.items():
            if task.done():
                completed.append(watcher_id)

        for watcher_id in completed:
            del self.engine.active_tasks[watcher_id]
            logger.debug(f"Removed completed watcher {watcher_id}")

    def _acquire_lock(self) -> bool:
        """Acquire a global lock so only one API process runs watchers."""
        if self._lock_handle is not None:
            return True

        try:
            self.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
            lock_handle = open(self.LOCK_FILE, "a+")
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_handle.seek(0)
            lock_handle.truncate()
            lock_handle.write(str(os.getpid()))
            lock_handle.flush()
            self._lock_handle = lock_handle
            return True
        except BlockingIOError:
            return False
        except Exception as e:
            logger.warning(f"Failed to acquire watcher service lock: {e}")
            return False

    def _release_lock(self) -> None:
        """Release the global watcher lock if held."""
        if self._lock_handle is None:
            return

        try:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass

        try:
            self._lock_handle.close()
        except Exception:
            pass

        self._lock_handle = None


# Global service instance
_watcher_service: Optional[WatcherService] = None


def get_watcher_service() -> WatcherService:
    """Get the global watcher service instance."""
    global _watcher_service
    if _watcher_service is None:
        _watcher_service = WatcherService()
    return _watcher_service


async def start_watcher_service():
    """Start the global watcher service."""
    service = get_watcher_service()
    await service.start()


async def stop_watcher_service():
    """Stop the global watcher service."""
    service = get_watcher_service()
    await service.stop()
