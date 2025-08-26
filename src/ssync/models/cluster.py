from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class CacheSettings:
    """Cache configuration settings."""

    enabled: bool = True
    cache_dir: Optional[str] = None  # If None, use default ~/.cache/ssync
    max_age_days: int = 365  # How long to keep cache entries
    script_max_age_days: int = 0  # 0 means never expire scripts
    cleanup_interval_hours: int = 168  # How often to run cleanup (weekly)
    max_size_mb: int = 1024  # Maximum cache size in MB
    auto_cleanup: bool = False  # Whether to automatically cleanup old entries

    def __post_init__(self):
        # Validate settings
        if self.max_age_days < 0:
            self.max_age_days = 0
        if self.script_max_age_days < 0:
            self.script_max_age_days = 0
        if self.cleanup_interval_hours < 1:
            self.cleanup_interval_hours = 1
        if self.max_size_mb < 10:
            self.max_size_mb = 10


@dataclass(frozen=True)
class SlurmDefaults:
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


@dataclass(frozen=True)
class Host:
    hostname: str
    username: str
    port: int = 22
    password: str | None = None
    ProxyJump: Host | None = None
    key_file: str | None = None
    use_ssh_config: bool = True

    def __post_init__(self):
        if self.key_file:
            self.key_file = Path(self.key_file).expanduser().resolve()
        if self.ProxyJump:
            self.ProxyJump = Host(**self.ProxyJump)


@dataclass(frozen=True)
class SlurmHost:
    host: Host
    work_dir: Path
    scratch_dir: Path
    slurm_defaults: Optional[SlurmDefaults] = None
