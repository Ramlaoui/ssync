from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional

from ..cache import get_cache
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


def _transition_timestamp(job, state_value: str) -> Optional[str]:
    if state_value == JobState.PENDING.value:
        return getattr(job, "submit_time", None)
    if state_value == JobState.RUNNING.value:
        return getattr(job, "start_time", None)
    if state_value in {
        JobState.COMPLETED.value,
        JobState.FAILED.value,
        JobState.CANCELLED.value,
        JobState.TIMEOUT.value,
    }:
        return getattr(job, "end_time", None)
    return None


def _is_recent_transition(job, state_value: str, window_seconds: int) -> bool:
    changed_at = _parse_time(_transition_timestamp(job, state_value))
    if not changed_at:
        return False
    return changed_at >= datetime.now() - timedelta(seconds=window_seconds)


async def notification_monitor_loop():
    service = get_notification_service()
    if not service.enabled:
        logger.info("Notification monitor disabled (no providers configured)")
        return

    job_data_manager = get_job_data_manager()
    cache = get_cache()

    fast_interval = int(os.getenv("SSYNC_NOTIFICATION_FAST_INTERVAL", "15"))
    full_interval = int(os.getenv("SSYNC_NOTIFICATION_FULL_INTERVAL", "60"))
    recent_window = int(os.getenv("SSYNC_NOTIFICATION_RECENT_SECONDS", "600"))

    last_full_update = 0.0

    logger.info("Notification monitor started")
    try:
        while True:
            await asyncio.sleep(fast_interval)

            current_time = asyncio.get_event_loop().time()
            time_since_full = current_time - last_full_update

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

            for job in all_jobs:
                job_key = f"{job.hostname}:{job.job_id}"
                current_job_ids.add(job_key)

                state_value = (
                    job.state.value if hasattr(job.state, "value") else job.state
                )

                old_state_value, _, is_new = cache.record_notification_job_state(
                    job_info=job
                )
                state_changed = old_state_value is not None and old_state_value != state_value
                first_seen_recent = is_new and (
                    _is_recent_terminal(job, recent_window)
                    or _is_recent_transition(job, state_value, recent_window)
                )

                if state_changed or first_seen_recent:
                    pending_notifications.append(
                        JobNotificationEvent(
                            job_id=job.job_id,
                            job_name=job.name or f"Job {job.job_id}",
                            hostname=job.hostname,
                            state=state_value,
                            old_state=old_state_value,
                            user=job.user,
                            changed_at=_transition_timestamp(job, state_value),
                        )
                    )

            if pending_notifications:
                service.enqueue_job_notifications(pending_notifications)

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
