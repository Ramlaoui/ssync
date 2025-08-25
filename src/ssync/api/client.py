"""API client for communicating with ssync web API."""

from pathlib import Path
from typing import List, Optional

import requests

from ..models.job import JobInfo, JobState
from ..utils.logging import setup_logger
from .server import ServerManager

logger = setup_logger(__name__, "DEBUG")


class ApiClient:
    """Client for communicating with ssync web API."""

    def __init__(self, base_url: str = "http://localhost:8042"):
        self.base_url = base_url
        self.server_manager = ServerManager(base_url)

    def ensure_server_running(self, config_path: Path) -> bool:
        """Ensure API server is running, start if needed."""
        return self.server_manager.start(config_path)

    def get_jobs(
        self,
        host: Optional[str] = None,
        user: Optional[str] = None,
        since: Optional[str] = None,
        limit: Optional[int] = None,
        job_ids: Optional[List[str]] = None,
        state_filter: Optional[str] = None,
        active_only: bool = False,
        completed_only: bool = False,
    ) -> List[JobInfo]:
        """Get jobs from API and convert to JobInfo objects."""
        # Build query parameters
        params = {}
        if host:
            params["host"] = host
        if user:
            params["user"] = user
        if since:
            params["since"] = since
        if limit:
            params["limit"] = limit
        if job_ids:
            params["job_ids"] = ",".join(job_ids)
        if state_filter:
            params["state"] = state_filter
        if active_only:
            params["active_only"] = "true"
        if completed_only:
            params["completed_only"] = "true"

        response = requests.get(f"{self.base_url}/status", params=params, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Extract jobs from all hosts and convert to JobInfo objects
        all_jobs = []

        for host_response in data:
            jobs_data = host_response.get("jobs", [])
            hostname = host_response.get("hostname", "unknown")

            for job_data in jobs_data:
                try:
                    state = JobState(job_data["state"])
                except ValueError:
                    state = JobState.UNKNOWN

                job = JobInfo(
                    job_id=job_data["job_id"],
                    name=job_data["name"],
                    state=state,
                    hostname=hostname,
                    user=job_data.get("user"),
                    partition=job_data.get("partition"),
                    nodes=job_data.get("nodes"),
                    cpus=job_data.get("cpus"),
                    memory=job_data.get("memory"),
                    time_limit=job_data.get("time_limit"),
                    runtime=job_data.get("runtime"),
                    reason=job_data.get("reason"),
                    work_dir=job_data.get("work_dir"),
                    stdout_file=job_data.get("stdout_file"),
                    stderr_file=job_data.get("stderr_file"),
                    submit_time=job_data.get("submit_time"),
                    start_time=job_data.get("start_time"),
                    end_time=job_data.get("end_time"),
                    node_list=job_data.get("node_list"),
                    alloc_tres=job_data.get("alloc_tres"),
                    req_tres=job_data.get("req_tres"),
                    cpu_time=job_data.get("cpu_time"),
                    total_cpu=job_data.get("total_cpu"),
                    user_cpu=job_data.get("user_cpu"),
                    system_cpu=job_data.get("system_cpu"),
                    ave_cpu=job_data.get("ave_cpu"),
                    ave_cpu_freq=job_data.get("ave_cpu_freq"),
                    req_cpu_freq_min=job_data.get("req_cpu_freq_min"),
                    req_cpu_freq_max=job_data.get("req_cpu_freq_max"),
                    max_rss=job_data.get("max_rss"),
                    ave_rss=job_data.get("ave_rss"),
                    max_vmsize=job_data.get("max_vmsize"),
                    ave_vmsize=job_data.get("ave_vmsize"),
                    max_disk_read=job_data.get("max_disk_read"),
                    max_disk_write=job_data.get("max_disk_write"),
                    ave_disk_read=job_data.get("ave_disk_read"),
                    ave_disk_write=job_data.get("ave_disk_write"),
                    consumed_energy=job_data.get("consumed_energy"),
                )
                all_jobs.append(job)

        return all_jobs
