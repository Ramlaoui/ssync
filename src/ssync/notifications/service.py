from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Iterable, List, Optional

from ..cache import get_cache
from ..models.job import JobState
from ..utils.async_helpers import create_task
from ..utils.config import config
from ..utils.logging import setup_logger

if TYPE_CHECKING:
    from .apns import APNsClient
    from .expo import ExpoPushClient
    from .webpush import WebPushClient

logger = setup_logger(__name__)


TERMINAL_STATES = {
    JobState.COMPLETED.value,
    JobState.FAILED.value,
    JobState.CANCELLED.value,
    JobState.TIMEOUT.value,
}


@dataclass
class JobNotificationEvent:
    job_id: str
    job_name: str
    hostname: str
    state: str
    old_state: Optional[str] = None
    user: Optional[str] = None
    changed_at: Optional[str] = None
    notification_id: Optional[str] = None


class NotificationService:
    """Notification dispatch service for job state changes."""

    def __init__(self) -> None:
        self.settings = config.notification_settings
        self._apns_client: Optional[APNsClient] = None
        self._expo_client: Optional[ExpoPushClient] = None
        self._webpush_client: Optional[WebPushClient] = None
        self._send_semaphore = asyncio.Semaphore(10)

        if self.settings.enabled and self.settings.is_apns_configured():
            try:
                from .apns import APNsClient

                self._apns_client = APNsClient(
                    key_id=self.settings.apns_key_id,
                    team_id=self.settings.apns_team_id,
                    bundle_id=self.settings.apns_bundle_id,
                    private_key=self.settings.apns_private_key,
                    use_sandbox=self.settings.apns_use_sandbox,
                    timeout_seconds=self.settings.apns_timeout_seconds,
                )
            except Exception as exc:
                logger.warning(
                    f"APNs provider unavailable; disabling APNs notifications: {exc}"
                )

        if self.settings.enabled:
            try:
                from .expo import ExpoPushClient

                self._expo_client = ExpoPushClient(
                    timeout_seconds=self.settings.apns_timeout_seconds
                )
            except Exception as exc:
                logger.warning(
                    f"Expo push provider unavailable; disabling Expo notifications: {exc}"
                )

        if self.settings.enabled and self.settings.is_webpush_configured():
            try:
                from .webpush import WebPushClient

                self._webpush_client = WebPushClient(
                    vapid_public_key=self.settings.webpush_vapid_public_key,
                    vapid_private_key=self.settings.webpush_vapid_private_key,
                    vapid_subject=self.settings.webpush_vapid_subject,
                )
            except Exception as exc:
                logger.warning(
                    f"Web Push provider unavailable; disabling Web Push notifications: {exc}"
                )
        if self.settings.enabled and not (
            self._apns_client or self._expo_client or self._webpush_client
        ):
            logger.warning("Notifications enabled but no providers are configured")

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.enabled
            and (self._apns_client or self._expo_client or self._webpush_client)
        )

    def provider_status(self) -> dict:
        return {
            "enabled": self.enabled,
            "apns": bool(self._apns_client),
            "expo": bool(self._expo_client),
            "webpush": bool(self._webpush_client),
        }

    async def send_job_notifications(
        self, events: Iterable[JobNotificationEvent]
    ) -> int:
        if not self.enabled:
            return 0

        events = list(events)
        if not events:
            return 0

        cache = get_cache()
        devices = [
            device
            for device in cache.list_notification_devices(
                platform="ios",
                environment="sandbox"
                if self.settings.apns_use_sandbox
                else "production",
                bundle_id=self.settings.apns_bundle_id,
                enabled_only=True,
            )
            if device.get("token_type", "apns") == "apns"
        ]
        expo_devices = [
            device
            for device in cache.list_notification_devices(enabled_only=True)
            if device.get("token_type") == "expo"
            or device.get("payload_format") == "expo"
        ]
        subscriptions = cache.list_webpush_subscriptions(enabled_only=True)

        devices_by_key: dict[str, list[dict]] = {}
        for device in devices:
            devices_by_key.setdefault(device["api_key_hash"], []).append(device)

        expo_devices_by_key: dict[str, list[dict]] = {}
        for device in expo_devices:
            expo_devices_by_key.setdefault(device["api_key_hash"], []).append(device)

        subs_by_key: dict[str, list[dict]] = {}
        for sub in subscriptions:
            subs_by_key.setdefault(sub["api_key_hash"], []).append(sub)

        all_keys = (
            set(devices_by_key.keys())
            | set(expo_devices_by_key.keys())
            | set(subs_by_key.keys())
        )
        total_sent = 0

        for api_key_hash in all_keys:
            preferences = cache.get_notification_preferences(api_key_hash=api_key_hash)
            filtered_events = self._filter_events(events, preferences)
            if not filtered_events:
                continue

            for event in filtered_events:
                payload = self._build_payload(event, payload_format="apns")
                total_sent += await self._send_payload_to_devices(
                    payload, devices_by_key.get(api_key_hash, [])
                )
                expo_payload = self._build_payload(event, payload_format="expo")
                total_sent += await self._send_payload_to_expo(
                    expo_payload, expo_devices_by_key.get(api_key_hash, [])
                )
                webpush_payload = self._build_payload(event, payload_format="webpush")
                total_sent += await self._send_payload_to_webpush(
                    webpush_payload, subs_by_key.get(api_key_hash, [])
                )

        return total_sent

    def enqueue_job_notifications(self, events: Iterable[JobNotificationEvent]) -> None:
        """Claim and dispatch events in the background without blocking callers."""
        if not self.enabled:
            return

        events = [event for event in events if self._claim_event(event)]
        if not events:
            return

        create_task(
            self._dispatch_claimed_events(events),
            name="send_job_notifications",
        )

    def enqueue_job_transition(
        self,
        *,
        job_id: str,
        job_name: str,
        hostname: str,
        new_state: str,
        old_state: Optional[str] = None,
        user: Optional[str] = None,
        changed_at: Optional[str] = None,
    ) -> None:
        self.enqueue_job_notifications(
            [
                JobNotificationEvent(
                    job_id=job_id,
                    job_name=job_name,
                    hostname=hostname,
                    state=new_state,
                    old_state=old_state,
                    user=user,
                    changed_at=changed_at,
                )
            ]
        )

    def enqueue_job_info_transition(
        self, job_info, old_state: Optional[str] = None
    ) -> None:
        new_state = _state_value(getattr(job_info, "state", None))
        if not new_state:
            return

        self.enqueue_job_transition(
            job_id=job_info.job_id,
            job_name=job_info.name or f"Job {job_info.job_id}",
            hostname=job_info.hostname,
            new_state=new_state,
            old_state=old_state,
            user=job_info.user,
            changed_at=job_transition_timestamp(job_info, new_state),
        )

    async def _dispatch_claimed_events(
        self, events: list[JobNotificationEvent]
    ) -> None:
        cache = get_cache()
        for event in events:
            try:
                sent_count = await self.send_job_notifications([event])
                last_error = None
            except Exception as exc:
                sent_count = 0
                last_error = str(exc)
                logger.error(f"Notification dispatch failed: {exc}")

            if event.notification_id:
                cache.mark_notification_event_sent(
                    notification_id=event.notification_id,
                    sent_count=sent_count,
                    last_error=last_error,
                )

    def _claim_event(self, event: JobNotificationEvent) -> bool:
        event.notification_id = event.notification_id or self._notification_id(event)
        event.changed_at = event.changed_at or datetime.now().isoformat()
        payload = self._build_payload(event, payload_format="canonical")
        return get_cache().claim_notification_event(
            notification_id=event.notification_id,
            job_id=event.job_id,
            hostname=event.hostname,
            old_state=event.old_state,
            new_state=event.state,
            changed_at=event.changed_at,
            job_name=event.job_name,
            user=event.user,
            payload=payload,
        )

    def _notification_id(self, event: JobNotificationEvent) -> str:
        changed_at = event.changed_at or datetime.now().isoformat()
        return f"{event.hostname}:{event.job_id}:{event.state}:{changed_at}"

    async def send_test_notification(
        self,
        *,
        title: str,
        body: str,
        token: Optional[str] = None,
        token_type: str = "apns",
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
            if token_type == "expo":
                return await self._send_payload_to_expo(
                    {
                        "title": title,
                        "body": body,
                        "sound": "default",
                        "data": {"type": "test_notification"},
                    },
                    [
                        {
                            "device_token": token,
                            "api_key_hash": "manual",
                        }
                    ],
                )

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

        expo_devices = [
            device
            for device in cache.list_notification_devices(enabled_only=True)
            if device.get("token_type") == "expo"
            or device.get("payload_format") == "expo"
        ]
        if expo_devices:
            sent += await self._send_payload_to_expo(
                {
                    "title": title,
                    "body": body,
                    "sound": "default",
                    "data": {"type": "test_notification"},
                },
                expo_devices,
            )

        subscriptions = cache.list_webpush_subscriptions(enabled_only=True)
        if subscriptions:
            sent += await self._send_payload_to_webpush(payload, subscriptions)

        return sent

    def _build_payload(
        self, event: JobNotificationEvent, *, payload_format: str
    ) -> dict:
        title, body = self._build_message(event)
        canonical = {
            "title": title,
            "body": body,
            "type": "job_notification",
            "notification_id": event.notification_id,
            "job_id": event.job_id,
            "hostname": event.hostname,
            "state": event.state,
            "old_state": event.old_state,
            "changed_at": event.changed_at,
            "job_name": event.job_name,
            "user": event.user,
            "timestamp": int(time.time()),
        }

        if payload_format == "canonical":
            return canonical

        if payload_format == "webpush":
            return canonical

        if payload_format == "expo":
            return {
                "title": title,
                "body": body,
                "sound": "default",
                "data": canonical,
            }

        return {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
                "category": "JOB_NOTIFICATION",
                "thread-id": f"job-{event.job_id}",
            },
            **canonical,
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

    async def _send_payload_to_expo(self, payload: dict, devices: List[dict]) -> int:
        if not self._expo_client or not devices:
            return 0

        cache = get_cache()

        async def send_one(device: dict):
            async with self._send_semaphore:
                success, reason, status = await self._expo_client.send(
                    token=device["device_token"],
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
            if status == 400 and reason in {"DeviceNotRegistered", "InvalidCredentials"}:
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


def _state_value(state) -> Optional[str]:
    if state is None:
        return None
    return state.value if hasattr(state, "value") else str(state)


def job_transition_timestamp(job_info, state_value: str) -> Optional[str]:
    if state_value == JobState.PENDING.value:
        return getattr(job_info, "submit_time", None)
    if state_value == JobState.RUNNING.value:
        return getattr(job_info, "start_time", None)
    if state_value in TERMINAL_STATES:
        return getattr(job_info, "end_time", None)
    return None
