"""Slurm query operations (squeue/sacct/scontrol)."""

from datetime import datetime, timedelta, timezone
import time
from typing import Any, List, Optional, Protocol

from ..models.job import JobInfo, JobState
from ..models.partition import PartitionResources
from ..parsers.slurm import SlurmParser
from ..parsers.partition import PartitionParser
from ..utils.logging import setup_logger
from .fields import SQUEUE_FIELDS
from .output import SlurmOutput


class SSHConnection(Protocol):
    """Protocol for SSH connection objects."""

    def run(self, command: str, **kwargs) -> Any: ...


logger = setup_logger(__name__, "INFO")


class SlurmQuery:
    """Handles Slurm query commands and parsing results."""

    def __init__(self, output: SlurmOutput | None = None):
        self.parser = SlurmParser()
        self._available_fields_cache = {}
        self._username_cache = {}
        self._partition_cache: dict[str, tuple[float, List[PartitionResources]]] = {}
        self._partition_cache_ttl = 20.0
        self.output = output or SlurmOutput()

    def get_available_sacct_fields(
        self, conn: SSHConnection, hostname: str
    ) -> List[str]:
        """Get list of available sacct fields for this Slurm cluster."""
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

    def get_partition_state(
        self,
        conn: SSHConnection,
        hostname: str,
        force_refresh: bool = False,
    ) -> tuple[List[PartitionResources], bool, float, bool]:
        """Get partition resource state using sinfo.

        Returns:
            (partitions, cached, cache_age_seconds, stale)
        """
        now = time.time()
        cache_entry = self._partition_cache.get(hostname)
        if cache_entry:
            cached_at, cached_data = cache_entry
            cache_age = now - cached_at
            if not force_refresh and cache_age < self._partition_cache_ttl:
                return cached_data, True, cache_age, False

        formats = [
            (
                "%P|%a|%D|%t|%C|%G|%g",
                ["partition", "availability", "nodes", "state", "cpus", "gres", "gres_used"],
            ),
            (
                "%P|%a|%D|%t|%C|%G",
                ["partition", "availability", "nodes", "state", "cpus", "gres"],
            ),
            (
                "%P|%a|%D|%t|%C",
                ["partition", "availability", "nodes", "state", "cpus"],
            ),
        ]

        last_error: Optional[Exception] = None
        for fmt, fields in formats:
            cmd = f"sinfo -a -h -o '{fmt}'"
            try:
                logger.debug(f"Running sinfo on {hostname}: {cmd}")
                result = conn.run(cmd, hide=True, timeout=20, warn=True, pty=True)
                if not result.ok or not result.stdout:
                    logger.debug(
                        f"sinfo command failed on {hostname} (fmt={fmt}): {result.stderr}"
                    )
                    continue

                partitions = PartitionParser.parse_sinfo_output(result.stdout, fields)
                partitions.sort(key=lambda p: p.name)
                self._partition_cache[hostname] = (now, partitions)
                return partitions, False, 0.0, False
            except Exception as e:
                last_error = e
                logger.debug(f"sinfo format failed on {hostname} (fmt={fmt}): {e}")

        if cache_entry:
            cached_at, cached_data = cache_entry
            cache_age = now - cached_at
            logger.warning(
                f"Returning cached partition data for {hostname} after sinfo failure"
            )
            return cached_data, True, cache_age, True

        if last_error:
            logger.debug(f"Failed to fetch partition state for {hostname}: {last_error}")
        return [], False, 0.0, False

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
        pending_ids = []

        try:
            format_str = "|".join(SQUEUE_FIELDS)
            cmd = f"squeue -r --format='{format_str}' --noheader"

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

                        if job_info.state in [JobState.RUNNING, JobState.PENDING]:
                            pending_ids.append(job_info.job_id)
                            if job_info.stdout_file and (
                                job_info.stdout_file.endswith(
                                    (".sh", ".sbatch", ".bash", ".slurm")
                                )
                                or "/submit/" in job_info.stdout_file
                                or "/scripts/" in job_info.stdout_file
                                or "%" in job_info.stdout_file
                            ):
                                if "%" in job_info.stdout_file:
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

                        jobs.append(job_info)
                    except Exception as e:
                        logger.debug(f"Failed to parse squeue line: {line}, error: {e}")

        except Exception as e:
            logger.debug(f"Error getting active jobs: {e}")

        if pending_ids:
            try:
                details = self.output.get_job_details_from_scontrol_batch(
                    conn, pending_ids, hostname
                )
                if details:
                    for job in jobs:
                        if job.job_id in details:
                            stdout_path, stderr_path, submit_line = details[job.job_id]
                            if stdout_path:
                                job.stdout_file = stdout_path
                            if stderr_path:
                                job.stderr_file = stderr_path
                            if submit_line and not job.submit_line:
                                job.submit_line = submit_line
            except Exception as e:
                logger.debug(f"Batch scontrol failed for active jobs: {e}")

        return jobs

    def get_job_final_state(
        self,
        conn: SSHConnection,
        hostname: str,
        job_id: str,
    ) -> Optional[JobInfo]:
        """Get final state of a specific job from sacct."""
        try:
            available_fields = self.get_available_sacct_fields(conn, hostname)
            format_str = ",".join(available_fields)

            query_job_id = job_id
            is_array_parent = False
            if "_[" in job_id and "]" in job_id:
                query_job_id = job_id.split("_[")[0]
                is_array_parent = True
                logger.debug(
                    f"Array parent job detected: {job_id}, querying base ID: {query_job_id}"
                )

            cmd = f"sacct -X --format={format_str} --parsable2 --noheader --jobs={query_job_id}"

            logger.debug(f"Fetching final state for job {job_id} on {hostname}")
            result = conn.run(cmd, hide=True, timeout=30, warn=True, pty=True)

            if not result.ok or not result.stdout.strip():
                logger.debug(f"No sacct data found for job {job_id} on {hostname}")
                return None

            lines = result.stdout.strip().split("\n")

            if is_array_parent and len(lines) > 1:
                first_line = lines[0].strip().split("|")
                if len(first_line) >= len(available_fields):
                    job_info = self.parser.from_sacct_fields(
                        first_line, hostname, available_fields
                    )

                    job_info.job_id = job_id

                    states = {}
                    for line in lines:
                        fields = line.strip().split("|")
                        if len(fields) >= 3:
                            state_str = fields[2]
                            state = self.parser.map_slurm_state(
                                state_str, from_sacct=True
                            )
                            states[state.value] = states.get(state.value, 0) + 1

                    if "F" in states or "TO" in states:
                        job_info.state = (
                            JobState.FAILED if "F" in states else JobState.TIMEOUT
                        )
                    elif "CA" in states:
                        job_info.state = JobState.CANCELLED

                    logger.info(
                        f"Retrieved final state for array job {job_id}: {job_info.state.value} "
                        f"(task states: {states})"
                    )
                    return job_info
            else:
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
        cached_completed_ids: Optional[set] = None,
    ) -> List[JobInfo]:
        """Get completed jobs using sacct."""
        if since:
            now = datetime.now() if since.tzinfo is None else datetime.now(since.tzinfo)
            time_range_days = (now - since).days
            if time_range_days > 60:
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
        needs_path_fix: list[str] = []

        try:
            logger.debug(f"Getting available fields for {hostname}")
            available_fields = self.get_available_sacct_fields(conn, hostname)
            logger.debug(f"Selected fields for {hostname}: {available_fields}")
            format_str = ",".join(available_fields)
            cmd = f"sacct -X --format={format_str} --parsable2 --noheader"

            if since:
                now = datetime.now(timezone.utc) if since.tzinfo else datetime.now()
                time_diff = now - since

                if time_diff.total_seconds() > 0 and time_diff.days < 7:
                    hours_ago = int(time_diff.total_seconds() / 3600)
                    if hours_ago > 0:
                        cmd += f" --starttime=now-{hours_ago}hours"
                        logger.debug(
                            f"Using relative starttime=now-{hours_ago}hours for sacct on {hostname}"
                        )
                    else:
                        since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
                        cmd += f" --starttime={since_str}"
                        logger.debug(
                            f"Using starttime={since_str} for sacct on {hostname} (input was {since})"
                        )
                else:
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
            timeout = 120 if since and "w" in str(since) else 180
            result = conn.run(cmd, hide=True, timeout=timeout, warn=True, pty=True)

            if not result.ok:
                logger.debug(
                    f"sacct command failed: exit={result.exited}, stderr: {result.stderr}"
                )
            elif len(result.stdout) == 0:
                logger.debug(f"No jobs found for {hostname} since {since}")
                try:
                    cluster_time_result = conn.run(
                        "date '+%Y-%m-%dT%H:%M:%S%z'", hide=True
                    )
                    logger.debug(
                        f"Cluster {hostname} current time: {cluster_time_result.stdout.strip()}"
                    )
                    logger.debug(f"Query was for jobs since: {since}")

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
                        )

                        if job_info and (
                            (
                                job_info.stdout_file
                                and (
                                    job_info.stdout_file.endswith(
                                        (".sh", ".sbatch", ".bash", ".slurm")
                                    )
                                    or "/submit/" in job_info.stdout_file
                                    or "/scripts/" in job_info.stdout_file
                                    or "%" in job_info.stdout_file
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
                                    or "%" in job_info.stderr_file
                                )
                            )
                        ):
                            needs_path_fix.append(job_info.job_id)
                    except Exception as e:
                        logger.debug(f"Failed to parse sacct line: {line}, error: {e}")

            if skipped_cached > 0:
                logger.info(
                    f"Skipped {skipped_cached} already-cached completed jobs from sacct query on {hostname}"
                )

        except Exception as e:
            logger.debug(f"Error fetching completed jobs: {e}")

        if needs_path_fix:
            try:
                details = self.output.get_job_details_from_scontrol_batch(
                    conn, needs_path_fix, hostname
                )
                for job in jobs:
                    if job.job_id not in needs_path_fix:
                        continue
                    if job.job_id in details:
                        stdout_path, stderr_path, _ = details[job.job_id]
                        if stdout_path and stdout_path != job.stdout_file:
                            job.stdout_file = stdout_path
                        if stderr_path and stderr_path != job.stderr_file:
                            job.stderr_file = stderr_path
                        logger.debug(
                            f"Corrected output paths for completed job {job.job_id}"
                        )
                        continue

                    var_dict = {
                        "j": job.job_id,
                        "i": job.job_id,
                        "u": job.user or "",
                        "x": job.name or "",
                    }
                    if job.stdout_file and "%" in job.stdout_file:
                        expanded_stdout = SlurmParser.expand_slurm_path_vars(
                            job.stdout_file, var_dict
                        )
                        if expanded_stdout != job.stdout_file:
                            job.stdout_file = expanded_stdout
                            logger.debug(f"Expanded stdout path for job {job.job_id}")
                    if job.stderr_file and "%" in job.stderr_file:
                        expanded_stderr = SlurmParser.expand_slurm_path_vars(
                            job.stderr_file, var_dict
                        )
                        if expanded_stderr != job.stderr_file:
                            job.stderr_file = expanded_stderr
                            logger.debug(f"Expanded stderr path for job {job.job_id}")
                    logger.debug(
                        f"Could not get paths from scontrol for completed job {job.job_id}, used placeholder expansion"
                    )
            except Exception:
                for job in jobs:
                    if job.job_id not in needs_path_fix:
                        continue
                    var_dict = {
                        "j": job.job_id,
                        "i": job.job_id,
                        "u": job.user or "",
                        "x": job.name or "",
                    }
                    if job.stdout_file and "%" in job.stdout_file:
                        expanded_stdout = SlurmParser.expand_slurm_path_vars(
                            job.stdout_file, var_dict
                        )
                        if expanded_stdout != job.stdout_file:
                            job.stdout_file = expanded_stdout
                            logger.debug(f"Expanded stdout path for job {job.job_id}")
                    if job.stderr_file and "%" in job.stderr_file:
                        expanded_stderr = SlurmParser.expand_slurm_path_vars(
                            job.stderr_file, var_dict
                        )
                        if expanded_stderr != job.stderr_file:
                            job.stderr_file = expanded_stderr
                            logger.debug(f"Expanded stderr path for job {job.job_id}")
                    logger.debug(
                        f"Could not get paths from scontrol for completed job {job.job_id}, used placeholder expansion"
                    )

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
        chunk_size_days = 7
        current_end = (
            datetime.now() if since.tzinfo is None else datetime.now(since.tzinfo)
        )
        current_start = max(since, current_end - timedelta(days=chunk_size_days))

        while current_start >= since and (not limit or len(all_jobs) < limit):
            logger.debug(
                f"Chunked query for {hostname}: {current_start.date()} to {current_end.date()}"
            )

            try:
                chunk_jobs = self._get_completed_jobs_single(
                    conn,
                    hostname,
                    current_start,
                    user,
                    job_ids,
                    state_filter,
                    exclude_job_ids,
                    skip_user_detection,
                    cached_completed_ids,
                )

                all_jobs.extend(chunk_jobs)
                logger.debug(
                    f"Got {len(chunk_jobs)} jobs from chunk, total: {len(all_jobs)}"
                )

                if limit and len(all_jobs) >= limit:
                    logger.debug(f"Hit limit {limit}, stopping chunked query")
                    break

            except Exception as e:
                logger.debug(
                    f"Chunk query failed for {current_start.date()}-{current_end.date()}: {e}"
                )

            current_end = current_start
            current_start = max(since, current_end - timedelta(days=chunk_size_days))

            if current_end <= since:
                break

        return all_jobs[:limit] if limit else all_jobs

    def get_username(
        self, conn: SSHConnection, user: str | None = None, hostname: str = "unknown"
    ) -> Optional[str]:
        """Get the username to use for Slurm queries."""
        if user:
            return user

        if hostname in self._username_cache:
            cached_username = self._username_cache[hostname]
            logger.debug(f"Using cached username for {hostname}: {cached_username}")
            return cached_username

        detected_username = None

        try:
            result = conn.run("whoami", hide=True, timeout=10, warn=True, pty=True)
            if result.ok and result.stdout.strip():
                detected_username = result.stdout.strip()
                logger.debug(f"Detected username from whoami: {detected_username}")
        except Exception as e:
            logger.warning(f"Failed to get current user via whoami: {e}")

        if not detected_username:
            try:
                if hasattr(conn, "user"):
                    detected_username = conn.user
                    logger.info(
                        f"Using SSH connection username as fallback: {detected_username}"
                    )
            except Exception as e:
                logger.debug(f"Could not get username from SSH connection: {e}")

        if not detected_username:
            try:
                result = conn.run(
                    "echo $USER", hide=True, timeout=10, warn=True, pty=True
                )
                if result.ok and result.stdout.strip():
                    detected_username = result.stdout.strip()
                    logger.info(
                        f"Got username from $USER environment variable: {detected_username}"
                    )
            except Exception as e:
                logger.debug(f"Could not get username from $USER: {e}")

        if detected_username:
            self._username_cache[hostname] = detected_username
            logger.info(f"Cached username for {hostname}: {detected_username}")
            return detected_username

        logger.error(
            "\u26a0\ufe0f  Could not determine username - Slurm query will fetch ALL users' jobs!"
        )
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
                f"squeue -r --user {user} -j {job_id} --format='{format_str}' --noheader",
                hide=True,
                timeout=30,
                warn=True,
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
                    timeout=30,
                    warn=True,
                )

                if result.ok and result.stdout.strip():
                    lines = result.stdout.strip().split("\n")
                    for line in lines:
                        fields = line.strip().split("|")
                        if (
                            len(fields) >= len(available_fields)
                            and "." not in fields[0]
                        ):
                            job_info = self.parser.from_sacct_fields(
                                fields, hostname, available_fields
                            )
                            break

            if job_info:
                try:
                    stdout_path, stderr_path = self.output.get_job_output_files(
                        conn, job_id, hostname
                    )
                    if stdout_path:
                        job_info.stdout_file = stdout_path
                    if stderr_path:
                        job_info.stderr_file = stderr_path
                except Exception:
                    if job_info.stdout_file and "%" in job_info.stdout_file:
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

    def check_slurm_availability(self, conn: SSHConnection, hostname: str) -> bool:
        """Check if Slurm is available on the host."""
        try:
            result = conn.run("squeue --version", hide=True, timeout=5)
            if result.ok:
                return True

            result2 = conn.run("which squeue", hide=True, timeout=3)
            return result2.ok

        except Exception as e:
            logger.debug(f"Slurm not available on {hostname}: {e}")
            if "No existing session" in str(e) or "Connection" in str(e):
                logger.debug(
                    f"Assuming Slurm available on {hostname} due to connection issue"
                )
                return True
            return False
