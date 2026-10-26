"""Per-service, queue-free admission for disposable PDF work only.

No database sessions or provider calls belong in these threads. The parser
observes the cancellation signal while supervising its disposable child.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from threading import Event, Lock


class PdfUnavailable(Exception):
    """Safe retryable admission refusal, without input or worker details."""


class PdfWorkCancelled(BaseException):
    """Internal stop signal that parser error adapters must not swallow."""


_stop: ContextVar[Event | None] = ContextVar('pdf_stop', default=None)


def check_pdf_cancelled() -> None:
    signal = _stop.get()
    if signal is not None and signal.is_set():
        raise PdfWorkCancelled()


class PdfExecutor:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError('PDF capacity must be positive')
        self._capacity = capacity
        self._pool = ThreadPoolExecutor(max_workers=capacity, thread_name_prefix='pdf')
        self._lock = Lock()
        self._active = {}
        self._closed = False

    async def run(self, function, /, *args, **kwargs):
        signal = Event()
        def work():
            token = _stop.set(signal)
            try:
                check_pdf_cancelled()
                result = function(*args, **kwargs)
                check_pdf_cancelled()
                return result
            finally:
                _stop.reset(token)

        with self._lock:
            if self._closed:
                raise PdfUnavailable('pdf_executor_closed')
            if len(self._active) >= self._capacity:
                raise PdfUnavailable('pdf_capacity_exhausted')
            future = self._pool.submit(work)
            self._active[future] = signal
        def finished(done):
            with self._lock:
                self._active.pop(done, None)
        future.add_done_callback(finished)
        waiting = asyncio.wrap_future(future)
        # A canceled HTTP task leaves the child supervisor running until its
        # cleanup completes; consume a late refusal without an orphan warning.
        waiting.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            return await asyncio.shield(waiting)
        except asyncio.CancelledError:
            signal.set()
            raise
        except PdfWorkCancelled:
            raise PdfUnavailable('pdf_executor_closed') from None

    def close(self) -> None:
        """Join from a non-event-loop thread; also used by synchronous owners."""
        with self._lock:
            self._closed = True
            for signal in self._active.values():
                signal.set()
        self._pool.shutdown(wait=True)

    async def aclose(self) -> None:
        # Closing admission precedes the first await, including when no work
        # has started. Repeated close and cancellation still finish cleanup.
        with self._lock:
            self._closed = True
            for signal in self._active.values():
                signal.set()
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
