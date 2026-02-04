"""CLI commands for managing and monitoring job watchers."""

import json
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional

import click
import requests

from ..api.client import APIClient
from ..utils.logging import setup_logger

logger = setup_logger(__name__)

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
GRAY = "\033[90m"


def format_state(state: str) -> str:
    """Format state with color."""
    colors = {
        "active": GREEN,
        "paused": YELLOW,
        "triggered": CYAN,
        "disabled": RED,
        "completed": GRAY,
    }
    color = colors.get(state, RESET)
    return f"{color}{state}{RESET}"


def format_success(success: bool) -> str:
    """Format success/failure with color."""
    return f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"


def format_time_ago(timestamp_str: str) -> str:
    """Format timestamp as 'X ago'."""
    if not timestamp_str:
        return "Never"

    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        now = datetime.now(timestamp.tzinfo) if timestamp.tzinfo else datetime.now()
        delta = now - timestamp

        if delta.total_seconds() < 60:
            return f"{int(delta.total_seconds())}s ago"
        elif delta.total_seconds() < 3600:
            return f"{int(delta.total_seconds() / 60)}m ago"
        elif delta.total_seconds() < 86400:
            return f"{int(delta.total_seconds() / 3600)}h ago"
        else:
            return f"{int(delta.days)}d ago"
    except Exception:
        return timestamp_str


def simple_table(rows, headers):
    """Simple table formatter."""
    if not rows:
        return ""

    # Calculate column widths (strip ANSI codes for width calculation)
    import re

    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    def visible_len(s):
        return len(ansi_escape.sub("", str(s)))

    widths = [visible_len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], visible_len(cell))

    # Format header
    lines = []
    header_line = " | ".join(str(h).ljust(w) for h, w in zip(headers, widths))
    lines.append(header_line)
    lines.append("-" * len(header_line))

    # Format rows (need to account for ANSI codes in padding)
    for row in rows:
        parts = []
        for cell, w in zip(row, widths):
            cell_str = str(cell)
            padding = w - visible_len(cell_str)
            parts.append(cell_str + " " * padding)
        lines.append(" | ".join(parts))

    return "\n".join(lines)


def get_client() -> APIClient:
    """Get an API client instance."""
    return APIClient()


def handle_api_error(e: Exception) -> None:
    """Handle API errors with user-friendly messages."""
    if isinstance(e, requests.exceptions.ConnectionError):
        click.echo(f"{RED}Error: Cannot connect to API server. Is it running?{RESET}")
        click.echo(f"{GRAY}Start with: ssync api{RESET}")
    elif isinstance(e, requests.exceptions.HTTPError):
        click.echo(f"{RED}Error: {e.response.status_code} - {e.response.text}{RESET}")
    else:
        click.echo(f"{RED}Error: {e}{RESET}")


@click.group()
def watchers():
    """Manage and monitor job watchers."""
    pass


@watchers.command(name="list")
@click.option("--job-id", "-j", help="Filter by job ID")
@click.option("--host", help="Filter by hostname")
@click.option("--state", help="Filter by state (active, paused, completed)")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def list_watchers(job_id, host, state, output_json):
    """List watchers."""
    try:
        client = get_client()
        params = {}
        if job_id:
            params["job_id"] = job_id
        if host:
            params["host"] = host
        if state:
            params["state"] = state

        data = client.get("/api/watchers", params=params)
        watchers_list = data.get("watchers", [])

        if output_json:
            click.echo(json.dumps(watchers_list, indent=2))
        elif not watchers_list:
            click.echo("No watchers found")
        else:
            click.echo(f"\n{BOLD}WATCHERS{RESET} ({len(watchers_list)} total)\n")

            headers = [
                "ID",
                "Job ID",
                "Name",
                "Pattern",
                "State",
                "Triggers",
                "Last Check",
            ]
            rows = []

            for w in watchers_list:
                pattern = w.get("pattern", "")
                if len(pattern) > 30:
                    pattern = pattern[:27] + "..."

                rows.append(
                    [
                        str(w.get("id", "")),
                        w.get("job_id", ""),
                        w.get("name", "")[:15],
                        pattern,
                        format_state(w.get("state", "")),
                        str(w.get("trigger_count", 0)),
                        format_time_ago(w.get("last_check", "")),
                    ]
                )

            click.echo(simple_table(rows, headers))

    except Exception as e:
        handle_api_error(e)


