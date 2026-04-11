"""Background cache verification and final-state recovery helpers."""

import asyncio
import os
from typing import Any, Dict, List, Optional

from ...utils.async_helpers import create_task
from ...utils.logging import setup_logger

logger = setup_logger(__name__)


class CacheVerificationService:
    """Rate-limited cache verification and completion recovery."""

    def __init__(self, cache):
        self.cache = cache
        self._unknown_retry_attempts: Dict[tuple[str, str], int] = {}
        self._failed_sacct_attempts: Dict[tuple[str, str], tuple[int, float]] = {}
        self._MAX_SACCT_RETRIES = 3
        self._MAX_SACCT_RETRY_TIME = 300
        self._last_verify_time: float = 0
        self._verify_cooldown_seconds: float = float(
            os.environ.get("SSYNC_CACHE_VERIFY_COOLDOWN", "30")
        )
        self._verify_in_progress: bool = False
        logger.info(
            f"Cache verification cooldown set to {self._verify_cooldown_seconds}s "
            f"(set SSYNC_CACHE_VERIFY_COOLDOWN to adjust)"
        )

    async def verify_and_update_cache(self, current_job_ids: Dict[str, List[str]]):
        import time

        current_time = time.time()
        time_since_last_verify = current_time - self._last_verify_time
        if time_since_last_verify < self._verify_cooldown_seconds:
            logger.debug(
                f"Skipping cache verification (last verify {time_since_last_verify:.1f}s ago, "
                f"cooldown={self._verify_cooldown_seconds}s)"
            )
            return

        if self._verify_in_progress:
            logger.debug("Cache verification already in progress, skipping")
            return

        self._verify_in_progress = True
        self._last_verify_time = current_time
        create_task(self._run_verification_in_background(current_job_ids))

    async def _run_verification_in_background(
        self, current_job_ids: Dict[str, List[str]]
    ):
        try:
            logger.info("Starting background cache verification")
            to_mark_completed = self.cache.verify_cached_jobs(current_job_ids)
            if not to_mark_completed:
                logger.debug("No jobs to mark as completed")
                return

            logger.info(
                f"Found {len(to_mark_completed)} jobs to verify and mark as completed"
            )
            successfully_updated = await self._fetch_final_states_and_preserve(
                to_mark_completed
            )

            for job_id, hostname in successfully_updated:
                self.cache.mark_job_completed(job_id, hostname)

            if successfully_updated:
                logger.info(
                    f"Marked {len(successfully_updated)} jobs as completed with final states"
                )

            if len(successfully_updated) < len(to_mark_completed):
                skipped = len(to_mark_completed) - len(successfully_updated)
                logger.info(
                    f"Skipped {skipped} jobs - will retry fetching their final state next time"
                )
        except Exception as e:
            logger.error(f"Error in background cache verification: {e}")
        finally:
            self._verify_in_progress = False

    async def _fetch_final_states_and_preserve(
        self, completing_jobs: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        if not completing_jobs:
            return []

        logger.info(
            f"Fetching final states from sacct for {len(completing_jobs)} completing jobs"
        )
        successfully_updated = []

        try:
            from ..app import get_slurm_manager

            manager = get_slurm_manager()
            if not manager:
                logger.warning("No manager available for fetching final states")
                return []

            jobs_by_host = {}
            for job_id, hostname in completing_jobs:
                jobs_by_host.setdefault(hostname, []).append(job_id)

            host_results = await asyncio.gather(
                *[
                    self._fetch_final_states_for_host(manager, hostname, job_ids)
                    for hostname, job_ids in jobs_by_host.items()
                ],
                return_exceptions=True,
            )

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
        successfully_updated = []

        try:
            slurm_host = manager.get_host_by_name(hostname)
            conn = await asyncio.to_thread(manager._get_connection, slurm_host.host)
            tasks = [
                self._fetch_single_job_final_state(manager, conn, hostname, job_id)
                for job_id in job_ids
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

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
        try:
            job_key = (job_id, hostname)
            unknown_attempts = self._unknown_retry_attempts.get(job_key, 0)
            if unknown_attempts >= 3:
                logger.warning(
                    f"Skipping job {job_id} on {hostname} - stuck in UNKNOWN state after {unknown_attempts} attempts"
                )
                self._unknown_retry_attempts.pop(job_key, None)
                return None

            from ..app import executor

            loop = asyncio.get_event_loop()
            final_state = await loop.run_in_executor(
                executor,
                manager.slurm_client.get_job_final_state,
                conn,
                hostname,
                job_id,
            )

            if final_state:
                from ...models.job import JobState

                if final_state.state == JobState.UNKNOWN:
                    self._unknown_retry_attempts[job_key] = unknown_attempts + 1
                    logger.warning(
                        f"Job {job_id} has UNKNOWN state (attempt {unknown_attempts + 1}/3) - will retry"
                    )
                    return None

                self._unknown_retry_attempts.pop(job_key, None)
                self._failed_sacct_attempts.pop(job_key, None)

                logger.info(
                    f"Updating job {job_id} with final state: {final_state.state.value}"
                )
                cached_job = self.cache.get_cached_jobs_by_ids([job_id], hostname).get(
                    job_id
                )
                script_content = cached_job.script_content if cached_job else None

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

                self.cache.cache_job(final_state, script_content=script_content)
                return True

            return self._handle_missing_final_state(job_id, hostname)
        except Exception as e:
            logger.warning(f"Error processing completing job {job_id}: {e}")
            return None

    def _handle_missing_final_state(self, job_id: str, hostname: str) -> Optional[bool]:
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
        if (
            attempts >= self._MAX_SACCT_RETRIES
            or time_elapsed >= self._MAX_SACCT_RETRY_TIME
        ):
            logger.warning(
                f"Giving up on job {job_id} after {attempts} failed sacct attempts "
                f"({time_elapsed:.0f}s elapsed). Marking as completed with UNKNOWN state."
            )
            cached_job = self.cache.get_cached_jobs_by_ids([job_id], hostname).get(
                job_id
            )
            if cached_job and cached_job.job_info:
                from ...models.job import JobState

                cached_job.job_info.state = JobState.UNKNOWN
                self.cache.cache_job(
                    cached_job.job_info,
                    script_content=cached_job.script_content,
                )

            self._failed_sacct_attempts.pop(job_key, None)
            return True

        logger.warning(
            f"Could not fetch final state for job {job_id} from sacct "
            f"(attempt {attempts}/{self._MAX_SACCT_RETRIES}) - will retry next time"
        )
        return None

    def extend_stats(self, stats: Dict[str, Any]) -> Dict[str, Any]:
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
