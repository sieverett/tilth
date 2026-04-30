"""Tests for queue overflow and worker behavior."""

from __future__ import annotations

import os

from tilth._metrics import metrics


def setup_function() -> None:
    import tilth._client as c

    metrics.reset()
    c._started = False
    c._queue = None
    c._worker_thread = None
    os.environ.pop("TILTH_DISABLE", None)


def test_queue_overflow_drops_with_reason() -> None:
    """Sending 20,000 records with queue size 100 drops ~19,900."""
    os.environ["TILTH_QUEUE_SIZE"] = "100"
    os.environ["TILTH_GATEWAY_URL"] = "http://localhost:1"

    import tilth._client as c

    c._started = False
    c._queue = None
    c._worker_thread = None

    from tilth import send

    for i in range(20_000):
        send(f"record {i}", namespace="ns")

    sent = metrics.get("tilth_sent_total", {"namespace": "ns"})
    dropped = metrics.get("tilth_dropped_total", {"reason": "queue_full"})

    # The queue can hold 100 items. Some will be consumed by the worker
    # before we finish, so sent may be somewhat more than 100.
    # But drops should be the vast majority.
    assert dropped > 19_000
    assert sent + dropped == 20_000

    os.environ.pop("TILTH_QUEUE_SIZE", None)
    os.environ.pop("TILTH_GATEWAY_URL", None)
