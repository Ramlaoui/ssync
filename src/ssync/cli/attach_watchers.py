"""CLI command to attach watchers to existing jobs."""

import json
import sys
from typing import Optional

import click

from ..models.watcher import ActionType
from ..utils.logging import setup_logger

logger = setup_logger(__name__)


@click.command(name="attach-watchers")
@click.argument("job_id")
@click.option(
    "--host",
    required=True,
    help="Hostname where job is running",
)
@click.option(
    "--watcher-file",
    type=click.Path(exists=True),
    help="JSON file with watcher definitions",
)
@click.option(
    "--pattern",
    help="Simple pattern to watch for (alternative to watcher-file)",
)
@click.option(
    "--action",
    type=click.Choice([a.value for a in ActionType]),
    default="LOG_EVENT",
    help="Action to take when pattern matches",
)
@click.option(
    "--output-type",
    type=click.Choice(["stdout", "stderr", "both"]),
    default="stdout",
    help="Which output stream to monitor",
)
@click.option(
    "--interval",
    type=int,
    default=30,
    help="Check interval in seconds",
)
@click.pass_context
def attach_watchers(
    ctx,
    job_id: str,
    host: str,
    watcher_file: Optional[str],
    pattern: Optional[str],
    action: str,
    output_type: str,
    interval: int,
):
    """Attach watchers to an existing SLURM job.
    
    Examples:
        # Simple pattern watcher
        ssync attach-watchers 12345 --host cluster1 --pattern "ERROR" --action CANCEL_JOB
        
        # Complex watchers from file
        ssync attach-watchers 12345 --host cluster1 --watcher-file watchers.json
        
        # Monitor Python metrics
        ssync attach-watchers 12345 --host cluster1 \\
            --pattern "Loss: ([\\d.]+)" --action RUN_COMMAND
    """
    try:
        from ..utils.config import config

        # Load config
        config.load_config()

        # Build watcher definitions
        if watcher_file:
            # Load from file
            with open(watcher_file, "r") as f:
                watchers = json.load(f)
        elif pattern:
            # Build simple watcher
            watchers = [
                {
                    "name": f"cli_watcher_{job_id}",
                    "pattern": pattern,
                    "output_type": output_type,
                    "interval_seconds": interval,
                    "actions": [{"type": action, "params": {}}],
                }
            ]
        else:
            click.echo(
                "Error: Must provide either --watcher-file or --pattern", err=True
            )
            sys.exit(1)

        # Call API to attach watchers
        from pathlib import Path

        import requests

        # Check for API key
        api_key_file = Path.home() / ".config" / "ssync" / ".api_key"
        api_key = None
        if api_key_file.exists():
            try:
                content = api_key_file.read_text().strip()
                # Check if it's JSON (contains API key data)
                if content.startswith("{"):
                    data = json.loads(content)
                    # Get the first key (the actual API key string)
                    if data:
                        api_key = list(data.keys())[0]
                else:
                    # Simple key file - just the key itself
                    api_key = content
            except Exception:
                pass

        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        # Check for API server configuration
        import os

        api_host = os.getenv("SSYNC_API_HOST", "localhost")
        api_port = os.getenv("SSYNC_API_PORT", "8042")
        use_https = os.getenv("SSYNC_USE_HTTPS", "true").lower() == "true"

        # Construct API URL
        protocol = "https" if use_https else "http"
        api_url = (
            f"{protocol}://{api_host}:{api_port}/api/jobs/{job_id}/watchers?host={host}"
        )

        # Debug output (always show for now to help debug)
        click.echo(f"Attaching watcher to job {job_id} on {host}")
        click.echo(f"API URL: {api_url}")
        if ctx.obj.get("verbose"):
            click.echo(f"Watchers: {json.dumps(watchers, indent=2)}")

        try:
            # For HTTPS with self-signed certs, disable SSL verification
            verify_ssl = (
                not use_https
                or os.getenv("SSYNC_VERIFY_SSL", "false").lower() == "true"
            )

            # Suppress SSL warnings for self-signed certs
            if not verify_ssl:
                import urllib3

                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            response = requests.post(
                api_url, json=watchers, headers=headers, timeout=30, verify=verify_ssl
            )

            if response.status_code == 200:
                result = response.json()
                click.echo(f"✅ {result['message']}")
                if "watcher_ids" in result:
                    click.echo(
                        f"Watcher IDs: {', '.join(map(str, result['watcher_ids']))}"
                    )
            else:
                error_msg = response.text
                try:
                    error_data = response.json()
                    if "detail" in error_data:
                        error_msg = error_data["detail"]
                except:
                    pass
                click.echo(f"❌ Failed to attach watchers: {error_msg}", err=True)
                sys.exit(1)
        except requests.exceptions.ConnectionError:
            click.echo(
                "❌ Error: Could not connect to API server. Is 'ssync web' running?",
                err=True,
            )
            click.echo("Start the API server with: ssync web", err=True)
            sys.exit(1)
        except requests.exceptions.Timeout:
            click.echo("❌ Error: Request timed out", err=True)
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            click.echo(f"❌ Error: {e}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    attach_watchers()
