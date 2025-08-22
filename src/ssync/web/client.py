import subprocess
import time
from pathlib import Path
from typing import List, Optional

import requests

from ..manager import JobInfo, JobState
from ..utils.logging import setup_logger

logger = setup_logger(__name__, "DEBUG")


class SlurmApiClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def is_running(self) -> bool:
        """Check if API is running."""
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def start_server(self, config_path: Path) -> bool:
        """Start API server if not running."""
        if self.is_running():
            return True

        logger.debug("Starting ssync API server...")
        try:
            # Start API server in background
            cmd = [
                "uvicorn",
                "src.ssync.web.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ]

            # Start in background, detached from terminal
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent
                cwd=Path(
                    __file__
                ).parent.parent.parent.parent,  # Set working directory to project root
            )

            # Wait for API to start
            for i in range(20):  # Wait up to 10 seconds
                time.sleep(0.5)
                if self.is_running():
                    logger.debug("API server started successfully")
                    return True

            logger.debug("Failed to start API server")
            return False

        except Exception as e:
            logger.debug(f"Failed to start API server: {e}")
            return False

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
                )
                all_jobs.append(job)

        return all_jobs
