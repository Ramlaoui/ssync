"""Cache-backed response helpers for the web API."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ...models.job import JobInfo, JobState
from ...utils.logging import setup_logger
from ..models import JobInfoWeb, JobOutputResponse, JobStatusResponse

logger = setup_logger(__name__)


class CacheResponseService:
    """Cache read/write helpers used by web endpoints."""

    def __init__(self, cache, *, recent_active_cache_ttl_seconds: float):
        self.cache = cache
        self._recent_active_cache_ttl_seconds = recent_active_cache_ttl_seconds

    async def cache_job_status_response(
        self,
        responses: List[JobStatusResponse],
        hostname: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        since: Optional[str] = None,
    ) -> List[JobStatusResponse]:
        enhanced_responses = []

        for response in responses:
            response_hostname = response.hostname
            current_jobs = []
            job_ids_for_range = []

            for job_web in response.jobs:
                job_info = job_web.to_job_info()
                job_ids_for_range.append(job_info.job_id)
                self.cache.cache_job(job_info)
                current_jobs.append(job_web)

            if hostname and filters and since and response_hostname == hostname:
                if current_jobs:
                    all_completed = all(
                        job_web.state in ["CD", "F", "CA", "TO"]
                        for job_web in current_jobs
                    )
                    ttl_seconds = 86400 if all_completed else 60
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

        return enhanced_responses

    async def check_date_range_cache(
        self, hostname: str, filters: Dict[str, Any], since: str
    ) -> Optional[List[JobInfoWeb]]:
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
        self,
        job_id: str,
        hostname: Optional[str] = None,
        *,
        allow_stale_active: bool = False,
    ) -> Optional[JobInfoWeb]:
        cached_job = self.cache.get_cached_jobs_by_ids([job_id], hostname).get(job_id)
        if cached_job and self._can_return_cached_job(
            cached_job, allow_stale_active=allow_stale_active
        ):
            logger.debug(f"Found cached job {job_id}")
            return JobInfoWeb.from_job_info(cached_job.job_info)
        return None

    def _can_return_cached_job(
        self, cached_job, *, allow_stale_active: bool = False
    ) -> bool:
        if not cached_job or not cached_job.job_info:
            return False
        if not cached_job.is_active:
            return True
        if allow_stale_active:
            return True

        recent_cutoff = datetime.now() - timedelta(
            seconds=self._recent_active_cache_ttl_seconds
        )
        return cached_job.last_updated >= recent_cutoff

    async def cache_job_output(
        self, job_id: str, hostname: str, response: JobOutputResponse
    ):
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
        cached_job = self.cache.get_cached_jobs_by_ids([job_id], hostname).get(job_id)
        if not cached_job or not (
            cached_job.stdout_compressed or cached_job.stderr_compressed
        ):
            return None

        stdout = self._decode_cached_output(
            cached_job.stdout_compressed,
            cached_job.stdout_compression,
            "stdout",
        )
        stderr = self._decode_cached_output(
            cached_job.stderr_compressed,
            cached_job.stderr_compression,
            "stderr",
        )

        return JobOutputResponse(
            job_id=job_id,
            hostname=cached_job.hostname,
            stdout=stdout,
            stderr=stderr,
            stdout_metadata=None,
            stderr_metadata=None,
        )

    @staticmethod
    def _decode_cached_output(
        compressed_data: Optional[bytes], compression: str, output_type: str
    ) -> Optional[str]:
        if not compressed_data:
            return None

        import gzip

        try:
            if compression == "gzip":
                return gzip.decompress(compressed_data).decode("utf-8")
            return compressed_data.decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to decompress {output_type}: {e}")
            return None

    async def cache_job_script(
        self,
        job_id: str,
        hostname: str,
        script_content: str,
        local_source_dir: Optional[str] = None,
    ):
        self.cache.update_job_script(job_id, hostname, script_content)

        if local_source_dir:
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


def cache_job_state_transition(
    cache,
    job_id: str,
    hostname: str,
    state: JobState,
    *,
    job_name: Optional[str] = None,
    reason: Optional[str] = None,
    array_submission: bool = False,
) -> tuple[JobInfo, Optional[JobState]]:
    """Persist an immediate job state transition in cache."""
    cached_job = cache.get_cached_job(job_id, hostname)
    previous_state = (
        cached_job.job_info.state if cached_job and cached_job.job_info else None
    )

    if cached_job and cached_job.job_info:
        job_info = replace(cached_job.job_info, state=state)
    else:
        job_info = JobInfo(
            job_id=job_id,
            name=job_name or f"job_{job_id}",
            state=state,
            hostname=hostname,
            submit_time=datetime.now(timezone.utc).isoformat(),
        )
        if array_submission:
            job_info.array_job_id = job_id
            job_info.array_task_id = "[submission]"

    if job_name:
        job_info.name = job_name
    if reason:
        job_info.reason = reason
    if state in {
        JobState.CANCELLED,
        JobState.COMPLETED,
        JobState.FAILED,
        JobState.TIMEOUT,
    }:
        job_info.end_time = job_info.end_time or datetime.now(timezone.utc).isoformat()

    cache.cache_job(job_info)
    if state not in {JobState.PENDING, JobState.RUNNING}:
        cache.mark_job_completed(job_id, hostname)

    return job_info, previous_state
