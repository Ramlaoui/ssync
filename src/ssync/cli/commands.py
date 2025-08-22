"""CLI command implementations."""

from pathlib import Path
from typing import List, Optional

import click

from ..api import ApiClient
from .display import JobDisplay


class BaseCommand:
    """Base class for CLI commands."""

    def __init__(self, config_path: Path, slurm_hosts: List, verbose: bool = False):
        self.config_path = config_path
        self.slurm_hosts = slurm_hosts
        self.verbose = verbose


class StatusCommand(BaseCommand):
    """Handles the status command logic."""

    def execute(
        self,
        host: Optional[str] = None,
        user: Optional[str] = None,
        simple: bool = False,
        since: Optional[str] = None,
        limit: Optional[int] = None,
        job_id: Optional[str] = None,
        state: Optional[str] = None,
        active_only: bool = False,
        completed_only: bool = False,
        cat_output: Optional[str] = None,
    ):
        """Execute status command."""
        # Validate conflicting flags
        if active_only and completed_only:
            click.echo(
                "Cannot use --active-only and --completed-only together", err=True
            )
            return False

        # Filter hosts if specific host requested
        if host:
            filtered_hosts = [h for h in self.slurm_hosts if h.host.hostname == host]
            if not filtered_hosts:
                click.echo(f"Host '{host}' not found in configuration", err=True)
                return False

        # Parse job IDs if provided
        job_ids = None
        if job_id:
            job_ids = [jid.strip() for jid in job_id.split(",")]

        try:
            # Initialize API client
            api_client = ApiClient()

            # Start API server
            if not api_client.ensure_server_running(self.config_path):
                click.echo("Failed to start API server", err=True)
                return False

            # Get jobs via API
            jobs = api_client.get_jobs(
                host=host,
                user=user,
                since=since,
                limit=limit,
                job_ids=job_ids,
                state_filter=state,
                active_only=active_only,
                completed_only=completed_only,
            )

            # Group jobs by hostname for display
            jobs_by_host = JobDisplay.group_jobs_by_host(jobs)

            # If no specific host requested, ensure all hosts are shown
            if not host:
                for slurm_host in self.slurm_hosts:
                    hostname = slurm_host.host.hostname
                    if hostname not in jobs_by_host:
                        jobs_by_host[hostname] = []

            # Display results
            if cat_output and job_ids:
                click.echo("Note: --cat-output not supported with API mode yet")

            JobDisplay.display_jobs_by_host(jobs_by_host, simple)
            return True

        except Exception as e:
            click.echo(f"Error getting jobs via API: {e}", err=True)
            return False


class SyncCommand(BaseCommand):
    """Handles the sync command logic."""

    def execute(
        self,
        source_dir: Path,
        exclude: List[str] = None,
        include: List[str] = None,
        no_gitignore: bool = False,
        host: Optional[str] = None,
    ):
        """Execute sync command."""
        click.echo(
            "Sync command will be implemented via API in a future update", err=True
        )
        return False


class SubmitCommand(BaseCommand):
    """Handles the submit command logic."""

    def execute(
        self,
        script_or_function: str,
        args: List[str] = None,
        host: Optional[str] = None,
        job_name: Optional[str] = None,
        cpus: Optional[int] = None,
        mem: Optional[int] = None,
        time: Optional[int] = None,
        partition: Optional[str] = None,
        output: Optional[str] = None,
        error: Optional[str] = None,
        python_env: Optional[str] = None,
    ):
        """Execute submit command."""
        click.echo(
            "Submit command will be implemented via API in a future update", err=True
        )
        return False
