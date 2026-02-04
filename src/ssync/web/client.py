"""Authenticated API client for Slurm Manager."""

import os
import subprocess
import time
from pathlib import Path
from typing import List, Optional

import requests

from ..manager import JobInfo, JobState
from ..utils.logging import setup_logger

logger = setup_logger(__name__, "INFO")


class AuthenticatedSlurmAPIClient:
    """API client with authentication support."""

    def __init__(
        self, base_url: Optional[str] = None, api_key: Optional[str] = None
    ):
        """Initialize authenticated API client.

        Args:
            base_url: API server URL. If None, reads from config.
            api_key: API key for authentication. If None, reads from config/env.
        """
        from ..utils.config import config as global_config

        if base_url is None:
            self.base_url = global_config.api_settings.url
        else:
            self.base_url = base_url

        self.api_key = api_key or self._get_api_key()
        self.session = requests.Session()

        # Set up authentication if we have an API key
        if self.api_key:
            self.session.headers.update({"X-API-Key": self.api_key})

    def _get_api_key(self) -> Optional[str]:
        """Get API key from various sources."""
        # 1. Environment variable (highest priority)
        api_key = os.getenv("SSYNC_API_KEY")
        if api_key:
            return api_key

        # 2. Config file
        try:
            from ..utils.config import config as global_config

            config_path = global_config.config_path
            if config_path and config_path.exists():
                import yaml

                with open(config_path, "r") as f:
                    config_data = yaml.safe_load(f)
                    api_key = config_data.get("api_key")
                    if api_key:
                        return api_key
        except Exception:
            pass

        # 3. API key file in config directory
        try:
            api_key_file = Path.home() / ".config" / "ssync" / ".api_key"
            if api_key_file.exists():
                api_key = api_key_file.read_text().strip()
                if api_key:
                    return api_key
        except Exception:
            pass

        return None

    def is_running(self) -> bool:
        """Check if API is running."""
        try:
            # Health endpoint doesn't require auth
            response = requests.get(f"{self.base_url}/health", timeout=5, verify=False)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def test_auth(self) -> bool:
        """Test if authentication is working."""
        try:
            response = self.session.get(f"{self.base_url}/", timeout=5, verify=False)
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response and e.response.status_code == 401:
                logger.error("Authentication failed. Please check your API key.")
            return False

    def start_server(self, config_path: Path, secure: bool = True) -> bool:
        """Start API server if not running."""
        if self.is_running():
            logger.info("API server is already running")
            return True

        logger.info("Starting ssync API server...")
        try:
            # Use the unified app module (security is handled within app.py)
            app_module = "ssync.web.app"

            # Start API server in background
            cmd = [
                "uvicorn",
                f"{app_module}:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ]

            # Set up environment for secure mode
            env = os.environ.copy()
            if secure and not self.api_key:
                # If no API key exists, run in open mode temporarily
                env["SSYNC_REQUIRE_API_KEY"] = "false"
                logger.warning(
                    "Starting in open mode (no API key configured). Run 'ssync auth setup' to enable security."
                )

            # Start in background, detached from terminal
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
                cwd=Path(__file__).parent.parent.parent.parent,
            )

            # Wait for API to start
            for i in range(20):  # Wait up to 10 seconds
                time.sleep(0.5)
                if self.is_running():
                    logger.info("API server started successfully")

                    # Test authentication if we have an API key
                    if self.api_key and not self.test_auth():
                        logger.warning("API is running but authentication failed")

                    return True

            logger.error("Failed to start API server")
            return False

        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
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

        response = self.session.get(
            f"{self.base_url}/status", params=params, timeout=30
        )

        if response.status_code == 401:
            raise Exception(
                "Authentication failed. Please run 'ssync auth setup' to configure API key."
            )

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

    def launch_job(self, request_data: dict) -> dict:
        """Launch a job through the API."""
        response = self.session.post(
            f"{self.base_url}/jobs/launch", json=request_data, timeout=60
        )

        if response.status_code == 401:
            raise Exception(
                "Authentication failed. Please run 'ssync auth setup' to configure API key."
            )

        response.raise_for_status()
        return response.json()


# Backward compatibility - use authenticated client by defaultSlurmAPIClient = AuthenticatedSlurmAPIClient
