from __future__ import annotations

from typing import Optional, Tuple

import httpx

from ..utils.logging import setup_logger

logger = setup_logger(__name__)


class ExpoPushClient:
    """Expo push notification client."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def send(
        self,
        *,
        token: str,
        payload: dict,
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        message = {"to": token, **payload}

        try:
            response = await self._client.post(
                "https://exp.host/--/api/v2/push/send",
                json=message,
            )
        except Exception as exc:
            logger.error(f"Expo push request failed for token {token[:16]}...: {exc}")
            return False, str(exc), None

        try:
            data = response.json()
        except Exception:
            data = {}

        if response.status_code == 200 and data.get("data", {}).get("status") == "ok":
            return True, None, response.status_code

        details = data.get("data", {}).get("details") or {}
        reason = details.get("error") or data.get("errors") or response.text
        logger.warning(
            f"Expo push failed status={response.status_code} reason={reason}"
        )
        return False, str(reason), response.status_code

    async def close(self) -> None:
        await self._client.aclose()
