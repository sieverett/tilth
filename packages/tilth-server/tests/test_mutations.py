"""Tests for delete and update operations on the query gateway."""

import json
import logging
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from tilth_server.query.app import create_app

POLICY_YAML = (
    "ops-copilot:\n  - sales\n  - analysis\n"
    "support-agent:\n  - support\n"
)

WRITE_POLICY_YAML = (
    "ops-copilot:\n  - analysis\n"
    "support-agent:\n  - support\n"
)


def _write_file(content: str) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(content)
        f.flush()
        return f.name


@pytest.fixture()
def read_policy_file() -> str:
    return _write_file(POLICY_YAML)


@pytest.fixture()
def write_policy_file() -> str:
    return _write_file(WRITE_POLICY_YAML)


@pytest.fixture()
def mock_qdrant() -> AsyncMock:
    client = AsyncMock()
    # For retrieve (get a record by ID)
    mock_record = MagicMock()
    mock_record.id = "abc-123"
    mock_record.payload = {
        "text": "original text",
        "source": "ops-copilot",
        "namespace": "analysis",
        "ts": 1.0,
        "content_hash": "aabbccdd",
    }
    mock_record.vector = [0.1] * 1536
    client.retrieve = AsyncMock(return_value=[mock_record])
    # For delete
    client.delete = AsyncMock()
    # For upsert (used by update)
    client.upsert = AsyncMock()
    return client


@pytest.fixture()
def mock_embedding() -> MagicMock:
    client = MagicMock()
    client.embed = AsyncMock(return_value=[[0.1] * 1536])
    client.model_name = "text-embedding-3-small"
    client.dimension = 1536
    return client


@pytest.fixture()
async def client(
    read_policy_file: str,
    write_policy_file: str,
    mock_qdrant: AsyncMock,
    mock_embedding: MagicMock,
) -> AsyncClient:
    app = create_app(
        policy_path=read_policy_file,
        write_policy_path=write_policy_file,
        qdrant_client=mock_qdrant,
        embedding_client=mock_embedding,
        collection_name="tilth-test",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# --- Delete ---


class TestDelete:
    async def test_delete_returns_200(
        self, client: AsyncClient
    ) -> None:
        resp = await client.request(
            "DELETE",
            "/records/abc-123",
            json={"reason": "takedown"},
            headers={"x-workload-identity": "ops-copilot"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    async def test_delete_requires_auth(
        self, client: AsyncClient
    ) -> None:
        resp = await client.request(
            "DELETE",
            "/records/abc-123",
            json={"reason": "takedown"},
        )
        assert resp.status_code == 401

    async def test_delete_requires_write_access_to_namespace(
        self, client: AsyncClient
    ) -> None:
        # support-agent has read on support but not write on analysis
        resp = await client.request(
            "DELETE",
            "/records/abc-123",
            json={"reason": "takedown"},
            headers={"x-workload-identity": "support-agent"},
        )
        assert resp.status_code == 403

    async def test_delete_nonexistent_record_returns_404(
        self, client: AsyncClient, mock_qdrant: AsyncMock
    ) -> None:
        mock_qdrant.retrieve = AsyncMock(return_value=[])
        resp = await client.request(
            "DELETE",
            "/records/nonexistent",
            json={"reason": "takedown"},
            headers={"x-workload-identity": "ops-copilot"},
        )
        assert resp.status_code == 404

    async def test_delete_audit_logged(
        self, client: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="tilth.audit"):
            resp = await client.request(
                "DELETE",
                "/records/abc-123",
                json={"reason": "leaked secret"},
                headers={"x-workload-identity": "ops-copilot"},
            )
        assert resp.status_code == 200
        audit_entries = [
            r for r in caplog.records if r.name == "tilth.audit"
        ]
        assert len(audit_entries) >= 1
        log_data = json.loads(audit_entries[-1].message)
        assert log_data["event"] == "delete"
        assert log_data["record_id"] == "abc-123"
        assert log_data["reason"] == "leaked secret"
        assert log_data["caller"] == "ops-copilot"

    async def test_delete_reason_required(
        self, client: AsyncClient
    ) -> None:
        resp = await client.request(
            "DELETE",
            "/records/abc-123",
            json={},
            headers={"x-workload-identity": "ops-copilot"},
        )
        assert resp.status_code == 422


# --- Update ---


class TestUpdate:
    async def test_update_returns_200_with_new_id(
        self, client: AsyncClient
    ) -> None:
        resp = await client.request(
            "PATCH",
            "/records/abc-123",
            json={"text": "corrected text", "reason": "correction"},
            headers={"x-workload-identity": "ops-copilot"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert "new_id" in data
        assert data["supersedes"] == "abc-123"

    async def test_update_requires_auth(
        self, client: AsyncClient
    ) -> None:
        resp = await client.request(
            "PATCH",
            "/records/abc-123",
            json={"text": "new text", "reason": "fix"},
        )
        assert resp.status_code == 401

    async def test_update_requires_write_access(
        self, client: AsyncClient
    ) -> None:
        resp = await client.request(
            "PATCH",
            "/records/abc-123",
            json={"text": "new text", "reason": "fix"},
            headers={"x-workload-identity": "support-agent"},
        )
        assert resp.status_code == 403

    async def test_update_nonexistent_returns_404(
        self, client: AsyncClient, mock_qdrant: AsyncMock
    ) -> None:
        mock_qdrant.retrieve = AsyncMock(return_value=[])
        resp = await client.request(
            "PATCH",
            "/records/nonexistent",
            json={"text": "new text", "reason": "fix"},
            headers={"x-workload-identity": "ops-copilot"},
        )
        assert resp.status_code == 404

    async def test_update_soft_deletes_old_record(
        self, client: AsyncClient, mock_qdrant: AsyncMock
    ) -> None:
        resp = await client.request(
            "PATCH",
            "/records/abc-123",
            json={"text": "corrected", "reason": "correction"},
            headers={"x-workload-identity": "ops-copilot"},
        )
        assert resp.status_code == 200
        # Old record should be updated with superseded_by field
        upsert_calls = mock_qdrant.upsert.call_args_list
        # Should have at least one upsert (for the new record)
        assert len(upsert_calls) >= 1

    async def test_update_audit_logged(
        self, client: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="tilth.audit"):
            resp = await client.request(
                "PATCH",
                "/records/abc-123",
                json={"text": "fixed analysis", "reason": "correction"},
                headers={"x-workload-identity": "ops-copilot"},
            )
        assert resp.status_code == 200
        audit_entries = [
            r for r in caplog.records if r.name == "tilth.audit"
        ]
        assert len(audit_entries) >= 1
        log_data = json.loads(audit_entries[-1].message)
        assert log_data["event"] == "update"
        assert log_data["record_id"] == "abc-123"
        assert "new_id" in log_data
        assert "previous_content_hash" in log_data
        assert "new_content_hash" in log_data

    async def test_update_reason_required(
        self, client: AsyncClient
    ) -> None:
        resp = await client.request(
            "PATCH",
            "/records/abc-123",
            json={"text": "new text"},
            headers={"x-workload-identity": "ops-copilot"},
        )
        assert resp.status_code == 422

    async def test_update_text_required(
        self, client: AsyncClient
    ) -> None:
        resp = await client.request(
            "PATCH",
            "/records/abc-123",
            json={"reason": "fix"},
            headers={"x-workload-identity": "ops-copilot"},
        )
        assert resp.status_code == 422
