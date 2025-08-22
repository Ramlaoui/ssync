"""Job display utilities for CLI."""

from typing import Dict, List

import click

from ..models.job import JobInfo


class JobDisplay:
    """Handles formatting and displaying job information."""

    @staticmethod
    def group_jobs_by_host(jobs: List[JobInfo]) -> Dict[str, List[JobInfo]]:
        """Group jobs by hostname for display."""
        jobs_by_host = {}
        for job in jobs:
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
