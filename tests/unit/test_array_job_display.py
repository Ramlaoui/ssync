"""Unit tests for synthetic array-parent placeholder filtering."""

import pytest

from ssync.cli.display import JobDisplay
from ssync.models.job import JobInfo, JobState
from ssync.utils.slurm_arrays import looks_like_array_submission
from ssync.web import app as web_app
from ssync.web.models import JobInfoWeb


def _make_job(
    job_id: str,
    *,
    state: JobState = JobState.PENDING,
    array_job_id: str | None = None,
    array_task_id: str | None = None,
):
    return JobInfo(
        job_id=job_id,
        name="array-test",
        state=state,
        hostname="cluster.example.com",
        user="testuser",
        array_job_id=array_job_id,
        array_task_id=array_task_id,
    )


@pytest.mark.unit
def test_cli_filter_array_jobs_hides_synthetic_parent_when_tasks_exist():
    jobs = [
        _make_job("9001"),
        _make_job("9001_0", array_job_id="9001", array_task_id="0"),
    ]

    filtered = JobDisplay.filter_array_jobs(jobs)

    assert [job.job_id for job in filtered] == ["9001_0"]


@pytest.mark.unit
def test_web_deduplicate_array_jobs_hides_synthetic_parent_when_tasks_exist():
    jobs = [
        JobInfoWeb.from_job_info(_make_job("9002")),
        JobInfoWeb.from_job_info(
            _make_job("9002_0", array_job_id="9002", array_task_id="0")
        ),
    ]

    filtered = web_app.deduplicate_array_jobs(jobs)

    assert [job.job_id for job in filtered] == ["9002_0"]


@pytest.mark.unit
def test_looks_like_array_submission_detects_sbatch_array_flags():
    assert looks_like_array_submission("#SBATCH --array=0-3")
    assert looks_like_array_submission(None, "sbatch --array 0-3 /tmp/job.sbatch")
    assert not looks_like_array_submission("#SBATCH --time=01:00:00")
