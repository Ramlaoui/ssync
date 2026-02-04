from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

from ..cache import get_cache
from ..models.job import JobState
from ..utils.config import config
from ..utils.logging import setup_logger
from .apns import APNsClient
from .webpush import WebPushClient

logger = setup_logger(__name__)


TERMINAL_STATES = {
    JobState.COMPLETED.value,
    JobState.FAILED.value,
    JobState.CANCELLED.value,
    JobState.TIMEOUT.value,
}


@dataclass(frozen=True)
class JobNotificationEvent:
    job_id: str
    job_name: str
    hostname: str
    state: str
    old_state: Optional[str] = None
    user: Optional[str] = None


class NotificationService:
    """Notification dispatch service for job state changes."""

    def __init__(self) -> None:
        self.settings = config.notification_settings
        self._apns_client: Optional[APNsClient] = None
        self._webpush_client: Optional[WebPushClient] = None
        self._send_semaphore = asyncio.Semaphore(10)

        if self.settings.enabled and self.settings.is_apns_configured():
            self._apns_client = APNsClient(
                key_id=self.settings.apns_key_id,
                team_id=self.settings.apns_team_id,
                bundle_id=self.settings.apns_bundle_id,
                private_key=self.settings.apns_private_key,
                use_sandbox=self.settings.apns_use_sandbox,
                timeout_seconds=self.settings.apns_timeout_seconds,
            )
        if self.settings.enabled and self.settings.is_webpush_configured():
            self._webpush_client = WebPushClient(
                vapid_public_key=self.settings.webpush_vapid_public_key,
                vapid_private_key=self.settings.webpush_vapid_private_key,
                vapid_subject=self.settings.webpush_vapid_subject,
            )
        if self.settings.enabled and not (self._apns_client or self._webpush_client):
            logger.warning("Notifications enabled but no providers are configured")

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.enabled and (self._apns_client or self._webpush_client)
        )

    async def send_job_notifications(
        self, events: Iterable[JobNotificationEvent]
    ) -> int:
        if not self.enabled:
            return 0

        events = list(events)
        if not events:
            return 0

        cache = get_cache()
        devices = cache.list_notification_devices(
            platform="ios",
            environment="sandbox" if self.settings.apns_use_sandbox else "production",
            bundle_id=self.settings.apns_bundle_id,
            enabled_only=True,
        )
        subscriptions = cache.list_webpush_subscriptions(enabled_only=True)

        devices_by_key: dict[str, list[dict]] = {}
        for device in devices:
            devices_by_key.setdefault(device["api_key_hash"], []).append(device)

        subs_by_key: dict[str, list[dict]] = {}
        for sub in subscriptions:
            subs_by_key.setdefault(sub["api_key_hash"], []).append(sub)

        all_keys = set(devices_by_key.keys()) | set(subs_by_key.keys())
        total_sent = 0

        for api_key_hash in all_keys:
            preferences = cache.get_notification_preferences(api_key_hash=api_key_hash)
            filtered_events = self._filter_events(events, preferences)
            if not filtered_events:
                continue

            for event in filtered_events:
                payload = self._build_payload(event)
                total_sent += await self._send_payload_to_devices(
                    payload, devices_by_key.get(api_key_hash, [])
                )
                total_sent += await self._send_payload_to_webpush(
                    payload, subs_by_key.get(api_key_hash, [])
                )

        return total_sent

    async def send_test_notification(
        self, *, title: str, body: str, token: Optional[str] = None
    ) -> int:
        if not self.enabled:
            return 0

        payload = {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
                "category": "JOB_NOTIFICATION",
                "thread-id": "ssync-test",
            },
            "timestamp": int(time.time()),
        }

        sent = 0
        if token:
            device = {"device_token": token, "api_key_hash": "manual"}
            sent += await self._send_payload_to_devices(payload, [device])
            return sent

        cache = get_cache()
        devices = cache.list_notification_devices(
            platform="ios",
            environment="sandbox" if self.settings.apns_use_sandbox else "production",
            bundle_id=self.settings.apns_bundle_id,
            enabled_only=True,
        )
        if devices:
            sent += await self._send_payload_to_devices(payload, devices)

        subscriptions = cache.list_webpush_subscriptions(enabled_only=True)
        if subscriptions:
            sent += await self._send_payload_to_webpush(payload, subscriptions)

        return sent

    def _build_payload(self, event: JobNotificationEvent) -> dict:
        title, body = self._build_message(event)
        return {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
                "category": "JOB_NOTIFICATION",
                "thread-id": f"job-{event.job_id}",
            },
            "title": title,
            "body": body,
            "type": "job_notification",
            "job_id": event.job_id,
            "hostname": event.hostname,
            "state": event.state,
            "old_state": event.old_state,
            "job_name": event.job_name,
            "user": event.user,
            "timestamp": int(time.time()),
        }

    def _build_message(self, event: JobNotificationEvent) -> tuple[str, str]:
        state_label = event.state
        if event.state == JobState.COMPLETED.value:
            state_label = "completed"
        elif event.state == JobState.FAILED.value:
            state_label = "failed"
        elif event.state == JobState.CANCELLED.value:
            state_label = "cancelled"
        elif event.state == JobState.TIMEOUT.value:
            state_label = "timed out"

        title = f"Job {state_label}"
        body = f"{event.job_name} ({event.job_id}) on {event.hostname}"
        return title, body

    def _filter_events(
        self, events: Iterable[JobNotificationEvent], preferences: dict
    ) -> List[JobNotificationEvent]:
        if not preferences.get("enabled", True):
            return []

        allowed_states = preferences.get("allowed_states")
        muted_job_ids = set(preferences.get("muted_job_ids") or [])
        muted_hosts = set(preferences.get("muted_hosts") or [])
        muted_patterns = [
            p.lower() for p in preferences.get("muted_job_name_patterns") or []
        ]
        allowed_users = set(preferences.get("allowed_users") or [])

        if allowed_states is None:
            allowed_states = TERMINAL_STATES

        filtered: List[JobNotificationEvent] = []
        for event in events:
            if allowed_states is not None and event.state not in allowed_states:
                continue
            if event.job_id in muted_job_ids:
                continue
            if event.hostname in muted_hosts:
                continue
            if allowed_users and event.user not in allowed_users:
                continue
            if muted_patterns and event.job_name:
                name = event.job_name.lower()
                if any(pattern in name for pattern in muted_patterns):
                    continue
            filtered.append(event)

        return filtered

    async def _send_payload_to_devices(self, payload: dict, devices: List[dict]) -> int:
        if not self._apns_client or not devices:
            return 0

        cache = get_cache()

        async def send_one(device: dict):
            async with self._send_semaphore:
                success, reason, status = await self._apns_client.send(
                    device_token=device["device_token"],
                    payload=payload,
                )
            return device, success, reason, status

        tasks = [asyncio.create_task(send_one(device)) for device in devices]
        if not tasks:
            return 0

        results = await asyncio.gather(*tasks, return_exceptions=True)
        sent = 0
        for result in results:
            if isinstance(result, Exception):
                continue
            device, success, reason, status = result
            if success:
                sent += 1
                continue
            if status in {400, 410} and reason in {"BadDeviceToken", "Unregistered"}:
                cache.remove_notification_device(
                    api_key_hash=device["api_key_hash"],
                    device_token=device["device_token"],
                )

        return sent

    async def _send_payload_to_webpush(
        self, payload: dict, subscriptions: List[dict]
    ) -> int:
        if not self._webpush_client or not subscriptions:
            return 0

        cache = get_cache()

        async def send_one(subscription: dict):
            async with self._send_semaphore:
                success, reason, status = await self._webpush_client.send(
                    endpoint=subscription["endpoint"],
                    p256dh=subscription["p256dh"],
                    auth=subscription["auth"],
                    payload=payload,
                )
            return subscription, success, reason, status

        tasks = [asyncio.create_task(send_one(sub)) for sub in subscriptions]
        if not tasks:
            return 0

        results = await asyncio.gather(*tasks, return_exceptions=True)
        sent = 0
        for result in results:
            if isinstance(result, Exception):
                continue
            subscription, success, reason, status = result
            if success:
                sent += 1
                continue
            if status in {404, 410}:
                cache.remove_webpush_subscription(
                    api_key_hash=subscription["api_key_hash"],
                    endpoint=subscription["endpoint"],
                )

        return sent


_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
