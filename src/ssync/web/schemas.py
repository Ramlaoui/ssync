from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ..models.job import JobInfo, JobState


class SlurmDefaultsWeb(BaseModel):
    """Web-serializable Slurm default parameters."""

    partition: Optional[str] = None
    account: Optional[str] = None
    constraint: Optional[str] = None
    cpus: Optional[int] = None
    mem: Optional[int] = None
    time: Optional[str] = None
    nodes: Optional[int] = None
    ntasks_per_node: Optional[int] = None
    gpus_per_node: Optional[int] = None
    gres: Optional[str] = None
    job_name_prefix: Optional[str] = None
    output_pattern: Optional[str] = None
    error_pattern: Optional[str] = None
    python_env: Optional[str] = None
    qos: Optional[str] = None
    priority: Optional[int] = None


class JobStateWeb(str, Enum):
    """Slurm job states for web API."""

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
    submit_line: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    node_list: Optional[str] = None
    array_job_id: Optional[str] = None
    array_task_id: Optional[str] = None
    alloc_tres: Optional[str] = None
    req_tres: Optional[str] = None
    cpu_time: Optional[str] = None
    total_cpu: Optional[str] = None
    user_cpu: Optional[str] = None
    system_cpu: Optional[str] = None
    ave_cpu: Optional[str] = None
    ave_cpu_freq: Optional[str] = None
    max_rss: Optional[str] = None
    ave_rss: Optional[str] = None
    max_vmsize: Optional[str] = None
    ave_vmsize: Optional[str] = None
    max_disk_read: Optional[str] = None
    max_disk_write: Optional[str] = None
    ave_disk_read: Optional[str] = None
    ave_disk_write: Optional[str] = None
    consumed_energy: Optional[str] = None

    @classmethod
    def from_job_info(cls, job_info: JobInfo) -> "JobInfoWeb":
        """Convert from core JobInfo to web schema."""
        payload = {
            field_name: getattr(job_info, field_name)
            for field_name in cls.model_fields
            if field_name != "state"
        }
        payload["state"] = JobStateWeb(job_info.state.value)
        return cls(**payload)

    def to_job_info(self) -> JobInfo:
        """Convert web schema back to core JobInfo."""
        payload = {
            field_name: getattr(self, field_name)
            for field_name in JobInfo.__dataclass_fields__
            if field_name in type(self).model_fields and field_name != "state"
        }
        payload["state"] = JobState(self.state.value)
        return JobInfo(**payload)


class HostInfoWeb(BaseModel):
    """Web-serializable host information."""

    hostname: str
    work_dir: str
    scratch_dir: str
    slurm_defaults: Optional[SlurmDefaultsWeb] = None


class PartitionGpuTypeWeb(BaseModel):
    total: int
    used: int


class PartitionResourcesWeb(BaseModel):
    partition: str
    availability: Optional[str] = None
    states: List[str] = Field(default_factory=list)
    nodes_total: int
    cpus_alloc: int
    cpus_idle: int
    cpus_other: int
    cpus_total: int
    gpus_total: Optional[int] = None
    gpus_used: Optional[int] = None
    gpus_idle: Optional[int] = None
    gpu_types: Optional[Dict[str, PartitionGpuTypeWeb]] = None


class PartitionStatusResponse(BaseModel):
    hostname: str
    partitions: List[PartitionResourcesWeb]
    query_time: str
    cached: bool = False
    stale: bool = False
    cache_age_seconds: Optional[int] = None
    updated_at: Optional[str] = None
    error: Optional[str] = None


class NotificationDeviceRegistration(BaseModel):
    token: str
    platform: str = "ios"
    environment: Optional[str] = None
    bundle_id: Optional[str] = None
    device_id: Optional[str] = None
    enabled: bool = True


class NotificationTestRequest(BaseModel):
    title: str = "Test Notification"
    body: str = "This is a test notification from ssync"
    token: Optional[str] = None


class NotificationPreferences(BaseModel):
    enabled: bool = True
    allowed_states: Optional[List[str]] = None
    muted_job_ids: List[str] = Field(default_factory=list)
    muted_hosts: List[str] = Field(default_factory=list)
    muted_job_name_patterns: List[str] = Field(default_factory=list)
    allowed_users: List[str] = Field(default_factory=list)


