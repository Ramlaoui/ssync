"""CLI command implementations."""

from pathlib import Path
from typing import List, Optional

import click

from ..api import ApiClient
from ..launch import LaunchManager
from ..manager import SlurmManager
from ..sync import SyncManager
from ..utils.slurm_params import SlurmParams
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
        max_depth: int = 3,
    ):
        """Execute sync command."""
        try:
            # Initialize SLURM manager
            slurm_manager = SlurmManager(self.slurm_hosts, use_ssh_config=True)

            # Initialize sync manager
            sync_manager = SyncManager(
                slurm_manager=slurm_manager,
                source_dir=source_dir,
                use_gitignore=not no_gitignore,
                max_depth=max_depth,
            )

            # Filter hosts if specific host requested
            if host:
                filtered_hosts = [
                    h for h in self.slurm_hosts if h.host.hostname == host
                ]
                if not filtered_hosts:
                    click.echo(f"Host '{host}' not found in configuration", err=True)
                    return False
                target_host = filtered_hosts[0]

                # Sync to specific host
                if self.verbose:
                    click.echo(f"Syncing {source_dir} to {host}...")

                success = sync_manager.sync_to_host(
                    slurm_host=target_host,
                    exclude=exclude or [],
                    include_patterns=include or [],
                )

                if success:
                    click.echo(f"Successfully synced to {host}")
                    return True
                else:
                    click.echo(f"Failed to sync to {host}", err=True)
                    return False
            else:
                # Sync to all hosts
                if self.verbose:
                    click.echo(f"Syncing {source_dir} to all hosts...")

                results = sync_manager.sync_to_all(
                    exclude=exclude or [], include_patterns=include or []
                )

                success_count = sum(1 for success in results.values() if success)
                total_count = len(results)

                for hostname, success in results.items():
                    if success:
                        click.echo(f"✓ Successfully synced to {hostname}")
                    else:
                        click.echo(f"✗ Failed to sync to {hostname}")

                if success_count == total_count:
                    click.echo(f"Successfully synced to all {total_count} hosts")
                    return True
                else:
                    click.echo(
                        f"Synced to {success_count}/{total_count} hosts", err=True
                    )
                    return success_count > 0

        except Exception as e:
            click.echo(f"Error during sync: {e}", err=True)
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


class LaunchCommand(BaseCommand):
    """Handles the launch command logic."""

    def execute(
        self,
        script_path: Path,
        source_dir: Path,
        host: str,
        job_name: Optional[str] = None,
        cpus: Optional[int] = None,
        mem: Optional[int] = None,
        time: Optional[int] = None,
        partition: Optional[str] = None,
        ntasks_per_node: Optional[int] = None,
        nodes: Optional[int] = None,
        gpus_per_node: Optional[int] = None,
        gres: Optional[str] = None,
        output: Optional[str] = None,
        error: Optional[str] = None,
        constraint: Optional[str] = None,
        account: Optional[str] = None,
        python_env: Optional[str] = None,
        exclude: List[str] = None,
        include: List[str] = None,
        no_gitignore: bool = False,
        no_defaults: bool = False,
    ):
        """Execute launch command."""
        try:
            # Initialize SLURM manager
            slurm_manager = SlurmManager(self.slurm_hosts, use_ssh_config=True)

            # Get the target host to access its defaults
            try:
                slurm_host = slurm_manager.get_host_by_name(host)
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)
                return False

            # Initialize launch manager
            launch_manager = LaunchManager(slurm_manager)

            # Start with host defaults if available and not disabled
            if not no_defaults and slurm_host.slurm_defaults:
                defaults = slurm_host.slurm_defaults
                # Create params starting with defaults
                slurm_params = SlurmParams(
                    job_name=job_name
                    or (
                        defaults.job_name_prefix + "_job"
                        if defaults.job_name_prefix
                        else None
                    ),
                    time_min=time
                    if time is not None
                    else (
                        int(defaults.time)
                        if defaults.time and defaults.time.isdigit()
                        else None
                    ),
                    cpus_per_task=cpus if cpus is not None else defaults.cpus,
                    mem_gb=mem if mem is not None else defaults.mem,
                    partition=partition or defaults.partition,
                    output=output or defaults.output_pattern,
                    error=error or defaults.error_pattern,
                    constraint=constraint or defaults.constraint,
                    account=account or defaults.account,
                    nodes=nodes if nodes is not None else defaults.nodes,
                    n_tasks_per_node=ntasks_per_node
                    if ntasks_per_node is not None
                    else defaults.ntasks_per_node,
                    gpus_per_node=gpus_per_node
                    if gpus_per_node is not None
                    else defaults.gpus_per_node,
                    gres=gres or defaults.gres,
                )
                # Use default python_env if not provided
                if not python_env and defaults.python_env:
                    python_env = defaults.python_env
            else:
                # No defaults or explicitly disabled - use only CLI params
                slurm_params = SlurmParams(
                    job_name=job_name,
                    time_min=time,
                    cpus_per_task=cpus,
                    mem_gb=mem,
                    partition=partition,
                    output=output,
                    error=error,
                    constraint=constraint,
                    account=account,
                    nodes=nodes,
                    n_tasks_per_node=ntasks_per_node,
                    gpus_per_node=gpus_per_node,
                    gres=gres,
                )

            job = launch_manager.launch_job(
                script_path=script_path,
                source_dir=source_dir,
                host=host,
                slurm_params=slurm_params,
                python_env=python_env,
                exclude=exclude or [],
                include=include or [],
                no_gitignore=no_gitignore,
            )

            if job:
                click.echo(f"Job launched successfully with ID: {job.job_id}")
                return True
            else:
                click.echo("Failed to launch job", err=True)
                return False

        except Exception as e:
            click.echo(f"Error launching job: {e}", err=True)
            return False
