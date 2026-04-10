"""CLI command implementations."""

from pathlib import Path
from typing import List, Optional
import json

import click
import requests

from ..api import APIClient
from ..manager import SlurmManager
from ..sync import SyncManager
from .display import JobDisplay, PartitionDisplay


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
            api_client = APIClient(verbose=self.verbose)

            # Start API server
            success, error_msg = api_client.ensure_server_running(self.config_path)
            if not success:
                click.echo(f"Failed to start API server: {error_msg}", err=True)
                return False

            # When querying specific job IDs, ignore since/limit to get precise results
            query_since = None if job_ids else since
            query_limit = None if job_ids else limit

            # Get jobs via API
            jobs = api_client.get_jobs(
                host=host,
                user=user,
                since=query_since,
                limit=query_limit,
                job_ids=job_ids,
                state_filter=state,
                active_only=active_only,
                completed_only=completed_only,
            )

            # Group jobs by hostname for display
            jobs_by_host = JobDisplay.group_jobs_by_host(jobs)

            # Ensure all configured hosts are shown (or just the requested one)
            hosts_to_show = (
                [host] if host else [h.host.hostname for h in self.slurm_hosts]
            )
            for hostname in hosts_to_show:
                if hostname not in jobs_by_host:
                    jobs_by_host[hostname] = []

            # Display results
            if cat_output and job_ids:
                click.echo("Note: --cat-output not supported with API mode yet")

            JobDisplay.display_jobs_by_host(jobs_by_host, simple)
            return True

        except requests.exceptions.ConnectionError:
            click.echo(
                "Could not connect to API server. Use 'ssync api' to start it manually.",
                err=True,
            )
            return False
        except Exception as e:
            click.echo(f"Error getting jobs: {str(e)}", err=True)
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False


