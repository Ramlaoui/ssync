from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class JobStateWeb(str, Enum):
    """SLURM job states for web API."""

    PENDING = "PD"
    RUNNING = "R"
    COMPLETED = "CD"
    FAILED = "F"
    CANCELLED = "CA"
    TIMEOUT = "TO"
    UNKNOWN = "UNKNOWN"


class JobInfoWeb(BaseModel):
    """Web-serializable job information."""

    job_id: str
    name: str
    state: JobStateWeb
    hostname: str
    user: Optional[str] = None
    partition: Optional[str] = None
    nodes: Optional[str] = None
    cpus: Optional[str] = None
    memory: Optional[str] = None
    time_limit: Optional[str] = None
    runtime: Optional[str] = None
    reason: Optional[str] = None
    work_dir: Optional[str] = None
    stdout_file: Optional[str] = None
    stderr_file: Optional[str] = None
    submit_time: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    node_list: Optional[str] = None

    # Resource allocation
    alloc_tres: Optional[str] = None
    req_tres: Optional[str] = None

    # CPU metrics
    cpu_time: Optional[str] = None
    total_cpu: Optional[str] = None
    user_cpu: Optional[str] = None
    system_cpu: Optional[str] = None
    ave_cpu: Optional[str] = None
    ave_cpu_freq: Optional[str] = None

    # Memory metrics
    max_rss: Optional[str] = None
    ave_rss: Optional[str] = None
    max_vmsize: Optional[str] = None
    ave_vmsize: Optional[str] = None

    # Disk I/O metrics
    max_disk_read: Optional[str] = None
    max_disk_write: Optional[str] = None
    ave_disk_read: Optional[str] = None
    ave_disk_write: Optional[str] = None

    # Energy metrics
    consumed_energy: Optional[str] = None

    @classmethod
    def from_job_info(cls, job_info) -> "JobInfoWeb":
        """Convert from CLI JobInfo to web model."""
        return cls(
            job_id=job_info.job_id,
            name=job_info.name,
            state=JobStateWeb(job_info.state.value),
            hostname=job_info.hostname,
            user=job_info.user,
            partition=job_info.partition,
            nodes=job_info.nodes,
            cpus=job_info.cpus,
            memory=job_info.memory,
            time_limit=job_info.time_limit,
            runtime=job_info.runtime,
            reason=job_info.reason,
            work_dir=job_info.work_dir,
            stdout_file=job_info.stdout_file,
            stderr_file=job_info.stderr_file,
            submit_time=job_info.submit_time,
            start_time=job_info.start_time,
            end_time=job_info.end_time,
            node_list=job_info.node_list,
            # Resource allocation
            alloc_tres=job_info.alloc_tres,
            req_tres=job_info.req_tres,
            # CPU metrics
            cpu_time=job_info.cpu_time,
            total_cpu=job_info.total_cpu,
            user_cpu=job_info.user_cpu,
            system_cpu=job_info.system_cpu,
            ave_cpu=job_info.ave_cpu,
            ave_cpu_freq=job_info.ave_cpu_freq,
            # Memory metrics
            max_rss=job_info.max_rss,
            ave_rss=job_info.ave_rss,
            max_vmsize=job_info.max_vmsize,
            ave_vmsize=job_info.ave_vmsize,
            # Disk I/O metrics
            max_disk_read=job_info.max_disk_read,
            max_disk_write=job_info.max_disk_write,
            ave_disk_read=job_info.ave_disk_read,
            ave_disk_write=job_info.ave_disk_write,
            # Energy metrics
            consumed_energy=job_info.consumed_energy,
        )


class HostInfoWeb(BaseModel):
    """Web-serializable host information."""

    hostname: str
    work_dir: str
    scratch_dir: str


class JobStatusResponse(BaseModel):
    """Response model for job status endpoint."""

    hostname: str
    jobs: List[JobInfoWeb]
    total_jobs: int
    query_time: datetime


class FileMetadata(BaseModel):
    """Metadata about a job output file."""

    path: str
    exists: bool = False
    size_bytes: Optional[int] = None
    last_modified: Optional[str] = None
    access_path: Optional[str] = None  # URL or path for direct file access


class JobOutputResponse(BaseModel):
    """Response model for job output endpoint."""

    job_id: str
    hostname: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    stdout_metadata: Optional[FileMetadata] = None
    stderr_metadata: Optional[FileMetadata] = None


class StatusQueryParams(BaseModel):
    """Query parameters for status endpoint."""

    user: Optional[str] = None
    since: Optional[str] = None
    limit: Optional[int] = None
    job_ids: Optional[List[str]] = None
    state_filter: Optional[str] = None
    active_only: Optional[bool] = False
    completed_only: Optional[bool] = False
    simple: Optional[bool] = False
