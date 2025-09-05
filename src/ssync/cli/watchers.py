"""CLI commands for managing and monitoring job watchers."""

import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import click

from ..cache import get_cache
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
    if success:
        return f"{GREEN}✓{RESET}"
    else:
        return f"{RED}✗{RESET}"


def format_time_ago(timestamp_str: str) -> str:
    """Format timestamp as 'X ago'."""
    if not timestamp_str:
        return "Never"

    try:
        timestamp = datetime.fromisoformat(timestamp_str)
        delta = datetime.now() - timestamp

        if delta.total_seconds() < 60:
            return f"{int(delta.total_seconds())}s ago"
        elif delta.total_seconds() < 3600:
            return f"{int(delta.total_seconds() / 60)}m ago"
        elif delta.total_seconds() < 86400:
            return f"{int(delta.total_seconds() / 3600)}h ago"
        else:
            return f"{int(delta.days)}d ago"
    except:
        return timestamp_str


def simple_table(rows, headers):
    """Simple table formatter without external dependencies."""
    if not rows:
        return ""

    # Calculate column widths
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    # Format header
    lines = []
    header_line = " | ".join(str(h).ljust(w) for h, w in zip(headers, widths))
    lines.append(header_line)
    lines.append("-" * len(header_line))

    # Format rows
    for row in rows:
        line = " | ".join(str(cell).ljust(w) for cell, w in zip(row, widths))
        lines.append(line)

    return "\n".join(lines)


