from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel


class SlurmDefaultsWeb(BaseModel):
    """Web-serializable Slurm default parameters."""

    # Basic job parameters
    partition: Optional[str] = None
    account: Optional[str] = None
    constraint: Optional[str] = None

    # Resource allocation
    cpus: Optional[int] = None
    mem: Optional[int] = None  # Memory in GB
    time: Optional[str] = None  # Time limit (HH:MM:SS or minutes)
    nodes: Optional[int] = None
    ntasks_per_node: Optional[int] = None
    gpus_per_node: Optional[int] = None
    gres: Optional[str] = None  # Generic resources (e.g., "gpu:2")

    # Job naming and output
    job_name_prefix: Optional[str] = None  # Prefix for job names
    output_pattern: Optional[str] = (
        None  # Pattern for stdout files (e.g., "job_%j.out")
    )
    error_pattern: Optional[str] = None  # Pattern for stderr files (e.g., "job_%j.err")

    # Environment and execution
    python_env: Optional[str] = None  # Default Python environment setup command

    # Quality of Service and priority
    qos: Optional[str] = None  # Quality of Service
    priority: Optional[int] = None  # Job priority


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

    # Array job fields
    array_job_id: Optional[str] = None
    array_task_id: Optional[str] = None

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
            submit_line=job_info.submit_line,
            start_time=job_info.start_time,
            end_time=job_info.end_time,
            node_list=job_info.node_list,
            # Array job fields
            array_job_id=job_info.array_job_id,
            array_task_id=job_info.array_task_id,
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

    def to_job_info(self):
        """Convert web model back to CLI JobInfo."""
        from ..models.job import JobInfo, JobState

        return JobInfo(
            job_id=self.job_id,
            name=self.name,
            state=JobState(self.state.value),
            hostname=self.hostname,
            user=self.user,
            partition=self.partition,
            nodes=self.nodes,
            cpus=self.cpus,
            memory=self.memory,
            time_limit=self.time_limit,
            runtime=self.runtime,
            reason=self.reason,
            work_dir=self.work_dir,
            stdout_file=self.stdout_file,
            stderr_file=self.stderr_file,
            submit_time=self.submit_time,
            submit_line=self.submit_line,
            start_time=self.start_time,
            end_time=self.end_time,
            node_list=self.node_list,
            # Array job fields
            array_job_id=self.array_job_id,
            array_task_id=self.array_task_id,
            # Resource allocation
            alloc_tres=self.alloc_tres,
            req_tres=self.req_tres,
            # CPU metrics
            cpu_time=self.cpu_time,
            total_cpu=self.total_cpu,
            user_cpu=self.user_cpu,
            system_cpu=self.system_cpu,
            ave_cpu=self.ave_cpu,
            ave_cpu_freq=self.ave_cpu_freq,
            # Memory metrics
            max_rss=self.max_rss,
            ave_rss=self.ave_rss,
            max_vmsize=self.max_vmsize,
            ave_vmsize=self.ave_vmsize,
            # Disk I/O metrics
            max_disk_read=self.max_disk_read,
            max_disk_write=self.max_disk_write,
            ave_disk_read=self.ave_disk_read,
            ave_disk_write=self.ave_disk_write,
            # Energy metrics
            consumed_energy=self.consumed_energy,
        )


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
    states: List[str] = []
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
    muted_job_ids: List[str] = []
    muted_hosts: List[str] = []
    muted_job_name_patterns: List[str] = []
    allowed_users: List[str] = []


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
    # Summary statistics
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
    cached: bool = False  # Indicates if the response was served from cache
    # Array job grouping
    array_groups: Optional[List[ArrayJobGroup]] = None
    group_array_jobs: bool = False  # Whether array jobs are grouped


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
    data_completeness: Dict[str, bool] = {
        "job_info": True,
        "script": False,
        "outputs": False,
    }


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
    source_dir: Optional[str] = None  # Optional - only required if sync is enabled
    host: str

    # Slurm parameters
    job_name: Optional[str] = None
    cpus: Optional[int] = None
    mem: Optional[int] = None
    time: Optional[int] = None
    partition: Optional[str] = None
    ntasks_per_node: Optional[int] = None
    # Alternate field name accepted by the API and used in parts of the codebase
    n_tasks_per_node: Optional[int] = None
    nodes: Optional[int] = None
    gpus_per_node: Optional[int] = None
    gres: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    constraint: Optional[str] = None
    account: Optional[str] = None
    python_env: Optional[str] = None

    # Sync parameters
    exclude: List[str] = []
    include: List[str] = []
    no_gitignore: bool = False
    force_sync: bool = False  # Override directory size validation

    # Job execution parameters
    abort_on_setup_failure: bool = True  # Whether to abort job if login setup fails


class LaunchJobResponse(BaseModel):
    """Response model for job launch endpoint."""

    success: bool
    job_id: Optional[str] = None
    message: str
    hostname: str

    # Directory validation information
    directory_warning: Optional[str] = None
    directory_stats: Optional[dict] = None
    requires_confirmation: bool = False
