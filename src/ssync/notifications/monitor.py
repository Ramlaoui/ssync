from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Set

from ..job_data_manager import get_job_data_manager
from ..models.job import JobState
from ..utils.async_helpers import create_task
from ..utils.logging import setup_logger
from .service import JobNotificationEvent, get_notification_service

logger = setup_logger(__name__)

_notification_task: Optional[asyncio.Task] = None
_notification_lock = asyncio.Lock()


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None


def _is_recent_terminal(job, window_seconds: int) -> bool:
    end_time = _parse_time(getattr(job, "end_time", None))
    if not end_time:
        return False
    return end_time >= datetime.now() - timedelta(seconds=window_seconds)


async def notification_monitor_loop():
    service = get_notification_service()
    if not service.enabled:
        logger.info("Notification monitor disabled (no providers configured)")
        return

    job_data_manager = get_job_data_manager()
    job_states: Dict[str, str] = {}
    notified_terminal_jobs: Dict[str, tuple[str, float]] = {}

    fast_interval = int(os.getenv("SSYNC_NOTIFICATION_FAST_INTERVAL", "15"))
    full_interval = int(os.getenv("SSYNC_NOTIFICATION_FULL_INTERVAL", "60"))
    recent_window = int(os.getenv("SSYNC_NOTIFICATION_RECENT_SECONDS", "600"))
    notified_ttl = int(os.getenv("SSYNC_NOTIFICATION_TTL_SECONDS", "86400"))

    terminal_states: Set[str] = {
        JobState.COMPLETED.value,
        JobState.FAILED.value,
        JobState.CANCELLED.value,
        JobState.TIMEOUT.value,
    }

    last_full_update = 0.0

    logger.info("Notification monitor started")
    try:
        while True:
            await asyncio.sleep(fast_interval)

            current_time = asyncio.get_event_loop().time()
            time_since_full = current_time - last_full_update

            # Clean expired notification markers
            if notified_terminal_jobs:
                expired_keys = [
                    key
                    for key, (_, ts) in notified_terminal_jobs.items()
                    if (current_time - ts) > notified_ttl
                ]
                for key in expired_keys:
                    notified_terminal_jobs.pop(key, None)

            if time_since_full >= full_interval:
                all_jobs = await job_data_manager.fetch_all_jobs(
                    hostname=None,
                    limit=500,
                    active_only=False,
                    since="1d",
                )
                last_full_update = current_time
            else:
                all_jobs = await job_data_manager.fetch_all_jobs(
                    hostname=None,
                    limit=500,
                    active_only=True,
                )

            current_job_ids = set()
            pending_notifications: list[JobNotificationEvent] = []

            def already_notified(job_key: str, state_value: str) -> bool:
                entry = notified_terminal_jobs.get(job_key)
                return bool(entry and entry[0] == state_value)

            def mark_notified(job_key: str, state_value: str) -> None:
                notified_terminal_jobs[job_key] = (state_value, current_time)

            for job in all_jobs:
                job_key = f"{job.hostname}:{job.job_id}"
                current_job_ids.add(job_key)

                state_value = (
                    job.state.value if hasattr(job.state, "value") else job.state
                )
                is_new = job_key not in job_states
                old_state_value = job_states.get(job_key)
                state_changed = not is_new and old_state_value != state_value

                job_states[job_key] = state_value

                if state_value in terminal_states:
                    should_notify = False
                    if state_changed:
                        should_notify = True
                    elif is_new and _is_recent_terminal(job, recent_window):
                        should_notify = True

                    if should_notify and not already_notified(job_key, state_value):
                        pending_notifications.append(
                            JobNotificationEvent(
                                job_id=job.job_id,
                                job_name=job.name or f"Job {job.job_id}",
                                hostname=job.hostname,
                                state=state_value,
                                old_state=old_state_value,
                                user=job.user,
                            )
                        )
                        mark_notified(job_key, state_value)

            # Detect jobs that disappeared (completed or removed)
            completed_jobs = set(job_states.keys()) - current_job_ids
            for job_key in completed_jobs:
                hostname, job_id = job_key.split(":", 1)
                try:
                    completed_job_data = await job_data_manager.fetch_all_jobs(
                        hostname=hostname, job_ids=[job_id], limit=1
                    )
                    if completed_job_data:
                        completed_job = completed_job_data[0]
                        state_value = (
                            completed_job.state.value
                            if hasattr(completed_job.state, "value")
                            else completed_job.state
                        )
                        if state_value in terminal_states and not already_notified(
                            job_key, state_value
                        ):
                            pending_notifications.append(
                                JobNotificationEvent(
                                    job_id=job_id,
                                    job_name=completed_job.name or f"Job {job_id}",
                                    hostname=hostname,
                                    state=state_value,
                                    old_state=None,
                                    user=completed_job.user,
                                )
                            )
                            mark_notified(job_key, state_value)
                except Exception as exc:
                    logger.debug(
                        f"Notification monitor failed to fetch completed job {job_id}: {exc}"
                    )

                job_states.pop(job_key, None)

            if pending_notifications:
                await service.send_job_notifications(pending_notifications)

    except asyncio.CancelledError:
        logger.info("Notification monitor cancelled")
    except Exception as exc:
        logger.error(f"Notification monitor error: {exc}")


async def start_notification_monitor():
    global _notification_task
    async with _notification_lock:
        if _notification_task is None or _notification_task.done():
            _notification_task = create_task(
                notification_monitor_loop(), name="notification_monitor"
            )


async def stop_notification_monitor():
    global _notification_task
    if _notification_task and not _notification_task.done():
        _notification_task.cancel()
        try:
            await _notification_task
        except asyncio.CancelledError:
            pass
    _notification_task = None
