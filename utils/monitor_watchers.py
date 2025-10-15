#!/usr/bin/env python3
"""Real-time watcher monitoring with live updates."""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ssync.cache import get_cache
from src.ssync.utils.logging import setup_logger

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


def clear_screen():
    """Clear the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


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
            return f"{int(delta.total_seconds())}s"
        elif delta.total_seconds() < 3600:
            return f"{int(delta.total_seconds() / 60)}m"
        elif delta.total_seconds() < 86400:
            return f"{int(delta.total_seconds() / 3600)}h"
        else:
            return f"{int(delta.days)}d"
    except:
        return "-"


def get_live_data(job_id: Optional[str] = None) -> Dict[str, Any]:
    """Get current watcher data from database."""
    cache = get_cache()
    data = {"watchers": [], "recent_events": [], "stats": {}}

    with cache._get_connection() as conn:
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


def display_dashboard(data: Dict[str, Any], job_id: Optional[str] = None):
    """Display the monitoring dashboard."""
    clear_screen()

    # Header
    print(f"{BOLD}{CYAN}╔{'═' * 78}╗{RESET}")
    print(f"{BOLD}{CYAN}║{RESET} {BOLD}WATCHER MONITOR{RESET}".center(86))
    if job_id:
        print(f"{BOLD}{CYAN}║{RESET} Job: {job_id}".center(86))
    print(
        f"{BOLD}{CYAN}║{RESET} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(
            86
        )
    )
    print(f"{BOLD}{CYAN}╚{'═' * 78}╝{RESET}")

    # Statistics
    print(f"\n{BOLD}📊 Statistics:{RESET}")
    stats = data["stats"]
    state_counts = stats.get("state_counts", {})

    stat_line = []
    for state, count in state_counts.items():
        stat_line.append(f"{format_state(state)}: {count}")

    if stat_line:
        print("  " + " | ".join(stat_line))

    print(f"  Events (5 min): {YELLOW}{stats.get('events_5min', 0)}{RESET}")

    # Active Watchers
    print(f"\n{BOLD}👁️  Active Watchers:{RESET}")
    if data["watchers"]:
        print(
            f"  {GRAY}{'ID':>4} {'Job ID':<12} {'Name':<15} {'Pattern':<25} {'State':<10} {'Trigs':>5} {'Last':>8}{RESET}"
        )
        print(
            f"  {GRAY}{'-' * 4} {'-' * 12} {'-' * 15} {'-' * 25} {'-' * 10} {'-' * 5} {'-' * 8}{RESET}"
        )

        for w in data["watchers"][:10]:  # Show top 10
            print(
                f"  {w['id']:>4} {w['job_id']:<12} {w['name']:<15} {w['pattern']:<25} "
                f"{format_state(w['state']):<19} {w['triggers']:>5} {format_time_ago(w['last_check']):>8}"
            )
    else:
        print(f"  {GRAY}No active watchers{RESET}")

    # Recent Events
    print(f"\n{BOLD}⚡ Recent Events:{RESET}")
    if data["recent_events"]:
        print(
            f"  {GRAY}{'Time':>8} {'Job ID':<12} {'Watcher':<15} {'Action':<15} {'✓/✗':<3} {'Matched':<20}{RESET}"
        )
        print(
            f"  {GRAY}{'-' * 8} {'-' * 12} {'-' * 15} {'-' * 15} {'-' * 3} {'-' * 20}{RESET}"
        )

        for e in data["recent_events"]:
            print(
                f"  {format_time_ago(e['timestamp']):>8} {e['job_id']:<12} {e['watcher_name']:<15} "
                f"{e['action']:<15} {format_success(e['success']):<3} {e['matched'] or '-':<20}"
            )
    else:
        print(f"  {GRAY}No recent events{RESET}")

    # Footer
    print(f"\n{GRAY}{'─' * 80}{RESET}")
    print(f"{GRAY}Press Ctrl+C to exit | Updates every 2 seconds{RESET}")


def monitor_loop(job_id: Optional[str] = None, interval: int = 2):
    """Main monitoring loop."""
    try:
        while True:
            data = get_live_data(job_id)
            display_dashboard(data, job_id)
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n{BOLD}Monitor stopped.{RESET}")
    except Exception as e:
        print(f"\n{RED}Error: {e}{RESET}")
        import traceback

        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="Monitor watchers in real-time")
    parser.add_argument("--job-id", "-j", help="Filter by job ID")
    parser.add_argument(
        "--interval", "-i", type=int, default=2, help="Update interval in seconds"
    )
    parser.add_argument("--once", action="store_true", help="Show once and exit")

    args = parser.parse_args()

    # Suppress logging for cleaner display
    import logging

    logging.getLogger().setLevel(logging.ERROR)

    if args.once:
        data = get_live_data(args.job_id)
        display_dashboard(data, args.job_id)
    else:
        print(f"{BOLD}{GREEN}Starting watcher monitor...{RESET}")
        time.sleep(0.5)
        monitor_loop(args.job_id, args.interval)


if __name__ == "__main__":
    main()
