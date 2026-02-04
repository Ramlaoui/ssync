from __future__ import annotations

import asyncio
import json
from typing import Optional, Tuple

from pywebpush import WebPushException, webpush

from ..utils.logging import setup_logger

logger = setup_logger(__name__)


class WebPushClient:
    """Web Push client using VAPID authentication."""

    def __init__(
        self,
        *,
        vapid_public_key: str,
        vapid_private_key: str,
        vapid_subject: str,
    ) -> None:
        self.vapid_public_key = vapid_public_key
        self.vapid_private_key = vapid_private_key
        self.vapid_subject = vapid_subject

    async def send(
        self,
        *,
        endpoint: str,
        p256dh: str,
        auth: str,
        payload: dict,
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        subscription_info = {
            "endpoint": endpoint,
            "keys": {"p256dh": p256dh, "auth": auth},
        }
        vapid_claims = {"sub": self.vapid_subject}
        data = json.dumps(payload)

        def _send_sync():
            return webpush(
                subscription_info=subscription_info,
                data=data,
                vapid_private_key=self.vapid_private_key,
                vapid_claims=vapid_claims,
            )

        try:
            await asyncio.to_thread(_send_sync)
            return True, None, 201
        except WebPushException as exc:
            status = None
            reason = str(exc)
            if exc.response is not None:
                status = exc.response.status_code
                reason = exc.response.text or reason
            logger.warning(f"Web Push failed status={status} reason={reason}")
            return False, reason, status
        except Exception as exc:
            logger.error(f"Web Push failed: {exc}")
            return False, str(exc), None
