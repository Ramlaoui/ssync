"""Authentication and middleware setup helpers for the web app."""

import fnmatch
import ipaddress
import os
from typing import Optional

from fastapi import Depends, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .inputs import RateLimiter


class CustomTrustedHostMiddleware(BaseHTTPMiddleware):
    """Trusted host middleware that supports domain and IP wildcard patterns."""

    def __init__(self, app, logger, allowed_hosts=None, allowed_ip_patterns=None):
        super().__init__(app)
        self.logger = logger
        self.allowed_hosts = allowed_hosts or []
        self.allowed_ip_patterns = allowed_ip_patterns or []

    def is_ip_allowed(self, ip: str) -> bool:
        for pattern in self.allowed_ip_patterns:
            if fnmatch.fnmatch(ip, pattern):
                return True
        return False

    async def dispatch(self, request, call_next):
        host_header = request.headers.get("host", "")
        host_part = host_header.split(":")[0] if ":" in host_header else host_header

        allowed = False
        for allowed_host in self.allowed_hosts:
            if allowed_host == "*":
                allowed = True
                break
            if allowed_host.startswith("*.") and host_part.endswith(allowed_host[1:]):
                allowed = True
                break
            if host_part == allowed_host:
                allowed = True
                break

        if not allowed and self.allowed_ip_patterns:
            try:
                ipaddress.ip_address(host_part)
                allowed = self.is_ip_allowed(host_part)
            except ValueError:
                allowed = self.is_ip_allowed(host_part)

        if not allowed:
            self.logger.warning(
                f"Rejected host header: {host_part}, "
                f"allowed_hosts: {self.allowed_hosts}, "
                f"allowed_ip_patterns: {self.allowed_ip_patterns}"
            )
            return Response(f"Invalid host header: {host_part}", status_code=400)

        return await call_next(request)


def configure_security_middleware(app, logger) -> None:
    """Register trusted host, CORS, and rate limiting middleware."""
    trusted_hosts_env = os.getenv("SSYNC_TRUSTED_HOSTS", "localhost,127.0.0.1")
    trusted_hosts_list = [host.strip() for host in trusted_hosts_env.split(",") if host.strip()]

    valid_patterns = []
    ip_patterns = []
    for host in trusted_hosts_list:
        if "*" in host and not host.startswith("*."):
            ip_patterns.append(host)
        else:
            valid_patterns.append(host)

    app.add_middleware(
        CustomTrustedHostMiddleware,
        logger=logger,
        allowed_hosts=valid_patterns,
        allowed_ip_patterns=ip_patterns,
    )

    allowed_origins = os.getenv("SSYNC_ALLOWED_ORIGINS", "").split(",")
    allowed_origins = [origin.strip() for origin in allowed_origins if origin.strip()]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["X-API-Key", "Content-Type"],
            max_age=3600,
        )

    rate_limiter = RateLimiter(
        requests_per_minute=int(os.getenv("SSYNC_RATE_LIMIT_PER_MINUTE", "120")),
        requests_per_hour=int(os.getenv("SSYNC_RATE_LIMIT_PER_HOUR", "2000")),
        burst_size=int(os.getenv("SSYNC_BURST_SIZE", "50")),
    )

    class RateLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if request.url.path == "/health":
                return await call_next(request)

            if not await rate_limiter.check_rate_limit(request):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please try again later."},
                    headers={"Retry-After": "60"},
                )

            return await call_next(request)

    app.add_middleware(RateLimitMiddleware)


def create_auth_dependencies(*, api_key_manager, api_key_header, require_api_key, logger):
    """Create request and websocket auth dependency functions."""

    async def verify_api_key(
        request: Request, api_key: Optional[str] = Depends(api_key_header)
    ):
        if not require_api_key or request.url.path == "/health":
            return True

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="API key required. Please provide X-API-Key header.",
            )

        if not api_key_manager.validate_key(api_key):
            raise HTTPException(status_code=401, detail="Invalid or expired API key.")

        return True

    async def get_api_key(
        request: Request, api_key: Optional[str] = Depends(api_key_header)
    ) -> str:
        if not require_api_key or request.url.path == "/health":
            return ""

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="API key required. Please provide X-API-Key header.",
            )

        if not api_key_manager.validate_key(api_key):
            raise HTTPException(status_code=401, detail="Invalid or expired API key.")

        return api_key

    async def verify_api_key_flexible(
        request: Request, api_key_query: Optional[str] = Query(None, alias="api_key")
    ):
        if not require_api_key or request.url.path == "/health":
            return True

        api_key = request.headers.get("x-api-key") or api_key_query
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="API key required. Please provide X-API-Key header or api_key query parameter.",
            )

        if not api_key_manager.validate_key(api_key):
            raise HTTPException(status_code=401, detail="Invalid or expired API key.")

        return True

    async def verify_websocket_api_key(websocket: WebSocket):
        if not require_api_key:
            return True

        api_key = websocket.query_params.get("api_key")
        logger.info(
            f"WebSocket auth: api_key from query params: {bool(api_key)}, path: {websocket.url.path}"
        )

        if not api_key:
            api_key = websocket.headers.get("x-api-key")
            logger.info(f"WebSocket auth: api_key from headers: {bool(api_key)}")

        if not api_key:
            logger.warning(
                f"WebSocket auth failed: no API key provided for {websocket.url.path}"
            )
            await websocket.close(code=1008, reason="API key required")
            return False

        if not api_key_manager.validate_key(api_key):
            logger.warning(
                f"WebSocket auth failed: invalid API key for {websocket.url.path}"
            )
            await websocket.close(code=1008, reason="Invalid or expired API key")
            return False

        logger.info(f"WebSocket auth successful for {websocket.url.path}")
        return True

    return verify_api_key, get_api_key, verify_api_key_flexible, verify_websocket_api_key
