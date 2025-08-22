from dataclasses import dataclass
from enum import Enum
from typing import Optional


class JobState(Enum):
    """SLURM job states."""

    PENDING = "PD"
    RUNNING = "R"
    COMPLETED = "CD"
    FAILED = "F"
    CANCELLED = "CA"
    TIMEOUT = "TO"
    UNKNOWN = "UNKNOWN"


@dataclass
class JobInfo:
    """Information about a SLURM job."""

    job_id: str
    name: str
    state: JobState
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
    req_cpu_freq_min: Optional[str] = None
    req_cpu_freq_max: Optional[str] = None

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

    @property
    def gpu_info(self) -> Optional[dict]:
        """Parse and return GPU information from TRES fields.

        Returns:
            Dictionary containing GPU information or None if no GPU was used
            Format: {
                'requested': {'count': int, 'type': str},
                'allocated': {'count': int, 'type': str},
            }
        """
        if not (self.req_tres or self.alloc_tres):
            return None

        result = {"requested": None, "allocated": None}

        # Parse requested GPUs from req_tres
        if self.req_tres and "gres/gpu" in self.req_tres:
            for resource in self.req_tres.split(","):
                if "gres/gpu" in resource:
                    try:
                        if "=" in resource:
                            parts = resource.split("=")
                            gpu_spec = parts[0].strip()
                            count = int(parts[1])

                            if ":" in gpu_spec:
                                gpu_type = gpu_spec.split(":")[-1]
                            else:
                                gpu_type = "unknown"

                            result["requested"] = {"count": count, "type": gpu_type}
                            break
                    except (ValueError, IndexError):
                        pass

        # Parse allocated GPUs from alloc_tres
        if self.alloc_tres and "gres/gpu" in self.alloc_tres:
            for resource in self.alloc_tres.split(","):
                if "gres/gpu:" in resource:  # Look for specific GPU types
                    try:
                        if "=" in resource:
                            parts = resource.split("=")
                            gpu_spec = parts[0].strip()
                            count = int(parts[1])

                            gpu_type = gpu_spec.split(":")[-1]
                            result["allocated"] = {"count": count, "type": gpu_type}
                            break
                    except (ValueError, IndexError):
                        pass

        return result if (result["requested"] or result["allocated"]) else None
