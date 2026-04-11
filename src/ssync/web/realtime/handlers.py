"""Realtime websocket endpoint handlers."""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, List

from fastapi import WebSocket, WebSocketDisconnect

from ...cache import get_cache
from ...models.job import JobState
from ...request_coalescer import get_request_coalescer
from ...utils.async_helpers import create_task
from ...utils.logging import setup_logger
from ..models import JobInfoWeb
from ..status_helpers import group_array_job_tasks
from .monitor import (
    filter_ws_initial_cached_jobs,
    monitor_all_jobs_singleton,
)
from .state import all_jobs_state, job_manager, watcher_manager

logger = setup_logger(__name__)
VerifyWebSocketAPIKey = Callable[[WebSocket], Awaitable[bool]]
GetSlurmManager = Callable[[], Any]


async def _stop_watchers_for_job(actual_job_id: str, hostname: str) -> None:
    try:
        from ...watchers import get_watcher_engine

        engine = get_watcher_engine()
        await engine.stop_watchers_for_job(actual_job_id, hostname)
    except Exception as exc:
        logger.error(f"Error stopping watchers for job {actual_job_id}: {exc}")


async def monitor_job_updates(
    websocket: WebSocket,
    job_id: str,
    hostname: str,
    actual_job_id: str,
    *,
    get_slurm_manager: GetSlurmManager,
):
    """Monitor a specific job for state changes and send updates via WebSocket."""
    try:
        from ...job_data_manager import get_job_data_manager

        get_slurm_manager()
        job_data_manager = get_job_data_manager()
        last_state = None
        last_output_size = 0

        while True:
            await asyncio.sleep(15)

            try:
                jobs = await job_data_manager.fetch_all_jobs(
                    hostname=hostname, job_ids=[actual_job_id], limit=1
                )
                job_info = jobs[0] if jobs else None

                if not job_info:
                    await _stop_watchers_for_job(actual_job_id, hostname)
                    await websocket.send_json(
                        {
                            "type": "job_completed",
                            "job_id": actual_job_id,
                            "hostname": hostname,
                        }
                    )
                    break

                previous_state = last_state
                if job_info.state != previous_state:
                    await websocket.send_json(
                        {
                            "type": "state_change",
                            "job_id": actual_job_id,
                            "hostname": hostname,
                            "old_state": previous_state.value
                            if previous_state
                            else None,
                            "new_state": job_info.state.value,
                            "job": JobInfoWeb.from_job_info(job_info).model_dump(
                                mode="json"
                            ),
                        }
                    )
                    last_state = job_info.state

                    if job_info.state in [
                        JobState.COMPLETED,
                        JobState.FAILED,
                        JobState.CANCELLED,
                        JobState.TIMEOUT,
                        JobState.UNKNOWN,
                    ]:
                        await _stop_watchers_for_job(actual_job_id, hostname)

                    await job_manager.broadcast_job_update(
                        job_id,
                        hostname,
                        {
                            "type": "state_change",
                            "old_state": previous_state.value
                            if previous_state
                            else None,
                            "new_state": job_info.state.value,
                            "job": JobInfoWeb.from_job_info(job_info).model_dump(
                                mode="json"
                            ),
                        },
                    )

                if job_info.state == JobState.RUNNING and job_info.stdout_file:
                    try:
                        output_path = Path(job_info.stdout_file)
                        if output_path.exists():
                            current_size = output_path.stat().st_size
                            if current_size > last_output_size:
                                with open(output_path, "r") as file_obj:
                                    file_obj.seek(last_output_size)
                                    new_content = file_obj.read(10000)
                                    if new_content:
                                        await websocket.send_json(
                                            {
                                                "type": "output_update",
                                                "job_id": actual_job_id,
                                                "hostname": hostname,
                                                "content": new_content,
                                                "truncated": len(new_content) == 10000,
                                            }
                                        )
                                last_output_size = current_size
                    except Exception as exc:
                        logger.debug(
                            f"Could not read output for job {actual_job_id}: {exc}"
                        )

            except Exception as exc:
                logger.error(f"Error monitoring job {actual_job_id}: {exc}")

    except asyncio.CancelledError:
        logger.debug(f"Job monitoring cancelled for {actual_job_id}")
    except Exception as exc:
        logger.error(f"Fatal error in job monitoring for {actual_job_id}: {exc}")


