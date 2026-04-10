"""Shared websocket connection state for realtime web APIs."""

import asyncio
import os
from typing import Optional, Set

from fastapi import WebSocket

from ...utils.logging import setup_logger

logger = setup_logger(__name__)
_WS_SEND_TIMEOUT_SECONDS = float(os.getenv("SSYNC_WS_SEND_TIMEOUT_SECONDS", "5"))


async def _send_json_to_websocket(
    websocket: WebSocket, message: dict[str, object]
) -> tuple[WebSocket, bool]:
    """Send a JSON websocket message with a bounded timeout."""
    try:
        if _WS_SEND_TIMEOUT_SECONDS > 0:
            await asyncio.wait_for(
                websocket.send_json(message), timeout=_WS_SEND_TIMEOUT_SECONDS
            )
        else:
            await websocket.send_json(message)
        return websocket, True
    except Exception as exc:
        logger.debug(f"Failed to send websocket message: {exc}")
        return websocket, False


async def broadcast_json_to_websockets(
    websockets, message: dict[str, object]
) -> Set[WebSocket]:
    """Broadcast JSON to websocket clients concurrently and return failed sockets."""
    websocket_list = list(websockets)
    if not websocket_list:
        return set()

    results = await asyncio.gather(
        *[_send_json_to_websocket(websocket, message) for websocket in websocket_list]
    )
    return {websocket for websocket, ok in results if not ok}


class WatcherConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = await broadcast_json_to_websockets(
            self.active_connections, message
        )
        for websocket in disconnected:
            self.disconnect(websocket)


class JobConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.all_jobs_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket, job_id: Optional[str] = None):
        await websocket.accept()
        if job_id:
            if job_id not in self.active_connections:
                self.active_connections[job_id] = []
            self.active_connections[job_id].append(websocket)
            return
        self.all_jobs_connections.append(websocket)

    def disconnect(self, websocket: WebSocket, job_id: Optional[str] = None):
        if job_id and job_id in self.active_connections:
            if websocket in self.active_connections[job_id]:
                self.active_connections[job_id].remove(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
            return

        if websocket in self.all_jobs_connections:
            self.all_jobs_connections.remove(websocket)

    async def send_to_job(self, job_id: str, message: dict):
        """Send message to all connections watching a specific job."""
        if job_id not in self.active_connections:
            return

        disconnected = await broadcast_json_to_websockets(
            self.active_connections[job_id], message
        )
        for websocket in disconnected:
            self.disconnect(websocket, job_id)

    async def broadcast_job_update(self, job_id: str, hostname: str, message: dict):
        """Broadcast job update to specific job watchers and all-jobs watchers."""
        await self.send_to_job(job_id, message)

        message_with_context = {**message, "job_id": job_id, "hostname": hostname}
        disconnected = await broadcast_json_to_websockets(
            self.all_jobs_connections, message_with_context
        )
        for websocket in disconnected:
            self.disconnect(websocket)


class AllJobsMonitorState:
    def __init__(self):
        self.monitor_task: Optional[asyncio.Task] = None
        self.websockets: Set[WebSocket] = set()
        self.lock = asyncio.Lock()


watcher_manager = WatcherConnectionManager()
job_manager = JobConnectionManager()
all_jobs_state = AllJobsMonitorState()
