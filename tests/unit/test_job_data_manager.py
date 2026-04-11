"""Unit tests for JobDataManager concurrency and timeout behavior."""

import asyncio
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ssync.job_data_manager import JobDataManager
from ssync.models.cluster import Host, SlurmHost
from ssync.models.job import JobInfo, JobState


class _FakeManager:
    def __init__(self, slurm_hosts):
        self.slurm_hosts = slurm_hosts
        self.slurm_client = None

    def get_host_by_name(self, hostname: str):
        for slurm_host in self.slurm_hosts:
            if slurm_host.host.hostname == hostname:
                return slurm_host
        raise ValueError(f"Host {hostname} not found")


def _install_fake_web_app(monkeypatch, manager):
    fake_module = types.ModuleType("ssync.web.app")
    fake_module.get_slurm_manager = lambda: manager
    monkeypatch.setitem(sys.modules, "ssync.web.app", fake_module)


def _make_slurm_host(hostname: str) -> SlurmHost:
    return SlurmHost(
        host=Host(hostname=hostname, username="testuser"),
        work_dir=Path("/tmp"),
        scratch_dir=Path("/tmp"),
    )


def _make_job(
    job_id: str, hostname: str, state: JobState = JobState.RUNNING
) -> JobInfo:
    return JobInfo(
        job_id=job_id,
        name=f"job_{job_id}",
        state=state,
        hostname=hostname,
        user="testuser",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_all_jobs_returns_cached_for_busy_host(monkeypatch, test_cache):
    hostname = "cluster-busy.example.com"
    slurm_host = _make_slurm_host(hostname)
    manager = _FakeManager([slurm_host])
    _install_fake_web_app(monkeypatch, manager)

    job_data_manager = JobDataManager()
    job_data_manager.cache = test_cache
    job_data_manager._busy_host_wait_seconds = 0.0

    cached_job = _make_job("1001", hostname)
    test_cache.cache_job(cached_job)

    # Simulate host already being fetched by another request.
    job_data_manager._fetching_hosts.add(hostname)

    jobs = await job_data_manager.fetch_all_jobs(hostname=hostname)

    assert [job.job_id for job in jobs] == ["1001"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_all_jobs_concurrent_requests_use_cache_for_second_request(
    monkeypatch, test_cache
):
    hostname = "cluster-concurrent.example.com"
    slurm_host = _make_slurm_host(hostname)
    manager = _FakeManager([slurm_host])
    _install_fake_web_app(monkeypatch, manager)

    job_data_manager = JobDataManager()
    job_data_manager.cache = test_cache
    job_data_manager._busy_host_wait_seconds = 0.0
    job_data_manager._host_fetch_timeout_seconds = 5.0

    cached_job = _make_job("2001", hostname)
    live_job = _make_job("2002", hostname)
    test_cache.cache_job(cached_job)

    started = asyncio.Event()
    release = asyncio.Event()
    fetch_calls = {"count": 0}

    async def fake_fetch_host_jobs(*args, **kwargs):
        fetch_calls["count"] += 1
        started.set()
        await release.wait()
        return [live_job]

    monkeypatch.setattr(job_data_manager, "_fetch_host_jobs", fake_fetch_host_jobs)

    first_request = asyncio.create_task(
        job_data_manager.fetch_all_jobs(hostname=hostname)
    )
    await started.wait()

    # While first request is in-flight, second should avoid duplicate fetch and use cache.
    second_result = await job_data_manager.fetch_all_jobs(hostname=hostname)

    release.set()
    first_result = await first_request

    assert fetch_calls["count"] == 1
    assert [job.job_id for job in second_result] == ["2001"]
    assert [job.job_id for job in first_result] == ["2002"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_all_jobs_timeout_returns_cache_and_releases_host_after_completion(
    monkeypatch, test_cache
):
    hostname = "cluster-timeout.example.com"
    slurm_host = _make_slurm_host(hostname)
    manager = _FakeManager([slurm_host])
    _install_fake_web_app(monkeypatch, manager)

    job_data_manager = JobDataManager()
    job_data_manager.cache = test_cache
    job_data_manager._host_fetch_timeout_seconds = 0.01
    job_data_manager._busy_host_wait_seconds = 0.0
    job_data_manager._host_failure_backoff_seconds = 60.0

    cached_job = _make_job("3001", hostname)
    live_job = _make_job("3002", hostname)
    test_cache.cache_job(cached_job)

    release = asyncio.Event()
    fetch_calls = {"count": 0}
    busy_cache_calls = {"count": 0}

    async def slow_fetch_host_jobs(*args, **kwargs):
        fetch_calls["count"] += 1
        await release.wait()
        await job_data_manager._clear_host_fetch_failure(hostname)
        return [live_job]

    async def fail_if_busy_host_cache(*args, **kwargs):
        busy_cache_calls["count"] += 1
        raise AssertionError(
            "timed-out host should use failure backoff, not busy-host cache"
        )

    monkeypatch.setattr(job_data_manager, "_fetch_host_jobs", slow_fetch_host_jobs)
    monkeypatch.setattr(
        job_data_manager, "_get_cached_jobs_for_busy_host", fail_if_busy_host_cache
    )

    result = await job_data_manager.fetch_all_jobs(hostname=hostname)

    # Fast response with cached data while slow fetch continues in background.
    assert [job.job_id for job in result] == ["3001"]
    assert hostname in job_data_manager._fetching_hosts
    assert hostname in job_data_manager._host_failure_until
    assert fetch_calls["count"] == 1

    second_result = await job_data_manager.fetch_all_jobs(hostname=hostname)
    assert [job.job_id for job in second_result] == ["3001"]
    assert fetch_calls["count"] == 1
    assert busy_cache_calls["count"] == 0

    release.set()

    # Background task completion should release host reservation.
    for _ in range(50):
        if hostname not in job_data_manager._fetching_hosts:
            break
        await asyncio.sleep(0.01)

    assert hostname not in job_data_manager._fetching_hosts
    assert hostname not in job_data_manager._host_failure_until


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_all_jobs_skips_backed_off_host_and_uses_cache(
    monkeypatch, test_cache
):
    hostname = "cluster-backoff.example.com"
    slurm_host = _make_slurm_host(hostname)
    manager = _FakeManager([slurm_host])
    _install_fake_web_app(monkeypatch, manager)

    job_data_manager = JobDataManager()
    job_data_manager.cache = test_cache
    job_data_manager._host_failure_backoff_seconds = 60.0

    cached_job = _make_job("4001", hostname)
    test_cache.cache_job(cached_job)

    loop = asyncio.get_running_loop()
    job_data_manager._host_failure_until[hostname] = loop.time() + 30.0

    fetch_calls = {"count": 0}

    async def fake_fetch_host_jobs(*args, **kwargs):
        fetch_calls["count"] += 1
        return [_make_job("4002", hostname)]

    monkeypatch.setattr(job_data_manager, "_fetch_host_jobs", fake_fetch_host_jobs)

    result = await job_data_manager.fetch_all_jobs(hostname=hostname)

    assert fetch_calls["count"] == 0
    assert [job.job_id for job in result] == ["4001"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_all_jobs_uses_live_fetch_after_backoff_expires(
    monkeypatch, test_cache
):
    hostname = "cluster-backoff-expired.example.com"
    slurm_host = _make_slurm_host(hostname)
    manager = _FakeManager([slurm_host])
    _install_fake_web_app(monkeypatch, manager)

    job_data_manager = JobDataManager()
    job_data_manager.cache = test_cache
    job_data_manager._host_failure_backoff_seconds = 60.0

    # Expired backoff should be ignored.
    loop = asyncio.get_running_loop()
    job_data_manager._host_failure_until[hostname] = loop.time() - 1.0

    fetch_calls = {"count": 0}
    live_job = _make_job("5001", hostname)

    async def fake_fetch_host_jobs(*args, **kwargs):
        fetch_calls["count"] += 1
        return [live_job]

    monkeypatch.setattr(job_data_manager, "_fetch_host_jobs", fake_fetch_host_jobs)

    result = await job_data_manager.fetch_all_jobs(hostname=hostname)

    assert fetch_calls["count"] == 1
    assert [job.job_id for job in result] == ["5001"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_force_output_fetch_deduplicates_concurrent_requests(test_cache):
    hostname = "cluster-output-dedup.example.com"
    job_data_manager = JobDataManager()
    job_data_manager.cache = test_cache

    job_info = _make_job("6001", hostname, state=JobState.RUNNING)
    started = asyncio.Event()
    release = asyncio.Event()
    fetch_calls = {"count": 0}

    async def fake_do_fetch_outputs(job_info_arg, force_fetch=False):
        fetch_calls["count"] += 1
        started.set()
        await release.wait()
        return (
            f"stdout:{job_info_arg.job_id}:{force_fetch}",
            f"stderr:{job_info_arg.job_id}:{force_fetch}",
        )

    job_data_manager._do_fetch_outputs = fake_do_fetch_outputs

    first = asyncio.create_task(
        job_data_manager._fetch_outputs_from_cached_paths(job_info, force_fetch=True)
    )
    await started.wait()
    second = asyncio.create_task(
        job_data_manager._fetch_outputs_from_cached_paths(job_info, force_fetch=True)
    )

    await asyncio.sleep(0)
    assert fetch_calls["count"] == 1

    release.set()
    first_result = await first
    second_result = await second

    assert first_result == second_result == (
        "stdout:6001:True",
        "stderr:6001:True",
    )
    assert not job_data_manager._output_fetch_futures


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_all_jobs_applies_global_limit_for_cache_only_paths(
    monkeypatch, test_cache
):
    host_a = "cluster-a.example.com"
    host_b = "cluster-b.example.com"
    slurm_hosts = [_make_slurm_host(host_a), _make_slurm_host(host_b)]
    manager = _FakeManager(slurm_hosts)
    _install_fake_web_app(monkeypatch, manager)

    job_data_manager = JobDataManager()
    job_data_manager.cache = test_cache
    job_data_manager._busy_host_wait_seconds = 0.0

    # Seed cache with more jobs than the requested global limit.
    for i in range(4):
        test_cache.cache_job(_make_job(f"a-{i}", host_a))
        test_cache.cache_job(_make_job(f"b-{i}", host_b))

    # Make all hosts unavailable for live fetch so response is cache-only.
    job_data_manager._fetching_hosts.update({host_a, host_b})

    result = await job_data_manager.fetch_all_jobs(limit=2)

    assert len(result) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_all_jobs_profile_mode_passes_flags_to_host_fetch(
    monkeypatch, test_cache
):
    hostname = "cluster-profile.example.com"
    slurm_host = _make_slurm_host(hostname)
    manager = _FakeManager([slurm_host])
    _install_fake_web_app(monkeypatch, manager)

    job_data_manager = JobDataManager()
    job_data_manager.cache = test_cache

    captured_kwargs = {}

    async def fake_fetch_host_jobs(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return [_make_job("6001", hostname)]

    monkeypatch.setattr(job_data_manager, "_fetch_host_jobs", fake_fetch_host_jobs)

    result = await job_data_manager.fetch_all_jobs(hostname=hostname, profile=True)

    assert [job.job_id for job in result] == ["6001"]
    assert captured_kwargs.get("profile_enabled") is True
    assert isinstance(captured_kwargs.get("profile_request_id"), str)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_all_jobs_merges_recent_cached_active_jobs_when_live_query_misses(
    monkeypatch, test_cache
):
    hostname = "cluster-recent-cache.example.com"
    slurm_host = _make_slurm_host(hostname)
    manager = _FakeManager([slurm_host])
    _install_fake_web_app(monkeypatch, manager)

    class _FakeConnection:
        def run(self, command: str, **kwargs):
            raise AssertionError(f"Unexpected command execution: {command}")

    class _FakeSlurmClient:
        def check_slurm_availability(self, conn, hostname_arg):
            assert hostname_arg == hostname
            return True

        def get_username(self, conn, _unused=None, hostname=None):
            assert hostname == hostname
            return "testuser"

        def get_active_jobs(
            self,
            conn,
            hostname_arg,
            user,
            job_ids,
            state_filter,
            skip_user_detection,
        ):
            assert hostname_arg == hostname
            assert user == "testuser"
            return []

    manager.slurm_client = _FakeSlurmClient()
    manager._get_connection = lambda host: _FakeConnection()

    job_data_manager = JobDataManager()
    job_data_manager.cache = test_cache

    cached_job = _make_job("6002", hostname, JobState.PENDING)
    cached_job.user = None  # Launch-time cache can precede user enrichment from Slurm.
    test_cache.cache_job(cached_job)

    jobs = await job_data_manager.fetch_all_jobs(hostname=hostname, active_only=True)

    assert [job.job_id for job in jobs] == ["6002"]
    assert jobs[0].state == JobState.PENDING


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_all_jobs_skips_stale_active_cache_for_missing_specific_job(
    monkeypatch, test_cache
):
    hostname = "cluster-stale-cache.example.com"
    slurm_host = _make_slurm_host(hostname)
    manager = _FakeManager([slurm_host])
    _install_fake_web_app(monkeypatch, manager)

    class _FakeConnection:
        def run(self, command: str, **kwargs):
            raise AssertionError(f"Unexpected command execution: {command}")

    class _FakeSlurmClient:
        def check_slurm_availability(self, conn, hostname_arg):
            assert hostname_arg == hostname
            return True

        def get_username(self, conn, _unused=None, hostname=None):
            assert hostname == hostname
            return "testuser"

        def get_active_jobs(
            self,
            conn,
            hostname_arg,
            user,
            job_ids,
            state_filter,
            skip_user_detection,
        ):
            assert hostname_arg == hostname
            assert job_ids == ["6003"]
            return []

        def get_completed_jobs(
            self,
            conn,
            hostname_arg,
            since,
            user,
            job_ids,
            state_filter,
            exclude_job_ids,
            skip_user_detection,
            limit,
            cached_completed_ids,
        ):
            assert hostname_arg == hostname
            assert job_ids == ["6003"]
            return []

    manager.slurm_client = _FakeSlurmClient()
    manager._get_connection = lambda host: _FakeConnection()

    job_data_manager = JobDataManager()
    job_data_manager.cache = test_cache
    job_data_manager._recent_active_cache_ttl_seconds = 60

    cached_job = _make_job("6003", hostname, JobState.RUNNING)
    test_cache.cache_job(cached_job)

    stale_time = (datetime.now() - timedelta(minutes=10)).isoformat()
    with test_cache._get_connection() as conn:
        conn.execute(
            """
            UPDATE cached_jobs
            SET last_updated = ?
            WHERE job_id = ? AND hostname = ?
            """,
            (stale_time, "6003", hostname),
        )
        conn.commit()

    jobs = await job_data_manager.fetch_all_jobs(hostname=hostname, job_ids=["6003"])

    assert jobs == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_all_jobs_returns_inactive_cache_for_missing_specific_job(
    monkeypatch, test_cache
):
    hostname = "cluster-inactive-cache.example.com"
    slurm_host = _make_slurm_host(hostname)
    manager = _FakeManager([slurm_host])
    _install_fake_web_app(monkeypatch, manager)

    class _FakeConnection:
        def run(self, command: str, **kwargs):
            raise AssertionError(f"Unexpected command execution: {command}")

    class _FakeSlurmClient:
        def check_slurm_availability(self, conn, hostname_arg):
            assert hostname_arg == hostname
            return True

        def get_username(self, conn, _unused=None, hostname=None):
            assert hostname == hostname
            return "testuser"

        def get_active_jobs(
            self,
            conn,
            hostname_arg,
            user,
            job_ids,
            state_filter,
            skip_user_detection,
        ):
            return []

        def get_completed_jobs(
            self,
            conn,
            hostname_arg,
            since,
            user,
            job_ids,
            state_filter,
            exclude_job_ids,
            skip_user_detection,
            limit,
            cached_completed_ids,
        ):
            return []

    manager.slurm_client = _FakeSlurmClient()
    manager._get_connection = lambda host: _FakeConnection()

    job_data_manager = JobDataManager()
    job_data_manager.cache = test_cache

    cached_job = _make_job("6004", hostname, JobState.FAILED)
    test_cache.cache_job(cached_job)

    jobs = await job_data_manager.fetch_all_jobs(hostname=hostname, job_ids=["6004"])

    assert [job.job_id for job in jobs] == ["6004"]
    assert jobs[0].state == JobState.FAILED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_all_jobs_skips_old_launch_placeholders_from_recent_active_merge(
    monkeypatch, test_cache
):
    hostname = "cluster-placeholder.example.com"
    slurm_host = _make_slurm_host(hostname)
    manager = _FakeManager([slurm_host])
    _install_fake_web_app(monkeypatch, manager)

    class _FakeConnection:
        def run(self, command: str, **kwargs):
            raise AssertionError(f"Unexpected command execution: {command}")

    class _FakeSlurmClient:
        def check_slurm_availability(self, conn, hostname_arg):
            assert hostname_arg == hostname
            return True

        def get_username(self, conn, _unused=None, hostname=None):
            assert hostname == hostname
            return "testuser"

        def get_active_jobs(
            self,
            conn,
            hostname_arg,
            user,
            job_ids,
            state_filter,
            skip_user_detection,
        ):
            return []

    manager.slurm_client = _FakeSlurmClient()
    manager._get_connection = lambda host: _FakeConnection()

    job_data_manager = JobDataManager()
    job_data_manager.cache = test_cache
    job_data_manager._recent_active_cache_ttl_seconds = 600
    job_data_manager._placeholder_active_cache_ttl_seconds = 30

    placeholder_job = JobInfo(
        job_id="6005",
        name="array-launch",
        state=JobState.PENDING,
        hostname=hostname,
        submit_line="sbatch --array=0-3 /tmp/job.sbatch",
        user=None,
    )
    test_cache.cache_job(placeholder_job)

    old_cached_at = (datetime.now() - timedelta(minutes=5)).isoformat()
    with test_cache._get_connection() as conn:
        conn.execute(
            """
            UPDATE cached_jobs
            SET cached_at = ?, last_updated = ?
            WHERE job_id = ? AND hostname = ?
            """,
            (old_cached_at, datetime.now().isoformat(), "6005", hostname),
        )
        conn.commit()

    jobs = await job_data_manager.fetch_all_jobs(hostname=hostname, active_only=True)

    assert jobs == []
