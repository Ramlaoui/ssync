"""SLURM output parsing utilities."""

from ..models.job import JobInfo, JobState
from .fields import SACCT_FIELDS, SQUEUE_FIELDS


class SlurmParser:
    """Handles parsing of SLURM command outputs into JobInfo objects."""

    @staticmethod
    def map_slurm_state(state_str: str, from_sacct: bool = False) -> JobState:
        """Map SLURM state string to JobState enum."""
        if from_sacct:
            # Handle sacct states
            state_clean = state_str.split()[0]  # Remove extra state info
            if state_clean in ["COMPLETED"]:
                return JobState.COMPLETED
            elif state_clean in [
                "FAILED",
                "BOOT_FAIL",
                "DEADLINE",
                "NODE_FAIL",
                "OUT_OF_MEMORY",
                "PREEMPTED",
            ]:
                return JobState.FAILED
            elif state_clean in ["CANCELLED"]:
                return JobState.CANCELLED
            elif state_clean in ["TIMEOUT"]:
                return JobState.TIMEOUT
            else:
                return JobState.UNKNOWN
        else:
            # Handle squeue states
            try:
                return JobState(state_str)
            except ValueError:
                return JobState.UNKNOWN

    @staticmethod
    def create_var_dict(fields: list[str]) -> dict:
        """Create variable dictionary for SLURM path expansion."""
        return {
            "j": fields[0],  # JobID
            "i": fields[0],  # JobID
            "u": fields[3],  # User
        }

    @staticmethod
    def expand_slurm_path_vars(path_str: str, var_dict: dict) -> str:
        """Expand SLURM path variables like %j, %u, %A, etc.

        Args:
            path_str: The path string with SLURM variables
            var_dict: Dictionary mapping variable names to values

        Returns:
            Path string with variables expanded
        """
        if not path_str:
            return path_str

        expanded = path_str
        for var, value in var_dict.items():
            expanded = expanded.replace(f"%{var}", str(value))

        return expanded

    @classmethod
    def from_squeue_fields(cls, fields: list[str], hostname: str) -> JobInfo:
        """Create JobInfo from squeue field array."""
        state = cls.map_slurm_state(fields[2])

        # Get field by name helper
        def get_field(field_name: str) -> str | None:
            try:
                idx = SQUEUE_FIELDS.index(field_name)
                return fields[idx] if len(fields) > idx and fields[idx] else None
            except (ValueError, IndexError):
                return None

        # Create variable dictionary for path expansion
        var_dict = cls.create_var_dict(fields)
        stdout_file = (
            cls.expand_slurm_path_vars(get_field("%o") or "", var_dict)
            if get_field("%o")
            else None
        )
        stderr_file = (
            cls.expand_slurm_path_vars(get_field("%e") or "", var_dict)
            if get_field("%e")
            else None
        )

        return JobInfo(
            job_id=get_field("%i") or "",
            name=get_field("%j") or "",
            state=state,
            hostname=hostname,
            user=get_field("%u"),
            partition=get_field("%P"),
            nodes=get_field("%D"),
            cpus=get_field("%C"),
            memory=get_field("%m"),
            time_limit=get_field("%l"),
            runtime=get_field("%M"),
            reason=get_field("%r"),
            work_dir=get_field("%Z"),
            stdout_file=stdout_file,
            stderr_file=stderr_file,
            submit_time=get_field("%V"),
            start_time=get_field("%S"),
        )

    @classmethod
    def from_sacct_fields(
        cls, fields: list[str], hostname: str, field_names: list[str] = None
    ) -> JobInfo:
        """Create JobInfo from sacct field array."""
        state = cls.map_slurm_state(fields[2], from_sacct=True)

        # Use provided field names or fall back to default
        active_field_names = field_names or SACCT_FIELDS

        # Get field by name helper
        def get_field(field_name: str) -> str | None:
            try:
                idx = active_field_names.index(field_name)
                return fields[idx] if len(fields) > idx and fields[idx] else None
            except (ValueError, IndexError):
                return None

        # Infer stdout/stderr paths
        work_dir = get_field("WorkDir")
        var_dict = cls.create_var_dict(fields)
        stdout_file = cls.expand_slurm_path_vars(get_field("StdOut") or "", var_dict)
        stderr_file = cls.expand_slurm_path_vars(get_field("StdErr") or "", var_dict)

        return JobInfo(
            job_id=get_field("JobID") or "",
            name=get_field("JobName") or "",
            state=state,
            hostname=hostname,
            user=get_field("User"),
            partition=get_field("Partition"),
            nodes=get_field("AllocNodes"),
            cpus=get_field("AllocCPUS"),
            memory=get_field("ReqMem"),
            time_limit=get_field("Timelimit"),
            runtime=get_field("Elapsed"),
            reason=get_field("Reason"),
            work_dir=work_dir,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
            submit_time=get_field("Submit"),
            submit_line=get_field("SubmitLine"),
            start_time=get_field("Start"),
            end_time=get_field("End"),
            node_list=get_field("NodeList"),
            # Resource allocation
            alloc_tres=get_field("AllocTRES"),
            req_tres=get_field("ReqTRES"),
            # CPU metrics
            cpu_time=get_field("CPUTime"),
            total_cpu=get_field("TotalCPU"),
            user_cpu=get_field("UserCPU"),
            system_cpu=get_field("SystemCPU"),
            ave_cpu=get_field("AveCPU"),
            ave_cpu_freq=get_field("AveCPUFreq"),
            req_cpu_freq_min=get_field("ReqCPUFreqMin"),
            req_cpu_freq_max=get_field("ReqCPUFreqMax"),
            # Memory metrics
            max_rss=get_field("MaxRSS"),
            ave_rss=get_field("AveRSS"),
            max_vmsize=get_field("MaxVMSize"),
            ave_vmsize=get_field("AveVMSize"),
            # Disk I/O metrics
            max_disk_read=get_field("MaxDiskRead"),
            max_disk_write=get_field("MaxDiskWrite"),
            ave_disk_read=get_field("AveDiskRead"),
            ave_disk_write=get_field("AveDiskWrite"),
            # Energy metrics
            consumed_energy=get_field("ConsumedEnergy"),
        )
