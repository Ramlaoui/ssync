"""CLI command to clean up orphaned watchers."""

import asyncio

import click

from ..utils.logging import setup_logger
from ..watchers import get_watcher_engine

logger = setup_logger(__name__)


@click.command(name="cleanup-watchers")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be cleaned up without making changes",
)
def cleanup_watchers(dry_run: bool):
    """Clean up watchers for completed or non-existent jobs.

    This command will:
    - Stop watchers for jobs that have completed
    - Stop watchers for jobs that no longer exist
    - Clean up any orphaned watcher tasks
    """

    async def run_cleanup():
        try:
            engine = get_watcher_engine()

            if dry_run:
                # Just list active watchers
                from ..cache import get_cache

                cache = get_cache()

                with cache._get_connection() as conn:
                    cursor = conn.execute(
                        """SELECT id, job_id, hostname, state 
                           FROM job_watchers 
                           WHERE state = 'active'"""
                    )
                    active_watchers = cursor.fetchall()

                if active_watchers:
                    click.echo(f"Found {len(active_watchers)} active watchers:")
                    for watcher in active_watchers:
                        click.echo(
                            f"  - Watcher {watcher[0]}: Job {watcher[1]} on {watcher[2]}"
                        )
                else:
                    click.echo("No active watchers found")
            else:
                click.echo("Cleaning up orphaned watchers...")
                await engine.cleanup_orphaned_watchers()
                click.echo("✅ Cleanup complete")

        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            raise

    # Run the async function
    asyncio.run(run_cleanup())


if __name__ == "__main__":
    cleanup_watchers()
