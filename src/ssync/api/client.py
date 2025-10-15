"""API client for communicating with ssync web API."""

import warnings
from pathlib import Path
from typing import List, Optional

import requests
from urllib3.exceptions import InsecureRequestWarning

from ..models.job import JobInfo, JobState
from ..utils.logging import setup_logger
from .server import ServerManager

# Suppress SSL warnings for self-signed certificates
warnings.filterwarnings("ignore", category=InsecureRequestWarning)

logger = setup_logger(__name__, "INFO")


class ApiClient:
    """Client for communicating with ssync web API."""

    def __init__(self, base_url: str = "https://localhost:8042", verbose: bool = False):
        self.base_url = base_url
        self.server_manager = ServerManager(base_url)
        self.verbose = verbose
        self.api_key = self._get_api_key()

    def _get_api_key(self) -> Optional[str]:
        """Get API key from config or environment."""
        try:
            from ..utils.config import config as global_config

            return global_config.api_key if global_config.api_key else None
        except Exception:
            return None

    def _get_headers(self) -> dict:
        """Get headers including API key if available."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def ensure_server_running(self, config_path: Path) -> tuple[bool, Optional[str]]:
        """Ensure API server is running, start if needed.

        Returns:
            tuple of (success, error_message)
        """
        try:
            if self.server_manager.is_running():
                if self.verbose:
                    logger.info("API server already running")
                return True, None

            if self.verbose:
                logger.info("Starting API server...")

            if self.server_manager.start(config_path):
                return True, None
            else:
                # Get logs for debugging
                logs = self.server_manager.get_logs(30)
                if logs:
                    return False, f"Failed to start API server. Recent logs:\n{logs}"
                else:
                    return False, "Failed to start API server (no logs available)"
        except Exception as e:
            return False, f"Failed to start API server: {str(e)}"

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

        response = requests.get(
            f"{self.base_url}/api/status",
            params=params,
            headers=self._get_headers(),
            timeout=30,
            verify=False,
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
                    node_list=job_data.get("node_list"),
                    array_job_id=job_data.get("array_job_id"),
                    array_task_id=job_data.get("array_task_id"),
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

    def launch_job(
        self,
        script_content: str,
        source_dir: Optional[str],
        host: str,
        job_name: Optional[str] = None,
        cpus: Optional[int] = None,
        mem: Optional[int] = None,
        time: Optional[int] = None,
        partition: Optional[str] = None,
        output: Optional[str] = None,
        error: Optional[str] = None,
        constraint: Optional[str] = None,
        account: Optional[str] = None,
        nodes: Optional[int] = None,
        ntasks_per_node: Optional[int] = None,
        gpus_per_node: Optional[int] = None,
        gres: Optional[str] = None,
        python_env: Optional[str] = None,
        exclude: Optional[List[str]] = None,
        include: Optional[List[str]] = None,
        no_gitignore: bool = False,
        abort_on_setup_failure: bool = True,
    ) -> tuple[bool, Optional[str], str]:
        """Launch a job via the API.

        Returns:
            tuple of (success, job_id, message)
        """
        request_data = {
            "script_content": script_content,
            "host": host,
        }

        # Add optional parameters
        if source_dir:
            request_data["source_dir"] = source_dir
        if job_name:
            request_data["job_name"] = job_name
        if cpus is not None:
            request_data["cpus"] = cpus
        if mem is not None:
            request_data["mem"] = mem
        if time is not None:
            request_data["time"] = time
        if partition:
            request_data["partition"] = partition
        if output:
            request_data["output"] = output
        if error:
            request_data["error"] = error
        if constraint:
            request_data["constraint"] = constraint
        if account:
            request_data["account"] = account
        if nodes is not None:
            request_data["nodes"] = nodes
        if ntasks_per_node is not None:
            request_data["n_tasks_per_node"] = ntasks_per_node
        if gpus_per_node is not None:
            request_data["gpus_per_node"] = gpus_per_node
        if gres:
            request_data["gres"] = gres
        if python_env:
            request_data["python_env"] = python_env
        if exclude:
            request_data["exclude"] = exclude
        if include:
            request_data["include"] = include
        if no_gitignore:
            request_data["no_gitignore"] = no_gitignore
        if not abort_on_setup_failure:
            request_data["abort_on_setup_failure"] = False

        try:
            response = requests.post(
                f"{self.base_url}/api/jobs/launch",
                json=request_data,
                headers=self._get_headers(),
                timeout=120,  # Longer timeout for launch operations
                verify=False,
            )

            if not response.ok:
                # Try to get error details from response
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", str(response.text))
                except Exception:
                    error_msg = f"HTTP {response.status_code}: {response.reason}"
                    if response.text:
                        error_msg += f" - {response.text[:200]}"
                # Don't log here to avoid duplication - let the caller handle display
                logger.debug(f"API request failed: {error_msg}")
                return False, None, error_msg

            data = response.json()
            return data["success"], data.get("job_id"), data["message"]

        except requests.exceptions.Timeout:
            return False, None, "API request timed out (server may be overloaded)"
        except requests.exceptions.ConnectionError:
            return (
                False,
                None,
                f"Could not connect to API server at {self.base_url}. Is it running?",
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            return False, None, f"API request failed: {str(e)}"
