"""Notification API route registration."""

import hashlib
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException

from ...cache import get_cache
from ...notifications import get_notification_service
from ...utils.logging import setup_logger
from ..models import (
    NotificationDeviceRegistration,
    NotificationPreferences,
    NotificationPreferencesPatch,
    NotificationTestRequest,
    WebPushSubscriptionRegistration,
    WebPushUnsubscribeRequest,
)
from ..security import (
    InputSanitizer,
    normalize_device_token,
    normalize_environment,
    sanitize_notification_preferences,
)

logger = setup_logger(__name__)


def _api_key_hash(api_key: Optional[str]) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest() if api_key else "public"


def register_notification_routes(
    app: FastAPI,
    *,
    get_api_key_dependency,
    verify_api_key_dependency,
    notification_settings,
) -> None:
    """Register notification-related API routes."""

    @app.post("/api/notifications/devices")
    async def register_notification_device(
        payload: NotificationDeviceRegistration,
        api_key: str = Depends(get_api_key_dependency),
    ):
        """Register or update a device token for push notifications."""
        try:
            token = normalize_device_token(payload.token)
            platform = payload.platform.lower()
            if platform not in {"ios"}:
                raise HTTPException(status_code=400, detail="Unsupported platform")

            environment = normalize_environment(payload.environment)
            cache = get_cache()
            cache.upsert_notification_device(
                api_key_hash=_api_key_hash(api_key),
                device_token=token,
                platform=platform,
                bundle_id=payload.bundle_id
                or notification_settings.apns_bundle_id
                or None,
                environment=environment,
                device_id=payload.device_id,
                enabled=payload.enabled,
            )

            return {"success": True, "token": token}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to register notification device: {e}")
            raise HTTPException(status_code=500, detail="Failed to register device")

    @app.delete("/api/notifications/devices/{token}")
    async def unregister_notification_device(
        token: str,
        api_key: str = Depends(get_api_key_dependency),
    ):
        """Unregister a device token."""
        try:
            normalized_token = normalize_device_token(token)
            cache = get_cache()
            deleted = cache.remove_notification_device(
                api_key_hash=_api_key_hash(api_key),
                device_token=normalized_token,
            )
            return {"success": True, "deleted": deleted}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to unregister device: {e}")
            raise HTTPException(status_code=500, detail="Failed to unregister device")

    @app.post("/api/notifications/test")
    async def test_notification(
        payload: NotificationTestRequest,
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Send a test notification to registered devices or a specific token."""
        service = get_notification_service()
        if not service.enabled:
            raise HTTPException(status_code=400, detail="Notifications not configured")

        token = normalize_device_token(payload.token) if payload.token else None
        sent = await service.send_test_notification(
            title=payload.title, body=payload.body, token=token
        )
        return {"success": True, "sent": sent}

    @app.get("/api/notifications/preferences")
    async def get_notification_preferences(
        api_key: str = Depends(get_api_key_dependency),
    ):
        """Get notification preferences for the current API key."""
        cache = get_cache()
        preferences = cache.get_notification_preferences(
            api_key_hash=_api_key_hash(api_key)
        )
        return NotificationPreferences(**preferences)

    @app.patch("/api/notifications/preferences")
    async def update_notification_preferences(
        payload: NotificationPreferencesPatch,
        api_key: str = Depends(get_api_key_dependency),
    ):
        """Update notification preferences for the current API key."""
        cache = get_cache()
        current = cache.get_notification_preferences(
            api_key_hash=_api_key_hash(api_key)
        )
        updates = sanitize_notification_preferences(
            payload.model_dump(exclude_unset=True)
        )

        merged = {**current, **updates}
        cache.upsert_notification_preferences(
            api_key_hash=_api_key_hash(api_key),
            preferences=merged,
        )
        return NotificationPreferences(**merged)

    @app.get("/api/notifications/webpush/vapid")
    async def get_webpush_vapid(
        _authenticated: bool = Depends(verify_api_key_dependency),
    ):
        """Return Web Push VAPID public key for browser registration."""
        return {
            "enabled": notification_settings.webpush_enabled,
            "public_key": notification_settings.webpush_vapid_public_key,
        }

    @app.post("/api/notifications/webpush/subscribe")
    async def register_webpush_subscription(
        payload: WebPushSubscriptionRegistration,
        api_key: str = Depends(get_api_key_dependency),
    ):
        """Register a Web Push subscription."""
        endpoint = InputSanitizer.sanitize_text(payload.endpoint, max_length=2048)
        if not endpoint.startswith("https://"):
            raise HTTPException(status_code=400, detail="Invalid endpoint")

        cache = get_cache()
        cache.upsert_webpush_subscription(
            api_key_hash=_api_key_hash(api_key),
            endpoint=endpoint,
            p256dh=InputSanitizer.sanitize_text(payload.keys.p256dh, max_length=512),
            auth=InputSanitizer.sanitize_text(payload.keys.auth, max_length=512),
            user_agent=payload.user_agent,
            enabled=payload.enabled,
        )
        return {"success": True, "endpoint": endpoint}

    @app.post("/api/notifications/webpush/unsubscribe")
    async def unregister_webpush_subscription(
        payload: WebPushUnsubscribeRequest,
        api_key: str = Depends(get_api_key_dependency),
    ):
        """Unregister a Web Push subscription."""
        endpoint = InputSanitizer.sanitize_text(payload.endpoint, max_length=2048)
        cache = get_cache()
        deleted = cache.remove_webpush_subscription(
            api_key_hash=_api_key_hash(api_key),
            endpoint=endpoint,
        )
        return {"success": True, "deleted": deleted}
