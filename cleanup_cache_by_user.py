#!/usr/bin/env python3
"""
Clean up cache entries from other users, keeping only your own jobs.
"""
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

def cleanup_cache_by_user(keep_users: list[str], backup: bool = True):
    """
    Remove all cached jobs from users not in the keep_users list.

    Args:
        keep_users: List of usernames to keep
        backup: Whether to create a backup before cleanup
    """
    cache_path = Path.home() / ".cache" / "ssync" / "jobs.db"

    if not cache_path.exists():
        print(f"Cache not found at: {cache_path}")
        return

    # Create backup
    if backup:
        backup_path = cache_path.parent / f"jobs.db.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"Creating backup at: {backup_path}")
        shutil.copy2(cache_path, backup_path)
        print(f"Backup created: {backup_path.stat().st_size / (1024*1024):.2f} MB\n")

    # Connect and cleanup
    conn = sqlite3.connect(str(cache_path))
    conn.row_factory = sqlite3.Row

    # Get counts before cleanup
    cursor = conn.execute("SELECT COUNT(*) FROM cached_jobs")
    total_before = cursor.fetchone()[0]

    cursor = conn.execute(f"""
        SELECT COUNT(*) FROM cached_jobs
        WHERE json_extract(job_info_json, '$.user') IN ({','.join('?' * len(keep_users))})
    """, keep_users)
    keep_count = cursor.fetchone()[0]

    delete_count = total_before - keep_count

    print(f"Cache Statistics:")
    print(f"  Total jobs: {total_before}")
    print(f"  Jobs to keep ({', '.join(keep_users)}): {keep_count}")
    print(f"  Jobs to delete: {delete_count}")
    print(f"\nProceeding with cleanup...\n")

    # Build WHERE clause for deletion
    placeholders = ','.join('?' * len(keep_users))

    # Delete from dependent tables first

    # 1. Delete watcher events for jobs we're removing
    cursor = conn.execute(f"""
        DELETE FROM watcher_events
        WHERE watcher_id IN (
            SELECT id FROM job_watchers
            WHERE (job_id, hostname) IN (
                SELECT job_id, hostname FROM cached_jobs
                WHERE json_extract(job_info_json, '$.user') NOT IN ({placeholders})
            )
        )
    """, keep_users)
    watcher_events_deleted = cursor.rowcount
    print(f"  Deleted {watcher_events_deleted} watcher events")

    # 2. Delete watcher variables
    cursor = conn.execute(f"""
        DELETE FROM watcher_variables
        WHERE watcher_id IN (
            SELECT id FROM job_watchers
            WHERE (job_id, hostname) IN (
                SELECT job_id, hostname FROM cached_jobs
                WHERE json_extract(job_info_json, '$.user') NOT IN ({placeholders})
            )
        )
    """, keep_users)
    watcher_vars_deleted = cursor.rowcount
    print(f"  Deleted {watcher_vars_deleted} watcher variables")

    # 3. Delete watchers
    cursor = conn.execute(f"""
        DELETE FROM job_watchers
        WHERE (job_id, hostname) IN (
            SELECT job_id, hostname FROM cached_jobs
            WHERE json_extract(job_info_json, '$.user') NOT IN ({placeholders})
        )
    """, keep_users)
    watchers_deleted = cursor.rowcount
    print(f"  Deleted {watchers_deleted} watchers")

    # 4. Delete array task stats
    cursor = conn.execute(f"""
        DELETE FROM array_task_stats
        WHERE (array_job_id, hostname) IN (
            SELECT DISTINCT json_extract(job_info_json, '$.array_job_id'), hostname
            FROM cached_jobs
            WHERE json_extract(job_info_json, '$.user') NOT IN ({placeholders})
              AND json_extract(job_info_json, '$.array_job_id') IS NOT NULL
        )
    """, keep_users)
    array_stats_deleted = cursor.rowcount
    print(f"  Deleted {array_stats_deleted} array task stats")

    # 5. Delete array jobs metadata
    cursor = conn.execute(f"""
        DELETE FROM array_jobs
        WHERE (array_job_id, hostname) IN (
            SELECT DISTINCT json_extract(job_info_json, '$.array_job_id'), hostname
            FROM cached_jobs
            WHERE json_extract(job_info_json, '$.user') NOT IN ({placeholders})
              AND json_extract(job_info_json, '$.array_job_id') IS NOT NULL
        )
    """, keep_users)
    array_jobs_deleted = cursor.rowcount
    print(f"  Deleted {array_jobs_deleted} array jobs")

    # 6. Finally, delete the jobs themselves
    cursor = conn.execute(f"""
        DELETE FROM cached_jobs
        WHERE json_extract(job_info_json, '$.user') NOT IN ({placeholders})
    """, keep_users)
    jobs_deleted = cursor.rowcount
    print(f"  Deleted {jobs_deleted} cached jobs")

    conn.commit()

    # Get final stats
    cursor = conn.execute("SELECT COUNT(*) FROM cached_jobs")
    total_after = cursor.fetchone()[0]

    conn.close()

    # Check file size reduction
    size_before = backup_path.stat().st_size if backup else cache_path.stat().st_size
    size_after = cache_path.stat().st_size

    print(f"\n✅ Cleanup complete!")
    print(f"  Jobs before: {total_before}")
    print(f"  Jobs after:  {total_after}")
    print(f"  Size before: {size_before / (1024*1024):.2f} MB")
    print(f"  Size after:  {size_after / (1024*1024):.2f} MB")
    print(f"  Space saved: {(size_before - size_after) / (1024*1024):.2f} MB")

    # Vacuum to reclaim space
    print(f"\nRunning VACUUM to reclaim disk space...")
    conn = sqlite3.connect(str(cache_path))
    conn.execute("VACUUM")
    conn.close()

    size_final = cache_path.stat().st_size
    print(f"  Final size after VACUUM: {size_final / (1024*1024):.2f} MB")
    print(f"  Total space saved: {(size_before - size_final) / (1024*1024):.2f} MB")


if __name__ == "__main__":
    # Your usernames
    keep_users = ['aramlaoui', 'ali_ramlaoui_entalpic_ai']

    print("=" * 70)
    print("Cache Cleanup - Remove Other Users' Jobs")
    print("=" * 70)
    print(f"\nKeeping jobs only from: {', '.join(keep_users)}")
    print("All other users' jobs will be PERMANENTLY DELETED.\n")

    response = input("Continue? (yes/no): ").strip().lower()
    if response == 'yes':
        cleanup_cache_by_user(keep_users, backup=True)
    else:
        print("Cleanup cancelled.")
