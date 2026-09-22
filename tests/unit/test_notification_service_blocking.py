"""Blocking and bounded scheduling tests for notification service cache work."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from ssync.notifications.service import JobNotificationEvent, NotificationService


def _service() -> NotificationService:
    service = NotificationService.__new__(NotificationService)
    service.settings = SimpleNamespace(
        enabled=True,
        apns_use_sandbox=True,
        apns_bundle_id="com.example.ssync",
    )
    service._apns_client = object()
    service._expo_client = None
    service._webpush_client = None
    service._send_semaphore = asyncio.Semaphore(10)
    service._notification_batch_tasks = {}
    service._closing = False
    return service


def _event(index: int = 0) -> JobNotificationEvent:
    return JobNotificationEvent(
        job_id=f"job-{index}",
        job_name="test",
        hostname="cluster",
        state="CD",
        changed_at=f"2026-09-22T12:00:{index:02d}",
    )


@pytest.mark.asyncio
async def test_send_job_notifications_cache_reads_run_off_event_loop(monkeypatch):
    service = _service()
    main_thread = threading.get_ident()
    started = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    class BlockingCache:
        def list_notification_devices(self, **kwargs):
            calls.append(threading.get_ident())
            started.set()
            release.wait(2)
            return []

        def list_webpush_subscriptions(self, **kwargs):
            calls.append(threading.get_ident())
            return []

    monkeypatch.setattr(
        "ssync.notifications.service.get_cache", lambda: BlockingCache()
    )
    timer = threading.Timer(0.2, release.set)
    timer.start()
    ticks = 0
    try:
        task = asyncio.create_task(service.send_job_notifications([_event()]))
        while not started.is_set():
            ticks += 1
            await asyncio.sleep(0.01)
        assert ticks > 0
        assert await task == 0
    finally:
        release.set()
        timer.cancel()

    assert calls
    assert all(thread_id != main_thread for thread_id in calls)


@pytest.mark.asyncio
async def test_send_test_notification_cache_reads_run_off_event_loop(monkeypatch):
    service = _service()
    main_thread = threading.get_ident()
    calls: list[int] = []

    class Cache:
        def list_notification_devices(self, **kwargs):
            calls.append(threading.get_ident())
            return []

        def list_webpush_subscriptions(self, **kwargs):
            calls.append(threading.get_ident())
            return []

    monkeypatch.setattr("ssync.notifications.service.get_cache", lambda: Cache())

    assert (await service.send_test_notification(title="Test", body="body")) == 0
    assert calls
    assert all(thread_id != main_thread for thread_id in calls)


@pytest.mark.asyncio
async def test_dispatch_marks_claimed_event_off_event_loop(monkeypatch):
    service = _service()
    main_thread = threading.get_ident()
    calls: list[int] = []

    class Cache:
        def mark_notification_event_sent(self, **kwargs):
            calls.append(threading.get_ident())

    async def send_job_notifications(events):
        return 3

    service.send_job_notifications = send_job_notifications
    monkeypatch.setattr("ssync.notifications.service.get_cache", lambda: Cache())
    event = _event()
    event.notification_id = "notification-1"

    await service._dispatch_claimed_events([event])

    assert calls
    assert all(thread_id != main_thread for thread_id in calls)


@pytest.mark.asyncio
async def test_enqueue_claims_off_event_loop_and_preserves_dedup(monkeypatch):
    service = _service()
    main_thread = threading.get_ident()
    started = threading.Event()
    release = threading.Event()
    claim_calls: list[tuple[int, str]] = []
    marked_calls: list[int] = []
    claimed_ids: set[str] = set()

    class Cache:
        def claim_notification_event(self, **kwargs):
            notification_id = kwargs["notification_id"]
            claim_calls.append((threading.get_ident(), notification_id))
            started.set()
            release.wait(2)
            if notification_id in claimed_ids:
                return False
            claimed_ids.add(notification_id)
            return True

        def mark_notification_event_sent(self, **kwargs):
            marked_calls.append(threading.get_ident())

    async def send_job_notifications(events):
        return 1

    monkeypatch.setattr("ssync.notifications.service.get_cache", lambda: Cache())
    service.send_job_notifications = send_job_notifications
    event = _event()

    timer = threading.Timer(0.2, release.set)
    timer.start()
    ticks = 0
    try:
        await service.enqueue_job_notifications([event])
        while not started.is_set():
            ticks += 1
            await asyncio.sleep(0.01)
        assert ticks > 0
        for _ in range(100):
            if not service._notification_batch_tasks:
                break
            await asyncio.sleep(0.01)
    finally:
        release.set()
        timer.cancel()

    assert len(claim_calls) == 1
    assert claim_calls[0][0] != main_thread
    assert marked_calls
    assert all(thread_id != main_thread for thread_id in marked_calls)

    # Re-enqueueing the same object after the first claim uses its stable ID
    # and relies on the durable claim for duplicate suppression.
    await service.enqueue_job_notifications([event])
    await asyncio.sleep(0.1)
    assert len(claim_calls) == 2
    assert claim_calls[0][1] == claim_calls[1][1]
    assert len(marked_calls) == 1


@pytest.mark.asyncio
async def test_enqueue_background_disabled_does_not_claim(monkeypatch):
    service = _service()
    claims = 0

    class Cache:
        def claim_notification_event(self, **kwargs):
            nonlocal claims
            claims += 1
            return True

    monkeypatch.setattr("ssync.notifications.service.get_cache", lambda: Cache())
    monkeypatch.setenv("SSYNC_DISABLE_BACKGROUND_TASKS", "true")

    await service.enqueue_job_notifications([_event()])
    await asyncio.sleep(0)

    assert claims == 0
    assert service._notification_batch_tasks == {}


@pytest.mark.asyncio
async def test_enqueue_notification_batches_are_bounded_to_64(monkeypatch):
    service = _service()
    gate = asyncio.Event()
    dispatched = []

    async def hold_batch(events):
        await gate.wait()
        dispatched.extend(event.job_id for event in events)

    service._claim_and_dispatch = hold_batch

    for index in range(64):
        await service.enqueue_job_notifications([_event(index)])

    overflow = asyncio.create_task(service.enqueue_job_notifications([_event(64)]))
    await asyncio.sleep(0)
    assert not overflow.done()
    assert len(service._notification_batch_tasks) == 64
    tasks = list(service._notification_batch_tasks.values())
    gate.set()
    await asyncio.gather(*tasks)
    await asyncio.wait_for(overflow, timeout=1)
    await asyncio.gather(*service._notification_batch_tasks.values())
    await asyncio.sleep(0)
    assert len(service._notification_batch_tasks) == 0
    assert set(dispatched) == {f"job-{index}" for index in range(65)}


@pytest.mark.asyncio
async def test_notification_claim_waits_for_busy_cache_without_dropping(monkeypatch):
    from ssync.notifications import service as service_module
    from ssync.utils.executors import WorkQueueFull

    service = _service()
    calls = 0
    sent = []

    async def busy_then_available(func, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise WorkQueueFull("busy")
        return True

    async def dispatch(events):
        sent.extend(event.job_id for event in events)

    monkeypatch.setattr(service_module, "run_local", busy_then_available)
    monkeypatch.setattr(service, "_dispatch_claimed_events", dispatch)

    await service._claim_and_dispatch([_event()])

    assert calls == 2
    assert sent == ["job-0"]


@pytest.mark.asyncio
async def test_close_drains_claimed_event_before_returning(monkeypatch):
    service = _service()
    claimed = asyncio.Event()
    release = asyncio.Event()
    marked = []

    class Cache:
        def mark_notification_event_sent(self, **kwargs):
            marked.append(kwargs["notification_id"])

    def claim(event):
        event.notification_id = "claimed-event"
        return True

    async def dispatch(events):
        claimed.set()
        await release.wait()
        return 1

    monkeypatch.setattr("ssync.notifications.service.get_cache", lambda: Cache())
    monkeypatch.setattr(service, "_claim_event", claim)
    monkeypatch.setattr(service, "send_job_notifications", dispatch)
    await service.enqueue_job_notifications([_event()])
    await asyncio.wait_for(claimed.wait(), timeout=1)
    shutdown = asyncio.create_task(service.close())
    await asyncio.sleep(0)
    assert not shutdown.done()
    assert not marked
    release.set()
    await asyncio.wait_for(shutdown, timeout=1)
    assert marked == ["claimed-event"]
    assert service._notification_batch_tasks == {}
