from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Tuple

import httpx
import jwt

from ..utils.logging import setup_logger

logger = setup_logger(__name__)


class APNsClient:
    """Minimal APNs HTTP/2 client using token-based authentication."""

    def __init__(
        self,
        *,
        key_id: str,
        team_id: str,
        bundle_id: str,
        private_key: str,
        use_sandbox: bool = True,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.key_id = key_id
        self.team_id = team_id
        self.bundle_id = bundle_id
        self.private_key = self._load_private_key(private_key)
        self.use_sandbox = use_sandbox
        self.timeout_seconds = timeout_seconds

        self._jwt_token: Optional[str] = None
        self._jwt_issued_at: float = 0.0
        self._client = httpx.AsyncClient(http2=True, timeout=timeout_seconds)

    def _load_private_key(self, value: str) -> str:
        value = value.strip()
        if value.startswith("-----BEGIN"):
            return value
        key_path = Path(value).expanduser()
        if key_path.exists():
            return key_path.read_text().strip()
        return value

    def _get_jwt(self) -> str:
        now = int(time.time())
        if self._jwt_token and (now - self._jwt_issued_at) < 50 * 60:
            return self._jwt_token

        headers = {"alg": "ES256", "kid": self.key_id}
        claims = {"iss": self.team_id, "iat": now}
        token = jwt.encode(claims, self.private_key, algorithm="ES256", headers=headers)

        self._jwt_token = token
        self._jwt_issued_at = now
        return token

    @property
    def base_url(self) -> str:
        if self.use_sandbox:
            return "https://api.sandbox.push.apple.com"
        return "https://api.push.apple.com"

    async def send(
        self,
        *,
        device_token: str,
        payload: dict,
        push_type: str = "alert",
        priority: int = 10,
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        token = device_token.replace(" ", "").replace("<", "").replace(">", "")
        url = f"{self.base_url}/3/device/{token}"

        headers = {
            "authorization": f"bearer {self._get_jwt()}",
            "apns-topic": self.bundle_id,
            "apns-push-type": push_type,
            "apns-priority": str(priority),
        }

        try:
            response = await self._client.post(url, json=payload, headers=headers)
        except Exception as exc:
            logger.error(f"APNs request failed for device {token[:8]}...: {exc}")
            return False, str(exc), None

        if response.status_code == 200:
            return True, None, response.status_code

        reason = None
        try:
            data = response.json()
            reason = data.get("reason")
        except Exception:
            reason = response.text.strip() if response.text else None

        logger.warning(
            f"APNs error status={response.status_code} reason={reason} token={token[:8]}..."
        )
        return False, reason, response.status_code

    async def close(self) -> None:
        await self._client.aclose()
