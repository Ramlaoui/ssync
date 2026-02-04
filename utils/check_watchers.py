#!/usr/bin/env python3
"""Check the status of watchers for Slurm jobs."""

import argparse
import json

# Add project to path
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from src.ssync.cache import get_cache
from src.ssync.utils.logging import setup_logger

logger = setup_logger(__name__)


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


def get_active_watchers(
    job_id: Optional[str] = None, hostname: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get active watchers from database."""
    cache = get_cache()

    with cache._get_connection() as conn:
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
    job_id: Optional[str] = None, watcher_id: Optional[int] = None, limit: int = 20
) -> List[Dict[str, Any]]:
    """Get recent watcher events."""
    cache = get_cache()

    with cache._get_connection() as conn:
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
                "watcher_name": row["watcher_name"] or f"watcher_{row['watcher_id']}",
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


def get_watcher_statistics() -> Dict[str, Any]:
    """Get overall watcher statistics."""
    cache = get_cache()

    with cache._get_connection() as conn:
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
        stats["by_state"] = {row["state"]: row["count"] for row in cursor.fetchall()}

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


def main():
    parser = argparse.ArgumentParser(description="Check watcher status")
    parser.add_argument("--job-id", "-j", help="Filter by job ID")
    parser.add_argument("--host", help="Filter by hostname")
    parser.add_argument("--watcher-id", "-w", type=int, help="Filter by watcher ID")
    parser.add_argument(
        "--events", "-e", action="store_true", help="Show watcher events"
    )
    parser.add_argument("--stats", "-s", action="store_true", help="Show statistics")
    parser.add_argument(
        "--limit", "-l", type=int, default=20, help="Limit number of events shown"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.stats:
        # Show statistics
        stats = get_watcher_statistics()

        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print("\n" + "=" * 60)
            print("WATCHER STATISTICS")
            print("=" * 60)

            print(f"\nTotal Watchers: {stats['total_watchers']}")
            print(f"Total Events: {stats['total_events']}")
            print(f"Events in Last Hour: {stats['events_last_hour']}")

            if stats["by_state"]:
                print("\nWatchers by State:")
                for state, count in stats["by_state"].items():
                    print(f"  {state}: {count}")

            if stats["by_action"]:
                print("\nEvents by Action Type:")
                headers = ["Action", "Total", "Success", "Failed"]
                rows = []
                for action, counts in stats["by_action"].items():
                    rows.append(
                        [action, counts["total"], counts["success"], counts["failed"]]
                    )
                print(simple_table(rows, headers))

            if stats["most_active"]:
                print("\nMost Active Watchers:")
                headers = ["ID", "Job ID", "Name", "Pattern", "Events"]
                rows = []
                for w in stats["most_active"]:
                    rows.append(
                        [w["id"], w["job_id"], w["name"], w["pattern"], w["events"]]
                    )
                print(simple_table(rows, headers))

    elif args.events:
        # Show events
        events = get_watcher_events(args.job_id, args.watcher_id, args.limit)

        if args.json:
            print(json.dumps(events, indent=2))
        else:
            if not events:
                print("No watcher events found")
            else:
                print(f"\n{'=' * 100}")
                print(f"WATCHER EVENTS (Last {args.limit})")
                print("=" * 100)

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

                print(simple_table(rows, headers))

    else:
        # Show watchers
        watchers = get_active_watchers(args.job_id, args.host)

        if args.json:
            print(json.dumps(watchers, indent=2))
        else:
            if not watchers:
                print("No watchers found")
            else:
                print(f"\n{'=' * 100}")
                print("ACTIVE WATCHERS")
                print("=" * 100)

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

                print(simple_table(rows, headers))

                print(f"\nShowing {len(watchers)} watchers")
                print("\nUse --events to see watcher events")
                print("Use --stats to see statistics")


if __name__ == "__main__":
    main()