async def send_job_output(
    websocket: WebSocket,
    hostname: str,
    job_id: str,
    *,
    get_slurm_manager: GetSlurmManager,
):
    """Send current job output to the WebSocket."""
    try:
        manager = get_slurm_manager()
        slurm_host = manager.get_host_by_name(hostname)

        output_result = await asyncio.to_thread(
            slurm_host.slurm_client.get_job_output, job_id
        )

        if output_result.success:
            await websocket.send_json(
                {
                    "type": "output",
                    "job_id": job_id,
                    "hostname": hostname,
                    "stdout": output_result.stdout,
                    "stderr": output_result.stderr,
                }
            )
            return

        await websocket.send_json(
            {
                "type": "output_error",
                "job_id": job_id,
                "hostname": hostname,
                "error": output_result.error,
            }
        )

    except Exception as exc:
        logger.error(f"Error sending job output: {exc}")
        await websocket.send_json(
            {
                "type": "output_error",
                "job_id": job_id,
                "hostname": hostname,
                "error": str(exc),
            }
        )


async def websocket_job_handler(
    websocket: WebSocket,
    job_id: str,
    *,
    verify_websocket_api_key: VerifyWebSocketAPIKey,
    get_slurm_manager: GetSlurmManager,
):
    """WebSocket endpoint handler for a specific job."""
    monitor_task = None
    try:
        if not await verify_websocket_api_key(websocket):
            return

        if ":" in job_id:
            hostname, actual_job_id = job_id.split(":", 1)
        else:
            hostname = None
            actual_job_id = job_id

        await job_manager.connect(websocket, job_id)
        try:
            from ...job_data_manager import get_job_data_manager

            get_slurm_manager()
            job_data_manager = get_job_data_manager()
            coalescer = get_request_coalescer()

            if hostname:

                async def fetch_batch(host: str, job_ids: List[str]):
                    return await job_data_manager.fetch_all_jobs(
                        hostname=host, job_ids=job_ids, limit=len(job_ids)
                    )

                job_info = await coalescer.fetch_job(
                    actual_job_id, hostname, fetch_batch
                )
            else:
                all_jobs = await job_data_manager.fetch_all_jobs(
                    hostname=None, job_ids=[actual_job_id], limit=1
                )
                job_info = all_jobs[0] if all_jobs else None
                if job_info:
                    hostname = job_info.hostname

            if job_info:
                await websocket.send_json(
                    {
                        "type": "initial",
                        "job": JobInfoWeb.from_job_info(job_info).model_dump(
                            mode="json"
                        ),
                        "hostname": hostname,
                    }
                )

                if job_info.state in [JobState.RUNNING, JobState.PENDING]:
                    monitor_task = create_task(
                        monitor_job_updates(
                            websocket,
                            job_id,
                            hostname,
                            actual_job_id,
                            get_slurm_manager=get_slurm_manager,
                        )
                    )
                else:
                    logger.info(
                        f"Job {actual_job_id} is already in state {job_info.state}, not starting monitor"
                    )
            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Job {actual_job_id} not found"}
                )
        except Exception as exc:
            logger.error(f"Error fetching initial job data: {exc}", exc_info=True)
            try:
                await websocket.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass

        while True:
            try:
                data = await websocket.receive_text()

                if data == "ping":
                    await websocket.send_text("pong")
                elif data == "get_output":
                    await send_job_output(
                        websocket,
                        hostname,
                        actual_job_id,
                        get_slurm_manager=get_slurm_manager,
                    )

            except WebSocketDisconnect:
                break
            except Exception:
                break

    except Exception as exc:
        logger.error(f"WebSocket job error: {exc}")
    finally:
        job_manager.disconnect(websocket, job_id)
        if monitor_task:
            monitor_task.cancel()


