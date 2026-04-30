"""Tests for the tilth-mcp server.

Tests the search_tilth tool function directly, mocking the HTTP boundary.
Does NOT test MCP transport — tests the behavior of the tool itself.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

# These will be importable once the implementation exists.
# For now, the tests define the expected behavior.

GATEWAY_URL = "http://fake-gateway:8000"

SAMPLE_GATEWAY_RESPONSE: dict[str, Any] = {
    "results": [
        {
            "content": "<retrieved_document>checkout event</retrieved_document>",
            "source": "checkout-service",
            "namespace": "checkout",
            "ts": 1700000000.0,
            "score": 0.95,
            "content_hash": "abc123def456",
        },
        {
            "content": "<retrieved_document>support ticket</retrieved_document>",
            "source": "support-service",
            "namespace": "support",
            "ts": 1700000001.0,
            "score": 0.88,
            "content_hash": "789ghi012jkl",
        },
    ]
}


@pytest.fixture()
def gateway_url(monkeypatch: pytest.MonkeyPatch) -> str:
    """Set up env vars and return gateway URL."""
    monkeypatch.setenv("TILTH_QUERY_GATEWAY_URL", GATEWAY_URL)
    return GATEWAY_URL


@pytest.fixture()
def dev_identity(monkeypatch: pytest.MonkeyPatch) -> str:
    """Set explicit dev identity."""
    identity = "test-user@example.com"
    monkeypatch.setenv("TILTH_MCP_DEV_IDENTITY", identity)
    return identity


async def _call_search_tilth(
    gateway_url: str,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Helper that calls the search_tilth tool function directly.

    Imports lazily so env vars are set before module-level reads.
    """
    from tilth_mcp.server import _search_tilth_impl

    async with httpx.AsyncClient(timeout=10.0) as client:
        return await _search_tilth_impl(
            client=client,
            gateway_url=gateway_url,
            identity="test-user@example.com",
            **kwargs,
        )


class TestToolDescription:
    """Tool description includes namespace documentation."""

    def test_description_includes_namespace_docs(self, gateway_url: str) -> None:
        from tilth_mcp.server import TOOL_DESCRIPTION

        assert "checkout" in TOOL_DESCRIPTION
        assert "payment and order events" in TOOL_DESCRIPTION
        assert "support" in TOOL_DESCRIPTION
        assert "customer support interactions" in TOOL_DESCRIPTION
        assert "billing" in TOOL_DESCRIPTION
        assert "invoice, subscription, and refund events" in TOOL_DESCRIPTION


class TestTopKCap:
    """top_k is capped at 10 even if caller requests more."""

    @respx.mock
    async def test_top_k_capped_at_10(self, gateway_url: str) -> None:
        route = respx.post(f"{GATEWAY_URL}/query").mock(
            return_value=httpx.Response(200, json=SAMPLE_GATEWAY_RESPONSE)
        )

        await _call_search_tilth(gateway_url, query="test", top_k=50)

        request_body = route.calls[0].request.content
        import json

        body = json.loads(request_body)
        assert body["top_k"] <= 10

    @respx.mock
    async def test_top_k_within_range_passes_through(
        self, gateway_url: str
    ) -> None:
        route = respx.post(f"{GATEWAY_URL}/query").mock(
            return_value=httpx.Response(200, json=SAMPLE_GATEWAY_RESPONSE)
        )

        await _call_search_tilth(gateway_url, query="test", top_k=3)

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["top_k"] == 3


class TestSuccessfulQuery:
    """Successful query returns results in documented shape with content_hash."""

    @respx.mock
    async def test_returns_documented_shape(self, gateway_url: str) -> None:
        respx.post(f"{GATEWAY_URL}/query").mock(
            return_value=httpx.Response(200, json=SAMPLE_GATEWAY_RESPONSE)
        )

        results = await _call_search_tilth(gateway_url, query="checkout events")

        assert len(results) == 2

        first = results[0]
        assert "content" in first
        assert "source" in first
        assert "namespace" in first
        assert "timestamp" in first
        assert "score" in first
        assert "content_hash" in first

        expected_content = (
            "<retrieved_document>checkout event</retrieved_document>"
        )
        assert first["content"] == expected_content
        assert first["source"] == "checkout-service"
        assert first["namespace"] == "checkout"
        assert first["timestamp"] == 1700000000.0
        assert first["score"] == 0.95
        assert first["content_hash"] == "abc123def456"


