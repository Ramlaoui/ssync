"""Compatibility facade for security helpers."""

from .api_keys import APIKeyManager
from .auth import (
    configure_security_middleware,
    create_auth_dependencies,
    register_auth_routes,
)
from .inputs import (
    InputSanitizer,
    PathValidator,
    RateLimiter,
    ScriptValidator,
    normalize_device_token,
    normalize_environment,
    normalize_push_token,
    sanitize_error_message,
    sanitize_notification_preferences,
)
from .sessions import SessionManager

__all__ = [
    "APIKeyManager",
    "InputSanitizer",
    "PathValidator",
    "RateLimiter",
    "ScriptValidator",
    "configure_security_middleware",
    "create_auth_dependencies",
    "register_auth_routes",
    "SessionManager",
    "normalize_device_token",
    "normalize_environment",
    "normalize_push_token",
    "sanitize_error_message",
    "sanitize_notification_preferences",
]
