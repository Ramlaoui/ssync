"""Cluster metadata route registration."""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query

from ...cache import get_cache
from ...utils.logging import setup_logger
from ..models import (
    HostInfoWeb,
    PartitionResourcesWeb,
    PartitionStatusResponse,
    SlurmDefaultsWeb,
)
from ..security import InputSanitizer, sanitize_error_message

logger = setup_logger(__name__)


def _format_time_delta(delta: timedelta) -> str:
    """Format a timedelta into a human-readable string."""
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds} seconds"
    if total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    if total_seconds < 86400:
        hours = total_seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = total_seconds // 86400
    return f"{days} day{'s' if days != 1 else ''}"


async def _run_in_executor(executor, func, *args, **kwargs):
    """Run blocking functions in the shared thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))


def register_cluster_routes(
    app: FastAPI,
    *,
    verify_api_key_dependency,
    get_slurm_manager,
    executor,
) -> None:
    """Register cache and cluster metadata routes."""

    @app.get("/api/cache/fetch-state")
    async def get_fetch_state(
        host: Optional[str] = Query(None, description="Specific host to check"),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Get the incremental fetch state for hosts."""
        try:
            cache = get_cache()
            manager = get_slurm_manager()

            if host:
                host = InputSanitizer.sanitize_hostname(host)
                hosts_to_check = [
                    slurm_host
                    for slurm_host in manager.slurm_hosts
                    if slurm_host.host.hostname == host
                ]
                if not hosts_to_check:
                    raise HTTPException(status_code=404, detail=f"Host '{host}' not found")
            else:
                hosts_to_check = manager.slurm_hosts

            fetch_states = {}
            for slurm_host in hosts_to_check:
                hostname = slurm_host.host.hostname
                state = cache.get_host_fetch_state(hostname)
                if not state:
                    fetch_states[hostname] = {
                        "status": "never_fetched",
                        "message": "No incremental fetch performed yet for this host",
                    }
                    continue

                last_fetch_utc = datetime.fromisoformat(state["last_fetch_time_utc"])
                time_since_fetch = datetime.now(timezone.utc) - last_fetch_utc.replace(
                    tzinfo=timezone.utc
                )
                fetch_states[hostname] = {
                    "last_fetch_time": state["last_fetch_time"],
                    "last_fetch_time_utc": state["last_fetch_time_utc"],
                    "cluster_timezone": state["cluster_timezone"],
                    "fetch_count": state["fetch_count"],
                    "updated_at": state["updated_at"],
                    "time_since_fetch_seconds": int(time_since_fetch.total_seconds()),
                    "time_since_fetch_human": _format_time_delta(time_since_fetch),
                }

            return {
                "status": "success",
                "fetch_states": fetch_states,
                "incremental_fetch_enabled": True,
                "message": "Fetch state retrieved successfully",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting fetch state: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve fetch state")

    @app.get("/api/hosts", response_model=List[HostInfoWeb])
    async def get_hosts(_authenticated: bool = Depends(verify_api_key_dependency)):
        """Get list of configured Slurm hosts."""
        try:
            manager = get_slurm_manager()
            hosts = []
            for slurm_host in manager.slurm_hosts:
                slurm_defaults_web = None
                if slurm_host.slurm_defaults:
                    slurm_defaults_web = SlurmDefaultsWeb(
                        **slurm_host.slurm_defaults.__dict__
                    )

                hosts.append(
                    HostInfoWeb(
                        hostname=slurm_host.host.hostname,
                        work_dir="[CONFIGURED]",
                        scratch_dir="[CONFIGURED]",
                        slurm_defaults=slurm_defaults_web,
                    )
                )
            return hosts
        except Exception as e:
            logger.error(f"Error getting hosts: {e}")
            raise HTTPException(status_code=500, detail=sanitize_error_message(e))

    @app.get("/api/partitions", response_model=List[PartitionStatusResponse])
    async def get_partitions(
        host: Optional[str] = Query(None, description="Specific host to query"),
        force_refresh: bool = Query(
            False, description="Force refresh from Slurm, bypassing cache"
        ),
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Get partition resource state across hosts."""
        try:
            manager = get_slurm_manager()

            if host:
                host = InputSanitizer.sanitize_hostname(host)
                slurm_hosts = [
                    slurm_host
                    for slurm_host in manager.slurm_hosts
                    if slurm_host.host.hostname == host
                ]
                if not slurm_hosts:
                    raise HTTPException(status_code=404, detail="Host not found")
            else:
                slurm_hosts = manager.slurm_hosts

            start = time.perf_counter()

            async def fetch_host_partitions(slurm_host):
                hostname = slurm_host.host.hostname
                try:
                    conn = await _run_in_executor(
                        executor, manager._get_connection, slurm_host.host
                    )
                    partitions, cached, cache_age, stale = await _run_in_executor(
                        executor,
                        manager.slurm_client.get_partition_state,
                        conn,
                        hostname,
                        force_refresh,
                    )

                    partition_web = []
                    for partition in partitions:
                        gpu_types = None
                        if partition.gpu_types:
                            gpu_types = {
                                gpu_type: {
                                    "total": usage["total"],
                                    "used": usage["used"],
                                }
                                for gpu_type, usage in partition.gpu_types.items()
                            }

                        partition_web.append(
                            PartitionResourcesWeb(
                                partition=partition.name,
                                availability=partition.availability,
                                states=sorted(partition.states),
                                nodes_total=partition.nodes_total,
                                cpus_alloc=partition.cpus_alloc,
                                cpus_idle=partition.cpus_idle,
                                cpus_other=partition.cpus_other,
                                cpus_total=partition.cpus_total,
                                gpus_total=partition.gpus_total,
                                gpus_used=partition.gpus_used,
                                gpus_idle=partition.gpus_idle,
                                gpu_types=gpu_types,
                            )
                        )

                    if cached:
                        cache_age_seconds = int(cache_age)
                        updated_at = (
                            datetime.now(timezone.utc) - timedelta(seconds=cache_age)
                        ).isoformat()
                    else:
                        cache_age_seconds = None
                        updated_at = datetime.now(timezone.utc).isoformat()

                    return PartitionStatusResponse(
                        hostname=hostname,
                        partitions=partition_web,
                        query_time=f"{time.perf_counter() - start:.3f}s",
                        cached=cached,
                        stale=stale,
                        cache_age_seconds=cache_age_seconds,
                        updated_at=updated_at,
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch partitions for {hostname}: {e}")
                    return PartitionStatusResponse(
                        hostname=hostname,
                        partitions=[],
                        query_time=f"{time.perf_counter() - start:.3f}s",
                        error=sanitize_error_message(e),
                    )

            return await asyncio.gather(
                *(fetch_host_partitions(slurm_host) for slurm_host in slurm_hosts)
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting partition state: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to retrieve partition state"
            )
