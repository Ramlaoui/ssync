"""Tests for notification service provider import robustness."""

from datetime import datetime, timezone

import pytest

from ssync.models.job import JobInfo, JobState


@pytest.mark.unit
def test_notification_service_initializes_without_optional_providers():
    """Service should initialize even when optional APNs/WebPush deps are absent."""
    from ssync.notifications.service import NotificationService

    service = NotificationService()
    assert isinstance(service.enabled, bool)


@pytest.mark.unit
def test_notification_state_and_event_claim_are_durable(test_cache):
    job = JobInfo(
        job_id="12345",
        name="train",
        state=JobState.PENDING,
        hostname="cluster",
        submit_time=datetime.now(timezone.utc).isoformat(),
    )

    old_state, new_state, is_new = test_cache.record_notification_job_state(
        job_info=job
    )
    assert old_state is None
    assert new_state == "PD"
    assert is_new is True

    running_job = JobInfo(
        **{
            **job.__dict__,
            "state": JobState.RUNNING,
            "start_time": datetime.now(timezone.utc).isoformat(),
        }
    )
    old_state, new_state, is_new = test_cache.record_notification_job_state(
        job_info=running_job
    )
    assert old_state == "PD"
    assert new_state == "R"
    assert is_new is False

    payload = {
        "type": "job_notification",
        "notification_id": "cluster:12345:R:test",
    }
    claimed = test_cache.claim_notification_event(
        notification_id="cluster:12345:R:test",
        job_id="12345",
        hostname="cluster",
        old_state="PD",
        new_state="R",
        changed_at=running_job.start_time,
        job_name="train",
        user="alice",
        payload=payload,
    )
    duplicate = test_cache.claim_notification_event(
        notification_id="cluster:12345:R:test",
        job_id="12345",
        hostname="cluster",
        old_state="PD",
        new_state="R",
        changed_at=running_job.start_time,
        job_name="train",
        user="alice",
        payload=payload,
    )

    assert claimed is True
    assert duplicate is False

    test_cache.mark_notification_event_sent(
        notification_id="cluster:12345:R:test",
        sent_count=2,
    )
    event = test_cache.get_notification_event(
        notification_id="cluster:12345:R:test"
    )
    assert event["status"] == "sent"
    assert event["sent_count"] == 2
    assert event["payload"] == payload


@pytest.mark.unit
def test_notification_device_registration_records_contract(test_cache):
    test_cache.upsert_notification_device(
        api_key_hash="key",
        device_token="ExponentPushToken[abc123]",
        platform="ios",
        token_type="expo",
        client_type="expo",
        payload_format="expo",
        device_id="device-1",
    )

    devices = test_cache.list_notification_devices(enabled_only=True)
    assert devices == [
        {
            "api_key_hash": "key",
            "device_token": "ExponentPushToken[abc123]",
            "platform": "ios",
            "token_type": "expo",
            "client_type": "expo",
            "payload_format": "expo",
            "bundle_id": None,
            "environment": None,
            "device_id": "device-1",
            "enabled": True,
            "created_at": devices[0]["created_at"],
            "last_seen": devices[0]["last_seen"],
        }
    ]


@pytest.mark.unit
def test_notification_payload_formats_include_canonical_fields():
    from ssync.notifications.service import JobNotificationEvent, NotificationService

    service = NotificationService()
    event = JobNotificationEvent(
        job_id="12345",
        job_name="train",
        hostname="cluster",
        state="R",
        old_state="PD",
        user="alice",
        changed_at="2026-05-08T20:00:00+00:00",
        notification_id="cluster:12345:R:2026-05-08T20:00:00+00:00",
    )

    canonical = service._build_payload(event, payload_format="canonical")
    expo = service._build_payload(event, payload_format="expo")
    apns = service._build_payload(event, payload_format="apns")

    assert canonical["notification_id"] == event.notification_id
    assert canonical["old_state"] == "PD"
    assert canonical["state"] == "R"
    assert expo["data"]["notification_id"] == event.notification_id
    assert apns["aps"]["category"] == "JOB_NOTIFICATION"
    assert apns["notification_id"] == event.notification_id
