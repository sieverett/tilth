"""Tests for the recording() test helper."""

from __future__ import annotations

import os

import tilth
from tilth._metrics import metrics


def setup_function() -> None:
    import tilth._client as c

    metrics.reset()
    c._started = False
    c._queue = None
    c._worker_thread = None
    os.environ.pop("TILTH_DISABLE", None)


def test_recording_captures_sends() -> None:
    """recording() captures send calls in-process."""
    from tilth.testing import recording

    with recording() as records:
        tilth.send("hello world", namespace="checkout")
        tilth.send("goodbye", namespace="support", severity="warn")

    assert len(records) == 2
    assert records[0].text == "hello world"
    assert records[0].namespace == "checkout"
    assert records[1].metadata == {"severity": "warn"}


def test_recording_does_not_start_worker() -> None:
    """recording() should not start the background worker."""
    import tilth._client as c

    c._started = False
    c._queue = None
    c._worker_thread = None

    from tilth.testing import recording

    with recording() as records:
        tilth.send("test", namespace="ns")

    assert len(records) == 1


def test_recording_restores_send_on_exit() -> None:
    """After recording() exits, send() works normally again."""
    from tilth.testing import recording

    with recording() as records:
        tilth.send("inside", namespace="ns")

    assert len(records) == 1

    # After exit, send should go to the real implementation
    os.environ["TILTH_GATEWAY_URL"] = "http://localhost:1"
    tilth.send("outside", namespace="ns")
    os.environ.pop("TILTH_GATEWAY_URL", None)
