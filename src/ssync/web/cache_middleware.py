"""
Cache middleware for SLURM API endpoints.

This middleware transparently caches job data without modifying existing logic.
"""

from datetime import datetime
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
        self, responses: List[JobStatusResponse]
    ) -> List[JobStatusResponse]:
        """
        Cache job status responses and enhance with cached data.

        Args:
            responses: List of JobStatusResponse from SLURM queries

        Returns:
            Enhanced responses with cached data when appropriate
        """
        enhanced_responses = []
        current_job_ids = {}

        for response in responses:
            hostname = response.hostname
            current_jobs = []

            # Cache current jobs
            current_job_ids[hostname] = []
            for job_web in response.jobs:
                job_info = job_web.to_job_info()
                current_job_ids[hostname].append(job_info.job_id)

                # Cache the job data
                self.cache.cache_job(job_info)
                current_jobs.append(job_web)

            enhanced_responses.append(
                JobStatusResponse(
                    hostname=hostname,
                    jobs=current_jobs,
                    total_jobs=len(current_jobs),
                    query_time=response.query_time,
                )
            )

        # Verify cached jobs and mark completed ones
        await self._verify_and_update_cache(current_job_ids)

        return enhanced_responses

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
        # First check cache
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

        if cached_job and (cached_job.stdout_content or cached_job.stderr_content):
            return JobOutputResponse(
                job_id=job_id,
                hostname=cached_job.hostname,
                stdout=cached_job.stdout_content,
                stderr=cached_job.stderr_content,
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
        # Update existing cache entry or cache script separately
        cached_job = self.cache.get_cached_job(job_id, hostname)
        if cached_job:
            # Update script in existing cache entry
            cached_job.script_content = script_content
            self.cache._store_cached_data(cached_job)
        else:
            # We might not have the job info yet - just update the field
            with self.cache._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE cached_jobs 
                    SET script_content = ?, last_updated = ?
                    WHERE job_id = ? AND hostname = ?
                """,
                    (script_content, datetime.now().isoformat(), job_id, hostname),
                )
                conn.commit()

        logger.debug(f"Cached script for job {job_id}")

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
            hostname=hostname, active_only=False, limit=50
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

            # Mark them as completed
            for job_id, hostname in to_mark_completed:
                self.cache.mark_job_completed(job_id, hostname)

            if to_mark_completed:
                logger.info(
                    f"Marked {len(to_mark_completed)} jobs as completed based on SLURM state"
                )

        except Exception as e:
            logger.error(f"Error verifying cache: {e}")

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
