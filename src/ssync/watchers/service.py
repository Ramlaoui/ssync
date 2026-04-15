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

        watchers = await asyncio.to_thread(load_active_watchers)

        for watcher_id, job_id, hostname in watchers:
            if watcher_id not in self.engine.active_tasks:
                logger.info(f"Starting monitor for watcher {watcher_id} (job {job_id})")
                task = create_task(
                    self.engine._monitor_watcher(watcher_id, job_id, hostname)
                )
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
