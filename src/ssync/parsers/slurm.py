"""Slurm output parsing utilities."""

from ..models.job import JobInfo, JobState
from ..slurm.fields import SACCT_FIELDS, SQUEUE_FIELDS


class SlurmParser:
    """Handles parsing of Slurm command outputs into JobInfo objects."""

    @staticmethod
    def map_slurm_state(state_str: str, from_sacct: bool = False) -> JobState:
        """Map Slurm state string to JobState enum."""
        if not state_str or not state_str.strip():
            return JobState.UNKNOWN

        state_clean = state_str.split()[0].upper().strip()

        if state_clean in {"COMPLETED", "CD"}:
            return JobState.COMPLETED

        if state_clean in {
            "FAILED",
            "F",
            "BOOT_FAIL",
            "BF",
            "DEADLINE",
            "DL",
            "NODE_FAIL",
            "NF",
            "OUT_OF_MEMORY",
            "OOM",
            "PREEMPTED",
            "PR",
        }:
            return JobState.FAILED

        if state_clean in {"CANCELLED", "CANCELED", "CA"}:
            return JobState.CANCELLED

        if state_clean in {"TIMEOUT", "TO"}:
            return JobState.TIMEOUT

        # `squeue` can report active jobs in transitional states such as
        # CONFIGURING/CF or COMPLETING/CG. Treat them as running so the UI
        # stays live while the allocation comes up or drains down.
        if state_clean in {
            "RUNNING",
            "R",
            "COMPLETING",
            "CG",
            "CONFIGURING",
            "CF",
            "STAGE_OUT",
            "SO",
            "SIGNALING",
            "SI",
        }:
            return JobState.RUNNING

        if state_clean in {
            "PENDING",
            "PD",
            "REQUEUED",
            "RQ",
            "REQUEUE_FED",
            "RF",
            "REQUEUE_HOLD",
            "RH",
            "RESV_DEL_HOLD",
            "RD",
            "SUSPENDED",
            "S",
            "STOPPED",
            "ST",
            "RESIZING",
            "RS",
            "REVOKED",
            "RV",
        }:
            return JobState.PENDING

        if not from_sacct:
            try:
                return JobState(state_str)
            except ValueError:
                return JobState.UNKNOWN

        return JobState.UNKNOWN

    @staticmethod
    def create_var_dict(fields: list[str], field_names: list[str] = None) -> dict:
        """Create variable dictionary for Slurm path expansion.

        Args:
            fields: Field values from Slurm command output
            field_names: Field names for sacct parsing (optional)

        Returns:
            Dictionary mapping Slurm variable names to values
        """
        if field_names:

            def get_field_value(field_name: str) -> str:
                try:
                    idx = field_names.index(field_name)
                    return fields[idx] if len(fields) > idx and fields[idx] else ""
                except (ValueError, IndexError):
                    return ""

            job_id = get_field_value("JobID")
            array_job_id = ""
            array_task_id = ""
            if "_" in job_id:
                array_job_id, array_task_id = job_id.split("_", 1)
            elif "[" in job_id and "]" in job_id:
                array_job_id = job_id.split("[")[0]
                array_task_id = job_id.split("[")[1].rstrip("]")

            return {
                "j": job_id,
                "i": job_id,
                "u": get_field_value("User"),
                "x": get_field_value("JobName"),
                "A": array_job_id or job_id,
                "a": array_task_id,
            }
        else:
            job_id = fields[0] if len(fields) > 0 else ""
            array_job_id = ""
            array_task_id = ""
            if "_" in job_id:
                array_job_id, array_task_id = job_id.split("_", 1)
            elif "[" in job_id and "]" in job_id:
                array_job_id = job_id.split("[")[0]
                array_task_id = job_id.split("[")[1].rstrip("]")

            return {
                "j": job_id,
                "i": job_id,
                "u": fields[3] if len(fields) > 3 else "",
                "x": fields[1] if len(fields) > 1 else "",
                "A": array_job_id or job_id,
                "a": array_task_id,
            }

    @staticmethod
    def expand_slurm_path_vars(path_str: str, var_dict: dict) -> str:
        """Expand Slurm path variables like %j, %u, %A, etc.

        Args:
            path_str: The path string with Slurm variables
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

        def get_field(field_name: str) -> str | None:
            try:
                idx = SQUEUE_FIELDS.index(field_name)
                return fields[idx] if len(fields) > idx and fields[idx] else None
            except (ValueError, IndexError):
                return None

        job_id_str = get_field("%i") or ""
        array_job_id = None
        array_task_id = None
        if "_" in job_id_str:
            array_job_id, array_task_id = job_id_str.split("_", 1)
        elif "[" in job_id_str and "]" in job_id_str:
            array_job_id = job_id_str.split("[")[0]
            array_task_id = job_id_str.split("[")[1].rstrip("]")

        return JobInfo(
            job_id=job_id_str,
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
            # squeue's %o/%e fields are command/expected-end-time, not stdout/stderr.
            # Real output paths are resolved later via sacct/scontrol.
            stdout_file=None,
            stderr_file=None,
            submit_time=get_field("%V"),
            start_time=get_field("%S"),
            account=get_field("%a"),
            qos=get_field("%q"),
            priority=get_field("%Q"),
            node_list=get_field("%R"),
            array_job_id=array_job_id,
            array_task_id=array_task_id,
        )

    @classmethod
    def from_sacct_fields(
        cls, fields: list[str], hostname: str, field_names: list[str] = None
    ) -> JobInfo:
        """Create JobInfo from sacct field array."""
        active_field_names = field_names or SACCT_FIELDS

        def get_field(field_name: str) -> str | None:
            try:
                idx = active_field_names.index(field_name)
                return fields[idx] if len(fields) > idx and fields[idx] else None
            except (ValueError, IndexError):
                return None

        state = cls.map_slurm_state(get_field("State") or "", from_sacct=True)

        work_dir = get_field("WorkDir")
        var_dict = cls.create_var_dict(fields, active_field_names)
        stdout_file = cls.expand_slurm_path_vars(get_field("StdOut") or "", var_dict)
        stderr_file = cls.expand_slurm_path_vars(get_field("StdErr") or "", var_dict)

        job_id_str = get_field("JobID") or ""
        array_job_id = None
        array_task_id = None
        if "_" in job_id_str:
            array_job_id, array_task_id = job_id_str.split("_", 1)
        elif "[" in job_id_str and "]" in job_id_str:
            array_job_id = job_id_str.split("[")[0]
            array_task_id = job_id_str.split("[")[1].rstrip("]")

        return JobInfo(
            job_id=job_id_str,
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
            exit_code=get_field("ExitCode"),
            account=get_field("Account"),
            qos=get_field("QOS"),
            priority=get_field("Priority"),
            array_job_id=array_job_id,
            array_task_id=array_task_id,
            alloc_tres=get_field("AllocTRES"),
            req_tres=get_field("ReqTRES"),
            cpu_time=get_field("CPUTime"),
            total_cpu=get_field("TotalCPU"),
            user_cpu=get_field("UserCPU"),
            system_cpu=get_field("SystemCPU"),
            ave_cpu=get_field("AveCPU"),
            ave_cpu_freq=get_field("AveCPUFreq"),
            req_cpu_freq_min=get_field("ReqCPUFreqMin"),
            req_cpu_freq_max=get_field("ReqCPUFreqMax"),
            max_rss=get_field("MaxRSS"),
            ave_rss=get_field("AveRSS"),
            max_vmsize=get_field("MaxVMSize"),
            ave_vmsize=get_field("AveVMSize"),
            max_disk_read=get_field("MaxDiskRead"),
            max_disk_write=get_field("MaxDiskWrite"),
            ave_disk_read=get_field("AveDiskRead"),
            ave_disk_write=get_field("AveDiskWrite"),
            consumed_energy=get_field("ConsumedEnergy"),
        )
