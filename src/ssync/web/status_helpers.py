"""Shared status endpoint helpers for web job views."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from ..cache import get_cache
from ..utils.async_helpers import create_task
from ..utils.logging import setup_logger
from .models import ArrayJobGroup, JobInfoWeb, JobStateWeb, JobStatusResponse

logger = setup_logger(__name__)


def _get_array_base_job_ids(jobs: List[JobInfoWeb]) -> Set[str]:
    """Return base array job IDs represented in the current job list."""
    array_base_ids: Set[str] = set()
    for job in jobs:
        if job.array_job_id:
            array_base_ids.add(job.array_job_id)
    return array_base_ids


def group_array_job_tasks(
    jobs: List[JobInfoWeb], use_cache: bool = True
) -> tuple[List[JobInfoWeb], List[ArrayJobGroup]]:
    """Group array job tasks together using pre-computed cache stats when possible."""
    from collections import defaultdict

    array_base_ids = _get_array_base_job_ids(jobs)

    array_tasks = defaultdict(list)
    regular_jobs = []
    array_hostnames = {}
    array_state_counts = defaultdict(lambda: defaultdict(int))

    for job in jobs:
        if job.array_job_id and job.array_task_id and job.array_task_id.isdigit():
            array_tasks[job.array_job_id].append(job)
            array_hostnames[job.array_job_id] = job.hostname
            if job.state == JobStateWeb.PENDING:
                array_state_counts[job.array_job_id]["pending"] += 1
            elif job.state == JobStateWeb.RUNNING:
                array_state_counts[job.array_job_id]["running"] += 1
            elif job.state == JobStateWeb.COMPLETED:
                array_state_counts[job.array_job_id]["completed"] += 1
            elif job.state == JobStateWeb.FAILED:
                array_state_counts[job.array_job_id]["failed"] += 1
            elif job.state == JobStateWeb.CANCELLED:
                array_state_counts[job.array_job_id]["cancelled"] += 1
        elif (
            job.array_job_id
            and job.array_task_id
            and "[" in job.array_task_id
            and "]" in job.array_task_id
        ):
            array_hostnames[job.array_job_id] = job.hostname
        else:
            if job.job_id in array_base_ids:
                continue
            regular_jobs.append(job)

    array_groups = []
    cache = get_cache() if use_cache else None

    for array_job_id, tasks in array_tasks.items():
        hostname = array_hostnames.get(array_job_id)
        if not hostname or not tasks:
            continue

        metadata = (
            cache.get_array_job_metadata(array_job_id, hostname) if cache else None
        )
        counts = array_state_counts.get(array_job_id, {})
        first_task = tasks[0]
        array_groups.append(
            ArrayJobGroup(
                array_job_id=array_job_id,
                job_name=(metadata.get("job_name") if metadata else None)
                or first_task.name,
                hostname=hostname,
                user=(metadata.get("user") if metadata else None) or first_task.user,
                total_tasks=len(tasks),
                tasks=tasks,
                pending_count=counts.get("pending", 0),
                running_count=counts.get("running", 0),
                completed_count=counts.get("completed", 0),
                failed_count=counts.get("failed", 0),
                cancelled_count=counts.get("cancelled", 0),
            )
        )

    return regular_jobs, array_groups


def deduplicate_array_jobs(jobs: List[JobInfoWeb]) -> List[JobInfoWeb]:
    """Remove duplicate array job entries when not grouping."""
    deduplicated_jobs = []
    array_base_ids = _get_array_base_job_ids(jobs)

    for job in jobs:
        if (
            job.array_job_id
            and job.array_task_id
            and "[" in job.array_task_id
            and "]" in job.array_task_id
        ):
            continue
        if job.job_id in array_base_ids:
            continue
        deduplicated_jobs.append(job)

    return deduplicated_jobs


def _parse_submit_time(value: Optional[str]) -> datetime:
    """Parse submit_time strings safely for sorting."""
    if not value:
        return datetime.fromtimestamp(0)
    try:
        return datetime.fromisoformat(value)
    except Exception:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return datetime.fromtimestamp(0)


def _job_matches_search(job: JobInfoWeb, search_lower: str) -> bool:
    """Return True when a job matches a lowercase status search term."""
    return search_lower in job.job_id.lower() or (
        bool(job.name) and search_lower in job.name.lower()
    )


def filter_jobs_by_search(
    jobs: List[JobInfoWeb], search: Optional[str]
) -> List[JobInfoWeb]:
    """Apply the status endpoint search filter to web jobs."""
    if not search:
        return jobs

    search_lower = search.lower()
    return [job for job in jobs if _job_matches_search(job, search_lower)]


def build_status_cache_filters(
    *,
    user: Optional[str],
    state: Optional[str],
    active_only: bool,
    completed_only: bool,
) -> Dict[str, Any]:
    """Build the cache-key filters for date-range status queries."""
    return {
        "user": user,
        "state": state,
        "active_only": active_only,
        "completed_only": completed_only,
    }


def _normalize_cached_status_jobs(
    *,
    cached_jobs: List[JobInfoWeb],
    cached_state_map: Dict[str, Any],
    active_only: bool,
    completed_only: bool,
) -> List[JobInfoWeb]:
    """Normalize cached jobs before applying search and grouping logic."""
    normalized_jobs: List[JobInfoWeb] = []

    for job in cached_jobs:
        cached = cached_state_map.get(job.job_id)
        is_active_cached = cached.is_active if cached else True

        if active_only and not is_active_cached:
            continue

        if completed_only and job.state not in [
            JobStateWeb.COMPLETED,
            JobStateWeb.FAILED,
            JobStateWeb.CANCELLED,
            JobStateWeb.TIMEOUT,
            JobStateWeb.UNKNOWN,
        ]:
            continue

        if (not is_active_cached) and job.state in [
            JobStateWeb.PENDING,
            JobStateWeb.RUNNING,
        ]:
            job = job.model_copy(update={"state": JobStateWeb.UNKNOWN})

        normalized_jobs.append(job)

    return normalized_jobs


async def get_cached_date_range_status_response(
    *,
    cache_middleware,
    hostname: str,
    since: str,
    cache_filters: Dict[str, Any],
    active_only: bool,
    completed_only: bool,
    state: Optional[str],
    search: Optional[str],
    group_array_jobs: bool,
    limit: Optional[int],
    refresh_callback,
) -> Optional[JobStatusResponse]:
    """Return a cached date-range status response when available."""
    cached_jobs = await cache_middleware.check_date_range_cache(
        hostname=hostname,
        filters=cache_filters,
        since=since,
    )
    if cached_jobs is None:
        return None

    cached_state_map = cache_middleware.cache.get_cached_jobs_by_ids(
        [job.job_id for job in cached_jobs],
        hostname,
    )
    normalized_jobs = _normalize_cached_status_jobs(
        cached_jobs=cached_jobs,
        cached_state_map=cached_state_map,
        active_only=active_only,
        completed_only=completed_only,
    )

    cache_entry = cache_middleware.cache.check_date_range_cache_entry(
        hostname,
        cache_filters,
        since,
    )
    if cache_entry:
        cache_age = (
            datetime.now() - cache_entry.get("cached_at", datetime.now())
        ).total_seconds()
        if cache_age > 60:
            logger.info(
                f"Cache for {hostname} is {cache_age:.0f}s old - triggering background refresh"
            )
            create_task(refresh_callback())

    if state:
        normalized_jobs = [job for job in normalized_jobs if job.state == state]

    web_jobs = filter_jobs_by_search(normalized_jobs, search)
    response = build_job_status_response(
        hostname=hostname,
        web_jobs=web_jobs,
        query_time=datetime.now(),
        group_array_jobs=group_array_jobs,
        limit=limit,
        cached=True,
    )
    logger.info(
        f"Served {len(web_jobs)} jobs from date range cache for {hostname} (grouping={group_array_jobs})"
    )
    return response


def apply_grouped_limit(
    display_jobs: List[JobInfoWeb],
    array_groups: Optional[List[ArrayJobGroup]],
    limit: Optional[int],
) -> tuple[List[JobInfoWeb], Optional[List[ArrayJobGroup]]]:
    """Apply limit where each array group counts as one item."""
    if not limit or limit <= 0:
        return display_jobs, array_groups

    groups = array_groups or []
    items: list[tuple[datetime, str, object]] = []
    for job in display_jobs:
        items.append((_parse_submit_time(job.submit_time), "job", job))
    for group in groups:
        group_time = None
        if group.tasks:
            group_time = max(
                (_parse_submit_time(task.submit_time) for task in group.tasks if task),
                default=None,
            )
        items.append((group_time or datetime.fromtimestamp(0), "group", group))

    items.sort(key=lambda item: item[0], reverse=True)
    items = items[:limit]

    limited_jobs: List[JobInfoWeb] = []
    limited_groups: List[ArrayJobGroup] = []
    for _ts, kind, obj in items:
        if kind == "job":
            limited_jobs.append(obj)  # type: ignore[arg-type]
        else:
            limited_groups.append(obj)  # type: ignore[arg-type]

    return limited_jobs, limited_groups


def build_job_status_response(
    *,
    hostname: str,
    web_jobs: List[JobInfoWeb],
    query_time: datetime,
    group_array_jobs: bool,
    limit: Optional[int],
    cached: bool = False,
) -> JobStatusResponse:
    """Build a status response with shared array-group shaping rules."""
    array_groups = None
    if group_array_jobs and web_jobs:
        display_jobs, array_groups = group_array_job_tasks(web_jobs)
        display_jobs, array_groups = apply_grouped_limit(
            display_jobs, array_groups, limit
        )
        total_jobs = len(display_jobs) + (len(array_groups) if array_groups else 0)
    else:
        display_jobs = deduplicate_array_jobs(web_jobs)
        total_jobs = len(web_jobs)

    return JobStatusResponse(
        hostname=hostname,
        jobs=display_jobs,
        total_jobs=total_jobs,
        query_time=query_time,
        group_array_jobs=group_array_jobs,
        array_groups=array_groups,
        cached=cached,
    )
