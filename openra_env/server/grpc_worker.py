"""Single-threaded gRPC worker to avoid HTTP/2 contention.

Problem: sync gRPC + asyncio.to_thread deadlocks because multiple threads
compete on one HTTP/2 connection. Sync gRPC without to_thread blocks the
event loop. Per-session channels crash dotnet with 64 TCP connections.

Solution: a single dedicated worker thread processes all gRPC-touching work
sequentially through a queue. Tool functions submit their (sync) callable
to the queue and await an asyncio.Future for the result.

Architecture:
    WebSocket handler -> tool function -> grpc_submit(fn, *args) -> await Future
                                                    |
                              gRPC worker thread (processes queue serially)
                              Makes sync call on shared channel
                              Posts result back via loop.call_soon_threadsafe

This gives us:
- No event loop blocking (tool functions await a Future, not a sync call)
- No thread contention (single thread owns all gRPC calls)
- No ghost threads (no asyncio.to_thread)
- Shared channel (one HTTP/2 connection, no dotnet crash)
"""

import asyncio
import logging
import queue
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Sentinel to stop the worker thread on shutdown.
_STOP = object()

# Module-level queue: (callable, args, kwargs, asyncio.Future, asyncio.Loop)
_work_queue: queue.Queue = queue.Queue()

# Worker thread reference (started once).
_worker_thread: threading.Thread | None = None
_started = False
_lock = threading.Lock()


def _worker_loop() -> None:
    """Run forever, pulling work items from the queue and executing them.

    Each item is a tuple of (fn, args, kwargs, future, loop).
    The result (or exception) is posted back to the asyncio event loop
    via loop.call_soon_threadsafe so the awaiting coroutine resumes.
    """
    while True:
        item = _work_queue.get()
        if item is _STOP:
            break
        fn, args, kwargs, future, loop = item
        try:
            result = fn(*args, **kwargs)
            loop.call_soon_threadsafe(future.set_result, result)
        except BaseException as exc:
            loop.call_soon_threadsafe(future.set_exception, exc)


def start_worker() -> None:
    """Start the gRPC worker thread (idempotent)."""
    global _worker_thread, _started
    with _lock:
        if _started:
            return
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="grpc-worker",
            daemon=True,
        )
        _worker_thread.start()
        _started = True
        logger.info("gRPC worker thread started")


def stop_worker() -> None:
    """Stop the gRPC worker thread (idempotent)."""
    global _worker_thread, _started
    with _lock:
        if not _started:
            return
        _work_queue.put(_STOP)
        if _worker_thread is not None:
            _worker_thread.join(timeout=5.0)
        _worker_thread = None
        _started = False
        logger.info("gRPC worker thread stopped")


async def grpc_submit(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """Submit a sync callable to the gRPC worker thread and await its result.

    The callable runs in the single worker thread (no HTTP/2 contention).
    The calling coroutine suspends until the result is posted back.

    Raises whatever exception the callable raises.
    """
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    _work_queue.put((fn, args, kwargs, future, loop))
    return await future