class PartitionsCommand(BaseCommand):
    """Handles the partitions command logic."""

    def execute(
        self,
        host: Optional[str] = None,
        force_refresh: bool = False,
        json_output: bool = False,
    ):
        """Execute partitions command."""
        # Filter hosts if specific host requested
        if host:
            filtered_hosts = [h for h in self.slurm_hosts if h.host.hostname == host]
            if not filtered_hosts:
                click.echo(f"Host '{host}' not found in configuration", err=True)
                return False

        try:
            api_client = APIClient(verbose=self.verbose)

            success, error_msg = api_client.ensure_server_running(self.config_path)
            if not success:
                click.echo(f"Failed to start API server: {error_msg}", err=True)
                return False

            responses = api_client.get_partitions(
                host=host, force_refresh=force_refresh
            )

            if json_output:
                click.echo(json.dumps(responses, indent=2))
                return True

            PartitionDisplay.display_partition_status(responses)
            return True

        except requests.exceptions.ConnectionError:
            click.echo(
                "Could not connect to API server. Use 'ssync api' to start it manually.",
                err=True,
            )
            return False
        except Exception as e:
            click.echo(f"Error getting partition state: {str(e)}", err=True)
            if self.verbose:
                import traceback

                traceback.print_exc()
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
            # Initialize Slurm manager
            slurm_manager = SlurmManager(self.slurm_hosts, use_ssh_config=True)

            # Get path restrictions from config
            from ..utils.config import config

            # Initialize sync manager
            sync_manager = SyncManager(
                slurm_manager=slurm_manager,
                source_dir=source_dir,
                use_gitignore=not no_gitignore,
                max_depth=max_depth,
                path_restrictions=config.path_restrictions,
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


class LaunchCommand(BaseCommand):
    """Handles the launch command logic via API."""

    def _follow_launch(self, api_client: APIClient, launch_id: str) -> tuple[bool, Optional[str], str]:
        last_stage = None
        last_message = ""
        final_job_id = None

        try:
            for event in api_client.stream_launch_events(launch_id):
                event_type = event.get("type")
                message = event.get("message") or ""

                if event_type == "launch_stage":
                    stage = event.get("stage")
                    if stage != last_stage or (message and message != last_message):
                        if message:
                            click.echo(message)
                        elif stage:
                            click.echo(f"Launch stage: {stage}")
                    last_stage = stage
                    last_message = message or last_message
                elif event_type == "launch_log" and self.verbose and message:
                    source = event.get("source", "launch")
                    stream = event.get("stream", "stdout")
                    click.echo(f"[{source}/{stream}] {message}")
                elif event_type == "launch_result":
                    final_job_id = event.get("job_id")
                    return bool(event.get("success")), final_job_id, message
        except requests.exceptions.RequestException as exc:
            if self.verbose:
                click.echo(f"Launch stream interrupted: {exc}", err=True)

        status = api_client.get_launch_status(launch_id)
        final_job_id = status.get("job_id")
        return bool(status.get("success")), final_job_id, status.get("message", "")

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
        abort_on_setup_failure: bool = True,
    ):
        """Execute launch command via API."""
        try:
            # Read script content
            if not script_path.exists():
                click.echo(f"Script file not found: {script_path}", err=True)
                return False

            with open(script_path, "r") as f:
                script_content = f.read()

            # Initialize API client
            api_client = APIClient(verbose=self.verbose)

            # Start API server if not running
            success, error_msg = api_client.ensure_server_running(self.config_path)
            if not success:
                click.echo(f"Failed to start API server: {error_msg}", err=True)
                return False

            # Convert source_dir to absolute path string if provided
            if source_dir:
                source_dir_path = Path(source_dir).resolve()
                source_dir_str = str(source_dir_path)
            else:
                source_dir_str = None

            # Launch job via API
            launch_response = api_client.launch_job(
                script_content=script_content,
                source_dir=source_dir_str,
                host=host,
                job_name=job_name,
                cpus=cpus,
                mem=mem,
                time=time,
                partition=partition,
                output=output,
                error=error,
                constraint=constraint,
                account=account,
                nodes=nodes,
                ntasks_per_node=ntasks_per_node,
                gpus_per_node=gpus_per_node,
                gres=gres,
                python_env=python_env,
                exclude=exclude,
                include=include,
                no_gitignore=no_gitignore,
                abort_on_setup_failure=abort_on_setup_failure,
            )

            success = bool(launch_response.get("success"))
            job_id = launch_response.get("job_id")
            launch_id = launch_response.get("launch_id")
            message = launch_response.get("message", "")

            if success:
                if job_id:
                    click.echo(f"Job launched successfully with ID: {job_id}")
                    return True

                if not launch_id:
                    click.echo(message or "Launch started but no job ID was returned.")
                    return True

                click.echo(message or f"Launch started with ID: {launch_id}")
                success, job_id, message = self._follow_launch(api_client, launch_id)
                if success and job_id:
                    click.echo(f"Job launched successfully with ID: {job_id}")
                    return True
                if success:
                    click.echo(message or f"Launch {launch_id} completed successfully")
                    return True
                click.echo(message or f"Launch {launch_id} failed", err=True)
                return False
            else:
                # Message already contains error details, don't add prefix
                click.echo(message, err=True)
                return False

        except Exception as e:
            click.echo(f"Error launching job: {e}", err=True)
            return False


