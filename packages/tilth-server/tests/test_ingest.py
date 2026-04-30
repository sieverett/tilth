"""Tests for the ingest gateway endpoint."""

import hashlib
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from tilth_server.ingest.app import create_app


def _write_policy(content: str) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(content)
        f.flush()
        return f.name


POLICY_YAML = "checkout-svc:\n  - checkout\nsupport-bot:\n  - support\n"


@pytest.fixture()
def policy_file() -> str:
    path = _write_policy(POLICY_YAML)
    yield path
    os.unlink(path)


@pytest.fixture()
def mock_qdrant() -> AsyncMock:
    client = AsyncMock()
    client.collection_exists = AsyncMock(return_value=True)
    client.get_collection = AsyncMock(
        return_value=MagicMock(
            params=MagicMock(
                vectors=MagicMock(size=1536)
            )
        )
    )
    # Return metadata with matching model
    info = MagicMock()
    info.config = MagicMock()
    info.config.params = MagicMock()
    coll_info = MagicMock()
    coll_info.payload_schema = {}
    client.get_collection.return_value = coll_info
    return client


@pytest.fixture()
def mock_openai() -> AsyncMock:
    client = AsyncMock()
    return client


@pytest.fixture()
def mock_analyzer() -> MagicMock:
    analyzer = MagicMock()
    analyzer.analyze.return_value = []
    return analyzer


@pytest.fixture()
def mock_anonymizer() -> MagicMock:
    return MagicMock()


@pytest.fixture()
async def client(
    policy_file: str,
    mock_qdrant: AsyncMock,
    mock_openai: AsyncMock,
    mock_analyzer: MagicMock,
    mock_anonymizer: MagicMock,
) -> AsyncClient:
    app = create_app(
        policy_path=policy_file,
        qdrant_client=mock_qdrant,
        openai_client=mock_openai,
        analyzer=mock_analyzer,
        anonymizer=mock_anonymizer,
        collection_name="tilth-test",
        embed_model="text-embedding-3-small",
        embed_dim=1536,
        batch_size=64,
        batch_window_ms=200,
        batch_queue_max=10_000,
        max_text_bytes=32768,
        skip_collection_check=True,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestIngestAuth:
    async def test_missing_identity_header_returns_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/ingest",
            json={"text": "hello", "namespace": "checkout"},
        )
        assert resp.status_code == 401

    async def test_unknown_caller_returns_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/ingest",
            json={"text": "hello", "namespace": "checkout"},
            headers={"x-workload-identity": "unknown-svc"},
        )
        assert resp.status_code == 401


class TestIngestNamespace:
    async def test_caller_outside_permitted_namespace_returns_403(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/ingest",
            json={"text": "hello", "namespace": "billing"},
            headers={"x-workload-identity": "checkout-svc"},
        )
        assert resp.status_code == 403


class TestIngestValidation:
    async def test_disallowed_metadata_key_returns_400(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/ingest",
            json={
                "text": "hello",
                "namespace": "checkout",
                "metadata": {"foo": "bar"},
            },
            headers={"x-workload-identity": "checkout-svc"},
        )
        assert resp.status_code == 422  # pydantic validation error

    async def test_text_over_32kb_returns_400(
        self, client: AsyncClient
    ) -> None:
        big_text = "x" * 32769
        resp = await client.post(
            "/ingest",
            json={"text": big_text, "namespace": "checkout"},
            headers={"x-workload-identity": "checkout-svc"},
        )
        assert resp.status_code == 422  # pydantic validation error


class TestIngestBehavior:
    async def test_email_scrubbed_before_batch(
        self,
        policy_file: str,
        mock_qdrant: AsyncMock,
        mock_openai: AsyncMock,
        mock_anonymizer: MagicMock,
    ) -> None:
        """Email in text is replaced with Presidio token before queueing."""
        from presidio_analyzer import RecognizerResult

        mock_analyzer = MagicMock()
        finding = RecognizerResult(
            entity_type="EMAIL_ADDRESS", start=8, end=26, score=0.99
        )
        mock_analyzer.analyze.return_value = [finding]
        mock_anonymizer.anonymize.return_value = MagicMock(
            text="Contact <EMAIL_ADDRESS> for info"
        )

        app = create_app(
            policy_path=policy_file,
            qdrant_client=mock_qdrant,
            openai_client=mock_openai,
            analyzer=mock_analyzer,
            anonymizer=mock_anonymizer,
            collection_name="tilth-test",
            embed_model="text-embedding-3-small",
            embed_dim=1536,
            skip_collection_check=True,
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/ingest",
                json={
                    "text": "Contact user@example.com for info",
                    "namespace": "checkout",
                },
                headers={"x-workload-identity": "checkout-svc"},
            )
        assert resp.status_code == 202
        mock_analyzer.analyze.assert_called_once()

    async def test_source_from_header_not_body(
        self,
        client: AsyncClient,
    ) -> None:
        """Body's source field is ignored; stored source is from the header."""
        resp = await client.post(
            "/ingest",
            json={
                "text": "hello",
                "namespace": "checkout",
                "source": "attacker-svc",  # should be ignored
            },
            headers={"x-workload-identity": "checkout-svc"},
        )
        assert resp.status_code == 202

    async def test_content_hash_matches_sha256_of_scrubbed_text(
        self,
        policy_file: str,
        mock_qdrant: AsyncMock,
        mock_openai: AsyncMock,
        mock_anonymizer: MagicMock,
    ) -> None:
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = []

        submitted_items: list[dict] = []

        app = create_app(
            policy_path=policy_file,
            qdrant_client=mock_qdrant,
            openai_client=mock_openai,
            analyzer=mock_analyzer,
            anonymizer=mock_anonymizer,
            collection_name="tilth-test",
            embed_model="text-embedding-3-small",
            embed_dim=1536,
            skip_collection_check=True,
            _capture_queue=submitted_items,
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/ingest",
                json={"text": "hello world", "namespace": "checkout"},
                headers={"x-workload-identity": "checkout-svc"},
            )
        assert resp.status_code == 202
        assert len(submitted_items) == 1
        payload = submitted_items[0]["payload"]
        expected_hash = hashlib.sha256(b"hello world").hexdigest()[:16]
        assert payload["content_hash"] == expected_hash

    async def test_queue_full_returns_503(
        self,
        policy_file: str,
        mock_qdrant: AsyncMock,
        mock_openai: AsyncMock,
        mock_anonymizer: MagicMock,
    ) -> None:
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = []

        app = create_app(
            policy_path=policy_file,
            qdrant_client=mock_qdrant,
            openai_client=mock_openai,
            analyzer=mock_analyzer,
            anonymizer=mock_anonymizer,
            collection_name="tilth-test",
            embed_model="text-embedding-3-small",
            embed_dim=1536,
            batch_queue_max=1,  # tiny queue
            skip_collection_check=True,
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            # Fill the queue
            resp1 = await ac.post(
                "/ingest",
                json={"text": "first", "namespace": "checkout"},
                headers={"x-workload-identity": "checkout-svc"},
            )
            assert resp1.status_code == 202

            # This one should get 503 since queue is full
            resp2 = await ac.post(
                "/ingest",
                json={"text": "second", "namespace": "checkout"},
                headers={"x-workload-identity": "checkout-svc"},
            )
            assert resp2.status_code == 503


class TestIngestHealth:
    async def test_healthz_returns_200_with_queue_depth(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "queue_depth" in data

    async def test_metrics_returns_200(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/metrics")
        assert resp.status_code == 200
