"""Slurm output retrieval utilities."""

import shlex
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from ..parsers.slurm import SlurmParser
from ..utils.logging import setup_logger


class SSHConnection(Protocol):
    """Protocol for SSH connection objects."""

    def run(self, command: str, **kwargs) -> Any: ...


logger = setup_logger(__name__, "INFO")


@dataclass
class JobScontrolDetails:
    """Parsed job metadata from ``scontrol show job``."""

    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
    submit_line: Optional[str] = None
    batch_host: Optional[str] = None
    node_list: Optional[str] = None
    num_nodes: Optional[str] = None
    num_cpus: Optional[str] = None
    tres: Optional[str] = None
    gres: Optional[str] = None
    tres_per_node: Optional[str] = None


class SlurmOutput:
    """Handles Slurm output paths and file retrieval."""

    def _expand_paths(
        self,
        job_id: str,
        stdout_path: Optional[str],
        stderr_path: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        """Expand Slurm path vars like %A/%a using the job_id."""
        if not stdout_path and not stderr_path:
            return stdout_path, stderr_path

        array_job_id = ""
        array_task_id = ""
        if "_" in job_id:
            array_job_id, array_task_id = job_id.split("_", 1)
        elif "[" in job_id and "]" in job_id:
            array_job_id = job_id.split("[")[0]
            array_task_id = job_id.split("[")[1].rstrip("]")

        var_dict = {
            "j": job_id,
            "i": job_id,
            "A": array_job_id or job_id,
            "a": array_task_id,
        }

        if stdout_path and "%" in stdout_path:
            stdout_path = SlurmParser.expand_slurm_path_vars(stdout_path, var_dict)
        if stderr_path and "%" in stderr_path:
            stderr_path = SlurmParser.expand_slurm_path_vars(stderr_path, var_dict)

        return stdout_path, stderr_path

    def get_job_metadata_from_scontrol_batch(
        self,
        conn: SSHConnection,
        job_ids: list[str],
        hostname: str,
        max_single_job_fallbacks: Optional[int] = None,
    ) -> dict[str, JobScontrolDetails]:
        """Fetch structured job metadata for multiple jobs in one scontrol call."""
        if not job_ids:
            return {}

        # scontrol accepts multiple job IDs as args.
        cmd = f"scontrol show job {' '.join(job_ids)}"
        details: dict[str, JobScontrolDetails] = {}

        try:
            result = conn.run(cmd, hide=True, timeout=20, warn=True, pty=True)
            if not result.ok or not result.stdout:
                logger.debug(
                    f"scontrol show job batch failed for {hostname}: {result.stderr}"
                )
            else:
                parsed = self._parse_scontrol_show_job_output(result.stdout)
                for parsed_job_id, parsed_details in parsed.items():
                    expanded_stdout, expanded_stderr = self._expand_paths(
                        parsed_job_id,
                        parsed_details.stdout_path,
                        parsed_details.stderr_path,
                    )
                    details[parsed_job_id] = JobScontrolDetails(
                        stdout_path=expanded_stdout,
                        stderr_path=expanded_stderr,
                        submit_line=parsed_details.submit_line,
                        batch_host=parsed_details.batch_host,
                        node_list=parsed_details.node_list,
                        num_nodes=parsed_details.num_nodes,
                        num_cpus=parsed_details.num_cpus,
                        tres=parsed_details.tres,
                        gres=parsed_details.gres,
                        tres_per_node=parsed_details.tres_per_node,
                    )

        except Exception as e:
            logger.debug(f"Failed batch scontrol for {hostname}: {e}")

        # Some clusters reject multi-job scontrol queries with:
        # "too many arguments for keyword:show".
        # Fallback to per-job queries for any missing details.
        missing_job_ids = [job_id for job_id in job_ids if job_id not in details]
        if max_single_job_fallbacks is not None and max_single_job_fallbacks >= 0:
            fallback_job_ids = missing_job_ids[:max_single_job_fallbacks]
            skipped_count = len(missing_job_ids) - len(fallback_job_ids)
            if skipped_count > 0:
                logger.info(
                    f"Skipping {skipped_count} per-job scontrol fallback queries on {hostname} "
                    f"(cap={max_single_job_fallbacks})"
                )
        else:
            fallback_job_ids = missing_job_ids

        for job_id in fallback_job_ids:
            job_details = self.get_job_metadata_from_scontrol(
                conn, job_id, hostname
            )
            if any(
                (
                    job_details.stdout_path,
                    job_details.stderr_path,
                    job_details.submit_line,
                    job_details.batch_host,
                    job_details.node_list,
                    job_details.tres,
                    job_details.gres,
                    job_details.tres_per_node,
                )
            ):
                details[job_id] = job_details

        return details

    def get_job_details_from_scontrol_batch(
        self,
        conn: SSHConnection,
        job_ids: list[str],
        hostname: str,
        max_single_job_fallbacks: Optional[int] = None,
    ) -> dict[str, tuple[Optional[str], Optional[str], Optional[str]]]:
        """Fetch output paths and submit command for multiple jobs."""
        details = self.get_job_metadata_from_scontrol_batch(
            conn=conn,
            job_ids=job_ids,
            hostname=hostname,
            max_single_job_fallbacks=max_single_job_fallbacks,
        )
        return {
            job_id: (
                job_details.stdout_path,
                job_details.stderr_path,
                job_details.submit_line,
            )
            for job_id, job_details in details.items()
        }

    def get_job_metadata_from_scontrol(
        self, conn: SSHConnection, job_id: str, hostname: str, user: str | None = None
    ) -> JobScontrolDetails:
        """Get structured job metadata using ``scontrol show job``."""
        try:
            logger.debug(f"Getting job details for job {job_id} on {hostname}")

            result = conn.run(
                f"scontrol show job {job_id}",
                hide=True,
                timeout=10,
                warn=True,
                pty=True,
            )

            if not result.ok:
                logger.debug(f"scontrol show job failed for {job_id}: {result.stderr}")
                return JobScontrolDetails()

            parsed = self._parse_scontrol_show_job_output(result.stdout)
            # Prefer exact JobId match, but fallback to first parsed block if needed.
            details = parsed.get(job_id, JobScontrolDetails())
            if not any(
                (
                    details.stdout_path,
                    details.stderr_path,
                    details.submit_line,
                    details.batch_host,
                    details.node_list,
                    details.tres,
                    details.gres,
                    details.tres_per_node,
                )
            ):
                if parsed:
                    details = next(iter(parsed.values()))

            stdout_path, stderr_path = self._expand_paths(
                job_id, details.stdout_path, details.stderr_path
            )
            enriched_details = JobScontrolDetails(
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                submit_line=details.submit_line,
                batch_host=details.batch_host,
                node_list=details.node_list,
                num_nodes=details.num_nodes,
                num_cpus=details.num_cpus,
                tres=details.tres,
                gres=details.gres,
                tres_per_node=details.tres_per_node,
            )
            logger.debug(
                "Found job details for job %s: stdout=%s, stderr=%s, submit_line=%s, "
                "batch_host=%s, node_list=%s, tres=%s, gres=%s",
                job_id,
                stdout_path,
                stderr_path,
                enriched_details.submit_line,
                enriched_details.batch_host,
                enriched_details.node_list,
                enriched_details.tres,
                enriched_details.gres,
            )
            return enriched_details

        except Exception as e:
            logger.debug(f"Failed to get job details for job {job_id}: {e}")
            return JobScontrolDetails()

    def get_job_details_from_scontrol(
        self, conn: SSHConnection, job_id: str, hostname: str, user: str | None = None
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Get output file paths and submit command using scontrol show job."""
        details = self.get_job_metadata_from_scontrol(conn, job_id, hostname, user)
        return details.stdout_path, details.stderr_path, details.submit_line

    def _parse_scontrol_show_job_output(
        self, raw_output: str
    ) -> dict[str, JobScontrolDetails]:
        """Parse ``scontrol show job`` output into structured metadata."""
        details: dict[str, JobScontrolDetails] = {}
        current_job_id: Optional[str] = None
        current_details = JobScontrolDetails()

        def flush_current() -> None:
            if current_job_id:
                details[current_job_id] = current_details

        for token in raw_output.replace("\n", " ").split():
            if token.startswith("JobId="):
                flush_current()
                current_job_id = token.split("=", 1)[1]
                current_details = JobScontrolDetails()
            elif token.startswith("StdOut="):
                current_details.stdout_path = token.split("=", 1)[1]
            elif token.startswith("StdErr="):
                current_details.stderr_path = token.split("=", 1)[1]
            elif token.startswith("Command="):
                current_details.submit_line = token.split("=", 1)[1]
            elif token.startswith("BatchHost="):
                current_details.batch_host = token.split("=", 1)[1]
            elif token.startswith("NodeList="):
                current_details.node_list = token.split("=", 1)[1]
            elif token.startswith("NumNodes="):
                current_details.num_nodes = token.split("=", 1)[1]
            elif token.startswith("NumCPUs="):
                current_details.num_cpus = token.split("=", 1)[1]
            elif token.startswith("TRES="):
                current_details.tres = token.split("=", 1)[1]
            elif token.startswith("Gres="):
                current_details.gres = token.split("=", 1)[1]
            elif token.startswith("TresPerNode="):
                current_details.tres_per_node = token.split("=", 1)[1]

        flush_current()
        return details

    def resolve_node_hostnames(
        self, conn: SSHConnection, node_list: Optional[str]
    ) -> Optional[list[str]]:
        """Expand a Slurm node list expression into concrete hostnames."""
        if not node_list:
            return None

        try:
            result = conn.run(
                f"scontrol show hostnames {shlex.quote(node_list)}",
                hide=True,
                timeout=10,
                warn=True,
                pty=True,
            )
            if not result.ok or not result.stdout.strip():
                return None
            hostnames = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            return hostnames or None
        except Exception as e:
            logger.debug(f"Failed to resolve node hostnames for {node_list}: {e}")
            return None

    def get_job_output_files(
        self, conn: SSHConnection, job_id: str, hostname: str, user: str | None = None
    ) -> tuple[Optional[str], Optional[str]]:
        """Get stdout and stderr file paths for a job using scontrol show job."""
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
        """Read and compress job output on remote host."""
        import base64

        try:
            stdout_path, stderr_path = self.get_job_output_files(conn, job_id, hostname)

            file_path = stdout_path if output_type == "stdout" else stderr_path
            if not file_path:
                logger.debug(f"No {output_type} file path found for job {job_id}")
                return None

            size_result = conn.run(
                f"stat -c%s '{file_path}' 2>/dev/null", hide=True, warn=True
            )

            if not size_result.ok:
                logger.debug(f"File not found: {file_path}")
                return None

            file_size = int(size_result.stdout.strip())
            logger.debug(f"File {file_path} size: {file_size} bytes")

            max_size = 100 * 1024 * 1024
            compress_threshold = 1024

            if file_size > max_size:
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
            elif file_size > compress_threshold:
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
                result = conn.run(
                    f"cat '{file_path}'", hide=True, timeout=30, warn=True
                )

                if result.ok:
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
        """Read the content of a job's output file (stdout or stderr)."""
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
        """Get the batch script content for a job using scontrol write batch_script."""
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

            script_content = result.stdout.strip()
            if script_content:
                logger.debug(
                    f"Retrieved batch script for job {job_id} ({len(script_content)} chars)"
                )
                return script_content

            logger.debug(f"No batch script content found for job {job_id}")
            return None

        except Exception as e:
            logger.debug(f"Failed to get batch script for job {job_id}: {e}")
            return None
