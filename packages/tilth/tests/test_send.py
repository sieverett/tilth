"""Tests for send() behavior."""

from __future__ import annotations

import os

from tilth._metrics import metrics


def setup_function() -> None:
    """Reset state between tests."""
    import tilth._client as c

    metrics.reset()
    c._started = False
    c._queue = None
    c._worker_thread = None


def test_send_returns_none_on_invalid_gateway(monkeypatch: object) -> None:
    """send() returns None and never raises, even with a bad URL."""
    import tilth._client as c

    # Reset module state
    c._started = False
    c._queue = None
    c._worker_thread = None

    os.environ["TILTH_GATEWAY_URL"] = "http://localhost:1"
    os.environ.pop("TILTH_DISABLE", None)

    from tilth import send

    result = send("test", namespace="ns")
    assert result is None

    # Clean up
    os.environ.pop("TILTH_GATEWAY_URL", None)


def test_send_disabled_drops_with_reason(monkeypatch: object) -> None:
    """TILTH_DISABLE=1 causes drops with reason=disabled."""
    import tilth._client as c

    c._started = False
    c._queue = None
    c._worker_thread = None

    os.environ["TILTH_DISABLE"] = "1"

    from tilth import send

    send("test", namespace="ns")
    send("test2", namespace="ns")

    count = metrics.get("tilth_dropped_total", {"reason": "disabled"})
    assert count == 2

    os.environ.pop("TILTH_DISABLE", None)


def test_send_disabled_never_starts_worker() -> None:
    """When disabled, the worker thread should never start."""
    import tilth._client as c

    c._started = False
    c._queue = None
    c._worker_thread = None

    os.environ["TILTH_DISABLE"] = "1"

    from tilth import send

    send("test", namespace="ns")

    assert c._worker_thread is None
    assert c._queue is None

    os.environ.pop("TILTH_DISABLE", None)