class NotificationPreferencesPatch(BaseModel):
    enabled: Optional[bool] = None
    allowed_states: Optional[List[str]] = None
    muted_job_ids: Optional[List[str]] = None
    muted_hosts: Optional[List[str]] = None
    muted_job_name_patterns: Optional[List[str]] = None
    allowed_users: Optional[List[str]] = None


class WebPushKeys(BaseModel):
    p256dh: str
    auth: str


class WebPushSubscriptionRegistration(BaseModel):
    endpoint: str
    keys: WebPushKeys
    user_agent: Optional[str] = None
    enabled: bool = True


class WebPushUnsubscribeRequest(BaseModel):
    endpoint: str


class ArrayJobGroup(BaseModel):
    """Group of array job tasks."""

    array_job_id: str
    job_name: str
    hostname: str
    user: Optional[str] = None
    total_tasks: int
    tasks: List[JobInfoWeb]
    pending_count: int = 0
    running_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0


class JobStatusResponse(BaseModel):
    """Response model for job status endpoint."""

    hostname: str
    jobs: List[JobInfoWeb]
    total_jobs: int
    query_time: datetime
    cached: bool = False
    array_groups: Optional[List[ArrayJobGroup]] = None
    group_array_jobs: bool = False


class FileMetadata(BaseModel):
    """Metadata about a job output file."""

    path: str
    exists: bool = False
    size_bytes: Optional[int] = None
    last_modified: Optional[str] = None
    access_path: Optional[str] = None


class JobOutputResponse(BaseModel):
    """Response model for job output endpoint."""

    job_id: str
    hostname: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    stdout_metadata: Optional[FileMetadata] = None
    stderr_metadata: Optional[FileMetadata] = None


class CompleteJobDataResponse(BaseModel):
    """Response model for unified job data endpoint."""

    job_id: str
    hostname: str
    job_info: JobInfoWeb
    script_content: Optional[str] = None
    script_length: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    stdout_metadata: Optional[FileMetadata] = None
    stderr_metadata: Optional[FileMetadata] = None
    cached_at: Optional[str] = None
    data_completeness: Dict[str, bool] = Field(
        default_factory=lambda: {
            "job_info": True,
            "script": False,
            "outputs": False,
        }
    )


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


class LaunchJobRequest(BaseModel):
    """Request model for job launch endpoint."""

    script_content: str
    source_dir: Optional[str] = None
    host: str
    job_name: Optional[str] = None
    cpus: Optional[int] = None
    mem: Optional[int] = None
    time: Optional[int] = None
    partition: Optional[str] = None
    ntasks_per_node: Optional[int] = None
    n_tasks_per_node: Optional[int] = None
    nodes: Optional[int] = None
    gpus_per_node: Optional[int] = None
    gres: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    constraint: Optional[str] = None
    account: Optional[str] = None
    python_env: Optional[str] = None
    exclude: List[str] = Field(default_factory=list)
    include: List[str] = Field(default_factory=list)
    no_gitignore: bool = False
    force_sync: bool = False
    abort_on_setup_failure: bool = True


class LaunchJobResponse(BaseModel):
    """Response model for job launch endpoint."""

    success: bool
    job_id: Optional[str] = None
    launch_id: Optional[str] = None
    message: str
    hostname: str
    directory_warning: Optional[str] = None
    directory_stats: Optional[dict] = None
    requires_confirmation: bool = False


class LaunchEventWeb(BaseModel):
    """Web-serializable launch event."""

    type: str
    launch_id: str
    hostname: str
    sequence: int
    timestamp: str
    stage: Optional[str] = None
    source: Optional[str] = None
    stream: Optional[str] = None
    level: Optional[str] = None
    message: Optional[str] = None
    job_id: Optional[str] = None
    success: Optional[bool] = None


class LaunchStatusResponse(BaseModel):
    """Current status and recent events for a launch."""

    launch_id: str
    hostname: str
    stage: str
    terminal: bool
    success: Optional[bool] = None
    job_id: Optional[str] = None
    message: Optional[str] = None
    events: List[LaunchEventWeb] = Field(default_factory=list)
