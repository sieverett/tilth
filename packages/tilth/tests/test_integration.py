"""Integration tests using respx to mock HTTP."""

from __future__ import annotations

import os
import time

import httpx
import respx
from tilth._metrics import metrics


def setup_function() -> None:
    import tilth._client as c

    metrics.reset()
    c._started = False
    c._queue = None
    c._worker_thread = None
    os.environ.pop("TILTH_DISABLE", None)


def test_send_posts_to_ingest_with_expected_body() -> None:
    """send() results in a POST to /ingest with the correct body."""
    import tilth._client as c

    c._started = False
    c._queue = None
    c._worker_thread = None

    os.environ["TILTH_GATEWAY_URL"] = "http://testgateway:8001"
    os.environ["TILTH_IDENTITY"] = "test-svc"

    from tilth import send

    with respx.mock(base_url="http://testgateway:8001") as mock:
        route = mock.post("/ingest").mock(
            return_value=httpx.Response(202, json={"status": "accepted"})
        )

        send("hello world", namespace="checkout", severity="warn")

        # Wait for the worker to process
        deadline = time.monotonic() + 2.0
        while not route.called and time.monotonic() < deadline:
            time.sleep(0.05)

        assert route.called
        request = route.calls[0].request
        body = request.content.decode()
        assert "hello world" in body
        assert "checkout" in body
        assert "severity" in body

    os.environ.pop("TILTH_GATEWAY_URL", None)
    os.environ.pop("TILTH_IDENTITY", None)


def test_workload_identity_header_set() -> None:
    """x-workload-identity header is set from TILTH_IDENTITY."""
    import tilth._client as c

    c._started = False
    c._queue = None
    c._worker_thread = None

    os.environ["TILTH_GATEWAY_URL"] = "http://testgateway:8002"
    os.environ["TILTH_IDENTITY"] = "my-service"

    from tilth import send

    with respx.mock(base_url="http://testgateway:8002") as mock:
        route = mock.post("/ingest").mock(
            return_value=httpx.Response(202, json={"status": "accepted"})
        )

        send("test", namespace="ns")

        deadline = time.monotonic() + 2.0
        while not route.called and time.monotonic() < deadline:
            time.sleep(0.05)

        assert route.called
        request = route.calls[0].request
        assert request.headers.get("x-workload-identity") == "my-service"
        assert "tilth/" in request.headers.get("user-agent", "")

    os.environ.pop("TILTH_GATEWAY_URL", None)
    os.environ.pop("TILTH_IDENTITY", None)
