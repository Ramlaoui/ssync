"""SLURM command execution utilities."""

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Protocol

from ..models.job import JobInfo, JobState
from ..utils.logging import setup_logger
from .fields import SQUEUE_FIELDS
from .parser import SlurmParser


# Define a protocol for SSH connections (duck typing)
class SSHConnection(Protocol):
    """Protocol for SSH connection objects."""

    def run(self, command: str, **kwargs) -> Any: ...


logger = setup_logger(__name__, "INFO")


class SlurmClient:
    """Handles execution of SLURM commands and parsing results."""

    def __init__(self):
        self.parser = SlurmParser()
        self._available_fields_cache = {}
        self._username_cache = {}  # Cache usernames per hostname to avoid repeated queries

    def get_available_sacct_fields(
        self, conn: SSHConnection, hostname: str
    ) -> List[str]:
        """Get list of available sacct fields for this SLURM cluster."""
        if hostname in self._available_fields_cache:
            logger.debug(
                f"Using cached fields for {hostname}: {self._available_fields_cache[hostname]}"
            )
            return self._available_fields_cache[hostname]

        try:
            logger.debug(f"Detecting available sacct fields for {hostname}")
            result = conn.run(
                "sacct --helpformat", hide=True, timeout=10, warn=True, pty=True
            )

            if not result.ok or not result.stdout:
                logger.debug(
                    f"sacct --helpformat failed for {hostname}, using basic fields"
                )
                basic_fields = [
                    "JobID",
                    "JobName",
                    "State",
                    "User",
                    "Partition",
                    "AllocNodes",
                    "AllocCPUS",
                    "Submit",
                    "Start",
                    "End",
                ]
                self._available_fields_cache[hostname] = basic_fields
                return basic_fields

            available_fields = []

            for line in result.stdout.replace("\r\n", "\n").split("\n"):
                line = line.strip()
                if line:
                    fields_in_line = line.split()
                    for field in fields_in_line:
                        field = field.strip()
                        if field and field.replace("_", "").isalnum():
                            available_fields.append(field)

            essential_fields = ["JobID", "JobName", "State", "User"]

            wanted_fields = [
                "JobID",
                "JobName",
                "State",
                "User",
                "Partition",
                "AllocNodes",
                "AllocCPUS",
                "ReqMem",
                "Timelimit",
                "Elapsed",
                "Submit",
                "SubmitLine",
                "Start",
                "End",
                "WorkDir",
                "StdOut",
                "StdErr",
                "NodeList",
                "Reason",
                "AllocTRES",
                "ReqTRES",
                "CPUTime",
                "TotalCPU",
                "MaxRSS",
                "ConsumedEnergy",
            ]

            cluster_fields = [
                field for field in wanted_fields if field in available_fields
            ]

            missing_essential = [
                field for field in essential_fields if field not in cluster_fields
            ]
            if missing_essential:
                logger.debug(
                    f"Missing essential fields {missing_essential} for {hostname}, using basic fallback"
                )
                cluster_fields = [
                    "JobID",
                    "JobName",
                    "State",
                    "User",
                    "Partition",
                    "Submit",
                    "Start",
                    "End",
                ]

            logger.debug(f"Available sacct fields for {hostname}: {cluster_fields}")
            self._available_fields_cache[hostname] = cluster_fields
            return cluster_fields

        except Exception as e:
            logger.debug(f"Failed to detect sacct fields for {hostname}: {e}")
            basic_fields = [
                "JobID",
                "JobName",
                "State",
                "User",
                "Partition",
                "Submit",
                "Start",
                "End",
            ]
            self._available_fields_cache[hostname] = basic_fields
            return basic_fields

    def get_active_jobs(
        self,
        conn: SSHConnection,
        hostname: str,
        user: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        state_filter: Optional[str] = None,
        skip_user_detection: bool = False,
    ) -> List[JobInfo]:
        """Get active (running/pending) jobs using squeue."""
        jobs = []

        try:
            format_str = "|".join(SQUEUE_FIELDS)
            cmd = f"squeue --format='{format_str}' --noheader"

            if user:
                query_user = user
                logger.debug(f"Using provided user filter: {user}")
            elif not skip_user_detection:
                query_user = self.get_username(conn, hostname=hostname)
                logger.debug(f"Auto-detected current user: {query_user}")
            else:
                query_user = None
                logger.debug("Querying all users (no user filter)")

            if query_user:
                cmd += f" --user={query_user}"
            if job_ids:
                cmd += f" --job={','.join(job_ids)}"
            if state_filter:
                cmd += f" --states={state_filter}"

            logger.debug(f"Running squeue command on {hostname}: {cmd}")
            # Try with PTY enabled to force output flushing
            result = conn.run(cmd, hide=True, timeout=30, warn=True, pty=True)
            logger.debug(
                f"squeue result: exit={result.exited}, stdout_len={len(result.stdout)}, stderr_len={len(result.stderr)}"
            )
            if result.stdout:
                logger.debug(f"squeue stdout preview: {result.stdout[:200]}...")
            if result.stderr:
                logger.debug(f"squeue stderr: {result.stderr}")
            if not result.ok:
                logger.debug(f"squeue command failed with exit code: {result.exited}")

            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue

                fields = line.strip().split("|")
                if len(fields) >= len(SQUEUE_FIELDS):
                    try:
                        job_info = self.parser.from_squeue_fields(fields, hostname)

                        # For RUNNING and PENDING jobs, proactively get correct output paths and submit_line from scontrol
                        # This avoids the script-as-output bug that affects some SLURM clusters
                        # and ensures we have submit_line which isn't available in squeue
                        if job_info.state in [JobState.RUNNING, JobState.PENDING]:
                            try:
                                stdout_path, stderr_path, submit_line = (
                                    self.get_job_details_from_scontrol(
                                        conn, job_info.job_id, hostname
                                    )
                                )
                                if stdout_path:
                                    job_info.stdout_file = stdout_path
                                if stderr_path:
                                    job_info.stderr_file = stderr_path
                                # Only update submit_line if it's not already set
                                if submit_line and not job_info.submit_line:
                                    job_info.submit_line = submit_line
                                logger.debug(
                                    f"Got job details from scontrol for {job_info.state} job {job_info.job_id}"
                                )
                            except Exception as e:
                                # If scontrol fails, keep the paths from squeue
                                logger.debug(
                                    f"Could not get output paths from scontrol for {job_info.job_id}: {e}"
                                )

                                # Log if paths look suspicious or try to expand placeholders
                                if job_info.stdout_file and (
                                    job_info.stdout_file.endswith(
                                        (".sh", ".sbatch", ".bash", ".slurm")
                                    )
                                    or "/submit/" in job_info.stdout_file
                                    or "/scripts/" in job_info.stdout_file
                                    or "%" in job_info.stdout_file
                                ):
                                    if "%" in job_info.stdout_file:
                                        # Try to expand SLURM placeholders ourselves
                                        from .parser import SlurmParser

                                        var_dict = {
                                            "j": job_info.job_id,
                                            "i": job_info.job_id,
                                            "u": job_info.user or "",
                                            "x": job_info.name or "",
                                        }
                                        expanded_stdout = (
                                            SlurmParser.expand_slurm_path_vars(
                                                job_info.stdout_file, var_dict
                                            )
                                        )
                                        if expanded_stdout != job_info.stdout_file:
                                            job_info.stdout_file = expanded_stdout
                                            logger.debug(
                                                f"Expanded stdout path for running job {job_info.job_id}"
                                            )
                                        if (
                                            job_info.stderr_file
                                            and "%" in job_info.stderr_file
                                        ):
                                            expanded_stderr = (
                                                SlurmParser.expand_slurm_path_vars(
                                                    job_info.stderr_file, var_dict
                                                )
                                            )
                                            if expanded_stderr != job_info.stderr_file:
                                                job_info.stderr_file = expanded_stderr
                                                logger.debug(
                                                    f"Expanded stderr path for running job {job_info.job_id}"
                                                )
                                    else:
                                        logger.warning(
                                            f"Running job {job_info.job_id} has suspicious stdout path: {job_info.stdout_file}"
                                        )

                        # For PENDING jobs, paths may not be set yet, so skip the check
                        # For other states, we rely on cached data

                        jobs.append(job_info)
                    except Exception as e:
                        logger.debug(f"Failed to parse squeue line: {line}, error: {e}")

        except Exception as e:
            logger.debug(f"Error getting active jobs: {e}")

        return jobs

    def get_job_final_state(
        self,
        conn: SSHConnection,
        hostname: str,
        job_id: str,
    ) -> Optional[JobInfo]:
        """
        Get final state of a specific job from sacct.

        This is used to fetch the final state of jobs that have completed/failed/cancelled
        but are no longer in the active queue.

        For array jobs with bracket notation (e.g., "24322_[0-3%4]"), queries the base
        job ID and aggregates states from individual tasks.

        Args:
            conn: SSH connection
            hostname: Target hostname
            job_id: Job ID to query (can include array notation like "123_[0-3%4]")

        Returns:
            JobInfo with final state, or None if job not found
        """
        try:
            # Get cluster-specific available fields
            available_fields = self.get_available_sacct_fields(conn, hostname)
            format_str = ",".join(available_fields)

            # For array jobs with brackets, extract base job ID
            query_job_id = job_id
            is_array_parent = False
            if "_[" in job_id and "]" in job_id:
                # This is an array job parent entry like "24322_[0-3%4]"
                query_job_id = job_id.split("_[")[0]
                is_array_parent = True
                logger.debug(
                    f"Array parent job detected: {job_id}, querying base ID: {query_job_id}"
                )

            # Query sacct for this specific job
            cmd = f"sacct -X --format={format_str} --parsable2 --noheader --jobs={query_job_id}"

            logger.debug(f"Fetching final state for job {job_id} on {hostname}")
            result = conn.run(cmd, hide=True, timeout=30, warn=True, pty=True)

            if not result.ok or not result.stdout.strip():
                logger.debug(f"No sacct data found for job {job_id} on {hostname}")
                return None

            lines = result.stdout.strip().split("\n")

            if is_array_parent and len(lines) > 1:
                # For array parent, aggregate info from all tasks
                # Use first task's info as base, but aggregate states
                first_line = lines[0].strip().split("|")
                if len(first_line) >= len(available_fields):
                    job_info = self.parser.from_sacct_fields(
                        first_line, hostname, available_fields
                    )

                    # Restore the original job_id with brackets
                    job_info.job_id = job_id

                    # Count states across all tasks
                    states = {}
                    for line in lines:
                        fields = line.strip().split("|")
                        if len(fields) >= 3:
                            state_str = fields[2]
                            state = self.parser.map_slurm_state(state_str, from_sacct=True)
                            states[state.value] = states.get(state.value, 0) + 1

                    # Determine overall state (prioritize failures/cancellations)
                    if "F" in states or "TO" in states:
                        from ..models.job import JobState
                        job_info.state = JobState.FAILED if "F" in states else JobState.TIMEOUT
                    elif "CA" in states:
                        from ..models.job import JobState
                        job_info.state = JobState.CANCELLED
                    # else keep COMPLETED or whatever the first task had

                    logger.info(
                        f"Retrieved final state for array job {job_id}: {job_info.state.value} "
                        f"(task states: {states})"
                    )
                    return job_info
            else:
                # Single job or single task
                line = lines[0]
                fields = line.strip().split("|")

                if len(fields) >= len(available_fields):
                    job_info = self.parser.from_sacct_fields(
                        fields, hostname, available_fields
                    )
                    logger.info(
                        f"Retrieved final state for job {job_id}: {job_info.state.value}"
                    )
                    return job_info
                else:
                    logger.warning(
                        f"Invalid sacct output for job {job_id}: got {len(fields)} fields, expected {len(available_fields)}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Error fetching final state for job {job_id}: {e}")
            return None

    def get_completed_jobs(
        self,
        conn: SSHConnection,
        hostname: str,
        since: Optional[datetime] = None,
        user: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        state_filter: Optional[str] = None,
        exclude_job_ids: Optional[List[str]] = None,
        skip_user_detection: bool = False,
        limit: Optional[int] = None,
        cached_completed_ids: Optional[set] = None,  # NEW: IDs to skip
    ) -> List[JobInfo]:
        """Get completed jobs using sacct."""
        # Check if we need chunking for large time ranges
        if since:
            # Handle both timezone-aware and naive datetimes
            now = datetime.now() if since.tzinfo is None else datetime.now(since.tzinfo)
            time_range_days = (now - since).days
            if time_range_days > 60:  # Only chunk for very large ranges (2+ months)
                logger.debug(f"Using chunked query for {time_range_days} days")
                return self._get_completed_jobs_chunked(
                    conn,
                    hostname,
                    since,
                    user,
                    job_ids,
                    state_filter,
                    exclude_job_ids,
                    skip_user_detection,
                    limit,
                    cached_completed_ids,
                )

        # Normal single query for small time ranges
        return self._get_completed_jobs_single(
            conn,
            hostname,
            since,
            user,
            job_ids,
            state_filter,
            exclude_job_ids,
            skip_user_detection,
            cached_completed_ids,
        )

    def _get_completed_jobs_single(
        self,
        conn: SSHConnection,
        hostname: str,
        since: Optional[datetime] = None,
        user: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        state_filter: Optional[str] = None,
        exclude_job_ids: Optional[List[str]] = None,
        skip_user_detection: bool = False,
        cached_completed_ids: Optional[set] = None,
    ) -> List[JobInfo]:
        """Single sacct query without chunking."""
        jobs = []

        try:
            # Get cluster-specific available fields
            logger.debug(f"Getting available fields for {hostname}")
            available_fields = self.get_available_sacct_fields(conn, hostname)
            logger.debug(f"Selected fields for {hostname}: {available_fields}")
            format_str = ",".join(available_fields)
            cmd = f"sacct -X --format={format_str} --parsable2 --noheader"

            if since:
                # Check if we can use relative time format (more reliable across timezones)
                now = datetime.now(timezone.utc) if since.tzinfo else datetime.now()
                time_diff = now - since

                # If the time difference is less than 7 days, use relative format
                if time_diff.total_seconds() > 0 and time_diff.days < 7:
                    hours_ago = int(time_diff.total_seconds() / 3600)
                    if hours_ago > 0:
                        # Use relative time format which is timezone-agnostic
                        cmd += f" --starttime=now-{hours_ago}hours"
                        logger.debug(
                            f"Using relative starttime=now-{hours_ago}hours for sacct on {hostname}"
                        )
                    else:
                        # Very recent, use absolute time
                        since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
                        cmd += f" --starttime={since_str}"
                        logger.debug(
                            f"Using starttime={since_str} for sacct on {hostname} (input was {since})"
                        )
                else:
                    # Use absolute time for older queries or future times
                    since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
                    cmd += f" --starttime={since_str}"
                    logger.debug(
                        f"Using starttime={since_str} for sacct on {hostname} (input was {since})"
                    )

            if user:
                query_user = user
                logger.debug(f"Using provided user filter: {user}")
            elif not skip_user_detection:
                query_user = self.get_username(conn, hostname=hostname)
                logger.debug(f"Auto-detected current user: {query_user}")
            else:
                query_user = None
                logger.debug("Querying all users (no user filter)")

            if query_user:
                cmd += f" --user={query_user}"
            if job_ids:
                cmd += f" --jobs={','.join(job_ids)}"
            if state_filter:
                cmd += f" --state={state_filter}"

            # For large time ranges (>2 weeks), consider chunking the query
            # to avoid SLURM timeouts with massive datasets
            if since:
                now = (
                    datetime.now()
                    if since.tzinfo is None
                    else datetime.now(since.tzinfo)
                )
                time_range_days = (now - since).days
            else:
                time_range_days = 0
            if time_range_days > 14:
                logger.debug(
                    f"Large time range detected ({time_range_days} days), may need chunking if query fails"
                )

            logger.debug(f"Running sacct command on {hostname}: {cmd}")
            # Try with PTY enabled to force output flushing
            # Increase timeout for potentially large queries
            timeout = (
                120 if since and "w" in str(since) else 180
            )  # Longer timeout for month queries
            result = conn.run(cmd, hide=True, timeout=timeout, warn=True, pty=True)

            # Only log details if there are issues or verbose debugging needed
            if not result.ok:
                logger.debug(
                    f"sacct command failed: exit={result.exited}, stderr: {result.stderr}"
                )
            elif len(result.stdout) == 0:
                logger.debug(f"No jobs found for {hostname} since {since}")
                # Get cluster's current time for debugging
                try:
                    cluster_time_result = conn.run(
                        "date '+%Y-%m-%dT%H:%M:%S%z'", hide=True
                    )
                    logger.debug(
                        f"Cluster {hostname} current time: {cluster_time_result.stdout.strip()}"
                    )
                    logger.debug(f"Query was for jobs since: {since}")

                    # Also check if there are ANY recent jobs to understand the issue
                    test_result = conn.run(
                        f"sacct -X --format=JobID,Submit --parsable2 --noheader "
                        f"--starttime=now-7days --user={query_user} | head -5",
                        hide=True,
                    )
                    if test_result.stdout.strip():
                        logger.debug(
                            f"Recent jobs found on {hostname}: {test_result.stdout.strip()[:200]}"
                        )
                    else:
                        logger.debug(
                            f"No recent jobs found on {hostname} in last 7 days"
                        )
                except Exception as e:
                    logger.debug(f"Debug query failed: {e}")
            else:
                logger.debug(
                    f"sacct found {len(result.stdout.strip().split(chr(10)))} lines for {hostname}"
                )

            skipped_cached = 0
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue

                fields = line.strip().split("|")
                if len(fields) >= len(available_fields):
                    job_id = fields[0].split(".")[0]

                    if exclude_job_ids and job_id in exclude_job_ids:
                        continue

                    if cached_completed_ids and job_id in cached_completed_ids:
                        skipped_cached += 1
                        continue

                    try:
                        state = self.parser.map_slurm_state(fields[2], from_sacct=True)

                        if state_filter and state.value != state_filter:
                            continue

                        job_info = self.parser.from_sacct_fields(
                            fields, hostname, available_fields
                        )
                        jobs.append(job_info)
                        logger.debug(
                            f"Parsed sacct job {fields[0]} on {hostname}: state={state.value}, user={fields[3] if len(fields) > 3 else 'unknown'}"
                        )  # Debug

                        # For recently completed jobs, try to get correct output paths from scontrol
                        # This might work if the job recently completed and is still in SLURM's memory
                        # Also try to fix paths that have unexpanded SLURM placeholders
                        if job_info and (
                            (
                                job_info.stdout_file
                                and (
                                    job_info.stdout_file.endswith(
                                        (".sh", ".sbatch", ".bash", ".slurm")
                                    )
                                    or "/submit/" in job_info.stdout_file
                                    or "/scripts/" in job_info.stdout_file
                                    or "%" in job_info.stdout_file  # SLURM placeholder
                                )
                            )
                            or (
                                job_info.stderr_file
                                and (
                                    job_info.stderr_file.endswith(
                                        (".sh", ".sbatch", ".bash", ".slurm")
                                    )
                                    or "/submit/" in job_info.stderr_file
                                    or "/scripts/" in job_info.stderr_file
                                    or "%" in job_info.stderr_file  # SLURM placeholder
                                )
                            )
                        ):
                            try:
                                stdout_path, stderr_path = self.get_job_output_files(
                                    conn, job_info.job_id, hostname
                                )
                                if stdout_path and stdout_path != job_info.stdout_file:
                                    job_info.stdout_file = stdout_path
                                if stderr_path and stderr_path != job_info.stderr_file:
                                    job_info.stderr_file = stderr_path
                                logger.debug(
                                    f"Corrected output paths for completed job {job_info.job_id}"
                                )
                            except Exception:
                                # scontrol likely failed because job is too old
                                # Try to expand SLURM placeholders ourselves
                                from .parser import SlurmParser

                                var_dict = {
                                    "j": job_info.job_id,
                                    "i": job_info.job_id,
                                    "u": job_info.user or "",
                                    "x": job_info.name or "",
                                }
                                if job_info.stdout_file and "%" in job_info.stdout_file:
                                    expanded_stdout = (
                                        SlurmParser.expand_slurm_path_vars(
                                            job_info.stdout_file, var_dict
                                        )
                                    )
                                    if expanded_stdout != job_info.stdout_file:
                                        job_info.stdout_file = expanded_stdout
                                        logger.debug(
                                            f"Expanded stdout path for job {job_info.job_id}"
                                        )
                                if job_info.stderr_file and "%" in job_info.stderr_file:
                                    expanded_stderr = (
                                        SlurmParser.expand_slurm_path_vars(
                                            job_info.stderr_file, var_dict
                                        )
                                    )
                                    if expanded_stderr != job_info.stderr_file:
                                        job_info.stderr_file = expanded_stderr
                                        logger.debug(
                                            f"Expanded stderr path for job {job_info.job_id}"
                                        )
                                logger.debug(
                                    f"Could not get paths from scontrol for completed job {job_info.job_id}, used placeholder expansion"
                                )
                    except Exception as e:
                        logger.debug(f"Failed to parse sacct line: {line}, error: {e}")

            # Log how many cached jobs we skipped
            if skipped_cached > 0:
                logger.info(
                    f"Skipped {skipped_cached} already-cached completed jobs from sacct query on {hostname}"
                )

        except Exception as e:
            logger.debug(f"Error fetching completed jobs: {e}")

        return jobs

    def _get_completed_jobs_chunked(
        self,
        conn: SSHConnection,
        hostname: str,
        since: datetime,
        user: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        state_filter: Optional[str] = None,
        exclude_job_ids: Optional[List[str]] = None,
        skip_user_detection: bool = False,
        limit: Optional[int] = None,
        cached_completed_ids: Optional[set] = None,
    ) -> List[JobInfo]:
        """Get completed jobs using chunked queries to avoid timeouts."""

        all_jobs = []
        chunk_size_days = 7  # Query 1 week at a time
        # Handle timezone-aware datetime
        current_end = (
            datetime.now() if since.tzinfo is None else datetime.now(since.tzinfo)
        )
        current_start = max(since, current_end - timedelta(days=chunk_size_days))

        while current_start >= since and (not limit or len(all_jobs) < limit):
            logger.debug(
                f"Chunked query for {hostname}: {current_start.date()} to {current_end.date()}"
            )

            try:
                # Query this chunk
                chunk_jobs = self._get_completed_jobs_single(
                    conn,
                    hostname,
                    current_start,
                    user,
                    job_ids,
                    state_filter,
                    exclude_job_ids,
                    skip_user_detection,
                    cached_completed_ids,  # Pass through to single query
                )

                # Add to results
                all_jobs.extend(chunk_jobs)
                logger.debug(
                    f"Got {len(chunk_jobs)} jobs from chunk, total: {len(all_jobs)}"
                )

                # Stop early if we hit the limit
                if limit and len(all_jobs) >= limit:
                    logger.debug(f"Hit limit {limit}, stopping chunked query")
                    break

            except Exception as e:
                logger.debug(
                    f"Chunk query failed for {current_start.date()}-{current_end.date()}: {e}"
                )

            current_end = current_start
            current_start = max(since, current_end - timedelta(days=chunk_size_days))

            # Prevent infinite loop
            if current_end <= since:
                break

        return all_jobs[:limit] if limit else all_jobs

    def get_username(
        self, conn: SSHConnection, user: str | None = None, hostname: str = "unknown"
    ) -> Optional[str]:
        """Get the username to use for SLURM queries.

        Uses caching to avoid repeated queries to the same host.
        """
        if user:
            return user

        # Check cache first
        if hostname in self._username_cache:
            cached_username = self._username_cache[hostname]
            logger.debug(f"Using cached username for {hostname}: {cached_username}")
            return cached_username

        # Try to detect username
        detected_username = None

        try:
            # Increase timeout to handle slow SSH connections
            result = conn.run("whoami", hide=True, timeout=10, warn=True, pty=True)
            if result.ok and result.stdout.strip():
                detected_username = result.stdout.strip()
                logger.debug(f"Detected username from whoami: {detected_username}")
        except Exception as e:
            logger.warning(f"Failed to get current user via whoami: {e}")

        # FALLBACK: Try to get username from SSH connection object
        if not detected_username:
            try:
                if hasattr(conn, 'user'):
                    detected_username = conn.user
                    logger.info(f"Using SSH connection username as fallback: {detected_username}")
            except Exception as e:
                logger.debug(f"Could not get username from SSH connection: {e}")

        # Last resort - try environment variable from connection
        if not detected_username:
            try:
                result = conn.run("echo $USER", hide=True, timeout=10, warn=True, pty=True)
                if result.ok and result.stdout.strip():
                    detected_username = result.stdout.strip()
                    logger.info(f"Got username from $USER environment variable: {detected_username}")
            except Exception as e:
                logger.debug(f"Could not get username from $USER: {e}")

        # Cache the result if we successfully detected a username
        if detected_username:
            self._username_cache[hostname] = detected_username
            logger.info(f"Cached username for {hostname}: {detected_username}")
            return detected_username

        logger.error("⚠️  Could not determine username - SLURM query will fetch ALL users' jobs!")
        return None

    def get_job_details(
        self, conn: SSHConnection, job_id: str, hostname: str, user: str | None = None
    ) -> Optional[JobInfo]:
        """Get detailed information about a specific job."""
        try:
            job_info = None

            user = user or self.get_username(conn, hostname=hostname)

            format_str = "|".join(SQUEUE_FIELDS)
            result = conn.run(
                f"squeue --user {user} -j {job_id} --format='{format_str}' --noheader",
                hide=True,
                timeout=30,  # Increased from 10s to handle slow SLURM responses
                warn=True,  # Don't throw exception on "Invalid job id"
            )

            if result.ok and result.stdout.strip():
                fields = result.stdout.strip().split("|")
                if len(fields) >= len(SQUEUE_FIELDS):
                    job_info = self.parser.from_squeue_fields(fields, hostname)

            if not job_info:
                available_fields = self.get_available_sacct_fields(conn, hostname)
                format_str = ",".join(available_fields)
                result = conn.run(
                    f"sacct -X -j {job_id} --format={format_str} --parsable2 --noheader --user {user}",
                    hide=True,
                    timeout=30,  # Increased from 10s to handle slow SLURM responses
                    warn=True,  # Don't throw exception if job not found in sacct either
                )

                if result.ok and result.stdout.strip():
                    lines = result.stdout.strip().split("\n")
                    for line in lines:
                        fields = line.strip().split("|")
                        if (
                            len(fields) >= len(available_fields)
                            and "." not in fields[0]
                        ):  # Avoid job steps
                            job_info = self.parser.from_sacct_fields(
                                fields, hostname, available_fields
                            )
                            break

            # IMPORTANT: squeue often returns the script path instead of actual output paths
            # This happens for all job states, not just running/pending
            # Always try to get the correct output paths from scontrol when possible
            if job_info:
                # Try to get actual output paths from scontrol
                # This is especially important for completed jobs where squeue returns wrong paths
                try:
                    stdout_path, stderr_path = self.get_job_output_files(
                        conn, job_id, hostname
                    )
                    if stdout_path:
                        job_info.stdout_file = stdout_path
                    if stderr_path:
                        job_info.stderr_file = stderr_path
                except Exception:
                    # If scontrol fails (e.g., job too old), try to expand SLURM placeholders
                    if job_info.stdout_file and "%" in job_info.stdout_file:
                        from .parser import SlurmParser

                        var_dict = {
                            "j": job_info.job_id,
                            "i": job_info.job_id,
                            "u": job_info.user or "",
                            "x": job_info.name or "",
                        }
                        expanded_stdout = SlurmParser.expand_slurm_path_vars(
                            job_info.stdout_file, var_dict
                        )
                        if expanded_stdout != job_info.stdout_file:
                            job_info.stdout_file = expanded_stdout
                            logger.debug(
                                f"Expanded stdout path for job {job_info.job_id}"
                            )
                        if job_info.stderr_file and "%" in job_info.stderr_file:
                            expanded_stderr = SlurmParser.expand_slurm_path_vars(
                                job_info.stderr_file, var_dict
                            )
                            if expanded_stderr != job_info.stderr_file:
                                job_info.stderr_file = expanded_stderr
                                logger.debug(
                                    f"Expanded stderr path for job {job_info.job_id}"
                                )
                    # They might still be wrong, but at least placeholders are expanded
                    pass

                # Merge cached submit_line if available
                # This is important for running jobs where SLURM doesn't provide submit_line
                if not job_info.submit_line:
                    try:
                        from ..cache import get_cache

                        cache = get_cache()
                        cached_data = cache.get_cached_job(job_id, hostname)
                        if (
                            cached_data
                            and cached_data.job_info
                            and cached_data.job_info.submit_line
                        ):
                            job_info.submit_line = cached_data.job_info.submit_line
                            logger.debug(f"Merged cached submit_line for job {job_id}")
                    except Exception as e:
                        logger.debug(
                            f"Could not merge cached submit_line for job {job_id}: {e}"
                        )

            return job_info

        except Exception as e:
            logger.debug(f"Failed to get job details for {job_id}: {e}")

        return None

    def cancel_job(self, conn: SSHConnection, job_id: str) -> bool:
        """Cancel a SLURM job."""
        try:
            conn.run(f"scancel {job_id}", hide=False)
            return True
        except Exception as e:
            logger.debug(f"Failed to cancel job {job_id}: {e}")
            return False

    def get_job_details_from_scontrol(
        self, conn: SSHConnection, job_id: str, hostname: str, user: str | None = None
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Get job details including output files and submit_line using scontrol show job.

        Args:
            conn: SSH connection to the cluster
            job_id: SLURM job ID
            hostname: Cluster hostname

        Returns:
            Tuple of (stdout_path, stderr_path, submit_line). Any may be None if not found.
        """
        try:
            logger.debug(f"Getting job details for job {job_id} on {hostname}")

            user = user or self.get_username(conn, hostname=hostname)

            result = conn.run(
                f"scontrol show job {job_id}",
                hide=True,
                timeout=10,
                warn=True,
                pty=True,
            )

            if not result.ok:
                logger.debug(f"scontrol show job failed for {job_id}: {result.stderr}")
                return None, None, None

            stdout_path = None
            stderr_path = None
            submit_line = None

            for line in result.stdout.split("\n"):
                line = line.strip()
                if "StdOut=" in line:
                    # Extract StdOut path - format is typically "StdOut=/path/to/file"
                    for part in line.split():
                        if part.startswith("StdOut="):
                            stdout_path = part.split("=", 1)[1]
                            break
                elif "StdErr=" in line:
                    # Extract StdErr path - format is typically "StdErr=/path/to/file"
                    for part in line.split():
                        if part.startswith("StdErr="):
                            stderr_path = part.split("=", 1)[1]
                            break
                elif "Command=" in line:
                    # Extract Command (submit_line) - format is "Command=/path/to/script.sh"
                    for part in line.split():
                        if part.startswith("Command="):
                            submit_line = part.split("=", 1)[1]
                            break

            logger.debug(
                f"Found job details for job {job_id}: stdout={stdout_path}, stderr={stderr_path}, submit_line={submit_line}"
            )
            return stdout_path, stderr_path, submit_line

        except Exception as e:
            logger.debug(f"Failed to get job details for job {job_id}: {e}")
            return None, None, None

    def get_job_output_files(
        self, conn: SSHConnection, job_id: str, hostname: str, user: str | None = None
    ) -> tuple[Optional[str], Optional[str]]:
        """Get stdout and stderr file paths for a job using scontrol show job.

        Args:
            conn: SSH connection to the cluster
            job_id: SLURM job ID
            hostname: Cluster hostname

        Returns:
            Tuple of (stdout_path, stderr_path). Either may be None if not found.
        """
        # Use the new function and just return the output files
        stdout_path, stderr_path, _ = self.get_job_details_from_scontrol(
            conn, job_id, hostname, user
        )
        return stdout_path, stderr_path

    def read_job_output_compressed(
        self,
        conn: SSHConnection,
        job_id: str,
        hostname: str,
        output_type: str = "stdout",
    ) -> Optional[dict]:
        """Read and compress job output on remote host.

        Args:
            conn: SSH connection to the cluster
            job_id: SLURM job ID
            hostname: Cluster hostname
            output_type: Either "stdout" or "stderr"

        Returns:
            Dictionary with compressed data and metadata or None
        """
        import base64

        try:
            stdout_path, stderr_path = self.get_job_output_files(conn, job_id, hostname)

            file_path = stdout_path if output_type == "stdout" else stderr_path
            if not file_path:
                logger.debug(f"No {output_type} file path found for job {job_id}")
                return None

            # Check file size first
            size_result = conn.run(
                f"stat -c%s '{file_path}' 2>/dev/null", hide=True, warn=True
            )

            if not size_result.ok:
                logger.debug(f"File not found: {file_path}")
                return None

            file_size = int(size_result.stdout.strip())
            logger.debug(f"File {file_path} size: {file_size} bytes")

            # Set size limits and compression threshold
            MAX_SIZE = 100 * 1024 * 1024  # 100MB max
            COMPRESS_THRESHOLD = 1024  # 1KB - compress anything larger

            if file_size > MAX_SIZE:
                # For very large files, read only the tail
                logger.warning(
                    f"File {file_path} is {file_size} bytes, reading last 10MB only"
                )
                result = conn.run(
                    f"tail -c 10485760 '{file_path}' | gzip -9 | base64 -w0",
                    hide=True,
                    timeout=60,
                    warn=True,
                )

                if result.ok:
                    return {
                        "compressed": True,
                        "data": result.stdout,
                        "original_size": file_size,
                        "truncated": True,
                        "truncated_size": 10485760,
                        "compression": "gzip",
                    }
            elif file_size > COMPRESS_THRESHOLD:
                # Compress on remote host
                logger.debug(f"Compressing {output_type} on remote host")
                result = conn.run(
                    f"gzip -9 -c '{file_path}' | base64 -w0",
                    hide=True,
                    timeout=60,
                    warn=True,
                )

                if result.ok:
                    return {
                        "compressed": True,
                        "data": result.stdout,
                        "original_size": file_size,
                        "truncated": False,
                        "compression": "gzip",
                    }
            else:
                # Small file - just read directly
                result = conn.run(
                    f"cat '{file_path}'", hide=True, timeout=30, warn=True
                )

                if result.ok:
                    # Base64 encode for consistency
                    encoded = base64.b64encode(result.stdout.encode("utf-8")).decode(
                        "ascii"
                    )
                    return {
                        "compressed": False,
                        "data": encoded,
                        "original_size": file_size,
                        "truncated": False,
                        "compression": "none",
                    }

            return None

        except Exception as e:
            logger.error(
                f"Failed to read compressed {output_type} for job {job_id}: {e}"
            )
            return None

    def read_job_output_content(
        self,
        conn: SSHConnection,
        job_id: str,
        hostname: str,
        output_type: str = "stdout",
    ) -> Optional[str]:
        """Read the content of a job's output file (stdout or stderr).

        Args:
            conn: SSH connection to the cluster
            job_id: SLURM job ID
            hostname: Cluster hostname
            output_type: Either "stdout" or "stderr"

        Returns:
            File content as string, or None if file not found/readable
        """
        try:
            stdout_path, stderr_path = self.get_job_output_files(conn, job_id, hostname)

            file_path = stdout_path if output_type == "stdout" else stderr_path
            if not file_path:
                logger.debug(f"No {output_type} file path found for job {job_id}")
                return None

            logger.debug(
                f"Reading {output_type} content from {file_path} for job {job_id}"
            )
            result = conn.run(
                f"cat '{file_path}'", hide=True, timeout=30, warn=True, pty=True
            )

            if not result.ok:
                logger.debug(f"Failed to read {file_path}: {result.stderr}")
                return None

            return result.stdout

        except Exception as e:
            logger.debug(f"Failed to read {output_type} for job {job_id}: {e}")
            return None

    def get_job_batch_script(
        self, conn: SSHConnection, job_id: str, hostname: str
    ) -> Optional[str]:
        """Get the batch script content for a job using scontrol write batch_script.

        Args:
            conn: SSH connection to the cluster
            job_id: SLURM job ID
            hostname: Cluster hostname

        Returns:
            Batch script content as string, or None if not available
        """
        try:
            logger.debug(f"Getting batch script for job {job_id} on {hostname}")
            result = conn.run(
                f"scontrol write batch_script {job_id} -",
                hide=True,
                timeout=30,
                warn=True,
                pty=True,
            )

            if not result.ok:
                logger.debug(
                    f"scontrol write batch_script failed for {job_id}: {result.stderr}"
                )
                return None

            # The batch script content is in stdout
            script_content = result.stdout.strip()
            if script_content:
                logger.debug(
                    f"Retrieved batch script for job {job_id} ({len(script_content)} chars)"
                )
                return script_content
            else:
                logger.debug(f"No batch script content found for job {job_id}")
                return None

        except Exception as e:
            logger.debug(f"Failed to get batch script for job {job_id}: {e}")
            return None

    def check_slurm_availability(self, conn: SSHConnection, hostname: str) -> bool:
        """Check if SLURM is available on the host."""
        try:
            # Try a simple squeue command first - this is more reliable than 'which'
            result = conn.run("squeue --version", hide=True, timeout=5)
            if result.ok:
                return True

            # Fallback to 'which squeue'
            result2 = conn.run("which squeue", hide=True, timeout=3)
            return result2.ok

        except Exception as e:
            logger.debug(f"SLURM not available on {hostname}: {e}")
            # For cache/connection issues, assume SLURM is available and let the actual commands fail gracefully
            if "No existing session" in str(e) or "Connection" in str(e):
                logger.debug(
                    f"Assuming SLURM available on {hostname} due to connection issue"
                )
                return True
            return False
