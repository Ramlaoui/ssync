"""Simplified Slurm manager using refactored components."""

import re
from dataclasses import dataclass
from typing import List, Optional

from .models import JobInfo
from .models.cluster import Host, SlurmHost
from .slurm import SlurmClient
from .slurm.params import SlurmParams
from .ssh.helpers import send_file
from .ssh.manager import ConnectionManager
from .utils.config import config
from .utils.logging import setup_logger

logger = setup_logger(__name__, "INFO")


@dataclass
class Job:
    """Represents a submitted Slurm job."""

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
    """Manages Slurm operations across multiple hosts."""

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
        force_refresh: bool = False,
    ) -> List[JobInfo]:
        """Get all jobs from a Slurm host via JobDataManager."""
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
            force_refresh=force_refresh,
        )
        return jobs

    def submit_script(
        self,
        slurm_host: SlurmHost | str,
        params: SlurmParams | None = None,
        local_script_path: str | None = None,
        remote_script_path: str | None = None,
        enable_watchers: bool = True,
    ) -> Optional[Job]:
        """Submit a script to Slurm."""

        params = params or SlurmParams()

        if isinstance(slurm_host, str):
            slurm_host = self.get_host_by_name(slurm_host)

        host = slurm_host.host
        conn = self._get_connection(host)

        try:
            if local_script_path:
                remote_scratch_dir = config.get_remote_cache_path(slurm_host)
                remote_script_path = send_file(
                    conn=conn,
                    local_path=local_script_path,
                    remote_path=remote_scratch_dir,
                    is_remote_dir=True,
                )

            # Extract watchers from script if enabled
            watchers = []
            script_content = None
            if enable_watchers and local_script_path:
                try:
                    from pathlib import Path

                    from .parsers.script_processor import ScriptProcessor

                    script_content = Path(local_script_path).read_text()
                    watchers, _ = ScriptProcessor.extract_watchers(script_content)

                    if watchers:
                        logger.info(f"Found {len(watchers)} watchers in script")
                except Exception as e:
                    logger.warning(f"Failed to extract watchers: {e}")

            result, _full_cmd, _cmd, submit_line = self.slurm_client.submit.run_sbatch(
                conn,
                params,
                remote_script_path,
                work_dir=None,
                warn=True,
            )
            job_id_match = re.search(r"Submitted batch job (\d+)", result.stdout)
            if job_id_match:
                job_id = job_id_match.group(1)

                # Cache the submit line for this job
                try:
                    from .cache import get_cache
                    from .models.job import JobInfo, JobState

                    cache = get_cache()
                    # Create a basic job info with the submit line
                    job_info = JobInfo(
                        job_id=job_id,
                        name=params.job_name or "unknown",
                        state=JobState.PENDING,  # Will be updated when job is queried
                        hostname=slurm_host.host.hostname
                        if isinstance(slurm_host, SlurmHost)
                        else slurm_host,
                        submit_line=submit_line,
                        user=None,  # Will be updated when job is queried
                    )
                    cache.cache_job(job_info)
                except Exception as e:
                    logger.warning(f"Failed to cache submit line for job {job_id}: {e}")

                # Start watchers if any were found
                if watchers and enable_watchers:
                    try:
                        import asyncio

                        from .watchers import get_watcher_engine
                        from .watchers.daemon import start_daemon_if_needed

                        engine = get_watcher_engine()
                        # Run async function in sync context
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            watcher_ids = loop.run_until_complete(
                                engine.start_watchers_for_job(
                                    job_id,
                                    slurm_host.host.hostname
                                    if isinstance(slurm_host, SlurmHost)
                                    else slurm_host,
                                    watchers,
                                )
                            )
                            if watcher_ids:
                                logger.info(
                                    f"Started {len(watcher_ids)} watchers for job {job_id}"
                                )

                                # Start the watcher daemon to monitor them
                                if start_daemon_if_needed():
                                    logger.info(
                                        "Watcher daemon is running to monitor watchers"
                                    )
                                else:
                                    logger.warning(
                                        "Failed to start watcher daemon - watchers won't be monitored"
                                    )
                        finally:
                            loop.close()
                    except Exception as e:
                        logger.error(f"Failed to start watchers for job {job_id}: {e}")

                # Cache script content if available
                if script_content:
                    try:
                        from .cache import get_cache

                        cache = get_cache()
                        cache.update_job_script(
                            job_id,
                            slurm_host.host.hostname
                            if isinstance(slurm_host, SlurmHost)
                            else slurm_host,
                            script_content,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to cache script for job {job_id}: {e}")

                return Job(job_id, slurm_host, self)
            else:
                return None

        except Exception as e:
            logger.debug(f"Failed to submit job on {host.hostname}: {e}")
            return None

    def cancel_job(self, slurm_host: SlurmHost | str, job_id: str) -> bool:
        """Cancel a Slurm job."""
        host = self.get_host_by_name(slurm_host)
        conn = self._get_connection(host.host)
        return self.slurm_client.cancel_job(conn, job_id)

    def get_partition_state(
        self, slurm_host: SlurmHost | str, force_refresh: bool = False
    ):
        """Get partition resource state from a Slurm host."""
        host = self.get_host_by_name(slurm_host)
        conn = self._get_connection(host.host)
        return self.slurm_client.get_partition_state(
            conn, host.host.hostname, force_refresh=force_refresh
        )

    def fetch_job_output_compressed(
        self, job_id: str, hostname: str, output_type: str = "stdout"
    ) -> dict | None:
        """Fetch and compress job output from remote host.

        Args:
            job_id: Job ID
            hostname: Hostname
            output_type: 'stdout' or 'stderr'

        Returns:
            Dictionary with compressed data or None
        """
        try:
            host = self.get_host_by_name(hostname)
            conn = self._get_connection(host.host)
            return self.slurm_client.read_job_output_compressed(
                conn, job_id, hostname, output_type
            )
        except Exception as e:
            logger.error(f"Error fetching compressed output: {e}")
            return None

    def get_job_info(
        self, slurm_host: SlurmHost | str, job_id: str, username: str | None = None
    ) -> Optional[JobInfo]:
        """Get detailed information about a Slurm job."""
        host = self.get_host_by_name(slurm_host)
        conn = self._get_connection(host.host)
        return self.slurm_client.get_job_details(
            conn, job_id, host.host.hostname, username
        )

    def get_host_by_name(self, hostname: str | SlurmHost) -> SlurmHost:
        """Get a Slurm host by hostname."""
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
