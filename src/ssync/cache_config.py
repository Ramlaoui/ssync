"""
Configuration for SLURM job cache.

Environment variables:
- SSYNC_CACHE_DIR: Cache directory path (default: ~/.ssync/cache)
- SSYNC_CACHE_MAX_AGE_DAYS: Max age of cache entries in days (default: 30)
- SSYNC_CACHE_CLEANUP_INTERVAL_HOURS: Hours between cleanup runs (default: 24)
- SSYNC_CACHE_ENABLED: Enable/disable caching (default: true)
"""

import os
from pathlib import Path


class CacheConfig:
    """Cache configuration settings."""

    def __init__(self):
        self.enabled = os.getenv("SSYNC_CACHE_ENABLED", "true").lower() in (
            "true",
            "1",
            "yes",
        )

        self.cache_dir = self._get_cache_dir()

        # Conservative defaults - preserve data longer since it might be the only copy
        self.max_age_days = int(
            os.getenv("SSYNC_CACHE_MAX_AGE_DAYS", "365")
        )  # 1 year default
        self.script_max_age_days = int(
            os.getenv("SSYNC_CACHE_SCRIPT_MAX_AGE_DAYS", "0")
        )  # Never expire scripts
        self.cleanup_interval_hours = int(
            os.getenv("SSYNC_CACHE_CLEANUP_INTERVAL_HOURS", "168")
        )  # Weekly

        # Size-based limits (MB)
        self.max_cache_size_mb = int(
            os.getenv("SSYNC_CACHE_MAX_SIZE_MB", "1024")
        )  # 1GB default
        self.auto_cleanup_enabled = os.getenv(
            "SSYNC_CACHE_AUTO_CLEANUP", "false"
        ).lower() in ("true", "1", "yes")

        # Validation
        if self.max_age_days < 0:
            self.max_age_days = 0  # 0 means never expire
        if self.script_max_age_days < 0:
            self.script_max_age_days = 0
        if self.cleanup_interval_hours < 1:
            self.cleanup_interval_hours = 1
        if self.max_cache_size_mb < 10:
            self.max_cache_size_mb = 10

    def _get_cache_dir(self) -> Path:
        """Get cache directory from environment or default."""
        cache_dir_env = os.getenv("SSYNC_CACHE_DIR")

        if cache_dir_env:
            return Path(cache_dir_env).expanduser().resolve()
        else:
            return Path.home() / ".ssync" / "cache"

    def __str__(self) -> str:
        return (
            f"CacheConfig(enabled={self.enabled}, "
            f"cache_dir={self.cache_dir}, "
            f"max_age_days={self.max_age_days}, "
            f"script_max_age_days={self.script_max_age_days}, "
            f"auto_cleanup={self.auto_cleanup_enabled}, "
            f"max_size_mb={self.max_cache_size_mb})"
        )

    def is_preservation_mode(self) -> bool:
        """Check if cache is in preservation mode (never expires)."""
        return self.max_age_days == 0


# Global config instance
_config = CacheConfig()


def get_cache_config() -> CacheConfig:
    """Get global cache configuration."""
    return _config