async def websocket_all_jobs_handler(
    websocket: WebSocket,
    *,
    verify_websocket_api_key: VerifyWebSocketAPIKey,
    get_slurm_manager: GetSlurmManager,
    cache_middleware,
):
    """WebSocket endpoint handler for all jobs."""
    try:
        if not await verify_websocket_api_key(websocket):
            return

        await job_manager.connect(websocket)

        try:
            from ...job_data_manager import get_job_data_manager

            manager = get_slurm_manager()
            job_data_manager = get_job_data_manager()
            cache = get_cache()
            all_jobs = []
            since_dt = datetime.now() - timedelta(days=1)
            cached_job_data = cache.get_cached_jobs(
                hostname=None, limit=500, since=since_dt
            )

            if cached_job_data and len(cached_job_data) > 0:
                filtered_cached_jobs = filter_ws_initial_cached_jobs(
                    job_data_manager, cached_job_data
                )
                if filtered_cached_jobs:
                    logger.info(
                        "Using %s filtered cached jobs (from %s raw rows since %s) for WebSocket initial data",
                        len(filtered_cached_jobs),
                        len(cached_job_data),
                        since_dt,
                    )
                    all_jobs = filtered_cached_jobs
                else:
                    logger.info(
                        "Raw cache had %s rows but none were suitable for initial WebSocket data; fetching from Slurm instead",
                        len(cached_job_data),
                    )

            if not all_jobs:
                logger.info(
                    "No suitable cache available, fetching jobs for WebSocket initial data"
                )
                all_jobs = await job_data_manager.fetch_all_jobs(
                    hostname=None,
                    limit=500,
                    active_only=False,
                    since="1d",
                )

            jobs_by_host = {}
            jobs_by_host_objects = {}
            for slurm_host in manager.slurm_hosts:
                hostname = slurm_host.host.hostname
                jobs_by_host[hostname] = []
                jobs_by_host_objects[hostname] = []

            for job in all_jobs:
                if job.hostname not in jobs_by_host:
                    jobs_by_host[job.hostname] = []
                    jobs_by_host_objects[job.hostname] = []

                web_job = JobInfoWeb.from_job_info(job)
                jobs_by_host[job.hostname].append(web_job.model_dump(mode="json"))
                jobs_by_host_objects[job.hostname].append(web_job)

            array_groups_by_host = {}
            for hostname, host_jobs in jobs_by_host_objects.items():
                if host_jobs:
                    _, array_groups = group_array_job_tasks(host_jobs)
                    if array_groups:
                        array_groups_by_host[hostname] = [
                            group.model_dump(mode="json") for group in array_groups
                        ]

            logger.info(
                f"Sending initial WebSocket data: {len(all_jobs)} jobs from {len(jobs_by_host)} hosts with {len(array_groups_by_host)} hosts having array groups"
            )

            await websocket.send_json(
                {
                    "type": "initial",
                    "jobs": jobs_by_host,
                    "total": len(all_jobs),
                    "array_groups": array_groups_by_host,
                }
            )

            async with all_jobs_state.lock:
                all_jobs_state.websockets.add(websocket)

                if (
                    all_jobs_state.monitor_task is None
                    or all_jobs_state.monitor_task.done()
                ):
                    logger.info("Starting singleton all-jobs monitor task")
                    all_jobs_state.monitor_task = create_task(
                        monitor_all_jobs_singleton(
                            get_slurm_manager=get_slurm_manager,
                            cache_middleware=cache_middleware,
                        )
                    )

        except WebSocketDisconnect:
            logger.debug("WebSocket client disconnected during initial data fetch")
            return
        except Exception as exc:
            if not isinstance(exc, WebSocketDisconnect):
                logger.error(f"Error fetching initial jobs data: {exc}", exc_info=True)
            try:
                await websocket.send_json({"type": "error", "message": str(exc)})
            except WebSocketDisconnect:
                pass

        while True:
            try:
                data = await websocket.receive_text()

                try:
                    parsed = json.loads(data)
                    if parsed.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                        logger.debug("Received JSON ping, sent pong response")
                except json.JSONDecodeError:
                    if data == "ping":
                        await websocket.send_text("pong")
                        logger.debug("Received text ping, sent pong response")

            except WebSocketDisconnect:
                break
            except Exception:
                break

    except Exception as exc:
        logger.error(f"WebSocket all jobs error: {exc}")
    finally:
        job_manager.disconnect(websocket)
        all_jobs_state.websockets.discard(websocket)


async def websocket_watchers_handler(
    websocket: WebSocket,
    *,
    verify_websocket_api_key: VerifyWebSocketAPIKey,
):
    """WebSocket endpoint handler for watcher updates."""
    try:
        if not await verify_websocket_api_key(websocket):
            return

        await watcher_manager.connect(websocket)

        cache = get_cache()
        def load_initial_events():
            with cache._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM watcher_events
                    ORDER BY timestamp DESC
                    LIMIT 10
                    """
                )
                columns = [desc[0] for desc in cursor.description]
                events = []
                for row in cursor.fetchall():
                    event_dict = dict(zip(columns, row))
                    if event_dict.get("captured_vars"):
                        event_dict["captured_vars"] = json.loads(
                            event_dict["captured_vars"]
                        )
                    events.append(event_dict)
                return events

        events = await asyncio.to_thread(load_initial_events)
        await websocket.send_json({"type": "initial", "events": events})

        while True:
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")

            except WebSocketDisconnect:
                break
            except Exception:
                break

    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
    finally:
        if websocket in watcher_manager.active_connections:
            watcher_manager.disconnect(websocket)
