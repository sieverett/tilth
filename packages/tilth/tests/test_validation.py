"""Tests for input validation."""

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
    os.environ["TILTH_GATEWAY_URL"] = "http://localhost:1"


def teardown_function() -> None:
    os.environ.pop("TILTH_GATEWAY_URL", None)


def test_disallowed_metadata_keys_drop() -> None:
    """Metadata keys not in the allowlist cause a drop."""
    from tilth import send

    send("hello", namespace="ns", foo="bar")

    assert metrics.get("tilth_dropped_total", {"reason": "invalid"}) == 1


def test_text_over_32kb_drops() -> None:
    """Text exceeding 32KB is dropped."""
    from tilth import send

    big_text = "x" * (32 * 1024 + 1)
    send(big_text, namespace="ns")

    assert metrics.get("tilth_dropped_total", {"reason": "invalid"}) == 1


def test_empty_text_drops() -> None:
    """Empty text is dropped."""
    from tilth import send

    send("", namespace="ns")

    assert metrics.get("tilth_dropped_total", {"reason": "invalid"}) == 1


def test_empty_namespace_drops() -> None:
    """Empty namespace is dropped."""
    from tilth import send

    send("hello", namespace="")

    assert metrics.get("tilth_dropped_total", {"reason": "invalid"}) == 1


def test_allowed_metadata_keys_accepted() -> None:
    """Valid metadata keys don't cause a drop."""
    from tilth import send

    send(
        "hello",
        namespace="ns",
        env="prod",
        severity="warn",
        trace_id="abc",
        subject_id="user1",
        ttl_days=30,
    )

    assert metrics.get("tilth_dropped_total", {"reason": "invalid"}) == 0
    assert metrics.get("tilth_sent_total", {"namespace": "ns"}) == 1
