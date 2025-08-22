"""Clean, modular CLI for ssync."""

from pathlib import Path

import click

from .cli.commands import StatusCommand, SubmitCommand, SyncCommand
from .config import ConfigError, get_default_config_path, load_config


@click.group()
@click.option(
    "--config", "-c", type=click.Path(path_type=Path), help="Configuration file path"
)
@click.option(
    "--no-ssh-config",
    is_flag=True,
    help="Disable SSH config file usage (use manual config only)",
)
@click.option("--verbose", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, config, no_ssh_config, verbose):
    """Sync files and manage SLURM jobs across multiple clusters."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["use_ssh_config"] = not no_ssh_config

    # Load configuration
    config_path = config or get_default_config_path()
    try:
        slurm_hosts = load_config(config_path)
        ctx.obj["slurm_hosts"] = slurm_hosts
        ctx.obj["config_path"] = config_path
    except ConfigError as e:
        click.echo(f"Configuration error: {e}", err=True)
        if not config_path.exists():
            click.echo(
                f"Create a config file at {config_path} or use --config", err=True
            )
        ctx.exit(1)


@cli.command(name="status")
@click.option("--host", help="Check specific host only")
@click.option("--user", help="Check jobs for specific user")
@click.option("--simple", is_flag=True, help="Show simple tabular output")
@click.option(
    "--since", help="Include completed jobs since time (e.g., 1h, 1d, 1w, 2025-08-20)"
)
@click.option("--limit", type=int, help="Limit number of jobs to show")
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
        config_path=ctx.obj["config_path"],
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
@click.argument("source_dir", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def sync_command(ctx, exclude, include, no_gitignore, host, source_dir):
    """Sync source directory to SLURM hosts."""
    command = SyncCommand(
        config_path=ctx.obj["config_path"],
        slurm_hosts=ctx.obj["slurm_hosts"],
        verbose=ctx.obj["verbose"],
    )

    success = command.execute(
        source_dir=source_dir,
        exclude=list(exclude),
        include=list(include),
        no_gitignore=no_gitignore,
        host=host,
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
        config_path=ctx.obj["config_path"],
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


def main():
    """Run the ssync CLI."""
    cli()


if __name__ == "__main__":
    main()