class CopyOutputCommand(BaseCommand):
    """Handles copying job output files via the API."""

    def execute(
        self,
        job_id: str,
        destination: Path,
        host: Optional[str] = None,
        output_type: str = "both",
        compressed: bool = False,
        overwrite: bool = False,
    ):
        """Execute output copy command."""
        try:
            api_client = APIClient(verbose=self.verbose)

            success, error_msg = api_client.ensure_server_running(self.config_path)
            if not success:
                click.echo(f"Failed to start API server: {error_msg}", err=True)
                return False

            if not host:
                if self.verbose:
                    click.echo(f"No host specified, searching for job {job_id}...")

                jobs = api_client.get_jobs(job_ids=[job_id])
                if not jobs:
                    click.echo(
                        f"Job {job_id} not found on any configured host", err=True
                    )
                    return False

                matching_hosts = sorted({job.hostname for job in jobs if job.hostname})
                if len(matching_hosts) > 1:
                    click.echo(
                        (
                            f"Job {job_id} was found on multiple hosts: "
                            f"{', '.join(matching_hosts)}. Specify --host."
                        ),
                        err=True,
                    )
                    return False

                host = matching_hosts[0]
                if self.verbose:
                    click.echo(f"Found job {job_id} on host {host}")

            host_exists = any(h.host.hostname == host for h in self.slurm_hosts)
            if not host_exists:
                click.echo(f"Host '{host}' not found in configuration", err=True)
                return False

            output_metadata = api_client.get_job_output(
                job_id=job_id,
                host=host,
                metadata_only=True,
            )

            requested_outputs = ["stdout", "stderr"]
            if output_type != "both":
                requested_outputs = [output_type]

            available_outputs = []
            missing_outputs = []
            for current_output in requested_outputs:
                metadata = output_metadata.get(f"{current_output}_metadata")
                if metadata and metadata.get("exists"):
                    available_outputs.append(current_output)
                else:
                    missing_outputs.append(current_output)

            if not available_outputs:
                requested_summary = ", ".join(requested_outputs)
                click.echo(
                    f"No {requested_summary} output available for job {job_id} on {host}",
                    err=True,
                )
                return False

            destination = destination.expanduser()
            if destination.exists() and not destination.is_dir():
                click.echo(
                    f"Destination must be a directory: {destination}", err=True
                )
                return False

            downloads = []
            for current_output in available_outputs:
                filename, content = api_client.download_job_output(
                    job_id=job_id,
                    host=host,
                    output_type=current_output,
                    compressed=compressed,
                )
                downloads.append((current_output, destination / filename, content))

            existing_paths = [
                str(target_path)
                for _, target_path, _ in downloads
                if target_path.exists() and not overwrite
            ]
            if existing_paths:
                click.echo(
                    (
                        "Refusing to overwrite existing output file(s): "
                        + ", ".join(existing_paths)
                        + ". Use --overwrite to replace them."
                    ),
                    err=True,
                )
                return False

            destination.mkdir(parents=True, exist_ok=True)
            for current_output, target_path, content in downloads:
                target_path.write_bytes(content)
                click.echo(f"Copied {current_output} to {target_path}")

            if missing_outputs:
                click.echo(
                    (
                        f"Skipped unavailable output(s) for job {job_id}: "
                        + ", ".join(missing_outputs)
                    ),
                    err=True,
                )

            return True

        except requests.exceptions.ConnectionError:
            click.echo(
                "Could not connect to API server. Use 'ssync api' to start it manually.",
                err=True,
            )
            return False
        except requests.exceptions.HTTPError as e:
            message = None
            response = getattr(e, "response", None)
            if response is not None:
                try:
                    payload = response.json()
                    message = payload.get("detail")
                except ValueError:
                    message = response.text.strip() or None
            click.echo(
                f"Error copying job output: {message or str(e)}",
                err=True,
            )
            return False
        except Exception as e:
            click.echo(f"Error copying job output: {e}", err=True)
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False


class CancelCommand(BaseCommand):
    """Handles the cancel command logic."""

    def execute(
        self,
        job_id: str,
        host: Optional[str] = None,
    ):
        """Execute cancel command."""
        try:
            # Initialize API client
            api_client = APIClient(verbose=self.verbose)

            # Start API server if not running
            success, error_msg = api_client.ensure_server_running(self.config_path)
            if not success:
                click.echo(f"Failed to start API server: {error_msg}", err=True)
                return False

            # If host not provided, try to find the job on any configured host
            if not host:
                if self.verbose:
                    click.echo(f"No host specified, searching for job {job_id}...")

                # Get all jobs to find which host has this job
                jobs = api_client.get_jobs(job_ids=[job_id])

                if not jobs:
                    click.echo(
                        f"Job {job_id} not found on any configured host", err=True
                    )
                    return False

                # Use the host from the found job (JobInfo object has hostname attribute)
                host = jobs[0].hostname
                if self.verbose:
                    click.echo(f"Found job {job_id} on host {host}")

            # Verify host exists in configuration
            host_exists = any(h.host.hostname == host for h in self.slurm_hosts)
            if not host_exists:
                click.echo(f"Host '{host}' not found in configuration", err=True)
                return False

            # Cancel job via API
            success, message = api_client.cancel_job(job_id=job_id, host=host)

            if success:
                click.echo(f"Successfully cancelled job {job_id} on {host}")
                return True
            else:
                click.echo(f"Failed to cancel job: {message}", err=True)
                return False

        except requests.exceptions.ConnectionError:
            click.echo(
                "Could not connect to API server. Use 'ssync api' to start it manually.",
                err=True,
            )
            return False
        except Exception as e:
            click.echo(f"Error cancelling job: {e}", err=True)
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False
