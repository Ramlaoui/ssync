"""Async helpers for background task control."""

from __future__ import annotations

import asyncio
import inspect
import os
from typing import Awaitable, Optional


def background_tasks_disabled() -> bool:
    return os.getenv("SSYNC_DISABLE_BACKGROUND_TASKS", "false").lower() == "true"


def create_task(
    coro: Awaitable, *, name: Optional[str] = None
) -> Optional[asyncio.Task]:
    """Create a background task unless disabled via env.

    Returns the created task, or None if background tasks are disabled.
    """
    if background_tasks_disabled():
        # Avoid "coroutine was never awaited" warnings by closing it.
        if inspect.iscoroutine(coro):
            coro.close()
        return None
    if name is not None:
        return asyncio.create_task(coro, name=name)
    return asyncio.create_task(coro)


def queue_task_once(*, registry, key, coro_factory, name, limit=64) -> bool:
    """Coalesce refreshes and bound detached tasks before creating coroutines."""
    existing = registry.get(key)
    if existing is not None and not existing.done():
        return True
    if len(registry) >= limit:
        return False
    task = create_task(coro_factory(), name=name)
    if task is None:
        return False
    registry[key] = task

    def finished(done):
        if registry.get(key) is done:
            registry.pop(key, None)
        if not done.cancelled():
            done.exception()

    task.add_done_callback(finished)
    return True
