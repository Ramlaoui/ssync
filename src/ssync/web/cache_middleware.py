"""
Cache middleware for SLURM API endpoints.

This middleware transparently caches job data without modifying existing logic.
"""

from typing import Any, Dict, List, Optional

from ..cache import get_cache
from ..utils.logging import setup_logger
from .models import JobInfoWeb, JobOutputResponse, JobStatusResponse

logger = setup_logger(__name__)


class CacheMiddleware:
    """
    Middleware that transparently handles caching for job-related API operations.

    This class intercepts API responses and:
    1. Caches job data when retrieved from SLURM
    2. Falls back to cached data when SLURM queries fail
    3. Verifies cache validity against current SLURM state
    """

    def __init__(self):
        self.cache = get_cache()

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
            responses: List of JobStatusResponse from SLURM queries
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

            enhanced_responses.append(
                JobStatusResponse(
                    hostname=response_hostname,
                    jobs=current_jobs,
                    total_jobs=len(current_jobs),
                    query_time=response.query_time,
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

        cached_jobs = []
        for job_id in cached_job_ids:
            cached_job = self.cache.get_cached_job(job_id, hostname)
            if cached_job:
                cached_jobs.append(JobInfoWeb.from_job_info(cached_job.job_info))

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
            JobInfoWeb if found (from SLURM or cache), None otherwise
        """
        cached_job = self.cache.get_cached_job(job_id, hostname)

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
        cached_job = self.cache.get_cached_job(job_id, hostname)

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

    async def cache_job_script(self, job_id: str, hostname: str, script_content: str):
        """
        Cache job script content.

        Args:
            job_id: Job ID
            hostname: Hostname
            script_content: Script content to cache
        """
        # Use the efficient update_job_script method which handles both update and create
        self.cache.update_job_script(job_id, hostname, script_content)
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
        cached_job = self.cache.get_cached_job(job_id, hostname)

        if cached_job and cached_job.script_content:
            return {
                "job_id": job_id,
                "hostname": cached_job.hostname,
                "script_content": cached_job.script_content,
                "content_length": len(cached_job.script_content),
            }

        return None

    async def enhance_job_list_with_cache(
        self, hostname: str, current_jobs: List[JobInfoWeb]
    ) -> List[JobInfoWeb]:
        """
        Enhance job list with additional cached jobs that are no longer in SLURM but still relevant.

        Args:
            hostname: Hostname to get cached jobs for
            current_jobs: Current jobs from SLURM

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
        Verify cached jobs against current SLURM state and update accordingly.

        Args:
            current_job_ids: Dict mapping hostname to current job IDs
        """
        try:
            # Find jobs that are no longer active
            to_mark_completed = self.cache.verify_cached_jobs(current_job_ids)

            # For jobs being marked as completed, try to preserve their scripts
            await self._preserve_scripts_for_completing_jobs(to_mark_completed)

            # Mark them as completed
            for job_id, hostname in to_mark_completed:
                self.cache.mark_job_completed(job_id, hostname)

            if to_mark_completed:
                logger.info(
                    f"Marked {len(to_mark_completed)} jobs as completed based on SLURM state"
                )

        except Exception as e:
            logger.error(f"Error verifying cache: {e}")

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
                for job_id in job_ids:
                    # Check if we already have the script cached
                    cached_job = self.cache.get_cached_job(job_id, hostname)
                    if cached_job and cached_job.script_content:
                        logger.debug(f"Script already cached for job {job_id}")
                        continue

                    # Try to get script from SLURM before it's completely gone
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
                                    f"No script content found for job {job_id} in SLURM"
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
        """Get cache statistics."""
        return self.cache.get_cache_stats()

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
