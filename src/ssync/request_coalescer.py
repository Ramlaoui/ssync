"""
Request Coalescing - Batch multiple individual job requests into efficient bulk queries.

This prevents thread pool saturation when many individual job requests arrive simultaneously
(e.g., when user has 30+ job WebSocket connections open).
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta

from .models.job import JobInfo
from .utils.logging import setup_logger
from .utils.async_helpers import background_tasks_disabled, create_task

logger = setup_logger(__name__)


@dataclass
class JobRequest:
    """Represents a pending job fetch request."""
    job_id: str
    hostname: str
    future: asyncio.Future
    timestamp: datetime


class JobRequestCoalescer:
    """
    Coalesces multiple individual job requests into batched bulk queries.

    When many individual job requests arrive simultaneously (e.g., 30 WebSocket
    connections each fetching a single job), this coalescer:

    1. Collects requests for a short time window (50-100ms)
    2. Groups requests by hostname
    3. Executes ONE bulk query per host instead of N individual queries
    4. Distributes results back to waiting requests

    This reduces thread pool usage from N to 1-5 queries (one per host).
    """

    def __init__(self, batch_window_ms: int = 100, max_batch_size: int = 50):
        """
        Initialize the coalescer.

        Args:
            batch_window_ms: Time to wait for more requests before executing (default 100ms)
            max_batch_size: Maximum jobs per batch (executes immediately when reached)
        """
        self.batch_window_ms = batch_window_ms
        self.max_batch_size = max_batch_size

        # Pending requests grouped by hostname
        self.pending: Dict[str, Dict[str, JobRequest]] = defaultdict(dict)  # hostname -> {job_id -> request}

        # Batch execution tasks
        self.batch_tasks: Dict[str, asyncio.Task] = {}  # hostname -> task

        # Lock for thread-safe access
        self.lock = asyncio.Lock()

        # Stats
        self.stats = {
            'total_requests': 0,
            'batched_requests': 0,
            'queries_saved': 0,  # Individual queries that were batched
            'batches_executed': 0,
        }

    async def fetch_job(
        self,
        job_id: str,
        hostname: str,
        fetch_func
    ) -> Optional[JobInfo]:
        """
        Request a job fetch. Will be automatically coalesced with other concurrent requests.

        Args:
            job_id: Job ID to fetch
            hostname: Hostname where job is running
            fetch_func: Async function that takes (hostname, job_ids: List[str]) and returns List[JobInfo]

        Returns:
            JobInfo if found, None otherwise
        """
        if background_tasks_disabled():
            jobs = await fetch_func(hostname, [job_id])
            return jobs[0] if jobs else None

        async with self.lock:
            self.stats['total_requests'] += 1

            # Check if request already pending for this job
            if job_id in self.pending[hostname]:
                logger.debug(f"Job {job_id} on {hostname} already has pending request, reusing")
                return await self.pending[hostname][job_id].future

            # Create new request
            future = asyncio.Future()
            request = JobRequest(
                job_id=job_id,
                hostname=hostname,
                future=future,
                timestamp=datetime.now()
            )
            self.pending[hostname][job_id] = request

            # Schedule batch execution if not already scheduled
            if hostname not in self.batch_tasks or self.batch_tasks[hostname].done():
                self.batch_tasks[hostname] = create_task(
                    self._execute_batch_after_delay(hostname, fetch_func)
                )

            # Check if we've reached max batch size - execute immediately
            pending_count = len(self.pending[hostname])
            if pending_count >= self.max_batch_size:
                logger.info(
                    f"Max batch size ({self.max_batch_size}) reached for {hostname}, "
                    f"executing batch immediately"
                )
                # Cancel the delayed task and execute now
                if not self.batch_tasks[hostname].done():
                    self.batch_tasks[hostname].cancel()
                self.batch_tasks[hostname] = create_task(
                    self._execute_batch(hostname, fetch_func)
                )

        # Wait for result outside the lock
        return await future

    async def _execute_batch_after_delay(self, hostname: str, fetch_func):
        """Wait for the batch window, then execute the batch."""
        await asyncio.sleep(self.batch_window_ms / 1000.0)
        await self._execute_batch(hostname, fetch_func)

    async def _execute_batch(self, hostname: str, fetch_func):
        """Execute a batch of pending requests for a hostname."""
        async with self.lock:
            # Get all pending requests for this host
            requests = self.pending[hostname]
            if not requests:
                return

            # Clear pending requests
            self.pending[hostname] = {}

            job_ids = list(requests.keys())
            request_count = len(job_ids)

            self.stats['batches_executed'] += 1
            self.stats['batched_requests'] += request_count
            if request_count > 1:
                self.stats['queries_saved'] += request_count - 1

            logger.info(
                f"🚀 Coalescing {request_count} individual job requests into 1 bulk query for {hostname} "
                f"(saved {request_count - 1} SSH operations)"
            )

        # Execute the bulk fetch (outside lock to avoid blocking)
        try:
            jobs = await fetch_func(hostname, job_ids)

            # Create a lookup map
            job_map = {job.job_id: job for job in jobs}

            # Distribute results to waiting requests
            for job_id, request in requests.items():
                if not request.future.done():
                    job = job_map.get(job_id)
                    request.future.set_result(job)
                    if job:
                        logger.debug(f"✓ Resolved job {job_id} from batch")
                    else:
                        logger.debug(f"✗ Job {job_id} not found in batch results")

        except Exception as e:
            logger.error(f"Batch fetch failed for {hostname}: {e}")
            # Propagate error to all waiting requests
            for request in requests.values():
                if not request.future.done():
                    request.future.set_exception(e)

    def get_stats(self) -> dict:
        """Get coalescing statistics."""
        if self.stats['total_requests'] == 0:
            efficiency = 0.0
        else:
            efficiency = (self.stats['queries_saved'] / self.stats['total_requests']) * 100

        return {
            **self.stats,
            'efficiency_percent': round(efficiency, 1),
            'pending_count': sum(len(reqs) for reqs in self.pending.values()),
        }


# Global coalescer instance
_coalescer: Optional[JobRequestCoalescer] = None


def get_request_coalescer() -> JobRequestCoalescer:
    """Get or create the global request coalescer."""
    global _coalescer
    if _coalescer is None:
        _coalescer = JobRequestCoalescer(batch_window_ms=100, max_batch_size=50)
        logger.info("Initialized global request coalescer (batch_window=100ms, max_batch=50)")
    return _coalescer
