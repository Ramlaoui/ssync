"""CLI command implementations."""

import json
from pathlib import Path
from typing import Any, List, Optional

import click
import requests

from ..api import APIClient
from ..manager import SlurmManager
from ..recipes import RecipeError, render_launch_recipe
from ..sync import SyncManager
from .display import JobDisplay, PartitionDisplay


class BaseCommand:
    """Base class for CLI commands."""

    def __init__(self, config_path: Path, slurm_hosts: List, verbose: bool = False):
        self.config_path = config_path
        self.slurm_hosts = slurm_hosts
        self.verbose = verbose

    def _resolve_job_host(self, api_client: APIClient, job_id: str, host: str | None):
        if host:
            host_exists = any(h.host.hostname == host for h in self.slurm_hosts)
            if not host_exists:
                click.echo(f"Host '{host}' not found in configuration", err=True)
                return None
            return host

        if self.verbose:
            click.echo(f"No host specified, searching for job {job_id}...")

        jobs = api_client.get_jobs(job_ids=[job_id])
        if not jobs:
            click.echo(f"Job {job_id} not found on any configured host", err=True)
            return None

        matching_hosts = sorted({job.hostname for job in jobs if job.hostname})
        if len(matching_hosts) > 1:
            click.echo(
                (
                    f"Job {job_id} was found on multiple hosts: "
                    f"{', '.join(matching_hosts)}. Specify --host."
                ),
                err=True,
            )
            return None

        resolved_host = matching_hosts[0]
        if self.verbose:
            click.echo(f"Found job {job_id} on host {resolved_host}")
        return resolved_host


def _format_mapping(mapping: dict[str, Any]) -> list[str]:
    return [f"  {key}: {value}" for key, value in sorted(mapping.items())]


_SBATCH_OVERRIDE_INT_FIELDS = {
    "cpus",
    "mem",
    "time",
    "nodes",
    "ntasks_per_node",
    "gpus_per_node",
}

_SBATCH_OVERRIDE_FIELDS = _SBATCH_OVERRIDE_INT_FIELDS | {
    "account",
    "constraint",
    "error",
    "gres",
    "job_name",
    "output",
    "partition",
}


