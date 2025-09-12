"""
Watcher service that runs continuously to monitor jobs.
Can be run as a standalone service or integrated with the web server.
"""

import asyncio
import logging
from typing import Optional

from ..cache import get_cache
from .engine import get_watcher_engine

logger = logging.getLogger(__name__)


class WatcherService:
    """Service to continuously run watchers."""

    def __init__(self):
        self.engine = get_watcher_engine()
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the watcher service."""
        if self.running:
            logger.info("Watcher service already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._run())
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

        with cache._get_connection() as conn:
            # Get active watchers that aren't already running
            cursor = conn.execute("""
                SELECT id, job_id, hostname
                FROM job_watchers
                WHERE state = 'active'
            """)
            watchers = cursor.fetchall()

        for watcher_id, job_id, hostname in watchers:
            if watcher_id not in self.engine.active_tasks:
                logger.info(f"Starting monitor for watcher {watcher_id} (job {job_id})")
                task = asyncio.create_task(
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
