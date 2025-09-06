"""Clean, modular CLI for ssync."""

from pathlib import Path

import click

from ..utils.config import ConfigError, config
from .auth import auth
from .commands import LaunchCommand, StatusCommand, SyncCommand
from .watchers import watchers


@click.group()
@click.option(
    "--no-ssh-config",
    is_flag=True,
    help="Disable SSH config file usage (use manual config only)",
)
@click.option("--verbose", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, no_ssh_config, verbose):
    """Sync files and manage SLURM jobs across multiple clusters."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["use_ssh_config"] = not no_ssh_config

    # Load configuration
    try:
        slurm_hosts = config.load_config()
        ctx.obj["slurm_hosts"] = slurm_hosts
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        ctx.exit(1)


@cli.command(name="status")
@click.option("--host", help="Check specific host only")
@click.option("--user", help="Check jobs for specific user")
@click.option("--simple", is_flag=True, help="Show simple tabular output")
@click.option(
    "--since",
    default="1d",
    help="Include completed jobs since time (e.g., 1h, 1d, 1w, 2025-08-20)",
)
@click.option("--limit", default=20, type=int, help="Limit number of jobs to show")
@click.option("--job-id", help="Show specific job ID(s), comma-separated")
@click.option("--state", help="Filter by job state (PD, R, CD, F, CA, TO)")
@click.option("--active-only", is_flag=True, help="Show only running/pending jobs")
@click.option("--completed-only", is_flag=True, help="Show only completed jobs")
@click.option(
    "--cat-output",
    type=click.Choice(["stdout", "stderr", "both"]),
    help="Print job output file(s)",
)
@click.pass_context
def status_command(
    ctx,
    host,
    user,
    simple,
    since,
    limit,
    job_id,
    state,
    active_only,
    completed_only,
    cat_output,
):
    """Check SLURM queue status across hosts."""
    command = StatusCommand(
        config_path=config.config_path,
        slurm_hosts=ctx.obj["slurm_hosts"],
        verbose=ctx.obj["verbose"],
    )

    success = command.execute(
        host=host,
        user=user,
        simple=simple,
        since=since,
        limit=limit,
        job_id=job_id,
        state=state,
        active_only=active_only,
        completed_only=completed_only,
        cat_output=cat_output,
    )

    if not success:
        ctx.exit(1)


@cli.command(name="sync")
@click.option(
    "--exclude", multiple=True, help="Additional patterns to exclude from sync"
)
@click.option(
    "--include", multiple=True, help="Patterns to include (overrides .gitignore)"
)
@click.option("--no-gitignore", is_flag=True, help="Disable .gitignore usage")
@click.option("--host", help="Sync to specific host only")
@click.option(
    "--max-depth",
    default=3,
    type=int,
    help="Maximum depth for recursive .gitignore search (default: 3)",
)
@click.argument("source_dir", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def sync_command(ctx, exclude, include, no_gitignore, host, max_depth, source_dir):
    """Sync source directory to SLURM hosts."""
    command = SyncCommand(
        config_path=config.config_path,
        slurm_hosts=ctx.obj["slurm_hosts"],
        verbose=ctx.obj["verbose"],
    )

    success = command.execute(
        source_dir=source_dir,
        exclude=list(exclude),
        include=list(include),
        no_gitignore=no_gitignore,
        host=host,
        max_depth=max_depth,
    )

    if not success:
        ctx.exit(1)


# Submit command removed - functionality is covered by launch command
# Users should use 'launch' which combines sync + submit


@cli.command(name="launch")
@click.option("--host", required=True, help="Target host for job submission")
@click.option("--job-name", help="SLURM job name")
@click.option("--cpus", type=int, help="Number of CPUs per task")
@click.option("--mem", type=int, help="Memory in GB")
@click.option("--time", type=int, help="Time limit in minutes")
@click.option("--partition", help="SLURM partition")
@click.option("--output", help="Output file path")
@click.option("--error", help="Error file path")
@click.option("--nodes", type=int, help="Number of nodes")
@click.option("--ntasks-per-node", type=int, help="Number of tasks per node")
@click.option("--gpus-per-node", type=int, help="Number of GPUs per node")
@click.option("--gres", help="Generic resources (e.g., 'gpu:2')")
@click.option("--constraint", help="Node constraints (e.g., gpu, bigmem)")
@click.option("--account", help="SLURM account for billing")
@click.option("--python-env", help="Python environment setup command")
@click.option(
    "--exclude", multiple=True, help="Additional patterns to exclude from sync"
)
@click.option(
    "--include", multiple=True, help="Patterns to include (overrides .gitignore)"
)
@click.option("--no-gitignore", is_flag=True, help="Disable .gitignore usage")
@click.option("--no-defaults", is_flag=True, help="Ignore per-host SLURM defaults")
@click.option(
    "--no-abort-on-setup-failure",
    is_flag=True,
    help="Continue job submission even if login setup fails",
)
@click.argument("script_path", type=click.Path(exists=True, path_type=Path))
@click.argument("source_dir", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def launch_command(
    ctx,
    host,
    job_name,
    cpus,
    mem,
    time,
    partition,
    output,
    error,
    nodes,
    ntasks_per_node,
    gpus_per_node,
    gres,
    constraint,
    account,
    python_env,
    exclude,
    include,
    no_gitignore,
    no_defaults,
    no_abort_on_setup_failure,
    script_path,
    source_dir,
):
    """Launch job by syncing source directory and submitting script.

    SCRIPT_PATH: Path to the script to submit (.sh or .slurm)
    SOURCE_DIR: Source directory to sync to remote host
    """
    command = LaunchCommand(
        config_path=config.config_path,
        slurm_hosts=ctx.obj["slurm_hosts"],
        verbose=ctx.obj["verbose"],
    )

    success = command.execute(
        script_path=script_path,
        source_dir=source_dir,
        host=host,
        job_name=job_name,
        cpus=cpus,
        mem=mem,
        time=time,
        partition=partition,
        nodes=nodes,
        ntasks_per_node=ntasks_per_node,
        gpus_per_node=gpus_per_node,
        gres=gres,
        output=output,
        error=error,
        constraint=constraint,
        account=account,
        python_env=python_env,
        exclude=list(exclude),
        include=list(include),
        no_gitignore=no_gitignore,
        no_defaults=no_defaults,
        abort_on_setup_failure=not no_abort_on_setup_failure,
    )

    if not success:
        ctx.exit(1)


cli.add_command(auth)
cli.add_command(watchers)


@cli.command(name="api")
@click.option("--port", default=8042, help="Port to run the API on")
@click.option("--host", default="127.0.0.1", help="Host to bind the API to")
@click.option("--no-https", is_flag=True, help="Disable HTTPS (use HTTP instead)")
@click.option("--stop", is_flag=True, help="Stop the running API server")
@click.option("--logs", is_flag=True, help="Show API server logs")
@click.pass_context
def api(ctx, port, host, no_https, stop, logs):
    """Start the API server only (no UI)."""
    from ..api.server import ServerManager
    from ..utils.config import config

    # Build base URL based on options
    protocol = "http" if no_https else "https"
    base_url = f"{protocol}://{host}:{port}"

    # Create server manager
    server = ServerManager(base_url)

    # Handle stop command
    if stop:
        if server.stop():
            click.echo("✓ API server stopped")
        else:
            click.echo("No running API server found")
        return

    # Handle logs command
    if logs:
        log_content = server.get_logs()
        if log_content:
            click.echo(log_content)
        else:
            click.echo("No logs available")
        return

    # Start the server
    click.echo(f"Starting API server on {base_url}...")
    if server.start(config.config_path):
        click.echo(f"✓ API server started on {base_url}")
        click.echo(f"  Logs: {server.log_file}")
        click.echo(f"  PID file: {server.pid_file}")
        click.echo("\nUse 'ssync api --stop' to stop the server")
    else:
        click.echo("✗ Failed to start API server", err=True)
        # Show recent logs if available
        log_content = server.get_logs(20)
        if log_content:
            click.echo("\nRecent logs:", err=True)
            click.echo(log_content, err=True)
        ctx.exit(1)


@cli.command(name="web")
@click.option("--port", default=8042, help="Port to run on")
@click.option("--host", default="127.0.0.1", help="Host to bind the server to")
@click.option("--stop", is_flag=True, help="Stop the running server")
@click.option("--status", is_flag=True, help="Check server status")
@click.option("--foreground", is_flag=True, help="Run in foreground (don't detach)")
@click.option("--no-browser", is_flag=True, help="Don't open browser")
@click.option("--skip-build", is_flag=True, help="Skip frontend build check")
@click.option("--no-https", is_flag=True, help="Disable HTTPS (use HTTP instead)")
@click.pass_context
def web(ctx, port, host, stop, status, foreground, no_browser, skip_build, no_https):
    """Launch the web interface (API + UI)."""
    # Call the web launcher directly
    # Create a mock context for the launcher since it expects click options
    import sys

    from ..web.launcher import main as web_launcher

    original_argv = sys.argv
    try:
        # Build command line args for the launcher
        args = []
        if port != 8042:
            args.extend(["--port", str(port)])
        if host != "127.0.0.1":
            args.extend(["--host", str(host)])
        if stop:
            args.append("--stop")
        if status:
            args.append("--status")
        if foreground:
            args.append("--foreground")
        if no_browser:
            args.append("--no-browser")
        if skip_build:
            args.append("--skip-build")
        if no_https:
            args.append("--no-https")

        # Temporarily replace argv
        sys.argv = ["ssync-web"] + args

        # Call the launcher
        web_launcher()
    finally:
        # Restore original argv
        sys.argv = original_argv


def main():
    """Run the ssync CLI."""
    cli()


if __name__ == "__main__":
    main()
