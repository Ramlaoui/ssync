"""
Background scheduler for cache maintenance tasks.

This module provides automated cache cleanup and verification.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from ..cache_config import get_cache_config
from ..utils.logging import setup_logger
from .cache_middleware import get_cache_middleware

logger = setup_logger(__name__)


class CacheScheduler:
    """
    Background scheduler for cache maintenance tasks.

    Handles:
    - Periodic cache cleanup
    - Cache verification against SLURM state
    - Statistics collection
    """

    def __init__(self, cleanup_interval_hours: Optional[int] = None):
        """
        Initialize cache scheduler.

        Args:
            cleanup_interval_hours: Hours between cache cleanup runs
        """
        config = get_cache_config()
        if cleanup_interval_hours is None:
            cleanup_interval_hours = config.cleanup_interval_hours

        self.cleanup_interval = timedelta(hours=cleanup_interval_hours)
        self.cache_middleware = get_cache_middleware()
        self.config = config
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

    async def start(self):
        """Start the background scheduler."""
        if self._running:
            return

        self._running = True
        self._shutdown_event.clear()
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("Cache scheduler started")

    async def stop(self):
        """Stop the background scheduler."""
        if not self._running:
            return

        self._running = False
        self._shutdown_event.set()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        logger.info("Cache scheduler stopped")

    async def _run_scheduler(self):
        """Main scheduler loop."""
        last_cleanup = datetime.now() - self.cleanup_interval  # Force initial cleanup

        while self._running:
            try:
                # Check if cleanup is needed
                if datetime.now() - last_cleanup >= self.cleanup_interval:
                    await self._perform_cleanup()
                    last_cleanup = datetime.now()

                # Wait for next check (or shutdown)
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=3600,  # Check every hour
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    continue  # Normal timeout, continue loop

            except Exception as e:
                logger.error(f"Error in cache scheduler: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def _perform_cleanup(self):
        """Perform cache cleanup operations."""
        try:
            # Skip cleanup if disabled
            if not self.config.auto_cleanup_enabled:
                logger.debug("Scheduled cleanup skipped (auto_cleanup_enabled=false)")
                return

            logger.info("Starting scheduled cache maintenance")

            # Size-based cleanup first (if configured)
            if self.config.max_cache_size_mb > 0:
                size_cleaned = self.cache_middleware.cache.cleanup_by_size(
                    self.config.max_cache_size_mb
                )
                if size_cleaned > 0:
                    logger.info(f"Size-based cleanup: removed {size_cleaned} entries")

            # Age-based cleanup (if configured and enabled)
            if self.config.max_age_days > 0:
                age_cleaned = await self.cache_middleware.cleanup_cache()
                if age_cleaned > 0:
                    logger.info(f"Age-based cleanup: removed {age_cleaned} entries")

            # Get updated stats
            stats = await self.cache_middleware.get_cache_stats()

            logger.info(
                f"Cache maintenance completed: {stats['total_jobs']} jobs, "
                f"{stats['db_size_mb']:.1f}MB"
            )

        except Exception as e:
            logger.error(f"Error during cache maintenance: {e}")

    async def force_cleanup(
        self, max_age_days: Optional[int] = None, preserve_scripts: bool = True
    ) -> int:
        """Force immediate cache cleanup with custom settings."""
        try:
            cleaned_count = 0

            # Age-based cleanup
            if max_age_days is not None and max_age_days >= 0:
                cleaned_count = self.cache_middleware.cache.cleanup_old_entries(
                    max_age_days=max_age_days, preserve_scripts=preserve_scripts
                )

            # Size-based cleanup
            if self.config.max_cache_size_mb > 0:
                size_cleaned = self.cache_middleware.cache.cleanup_by_size(
                    self.config.max_cache_size_mb
                )
                cleaned_count += size_cleaned

            return cleaned_count

        except Exception as e:
            logger.error(f"Error during forced cleanup: {e}")
            return 0


# Global scheduler instance
_scheduler_instance: Optional[CacheScheduler] = None
_scheduler_lock = asyncio.Lock()


async def get_cache_scheduler() -> CacheScheduler:
    """Get or create global cache scheduler instance."""
    global _scheduler_instance

    async with _scheduler_lock:
        if _scheduler_instance is None:
            _scheduler_instance = CacheScheduler()

        return _scheduler_instance


async def start_cache_scheduler():
    """Start the global cache scheduler."""
    scheduler = await get_cache_scheduler()
    await scheduler.start()


async def stop_cache_scheduler():
    """Stop the global cache scheduler."""
    global _scheduler_instance

    if _scheduler_instance:
        await _scheduler_instance.stop()
        _scheduler_instance = None
