"""Async helpers for background task control."""

from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Optional
import inspect


def background_tasks_disabled() -> bool:
    return os.getenv("SSYNC_DISABLE_BACKGROUND_TASKS", "false").lower() == "true"


def create_task(coro: Awaitable, *, name: Optional[str] = None) -> Optional[asyncio.Task]:
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
