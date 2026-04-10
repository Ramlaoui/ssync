"""API key persistence and usage tracking helpers."""

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from ...utils.logging import setup_logger

logger = setup_logger(__name__)


class APIKeyManager:
    """Manage API keys with secure storage and rotation."""

    def __init__(
        self,
        key_file: Optional[Path] = None,
        usage_save_interval_seconds: Optional[float] = None,
        usage_save_batch_size: Optional[int] = None,
    ):
        self.key_file = key_file or Path.home() / ".config" / "ssync" / ".api_key"
        self.keys: Dict[str, Dict] = {}
        self.simple_key: Optional[str] = None
        self._lock = threading.RLock()
        self._usage_save_interval_seconds = (
            usage_save_interval_seconds
            if usage_save_interval_seconds is not None
            else float(os.getenv("SSYNC_API_KEY_SAVE_INTERVAL_SECONDS", "30"))
        )
        self._usage_save_batch_size = (
            usage_save_batch_size
            if usage_save_batch_size is not None
            else int(os.getenv("SSYNC_API_KEY_SAVE_BATCH_SIZE", "100"))
        )
        self._pending_usage_updates = 0
        self._last_save_monotonic = time.monotonic()
        self._load_keys()

    def _load_keys(self):
        with self._lock:
            if self.key_file.exists():
                try:
                    self.key_file.chmod(0o600)
                except Exception:
                    pass

                try:
                    with open(self.key_file, "r") as file_obj:
                        content = file_obj.read().strip()

                    if content.startswith("{"):
                        self.keys = json.loads(content)
                    else:
                        self.simple_key = content
                        self.keys[content] = {
                            "name": "default",
                            "created_at": datetime.now().isoformat(),
                            "expires_at": (
                                datetime.now() + timedelta(days=365)
                            ).isoformat(),
                            "last_used": None,
                            "usage_count": 0,
                        }
                except Exception as e:
                    logger.error(f"Failed to load API keys: {e}")
                    self.keys = {}

            self._pending_usage_updates = 0
            self._last_save_monotonic = time.monotonic()

    def validate_key(self, key: str) -> bool:
        should_persist = False
        now = datetime.now()

        with self._lock:
            if key not in self.keys:
                return False

            key_data = self.keys[key]
            expires_at = datetime.fromisoformat(key_data["expires_at"])
            if now > expires_at:
                return False

            key_data["last_used"] = now.isoformat()
            key_data["usage_count"] = int(key_data.get("usage_count", 0)) + 1
            self._pending_usage_updates += 1
            should_persist = self._should_persist_usage_stats_locked()

        if should_persist:
            self._save_keys()

        return True

    def flush_usage_stats(self):
        with self._lock:
            if self._pending_usage_updates > 0:
                self._save_keys_locked()

    def _should_persist_usage_stats_locked(self) -> bool:
        if self._pending_usage_updates <= 0:
            return False
        if self._usage_save_batch_size <= 1:
            return True
        if self._usage_save_interval_seconds <= 0:
            return True
        if self._pending_usage_updates >= self._usage_save_batch_size:
            return True

        elapsed = time.monotonic() - self._last_save_monotonic
        return elapsed >= self._usage_save_interval_seconds

    def _save_keys(self):
        with self._lock:
            self._save_keys_locked()

    def _save_keys_locked(self):
        self.key_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.key_file, "w") as file_obj:
            json.dump(self.keys, file_obj, indent=2)

        self.key_file.chmod(0o600)
        self._pending_usage_updates = 0
        self._last_save_monotonic = time.monotonic()
