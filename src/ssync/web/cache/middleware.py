"""
Cache middleware compatibility layer for Slurm API endpoints.
"""

import os
from typing import Any, Dict, List, Optional

from ...cache import get_cache
from ...models.job import JobInfo, JobState
from ..models import JobInfoWeb, JobOutputResponse, JobStatusResponse
from .responses import (
    CacheResponseService,
)
from .responses import (
    cache_job_state_transition as _cache_job_state_transition,
)
from .verifier import CacheVerificationService


class CacheMiddleware:
    """
    Compatibility facade for cache-backed web helpers.

    This keeps the old singleton and method surface while delegating the
    implementation to smaller focused services.
    """

    def __init__(self):
        self.cache = get_cache()
        recent_active_cache_ttl_seconds = float(
            os.environ.get("SSYNC_RECENT_ACTIVE_CACHE_TTL_SECONDS", "300")
        )
        self._responses = CacheResponseService(
            self.cache,
            recent_active_cache_ttl_seconds=recent_active_cache_ttl_seconds,
        )
        self._verifier = CacheVerificationService(self.cache)

    async def cache_job_status_response(
        self,
        responses: List[JobStatusResponse],
        hostname: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        since: Optional[str] = None,
        verify_active_jobs: bool = False,
    ) -> List[JobStatusResponse]:
        enhanced_responses = await self._responses.cache_job_status_response(
            responses,
            hostname=hostname,
            filters=filters,
            since=since,
        )
        if verify_active_jobs:
            current_job_ids = {
                response.hostname: [job.job_id for job in response.jobs]
                for response in responses
            }
            await self._verify_and_update_cache(current_job_ids)
        return enhanced_responses

    async def check_date_range_cache(
        self, hostname: str, filters: Dict[str, Any], since: str
    ) -> Optional[List[JobInfoWeb]]:
        return await self._responses.check_date_range_cache(hostname, filters, since)

    async def get_job_with_cache_fallback(
        self,
        job_id: str,
        hostname: Optional[str] = None,
        *,
        allow_stale_active: bool = False,
    ) -> Optional[JobInfoWeb]:
        return await self._responses.get_job_with_cache_fallback(
            job_id,
            hostname,
            allow_stale_active=allow_stale_active,
        )

    async def cache_job_output(
        self, job_id: str, hostname: str, response: JobOutputResponse
    ):
        await self._responses.cache_job_output(job_id, hostname, response)

    async def get_cached_job_output(
        self, job_id: str, hostname: Optional[str] = None
    ) -> Optional[JobOutputResponse]:
        return await self._responses.get_cached_job_output(job_id, hostname)

    async def cache_job_script(
        self,
        job_id: str,
        hostname: str,
        script_content: str,
        local_source_dir: Optional[str] = None,
    ):
        await self._responses.cache_job_script(
            job_id,
            hostname,
            script_content,
            local_source_dir=local_source_dir,
        )

    async def get_cached_job_script(
        self, job_id: str, hostname: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        return await self._responses.get_cached_job_script(job_id, hostname)

    async def _verify_and_update_cache(self, current_job_ids: Dict[str, List[str]]):
        await self._verifier.verify_and_update_cache(current_job_ids)

    async def get_cache_stats(self) -> Dict[str, Any]:
        stats = self.cache.get_cache_stats()
        return self._verifier.extend_stats(stats)

    async def cleanup_cache(self, max_age_days: Optional[int] = None) -> int:
        return self.cache.cleanup_old_entries(max_age_days)


_middleware_instance: Optional[CacheMiddleware] = None


def get_cache_middleware() -> CacheMiddleware:
    """Get or create global cache middleware instance."""
    global _middleware_instance

    if _middleware_instance is None:
        _middleware_instance = CacheMiddleware()

    return _middleware_instance


def cache_job_state_transition(
    job_id: str,
    hostname: str,
    state: JobState,
    *,
    job_name: Optional[str] = None,
    reason: Optional[str] = None,
    array_submission: bool = False,
) -> tuple[JobInfo, Optional[JobState]]:
    """Persist an immediate job state transition in cache."""
    return _cache_job_state_transition(
        get_cache_middleware().cache,
        job_id,
        hostname,
        state,
        job_name=job_name,
        reason=reason,
        array_submission=array_submission,
    )
