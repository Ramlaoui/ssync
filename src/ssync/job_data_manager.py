"""
Unified Job Data Manager - THE SINGLE JOB FETCHER AND DATA MANAGER.

This service completely replaces the existing job fetching logic in manager.py
and provides a unified interface for:

- Fetching jobs from SLURM (active + completed)
- Capturing and preserving ALL job data (info + scripts + outputs)
- Managing job lifecycle transitions
- Serving job data with smart caching

DESIGN PRINCIPLE: One fetcher, one source of truth, one data flow.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from .cache import get_cache
from .models.job import JobInfo, JobState
from .utils.logging import setup_logger

logger = setup_logger(__name__)


@dataclass
class CompleteJobData:
    """Complete job data including all cached information."""

    job_info: JobInfo
    script_content: Optional[str] = None
    stdout_content: Optional[str] = None
    stderr_content: Optional[str] = None
    stdout_metadata: Optional[Dict[str, Any]] = None
    stderr_metadata: Optional[Dict[str, Any]] = None


class JobDataManager:
    @staticmethod
    def _decompress_output(compressed_data: bytes, compression: str) -> str:
        """Decompress output data based on compression type."""
        import gzip

        if not compressed_data:
            return None

        if compression == "gzip":
            try:
                return gzip.decompress(compressed_data).decode("utf-8")
            except Exception:
                return None
        elif compression == "none":
            try:
                return compressed_data.decode("utf-8")
            except Exception:
                return None
        return None

    """THE SINGLE JOB FETCHER - replaces all job fetching logic."""

    def __init__(self):
        self.cache = get_cache()
        self._fetching_hosts: Set[str] = set()  # Prevent concurrent fetching per host

    async def _run_in_executor(self, func, *args, **kwargs):
        """Run a blocking function in the thread pool if available."""
        try:
            # Try to get the executor from the web app
            from .web.app import executor

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))
        except ImportError:
            # If not running in web context, run directly (blocking)
            logger.debug(
                "No thread pool available, running SSH operations synchronously"
            )
            return func(*args, **kwargs)

    async def fetch_all_jobs(
        self,
        hostname: Optional[str] = None,
        user: Optional[str] = None,
        since: Optional[str] = None,
        limit: Optional[int] = None,
        job_ids: Optional[List[str]] = None,
        state_filter: Optional[str] = None,
        active_only: bool = False,
        completed_only: bool = False,
        skip_user_detection: bool = False,
        force_refresh: bool = False,
    ) -> List[JobInfo]:
        """
        THE MAIN JOB FETCHER - replaces manager.py get_all_jobs().

        This method:
        1. Fetches jobs from SLURM (active + completed as needed)
        2. Captures scripts proactively for new jobs
        3. Updates cache with comprehensive data
        4. Triggers background output harvesting
        5. Returns unified job list

        Args:
            hostname: Target host (if None, fetches from all hosts)
            user: Filter by user
            since: Time filter (e.g., "1d", "2h", datetime string)
            limit: Max number of jobs to return
            job_ids: Specific job IDs to fetch
            state_filter: Filter by job state
            active_only: Only return running/pending jobs
            completed_only: Only return completed jobs
            skip_user_detection: Skip user detection logic
            force_refresh: Force refresh from SLURM (ignore cache timing)

        Returns:
            List of JobInfo objects with comprehensive data
        """
        try:
            from .web.app import get_slurm_manager

            manager = get_slurm_manager()
            if not manager:
                logger.warning("No SLURM manager available")
                return []

            # Determine hosts to query
            hosts_to_query = (
                [manager.get_host_by_name(hostname)]
                if hostname
                else manager.slurm_hosts
            )

            # Filter out hosts that are already being fetched to avoid conflicts
            available_hosts = []
            for slurm_host in hosts_to_query:
                host_name = slurm_host.host.hostname
                if host_name not in self._fetching_hosts:
                    available_hosts.append(slurm_host)
            if not available_hosts:
                logger.debug("No available hosts to fetch from")
                return []

            # Mark all hosts as being fetched
            for slurm_host in available_hosts:
                self._fetching_hosts.add(slurm_host.host.hostname)

            try:
                # Fetch from all hosts concurrently using asyncio.gather()
                logger.info(
                    f"Fetching jobs concurrently from {len(available_hosts)} hosts with limit={limit} per host"
                )
                host_results = await asyncio.gather(
                    *[
                        self._fetch_host_jobs(
                            manager,
                            slurm_host,
                            user,
                            since,
                            job_ids,
                            state_filter,
                            active_only,
                            completed_only,
                            skip_user_detection,
                            force_refresh,
                            limit,
                        )
                        for slurm_host in available_hosts
                    ],
                    return_exceptions=True,  # Don't fail all if one host fails
                )

                # Collect successful results
                all_jobs = []
                for i, result in enumerate(host_results):
                    if isinstance(result, Exception):
                        logger.error(
                            f"Error fetching from {available_hosts[i].host.hostname}: {result}"
                        )
                    else:
                        all_jobs.extend(result)

            finally:
                # Clean up fetching state for all hosts
                for slurm_host in available_hosts:
                    self._fetching_hosts.discard(slurm_host.host.hostname)

            # Apply final filtering (limit already applied per-host)
            filtered_jobs = self._apply_filters(all_jobs, state_filter, None)

            logger.info(
                f"Fetched {len(filtered_jobs)} jobs from {len(hosts_to_query)} hosts"
            )
            return filtered_jobs

        except Exception as e:
            logger.error(f"Error in fetch_all_jobs: {e}")
            return []

    async def _fetch_host_jobs(
        self,
        manager,
        slurm_host,
        user: Optional[str],
        since: Optional[str],
        job_ids: Optional[List[str]],
        state_filter: Optional[str],
        active_only: bool,
        completed_only: bool,
        skip_user_detection: bool,
        force_refresh: bool,
        limit: Optional[int] = None,
    ) -> List[JobInfo]:
        """Fetch jobs from a single host with comprehensive data capture."""
        hostname = slurm_host.host.hostname
        jobs = []
        logger.info(f"_fetch_host_jobs called for {hostname} with limit={limit}")

        try:
            # Get connection with timeout - if it takes too long, try force refresh
            try:
                conn = await asyncio.wait_for(
                    self._run_in_executor(manager._get_connection, slurm_host.host),
                    timeout=15.0,  # Increased from 10s to 15s for initial connection
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Connection to {hostname} timed out after 15s, attempting connection refresh..."
                )
                # Try a gentle refresh first (not force) - this preserves more state
                try:
                    conn = await asyncio.wait_for(
                        self._run_in_executor(
                            manager._get_connection,
                            slurm_host.host,
                            False,  # Don't force
                        ),
                        timeout=20.0,  # Give 20s for retry
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        f"Connection to {hostname} still timing out after retry, using force refresh as last resort..."
                    )
                    # Only force refresh as absolute last resort
                    conn = await asyncio.wait_for(
                        self._run_in_executor(
                            manager._get_connection, slurm_host.host, True
                        ),
                        timeout=30.0,  # Give more time for fresh connection
                    )

            # Check SLURM availability - run in thread pool
            slurm_available = await self._run_in_executor(
                manager.slurm_client.check_slurm_availability, conn, hostname
            )
            if not slurm_available:
                logger.warning(f"SLURM not available on {hostname}")
                return []

            # Parse since parameter - each host gets its own parsing to ensure proper timezone handling
            since_dt = self._parse_since_to_datetime(since) if since else None

            # Determine effective user based on skip_user_detection flag
            effective_user = user
            if not skip_user_detection and not effective_user:
                # Auto-detect current user only if not skipping detection
                try:
                    effective_user = await self._run_in_executor(
                        manager.slurm_client.get_username, conn
                    )
                    logger.debug(f"Auto-detected user on {hostname}: {effective_user}")
                except Exception as e:
                    logger.error(
                        f"CRITICAL: Could not detect current user on {hostname}: {e}"
                    )
                    logger.error(
                        "Refusing to fetch jobs without user filter to prevent performance issues"
                    )
                    return []  # Fail safe: don't fetch anything if we can't determine user
            elif skip_user_detection and not effective_user:
                # Explicitly requested to skip user detection and query all users
                logger.info(
                    f"Fetching jobs for ALL users on {hostname} (skip_user_detection=True)"
                )
                effective_user = (
                    None  # None means all users in get_active_jobs/get_completed_jobs
                )

            # 1. GET ACTIVE JOBS (unless completed_only) - OPTIMIZED with thread pool
            if not completed_only:
                active_jobs = await self._run_in_executor(
                    manager.slurm_client.get_active_jobs,
                    conn,
                    hostname,
                    effective_user,
                    job_ids,
                    state_filter,
                    skip_user_detection,
                )

                # LIGHTWEIGHT CACHING - only cache job info, don't fetch expensive data
                for job in active_jobs:
                    job.hostname = hostname
                    # Only cache basic job info (preserving existing script/outputs)
                    self.cache.cache_job(
                        job,
                        script_content=None,  # Preserve existing
                    )

                jobs.extend(active_jobs)

            # 2. GET COMPLETED JOBS (unless active_only) - OPTIMIZED with thread pool
            if not active_only:
                active_job_ids = [job.job_id for job in jobs]

                # Use intelligent since time (incremental fetching) - host-specific
                effective_since = await self._determine_effective_since(
                    hostname, since_dt
                )

                # NEW: Get cached completed job IDs to skip re-querying
                cached_completed_ids = set()
                # Use cache even on force_refresh for completed jobs (they don't change)
                # Only skip cache if we're looking for specific job_ids
                if not job_ids:
                    cached_completed_ids = self.cache.get_cached_completed_job_ids(
                        hostname, effective_since
                    )
                    if cached_completed_ids:
                        logger.info(
                            f"Found {len(cached_completed_ids)} completed jobs in cache for {hostname}, "
                            f"will skip re-querying these from SLURM"
                        )

                completed_jobs = await self._run_in_executor(
                    manager.slurm_client.get_completed_jobs,
                    conn,
                    hostname,
                    effective_since,
                    effective_user,
                    job_ids,
                    state_filter,
                    active_job_ids,
                    skip_user_detection,
                    None,
                    cached_completed_ids,  # NEW: Pass cached IDs to skip
                )

                # CACHE COMPLETED JOBS AND FETCH OUTPUTS
                for job in completed_jobs:
                    job.hostname = hostname

                    # Check if we already have this job cached
                    cached_job = self.cache.get_cached_job(job.job_id, hostname)

                    # Cache job info (preserving existing data)
                    self.cache.cache_job(
                        job,
                        script_content=None,  # Preserve existing
                    )

                    # If this is a new completed job without cached outputs, fetch them
                    if not cached_job or (
                        not cached_job.stdout_compressed
                        and not cached_job.stderr_compressed
                    ):
                        if job.stdout_file or job.stderr_file:
                            try:
                                # Fetch outputs asynchronously without blocking the main fetch
                                asyncio.create_task(
                                    self._fetch_outputs_from_cached_paths(job)
                                )
                            except Exception:
                                pass
                jobs.extend(completed_jobs)

                # UPDATE FETCH STATE
                await self._update_fetch_state(hostname, conn)

            # 3. ENHANCE WITH CACHED JOBS (filtered by user and respecting active_only/completed_only)
            # Only merge cached jobs if we're not filtering to active_only
            if not active_only:
                cached_jobs = self.cache.get_cached_completed_jobs(
                    hostname, since=since_dt
                )

                # CRITICAL: Filter cached jobs by current user
                user_cached_jobs = []
                if cached_jobs:
                    for cached_job in cached_jobs:
                        if cached_job.user == effective_user:
                            # Also respect completed_only flag
                            if not completed_only or cached_job.state in [
                                JobState.COMPLETED,
                                JobState.FAILED,
                                JobState.CANCELLED,
                                JobState.TIMEOUT,
                            ]:
                                user_cached_jobs.append(cached_job)

                jobs = self._merge_with_cached_jobs(jobs, user_cached_jobs)

            # Apply per-host limit if specified
            if limit:
                # Sort by submit time (newest first) before limiting
                jobs.sort(key=lambda job: job.submit_time or "", reverse=True)
                original_count = len(jobs)
                jobs = jobs[:limit]
                logger.info(
                    f"Applied per-host limit of {limit} to {hostname}, reduced from {original_count} to {len(jobs)} jobs"
                )

            logger.info(
                f"Returning {len(jobs)} jobs for user {effective_user} from {hostname} (limit={limit})"
            )
            return jobs

        except Exception as e:
            logger.error(f"Error fetching jobs from {hostname}: {e}")
            return []

    # Removed complex _capture_job_data_comprehensive method - no longer needed
    # Job data is now captured at submission time and outputs are fetched on-demand

    def _is_users_job(self, manager, conn, job: JobInfo) -> bool:
        """Check if a job belongs to the current user."""
        try:
            # Get current username
            current_user = manager.slurm_client.get_username(conn)
            return job.user == current_user
        except Exception:
            return False

    async def capture_job_submission(
        self, job_id: str, hostname: str, script_content: str
    ):
        """
        Called immediately after job submission to capture ALL critical data while still accessible.

        This is the key method that prevents data loss - it captures everything we need
        BEFORE the job completes and scontrol commands stop working.

        Args:
            job_id: SLURM job ID
            hostname: Target host
            script_content: The script content that was submitted
        """
        try:
            # Get manager and connection
            from .web.app import get_slurm_manager

            manager = get_slurm_manager()
            if not manager:
                logger.warning(
                    f"No manager available for comprehensive capture of job {job_id}"
                )
                # Still cache the script at minimum
                self.cache.update_job_script(job_id, hostname, script_content)
                return

            slurm_host = manager.get_host_by_name(hostname)
            conn = manager._get_connection(slurm_host.host)

            # 1. Cache the script immediately
            self.cache.update_job_script(job_id, hostname, script_content)

            # 2. Capture COMPLETE job metadata while scontrol still works
            # This is CRITICAL - get ALL info including output file paths NOW
            try:
                complete_job_info = await self._run_in_executor(
                    manager.get_job_info, slurm_host, job_id, None
                )

                if complete_job_info:
                    # Cache complete job info with all metadata
                    self.cache.cache_job(
                        complete_job_info, script_content=script_content
                    )
                    logger.info(
                        f"Captured COMPLETE job metadata for {job_id} including output paths"
                    )
                else:
                    # Fallback to minimal record if full info not available yet
                    minimal_job_info = JobInfo(
                        job_id=job_id,
                        name=f"job_{job_id}",
                        state=JobState.PENDING,
                        hostname=hostname,
                        submit_time=datetime.now().isoformat(),
                    )
                    self.cache.cache_job(
                        minimal_job_info, script_content=script_content
                    )

            except Exception as e:
                import traceback

                logger.warning(f"Could not get complete job info for {job_id}: {e}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
                # Create minimal record as fallback
                minimal_job_info = JobInfo(
                    job_id=job_id,
                    name=f"job_{job_id}",
                    state=JobState.PENDING,
                    hostname=hostname,
                    submit_time=datetime.now().isoformat(),
                )
                self.cache.cache_job(minimal_job_info, script_content=script_content)

            # 3. Try to get output file paths immediately (while scontrol works)
            try:
                stdout_path, stderr_path = await self._run_in_executor(
                    manager.slurm_client.get_job_output_files, conn, job_id, hostname
                )

                if stdout_path or stderr_path:
                    logger.info(
                        f"Captured output paths for job {job_id}: stdout={stdout_path}, stderr={stderr_path}"
                    )
                    # These paths are now safely stored in the cached job info

            except Exception:
                pass

            logger.info(
                f"Comprehensive submission data captured for job {job_id} on {hostname}"
            )

        except Exception as e:
            logger.error(f"Failed to capture submission data for job {job_id}: {e}")
            # At minimum, try to save the script
            try:
                self.cache.update_job_script(job_id, hostname, script_content)
            except Exception as script_error:
                logger.error(
                    f"Even script caching failed for job {job_id}: {script_error}"
                )

    async def update_job_status(self, job_info: JobInfo):
        """
        Called when job status changes - preserves existing data.
        For completed jobs, automatically fetches outputs if not already cached.

        Args:
            job_info: Updated job information from SLURM
        """
        try:
            # Always preserve existing data, only update status fields
            self.cache.cache_job(
                job_info,
                script_content=None,  # Preserve existing
            )

            # If job just completed, fetch outputs if we don't have them
            if job_info.state in [
                JobState.COMPLETED,
                JobState.FAILED,
                JobState.CANCELLED,
                JobState.TIMEOUT,
            ]:
                cached_job = self.cache.get_cached_job(
                    job_info.job_id, job_info.hostname
                )
                if (
                    cached_job
                    and not cached_job.stdout_compressed
                    and not cached_job.stderr_compressed
                ):
                    if job_info.stdout_file or job_info.stderr_file:
                        logger.info(
                            f"Job {job_info.job_id} completed, fetching outputs"
                        )
                        asyncio.create_task(
                            self._fetch_outputs_from_cached_paths(job_info)
                        )

        except Exception as e:
            logger.error(f"Failed to update job status for {job_info.job_id}: {e}")

    async def _fetch_outputs_from_cached_paths(
        self, job_info: JobInfo, force_fetch: bool = False
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Fetch output files from remote filesystem.

        For completed jobs: Always tries to fetch from SSH unless already fetched after completion.
        For running jobs: Always fetches latest output.

        Args:
            job_info: Job information including output file paths
            force_fetch: If True, always fetch from SSH regardless of cache state
        """
        try:
            from .web.app import get_slurm_manager

            manager = get_slurm_manager()
            if not manager:
                return None, None

            # Check if job is completed
            is_completed = job_info.state in [
                JobState.COMPLETED,
                JobState.FAILED,
                JobState.CANCELLED,
                JobState.TIMEOUT,
            ]

            # Check if we've already fetched outputs after completion
            stdout_fetched_after, stderr_fetched_after = (
                self.cache.check_outputs_fetched_after_completion(
                    job_info.job_id, job_info.hostname
                )
            )

            # Determine what to fetch
            should_fetch_stdout = (
                force_fetch
                or not is_completed  # Always fetch for running jobs
                or (
                    is_completed and not stdout_fetched_after
                )  # Fetch if not fetched after completion
            ) and job_info.stdout_file

            should_fetch_stderr = (
                force_fetch
                or not is_completed  # Always fetch for running jobs
                or (
                    is_completed and not stderr_fetched_after
                )  # Fetch if not fetched after completion
            ) and job_info.stderr_file

            # If nothing to fetch, return existing cached content
            if not should_fetch_stdout and not should_fetch_stderr:
                cached_job = self.cache.get_cached_job(
                    job_info.job_id, job_info.hostname
                )
                if cached_job:
                    logger.debug(
                        f"Job {job_info.job_id} outputs already fetched after completion, using cache"
                    )
                    stdout = self._decompress_output(
                        cached_job.stdout_compressed, cached_job.stdout_compression
                    )
                    stderr = self._decompress_output(
                        cached_job.stderr_compressed, cached_job.stderr_compression
                    )
                    return stdout, stderr
                return None, None

            try:
                slurm_host = manager.get_host_by_name(job_info.hostname)
                conn = manager._get_connection(slurm_host.host)
            except Exception as e:
                error_msg = f"Failed to connect to {job_info.hostname}: {e}"
                logger.error(error_msg)
                if force_fetch:
                    raise RuntimeError(error_msg)
                # Return cached content if available
                cached_job = self.cache.get_cached_job(
                    job_info.job_id, job_info.hostname
                )
                if cached_job:
                    logger.info(
                        f"Using cached content for job {job_info.job_id} after connection error"
                    )
                    stdout = self._decompress_output(
                        cached_job.stdout_compressed, cached_job.stdout_compression
                    )
                    stderr = self._decompress_output(
                        cached_job.stderr_compressed, cached_job.stderr_compression
                    )
                    return stdout, stderr
                return None, None

            stdout_content = None
            stderr_content = None

            # Try to fetch stdout if needed
            if should_fetch_stdout:
                try:
                    # For completed jobs, check if the path looks like a script file (common SLURM bug)
                    # For running jobs, we've already corrected this in get_active_jobs
                    if (
                        is_completed
                        and job_info.stdout_file
                        and (
                            job_info.stdout_file.endswith(".sh")
                            or job_info.stdout_file.endswith(".sbatch")
                            or job_info.stdout_file.endswith(".bash")
                            or job_info.stdout_file.endswith(".slurm")
                            or "/submit/"
                            in job_info.stdout_file  # Common pattern for script directories
                            or "/scripts/" in job_info.stdout_file
                        )
                    ):
                        logger.warning(
                            f"Completed job {job_info.job_id} has suspicious stdout path: {job_info.stdout_file}. "
                            "This is likely a SLURM bug. scontrol may not work for completed jobs, skipping fetch."
                        )
                        stdout_content = None
                        should_fetch_stdout = False

                    if should_fetch_stdout and job_info.stdout_file:
                        # First check if file exists
                        check_result = await self._run_in_executor(
                            conn.run,
                            f"test -f '{job_info.stdout_file}' && echo 'exists' || echo 'notfound'",
                            hide=True,
                        )

                        if "exists" in check_result.stdout:
                            result = await self._run_in_executor(
                                conn.run,
                                f"cat '{job_info.stdout_file}'",
                                hide=True,
                            )
                            if result.ok:
                                stdout_content = result.stdout
                                logger.debug(
                                    f"Fetched stdout for job {job_info.job_id} from SSH"
                                )
                        else:
                            logger.debug(
                                f"Stdout file not found for job {job_info.job_id}"
                            )
                            # Keep existing cached content if file not found
                            cached_job = self.cache.get_cached_job(
                                job_info.job_id, job_info.hostname
                            )
                            if cached_job and cached_job.stdout_compressed:
                                stdout_content = self._decompress_output(
                                    cached_job.stdout_compressed,
                                    cached_job.stdout_compression,
                                )
                except Exception as e:
                    logger.error(
                        f"Error fetching stdout for job {job_info.job_id} from {job_info.hostname}: {e}"
                    )
                    # If force_fetch was requested, don't fall back to cache - raise the error
                    if force_fetch:
                        raise RuntimeError(f"Failed to fetch stdout from SSH: {e}")

                    # Otherwise, keep existing cached content on error
                    cached_job = self.cache.get_cached_job(
                        job_info.job_id, job_info.hostname
                    )
                    if cached_job and cached_job.stdout_compressed:
                        logger.info(
                            f"Using cached stdout for job {job_info.job_id} after fetch error"
                        )
                        stdout_content = self._decompress_output(
                            cached_job.stdout_compressed, cached_job.stdout_compression
                        )
            else:
                # Use cached content
                cached_job = self.cache.get_cached_job(
                    job_info.job_id, job_info.hostname
                )
                if cached_job:
                    stdout_content = self._decompress_output(
                        cached_job.stdout_compressed, cached_job.stdout_compression
                    )

            # Try to fetch stderr if needed
            if should_fetch_stderr:
                try:
                    # For completed jobs, check if the path looks like a script file (common SLURM bug)
                    # For running jobs, we've already corrected this in get_active_jobs
                    if (
                        is_completed
                        and job_info.stderr_file
                        and (
                            job_info.stderr_file.endswith(".sh")
                            or job_info.stderr_file.endswith(".sbatch")
                            or job_info.stderr_file.endswith(".bash")
                            or job_info.stderr_file.endswith(".slurm")
                            or "/submit/"
                            in job_info.stderr_file  # Common pattern for script directories
                            or "/scripts/" in job_info.stderr_file
                        )
                    ):
                        logger.warning(
                            f"Completed job {job_info.job_id} has suspicious stderr path: {job_info.stderr_file}. "
                            "This is likely a SLURM bug. scontrol may not work for completed jobs, skipping fetch."
                        )
                        stderr_content = None
                        should_fetch_stderr = False

                    if should_fetch_stderr and job_info.stderr_file:
                        # First check if file exists
                        check_result = await self._run_in_executor(
                            conn.run,
                            f"test -f '{job_info.stderr_file}' && echo 'exists' || echo 'notfound'",
                            hide=True,
                        )

                        if "exists" in check_result.stdout:
                            result = await self._run_in_executor(
                                conn.run,
                                f"cat '{job_info.stderr_file}'",
                                hide=True,
                            )
                            if result.ok:
                                stderr_content = result.stdout
                                logger.debug(
                                    f"Fetched stderr for job {job_info.job_id} from SSH"
                                )
                        else:
                            logger.debug(
                                f"Stderr file not found for job {job_info.job_id}"
                            )
                            # Keep existing cached content if file not found
                            cached_job = self.cache.get_cached_job(
                                job_info.job_id, job_info.hostname
                            )
                            if cached_job and cached_job.stderr_compressed:
                                stderr_content = self._decompress_output(
                                    cached_job.stderr_compressed,
                                    cached_job.stderr_compression,
                                )
                except Exception as e:
                    logger.error(
                        f"Error fetching stderr for job {job_info.job_id} from {job_info.hostname}: {e}"
                    )
                    # If force_fetch was requested, don't fall back to cache - raise the error
                    if force_fetch:
                        raise RuntimeError(f"Failed to fetch stderr from SSH: {e}")

                    # Otherwise, keep existing cached content on error
                    cached_job = self.cache.get_cached_job(
                        job_info.job_id, job_info.hostname
                    )
                    if cached_job and cached_job.stderr_compressed:
                        logger.info(
                            f"Using cached stderr for job {job_info.job_id} after fetch error"
                        )
                        stderr_content = self._decompress_output(
                            cached_job.stderr_compressed, cached_job.stderr_compression
                        )
            else:
                # Use cached content
                cached_job = self.cache.get_cached_job(
                    job_info.job_id, job_info.hostname
                )
                if cached_job:
                    stderr_content = self._decompress_output(
                        cached_job.stderr_compressed, cached_job.stderr_compression
                    )

            # Update cache with fetched outputs
            if should_fetch_stdout or should_fetch_stderr:
                self.cache.update_job_outputs(
                    job_info.job_id,
                    job_info.hostname,
                    stdout_content=stdout_content if should_fetch_stdout else None,
                    stderr_content=stderr_content if should_fetch_stderr else None,
                    mark_fetched_after_completion=is_completed,  # Mark as fetched after completion if job is completed
                )
                logger.info(
                    f"Updated outputs for job {job_info.job_id} (completed={is_completed})"
                )

            return stdout_content, stderr_content

        except Exception as e:
            logger.error(f"Error fetching outputs for job {job_info.job_id}: {e}")
            # Return cached content on error
            cached_job = self.cache.get_cached_job(job_info.job_id, job_info.hostname)
            if cached_job:
                stdout = self._decompress_output(
                    cached_job.stdout_compressed, cached_job.stdout_compression
                )
                stderr = self._decompress_output(
                    cached_job.stderr_compressed, cached_job.stderr_compression
                )
                return stdout, stderr
            return None, None

    async def get_job_data(
        self, job_id: str, hostname: str
    ) -> Optional[CompleteJobData]:
        """
        Unified interface for retrieving all job data.
        For completed jobs without cached outputs, fetches them from filesystem.

        Args:
            job_id: Job ID to retrieve
            hostname: Hostname where job ran

        Returns:
            Complete job data if found, None otherwise
        """
        try:
            cached_job = self.cache.get_cached_job(job_id, hostname)
            if not cached_job:
                return None

            stdout_content = self._decompress_output(
                cached_job.stdout_compressed, cached_job.stdout_compression
            )
            stderr_content = self._decompress_output(
                cached_job.stderr_compressed, cached_job.stderr_compression
            )

            # If job is completed but we don't have outputs cached, fetch them from filesystem
            if (
                cached_job.job_info.state not in [JobState.PENDING, JobState.RUNNING]
                and not stdout_content
                and not stderr_content
            ):
                (
                    stdout_content,
                    stderr_content,
                ) = await self._fetch_outputs_from_cached_paths(cached_job.job_info)

            return CompleteJobData(
                job_info=cached_job.job_info,
                script_content=cached_job.script_content,
                stdout_content=stdout_content,
                stderr_content=stderr_content,
                stdout_metadata=None,  # Could be enhanced later
                stderr_metadata=None,
            )

        except Exception as e:
            logger.error(f"Error retrieving job data for {job_id}: {e}")
            return None

    async def get_job_script(
        self, job_id: str, hostname: Optional[str] = None
    ) -> Optional[str]:
        """
        Get job script content with fallback logic.

        Args:
            job_id: Job ID
            hostname: Optional hostname filter

        Returns:
            Script content if found, None otherwise
        """
        try:
            # Check cache first
            cached_job = self.cache.get_cached_job(job_id, hostname)
            if cached_job and cached_job.script_content:
                return cached_job.script_content

            # Try to get from SLURM as fallback
            from .web.app import get_slurm_manager

            manager = get_slurm_manager()
            if not manager:
                return None

            # Try all hosts if hostname not specified
            hosts_to_try = (
                [manager.get_host_by_name(hostname)]
                if hostname
                else manager.slurm_hosts
            )

            for slurm_host in hosts_to_try:
                try:
                    conn = manager._get_connection(slurm_host.host)
                    script_content = manager.slurm_client.get_job_batch_script(
                        conn, job_id, slurm_host.host.hostname
                    )

                    if script_content:
                        # Cache it for future use
                        self.cache.update_job_script(
                            job_id, slurm_host.host.hostname, script_content
                        )
                        return script_content

                except Exception:
                    continue

            return None

        except Exception as e:
            logger.error(f"Error retrieving script for job {job_id}: {e}")
            return None

    # HELPER METHODS

    def _parse_since_to_datetime(self, since: str) -> datetime:
        """Parse since parameter to datetime (returns UTC timezone-aware datetime)."""
        if not since:
            return datetime.now(timezone.utc) - timedelta(days=1)

        # Parse patterns like "1h", "2d", "1w", "1m", or specific dates
        if since.endswith("h"):
            hours = int(since[:-1])
            return datetime.now(timezone.utc) - timedelta(hours=hours)
        elif since.endswith("d"):
            days = int(since[:-1])
            return datetime.now(timezone.utc) - timedelta(days=days)
        elif since.endswith("w"):
            weeks = int(since[:-1])
            return datetime.now(timezone.utc) - timedelta(weeks=weeks)
        elif since.endswith("m"):
            months = int(since[:-1])
            # Approximate months as 30 days each
            return datetime.now(timezone.utc) - timedelta(days=months * 30)
        else:
            # Try to parse as datetime
            try:
                dt = datetime.fromisoformat(since)
                # Ensure it's timezone-aware
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                return datetime.now(timezone.utc) - timedelta(days=1)

    def _apply_filters(
        self, jobs: List[JobInfo], state_filter: Optional[str], limit: Optional[int]
    ) -> List[JobInfo]:
        """Apply final filters and limits to job list."""
        # Apply state filter
        if state_filter:
            jobs = [job for job in jobs if job.state.value == state_filter]

        # Sort by submit time (newest first)
        jobs.sort(key=lambda job: job.submit_time or "", reverse=True)

        # Apply limit
        if limit:
            jobs = jobs[:limit]

        return jobs

    async def _determine_effective_since(
        self, hostname: str, requested_since: Optional[datetime]
    ) -> Optional[datetime]:
        """Determine effective since time for incremental fetching, respecting host timezone."""
        # IMPORTANT: Always respect the user's requested since parameter
        # The incremental fetching optimization should only apply when no explicit since is provided

        if requested_since:
            # User explicitly requested a time range - respect it
            # Ensure it's UTC-aware for consistency
            if requested_since.tzinfo is None:
                requested_since = requested_since.replace(tzinfo=timezone.utc)
            return requested_since

        # No explicit since requested - use incremental fetching from last fetch time
        fetch_state = self.cache.get_host_fetch_state(hostname)
        if fetch_state:
            last_fetch_utc_str = fetch_state["last_fetch_time_utc"]
            if "+" in last_fetch_utc_str or "Z" in last_fetch_utc_str:
                last_fetch_utc = datetime.fromisoformat(
                    last_fetch_utc_str.replace("Z", "+00:00")
                )
            else:
                last_fetch_utc = datetime.fromisoformat(last_fetch_utc_str).replace(
                    tzinfo=timezone.utc
                )

            # Use last fetch time with small buffer for incremental updates
            return last_fetch_utc - timedelta(minutes=1)

        # No fetch history and no explicit since - default to 24 hours
        return datetime.now(timezone.utc) - timedelta(days=1)

    async def _update_fetch_state(self, hostname: str, conn):
        """Update fetch state tracking."""
        try:
            # Get cluster's current time - run in thread pool
            cluster_time_result = await self._run_in_executor(
                conn.run, "date '+%Y-%m-%dT%H:%M:%S%z'", hide=True
            )
            cluster_time_str = cluster_time_result.stdout.strip()

            if "+" in cluster_time_str or "-" in cluster_time_str[-6:]:
                cluster_time = datetime.fromisoformat(cluster_time_str)
            else:
                cluster_time = datetime.fromisoformat(cluster_time_str)

            utc_time = datetime.now(timezone.utc)

            self.cache.update_host_fetch_state(
                hostname=hostname,
                fetch_time=cluster_time,
                fetch_time_utc=utc_time,
                cluster_timezone=None,
            )

        except Exception as e:
            logger.warning(f"Failed to update fetch state for {hostname}: {e}")

    def _merge_with_cached_jobs(
        self, slurm_jobs: List[JobInfo], cached_jobs: List[JobInfo]
    ) -> List[JobInfo]:
        """Merge SLURM jobs with cached jobs, removing duplicates."""
        slurm_job_ids = {job.job_id for job in slurm_jobs}

        # Add cached jobs that aren't already in SLURM results
        for cached_job in cached_jobs:
            if cached_job.job_id not in slurm_job_ids:
                slurm_jobs.append(cached_job)

        return slurm_jobs

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        return self.cache.get_cache_stats()

    async def cleanup_old_data(self, max_age_days: Optional[int] = None) -> int:
        """Clean up old job data according to retention policies."""
        return self.cache.cleanup_old_entries(max_age_days)


# Global instance
_job_data_manager: Optional[JobDataManager] = None


def get_job_data_manager() -> JobDataManager:
    """Get or create global job data manager instance."""
    global _job_data_manager
    if _job_data_manager is None:
        _job_data_manager = JobDataManager()
    return _job_data_manager