def _parse_var_overrides(var_overrides: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in var_overrides:
        if "=" not in item:
            raise ValueError(f"Variable override must be KEY=VALUE: {item}")
        key, value = item.split("=", 1)
        if not key.isidentifier():
            raise ValueError(f"Invalid variable override name: {key}")
        parsed[key] = value
    return parsed


def _parse_sbatch_overrides(set_overrides: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for item in set_overrides:
        if "=" not in item:
            raise ValueError(f"Override must be sbatch.FIELD=VALUE: {item}")
        key, value = item.split("=", 1)
        if not key.startswith("sbatch."):
            raise ValueError(f"Only sbatch.* overrides are supported: {key}")
        field_name = key.removeprefix("sbatch.")
        if field_name not in _SBATCH_OVERRIDE_FIELDS:
            raise ValueError(f"Unsupported sbatch override field: {field_name}")
        if field_name in _SBATCH_OVERRIDE_INT_FIELDS:
            try:
                converted_value = int(value)
            except ValueError as exc:
                raise ValueError(
                    f"sbatch.{field_name} override must be an integer"
                ) from exc
            if converted_value <= 0:
                raise ValueError(
                    f"sbatch.{field_name} override must be a positive integer"
                )
            parsed[field_name] = converted_value
        else:
            parsed[field_name] = value
    return parsed


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

    def _follow_launch(
        self, api_client: APIClient, launch_id: str
    ) -> tuple[bool, Optional[str], str]:
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

    def _launch_script_content(
        self,
        script_content: str,
        source_dir: Optional[Path],
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
        abort_on_setup_failure: bool = True,
        launch_manifest: Optional[dict] = None,
    ) -> bool:
        try:
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
                launch_manifest=launch_manifest,
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

            return self._launch_script_content(
                script_content=script_content,
                source_dir=source_dir,
                host=host,
                job_name=job_name,
                cpus=cpus,
                mem=mem,
                time=time,
                partition=partition,
                ntasks_per_node=ntasks_per_node,
                nodes=nodes,
                gpus_per_node=gpus_per_node,
                gres=gres,
                output=output,
                error=error,
                constraint=constraint,
                account=account,
                python_env=python_env,
                exclude=exclude,
                include=include,
                no_gitignore=no_gitignore,
                abort_on_setup_failure=abort_on_setup_failure,
            )

        except Exception as e:
            click.echo(f"Error launching job: {e}", err=True)
            return False


class LaunchRecipeCommand(LaunchCommand):
    """Handles the launch-recipe command logic via rendered recipes."""

    def _echo_dry_run(
        self,
        rendered,
        *,
        host: str,
        job_name: Optional[str],
        sbatch: dict[str, Any],
        json_output: bool,
    ) -> None:
        manifest = dict(rendered.manifest)
        manifest["submit"] = {
            "host": host,
            "job_name": job_name,
            "sbatch": {
                key: value for key, value in sbatch.items() if value is not None
            },
        }

        if json_output:
            click.echo(json.dumps(manifest, indent=2, sort_keys=True))
            return

        click.echo(f"Recipe: {rendered.recipe_path}")
        click.echo(f"Source dir: {rendered.source_dir}")
        click.echo(f"Host: {host}")
        if job_name:
            click.echo(f"Job name: {job_name}")
        click.echo(f"Script sha256: {rendered.manifest['script_sha256']}")
        if sbatch:
            click.echo("Sbatch:")
            for line in _format_mapping(
                {key: value for key, value in sbatch.items() if value is not None}
            ):
                click.echo(line)
        if rendered.fragments:
            click.echo("Fragments:")
            for fragment in rendered.fragments:
                click.echo(f"  {fragment}")
        if rendered.manifest.get("watchers"):
            click.echo("Watchers:")
            for watcher in rendered.manifest["watchers"]:
                name = watcher.get("name") or watcher.get("policy_ref")
                click.echo(f"  {name}")
        if rendered.vars:
            click.echo("Variables:")
            for line in _format_mapping(rendered.vars):
                click.echo(line)
        click.echo("Rendered script:")
        click.echo(rendered.script_content)

    def execute(
        self,
        recipe_path: Path,
        workflow: Optional[str] = None,
        host_partition: Optional[str] = None,
        env_profile: Optional[str] = None,
        var_overrides: List[str] = None,
        set_overrides: List[str] = None,
        add_watchers: List[str] = None,
        remove_watchers: List[str] = None,
        host: Optional[str] = None,
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
        abort_on_setup_failure: bool = True,
        dry_run: bool = False,
        json_output: bool = False,
    ) -> bool:
        """Render a launch recipe and submit it via the existing launch API."""
        try:
            parsed_var_overrides = _parse_var_overrides(var_overrides or [])
            parsed_sbatch_overrides = _parse_sbatch_overrides(set_overrides or [])
        except ValueError as e:
            click.echo(f"Invalid launch recipe override: {e}", err=True)
            return False

        cli_overrides = {
            key: value
            for key, value in {
                "workflow": workflow,
                "host_partition": host_partition,
                "env": env_profile,
                "vars": parsed_var_overrides,
                "sbatch": parsed_sbatch_overrides,
                "add_watchers": add_watchers or [],
                "remove_watchers": remove_watchers or [],
            }.items()
            if value
        }

        try:
            rendered = render_launch_recipe(
                recipe_path,
                workflow=workflow,
                host_partition=host_partition,
                env=env_profile,
                vars=parsed_var_overrides,
                sbatch=parsed_sbatch_overrides,
                add_watchers=add_watchers or [],
                remove_watchers=remove_watchers or [],
                cli_overrides=cli_overrides,
            )
        except RecipeError as e:
            click.echo(f"Error rendering launch recipe: {e}", err=True)
            return False

        resolved_host = host or rendered.host
        if not resolved_host and not dry_run:
            click.echo(
                "Launch recipe does not define a host; pass --host.",
                err=True,
            )
            return False
        dry_run_host = resolved_host or "<not set>"

        resolved_job_name = job_name if job_name is not None else rendered.job_name
        resolved_cpus = cpus if cpus is not None else rendered.cpus
        resolved_mem = mem if mem is not None else rendered.mem
        resolved_time = time if time is not None else rendered.time
        resolved_partition = partition if partition is not None else rendered.partition
        resolved_ntasks = (
            ntasks_per_node if ntasks_per_node is not None else rendered.ntasks_per_node
        )
        resolved_nodes = nodes if nodes is not None else rendered.nodes
        resolved_gpus = (
            gpus_per_node if gpus_per_node is not None else rendered.gpus_per_node
        )
        resolved_gres = gres if gres is not None else rendered.gres
        resolved_output = output if output is not None else rendered.output
        resolved_error = error if error is not None else rendered.error
        resolved_constraint = (
            constraint if constraint is not None else rendered.constraint
        )
        resolved_account = account if account is not None else rendered.account
        resolved_python_env = (
            python_env if python_env is not None else rendered.python_env
        )
        resolved_sbatch = {
            "cpus": resolved_cpus,
            "mem": resolved_mem,
            "time": resolved_time,
            "partition": resolved_partition,
            "output": resolved_output,
            "error": resolved_error,
            "nodes": resolved_nodes,
            "ntasks_per_node": resolved_ntasks,
            "gpus_per_node": resolved_gpus,
            "gres": resolved_gres,
            "constraint": resolved_constraint,
            "account": resolved_account,
        }

        if dry_run:
            self._echo_dry_run(
                rendered,
                host=dry_run_host,
                job_name=resolved_job_name,
                sbatch=resolved_sbatch,
                json_output=json_output,
            )
            return True

        launch_manifest = dict(rendered.manifest)
        launch_manifest["sbatch"] = {
            key: value for key, value in resolved_sbatch.items() if value is not None
        }
        launch_manifest["submit"] = {
            "host": resolved_host,
            "job_name": resolved_job_name,
            "sbatch": launch_manifest["sbatch"],
        }

        return self._launch_script_content(
            script_content=rendered.script_content,
            source_dir=rendered.source_dir,
            host=resolved_host,
            job_name=resolved_job_name,
            cpus=resolved_cpus,
            mem=resolved_mem,
            time=resolved_time,
            partition=resolved_partition,
            ntasks_per_node=resolved_ntasks,
            nodes=resolved_nodes,
            gpus_per_node=resolved_gpus,
            gres=resolved_gres,
            output=resolved_output,
            error=resolved_error,
            constraint=resolved_constraint,
            account=resolved_account,
            python_env=resolved_python_env,
            exclude=exclude,
            include=include,
            no_gitignore=no_gitignore,
            abort_on_setup_failure=abort_on_setup_failure,
            launch_manifest=launch_manifest,
        )


class ManifestCommand(BaseCommand):
    """Handles displaying stored recipe launch manifests."""

    def execute(
        self,
        job_id: str,
        host: Optional[str] = None,
        json_output: bool = False,
    ) -> bool:
        """Fetch and display a stored run manifest."""
        try:
            api_client = APIClient(verbose=self.verbose)

            success, error_msg = api_client.ensure_server_running(self.config_path)
            if not success:
                click.echo(f"Failed to start API server: {error_msg}", err=True)
                return False

            resolved_host = self._resolve_job_host(api_client, job_id, host)
            if not resolved_host:
                return False

            try:
                manifest = api_client.get_run_manifest(job_id, resolved_host)
            except requests.exceptions.HTTPError as exc:
                status_code = exc.response.status_code if exc.response else None
                if status_code == 404:
                    click.echo(
                        f"No run manifest found for job {job_id} on {resolved_host}",
                        err=True,
                    )
                    return False
                raise

            if json_output:
                click.echo(json.dumps(manifest, indent=2, sort_keys=True))
                return True

            click.echo(f"Job: {job_id}")
            click.echo(f"Host: {resolved_host}")
            if manifest.get("recipe_path"):
                click.echo(f"Recipe: {manifest['recipe_path']}")
            if manifest.get("source_dir"):
                click.echo(f"Source dir: {manifest['source_dir']}")
            if manifest.get("host_partition"):
                click.echo(f"Host partition: {manifest['host_partition']}")
            if manifest.get("env"):
                click.echo(f"Env: {manifest['env']}")
            if manifest.get("script_sha256"):
                click.echo(f"Script sha256: {manifest['script_sha256']}")
            if manifest.get("sbatch"):
                click.echo("Sbatch:")
                for line in _format_mapping(manifest["sbatch"]):
                    click.echo(line)
            if manifest.get("fragments"):
                click.echo("Fragments:")
                for fragment in manifest["fragments"]:
                    click.echo(f"  {fragment}")
            if manifest.get("vars"):
                click.echo("Variables:")
                for line in _format_mapping(manifest["vars"]):
                    click.echo(line)
            return True

        except requests.exceptions.ConnectionError:
            click.echo(
                "Could not connect to API server. Use 'ssync api' to start it manually.",
                err=True,
            )
            return False
        except Exception as e:
            click.echo(f"Error getting run manifest: {e}", err=True)
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False


class RerenderCommand(BaseCommand):
    """Handles displaying frozen or live rerenders for recipe jobs."""

    def execute(
        self,
        job_id: str,
        host: Optional[str] = None,
        json_output: bool = False,
        from_current_repo: bool = False,
    ) -> bool:
        """Show the script represented by a stored manifest."""
        try:
            api_client = APIClient(verbose=self.verbose)

            success, error_msg = api_client.ensure_server_running(self.config_path)
            if not success:
                click.echo(f"Failed to start API server: {error_msg}", err=True)
                return False

            resolved_host = self._resolve_job_host(api_client, job_id, host)
            if not resolved_host:
                return False

            try:
                manifest = api_client.get_run_manifest(job_id, resolved_host)
            except requests.exceptions.HTTPError as exc:
                status_code = exc.response.status_code if exc.response else None
                if status_code == 404:
                    click.echo(
                        f"No run manifest found for job {job_id} on {resolved_host}",
                        err=True,
                    )
                    return False
                raise

            if from_current_repo:
                recipe_path = manifest.get("recipe_path")
                if not recipe_path:
                    click.echo(
                        f"Run manifest for job {job_id} does not record a recipe path",
                        err=True,
                    )
                    return False
                overrides = manifest.get("cli_overrides") or {}
                try:
                    rendered = render_launch_recipe(
                        recipe_path,
                        workflow=overrides.get("workflow"),
                        host_partition=overrides.get("host_partition"),
                        env=overrides.get("env"),
                        vars=overrides.get("vars"),
                        sbatch=overrides.get("sbatch"),
                        add_watchers=overrides.get("add_watchers"),
                        remove_watchers=overrides.get("remove_watchers"),
                        cli_overrides=overrides,
                    )
                except RecipeError as e:
                    click.echo(f"Error rerendering from current repo: {e}", err=True)
                    return False
                manifest = rendered.manifest

            if json_output:
                click.echo(json.dumps(manifest, indent=2, sort_keys=True))
                return True

            mode = "current repo" if from_current_repo else "frozen manifest"
            click.echo(f"Job: {job_id}")
            click.echo(f"Host: {resolved_host}")
            click.echo(f"Rerender mode: {mode}")
            if manifest.get("recipe_path"):
                click.echo(f"Recipe: {manifest['recipe_path']}")
            if manifest.get("script_sha256"):
                click.echo(f"Script sha256: {manifest['script_sha256']}")
            script = manifest.get("rendered_script")
            if not script:
                click.echo("Run manifest does not contain a rendered script", err=True)
                return False
            click.echo("Rendered script:")
            click.echo(script)
            return True

        except requests.exceptions.ConnectionError:
            click.echo(
                "Could not connect to API server. Use 'ssync api' to start it manually.",
                err=True,
            )
            return False
        except Exception as e:
            click.echo(f"Error rerendering run manifest: {e}", err=True)
            if self.verbose:
                import traceback

                traceback.print_exc()
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
                click.echo(f"Destination must be a directory: {destination}", err=True)
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
