from datetime import datetime

import pytest

from ssync.web.cache.responses import CacheResponseService
from ssync.web.schemas import JobInfoWeb, JobStateWeb, JobStatusResponse


class _FakeCache:
    def __init__(self):
        self.cache_job_calls = []
        self.cache_date_range_calls = []

    def cache_job(self, job_info):
        self.cache_job_calls.append(job_info)

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
