"""
Cache middleware for Slurm API endpoints.

This middleware transparently caches job data without modifying existing logic.
"""

import asyncio
from typing import Any, Dict, List, Optional

from ..cache import get_cache
from ..utils.async_helpers import create_task
from ..utils.logging import setup_logger
from .models import JobInfoWeb, JobOutputResponse, JobStatusResponse

logger = setup_logger(__name__)


class CacheMiddleware:
    """
    Middleware that transparently handles caching for job-related API operations.

    This class intercepts API responses and:
    1. Caches job data when retrieved from Slurm
    2. Falls back to cached data when Slurm queries fail
    3. Verifies cache validity against current Slurm state
    """

    def __init__(self):
        self.cache = get_cache()
        # Track UNKNOWN state retry attempts to prevent infinite loops
        # Format: {(job_id, hostname): attempt_count}
        self._unknown_retry_attempts: Dict[tuple[str, str], int] = {}
        # Track failed sacct query attempts to prevent infinite retries
        # Format: {(job_id, hostname): (attempt_count, first_attempt_time)}
        self._failed_sacct_attempts: Dict[tuple[str, str], tuple[int, float]] = {}
        # Maximum retries for failed sacct queries before giving up
        self._MAX_SACCT_RETRIES = 3
        # Maximum time to keep retrying (5 minutes)
        self._MAX_SACCT_RETRY_TIME = 300

        # ⚡ PERFORMANCE: Rate limit cache verification
        # Don't verify more than once every N seconds (configurable via env)
        import os

        self._last_verify_time: float = 0
        self._verify_cooldown_seconds: float = float(
            os.environ.get("SSYNC_CACHE_VERIFY_COOLDOWN", "30")
        )
        self._verify_in_progress: bool = False
        logger.info(
            f"Cache verification cooldown set to {self._verify_cooldown_seconds}s "
            f"(set SSYNC_CACHE_VERIFY_COOLDOWN to adjust)"
        )

    async def cache_job_status_response(
        self,
        responses: List[JobStatusResponse],
        hostname: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        since: Optional[str] = None,
    ) -> List[JobStatusResponse]:
        """
        Cache job status responses and enhance with cached data.

        Args:
            responses: List of JobStatusResponse from Slurm queries
            hostname: Optional hostname for date range caching
            filters: Optional filters for date range caching
            since: Optional since parameter for date range caching

        Returns:
            Enhanced responses with cached data when appropriate
        """
        enhanced_responses = []
        current_job_ids = {}

        for response in responses:
            response_hostname = response.hostname
            current_jobs = []

            current_job_ids[response_hostname] = []
            job_ids_for_range = []

            for job_web in response.jobs:
                job_info = job_web.to_job_info()
                current_job_ids[response_hostname].append(job_info.job_id)
                job_ids_for_range.append(job_info.job_id)

                self.cache.cache_job(job_info)
                current_jobs.append(job_web)

            if hostname and filters and since and response_hostname == hostname:
                # Only cache non-empty results
                # Empty results shouldn't be cached because:
                # 1. They might be transient (jobs haven't been submitted yet)
                # 2. all([]) returns True in Python, causing long TTL for empty results
                # 3. Better to re-query than serve stale empty results
                if current_jobs:
                    # Determine TTL based on job states
                    # Check if all jobs in this response are completed
                    all_completed = all(
                        job_web.state in ["CD", "F", "CA", "TO"]  # Completed states
                        for job_web in current_jobs
                    )

                    if all_completed:
                        # All jobs are completed - cache for a long time
                        ttl_seconds = 86400  # 24 hours
                    else:
                        # Has active/pending jobs - short cache
                        ttl_seconds = 60  # 1 minute

                    self.cache.cache_date_range_query(
                        hostname=hostname,
                        filters=filters,
                        since=since,
                        job_ids=job_ids_for_range,
                        ttl_seconds=ttl_seconds,
                    )
                    logger.info(
                        f"Cached date range for {hostname}: {len(job_ids_for_range)} jobs, "
                        f"TTL={ttl_seconds}s (all_completed={all_completed})"
                    )
                else:
                    logger.debug(
                        f"Skipping cache for {hostname}: empty result (will re-query next time)"
                    )

            enhanced_responses.append(
                JobStatusResponse(
                    hostname=response_hostname,
                    jobs=current_jobs,
                    total_jobs=len(current_jobs),
                    query_time=response.query_time,
                    group_array_jobs=response.group_array_jobs,
                    array_groups=response.array_groups,
                    cached=response.cached if hasattr(response, "cached") else False,
                )
            )

        await self._verify_and_update_cache(current_job_ids)

        return enhanced_responses

    async def check_date_range_cache(
        self, hostname: str, filters: Dict[str, Any], since: str
    ) -> Optional[List[JobInfoWeb]]:
        """
        Check if we have cached jobs for this date range query.

        Args:
            hostname: Hostname to query
            filters: Query filters
            since: Time range parameter

        Returns:
            List of JobInfoWeb if cache hit, None if cache miss
        """
        cached_job_ids = self.cache.check_date_range_cache(hostname, filters, since)

        if cached_job_ids is None:
            return None

        cached_map = self.cache.get_cached_jobs_by_ids(cached_job_ids, hostname)
        cached_jobs = [
            JobInfoWeb.from_job_info(cached.job_info)
            for cached in cached_map.values()
            if cached and cached.job_info
        ]

        if cached_jobs:
            logger.info(
                f"Date range cache HIT: returning {len(cached_jobs)} cached jobs for {hostname}"
            )
            return cached_jobs

        return None

    async def get_job_with_cache_fallback(
        self, job_id: str, hostname: Optional[str] = None
    ) -> Optional[JobInfoWeb]:
        """
        Get job info with cache fallback.

        Args:
            job_id: Job ID to retrieve
            hostname: Optional hostname filter

        Returns:
            JobInfoWeb if found (from Slurm or cache), None otherwise
        """
        cached_job = self.cache.get_cached_jobs_by_ids([job_id], hostname).get(job_id)

        if cached_job:
            logger.debug(f"Found cached job {job_id}")
            return JobInfoWeb.from_job_info(cached_job.job_info)

        return None

    async def cache_job_output(
        self, job_id: str, hostname: str, response: JobOutputResponse
    ):
        """
        Cache job output data.

        Args:
            job_id: Job ID
            hostname: Hostname
            response: JobOutputResponse to cache
        """
        self.cache.update_job_outputs(
            job_id=job_id,
            hostname=hostname,
            stdout_content=response.stdout,
            stderr_content=response.stderr,
        )
        logger.debug(f"Cached output for job {job_id}")

    async def get_cached_job_output(
        self, job_id: str, hostname: Optional[str] = None
    ) -> Optional[JobOutputResponse]:
        """
        Get cached job output.

        Args:
            job_id: Job ID
            hostname: Optional hostname filter

        Returns:
            JobOutputResponse if cached data exists, None otherwise
        """
        cached_job = self.cache.get_cached_jobs_by_ids([job_id], hostname).get(job_id)

        if cached_job and (
            cached_job.stdout_compressed or cached_job.stderr_compressed
        ):
            # Decompress outputs if available
            import gzip

            stdout = None
            stderr = None

            if cached_job.stdout_compressed:
                try:
                    if cached_job.stdout_compression == "gzip":
                        stdout = gzip.decompress(cached_job.stdout_compressed).decode(
                            "utf-8"
                        )
                    else:
                        stdout = cached_job.stdout_compressed.decode("utf-8")
                except Exception as e:
                    logger.error(f"Failed to decompress stdout: {e}")

            if cached_job.stderr_compressed:
                try:
                    if cached_job.stderr_compression == "gzip":
                        stderr = gzip.decompress(cached_job.stderr_compressed).decode(
                            "utf-8"
                        )
                    else:
                        stderr = cached_job.stderr_compressed.decode("utf-8")
                except Exception as e:
                    logger.error(f"Failed to decompress stderr: {e}")

            return JobOutputResponse(
                job_id=job_id,
                hostname=cached_job.hostname,
                stdout=stdout,
                stderr=stderr,
                stdout_metadata=None,  # Metadata not cached currently
                stderr_metadata=None,
            )

        return None

    async def cache_job_script(
        self,
        job_id: str,
        hostname: str,
        script_content: str,
        local_source_dir: Optional[str] = None,
    ):
        """
        Cache job script content and optionally the local source directory.

        Args:
            job_id: Job ID
            hostname: Hostname
            script_content: Script content to cache
            local_source_dir: Optional local source directory that was synced
        """
        # First update the script
        self.cache.update_job_script(job_id, hostname, script_content)

        # Then update the local source dir if provided
        if local_source_dir:
            # Get existing cached job and update with local source dir
            cached = self.cache.get_cached_jobs_by_ids([job_id], hostname).get(job_id)
            if cached:
                self.cache.cache_job(
                    cached.job_info,
                    script_content=script_content,
                    local_source_dir=local_source_dir,
                )

        logger.info(f"Cached script for job {job_id} ({len(script_content)} chars)")

    async def get_cached_job_script(
        self, job_id: str, hostname: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached job script.

        Args:
            job_id: Job ID
            hostname: Optional hostname filter

        Returns:
            Script response dict if cached, None otherwise
        """
        cached_job = self.cache.get_cached_jobs_by_ids([job_id], hostname).get(job_id)

        if cached_job and cached_job.script_content:
            return {
                "job_id": job_id,
                "hostname": cached_job.hostname,
                "script_content": cached_job.script_content,
                "content_length": len(cached_job.script_content),
                "local_source_dir": cached_job.local_source_dir,
            }

        return None

    async def enhance_job_list_with_cache(
        self, hostname: str, current_jobs: List[JobInfoWeb]
    ) -> List[JobInfoWeb]:
        """
        Enhance job list with additional cached jobs that are no longer in Slurm but still relevant.

        Args:
            hostname: Hostname to get cached jobs for
            current_jobs: Current jobs from Slurm

        Returns:
            Enhanced job list with recent cached jobs
        """
        current_job_ids = {job.job_id for job in current_jobs}

        # Get recently cached jobs that aren't in current results
        cached_jobs = self.cache.get_cached_jobs(
            hostname=hostname, active_only=False, limit=100
        )

        enhanced_jobs = list(current_jobs)

        for cached_job in cached_jobs:
            if cached_job.job_id not in current_job_ids:
                # Add recently completed jobs that might be useful
                job_web = JobInfoWeb.from_job_info(cached_job.job_info)
                enhanced_jobs.append(job_web)

        return enhanced_jobs

    async def _verify_and_update_cache(self, current_job_ids: Dict[str, List[str]]):
        """
        Verify cached jobs against current Slurm state and update accordingly.

        ⚡ PERFORMANCE FIX: Rate-limited and runs in background to avoid blocking requests.

        Args:
            current_job_ids: Dict mapping hostname to current job IDs
        """
        import time

        current_time = time.time()
        time_since_last_verify = current_time - self._last_verify_time

        # ⚡ Skip if we verified recently (within cooldown period)
        if time_since_last_verify < self._verify_cooldown_seconds:
            logger.debug(
                f"Skipping cache verification (last verify {time_since_last_verify:.1f}s ago, "
                f"cooldown={self._verify_cooldown_seconds}s)"
            )
            return

        # ⚡ Skip if verification already in progress
        if self._verify_in_progress:
            logger.debug("Cache verification already in progress, skipping")
            return

        # Mark as in progress and update last verify time
        self._verify_in_progress = True
        self._last_verify_time = current_time

        # ⚡ Run verification in background (don't block the request)
        create_task(self._run_verification_in_background(current_job_ids))

    async def _run_verification_in_background(
        self, current_job_ids: Dict[str, List[str]]
    ):
        """Run cache verification in background without blocking requests."""
        try:
            logger.info("🔄 Starting background cache verification")

            # Find jobs that are no longer active
            to_mark_completed = self.cache.verify_cached_jobs(current_job_ids)

            if not to_mark_completed:
                logger.debug("No jobs to mark as completed")
                return

            logger.info(
                f"Found {len(to_mark_completed)} jobs to verify and mark as completed"
            )

            # For jobs being marked as completed:
            # 1. Fetch final state from sacct (ONE LAST TIME)
            # 2. Preserve scripts if possible
            # 3. Mark as inactive (won't be queried again)

            successfully_updated = await self._fetch_final_states_and_preserve(
                to_mark_completed
            )

            # CRITICAL: Only mark jobs as completed if we successfully fetched their final state
            # Jobs that couldn't be updated should remain active so we can retry later
            for job_id, hostname in successfully_updated:
                self.cache.mark_job_completed(job_id, hostname)

            if successfully_updated:
                logger.info(
                    f"✅ Marked {len(successfully_updated)} jobs as completed with final states"
                )

            if len(successfully_updated) < len(to_mark_completed):
                skipped = len(to_mark_completed) - len(successfully_updated)
                logger.info(
                    f"⏭️  Skipped {skipped} jobs - will retry fetching their final state next time"
                )

        except Exception as e:
            logger.error(f"Error in background cache verification: {e}")
        finally:
            self._verify_in_progress = False

    async def _fetch_final_states_and_preserve(
        self, completing_jobs: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        """
        Fetch final states from sacct and preserve scripts for completing jobs.

        This is the "one last check" that ensures we capture the correct final state
        (COMPLETED/CANCELLED/FAILED/TIMEOUT) before marking jobs as inactive.

        Args:
            completing_jobs: List of (job_id, hostname) tuples for jobs being marked as completed

        Returns:
            List of (job_id, hostname) tuples that were successfully updated with final state
        """
        if not completing_jobs:
            return []

        logger.info(
            f"Fetching final states from sacct for {len(completing_jobs)} completing jobs"
        )

        successfully_updated = []

        try:
            from .app import get_slurm_manager

            manager = get_slurm_manager()
            if not manager:
                logger.warning("No manager available for fetching final states")
                return []

            # Group jobs by hostname for efficient processing
            jobs_by_host = {}
            for job_id, hostname in completing_jobs:
                if hostname not in jobs_by_host:
                    jobs_by_host[hostname] = []
                jobs_by_host[hostname].append(job_id)

            # ⚡ PERFORMANCE FIX: Process all hosts in parallel using asyncio.gather
            host_results = await asyncio.gather(
                *[
                    self._fetch_final_states_for_host(manager, hostname, job_ids)
                    for hostname, job_ids in jobs_by_host.items()
                ],
                return_exceptions=True,
            )

            # Collect results from all hosts
            for result in host_results:
                if isinstance(result, Exception):
                    logger.error(f"Error fetching final states from host: {result}")
                else:
                    successfully_updated.extend(result)

        except Exception as e:
            logger.error(f"Error in _fetch_final_states_and_preserve: {e}")

        return successfully_updated

    async def _fetch_final_states_for_host(
        self, manager, hostname: str, job_ids: list[str]
    ) -> list[tuple[str, str]]:
        """
        Fetch final states for all jobs on a single host in parallel.

        Args:
            manager: Slurm manager instance
            hostname: Hostname to fetch from
            job_ids: List of job IDs to fetch

        Returns:
            List of (job_id, hostname) tuples that were successfully updated
        """
        successfully_updated = []

        try:
            slurm_host = manager.get_host_by_name(hostname)
            conn = manager._get_connection(slurm_host.host)

            # ⚡ PERFORMANCE FIX: Fetch all job states in parallel using asyncio.gather
            tasks = [
                self._fetch_single_job_final_state(manager, conn, hostname, job_id)
                for job_id in job_ids
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for job_id, result in zip(job_ids, results):
                if isinstance(result, Exception):
                    logger.warning(f"Error processing job {job_id}: {result}")
                elif result is not None:
                    successfully_updated.append((job_id, hostname))

        except Exception as e:
            logger.error(f"Error processing host {hostname}: {e}")

        return successfully_updated

    async def _fetch_single_job_final_state(
        self, manager, conn, hostname: str, job_id: str
    ) -> Optional[bool]:
        """
        Fetch final state for a single job.

        Args:
            manager: Slurm manager instance
            conn: SSH connection
            hostname: Hostname
            job_id: Job ID to fetch

        Returns:
            True if successfully updated, None otherwise
        """
        try:
            # Check if this job has been stuck in UNKNOWN state
            job_key = (job_id, hostname)
            unknown_attempts = self._unknown_retry_attempts.get(job_key, 0)

            # Skip jobs that have been UNKNOWN too many times (max 3 attempts)
            if unknown_attempts >= 3:
                logger.warning(
                    f"Skipping job {job_id} on {hostname} - stuck in UNKNOWN state after {unknown_attempts} attempts"
                )
                # Clean up the tracking entry
                self._unknown_retry_attempts.pop(job_key, None)
                return None

            # Use thread pool to run blocking Slurm commands
            import asyncio

            from .app import executor

            loop = asyncio.get_event_loop()

            # CRITICAL: Fetch final state from sacct (ONE LAST TIME)
            final_state = await loop.run_in_executor(
                executor,
                manager.slurm_client.get_job_final_state,
                conn,
                hostname,
                job_id,
            )

            if final_state:
                # Check if state is UNKNOWN
                from ..models.job import JobState

                if final_state.state == JobState.UNKNOWN:
                    # Increment retry counter for UNKNOWN jobs
                    self._unknown_retry_attempts[job_key] = unknown_attempts + 1
                    logger.warning(
                        f"Job {job_id} has UNKNOWN state (attempt {unknown_attempts + 1}/3) - will retry"
                    )
                    return None
                else:
                    # Clear retry counter for jobs with known states
                    self._unknown_retry_attempts.pop(job_key, None)

                # Clear failed sacct attempt tracking on success
                self._failed_sacct_attempts.pop(job_key, None)

                # Update cache with correct final state
                logger.info(
                    f"Updating job {job_id} with final state: {final_state.state.value}"
                )

                # Get existing cached job to preserve script if already cached
                cached_job = self.cache.get_cached_jobs_by_ids([job_id], hostname).get(
                    job_id
                )
                script_content = cached_job.script_content if cached_job else None

                # Try to fetch script if not already cached
                if not script_content:
                    try:
                        script_content = await loop.run_in_executor(
                            executor,
                            manager.slurm_client.get_job_batch_script,
                            conn,
                            job_id,
                            hostname,
                        )
                        if script_content:
                            logger.info(
                                f"Preserved script for job {job_id} ({len(script_content)} chars)"
                            )
                    except Exception as e:
                        logger.debug(f"Could not fetch script for job {job_id}: {e}")

                # Update cache with final state and script
                self.cache.cache_job(final_state, script_content=script_content)

                return True
            else:
                # ⚡ PERFORMANCE FIX: Track failed attempts and give up after max retries
                import time

                job_key = (job_id, hostname)

                if job_key in self._failed_sacct_attempts:
                    attempts, first_attempt = self._failed_sacct_attempts[job_key]
                    attempts += 1
                    time_elapsed = time.time() - first_attempt
                else:
                    attempts = 1
                    first_attempt = time.time()
                    time_elapsed = 0

                self._failed_sacct_attempts[job_key] = (attempts, first_attempt)

                # Give up after max retries or max time
                if (
                    attempts >= self._MAX_SACCT_RETRIES
                    or time_elapsed >= self._MAX_SACCT_RETRY_TIME
                ):
                    logger.warning(
                        f"Giving up on job {job_id} after {attempts} failed sacct attempts "
                        f"({time_elapsed:.0f}s elapsed). Marking as completed with UNKNOWN state."
                    )
                    # Mark as completed anyway to stop retrying
                    # Use the cached job info if available, otherwise create minimal entry
                    cached_job = self.cache.get_cached_jobs_by_ids(
                        [job_id], hostname
                    ).get(job_id)
                    if cached_job and cached_job.job_info:
                        # Update to UNKNOWN state
                        from ..models.job import JobState

                        cached_job.job_info.state = JobState.UNKNOWN
                        self.cache.cache_job(
                            cached_job.job_info,
                            script_content=cached_job.script_content,
                        )

                    # Clean up retry tracking
                    self._failed_sacct_attempts.pop(job_key, None)
                    return (
                        True  # Mark as successfully handled so it gets marked completed
                    )
                else:
                    logger.warning(
                        f"Could not fetch final state for job {job_id} from sacct "
                        f"(attempt {attempts}/{self._MAX_SACCT_RETRIES}) - will retry next time"
                    )
                    return None

        except Exception as e:
            logger.warning(f"Error processing completing job {job_id}: {e}")
            return None

    async def _preserve_scripts_for_completing_jobs(
        self, completing_jobs: list[tuple[str, str]]
    ):
        """
        Try to retrieve and cache scripts for jobs that are completing.

        Args:
            completing_jobs: List of (job_id, hostname) tuples for jobs being marked as completed
        """
        if not completing_jobs:
            return

        logger.debug(
            f"Attempting to preserve scripts for {len(completing_jobs)} completing jobs"
        )

        # Import here to avoid circular imports

        try:
            # Group jobs by hostname for efficient querying
            jobs_by_host = {}
            for job_id, hostname in completing_jobs:
                if hostname not in jobs_by_host:
                    jobs_by_host[hostname] = []
                jobs_by_host[hostname].append(job_id)

            # Try to get scripts for each host
            for hostname, job_ids in jobs_by_host.items():
                cached_map = self.cache.get_cached_jobs_by_ids(job_ids, hostname)
                for job_id in job_ids:
                    # Check if we already have the script cached
                    cached_job = cached_map.get(job_id)
                    if cached_job and cached_job.script_content:
                        logger.debug(f"Script already cached for job {job_id}")
                        continue

                    # Try to get script from Slurm before it's completely gone
                    try:
                        # Import here to avoid circular imports
                        from .app import get_slurm_manager

                        manager = get_slurm_manager()
                        if manager:
                            slurm_host = manager.get_host_by_name(hostname)
                            conn = manager._get_connection(slurm_host.host)

                            script_content = manager.slurm_client.get_job_batch_script(
                                conn, job_id, hostname
                            )
                            if script_content:
                                self.cache.update_job_script(
                                    job_id, hostname, script_content
                                )
                                logger.info(
                                    f"Preserved script for completing job {job_id}"
                                )
                            else:
                                logger.debug(
                                    f"No script content found for job {job_id} in Slurm"
                                )
                        else:
                            logger.debug(
                                f"No manager available for script preservation of job {job_id}"
                            )

                    except Exception as e:
                        logger.warning(
                            f"Failed to preserve script for job {job_id}: {e}"
                        )

        except Exception as e:
            logger.warning(f"Error preserving scripts for completing jobs: {e}")

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics including failed sacct retry tracking."""
        stats = self.cache.get_cache_stats()

        # Add middleware-specific stats
        stats["middleware"] = {
            "failed_sacct_retries": len(self._failed_sacct_attempts),
            "unknown_state_retries": len(self._unknown_retry_attempts),
            "failed_jobs": [
                {
                    "job_id": job_id,
                    "hostname": hostname,
                    "attempts": attempts,
                    "elapsed_seconds": int(__import__("time").time() - first_attempt),
                }
                for (job_id, hostname), (
                    attempts,
                    first_attempt,
                ) in self._failed_sacct_attempts.items()
            ],
        }

        return stats

    async def cleanup_cache(self, max_age_days: Optional[int] = None) -> int:
        """
        Perform cache cleanup.

        Args:
            max_age_days: Override default max age

        Returns:
            Number of entries cleaned up
        """
        return self.cache.cleanup_old_entries(max_age_days)


# Global middleware instance
_middleware_instance: Optional[CacheMiddleware] = None


def get_cache_middleware() -> CacheMiddleware:
    """Get or create global cache middleware instance."""
    global _middleware_instance

    if _middleware_instance is None:
        _middleware_instance = CacheMiddleware()

    return _middleware_instance
