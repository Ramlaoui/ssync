import asyncio
import threading
from datetime import datetime

import pytest

from ssync.models.job import JobState
from ssync.web.cache.responses import CacheResponseService
from ssync.web.schemas import JobInfoWeb, JobStateWeb, JobStatusResponse


class _FakeCache:
    def __init__(self):
        self.cache_job_calls = []
        self.cache_date_range_calls = []

    def cache_job(self, job_info):
        self.cache_job_calls.append(job_info)

    def cache_jobs(self, job_infos):
        self.cache_job_calls.extend(job_infos)

    def cache_date_range_query(self, **kwargs):
        self.cache_date_range_calls.append(kwargs)


def _make_job(job_id: str, hostname: str) -> JobInfoWeb:
    return JobInfoWeb(
        job_id=job_id,
        name=f"job-{job_id}",
        state=JobStateWeb.RUNNING,
        hostname=hostname,
        user="testuser",
        partition=None,
        nodes=None,
        cpus=None,
        memory=None,
        time_limit=None,
        runtime=None,
        reason=None,
        work_dir=None,
        stdout_file=None,
        stderr_file=None,
        submit_time=None,
        submit_line=None,
        start_time=None,
        end_time=None,
        node_list=None,
        alloc_tres=None,
        req_tres=None,
        cpu_time=None,
        total_cpu=None,
        user_cpu=None,
        system_cpu=None,
        ave_cpu=None,
        ave_cpu_freq=None,
        max_rss=None,
        ave_rss=None,
        max_vmsize=None,
        ave_vmsize=None,
        max_disk_read=None,
        max_disk_write=None,
        ave_disk_read=None,
        ave_disk_write=None,
        consumed_energy=None,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_job_status_response_skips_recaching_cached_responses():
    cache = _FakeCache()
    service = CacheResponseService(cache, recent_active_cache_ttl_seconds=60)
    response = JobStatusResponse(
        hostname="adastra",
        jobs=[_make_job("1001", "adastra")],
        total_jobs=42,
        query_time=datetime.now(),
        group_array_jobs=True,
        array_groups=[],
        cached=True,
    )

    result = await service.cache_job_status_response([response])

    assert result == [response]
    assert cache.cache_job_calls == []
    assert cache.cache_date_range_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_job_status_response_preserves_total_jobs_for_grouped_results():
    cache = _FakeCache()
    service = CacheResponseService(cache, recent_active_cache_ttl_seconds=60)
    response = JobStatusResponse(
        hostname="adastra",
        jobs=[_make_job("1001", "adastra")],
        total_jobs=7,
        query_time=datetime.now(),
        group_array_jobs=True,
        array_groups=[],
        cached=False,
    )

    result = await service.cache_job_status_response([response])

    assert result[0].total_jobs == 7
    assert len(cache.cache_job_calls) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_job_status_response_prepares_job_models_off_event_loop(
    monkeypatch,
):
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    call_thread = {}
    original_to_job_info = JobInfoWeb.to_job_info

    def blocking_to_job_info(self):
        call_thread["ident"] = threading.get_ident()
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=1)
        return original_to_job_info(self)

    monkeypatch.setattr(JobInfoWeb, "to_job_info", blocking_to_job_info)

    cache = _FakeCache()
    service = CacheResponseService(cache, recent_active_cache_ttl_seconds=60)
    response = JobStatusResponse(
        hostname="adastra",
        jobs=[_make_job("1001", "adastra")],
        total_jobs=1,
        query_time=datetime.now(),
        cached=False,
    )

    task = asyncio.create_task(service.cache_job_status_response([response]))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert call_thread["ident"] != threading.get_ident()

    release.set()
    result = await asyncio.wait_for(task, timeout=1.0)

    assert result[0].jobs[0].job_id == "1001"
    assert len(cache.cache_job_calls) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_job_status_response_runs_bulk_cache_off_event_loop():
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    call_thread = {}

    class BlockingCache(_FakeCache):
        def cache_jobs(self, job_infos):
            call_thread["ident"] = threading.get_ident()
            call_thread["jobs"] = [job.job_id for job in job_infos]
            loop.call_soon_threadsafe(started.set)
            assert release.wait(timeout=1)
            super().cache_jobs(job_infos)

    cache = BlockingCache()
    service = CacheResponseService(cache, recent_active_cache_ttl_seconds=60)
    response = JobStatusResponse(
        hostname="adastra",
        jobs=[_make_job("1001", "adastra")],
        total_jobs=1,
        query_time=datetime.now(),
        cached=False,
    )

    task = asyncio.create_task(service.cache_job_status_response([response]))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert call_thread["ident"] != threading.get_ident()
    assert call_thread["jobs"] == ["1001"]

    release.set()
    result = await asyncio.wait_for(task, timeout=1.0)

    assert result[0].jobs[0].job_id == "1001"
    assert len(cache.cache_job_calls) == 1


@pytest.mark.unit
def test_cache_jobs_preserves_existing_script_outputs_and_fields(test_cache):
    original = _make_job("1002", "adastra").to_job_info()
    original.stdout_file = "/old/stdout.log"
    test_cache.cache_job(original, script_content="#!/bin/bash\necho old")
    test_cache.update_job_outputs("1002", "adastra", stdout_content="old output")

    updated = _make_job("1002", "adastra").to_job_info()
    updated.state = JobState.COMPLETED
    updated.stdout_file = None

    test_cache.cache_jobs([updated])

    cached = test_cache.get_cached_job("1002", "adastra")
    assert cached is not None
    assert cached.script_content == "#!/bin/bash\necho old"
    assert cached.stdout_compressed
    assert cached.job_info.state == JobState.COMPLETED
    assert cached.job_info.stdout_file == "/old/stdout.log"