@watchers.command(name="events")
@click.option("--job-id", "-j", help="Filter by job ID")
@click.option("--watcher-id", "-w", type=int, help="Filter by watcher ID")
@click.option("--limit", "-l", type=int, default=20, help="Limit number of events")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def show_events(job_id, watcher_id, limit, output_json):
    """Show watcher events."""
    try:
        client = get_client()
        params = {"limit": limit}
        if job_id:
            params["job_id"] = job_id
        if watcher_id:
            params["watcher_id"] = watcher_id

        data = client.get("/api/watchers/events", params=params)
        events = data.get("events", [])

        if output_json:
            click.echo(json.dumps(events, indent=2))
        elif not events:
            click.echo("No events found")
        else:
            click.echo(f"\n{BOLD}WATCHER EVENTS{RESET} (last {limit})\n")

            headers = ["Time", "Job ID", "Watcher", "Action", "OK", "Matched"]
            rows = []

            for e in events:
                matched = e.get("matched_text", "") or ""
                if len(matched) > 25:
                    matched = matched[:22] + "..."

                rows.append(
                    [
                        format_time_ago(e.get("timestamp", "")),
                        e.get("job_id", ""),
                        e.get("watcher_name", "")[:12],
                        e.get("action_type", "")[:12],
                        format_success(e.get("success", False)),
                        matched,
                    ]
                )

            click.echo(simple_table(rows, headers))

    except Exception as e:
        handle_api_error(e)


@watchers.command(name="stats")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def show_stats(output_json):
    """Show watcher statistics."""
    try:
        client = get_client()
        stats = client.get("/api/watchers/stats")

        if output_json:
            click.echo(json.dumps(stats, indent=2))
        else:
            click.echo(f"\n{BOLD}WATCHER STATISTICS{RESET}\n")

            click.echo(f"Total Watchers: {stats.get('total_watchers', 0)}")
            click.echo(f"Total Events: {stats.get('total_events', 0)}")
            click.echo(f"Events (last hour): {stats.get('events_last_hour', 0)}")

            by_state = stats.get("by_state", {})
            if by_state:
                click.echo(f"\n{BOLD}By State:{RESET}")
                for state, count in by_state.items():
                    click.echo(f"  {format_state(state)}: {count}")

            by_action = stats.get("by_action", {})
            if by_action:
                click.echo(f"\n{BOLD}By Action:{RESET}")
                for action, counts in by_action.items():
                    total = counts.get("total", 0)
                    success = counts.get("success", 0)
                    click.echo(f"  {action}: {total} ({GREEN}{success} ok{RESET})")

    except Exception as e:
        handle_api_error(e)


@watchers.command(name="pause")
@click.argument("watcher_id", type=int)
def pause_watcher(watcher_id):
    """Pause a watcher."""
    try:
        client = get_client()
        client.post(f"/api/watchers/{watcher_id}/pause")
        click.echo(f"{GREEN}✓{RESET} Watcher {watcher_id} paused")
    except Exception as e:
        handle_api_error(e)


@watchers.command(name="resume")
@click.argument("watcher_id", type=int)
def resume_watcher(watcher_id):
    """Resume a paused watcher."""
    try:
        client = get_client()
        client.post(f"/api/watchers/{watcher_id}/resume")
        click.echo(f"{GREEN}✓{RESET} Watcher {watcher_id} resumed")
    except Exception as e:
        handle_api_error(e)


@watchers.command(name="trigger")
@click.argument("watcher_id", type=int)
def trigger_watcher(watcher_id):
    """Manually trigger a watcher."""
    try:
        client = get_client()
        result = client.post(f"/api/watchers/{watcher_id}/trigger")
        click.echo(f"{GREEN}✓{RESET} Watcher {watcher_id} triggered")
        if result.get("message"):
            click.echo(f"  {result['message']}")
    except Exception as e:
        handle_api_error(e)


