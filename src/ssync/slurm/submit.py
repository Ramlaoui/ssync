"""Slurm submit/cancel operations."""

from typing import Any, Protocol

from ..utils.logging import setup_logger
from .params import SlurmParams


class SSHConnection(Protocol):
    """Protocol for SSH connection objects."""

    def run(self, command: str, **kwargs) -> Any: ...


logger = setup_logger(__name__, "INFO")


class SlurmSubmit:
    """Handles Slurm submission-related commands."""

    def build_sbatch_command(
        self, slurm_params: SlurmParams, remote_script_path: str
    ) -> tuple[list[str], str]:
        """Build the sbatch command list and submit line (without cd)."""
        cmd = ["sbatch"]

        if slurm_params.job_name:
            cmd.append(f"--job-name={slurm_params.job_name}")
        if slurm_params.time_min:
            cmd.append(f"--time={slurm_params.time_min}")
        if slurm_params.cpus_per_task:
            cmd.append(f"--cpus-per-task={slurm_params.cpus_per_task}")
        if slurm_params.mem_gb:
            cmd.append(f"--mem={slurm_params.mem_gb}G")
        if slurm_params.partition:
            cmd.append(f"--partition={slurm_params.partition}")
        if slurm_params.output:
            cmd.append(f"--output={slurm_params.output}")
        if slurm_params.error:
            cmd.append(f"--error={slurm_params.error}")
        if slurm_params.constraint:
            cmd.append(f"--constraint={slurm_params.constraint}")
        if slurm_params.account:
            cmd.append(f"--account={slurm_params.account}")
        if slurm_params.nodes:
            cmd.append(f"--nodes={slurm_params.nodes}")
        if slurm_params.n_tasks_per_node:
            cmd.append(f"--ntasks-per-node={slurm_params.n_tasks_per_node}")
        if slurm_params.gpus_per_node:
            cmd.append(f"--gpus-per-node={slurm_params.gpus_per_node}")
        if slurm_params.gres:
            cmd.append(f"--gres={slurm_params.gres}")

        cmd.append(remote_script_path)
        submit_line = " ".join(cmd)
        return cmd, submit_line

    def run_sbatch(
        self,
        conn: SSHConnection,
        slurm_params: SlurmParams,
        remote_script_path: str,
        work_dir: str | None = None,
        warn: bool = True,
    ) -> tuple[Any, str, list[str], str]:
        """Run sbatch on the remote host and return result, command, and submit_line."""
        cmd, submit_line = self.build_sbatch_command(
            slurm_params, remote_script_path
        )
        full_cmd = submit_line
        if work_dir:
            full_cmd = f"cd {work_dir} && {submit_line}"

        result = conn.run(full_cmd, hide=False, warn=warn)
        return result, full_cmd, cmd, submit_line

    def cancel_job(self, conn: SSHConnection, job_id: str) -> bool:
        """Cancel a Slurm job."""
        try:
            conn.run(f"scancel {job_id}", hide=False)
            return True
        except Exception as e:
            logger.debug(f"Failed to cancel job {job_id}: {e}")
            return False
