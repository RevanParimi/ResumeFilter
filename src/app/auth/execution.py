"""Bound complete login-code operations without moving live SQL sessions."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import Lock


class AuthCodeUnavailable(Exception):
    """Safe admission refusal, before any account lookup or mail work."""


class AuthCodePending(Exception):
    """Caller stopped waiting; delivery/activation may still complete."""


class AuthCodeExecutor:
    def __init__(self, capacity: int, wait_seconds: float):
        self._capacity = capacity
        self._wait_seconds = wait_seconds
        self._pool = ThreadPoolExecutor(max_workers=capacity, thread_name_prefix='auth-code')
        self._lock = Lock()
        self._active = set()
        self._closed = False

    async def run(self, function, /, *args, **kwargs):
        context = copy_context()
        with self._lock:
            if self._closed:
                raise AuthCodeUnavailable('auth_code_executor_closed')
            if len(self._active) >= self._capacity:
                raise AuthCodeUnavailable('auth_code_capacity_exhausted')
            future = self._pool.submit(context.run, function, *args, **kwargs)
            self._active.add(future)
        def finished(done):
            with self._lock:
                self._active.discard(done)
        future.add_done_callback(finished)
        waiting = asyncio.wrap_future(future)
        # Timeout/cancellation does not cancel a running SQL transaction or
        # recall mail. Keep admission until actual completion and consume any
        # late exception without exposing code/address/provider details.
        waiting.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        done, _ = await asyncio.wait({waiting}, timeout=self._wait_seconds)
        if not done:
            raise AuthCodePending()
        return waiting.result()

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=True)

    async def aclose(self) -> None:
        with self._lock:
            self._closed = True
        closing = asyncio.create_task(asyncio.to_thread(self.close))
        cancelled = False
        while True:
            try:
                await asyncio.shield(closing)
                break
            except asyncio.CancelledError:
                cancelled = True
        if cancelled:
            raise asyncio.CancelledError()
