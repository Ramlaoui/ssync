"""
Request coalescing for individual job lookups.

Requests are grouped into short per-host batches. A host has one draining
worker at a time, so requests arriving while a fetch is in flight are picked
up by the same worker instead of being left behind behind a completed task.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from .models.job import JobInfo
from .utils.async_helpers import background_tasks_disabled, create_task
from .utils.executors import WorkQueueFull
from .utils.logging import setup_logger

logger = setup_logger(__name__)


@dataclass
class JobRequest:
    """Represents one unique pending or in-flight job fetch."""

    job_id: str
    hostname: str
    future: asyncio.Future
    timestamp: datetime


class JobRequestCoalescer:
    """Coalesce concurrent job requests into bounded per-host bulk fetches."""

    def __init__(
        self,
        batch_window_ms: int = 100,
        max_batch_size: int = 50,
        max_outstanding_jobs: int = 256,
    ):
        if batch_window_ms < 0:
            raise ValueError("batch_window_ms must be non-negative")
        if max_batch_size <= 0:
            raise ValueError("max_batch_size must be positive")
        if max_outstanding_jobs <= 0:
            raise ValueError("max_outstanding_jobs must be positive")

        self.batch_window_ms = batch_window_ms
        self.max_batch_size = max_batch_size
        self.max_outstanding_jobs = max_outstanding_jobs

        # Requests not yet handed to fetch_func, grouped by host. Keep these
        # separate from in_flight so arrivals during a fetch are visible to the
        # already-running worker.
        self.pending: Dict[str, Dict[str, JobRequest]] = defaultdict(dict)
        self.in_flight: Dict[str, Dict[str, JobRequest]] = defaultdict(dict)
        self.batch_tasks: Dict[str, asyncio.Task] = {}

        # All mutations happen on the event-loop thread, but retain the lock as
        # part of the small public compatibility surface used by callers/tests.
        self.lock = asyncio.Lock()

        self.stats = {
            "total_requests": 0,
            "batched_requests": 0,
            "queries_saved": 0,
            "batches_executed": 0,
        }

    def _outstanding_count(self) -> int:
        return sum(
            len(requests)
            for requests in (*self.pending.values(), *self.in_flight.values())
        )

    async def fetch_job(
        self, job_id: str, hostname: str, fetch_func
    ) -> Optional[JobInfo]:
        """Request one job and await its coalesced result.

        ``shield`` is required here: cancelling one websocket/request waiter
        must not cancel the shared Future used by other waiters for the same
        job.
        """
        if background_tasks_disabled():
            jobs = await fetch_func(hostname, [job_id])
            return jobs[0] if jobs else None

        async with self.lock:
            self.stats["total_requests"] += 1

            request = self.pending.get(hostname, {}).get(job_id)
            if request is None:
                request = self.in_flight.get(hostname, {}).get(job_id)

            if request is None:
                if self._outstanding_count() >= self.max_outstanding_jobs:
                    raise WorkQueueFull(
                        "job request coalescer is at capacity "
                        f"({self.max_outstanding_jobs} unique jobs)"
                    )

                request = JobRequest(
                    job_id=job_id,
                    hostname=hostname,
                    future=asyncio.get_running_loop().create_future(),
                    timestamp=datetime.now(),
                )
                request.future.add_done_callback(
                    lambda done: done.exception() if not done.cancelled() else None
                )
                self.pending[hostname][job_id] = request

            worker = self.batch_tasks.get(hostname)
            if worker is None or worker.done():
                worker = create_task(
                    self._drain_host(hostname, fetch_func),
                    name=f"job-request-batch:{hostname}",
                )
                if worker is None:
                    # This is only possible if the environment changed the
                    # background-task setting between the bypass check and
                    # create_task. Avoid leaving a Future permanently pending.
                    self.pending.get(hostname, {}).pop(job_id, None)
                    if not self.pending.get(hostname):
                        self.pending.pop(hostname, None)
                    raise RuntimeError("could not create request coalescer worker")
                self.batch_tasks[hostname] = worker

            future = request.future

        # A cancelled waiter leaves the shared future and worker alive. The
        # worker will still resolve it for any other waiter and clean it up.
        return await asyncio.shield(future)

    async def _drain_host(self, hostname: str, fetch_func) -> None:
        """Drain all requests for one host, in batches of max_batch_size."""
        worker = asyncio.current_task()
        cancelled = False
        try:
            while True:
                # Preserve the coalescing window for each batch. A new request
                # arriving during fetch_func is therefore collected briefly
                # before the next bounded SSH query.
                await asyncio.sleep(self.batch_window_ms / 1000.0)
                async with self.lock:
                    host_pending = self.pending.get(hostname)
                    if not host_pending:
                        if self.batch_tasks.get(hostname) is worker:
                            self.batch_tasks.pop(hostname, None)
                        self.pending.pop(hostname, None)
                        self.in_flight.pop(hostname, None)
                        return

                    selected_ids = list(host_pending)[: self.max_batch_size]
                    requests = {
                        job_id: host_pending.pop(job_id) for job_id in selected_ids
                    }
                    if not host_pending:
                        self.pending.pop(hostname, None)
                    self.in_flight[hostname].update(requests)

                    job_ids = list(requests)
                    request_count = len(job_ids)
                    self.stats["batches_executed"] += 1
                    self.stats["batched_requests"] += request_count
                    if request_count > 1:
                        self.stats["queries_saved"] += request_count - 1

                logger.info(
                    "Coalescing %s individual job requests into 1 bulk query for %s "
                    "(saved %s SSH operations)",
                    request_count,
                    hostname,
                    request_count - 1,
                )

                try:
                    jobs = await fetch_func(hostname, job_ids)
                    job_map = {job.job_id: job for job in jobs}
                except asyncio.CancelledError:
                    # Worker cancellation is a shutdown/error boundary. Do
                    # not leave either in-flight or newly pending callers
                    # waiting forever.
                    async with self.lock:
                        self._cleanup_host_requests(hostname)
                        cancelled = True
                    raise
                except BaseException as exc:
                    async with self.lock:
                        self._finish_host_requests(hostname, requests, exception=exc)
                else:
                    async with self.lock:
                        self._finish_host_requests(hostname, requests, job_map=job_map)
                # Loop immediately: requests arriving while fetch_func ran are
                # in pending and must be drained without another caller.
        except asyncio.CancelledError:
            cancelled = True
            raise
        except BaseException as exc:
            # Unexpected worker failures (for example malformed fetch results)
            # must resolve every waiter and release the host maps as well.
            async with self.lock:
                self._finish_host_requests(
                    hostname,
                    {
                        **self.pending.get(hostname, {}),
                        **self.in_flight.get(hostname, {}),
                    },
                    exception=exc,
                )
                self.pending.pop(hostname, None)
                self.in_flight.pop(hostname, None)
            raise
        finally:
            # A cancellation while acquiring the lock or during another await
            # still needs to release every request owned by this worker.
            if cancelled or (worker is not None and worker.cancelled()):
                async with self.lock:
                    self._cleanup_host_requests(hostname)
                    if self.batch_tasks.get(hostname) is worker:
                        self.batch_tasks.pop(hostname, None)
                    self.pending.pop(hostname, None)
                    self.in_flight.pop(hostname, None)

    def _finish_host_requests(
        self,
        hostname: str,
        requests: Dict[str, JobRequest],
        *,
        job_map: Optional[Dict[str, JobInfo]] = None,
        exception: Optional[BaseException] = None,
    ) -> None:
        in_flight = self.in_flight.get(hostname)
        for job_id, request in requests.items():
            if in_flight is not None:
                in_flight.pop(job_id, None)
            if request.future.done():
                continue
            if exception is not None:
                request.future.set_exception(exception)
            else:
                request.future.set_result(job_map.get(job_id))
        if in_flight is not None and not in_flight:
            self.in_flight.pop(hostname, None)

    def _cancel_host_requests(
        self,
        hostname: str,
        requests: Optional[Dict[str, JobRequest]] = None,
    ) -> None:
        owned = requests or {}
        if requests is None:
            owned = {
                **self.pending.get(hostname, {}),
                **self.in_flight.get(hostname, {}),
            }
        for request in owned.values():
            if not request.future.done():
                request.future.cancel()

    def _cleanup_host_requests(self, hostname: str) -> None:
        """Cancel and remove all requests owned by a failed host worker."""
        self._cancel_host_requests(hostname)
        self.pending.pop(hostname, None)
        self.in_flight.pop(hostname, None)

    def get_stats(self) -> dict:
        """Get coalescing statistics and bounded queue occupancy."""
        if self.stats["total_requests"] == 0:
            efficiency = 0.0
        else:
            efficiency = (
                self.stats["queries_saved"] / self.stats["total_requests"]
            ) * 100

        return {
            **self.stats,
            "efficiency_percent": round(efficiency, 1),
            "pending_count": sum(len(reqs) for reqs in self.pending.values()),
            "in_flight_count": sum(len(reqs) for reqs in self.in_flight.values()),
            "outstanding_count": self._outstanding_count(),
        }

    async def close(self) -> None:
        """Cancel workers and settle all waiters during application shutdown."""
        async with self.lock:
            workers = list(self.batch_tasks.values())
            self._cleanup_all_requests()
            self.batch_tasks.clear()
            for worker in workers:
                if not worker.done():
                    worker.cancel()

        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

    async def shutdown(self) -> None:
        """Compatibility alias for lifespan shutdown hooks."""
        await self.close()

    def _cleanup_all_requests(self) -> None:
        for hostname in set(self.pending) | set(self.in_flight):
            self._cancel_host_requests(hostname)
        self.pending.clear()
        self.in_flight.clear()


# Global coalescer instance
_coalescer: Optional[JobRequestCoalescer] = None


def get_request_coalescer() -> JobRequestCoalescer:
    """Get or create the global request coalescer."""
    global _coalescer
    if _coalescer is None:
        _coalescer = JobRequestCoalescer(
            batch_window_ms=100,
            max_batch_size=50,
            max_outstanding_jobs=256,
        )
        logger.info(
            "Initialized global request coalescer (batch_window=100ms, max_batch=50)"
        )
    return _coalescer
