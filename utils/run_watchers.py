#!/usr/bin/env python
"""
Run watchers for existing jobs in the database.
This script maintains an event loop to keep watchers running.
"""

import asyncio
import signal
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import logging

from ssync.cache import get_cache
from ssync.watchers import get_watcher_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_existing_watchers():
    """Start monitoring for all active watchers in the database."""
    engine = get_watcher_engine()
    cache = get_cache()

    # Keep running until interrupted
    try:
        last_check_time = None
        check_interval = 5  # Check for new watchers every 5 seconds

        while True:
            # Check for new watchers periodically
            with cache._get_connection() as conn:
                # Get all active watchers that aren't already being monitored
                cursor = conn.execute("""
                    SELECT id, job_id, hostname
                    FROM job_watchers
                    WHERE state = 'active'
                """)
                all_watchers = cursor.fetchall()

            # Start monitoring for any new watchers
            new_watchers_started = 0
            for row in all_watchers:
                watcher_id = row["id"]
                job_id = row["job_id"]
                hostname = row["hostname"]

                # Skip if already monitoring
                if (
                    watcher_id in engine.active_tasks
                    and not engine.active_tasks[watcher_id].done()
                ):
                    continue

                # Start monitoring this watcher
                logger.info(f"Starting monitor for watcher {watcher_id} (job {job_id})")
                task = asyncio.create_task(
                    engine._monitor_watcher(watcher_id, job_id, hostname)
                )
                engine.active_tasks[watcher_id] = task
                new_watchers_started += 1

            if new_watchers_started > 0:
                logger.info(f"Started {new_watchers_started} new monitoring tasks")

            # Remove completed tasks
            completed = []
            for watcher_id, task in engine.active_tasks.items():
                if task.done():
                    completed.append(watcher_id)
                    # Log any exceptions from the task
                    try:
                        task.result()
                    except Exception as e:
                        logger.error(f"Watcher {watcher_id} failed with error: {e}")

            for watcher_id in completed:
                del engine.active_tasks[watcher_id]
                logger.info(f"Watcher {watcher_id} completed")

            # Also run cleanup and health check periodically
            if (
                last_check_time is None
                or (asyncio.get_event_loop().time() - last_check_time) > 30
            ):
                logger.debug("Running periodic cleanup and health check")
                await engine.cleanup_orphaned_watchers()
                await engine.check_and_restart_watchers()
                last_check_time = asyncio.get_event_loop().time()

            # Sleep before next check
            await asyncio.sleep(check_interval)

    except asyncio.CancelledError:
        logger.info("Shutting down watcher service")
        # Cancel all tasks
        for task in engine.active_tasks.values():
            task.cancel()
        await asyncio.gather(*engine.active_tasks.values(), return_exceptions=True)


async def main():
    """Main entry point."""
    logger.info("Starting watcher service...")

    # Handle shutdown signals
    loop = asyncio.get_running_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        for task in asyncio.all_tasks():
            task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await run_existing_watchers()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Watcher service stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
