"""Tests for notification service provider import robustness."""

import pytest


@pytest.mark.unit
def test_notification_service_initializes_without_optional_providers():
    """Service should initialize even when optional APNs/WebPush deps are absent."""
    from ssync.notifications.service import NotificationService

    service = NotificationService()
    assert isinstance(service.enabled, bool)
