"""Slurm client facade for query/output/submit operations."""

from typing import Any, List, Optional, Protocol

from ..models.job import JobInfo
from .output import SlurmOutput
from .query import SlurmQuery
from .submit import SlurmSubmit


class SSHConnection(Protocol):
    """Protocol for SSH connection objects."""

    def run(self, command: str, **kwargs) -> Any: ...


class SlurmClient:
    """Facade for Slurm query/output/submit helpers."""

    def __init__(self):
        self.output = SlurmOutput()
        self.query = SlurmQuery(output=self.output)
        self.submit = SlurmSubmit()

    def get_available_sacct_fields(
        self, conn: SSHConnection, hostname: str
    ) -> List[str]:
        return self.query.get_available_sacct_fields(conn, hostname)

    def get_active_jobs(
        self,
        conn: SSHConnection,
        hostname: str,
        user: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        state_filter: Optional[str] = None,
        skip_user_detection: bool = False,
    ) -> List[JobInfo]:
        return self.query.get_active_jobs(
            conn,
            hostname,
            user=user,
            job_ids=job_ids,
            state_filter=state_filter,
            skip_user_detection=skip_user_detection,
        )

    def get_job_final_state(
        self, conn: SSHConnection, hostname: str, job_id: str
    ) -> Optional[JobInfo]:
        return self.query.get_job_final_state(conn, hostname, job_id)

    def get_completed_jobs(
        self,
        conn: SSHConnection,
        hostname: str,
        since: Optional[Any] = None,
        user: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        state_filter: Optional[str] = None,
        exclude_job_ids: Optional[List[str]] = None,
        skip_user_detection: bool = False,
        limit: Optional[int] = None,
        cached_completed_ids: Optional[set] = None,
    ) -> List[JobInfo]:
        return self.query.get_completed_jobs(
            conn,
            hostname,
            since=since,
            user=user,
            job_ids=job_ids,
            state_filter=state_filter,
            exclude_job_ids=exclude_job_ids,
            skip_user_detection=skip_user_detection,
            limit=limit,
            cached_completed_ids=cached_completed_ids,
        )

    def get_username(
        self, conn: SSHConnection, user: str | None = None, hostname: str = "unknown"
    ) -> Optional[str]:
        return self.query.get_username(conn, user=user, hostname=hostname)

    def get_job_details(
        self, conn: SSHConnection, job_id: str, hostname: str, user: str | None = None
    ) -> Optional[JobInfo]:
        return self.query.get_job_details(conn, job_id, hostname, user=user)

    def cancel_job(self, conn: SSHConnection, job_id: str) -> bool:
        return self.submit.cancel_job(conn, job_id)

    def get_job_details_from_scontrol(
        self, conn: SSHConnection, job_id: str, hostname: str, user: str | None = None
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        return self.output.get_job_details_from_scontrol(conn, job_id, hostname, user)

    def get_job_output_files(
        self, conn: SSHConnection, job_id: str, hostname: str, user: str | None = None
    ) -> tuple[Optional[str], Optional[str]]:
        return self.output.get_job_output_files(conn, job_id, hostname, user)

    def read_job_output_compressed(
        self,
        conn: SSHConnection,
        job_id: str,
        hostname: str,
        output_type: str = "stdout",
    ) -> Optional[dict]:
        return self.output.read_job_output_compressed(
            conn, job_id, hostname, output_type
        )

    def read_job_output_content(
        self,
        conn: SSHConnection,
        job_id: str,
        hostname: str,
        output_type: str = "stdout",
    ) -> Optional[str]:
        return self.output.read_job_output_content(
            conn, job_id, hostname, output_type
        )

    def get_job_batch_script(
        self, conn: SSHConnection, job_id: str, hostname: str
    ) -> Optional[str]:
        return self.output.get_job_batch_script(conn, job_id, hostname)

    def check_slurm_availability(self, conn: SSHConnection, hostname: str) -> bool:
        return self.query.check_slurm_availability(conn, hostname)