class WatcherCommands:
    """Commands for managing job watchers."""

    def __init__(self):
        self.cache = get_cache()

    def get_active_watchers(
        self, job_id: Optional[str] = None, hostname: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get active watchers from database."""
        with self.cache._get_connection() as conn:
            query = """
                SELECT 
                    id, job_id, hostname, name, pattern, 
                    interval_seconds, state, trigger_count,
                    last_check, last_position, created_at
                FROM job_watchers
                WHERE 1=1
            """
            params = []

            if job_id:
                query += " AND job_id = ?"
                params.append(job_id)

            if hostname:
                query += " AND hostname = ?"
                params.append(hostname)

            query += " ORDER BY created_at DESC"

            cursor = conn.execute(query, params)
            watchers = []

            for row in cursor.fetchall():
                watcher = {
                    "id": row["id"],
                    "job_id": row["job_id"],
                    "hostname": row["hostname"],
                    "name": row["name"] or f"watcher_{row['id']}",
                    "pattern": row["pattern"][:50] + "..."
                    if len(row["pattern"]) > 50
                    else row["pattern"],
                    "interval": row["interval_seconds"],
                    "state": row["state"],
                    "triggers": row["trigger_count"],
                    "last_check": row["last_check"],
                    "last_pos": row["last_position"],
                    "created": row["created_at"],
                }
                watchers.append(watcher)

        return watchers

    def get_watcher_events(
        self,
        job_id: Optional[str] = None,
        watcher_id: Optional[int] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get recent watcher events."""
        with self.cache._get_connection() as conn:
            query = """
                SELECT 
                    e.id, e.watcher_id, e.job_id, e.hostname,
                    e.timestamp, e.matched_text, e.captured_vars_json,
                    e.action_type, e.action_result, e.success,
                    w.name as watcher_name, w.pattern
                FROM watcher_events e
                LEFT JOIN job_watchers w ON e.watcher_id = w.id
                WHERE 1=1
            """
            params = []

            if job_id:
                query += " AND e.job_id = ?"
                params.append(job_id)

            if watcher_id:
                query += " AND e.watcher_id = ?"
                params.append(watcher_id)

            query += f" ORDER BY e.timestamp DESC LIMIT {limit}"

            cursor = conn.execute(query, params)
            events = []

            for row in cursor.fetchall():
                event = {
                    "id": row["id"],
                    "watcher_id": row["watcher_id"],
                    "watcher_name": row["watcher_name"]
                    or f"watcher_{row['watcher_id']}",
                    "job_id": row["job_id"],
                    "hostname": row["hostname"],
                    "timestamp": row["timestamp"],
                    "matched": row["matched_text"][:50] + "..."
                    if row["matched_text"] and len(row["matched_text"]) > 50
                    else row["matched_text"],
                    "action": row["action_type"],
                    "success": "✓" if row["success"] else "✗",
                    "result": row["action_result"][:50] + "..."
                    if row["action_result"] and len(row["action_result"]) > 50
                    else row["action_result"],
                }

                # Add captured variables if any
                if row["captured_vars_json"]:
                    try:
                        vars_dict = json.loads(row["captured_vars_json"])
                        event["vars"] = ", ".join(
                            [f"{k}={v}" for k, v in vars_dict.items()]
                        )
                    except:
                        event["vars"] = ""
                else:
                    event["vars"] = ""

                events.append(event)

        return events

    def get_watcher_statistics(self) -> Dict[str, Any]:
        """Get overall watcher statistics."""
        with self.cache._get_connection() as conn:
            stats = {}

            # Total watchers
            cursor = conn.execute("SELECT COUNT(*) as count FROM job_watchers")
            stats["total_watchers"] = cursor.fetchone()["count"]

            # Watchers by state
            cursor = conn.execute("""
                SELECT state, COUNT(*) as count 
                FROM job_watchers 
                GROUP BY state
            """)
            stats["by_state"] = {
                row["state"]: row["count"] for row in cursor.fetchall()
            }

            # Total events
            cursor = conn.execute("SELECT COUNT(*) as count FROM watcher_events")
            stats["total_events"] = cursor.fetchone()["count"]

            # Events by action type
            cursor = conn.execute("""
                SELECT action_type, COUNT(*) as count, 
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count
                FROM watcher_events 
                GROUP BY action_type
            """)
            stats["by_action"] = {}
            for row in cursor.fetchall():
                stats["by_action"][row["action_type"]] = {
                    "total": row["count"],
                    "success": row["success_count"],
                    "failed": row["count"] - row["success_count"],
                }

            # Most active watchers
            cursor = conn.execute("""
                SELECT w.id, w.job_id, w.name, w.pattern, COUNT(e.id) as event_count
                FROM job_watchers w
                LEFT JOIN watcher_events e ON w.id = e.watcher_id
                GROUP BY w.id
                ORDER BY event_count DESC
                LIMIT 5
            """)
            stats["most_active"] = []
            for row in cursor.fetchall():
                stats["most_active"].append(
                    {
                        "id": row["id"],
                        "job_id": row["job_id"],
                        "name": row["name"] or f"watcher_{row['id']}",
                        "pattern": row["pattern"][:30] + "..."
                        if len(row["pattern"]) > 30
                        else row["pattern"],
                        "events": row["event_count"],
                    }
                )

            # Recent activity (last hour)
            one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count 
                FROM watcher_events 
                WHERE timestamp > ?
            """,
                (one_hour_ago,),
            )
            stats["events_last_hour"] = cursor.fetchone()["count"]

        return stats

    def get_live_data(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        """Get current watcher data for monitoring dashboard."""
        data = {"watchers": [], "recent_events": [], "stats": {}}

        with self.cache._get_connection() as conn:
            # Get active watchers
            query = """
                SELECT w.*, j.is_active as job_active
                FROM job_watchers w
                LEFT JOIN cached_jobs j ON w.job_id = j.job_id AND w.hostname = j.hostname
                WHERE 1=1
            """
            params = []

            if job_id:
                query += " AND w.job_id = ?"
                params.append(job_id)

            query += " ORDER BY w.created_at DESC LIMIT 20"

            cursor = conn.execute(query, params)

            for row in cursor.fetchall():
                watcher = {
                    "id": row["id"],
                    "job_id": row["job_id"],
                    "hostname": row["hostname"],
                    "name": row["name"] or f"W{row['id']}",
                    "pattern": row["pattern"][:40] + "..."
                    if len(row["pattern"]) > 40
                    else row["pattern"],
                    "state": row["state"],
                    "triggers": row["trigger_count"],
                    "last_check": row["last_check"],
                    "interval": row["interval_seconds"],
                    "job_active": "Active" if row["job_active"] else "Completed",
                }
                data["watchers"].append(watcher)

            # Get recent events (last 10)
            query = """
                SELECT e.*, w.name as watcher_name
                FROM watcher_events e
                LEFT JOIN job_watchers w ON e.watcher_id = w.id
                WHERE 1=1
            """
            params = []

            if job_id:
                query += " AND e.job_id = ?"
                params.append(job_id)

            query += " ORDER BY e.timestamp DESC LIMIT 10"

            cursor = conn.execute(query, params)

            for row in cursor.fetchall():
                event = {
                    "watcher_name": row["watcher_name"] or f"W{row['watcher_id']}",
                    "job_id": row["job_id"],
                    "action": row["action_type"],
                    "success": row["success"],
                    "timestamp": row["timestamp"],
                    "matched": row["matched_text"][:30] + "..."
                    if row["matched_text"] and len(row["matched_text"]) > 30
                    else row["matched_text"],
                }
                data["recent_events"].append(event)

            # Get statistics
            cursor = conn.execute(
                "SELECT COUNT(*) as count, state FROM job_watchers GROUP BY state"
            )
            state_counts = {row["state"]: row["count"] for row in cursor.fetchall()}

            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM watcher_events WHERE timestamp > ?",
                ((datetime.now() - timedelta(minutes=5)).isoformat(),),
            )
            events_5min = cursor.fetchone()["count"]

            data["stats"] = {
                "state_counts": state_counts,
                "events_5min": events_5min,
            }

        return data


@click.group()
def watchers():
    """Manage and monitor job watchers."""
    pass


@watchers.command(name="list")
@click.option("--job-id", "-j", help="Filter by job ID")
@click.option("--host", help="Filter by hostname")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def list_watchers(job_id, host, output_json):
    """List active watchers."""
    cmd = WatcherCommands()
    watchers = cmd.get_active_watchers(job_id, host)

    if output_json:
        click.echo(json.dumps(watchers, indent=2))
    else:
        if not watchers:
            click.echo("No watchers found")
        else:
            click.echo(f"\n{'=' * 100}")
            click.echo("ACTIVE WATCHERS")
            click.echo("=" * 100)

            headers = [
                "ID",
                "Job ID",
                "Host",
                "Name",
                "Pattern",
                "State",
                "Triggers",
                "Last Check",
                "Interval",
            ]
            rows = []

            for watcher in watchers:
                rows.append(
                    [
                        watcher["id"],
                        watcher["job_id"],
                        watcher["hostname"],
                        watcher["name"],
                        watcher["pattern"],
                        watcher["state"],
                        watcher["triggers"],
                        format_time_ago(watcher["last_check"]),
                        f"{watcher['interval']}s",
                    ]
                )

            click.echo(simple_table(rows, headers))

            click.echo(f"\nShowing {len(watchers)} watchers")
            click.echo("\nUse 'ssync watchers events' to see watcher events")
            click.echo("Use 'ssync watchers stats' to see statistics")


@watchers.command(name="events")
@click.option("--job-id", "-j", help="Filter by job ID")
@click.option("--watcher-id", "-w", type=int, help="Filter by watcher ID")
@click.option(
    "--limit", "-l", type=int, default=20, help="Limit number of events shown"
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def show_events(job_id, watcher_id, limit, output_json):
    """Show watcher events."""
    cmd = WatcherCommands()
    events = cmd.get_watcher_events(job_id, watcher_id, limit)

    if output_json:
        click.echo(json.dumps(events, indent=2))
    else:
        if not events:
            click.echo("No watcher events found")
        else:
            click.echo(f"\n{'=' * 100}")
            click.echo(f"WATCHER EVENTS (Last {limit})")
            click.echo("=" * 100)

            headers = [
                "Time",
                "Job ID",
                "Watcher",
                "Action",
                "Success",
                "Matched",
                "Variables",
            ]
            rows = []

            for event in events:
                rows.append(
                    [
                        format_time_ago(event["timestamp"]),
                        event["job_id"],
                        event["watcher_name"],
                        event["action"],
                        event["success"],
                        event["matched"],
                        event.get("vars", ""),
                    ]
                )

            click.echo(simple_table(rows, headers))


@watchers.command(name="stats")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def show_stats(output_json):
    """Show watcher statistics."""
    cmd = WatcherCommands()
    stats = cmd.get_watcher_statistics()

    if output_json:
        click.echo(json.dumps(stats, indent=2))
    else:
        click.echo("\n" + "=" * 60)
        click.echo("WATCHER STATISTICS")
        click.echo("=" * 60)

        click.echo(f"\nTotal Watchers: {stats['total_watchers']}")
        click.echo(f"Total Events: {stats['total_events']}")
        click.echo(f"Events in Last Hour: {stats['events_last_hour']}")

        if stats["by_state"]:
            click.echo("\nWatchers by State:")
            for state, count in stats["by_state"].items():
                click.echo(f"  {state}: {count}")

        if stats["by_action"]:
            click.echo("\nEvents by Action Type:")
            headers = ["Action", "Total", "Success", "Failed"]
            rows = []
            for action, counts in stats["by_action"].items():
                rows.append(
                    [action, counts["total"], counts["success"], counts["failed"]]
                )
            click.echo(simple_table(rows, headers))

        if stats["most_active"]:
            click.echo("\nMost Active Watchers:")
            headers = ["ID", "Job ID", "Name", "Pattern", "Events"]
            rows = []
            for w in stats["most_active"]:
                rows.append(
                    [w["id"], w["job_id"], w["name"], w["pattern"], w["events"]]
                )
            click.echo(simple_table(rows, headers))


@watchers.command(name="monitor")
@click.option("--job-id", "-j", help="Filter by job ID")
@click.option(
    "--interval", "-i", type=int, default=2, help="Update interval in seconds"
)
@click.option("--once", is_flag=True, help="Show once and exit")
def monitor_watchers(job_id, interval, once):
    """Real-time monitoring dashboard for watchers."""
    import logging
    import os

    # Suppress logging for cleaner display
    logging.getLogger().setLevel(logging.ERROR)

    cmd = WatcherCommands()

    def clear_screen():
        """Clear the terminal screen."""
        os.system("cls" if os.name == "nt" else "clear")

    def display_dashboard(data: Dict[str, Any], job_id: Optional[str] = None):
        """Display the monitoring dashboard."""
        clear_screen()

        # Header
        click.echo(f"{BOLD}{CYAN}╔{'═' * 78}╗{RESET}")
        click.echo(f"{BOLD}{CYAN}║{RESET} {BOLD}WATCHER MONITOR{RESET}".center(86))
        if job_id:
            click.echo(f"{BOLD}{CYAN}║{RESET} Job: {job_id}".center(86))
        click.echo(
            f"{BOLD}{CYAN}║{RESET} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(
                86
            )
        )
        click.echo(f"{BOLD}{CYAN}╚{'═' * 78}╝{RESET}")

        # Statistics
        click.echo(f"\n{BOLD}📊 Statistics:{RESET}")
        stats = data["stats"]
        state_counts = stats.get("state_counts", {})

        stat_line = []
        for state, count in state_counts.items():
            stat_line.append(f"{format_state(state)}: {count}")

        if stat_line:
            click.echo("  " + " | ".join(stat_line))

        click.echo(f"  Events (5 min): {YELLOW}{stats.get('events_5min', 0)}{RESET}")

        # Active Watchers
        click.echo(f"\n{BOLD}👁️  Active Watchers:{RESET}")
        if data["watchers"]:
            click.echo(
                f"  {GRAY}{'ID':>4} {'Job ID':<12} {'Name':<15} {'Pattern':<25} {'State':<10} {'Trigs':>5} {'Last':>8}{RESET}"
            )
            click.echo(
                f"  {GRAY}{'-' * 4} {'-' * 12} {'-' * 15} {'-' * 25} {'-' * 10} {'-' * 5} {'-' * 8}{RESET}"
            )

            for w in data["watchers"][:10]:  # Show top 10
                last_check = (
                    format_time_ago(w["last_check"]) if w["last_check"] else "Never"
                )
                last_check = last_check.replace(" ago", "")  # Shorten for display
                click.echo(
                    f"  {w['id']:>4} {w['job_id']:<12} {w['name']:<15} {w['pattern']:<25} "
                    f"{format_state(w['state']):<19} {w['triggers']:>5} {last_check:>8}"
                )
        else:
            click.echo(f"  {GRAY}No active watchers{RESET}")

        # Recent Events
        click.echo(f"\n{BOLD}⚡ Recent Events:{RESET}")
        if data["recent_events"]:
            click.echo(
                f"  {GRAY}{'Time':>8} {'Job ID':<12} {'Watcher':<15} {'Action':<15} {'✓/✗':<3} {'Matched':<20}{RESET}"
            )
            click.echo(
                f"  {GRAY}{'-' * 8} {'-' * 12} {'-' * 15} {'-' * 15} {'-' * 3} {'-' * 20}{RESET}"
            )

            for e in data["recent_events"]:
                time_str = format_time_ago(e["timestamp"]).replace(
                    " ago", ""
                )  # Shorten for display
                click.echo(
                    f"  {time_str:>8} {e['job_id']:<12} {e['watcher_name']:<15} "
                    f"{e['action']:<15} {format_success(e['success']):<3} {e['matched'] or '-':<20}"
                )
        else:
            click.echo(f"  {GRAY}No recent events{RESET}")

        # Footer
        click.echo(f"\n{GRAY}{'─' * 80}{RESET}")
        click.echo(
            f"{GRAY}Press Ctrl+C to exit | Updates every {interval} seconds{RESET}"
        )

    try:
        if once:
            data = cmd.get_live_data(job_id)
            display_dashboard(data, job_id)
        else:
            click.echo(f"{BOLD}{GREEN}Starting watcher monitor...{RESET}")
            time.sleep(0.5)
            while True:
                data = cmd.get_live_data(job_id)
                display_dashboard(data, job_id)
                time.sleep(interval)
    except KeyboardInterrupt:
        click.echo(f"\n{BOLD}Monitor stopped.{RESET}")
    except Exception as e:
        click.echo(f"\n{RED}Error: {e}{RESET}")
        import traceback

        traceback.print_exc()
