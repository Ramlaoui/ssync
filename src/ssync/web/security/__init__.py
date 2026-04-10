"""Compatibility facade for security helpers."""

from .api_keys import APIKeyManager
from .auth import configure_security_middleware, create_auth_dependencies
from .inputs import (
    InputSanitizer,
    PathValidator,
    RateLimiter,
    ScriptValidator,
    normalize_device_token,
    normalize_environment,
    sanitize_error_message,
    sanitize_notification_preferences,
)

__all__ = [
    "APIKeyManager",
    "InputSanitizer",
    "PathValidator",
    "RateLimiter",
    "ScriptValidator",
    "configure_security_middleware",
    "create_auth_dependencies",
    "normalize_device_token",
    "normalize_environment",
    "sanitize_error_message",
    "sanitize_notification_preferences",
]
