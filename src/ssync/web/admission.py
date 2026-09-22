"""Fail fast under overload, before requests retain large bodies or responses."""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from .services.watchers import MAX_MANUAL_WATCHER_BYTES, WatcherOutputTooLarge


class RequestAdmissionMiddleware:
    """Separate budgets for ordinary requests, output transfers and sockets.

    Reservations cover the entire ASGI response, including streaming and slow
    clients. Health checks have no dependency on worker or request capacity.
    Counters are only accessed on the application's event loop.
    """

    def __init__(
        self,
        app,
        *,
        request_limit=64,
        output_limit=8,
        stream_limit=16,
        websocket_limit=64,
    ):
        self.app = app
        self.limits = {
            "request": request_limit,
            "output": output_limit,
            "stream": stream_limit,
            "websocket": websocket_limit,
            "filesystem": 2,
            "watcher": 2,
        }
        self.active = dict.fromkeys(self.limits, 0)

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        path = scope.get("path", "")
        if kind not in {"http", "websocket"} or path == "/health":
            return await self.app(scope, receive, send)

        if kind == "websocket":
            lane = "websocket"
        elif path in {"/api/local/list", "/api/launch-catalog"}:
            lane = "filesystem"
        elif path.endswith(("/stream", "/download", "/events")):
            lane = "stream"
        elif path.startswith("/api/watchers/") and path.endswith("/trigger"):
            lane = "watcher"
        elif path.endswith(("/output", "/data")):
            lane = "output"
        else:
            lane = "request"

        if self.active[lane] >= self.limits[lane]:
            if kind == "websocket":
                await send(
                    {
                        "type": "websocket.close",
                        "code": 1013,
                        "reason": "Server busy; retry shortly",
                    }
                )
            else:
                await JSONResponse(
                    {"detail": "Server busy. Please retry shortly."},
                    status_code=503,
                    headers={"Retry-After": "1"},
                )(scope, receive, send)
            return

        self.active[lane] += 1
        try:
            if lane == "watcher":
                # Apply the byte budget before the JSON parser accumulates a
                # test sample. Count actual bytes for chunked uploads too.
                received_bytes = 0
                original_receive = receive

                async def limited_receive():
                    nonlocal received_bytes
                    message = await original_receive()
                    received_bytes += len(message.get("body", b""))
                    if received_bytes > MAX_MANUAL_WATCHER_BYTES:
                        raise HTTPException(413, str(WatcherOutputTooLarge()))
                    return message

                receive = limited_receive
            await self.app(scope, receive, send)
        finally:
            self.active[lane] -= 1
