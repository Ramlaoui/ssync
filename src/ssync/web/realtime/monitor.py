"""Realtime broadcast and all-jobs monitor helpers."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Set

from ...models.job import JobInfo, JobState
from ...utils.logging import setup_logger
from ..models import JobInfoWeb
from .state import (
    all_jobs_state,
    broadcast_json_to_websockets,
    job_manager,
)

logger = setup_logger(__name__)
GetSlurmManager = Callable[[], Any]


def filter_ws_initial_cached_jobs(job_data_manager, cached_job_data) -> list:
    """Filter raw cache rows before sending initial all-jobs websocket state."""
    if not cached_job_data:
        return []

    placeholder_ttl = float(
        getattr(job_data_manager, "_placeholder_active_cache_ttl_seconds", 90)
    )
    placeholder_cutoff = datetime.now() - timedelta(seconds=placeholder_ttl)
    filtered_jobs = []

    for cached_data in cached_job_data:
        job_info = getattr(cached_data, "job_info", None)
        if not job_info:
            continue

        is_placeholder = job_data_manager._is_launch_placeholder_job(job_info)
        if is_placeholder:
            if not getattr(cached_data, "is_active", False):
                continue
            cached_at = getattr(cached_data, "cached_at", None)
            if cached_at and cached_at < placeholder_cutoff:
                continue

        filtered_jobs.append(job_info)

    return filtered_jobs


def serialize_job_for_ws(job: JobInfo) -> dict[str, Any]:
    """Serialize a job once for websocket delivery with consistency checks."""
    original_job_id = job.job_id
    original_hostname = job.hostname
    job_dict = JobInfoWeb.from_job_info(job).model_dump(mode="json")

    if job.job_id != original_job_id:
        raise ValueError(
            f"job mutated during websocket serialization: was {original_job_id}, now {job.job_id}"
        )

    if job_dict["job_id"] != original_job_id:
        raise ValueError(
            "job_id mismatch during websocket serialization: "
            f"original={original_job_id} serialized={job_dict['job_id']} "
            f"hostname={original_hostname}"
        )

    return job_dict


async def _fetch_completed_job_updates(
    job_data_manager, completed_job_keys: Set[str]
) -> list[dict[str, Any]]:
    """Resolve disappeared jobs in host-sized batches for websocket completion events."""
    if not completed_job_keys:
        return []

    job_ids_by_host: dict[str, list[str]] = {}
    sorted_job_keys = sorted(completed_job_keys)
    for job_key in sorted_job_keys:
        hostname, job_id = job_key.split(":", 1)
        job_ids_by_host.setdefault(hostname, []).append(job_id)

    fetch_tasks = {
        hostname: asyncio.create_task(
            job_data_manager.fetch_all_jobs(
                hostname=hostname,
                job_ids=job_ids,
                limit=len(job_ids),
            ),
            name=f"fetch_completed_jobs_{hostname}",
        )
        for hostname, job_ids in job_ids_by_host.items()
    }

    jobs_by_host: dict[str, dict[str, JobInfo]] = {}
    for hostname, task in fetch_tasks.items():
        try:
            jobs_by_host[hostname] = {
                job.job_id: job for job in await task if getattr(job, "job_id", None)
            }
        except Exception as exc:
            logger.debug(
                f"Skipping completed job refresh for host {hostname} after fetch failure: {exc}"
            )
            jobs_by_host[hostname] = {}

    updates = []
    for job_key in sorted_job_keys:
        hostname, job_id = job_key.split(":", 1)
        completed_job = jobs_by_host.get(hostname, {}).get(job_id)
        if not completed_job:
            logger.debug(
                f"Skipping job_completed update for {job_id} - no job data available"
            )
            continue

        try:
            updates.append(
                {
                    "type": "job_completed",
                    "job_id": job_id,
                    "hostname": hostname,
                    "job": serialize_job_for_ws(completed_job),
                }
            )
        except Exception as exc:
            logger.debug(
                f"Skipping job_completed update for {job_id} - serialization failed: {exc}"
            )

    return updates


async def broadcast_job_state(
    job_info, previous_state: Optional[JobState] = None
) -> None:
    """Broadcast a single realtime job update to websocket clients."""
    await job_manager.broadcast_job_update(
        job_info.job_id,
        job_info.hostname,
        {
            "type": "job_update",
            "old_state": previous_state.value if previous_state else None,
            "new_state": job_info.state.value,
            "job": JobInfoWeb.from_job_info(job_info).model_dump(mode="json"),
        },
    )


def _legacy_launch_progress_payload(
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    stage = payload.get("stage")
    if not stage:
        return None

    if stage.startswith("sync_") or stage == "accepted":
        legacy_stage = "syncing"
    elif stage.startswith("submit_") or stage.startswith("setup_"):
        legacy_stage = "submitting"
    elif stage == "completed":
        legacy_stage = "completed"
    elif stage == "failed":
        legacy_stage = "failed"
    else:
        return None

    legacy_payload: Dict[str, Any] = {
        "type": "launch_progress",
        "launch_id": payload["launch_id"],
        "hostname": payload["hostname"],
        "stage": legacy_stage,
        "message": payload.get("message", ""),
    }
    if payload.get("job_id") is not None:
        legacy_payload["job_id"] = payload["job_id"]
    return legacy_payload


async def broadcast_launch_event_to_all_jobs(payload: Dict[str, Any]) -> None:
    disconnected = []
    for connection in job_manager.all_jobs_connections:
        try:
            await connection.send_json(payload)
            legacy_payload = _legacy_launch_progress_payload(payload)
            if legacy_payload is not None:
                await connection.send_json(legacy_payload)
        except Exception:
            disconnected.append(connection)
    for websocket in disconnected:
        job_manager.disconnect(websocket)


async def _verify_active_snapshot_cache(
    all_jobs,
    manager,
    active_fetch_limit: Optional[int],
    cache_middleware,
):
    """Verify cached active jobs against a full active snapshot."""
    if active_fetch_limit and len(all_jobs) >= active_fetch_limit:
        logger.debug(
            "Skipping active snapshot cache verification because the result hit the fetch limit"
        )
        return

    current_job_ids = {
        slurm_host.host.hostname: [] for slurm_host in manager.slurm_hosts
    }
    for job in all_jobs:
        current_job_ids.setdefault(job.hostname, []).append(job.job_id)

    await cache_middleware._verify_and_update_cache(current_job_ids)


async def monitor_all_jobs_singleton(
    *,
    get_slurm_manager: GetSlurmManager,
    cache_middleware,
):
    """Single background task that broadcasts to all connected all-jobs clients."""
    try:
        from ...job_data_manager import get_job_data_manager

        manager = get_slurm_manager()
        job_data_manager = get_job_data_manager()
        job_states = {}
        last_full_update = 0
        fast_interval = 15
        full_interval = 60
        active_fetch_limit = 500

        while True:
            await asyncio.sleep(fast_interval)

            if not all_jobs_state.websockets:
                logger.info("No WebSocket clients connected, stopping monitor task")
                break

            try:
                logger.debug(
                    f"Monitor task running - {len(all_jobs_state.websockets)} clients connected"
                )

                current_time = asyncio.get_event_loop().time()
                time_since_full = current_time - last_full_update
                if time_since_full >= full_interval:
                    logger.debug(
                        "Performing full job update (active + recent completed)"
                    )
                    all_jobs = await job_data_manager.fetch_all_jobs(
                        hostname=None,
                        limit=active_fetch_limit,
                        active_only=False,
                        since="1d",
                    )
                    last_full_update = current_time
                    did_fetch_active_snapshot = False
                else:
                    logger.debug("Performing fast job update (active only)")
                    all_jobs = await job_data_manager.fetch_all_jobs(
                        hostname=None,
                        limit=active_fetch_limit,
                        active_only=True,
                    )
                    did_fetch_active_snapshot = True

                logger.debug(f"Monitor task fetched {len(all_jobs)} jobs")

                if did_fetch_active_snapshot:
                    await _verify_active_snapshot_cache(
                        all_jobs,
                        manager,
                        active_fetch_limit,
                        cache_middleware,
                    )

                current_job_ids = set()
                updates = []
                new_job_count = 0
                state_change_count = 0
                running_refresh_count = 0

                for job in all_jobs:
                    job_key = f"{job.hostname}:{job.job_id}"
                    current_job_ids.add(job_key)

                    if not job.job_id:
                        logger.error(f"Job object missing job_id: {job}")
                        continue

                    is_new = job_key not in job_states
                    state_changed = not is_new and job_states[job_key] != job.state
                    is_running = job.state == JobState.RUNNING

                    if is_new or state_changed or is_running:
                        old_state = job_states.get(job_key)
                        job_states[job_key] = job.state
                        if is_new:
                            new_job_count += 1
                        elif state_changed:
                            state_change_count += 1
                        else:
                            running_refresh_count += 1

                        new_state_value = (
                            job.state.value
                            if hasattr(job.state, "value")
                            else job.state
                        )
                        old_state_value = (
                            old_state.value
                            if old_state is not None and hasattr(old_state, "value")
                            else old_state
                        )

                        try:
                            job_dict = serialize_job_for_ws(job)
                        except Exception as exc:
                            logger.error(
                                f"Skipping websocket job update for {job.job_id} on {job.hostname}: {exc}"
                            )
                            continue

                        updates.append(
                            {
                                "type": "job_update",
                                "job_id": job.job_id,
                                "hostname": job.hostname,
                                "old_state": old_state_value,
                                "new_state": new_state_value,
                                "job": job_dict,
                            }
                        )

                completed_jobs = set(job_states.keys()) - current_job_ids
                completed_updates = await _fetch_completed_job_updates(
                    job_data_manager, completed_jobs
                )
                updates.extend(completed_updates)
                for job_key in completed_jobs:
                    del job_states[job_key]

                if updates:
                    logger.info(
                        "Broadcasting %s updates (%s new, %s state changes, %s running refreshes, %s completed) to %s clients",
                        len(updates),
                        new_job_count,
                        state_change_count,
                        running_refresh_count,
                        len(completed_updates),
                        len(all_jobs_state.websockets),
                    )

                    message = {
                        "type": "batch_update",
                        "updates": updates,
                        "timestamp": datetime.now().isoformat(),
                    }

                    disconnected = await broadcast_json_to_websockets(
                        all_jobs_state.websockets, message
                    )
                    all_jobs_state.websockets -= disconnected

            except Exception as exc:
                logger.error(f"Error in monitor loop: {exc}")

    except asyncio.CancelledError:
        logger.info("Monitor task cancelled")
    except Exception as exc:
        logger.error(f"Fatal error in monitor task: {exc}")
