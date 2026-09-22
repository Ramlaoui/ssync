"""Bounded worker pools: local reads must never wait behind SSH commands."""

import asyncio
import functools
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor


class WorkQueueFull(RuntimeError):
    """The server has no capacity for more work; callers may retry later."""


class BoundedThreadPoolExecutor(ThreadPoolExecutor):
    """Bound running and queued work, including cancelled queue entries.

    Cancelling a caller cannot stop a running thread. Keep its reservation until
    the worker finishes (or dequeues a cancelled call), rather than admitting
    an unlimited backlog of abandoned work into ThreadPoolExecutor's queue.
    """

    def __init__(self, max_workers: int, *, max_queue: int, thread_name_prefix: str):
        if max_queue < 0:
            raise ValueError("max_queue must be non-negative")
        super().__init__(max_workers=max_workers, thread_name_prefix=thread_name_prefix)
        self.capacity = max_workers + max_queue
        self._slots = threading.BoundedSemaphore(self.capacity)
        self._stats_lock = threading.Lock()
        self._outstanding = 0
        self._rejected = 0

    def submit(self, fn, /, *args, **kwargs):
        if not self._slots.acquire(blocking=False):
            with self._stats_lock:
                self._rejected += 1
            raise WorkQueueFull("Server worker queue is full. Please retry shortly.")
        with self._stats_lock:
            self._outstanding += 1
        result = Future()

        def invoke():
            if not result.set_running_or_notify_cancel():
                return
            try:
                result.set_result(fn(*args, **kwargs))
            except BaseException as exc:
                result.set_exception(exc)

        def release(worker=None):
            if worker is not None and worker.cancelled():
                result.cancel()
            with self._stats_lock:
                self._outstanding -= 1
            self._slots.release()

        try:
            worker = super().submit(invoke)
        except BaseException:
            release()
            raise
        worker.add_done_callback(release)
        return result

    def stats(self):
        with self._stats_lock:
            return {
                "workers": self._max_workers,
                "capacity": self.capacity,
                "outstanding": self._outstanding,
                "rejected": self._rejected,
            }


def _worker_count(name, default):
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


THREAD_POOL_SIZE = _worker_count(
    "SSYNC_THREAD_POOL_SIZE", min(8, (os.cpu_count() or 1) + 4)
)
BACKGROUND_THREAD_POOL_SIZE = _worker_count("SSYNC_BACKGROUND_THREAD_POOL_SIZE", 4)
LAUNCH_THREAD_POOL_SIZE = _worker_count("SSYNC_LAUNCH_THREAD_POOL_SIZE", 2)

local_executor = BoundedThreadPoolExecutor(
    4, max_queue=64, thread_name_prefix="ssync-local"
)
interactive_executor = BoundedThreadPoolExecutor(
    THREAD_POOL_SIZE, max_queue=16, thread_name_prefix="ssh-interactive"
)
background_executor = BoundedThreadPoolExecutor(
    BACKGROUND_THREAD_POOL_SIZE, max_queue=16, thread_name_prefix="ssh-background"
)
launch_executor = BoundedThreadPoolExecutor(
    LAUNCH_THREAD_POOL_SIZE, max_queue=4, thread_name_prefix="ssh-launch"
)
output_executor = BoundedThreadPoolExecutor(
    2, max_queue=8, thread_name_prefix="ssync-output"
)
transfer_executor = BoundedThreadPoolExecutor(
    2, max_queue=4, thread_name_prefix="ssync-transfer"
)


async def run_local(func, /, *args, **kwargs):
    """Run local filesystem, cache or serialization work independently of SSH."""
    return await asyncio.get_running_loop().run_in_executor(
        local_executor, functools.partial(func, *args, **kwargs)
    )


async def run_remote(func, /, *args, **kwargs):
    """Run blocking remote work with bounded admission and existing SSH limits."""
    return await asyncio.get_running_loop().run_in_executor(
        interactive_executor, functools.partial(func, *args, **kwargs)
    )


async def run_background(func, /, *args, **kwargs):
    """Run refresh work without consuming interactive or local workers."""
    return await asyncio.get_running_loop().run_in_executor(
        background_executor, functools.partial(func, *args, **kwargs)
    )


async def run_output(func, /, *args, **kwargs):
    """Keep large log decompression and transfers separate from cache reads."""
    return await asyncio.get_running_loop().run_in_executor(
        output_executor, functools.partial(func, *args, **kwargs)
    )


async def run_transfer(func, /, *args, **kwargs):
    """A slow SCP/archive transfer must not monopolize cached log decoders."""
    return await asyncio.get_running_loop().run_in_executor(
        transfer_executor, functools.partial(func, *args, **kwargs)
    )
