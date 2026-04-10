"""Launch event buffering and delivery helpers."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any, Deque, Dict, Iterable, Optional

from .utils.logging import setup_logger

logger = setup_logger(__name__, "INFO")

MAX_EVENTS_PER_LAUNCH = 400
MAX_LOG_MESSAGE_BYTES = 4000
MAX_ACTIVE_LAUNCHES = 128
DISPATCH_BACKLOG_LIMIT = 2000
SUBSCRIBER_QUEUE_LIMIT = 200
LAUNCH_TTL_SECONDS = 15 * 60

TERMINAL_STAGES = {"completed", "failed"}
LOG_EVENT_TYPE = "launch_log"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate_message(message: str, limit: int = MAX_LOG_MESSAGE_BYTES) -> str:
    encoded = message.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return message
    truncated = encoded[:limit].decode("utf-8", errors="ignore").rstrip()
    suffix = " [truncated]"
    if truncated.endswith(suffix):
        return truncated
    return f"{truncated}{suffix}"


@dataclass
class LaunchRecord:
    launch_id: str
    hostname: str
    created_at: float = field(default_factory=monotonic)
    updated_at: float = field(default_factory=monotonic)
    sequence: int = 0
    stage: str = "accepted"
    terminal: bool = False
    success: Optional[bool] = None
    job_id: Optional[str] = None
    message: str = ""
    events: Deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=MAX_EVENTS_PER_LAUNCH)
    )


class LaunchEventEmitter:
    """Thread-safe helper used by launch execution code."""

    def __init__(self, manager: "LaunchEventManager", launch_id: str, hostname: str):
        self.manager = manager
        self.launch_id = launch_id
        self.hostname = hostname

    def stage(self, stage: str, *, message: str = "", job_id: Optional[str] = None):
        self.manager.publish(
            launch_id=self.launch_id,
            hostname=self.hostname,
            event_type="launch_stage",
            stage=stage,
            message=message,
            job_id=job_id,
        )

    def log(
        self,
        source: str,
        message: str,
        *,
        stream: str = "stdout",
        level: str = "info",
        job_id: Optional[str] = None,
    ):
        if not message:
            return
        self.manager.publish(
            launch_id=self.launch_id,
            hostname=self.hostname,
            event_type=LOG_EVENT_TYPE,
            source=source,
            stream=stream,
            level=level,
            message=message,
            job_id=job_id,
        )

    def result(self, *, success: bool, message: str, job_id: Optional[str] = None):
        self.manager.publish(
            launch_id=self.launch_id,
            hostname=self.hostname,
            event_type="launch_result",
            stage="completed" if success else "failed",
            success=success,
            message=message,
            job_id=job_id,
        )


class LaunchEventManager:
    """Buffers launch events and fans them out asynchronously."""

    def __init__(self):
        self._lock = Lock()
        self._records: Dict[str, LaunchRecord] = {}
        self._subscribers: Dict[str, set[asyncio.Queue]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._dispatch_ready: Optional[asyncio.Event] = None
        self._dispatch_buffer: Deque[dict[str, Any]] = deque()
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._ws_broadcaster = None

    def set_websocket_broadcaster(self, broadcaster) -> None:
        self._ws_broadcaster = broadcaster

    async def start(self) -> None:
        if self._dispatcher_task and not self._dispatcher_task.done():
            return
        self._loop = asyncio.get_running_loop()
        self._dispatch_ready = asyncio.Event()
        self._dispatcher_task = asyncio.create_task(
            self._dispatch_loop(), name="launch-event-dispatcher"
        )

    async def stop(self) -> None:
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
            self._dispatcher_task = None
        self._loop = None
        self._dispatch_ready = None

    def create_emitter(self, launch_id: str, hostname: str) -> LaunchEventEmitter:
        with self._lock:
            self._cleanup_expired_locked()
            self._ensure_record_locked(launch_id, hostname)
        return LaunchEventEmitter(self, launch_id, hostname)

    def publish(self, *, launch_id: str, hostname: str, event_type: str, **fields) -> None:
        with self._lock:
            self._cleanup_expired_locked()
            record = self._ensure_record_locked(launch_id, hostname)
            record.sequence += 1
            record.updated_at = monotonic()
            payload = {
                "type": event_type,
                "launch_id": launch_id,
                "hostname": hostname,
                "sequence": record.sequence,
                "timestamp": _utc_now_iso(),
            }
            payload.update(fields)
            if "message" in payload and payload["message"] is not None:
                payload["message"] = _truncate_message(str(payload["message"]))

            if event_type == "launch_stage":
                record.stage = payload.get("stage") or record.stage
                record.message = payload.get("message", record.message)
                if payload.get("job_id"):
                    record.job_id = payload["job_id"]
            elif event_type == LOG_EVENT_TYPE:
                if payload.get("job_id"):
                    record.job_id = payload["job_id"]
            elif event_type == "launch_result":
                record.stage = payload.get("stage") or record.stage
                record.terminal = True
                record.success = bool(payload.get("success"))
                record.message = payload.get("message", record.message)
                if payload.get("job_id"):
                    record.job_id = payload["job_id"]

            record.events.append(payload)

        self._enqueue_for_dispatch(payload)

    def get_status(self, launch_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            self._cleanup_expired_locked()
            record = self._records.get(launch_id)
            if not record:
                return None
            return self._record_to_status(record)

    async def subscribe(
        self, launch_id: str
    ) -> tuple[dict[str, Any], asyncio.Queue]:
        with self._lock:
            self._cleanup_expired_locked()
            record = self._records.get(launch_id)
            if not record:
                raise KeyError(launch_id)
            snapshot = self._record_to_status(record)

        queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_LIMIT)
        subscribers = self._subscribers.setdefault(launch_id, set())
        subscribers.add(queue)
        return snapshot, queue

    def unsubscribe(self, launch_id: str, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get(launch_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(launch_id, None)

    def _record_to_status(self, record: LaunchRecord) -> dict[str, Any]:
        return {
            "launch_id": record.launch_id,
            "hostname": record.hostname,
            "stage": record.stage,
            "terminal": record.terminal,
            "success": record.success,
            "job_id": record.job_id,
            "message": record.message,
            "events": list(record.events),
        }

    def _ensure_record_locked(self, launch_id: str, hostname: str) -> LaunchRecord:
        record = self._records.get(launch_id)
        if record is None:
            if len(self._records) >= MAX_ACTIVE_LAUNCHES:
                self._evict_oldest_locked()
            record = LaunchRecord(launch_id=launch_id, hostname=hostname)
            self._records[launch_id] = record
        return record

    def _evict_oldest_locked(self) -> None:
        if not self._records:
            return
        oldest_launch_id = min(
            self._records,
            key=lambda key: self._records[key].updated_at,
        )
        self._records.pop(oldest_launch_id, None)
        self._subscribers.pop(oldest_launch_id, None)

    def _cleanup_expired_locked(self) -> None:
        now = monotonic()
        expired = [
            launch_id
            for launch_id, record in self._records.items()
            if record.terminal and now - record.updated_at > LAUNCH_TTL_SECONDS
        ]
        for launch_id in expired:
            self._records.pop(launch_id, None)
            self._subscribers.pop(launch_id, None)

    def _enqueue_for_dispatch(self, payload: dict[str, Any]) -> None:
        if self._loop is None:
            return
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is self._loop:
            self._enqueue_on_loop(payload)
        else:
            self._loop.call_soon_threadsafe(self._enqueue_on_loop, payload)

    def _enqueue_on_loop(self, payload: dict[str, Any]) -> None:
        if self._dispatch_ready is None:
            return
        if len(self._dispatch_buffer) >= DISPATCH_BACKLOG_LIMIT:
            if payload["type"] == LOG_EVENT_TYPE:
                return
            for index, queued in enumerate(self._dispatch_buffer):
                if queued["type"] == LOG_EVENT_TYPE:
                    del self._dispatch_buffer[index]
                    break
            else:
                self._dispatch_buffer.popleft()
        self._dispatch_buffer.append(payload)
        self._dispatch_ready.set()

    async def _dispatch_loop(self) -> None:
        assert self._dispatch_ready is not None
        while True:
            await self._dispatch_ready.wait()
            while True:
                try:
                    payload = self._dispatch_buffer.popleft()
                except IndexError:
                    self._dispatch_ready.clear()
                    if self._dispatch_buffer:
                        self._dispatch_ready.set()
                        continue
                    break
                await self._dispatch_payload(payload)

    async def _dispatch_payload(self, payload: dict[str, Any]) -> None:
        launch_id = payload["launch_id"]
        disconnected: list[asyncio.Queue] = []
        for queue in list(self._subscribers.get(launch_id, ())):
            try:
                self._enqueue_subscriber(queue, payload)
            except Exception:
                disconnected.append(queue)
        for queue in disconnected:
            self.unsubscribe(launch_id, queue)

        if self._ws_broadcaster is not None:
            try:
                await self._ws_broadcaster(payload)
            except Exception as exc:
                logger.debug("Launch websocket broadcast failed: %s", exc)

    def _enqueue_subscriber(self, queue: asyncio.Queue, payload: dict[str, Any]) -> None:
        if not queue.full():
            queue.put_nowait(payload)
            return

        if payload["type"] == LOG_EVENT_TYPE:
            return

        while queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        queue.put_nowait(payload)

    @staticmethod
    def iter_recent_logs(events: Iterable[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
        logs = [event for event in events if event["type"] == LOG_EVENT_TYPE]
        return logs[-limit:]
