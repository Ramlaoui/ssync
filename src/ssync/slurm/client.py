"""SLURM command execution utilities."""

from datetime import datetime, timedelta
from typing import List, Optional

from fabric import Connection

from ..models.job import JobInfo, JobState
from ..utils.logging import setup_logger
from .fields import SQUEUE_FIELDS
from .parser import SlurmParser

logger = setup_logger(__name__, "DEBUG")


class SlurmClient:
    """Handles execution of SLURM commands and parsing results."""

    def __init__(self):
        self.parser = SlurmParser()
        # Cache of available sacct fields per hostname
        self._available_fields_cache = {}

    def get_available_sacct_fields(self, conn: Connection, hostname: str) -> List[str]:
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
                # Fall back to basic compatible fields
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

            # Parse the helpformat output - it's in columnar format
            # Fields are separated by whitespace and arranged in columns
            available_fields = []

            # Split the output and extract all field names
            for line in result.stdout.replace("\r\n", "\n").split("\n"):
                line = line.strip()
                if line:
                    # Split by whitespace to get individual field names
                    fields_in_line = line.split()
                    for field in fields_in_line:
                        field = field.strip()
                        if field and field.replace("_", "").isalnum():
                            available_fields.append(field)

            # Essential fields that we absolutely need
            essential_fields = ["JobID", "JobName", "State", "User"]

            # Additional useful fields in the ORDER we want them in the command
            # This order determines both the sacct command format AND the parsing order
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

            # Filter to only available fields, preserving the order
            cluster_fields = [
                field for field in wanted_fields if field in available_fields
            ]

            # Ensure we have essential fields - if not, fall back to basic set
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
            # Fall back to basic fields
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
        conn: Connection,
        hostname: str,
        user: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        state_filter: Optional[str] = None,
        skip_user_detection: bool = False,
    ) -> List[JobInfo]:
        """Get active (running/pending) jobs using squeue."""
        jobs = []

        try:
            # Build squeue command
            format_str = "|".join(SQUEUE_FIELDS)
            cmd = f"squeue --format='{format_str}' --noheader"

            # Default to current user if no user specified (unless explicitly skipping)
            query_user = self.get_username(conn) if not skip_user_detection else user

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

                        # For running jobs, enrich with actual stdout/stderr paths from scontrol
                        # since squeue doesn't provide the correct output file paths
                        if job_info.state in [JobState.RUNNING, JobState.PENDING]:
                            stdout_path, stderr_path = self.get_job_output_files(
                                conn, job_info.job_id, hostname
                            )
                            if stdout_path:
                                job_info.stdout_file = stdout_path
                            if stderr_path:
                                job_info.stderr_file = stderr_path

                        jobs.append(job_info)
                    except Exception as e:
                        logger.debug(f"Failed to parse squeue line: {line}, error: {e}")

        except Exception as e:
            logger.debug(f"Error getting active jobs: {e}")

        return jobs

    def get_completed_jobs(
        self,
        conn: Connection,
        hostname: str,
        since: Optional[datetime] = None,
        user: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        state_filter: Optional[str] = None,
        exclude_job_ids: Optional[List[str]] = None,
        skip_user_detection: bool = False,
        limit: Optional[int] = None,
    ) -> List[JobInfo]:
        """Get completed jobs using sacct."""
        # Check if we need chunking for large time ranges
        if since:
            time_range_days = (datetime.now() - since).days
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
        )

    def _get_completed_jobs_single(
        self,
        conn: Connection,
        hostname: str,
        since: Optional[datetime] = None,
        user: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        state_filter: Optional[str] = None,
        exclude_job_ids: Optional[List[str]] = None,
        skip_user_detection: bool = False,
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

            # Time filter
            if since:
                since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
                cmd += f" --starttime={since_str}"

            # Default to current user if no user specified (unless explicitly skipping)
            query_user = self.get_username(conn) if not skip_user_detection else user

            if query_user:
                cmd += f" --user={query_user}"
            if job_ids:
                cmd += f" --jobs={','.join(job_ids)}"
            if state_filter:
                cmd += f" --state={state_filter}"

            # For large time ranges (>2 weeks), consider chunking the query
            # to avoid SLURM timeouts with massive datasets
            time_range_days = (datetime.now() - since).days if since else 0
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
            else:
                logger.debug(
                    f"sacct found {len(result.stdout.strip().split(chr(10)))} lines for {hostname}"
                )

            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue

                fields = line.strip().split("|")
                if len(fields) >= len(available_fields):
                    job_id = fields[0].split(".")[0]  # Remove job step suffix

                    # Skip if we should exclude this job
                    if exclude_job_ids and job_id in exclude_job_ids:
                        continue

                    try:
                        # Parse job state
                        state = self.parser.map_slurm_state(fields[2], from_sacct=True)

                        # Apply state filter if provided
                        if state_filter and state.value != state_filter:
                            continue

                        job_info = self.parser.from_sacct_fields(
                            fields, hostname, available_fields
                        )
                        jobs.append(job_info)
                        logger.debug(
                            f"Parsed sacct job {fields[0]} on {hostname}: state={state.value}, user={fields[3] if len(fields) > 3 else 'unknown'}"
                        )  # Debug

                    except Exception as e:
                        logger.debug(f"Failed to parse sacct line: {line}, error: {e}")

        except Exception as e:
            logger.debug(f"Error fetching completed jobs: {e}")

        return jobs

    def _get_completed_jobs_chunked(
        self,
        conn: Connection,
        hostname: str,
        since: datetime,
        user: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        state_filter: Optional[str] = None,
        exclude_job_ids: Optional[List[str]] = None,
        skip_user_detection: bool = False,
        limit: Optional[int] = None,
    ) -> List[JobInfo]:
        """Get completed jobs using chunked queries to avoid timeouts."""

        all_jobs = []
        chunk_size_days = 7  # Query 1 week at a time
        current_end = datetime.now()
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
                # Continue with next chunk even if this one fails

            # Move to previous chunk
            current_end = current_start
            current_start = max(since, current_end - timedelta(days=chunk_size_days))

            # Prevent infinite loop
            if current_end <= since:
                break

        return all_jobs[:limit] if limit else all_jobs

    def get_username(self, conn: Connection, user: str | None = None) -> Optional[str]:
        """Get the username to use for SLURM queries."""
        if user:
            return user

        try:
            result = conn.run("whoami", hide=True, timeout=3, warn=True, pty=True)
            if result.ok and result.stdout.strip():
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"Failed to get current user: {e}")

        return None

    def get_job_details(
        self, conn: Connection, job_id: str, hostname: str, user: str | None = None
    ) -> Optional[JobInfo]:
        """Get detailed information about a specific job."""
        try:
            job_info = None

            user = user or self.get_username(conn)

            # Try squeue first (for active jobs)
            format_str = "|".join(SQUEUE_FIELDS)
            result = conn.run(
                f"squeue --user {user} -j {job_id} --format='{format_str}' --noheader",
                hide=True,
                timeout=10,
                warn=True,  # Don't throw exception on "Invalid job id"
            )

            if result.ok and result.stdout.strip():
                fields = result.stdout.strip().split("|")
                if len(fields) >= len(SQUEUE_FIELDS):
                    job_info = self.parser.from_squeue_fields(fields, hostname)

            # Try sacct for completed jobs if not found in squeue
            if not job_info:
                available_fields = self.get_available_sacct_fields(conn, hostname)
                format_str = ",".join(available_fields)
                result = conn.run(
                    f"sacct -X -j {job_id} --format={format_str} --parsable2 --noheader --user {user}",
                    hide=True,
                    timeout=10,
                    warn=True,  # Don't throw exception if job not found in sacct either
                )

                if result.ok and result.stdout.strip():
                    # Take the first line (main job, not job steps)
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

            # For active jobs (running/pending), always get actual output paths from scontrol
            # since squeue provides incorrect values (script path instead of output path)
            if job_info and job_info.state in [JobState.RUNNING, JobState.PENDING]:
                stdout_path, stderr_path = self.get_job_output_files(
                    conn, job_id, hostname
                )
                if stdout_path:
                    job_info.stdout_file = stdout_path
                if stderr_path:
                    job_info.stderr_file = stderr_path
            # Also try scontrol if we don't have output paths at all
            elif job_info and not (job_info.stdout_file or job_info.stderr_file):
                stdout_path, stderr_path = self.get_job_output_files(
                    conn, job_id, hostname
                )
                if stdout_path:
                    job_info.stdout_file = stdout_path
                if stderr_path:
                    job_info.stderr_file = stderr_path

            return job_info

        except Exception as e:
            logger.debug(f"Failed to get job details for {job_id}: {e}")

        return None

    def cancel_job(self, conn: Connection, job_id: str) -> bool:
        """Cancel a SLURM job."""
        try:
            conn.run(f"scancel {job_id}", hide=False)
            return True
        except Exception as e:
            logger.debug(f"Failed to cancel job {job_id}: {e}")
            return False

    def get_job_output_files(
        self, conn: Connection, job_id: str, hostname: str, user: str | None = None
    ) -> tuple[Optional[str], Optional[str]]:
        """Get stdout and stderr file paths for a job using scontrol show job.

        Args:
            conn: SSH connection to the cluster
            job_id: SLURM job ID
            hostname: Cluster hostname

        Returns:
            Tuple of (stdout_path, stderr_path). Either may be None if not found.
        """
        try:
            logger.debug(f"Getting output files for job {job_id} on {hostname}")

            user = user or self.get_username(conn)

            result = conn.run(
                f"scontrol show job {job_id}",
                hide=True,
                timeout=10,
                warn=True,
                pty=True,
            )

            if not result.ok:
                logger.debug(f"scontrol show job failed for {job_id}: {result.stderr}")
                return None, None

            stdout_path = None
            stderr_path = None

            # Parse the scontrol output
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

            logger.debug(
                f"Found output files for job {job_id}: stdout={stdout_path}, stderr={stderr_path}"
            )
            return stdout_path, stderr_path

        except Exception as e:
            logger.debug(f"Failed to get output files for job {job_id}: {e}")
            return None, None

    def read_job_output_content(
        self, conn: Connection, job_id: str, hostname: str, output_type: str = "stdout"
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
        self, conn: Connection, job_id: str, hostname: str
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

    def check_slurm_availability(self, conn: Connection, hostname: str) -> bool:
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
