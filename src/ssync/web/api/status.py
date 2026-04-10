"""Job status and cache route registration."""

import asyncio
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request

from ...cache import get_cache
from ...utils.logging import setup_logger
from ..models import JobInfoWeb, JobStatusResponse
from ..security import InputSanitizer
from ..status_helpers import (
    build_job_status_response,
    build_status_cache_filters,
    filter_jobs_by_search,
    get_cached_date_range_status_response,
)

logger = setup_logger(__name__)


def register_status_routes(
    app: FastAPI,
    *,
    verify_api_key_dependency,
    get_slurm_manager,
    cache_middleware,
) -> None:
    """Register job status and cache maintenance routes."""

    @app.get("/api/cache/stats")
    async def get_cache_stats(_authenticated: bool = Depends(verify_api_key_dependency)):
        """Get cache statistics including date range cache information."""
        try:
            stats = await cache_middleware.get_cache_stats()
            cache_middleware.cache.cleanup_expired_ranges()

            from ...request_coalescer import get_request_coalescer

            coalescer_stats = get_request_coalescer().get_stats()
            return {
                "status": "success",
                "statistics": {
                    **stats,
                    "request_coalescer": coalescer_stats,
                },
                "message": "Cache statistics retrieved successfully",
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to retrieve cache statistics"
            )

    @app.post("/api/cache/clear")
    async def clear_cache(_authenticated: bool = Depends(verify_api_key_dependency)):
        """Clear all cache entries."""
        try:
            get_cache().clear_all()
            return {"status": "success", "message": "Cache cleared successfully"}
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            raise HTTPException(status_code=500, detail="Failed to clear cache")

    @app.get("/api/status", response_model=List[JobStatusResponse])
    async def get_job_status(
        request: Request,
        host: Optional[str] = Query(None, description="Specific host to query"),
        user: Optional[str] = Query(
            None, description="User to filter jobs for (use '*' or 'all' for all users)"
        ),
        since: Optional[str] = Query(
            None,
            description="Time range for completed jobs",
            regex="^[0-9]+[hdwm]$",
        ),
        limit: Optional[int] = Query(
            None,
            description="Limit number of jobs returned",
            ge=1,
            le=1000,
        ),
        job_ids: Optional[str] = Query(None, description="Comma-separated job IDs"),
        state: Optional[str] = Query(
            None,
            description="Filter by job state",
            regex="^(PD|R|CD|F|CA|TO)$",
        ),
        active_only: bool = Query(False, description="Show only running/pending jobs"),
        completed_only: bool = Query(False, description="Show only completed jobs"),
        search: Optional[str] = Query(None, description="Search for jobs by name or ID"),
        group_array_jobs: bool = Query(
            False, description="Group array job tasks together"
        ),
        force_refresh: bool = Query(
            False, description="Force refresh from Slurm, bypassing all caches"
        ),
        profile: bool = Query(
            False,
            description="Enable server-side timing profile logs for this request",
        ),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Get job status across hosts."""
        try:
            if host:
                host = InputSanitizer.sanitize_hostname(host)

            skip_user_detection = False
            if user and user.lower() in ["*", "all"]:
                logger.warning(
                    f"⚠️ SECURITY ALERT: Special user value '{user}' detected - attempting to fetch ALL users' jobs"
                )
                logger.warning(
                    "This will fetch jobs from ALL users on the cluster, which may be slow and cause cache pollution"
                )
                logger.warning(
                    f"Request from: {request.client.host if request and hasattr(request, 'client') else 'unknown'}"
                )
                user = None
                skip_user_detection = True
            elif user:
                logger.info(f"Filtering for specific user: {user}")
                user = InputSanitizer.sanitize_username(user)
            else:
                logger.info(
                    "No user specified - will auto-detect current user for security"
                )

            if search:
                search = InputSanitizer.sanitize_text(search)
            if job_ids:
                job_id_list = [
                    InputSanitizer.sanitize_job_id(job_id.strip())
                    for job_id in job_ids.split(",")
                ]
            else:
                job_id_list = None

            safe_for_cache_verification = (
                not job_id_list
                and not search
                and not state
                and not active_only
                and not completed_only
                and not group_array_jobs
                and since is None
                and limit is None
            )

            manager = get_slurm_manager()
            slurm_hosts = manager.slurm_hosts
            if host:
                slurm_hosts = [slurm_host for slurm_host in slurm_hosts if slurm_host.host.hostname == host]
                if not slurm_hosts:
                    raise HTTPException(status_code=404, detail="Host not found")

            if len(slurm_hosts) > 1 and not job_id_list:
                from ...job_data_manager import get_job_data_manager

                logger.info(
                    f"Using optimized concurrent fetching for {len(slurm_hosts)} hosts"
                )
                logger.info(
                    f"Parameters: user={user}, skip_user_detection={skip_user_detection}"
                )
                job_data_manager = get_job_data_manager()

                try:
                    all_jobs = await job_data_manager.fetch_all_jobs(
                        hostname=None,
                        user=user,
                        since=since,
                        limit=limit,
                        job_ids=job_id_list,
                        state_filter=state,
                        active_only=active_only,
                        completed_only=completed_only,
                        skip_user_detection=skip_user_detection,
                        force_refresh=force_refresh,
                        profile=profile,
                    )

                    jobs_by_host = {}
                    for job in all_jobs:
                        jobs_by_host.setdefault(job.hostname, []).append(job)

                    for hostname in jobs_by_host:
                        web_jobs = [
                            JobInfoWeb.from_job_info(job)
                            for job in jobs_by_host[hostname]
                        ]
                        jobs_by_host[hostname] = filter_jobs_by_search(
                            web_jobs, search
                        )

                    results = []
                    for slurm_host in slurm_hosts:
                        hostname = slurm_host.host.hostname
                        results.append(
                            build_job_status_response(
                                hostname=hostname,
                                web_jobs=jobs_by_host.get(hostname, []),
                                query_time=datetime.now(),
                                group_array_jobs=group_array_jobs,
                                limit=limit,
                            )
                        )

                    logger.info(
                        f"Concurrent fetch completed: {sum(len(result.jobs) for result in results)} total jobs from {len(slurm_hosts)} hosts"
                    )

                    return await cache_middleware.cache_job_status_response(
                        results, verify_active_jobs=safe_for_cache_verification
                    )
                except Exception as e:
                    logger.error(f"Error in optimized concurrent fetch: {e}")
                    logger.info("Falling back to per-host fetching")

            async def fetch_host_jobs(slurm_host):
                hostname = slurm_host.host.hostname
                if host and since and not job_id_list and not force_refresh:
                    cache_filters = build_status_cache_filters(
                        user=user,
                        state=state,
                        active_only=active_only,
                        completed_only=completed_only,
                    )
                    cached_response = await get_cached_date_range_status_response(
                        cache_middleware=cache_middleware,
                        hostname=hostname,
                        since=since,
                        cache_filters=cache_filters,
                        active_only=active_only,
                        completed_only=completed_only,
                        state=state,
                        search=search,
                        group_array_jobs=group_array_jobs,
                        limit=limit,
                        refresh_callback=lambda: fetch_host_jobs(slurm_host),
                    )
                    if cached_response is not None:
                        return cached_response

                try:
                    jobs = await manager.get_all_jobs(
                        slurm_host,
                        user,
                        since,
                        limit,
                        job_id_list,
                        state,
                        active_only,
                        completed_only,
                        skip_user_detection,
                        force_refresh,
                    )
                    web_jobs = filter_jobs_by_search(
                        [JobInfoWeb.from_job_info(job) for job in jobs], search
                    )
                    return build_job_status_response(
                        hostname=hostname,
                        web_jobs=web_jobs,
                        query_time=datetime.now(),
                        group_array_jobs=group_array_jobs,
                        limit=limit,
                    )
                except Exception as e:
                    logger.error(f"Error querying {hostname}: {e}")
                    return JobStatusResponse(
                        hostname=hostname,
                        jobs=[],
                        total_jobs=0,
                        query_time=datetime.now(),
                    )

            results = await asyncio.gather(
                *(fetch_host_jobs(slurm_host) for slurm_host in slurm_hosts)
            )

            if host and since and not job_id_list:
                cache_filters = {
                    "user": user,
                    "state": state,
                    "active_only": active_only,
                    "completed_only": completed_only,
                }
                return await cache_middleware.cache_job_status_response(
                    results,
                    hostname=host,
                    filters=cache_filters,
                    since=since,
                    verify_active_jobs=safe_for_cache_verification,
                )

            return await cache_middleware.cache_job_status_response(
                results, verify_active_jobs=safe_for_cache_verification
            )
        except HTTPException:
            raise
        except Exception as e:
            import traceback

            logger.error(f"Error in get_job_status: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail="Internal server error occurred")
