"""End-to-end tests for the tilth system.

These tests require a running docker-compose stack with real OpenAI keys.
Run via `make e2e` which handles stack lifecycle automatically.
"""

import os
import time

import httpx
import pytest

pytestmark = pytest.mark.e2e


def test_full_write_read_cycle() -> None:
    """Verify the complete write-then-read path through the system."""
    os.environ["TILTH_GATEWAY_URL"] = "http://localhost:8001"
    os.environ["TILTH_IDENTITY"] = "test-writer"

    from tilth import send

    send(
        "Stripe returned card_declined for user 42",
        namespace="checkout",
        severity="warn",
    )
    send(
        "Customer requested refund cited shipping delay",
        namespace="support",
        severity="info",
    )
    send(
        "Invoice paid for subscription tier-2",
        namespace="billing",
        severity="info",
    )

    # Wait for background worker + gateway batch to flush.
    time.sleep(3)

    # Query directly through the query gateway.
    resp = httpx.post(
        "http://localhost:8002/query",
        headers={"x-workload-identity": "ops-copilot"},
        json={"query": "payment failures", "top_k": 3},
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) > 0

    # Top result should be the checkout record.
    top = results[0]
    assert top["namespace"] == "checkout"
    assert "card_declined" in top["content"]
    assert "<retrieved_document" in top["content"]
    assert top["content_hash"] is not None

    # ACL enforcement: a caller restricted to billing shouldn't see
    # the checkout record, even when it's most relevant.
    resp = httpx.post(
        "http://localhost:8002/query",
        headers={"x-workload-identity": "billing-only-reader"},
        json={"query": "payment failures", "top_k": 3},
    )
    assert resp.status_code == 200
    for r in resp.json()["results"]:
        assert r["namespace"] == "billing"


def test_pii_scrubbing_end_to_end() -> None:
    """Verify PII is scrubbed before storage and never returned in queries."""
    os.environ["TILTH_GATEWAY_URL"] = "http://localhost:8001"
    os.environ["TILTH_IDENTITY"] = "test-writer"

    from tilth import send

    send(
        "User email is alice@example.com and card 4111-1111-1111-1111 was declined",
        namespace="checkout",
    )
    time.sleep(3)

    resp = httpx.post(
        "http://localhost:8002/query",
        headers={"x-workload-identity": "ops-copilot"},
        json={"query": "card declined", "top_k": 1},
    )
    text = resp.json()["results"][0]["content"]
    assert "alice@example.com" not in text
    assert "4111-1111-1111-1111" not in text
    assert "<EMAIL_ADDRESS>" in text or "<CREDIT_CARD>" in text


def test_mcp_search_tool_round_trip() -> None:
    """Spawn the MCP server in stdio mode and verify search_tilth returns results.

    This test starts the MCP server as a subprocess, drives it with the MCP
    client SDK, and asserts that search_tilth returns expected results from
    data ingested earlier in the test suite.
    """
    # TODO: Implement once the MCP server subprocess harness is finalized.
    # The test should:
    # 1. Spawn `uv run tilth-mcp` as a subprocess in stdio mode
    # 2. Connect with the MCP client SDK
    # 3. Call the search_tilth tool
    # 4. Assert results match previously ingested data
    pytest.skip("MCP subprocess harness not yet implemented")
