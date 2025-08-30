"""Simplified SLURM manager using refactored components."""

import re
from dataclasses import dataclass
from typing import List, Optional

from .connection import ConnectionManager
from .models import JobInfo
from .models.cluster import Host, SlurmHost
from .slurm import SlurmClient
from .utils.config import config
from .utils.logging import setup_logger
from .utils.slurm_params import SlurmParams
from .utils.ssh import send_file

logger = setup_logger(__name__, "DEBUG")


@dataclass
class Job:
    """Represents a submitted SLURM job."""

    def __init__(self, job_id: str, slurm_host: SlurmHost, manager):
        self.job_id = job_id
        self.slurm_host = slurm_host
        self.manager = manager

    def cancel(self) -> bool:
        """Cancel this job."""
        return self.manager.cancel_job(self.slurm_host, self.job_id)

    def get_info(self) -> Optional[JobInfo]:
        """Get detailed job information."""
        return self.manager.get_job_info(self.slurm_host, self.job_id)


class SlurmManager:
    """Manages SLURM operations across multiple hosts."""

    def __init__(
        self,
        slurm_hosts: List[SlurmHost],
        use_ssh_config: bool = True,
        connection_timeout: int = 30,
    ):
        self.slurm_hosts = slurm_hosts
        self.connection_manager = ConnectionManager(
            use_ssh_config, connection_timeout=connection_timeout
        )
        self.slurm_client = SlurmClient()

    def _get_connection(self, host: Host, force_refresh: bool = False):
        """Get SSH connection for a host.

        Args:
            host: Host configuration
            force_refresh: Force refresh the connection

        Returns:
            Connection object
        """
        return self.connection_manager.get_connection(host, force_refresh=force_refresh)

    def refresh_connections(self):
        """Refresh all SSH connections.

        Returns:
            Number of connections refreshed
        """
        return self.connection_manager.refresh_all_connections()

    async def get_all_jobs(
        self,
        slurm_host: SlurmHost | str,
        user: str | None = None,
        since: str | None = None,
        limit: int | None = None,
        job_ids: List[str] | None = None,
        state_filter: str | None = None,
        active_only: bool = False,
        completed_only: bool = False,
        skip_user_detection: bool = False,
    ) -> List[JobInfo]:
        """Get all jobs from a SLURM host via JobDataManager."""
        from .job_data_manager import get_job_data_manager

        hostname = (
            slurm_host if isinstance(slurm_host, str) else slurm_host.host.hostname
        )
        job_data_manager = get_job_data_manager()
        jobs = await job_data_manager.fetch_all_jobs(
            hostname=hostname,
            user=user,
            since=since,
            limit=limit,
            job_ids=job_ids,
            state_filter=state_filter,
            active_only=active_only,
            completed_only=completed_only,
            skip_user_detection=skip_user_detection,
        )
        return jobs

    def submit_script(
        self,
        slurm_host: SlurmHost | str,
        params: SlurmParams | None = None,
        local_script_path: str | None = None,
        remote_script_path: str | None = None,
    ) -> Optional[Job]:
        """Submit a script to SLURM."""

        params = params or SlurmParams()

        if isinstance(slurm_host, str):
            slurm_host = self.get_host_by_name(slurm_host)

        host = slurm_host.host
        conn = self._get_connection(host)

        try:
            cmd = ["sbatch"]

            if params.job_name:
                cmd.append(f"--job-name={params.job_name}")
            if params.time_min:
                cmd.append(f"--time={params.time_min}")
            if params.cpus_per_task:
                cmd.append(f"--cpus-per-task={params.cpus_per_task}")
            if params.mem_gb:
                cmd.append(f"--mem={params.mem_gb}G")
            if params.partition:
                cmd.append(f"--partition={params.partition}")
            if params.output:
                cmd.append(f"--output={params.output}")
            if params.error:
                cmd.append(f"--error={params.error}")
            if params.constraint:
                cmd.append(f"--constraint={params.constraint}")
            if params.account:
                cmd.append(f"--account={params.account}")
            if params.nodes:
                cmd.append(f"--nodes={params.nodes}")
            if params.n_tasks_per_node:
                cmd.append(f"--ntasks-per-node={params.n_tasks_per_node}")
            if params.gpus_per_node:
                cmd.append(f"--gpus-per-node={params.gpus_per_node}")
            if params.gres:
                cmd.append(f"--gres={params.gres}")

            if local_script_path:
                remote_scratch_dir = config.get_remote_cache_path(slurm_host)
                remote_script_path = send_file(
                    conn=conn,
                    local_path=local_script_path,
                    remote_path=remote_scratch_dir,
                    is_remote_dir=True,
                )

            cmd.append(remote_script_path)
            result = conn.run(" ".join(cmd), hide=False)
            job_id_match = re.search(r"Submitted batch job (\d+)", result.stdout)
            if job_id_match:
                job_id = job_id_match.group(1)
                return Job(job_id, slurm_host, self)
            else:
                return None

        except Exception as e:
            logger.debug(f"Failed to submit job on {host.hostname}: {e}")
            return None

    def cancel_job(self, slurm_host: SlurmHost | str, job_id: str) -> bool:
        """Cancel a SLURM job."""
        host = self.get_host_by_name(slurm_host)
        conn = self._get_connection(host.host)
        return self.slurm_client.cancel_job(conn, job_id)

    def get_job_info(
        self, slurm_host: SlurmHost | str, job_id: str, username: str | None = None
    ) -> Optional[JobInfo]:
        """Get detailed information about a SLURM job."""
        host = self.get_host_by_name(slurm_host)
        conn = self._get_connection(host.host)
        return self.slurm_client.get_job_details(
            conn, job_id, host.host.hostname, username
        )

    def get_host_by_name(self, hostname: str | SlurmHost) -> SlurmHost:
        """Get a SLURM host by hostname."""
        if isinstance(hostname, SlurmHost):
            return hostname
        for slurm_host in self.slurm_hosts:
            if slurm_host.host.hostname == hostname:
                return slurm_host
        raise ValueError(f"Host {hostname} not found")

    def check_connection_health(self) -> int:
        """Check health of SSH connections."""
        return self.connection_manager.check_connection_health()

    def get_connection_stats(self) -> dict:
        """Get SSH connection statistics."""
        return self.connection_manager.get_connection_stats()

    def close_connections(self):
        """Close all SSH connections."""
        self.connection_manager.close_connections()
