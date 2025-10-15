#!/usr/bin/env python3
"""
One-time script to fix corrupted cache entries where is_active=False but state=PD.

This queries sacct for the correct final state and updates the cache.
"""

import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, 'src')

from ssync.cache import get_cache
from ssync.slurm.client import SlurmClient
from ssync.connection import ConnectionManager
from ssync.models.cluster import Host
from ssync.utils.config import config

def fix_corrupted_cache():
    """Fix all corrupted cache entries."""

    cache = get_cache()

    # Find all corrupted entries
    db_path = Path.home() / '.cache' / 'ssync' / 'jobs.db'
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT job_id, hostname, job_info_json
        FROM cached_jobs
        WHERE is_active = 0
          AND json_extract(job_info_json, '$.state') = 'PD'
        ORDER BY hostname, job_id
    """)

    corrupted_jobs = []
    for row in cursor.fetchall():
        job_info = json.loads(row['job_info_json'])
        corrupted_jobs.append({
            'job_id': row['job_id'],
            'hostname': row['hostname'],
            'submit_time': job_info.get('submit_time'),
        })

    conn.close()

    if not corrupted_jobs:
        print("✓ No corrupted jobs found!")
        return 0

    print(f"Found {len(corrupted_jobs)} corrupted job entries")
    print(f"\nStarting cleanup...\n")

    # Group by hostname
    jobs_by_host = {}
    for job in corrupted_jobs:
        host = job['hostname']
        if host not in jobs_by_host:
            jobs_by_host[host] = []
        jobs_by_host[host].append(job)

    # Connect and fix each host
    connection_manager = ConnectionManager(use_ssh_config=True)
    slurm_client = SlurmClient()

    total_fixed = 0
    total_failed = 0

    for hostname, jobs in jobs_by_host.items():
        print(f"\n{'='*60}")
        print(f"Processing {hostname}: {len(jobs)} jobs")
        print(f"{'='*60}")

        try:
            # Get connection - try different approaches from config
            host_config = None
            for slurm_host in config.config:  # config.config is the list of SlurmHost objects
                if slurm_host.host.hostname == hostname:
                    host_config = slurm_host.host
                    break

            if not host_config:
                print(f"⚠ Warning: No config found for {hostname}, skipping...")
                total_failed += len(jobs)
                continue

            print(f"Connecting to {hostname}...")
            conn = connection_manager.get_connection(host_config)
            print(f"✓ Connected")

            # Process each job
            fixed_count = 0
            failed_count = 0

            for i, job in enumerate(jobs, 1):
                job_id = job['job_id']

                if i % 10 == 0 or i == len(jobs):
                    print(f"  Progress: {i}/{len(jobs)} jobs processed...", end='\r')

                try:
                    # Fetch final state from sacct
                    final_state = slurm_client.get_job_final_state(
                        conn, hostname, job_id
                    )

                    if final_state:
                        # Get existing cached job to preserve script
                        cached_job = cache.get_cached_job(job_id, hostname)
                        script_content = cached_job.script_content if cached_job else None

                        # Update cache with correct final state
                        cache.cache_job(final_state, script_content=script_content)
                        fixed_count += 1
                    else:
                        # Job not found in sacct - might be too old
                        # Just mark as unknown/completed
                        failed_count += 1

                except Exception as e:
                    print(f"\n  ✗ Error fixing {job_id}: {e}")
                    failed_count += 1

            print(f"\n  ✓ Fixed: {fixed_count}, ✗ Failed: {failed_count}")
            total_fixed += fixed_count
            total_failed += failed_count

        except Exception as e:
            print(f"\n✗ Error connecting to {hostname}: {e}")
            total_failed += len(jobs)

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Total jobs processed: {len(corrupted_jobs)}")
    print(f"✓ Successfully fixed: {total_fixed}")
    print(f"✗ Failed to fix: {total_failed}")

    if total_failed > 0:
        print(f"\nNote: Failed jobs might be too old (>30 days) and purged from sacct.")
        print(f"These will show as 'UNKNOWN' state but won't cause issues.")

    return 0

if __name__ == '__main__':
    try:
        sys.exit(fix_corrupted_cache())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
