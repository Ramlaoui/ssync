"""Short-lived browser session tokens for realtime auth."""

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class SessionRecord:
    api_key: str
    expires_at: float


class SessionManager:
    """In-memory session token store.

    Sessions intentionally do not persist across server restarts. Clients can
    re-create them by presenting the API key over the normal header path.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = 12 * 60 * 60,
        cookie_name: str = "ssync_session",
    ):
        self.ttl_seconds = ttl_seconds
        self.cookie_name = cookie_name
        self._sessions: Dict[str, SessionRecord] = {}
        self._lock = threading.RLock()

    def create_session(self, api_key: str) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + self.ttl_seconds
        with self._lock:
            self._sessions[token] = SessionRecord(
                api_key=api_key,
                expires_at=expires_at,
            )
            self._prune_expired_locked(time.time())
        return token

    def get_api_key(self, token: Optional[str]) -> Optional[str]:
        if not token:
            return None

        now = time.time()
        with self._lock:
            record = self._sessions.get(token)
            if record is None:
                return None
            if record.expires_at <= now:
                self._sessions.pop(token, None)
                return None
            return record.api_key

    def revoke_session(self, token: Optional[str]) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def _prune_expired_locked(self, now: float) -> None:
        expired = [
            token for token, record in self._sessions.items() if record.expires_at <= now
        ]
        for token in expired:
            self._sessions.pop(token, None)
