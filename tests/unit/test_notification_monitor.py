from datetime import datetime, timedelta, timezone

import pytest

from ssync.models.job import JobInfo, JobState
from ssync.notifications.monitor import _is_recent_terminal, _is_recent_transition


def _job(**overrides) -> JobInfo:
    now = datetime.now()
    payload = {
        "job_id": "12345",
        "name": "train",
        "state": JobState.RUNNING,
        "hostname": "jz",
        "submit_time": now.isoformat(),
    }
    payload.update(overrides)
    return JobInfo(**payload)


@pytest.mark.unit
def test_recent_transition_accepts_timezone_aware_times():
    start_time = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    job = _job(state=JobState.RUNNING, start_time=start_time)

    assert _is_recent_transition(job, JobState.RUNNING.value, 600) is True


@pytest.mark.unit
def test_recent_terminal_accepts_timezone_aware_times():
    end_time = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    job = _job(state=JobState.COMPLETED, end_time=end_time)

    assert _is_recent_terminal(job, 600) is True


@pytest.mark.unit
def test_recent_transition_accepts_naive_times():
    start_time = (datetime.now() - timedelta(seconds=30)).isoformat()
    job = _job(state=JobState.RUNNING, start_time=start_time)

    assert _is_recent_transition(job, JobState.RUNNING.value, 600) is True
