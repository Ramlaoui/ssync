#!/usr/bin/env python3
import os
import sqlite3
import time
from datetime import datetime


def monitor_watcher_activity(job_id):
    """Monitor watcher database for timer mode activity."""

    db_path = os.path.expanduser("~/.config/ssync/cache.db")

    print(f"Monitoring watcher activity for job {job_id}")
    print("-" * 50)

    last_trigger_count = 0
    last_timer_mode = False

    for _ in range(30):  # Monitor for 5 minutes
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get watcher status
            cursor.execute(
                """
                SELECT id, name, state, trigger_count, timer_mode_active, 
                       timer_mode_enabled, last_check
                FROM job_watchers 
                WHERE job_id = ?
            """,
                (job_id,),
            )

            watcher = cursor.fetchone()

            if watcher:
                timer_mode_changed = watcher["timer_mode_active"] != last_timer_mode
                trigger_increased = watcher["trigger_count"] > last_trigger_count

                if timer_mode_changed or trigger_increased:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Watcher Update:")
                    print(
                        f"  - Timer Mode Active: {bool(watcher['timer_mode_active'])}"
                    )
                    print(f"  - Trigger Count: {watcher['trigger_count']}")
                    print(f"  - State: {watcher['state']}")
                    print(f"  - Last Check: {watcher['last_check']}")

                    # Check for events
                    cursor.execute(
                        """
                        SELECT timestamp, action_type, action_result
                        FROM watcher_events
                        WHERE watcher_id = ?
                        ORDER BY timestamp DESC
                        LIMIT 5
                    """,
                        (watcher["id"],),
                    )

                    events = cursor.fetchall()
                    if events:
                        print("  Recent Events:")
                        for event in events:
                            print(
                                f"    [{event['timestamp']}] {event['action_type']}: {event['action_result'][:50]}"
                            )

                last_trigger_count = watcher["trigger_count"]
                last_timer_mode = watcher["timer_mode_active"]

            conn.close()

        except Exception as e:
            print(f"Error accessing database: {e}")

        time.sleep(10)

    print("\nMonitoring completed")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        monitor_watcher_activity(sys.argv[1])
    else:
        print("Usage: python monitor_watcher.py <job_id>")
