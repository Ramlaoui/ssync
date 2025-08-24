"""Clean, modular CLI for ssync."""

from pathlib import Path

import click

from ..utils.config import ConfigError, config
from .commands import LaunchCommand, StatusCommand, SubmitCommand, SyncCommand


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


@cli.command(name="submit")
@click.option("--host", help="Submit to specific host only")
@click.option("--job-name", help="SLURM job name")
@click.option("--cpus", type=int, help="Number of CPUs per task")
@click.option("--mem", type=int, help="Memory in GB")
@click.option("--time", type=int, help="Time limit in minutes")
@click.option("--partition", help="SLURM partition")
@click.option("--output", help="Output file path")
@click.option("--error", help="Error file path")
@click.option("--python-env", help="Python environment setup command")
@click.argument("script_or_function")
@click.argument("args", nargs=-1)
@click.pass_context
def submit_command(
    ctx,
    host,
    job_name,
    cpus,
    mem,
    time,
    partition,
    output,
    error,
    python_env,
    script_or_function,
    args,
):
    """Submit a job to SLURM hosts.

    SCRIPT_OR_FUNCTION can be:
    - A shell script path (e.g., my_script.sh)
    - A Python function in format module.py:function_name
    - A Python script (e.g., my_script.py)

    ARGS are passed to the script/function.
    """
    command = SubmitCommand(
        config_path=config.config_path,
        slurm_hosts=ctx.obj["slurm_hosts"],
        verbose=ctx.obj["verbose"],
    )

    success = command.execute(
        script_or_function=script_or_function,
        args=list(args),
        host=host,
        job_name=job_name,
        cpus=cpus,
        mem=mem,
        time=time,
        partition=partition,
        output=output,
        error=error,
        python_env=python_env,
    )

    if not success:
        ctx.exit(1)


@cli.command(name="launch")
@click.option("--host", required=True, help="Target host for job submission")
@click.option("--job-name", help="SLURM job name")
@click.option("--cpus", type=int, help="Number of CPUs per task")
@click.option("--mem", type=int, help="Memory in GB")
@click.option("--time", type=int, help="Time limit in minutes")
@click.option("--partition", help="SLURM partition")
@click.option("--output", help="Output file path")
@click.option("--error", help="Error file path")
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
    constraint,
    account,
    python_env,
    exclude,
    include,
    no_gitignore,
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
        output=output,
        error=error,
        constraint=constraint,
        account=account,
        python_env=python_env,
        exclude=list(exclude),
        include=list(include),
        no_gitignore=no_gitignore,
    )

    if not success:
        ctx.exit(1)


def main():
    """Run the ssync CLI."""
    cli()


if __name__ == "__main__":
    main()
