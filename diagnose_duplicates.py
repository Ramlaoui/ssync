#!/usr/bin/env python3
"""Diagnostic script to check for duplicate jobs in the UI."""

import requests
import json
from collections import Counter

# Fetch jobs from the API
response = requests.get('http://localhost:8042/api/status', verify=False)
data = response.json()

print("=== API Response Analysis ===\n")

all_jobs = []
for host_data in data:
    hostname = host_data['hostname']
    jobs = host_data['jobs']
    print(f"Host: {hostname}")
    print(f"  Total jobs returned: {len(jobs)}")

    # Check for duplicates in this host's response
    job_ids = [j['job_id'] for j in jobs]
    duplicates = [(job_id, count) for job_id, count in Counter(job_ids).items() if count > 1]

    if duplicates:
        print(f"  ⚠️  DUPLICATES FOUND:")
        for job_id, count in duplicates:
            print(f"    - {job_id}: appears {count} times")
            # Show details of duplicate entries
            dupes = [j for j in jobs if j['job_id'] == job_id]
            for i, dupe in enumerate(dupes):
                print(f"      [{i+1}] state={dupe.get('state')}, "
                      f"array_job_id={dupe.get('array_job_id')}, "
                      f"array_task_id={dupe.get('array_task_id')}")
    else:
        print(f"  ✓ No duplicates")

    all_jobs.extend(jobs)
    print()

print(f"Total jobs across all hosts: {len(all_jobs)}")
print(f"Unique job_ids: {len(set(j['job_id'] for j in all_jobs))}")

# Check for array job parent entries
parent_entries = [j for j in all_jobs if j.get('array_task_id') and '[' in str(j.get('array_task_id'))]
print(f"Array job parent entries (with brackets): {len(parent_entries)}")
if parent_entries:
    print("  Examples:")
    for j in parent_entries[:5]:
        print(f"    - {j['job_id']}: {j.get('array_task_id')}")
