"""Slurm output retrieval utilities."""

from typing import Any, Optional, Protocol

from ..utils.logging import setup_logger
from ..parsers.slurm import SlurmParser


class SSHConnection(Protocol):
    """Protocol for SSH connection objects."""

    def run(self, command: str, **kwargs) -> Any: ...


logger = setup_logger(__name__, "INFO")


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

    def get_job_details_from_scontrol_batch(
        self, conn: SSHConnection, job_ids: list[str], hostname: str
    ) -> dict[str, tuple[Optional[str], Optional[str], Optional[str]]]:
        """Fetch job details for multiple jobs in a single scontrol call.

        Returns a mapping of job_id -> (stdout_path, stderr_path, submit_line).
        """
        if not job_ids:
            return {}

        # scontrol accepts multiple job IDs as args.
        cmd = f"scontrol show job {' '.join(job_ids)}"
        details: dict[str, tuple[Optional[str], Optional[str], Optional[str]]] = {}

        try:
            result = conn.run(cmd, hide=True, timeout=20, warn=True, pty=True)
            if not result.ok or not result.stdout:
                logger.debug(
                    f"scontrol show job batch failed for {hostname}: {result.stderr}"
                )
                return details

            # scontrol prints blocks separated by blank lines
            blocks = result.stdout.strip().split("\n\n")
            for block in blocks:
                if "JobId=" not in block:
                    continue

                stdout_path = None
                stderr_path = None
                submit_line = None
                job_id = None

                for token in block.replace("\n", " ").split():
                    if token.startswith("JobId="):
                        job_id = token.split("=", 1)[1]
                    elif token.startswith("StdOut="):
                        stdout_path = token.split("=", 1)[1]
                    elif token.startswith("StdErr="):
                        stderr_path = token.split("=", 1)[1]
                    elif token.startswith("Command="):
                        submit_line = token.split("=", 1)[1]

                if job_id:
                    stdout_path, stderr_path = self._expand_paths(
                        job_id, stdout_path, stderr_path
                    )
                    details[job_id] = (stdout_path, stderr_path, submit_line)

        except Exception as e:
            logger.debug(f"Failed batch scontrol for {hostname}: {e}")

        return details

    def get_job_details_from_scontrol(
        self, conn: SSHConnection, job_id: str, hostname: str, user: str | None = None
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Get job details including output files and submit_line using scontrol show job."""
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
                return None, None, None

            stdout_path = None
            stderr_path = None
            submit_line = None

            for line in result.stdout.split("\n"):
                line = line.strip()
                if "StdOut=" in line:
                    for part in line.split():
                        if part.startswith("StdOut="):
                            stdout_path = part.split("=", 1)[1]
                            break
                elif "StdErr=" in line:
                    for part in line.split():
                        if part.startswith("StdErr="):
                            stderr_path = part.split("=", 1)[1]
                            break
                elif "Command=" in line:
                    for part in line.split():
                        if part.startswith("Command="):
                            submit_line = part.split("=", 1)[1]
                            break

            stdout_path, stderr_path = self._expand_paths(
                job_id, stdout_path, stderr_path
            )
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
                result = conn.run(f"cat '{file_path}'", hide=True, timeout=30, warn=True)

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