@watchers.command(name="monitor")
@click.option("--job-id", "-j", help="Filter by job ID")
@click.option("--interval", "-i", type=int, default=2, help="Update interval (seconds)")
@click.option("--once", is_flag=True, help="Show once and exit")
def monitor_watchers(job_id, interval, once):
    """Real-time monitoring dashboard."""
    import os

    client = get_client()

    def clear_screen():
        os.system("cls" if os.name == "nt" else "clear")

    def display_dashboard(data: Dict[str, Any]):
        clear_screen()

        # Header
        click.echo(f"{BOLD}{CYAN}{'═' * 70}{RESET}")
        click.echo(
            f"{BOLD}  WATCHER MONITOR{RESET}  {datetime.now().strftime('%H:%M:%S')}"
        )
        if job_id:
            click.echo(f"  Job: {job_id}")
        click.echo(f"{BOLD}{CYAN}{'═' * 70}{RESET}")

        # Stats
        stats = data.get("stats", {})
        by_state = stats.get("by_state", {})
        state_parts = [f"{format_state(s)}: {c}" for s, c in by_state.items()]
        if state_parts:
            click.echo(f"\n{BOLD}Stats:{RESET} " + " | ".join(state_parts))

        # Watchers
        watchers_list = data.get("watchers", [])
        click.echo(f"\n{BOLD}Watchers:{RESET}")
        if watchers_list:
            for w in watchers_list[:10]:
                last = format_time_ago(w.get("last_check", "")).replace(" ago", "")
                click.echo(
                    f"  {w.get('id', ''):>3} {w.get('job_id', ''):<12} "
                    f"{format_state(w.get('state', '')):<18} "
                    f"triggers={w.get('trigger_count', 0):<3} last={last}"
                )
        else:
            click.echo(f"  {GRAY}No watchers{RESET}")

        # Events
        events = data.get("recent_events", [])
        click.echo(f"\n{BOLD}Recent Events:{RESET}")
        if events:
            for e in events[:5]:
                time_str = format_time_ago(e.get("timestamp", "")).replace(" ago", "")
                click.echo(
                    f"  {time_str:>6} {e.get('job_id', ''):<12} "
                    f"{e.get('action_type', ''):<12} {format_success(e.get('success', False))}"
                )
        else:
            click.echo(f"  {GRAY}No recent events{RESET}")

        click.echo(f"\n{GRAY}Press Ctrl+C to exit{RESET}")

    try:
        params = {}
        if job_id:
            params["job_id"] = job_id

        if once:
            # Get combined data
            watchers_data = client.get("/api/watchers", params=params)
            events_data = client.get(
                "/api/watchers/events", params={**params, "limit": 10}
            )
            stats_data = client.get("/api/watchers/stats")

            data = {
                "watchers": watchers_data.get("watchers", []),
                "recent_events": events_data.get("events", []),
                "stats": stats_data,
            }
            display_dashboard(data)
        else:
            while True:
                watchers_data = client.get("/api/watchers", params=params)
                events_data = client.get(
                    "/api/watchers/events", params={**params, "limit": 10}
                )
                stats_data = client.get("/api/watchers/stats")

                data = {
                    "watchers": watchers_data.get("watchers", []),
                    "recent_events": events_data.get("events", []),
                    "stats": stats_data,
                }
                display_dashboard(data)
                time.sleep(interval)

    except KeyboardInterrupt:
        click.echo(f"\n{BOLD}Monitor stopped.{RESET}")
    except Exception as e:
        handle_api_error(e)


@watchers.command(name="attach")
@click.argument("job_id")
@click.option("--host", required=True, help="Hostname where job is running")
@click.option(
    "--watcher-file",
    type=click.Path(exists=True),
    help="JSON file with watcher definitions",
)
@click.option(
    "--pattern", help="Simple pattern to watch for (alternative to watcher-file)"
)
@click.option(
    "--action",
    type=click.Choice(
        [
            "cancel_job",
            "resubmit",
            "notify_email",
            "notify_slack",
            "run_command",
            "store_metric",
            "pause_watcher",
            "log_event",
        ]
    ),
    default="log_event",
    help="Action to take when pattern matches",
)
@click.option(
    "--output-type",
    type=click.Choice(["stdout", "stderr", "both"]),
    default="stdout",
    help="Which output stream to monitor",
)
@click.option("--interval", type=int, default=30, help="Check interval in seconds")
def attach_watcher(
    job_id: str,
    host: str,
    watcher_file: Optional[str],
    pattern: Optional[str],
    action: str,
    output_type: str,
    interval: int,
):
    """Attach watchers to an existing Slurm job.

    Examples:
        # Simple pattern watcher
        ssync watchers attach 12345 --host cluster1 --pattern "ERROR" --action cancel_job

        # Complex watchers from file
        ssync watchers attach 12345 --host cluster1 --watcher-file watchers.json

        # Monitor metrics
        ssync watchers attach 12345 --host cluster1 --pattern "Loss: ([\\d.]+)" --action store_metric
    """
    try:
        # Build watcher definitions
        if watcher_file:
            with open(watcher_file, "r") as f:
                watchers_data = json.load(f)
        elif pattern:
            watchers_data = [
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
                f"{RED}Error: Must provide either --watcher-file or --pattern{RESET}",
                err=True,
            )
            sys.exit(1)

        client = get_client()
        result = client.post(
            f"/api/jobs/{job_id}/watchers",
            data=watchers_data,
            params={"host": host},
        )

        click.echo(f"{GREEN}✓{RESET} {result.get('message', 'Watchers attached')}")
        if "watcher_ids" in result:
            click.echo(f"Watcher IDs: {', '.join(map(str, result['watcher_ids']))}")

    except Exception as e:
        handle_api_error(e)
        sys.exit(1)


@watchers.command(name="cleanup")
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
    try:
        client = get_client()

        if dry_run:
            # List active watchers
            data = client.get("/api/watchers", params={"state": "active"})
            watchers_list = data.get("watchers", [])

            if watchers_list:
                click.echo(f"Found {len(watchers_list)} active watchers:")
                for w in watchers_list:
                    click.echo(
                        f"  - Watcher {w.get('id')}: Job {w.get('job_id')} on {w.get('hostname', 'unknown')}"
                    )
            else:
                click.echo("No active watchers found")
        else:
            click.echo("Cleaning up orphaned watchers...")
            result = client.post("/api/watchers/cleanup")
            cleaned = result.get("cleaned_count", 0)
            click.echo(f"{GREEN}✓{RESET} Cleanup complete ({cleaned} watchers cleaned)")

    except Exception as e:
        handle_api_error(e)