class TestErrorMapping:
    """Gateway errors are mapped to agent-safe messages."""

    @respx.mock
    async def test_401_raises_tool_error_with_auth_message(
        self, gateway_url: str
    ) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        respx.post(f"{GATEWAY_URL}/query").mock(
            return_value=httpx.Response(401, json={"detail": "unauthorized"})
        )

        with pytest.raises(ToolError, match="memory service authentication failed"):
            await _call_search_tilth(gateway_url, query="test")

    @respx.mock
    async def test_403_raises_permission_error(self, gateway_url: str) -> None:
        respx.post(f"{GATEWAY_URL}/query").mock(
            return_value=httpx.Response(403, json={"detail": "forbidden"})
        )

        with pytest.raises(
            PermissionError,
            match="not authorized to read the requested namespaces",
        ):
            await _call_search_tilth(gateway_url, query="test")

    @respx.mock
    async def test_500_raises_generic_tool_error(self, gateway_url: str) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        respx.post(f"{GATEWAY_URL}/query").mock(
            return_value=httpx.Response(500, json={"detail": "internal error"})
        )

        with pytest.raises(ToolError, match="memory search failed"):
            await _call_search_tilth(gateway_url, query="test")

    @respx.mock
    async def test_network_error_raises_temporarily_unavailable(
        self, gateway_url: str
    ) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        respx.post(f"{GATEWAY_URL}/query").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with pytest.raises(ToolError, match="temporarily unavailable"):
            await _call_search_tilth(gateway_url, query="test")


class TestIdentityHeader:
    """x-workload-identity header is set on every gateway call."""

    @respx.mock
    async def test_identity_from_env_var(
        self, gateway_url: str, dev_identity: str
    ) -> None:
        route = respx.post(f"{GATEWAY_URL}/query").mock(
            return_value=httpx.Response(200, json=SAMPLE_GATEWAY_RESPONSE)
        )

        # Call with the explicit identity from the fixture
        from tilth_mcp.server import _search_tilth_impl

        async with httpx.AsyncClient(timeout=10.0) as client:
            await _search_tilth_impl(
                client=client,
                gateway_url=gateway_url,
                identity=dev_identity,
                query="test",
            )

        request = route.calls[0].request
        assert request.headers["x-workload-identity"] == dev_identity

    @respx.mock
    async def test_fallback_identity(self, gateway_url: str) -> None:
        route = respx.post(f"{GATEWAY_URL}/query").mock(
            return_value=httpx.Response(200, json=SAMPLE_GATEWAY_RESPONSE)
        )

        from tilth_mcp.server import _search_tilth_impl

        async with httpx.AsyncClient(timeout=10.0) as client:
            await _search_tilth_impl(
                client=client,
                gateway_url=gateway_url,
                identity="dev-stdio-user",
                query="test",
            )

        request = route.calls[0].request
        assert request.headers["x-workload-identity"] == "dev-stdio-user"


class TestFilterForwarding:
    """severity, env, subject_id filters are forwarded correctly."""

    @respx.mock
    async def test_all_filters_forwarded(self, gateway_url: str) -> None:
        route = respx.post(f"{GATEWAY_URL}/query").mock(
            return_value=httpx.Response(200, json=SAMPLE_GATEWAY_RESPONSE)
        )

        await _call_search_tilth(
            gateway_url,
            query="test",
            severity="error",
            env="prod",
            subject_id="customer-123",
        )

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["filters"]["severity"] == "error"
        assert body["filters"]["env"] == "prod"
        assert body["filters"]["subject_id"] == "customer-123"

    @respx.mock
    async def test_no_filters_when_none(self, gateway_url: str) -> None:
        route = respx.post(f"{GATEWAY_URL}/query").mock(
            return_value=httpx.Response(200, json=SAMPLE_GATEWAY_RESPONSE)
        )

        await _call_search_tilth(gateway_url, query="test")

        import json

        body = json.loads(route.calls[0].request.content)
        assert "filters" not in body

    @respx.mock
    async def test_partial_filters(self, gateway_url: str) -> None:
        route = respx.post(f"{GATEWAY_URL}/query").mock(
            return_value=httpx.Response(200, json=SAMPLE_GATEWAY_RESPONSE)
        )

        await _call_search_tilth(
            gateway_url, query="test", severity="warn"
        )

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["filters"] == {"severity": "warn"}

    @respx.mock
    async def test_namespaces_forwarded(self, gateway_url: str) -> None:
        route = respx.post(f"{GATEWAY_URL}/query").mock(
            return_value=httpx.Response(200, json=SAMPLE_GATEWAY_RESPONSE)
        )

        await _call_search_tilth(
            gateway_url, query="test", namespaces=["checkout", "billing"]
        )

        import json

        body = json.loads(route.calls[0].request.content)
        assert body["namespaces"] == ["checkout", "billing"]


class TestIdentityResolution:
    """Identity resolution from env var with fallback."""

    def test_resolve_identity_from_env(
        self, gateway_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TILTH_MCP_DEV_IDENTITY", "custom-user")
        from tilth_mcp.server import resolve_identity

        assert resolve_identity() == "custom-user"

    def test_resolve_identity_fallback(
        self, gateway_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TILTH_MCP_DEV_IDENTITY", raising=False)
        from tilth_mcp.server import resolve_identity

        assert resolve_identity() == "dev-stdio-user"
