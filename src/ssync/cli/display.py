"""Job display utilities for CLI."""

from collections import defaultdict
from typing import Dict, List

import click

from ..models.job import JobInfo


class JobDisplay:
    """Handles formatting and displaying job information."""

    @staticmethod
    def filter_array_jobs(jobs: List[JobInfo]) -> List[JobInfo]:
        """Filter out array parent entries when individual tasks exist.

        SLURM returns both array parent entries (e.g., 443214_[2-3%4]) and individual
        tasks (e.g., 443214_0, 443214_1). The parent entry only shows the state of
        REMAINING tasks, which is misleading. This method filters them out.

        Args:
            jobs: List of jobs from SLURM

        Returns:
            Filtered list with array parent entries removed when tasks exist
        """
        # Separate array tasks from regular jobs
        array_tasks = defaultdict(list)
        parent_jobs = {}
        regular_jobs = []

        for job in jobs:
            # Check if this is an array task (numeric task ID)
            if job.array_job_id and job.array_task_id and job.array_task_id.isdigit():
                # This is an individual array task
                array_tasks[job.array_job_id].append(job)
            # Check if this is a parent job entry (has brackets like [0-4])
            elif (job.array_job_id and job.array_task_id and
                  '[' in job.array_task_id and ']' in job.array_task_id):
                # This is a parent job entry - store it for potential removal
                parent_jobs[job.array_job_id] = job
            else:
                # Regular non-array job
                regular_jobs.append(job)

        # Add back individual array tasks (these are the real jobs)
        for array_job_id, tasks in array_tasks.items():
            regular_jobs.extend(tasks)

        # Only add parent entries if they have NO individual tasks
        # (This handles the case where only the parent entry exists)
        for array_job_id, parent_job in parent_jobs.items():
            if array_job_id not in array_tasks:
                regular_jobs.append(parent_job)

        return regular_jobs

    @staticmethod
    def group_jobs_by_host(jobs: List[JobInfo]) -> Dict[str, List[JobInfo]]:
        """Group jobs by hostname for display."""
        # First filter out misleading array parent entries
        filtered_jobs = JobDisplay.filter_array_jobs(jobs)

        jobs_by_host = {}
        for job in filtered_jobs:
            if job.hostname not in jobs_by_host:
                jobs_by_host[job.hostname] = []
            jobs_by_host[job.hostname].append(job)
        return jobs_by_host

    @staticmethod
    def display_jobs_simple(jobs: List[JobInfo]):
        """Display jobs in a simple tabular format."""
        if not jobs:
            return

        click.echo(
            f"{'JobID':<12} {'Name':<20} {'State':<12} {'Runtime':<12} {'Reason':<20}"
        )
        click.echo("-" * 76)

        for job in jobs:
            runtime = job.runtime or "N/A"
            reason = job.reason or "N/A"
            if len(reason) > 18:
                reason = reason[:15] + "..."

            click.echo(
                f"{job.job_id:<12} {job.name:<20} {job.state.value:<12} {runtime:<12} {reason:<20}"
            )

    @staticmethod
    def display_jobs_detailed(jobs: List[JobInfo]):
        """Display jobs with detailed information."""
        for job in jobs:
            click.echo(f"\nJob {job.job_id}: {job.name}")
            click.echo(f"  State: {job.state.value}")

            if job.user:
                click.echo(f"  User: {job.user}")
            if job.partition:
                click.echo(f"  Partition: {job.partition}")

            # Resources
            resources = []
            if job.nodes and job.nodes != "N/A":
                resources.append(f"Nodes: {job.nodes}")
            if job.cpus and job.cpus != "N/A":
                resources.append(f"CPUs: {job.cpus}")
            if job.memory and job.memory != "N/A":
                resources.append(f"Memory: {job.memory}")
            if resources:
                click.echo(f"  Resources: {', '.join(resources)}")

            # GPU information
            if job.gpu_info:
                gpu_info = job.gpu_info
                if gpu_info.get("allocated"):
                    gpu_str = f"{gpu_info['allocated']['count']}x {gpu_info['allocated']['type']}"
                    click.echo(f"  GPUs: {gpu_str}")

            # Timing
            if job.time_limit and job.time_limit != "N/A":
                click.echo(f"  Time Limit: {job.time_limit}")
            if job.runtime and job.runtime != "N/A":
                click.echo(f"  Runtime: {job.runtime}")
            if job.submit_time and job.submit_time != "N/A":
                click.echo(f"  Submitted: {job.submit_time}")

            # Submit command
            if job.submit_line and job.submit_line != "N/A":
                click.echo(f"  Submit Command: {job.submit_line}")

            # Files
            if job.stdout_file and job.stdout_file != "N/A":
                click.echo(f"  Output: {job.stdout_file}")
            if job.stderr_file and job.stderr_file != "N/A":
                click.echo(f"  Error: {job.stderr_file}")
            if job.work_dir and job.work_dir != "N/A":
                click.echo(f"  Work Dir: {job.work_dir}")

            # Reason for pending jobs
            if job.reason and job.reason != "N/A" and job.state.value == "PD":
                click.echo(f"  Reason: {job.reason}")

    @staticmethod
    def display_jobs_by_host(
        jobs_by_host: Dict[str, List[JobInfo]], simple: bool = False
    ):
        """Display jobs grouped by hostname."""
        for hostname, host_jobs in jobs_by_host.items():
            click.echo(f"\n=== {hostname} ===")

            if not host_jobs:
                click.echo("No jobs found")
                continue

            if simple:
                JobDisplay.display_jobs_simple(host_jobs)
            else:
                JobDisplay.display_jobs_detailed(host_jobs)
