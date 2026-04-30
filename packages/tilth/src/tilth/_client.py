"""Core client — queue, worker, send logic."""

from __future__ import annotations

import atexit
import contextlib
import logging
import queue
import threading
import time
from typing import Any

import httpx

from tilth._config import gateway_url, identity, is_disabled, queue_size, timeout_s
from tilth._metrics import metrics

log = logging.getLogger("tilth")

ALLOWED_METADATA_KEYS = frozenset(
    {"env", "severity", "trace_id", "subject_id", "ttl_days"}
)
MAX_TEXT_BYTES = 32 * 1024

_SENTINEL = object()

_queue: queue.Queue[Any] | None = None
_worker_thread: threading.Thread | None = None
_lock = threading.Lock()
_started = False


def _ensure_started() -> queue.Queue[Any]:
    """Lazily start the worker thread on first send()."""
    global _queue, _worker_thread, _started  # noqa: PLW0603
    if _started and _queue is not None:
        return _queue
    with _lock:
        if _started and _queue is not None:
            return _queue
        _queue = queue.Queue(maxsize=queue_size())
        _worker_thread = threading.Thread(target=_worker, daemon=True)
        _worker_thread.start()
        atexit.register(_shutdown)
        _started = True
        return _queue


def _worker() -> None:
    """Background worker — pulls from queue, POSTs to gateway."""
    try:
        client = httpx.Client(timeout=timeout_s())
    except Exception:
        log.debug("tilth: failed to create HTTP client", exc_info=True)
        return

    try:
        while True:
            item = _queue.get()  # type: ignore[union-attr]
            if item is _SENTINEL:
                _queue.task_done()  # type: ignore[union-attr]
                return
            t0, payload = item
            url = gateway_url()
            if not url:
                metrics.inc(
                    "tilth_dropped_total", {"reason": "gateway_error"}
                )
                log.debug("tilth: no gateway URL configured, dropping record")
                _queue.task_done()  # type: ignore[union-attr]
                continue
            headers: dict[str, str] = {"user-agent": "tilth/0.1.0"}
            ident = identity()
            if ident:
                headers["x-workload-identity"] = ident
            try:
                resp = client.post(
                    f"{url}/ingest", json=payload, headers=headers
                )
                if resp.status_code < 300:
                    latency = time.monotonic() - t0
                    metrics.set_gauge("tilth_flush_latency_seconds", latency)
                else:
                    metrics.inc(
                        "tilth_dropped_total", {"reason": "gateway_error"}
                    )
                    log.debug(
                        "tilth: gateway returned %d", resp.status_code
                    )
            except Exception:
                metrics.inc(
                    "tilth_dropped_total", {"reason": "gateway_error"}
                )
                log.debug("tilth: gateway request failed", exc_info=True)
            finally:
                _queue.task_done()  # type: ignore[union-attr]
    except Exception:
        log.debug("tilth: worker crashed", exc_info=True)
    finally:
        client.close()


def _shutdown() -> None:
    """Atexit handler — push sentinel, wait up to 2 seconds."""
    if _queue is None:
        return
    try:
        _queue.put_nowait(_SENTINEL)
    except queue.Full:
        return
    with contextlib.suppress(Exception):
        _queue.join()


def send(text: str, *, namespace: str, **metadata: Any) -> None:
    """Fire-and-forget send. Never raises."""
    try:
        if is_disabled():
            metrics.inc("tilth_dropped_total", {"reason": "disabled"})
            return

        # Validate
        if not text or not namespace:
            metrics.inc("tilth_dropped_total", {"reason": "invalid"})
            return

        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            metrics.inc("tilth_dropped_total", {"reason": "invalid"})
            return

        bad_keys = set(metadata.keys()) - ALLOWED_METADATA_KEYS
        if bad_keys:
            metrics.inc("tilth_dropped_total", {"reason": "invalid"})
            log.debug("tilth: disallowed metadata keys: %s", bad_keys)
            return

        # Enqueue
        q = _ensure_started()
        payload = {
            "text": text,
            "namespace": namespace,
            "metadata": metadata,
        }
        try:
            q.put_nowait((time.monotonic(), payload))
            metrics.inc("tilth_sent_total", {"namespace": namespace})
            metrics.set_gauge("tilth_queue_depth", float(q.qsize()))
        except queue.Full:
            metrics.inc("tilth_dropped_total", {"reason": "queue_full"})

    except Exception:
        metrics.inc("tilth_dropped_total", {"reason": "invalid"})
        log.debug("tilth: unexpected error in send()", exc_info=True)


async def asend(text: str, *, namespace: str, **metadata: Any) -> None:
    """Async wrapper — just calls send() synchronously."""
    send(text, namespace=namespace, **metadata)
