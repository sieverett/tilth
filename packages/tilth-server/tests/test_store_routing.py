"""Tests for multi-store routing."""

import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from tilth_server._shared.store_router import (
    StoreConfig,
    StoreRouter,
    load_store_config,
)

# --- Store config loading ---


class TestLoadStoreConfig:
    def test_load_valid_config(self) -> None:
        config = {
            "stores": [
                {"name": "default", "namespaces": ["sales", "support"]},
                {"name": "engineering", "namespaces": ["incidents", "deploys"]},
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config, f)
            f.flush()
            result = load_store_config(f.name)

        assert len(result) == 2
        assert result[0].name == "default"
        assert result[0].namespaces == ["sales", "support"]
        assert result[1].name == "engineering"
        assert result[1].namespaces == ["incidents", "deploys"]

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_store_config("/nonexistent/stores.yaml")

    def test_single_store_is_valid(self) -> None:
        config = {
            "stores": [
                {"name": "default", "namespaces": ["sales", "support", "billing"]},
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config, f)
            f.flush()
            result = load_store_config(f.name)

        assert len(result) == 1

    def test_duplicate_namespace_across_stores_raises(self) -> None:
        config = {
            "stores": [
                {"name": "store1", "namespaces": ["sales"]},
                {"name": "store2", "namespaces": ["sales"]},
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config, f)
            f.flush()
            with pytest.raises(ValueError, match="duplicate"):
                load_store_config(f.name)


# --- Router ---


class TestStoreRouter:
    def _make_router(self) -> StoreRouter:
        stores = [
            StoreConfig(name="default", namespaces=["sales", "support", "analysis"]),
            StoreConfig(name="engineering", namespaces=["incidents", "deploys"]),
            StoreConfig(name="sensitive", namespaces=["hr", "legal"]),
        ]
        return StoreRouter(stores)

    def test_route_namespace_to_correct_store(self) -> None:
        router = self._make_router()
        assert router.get_collection("sales") == "default"
        assert router.get_collection("incidents") == "engineering"
        assert router.get_collection("hr") == "sensitive"

    def test_unknown_namespace_raises(self) -> None:
        router = self._make_router()
        with pytest.raises(ValueError, match="unknown namespace"):
            router.get_collection("nonexistent")

    def test_get_collections_for_namespaces_single_store(self) -> None:
        router = self._make_router()
        result = router.get_collections_for_namespaces(["sales", "support"])
        # All in one store — returns single collection mapping
        assert result == {"default": ["sales", "support"]}

    def test_get_collections_for_namespaces_multi_store(self) -> None:
        router = self._make_router()
        result = router.get_collections_for_namespaces(
            ["sales", "incidents", "hr"]
        )
        # Spans three stores
        assert result == {
            "default": ["sales"],
            "engineering": ["incidents"],
            "sensitive": ["hr"],
        }

    def test_needs_fanout_false_for_single_store(self) -> None:
        router = self._make_router()
        assert router.needs_fanout(["sales", "support"]) is False

    def test_needs_fanout_true_for_multi_store(self) -> None:
        router = self._make_router()
        assert router.needs_fanout(["sales", "incidents"]) is True

    def test_all_store_names(self) -> None:
        router = self._make_router()
        assert router.store_names == ["default", "engineering", "sensitive"]

    def test_all_namespaces(self) -> None:
        router = self._make_router()
        assert sorted(router.all_namespaces) == [
            "analysis", "deploys", "hr", "incidents", "legal",
            "sales", "support",
        ]


# --- Query fan-out ---


class TestQueryFanout:
    async def test_single_store_query_no_fanout(self) -> None:
        """When all namespaces are in one store, query that store directly."""
        router = StoreRouter([
            StoreConfig(name="default", namespaces=["sales", "support"]),
            StoreConfig(name="eng", namespaces=["incidents"]),
        ])

        mock_hit = MagicMock()
        mock_hit.id = "abc"
        mock_hit.score = 0.9
        mock_hit.payload = {
            "text": "test",
            "source": "svc",
            "namespace": "sales",
            "ts": 1.0,
        }

        mock_result = MagicMock()
        mock_result.points = [mock_hit]

        mock_qdrant = AsyncMock()
        mock_qdrant.query_points = AsyncMock(return_value=mock_result)

        results = await router.fan_out_query(
            qdrant_client=mock_qdrant,
            query_vector=[0.1] * 1536,
            namespaces=["sales", "support"],
            query_filter=None,
            top_k=5,
        )

        # Should have called query_points once (no fan-out)
        assert mock_qdrant.query_points.call_count == 1
        assert len(results) == 1

    async def test_multi_store_query_fans_out(self) -> None:
        """When namespaces span stores, query each store and merge."""
        router = StoreRouter([
            StoreConfig(name="default", namespaces=["sales"]),
            StoreConfig(name="eng", namespaces=["incidents"]),
        ])

        hit_sales = MagicMock()
        hit_sales.id = "s1"
        hit_sales.score = 0.8
        hit_sales.payload = {
            "text": "sales record",
            "source": "svc",
            "namespace": "sales",
            "ts": 1.0,
        }

        hit_eng = MagicMock()
        hit_eng.id = "e1"
        hit_eng.score = 0.9
        hit_eng.payload = {
            "text": "incident record",
            "source": "svc",
            "namespace": "incidents",
            "ts": 2.0,
        }

        result_sales = MagicMock()
        result_sales.points = [hit_sales]

        result_eng = MagicMock()
        result_eng.points = [hit_eng]

        mock_qdrant = AsyncMock()
        mock_qdrant.query_points = AsyncMock(
            side_effect=[result_sales, result_eng]
        )

        results = await router.fan_out_query(
            qdrant_client=mock_qdrant,
            query_vector=[0.1] * 1536,
            namespaces=["sales", "incidents"],
            query_filter=None,
            top_k=5,
        )

        # Should have called query_points twice (one per store)
        assert mock_qdrant.query_points.call_count == 2
        # Results merged and sorted by score descending
        assert len(results) == 2
        assert results[0].score >= results[1].score
        # Highest score should be the engineering hit (0.9 > 0.8)
        assert results[0].id == "e1"

    async def test_fanout_respects_top_k(self) -> None:
        """Fan-out returns at most top_k results after merge."""
        router = StoreRouter([
            StoreConfig(name="s1", namespaces=["a"]),
            StoreConfig(name="s2", namespaces=["b"]),
        ])

        hits_a = [MagicMock(id=f"a{i}", score=0.9 - i * 0.1, payload={
            "text": f"rec {i}", "source": "svc", "namespace": "a", "ts": 1.0,
        }) for i in range(5)]

        hits_b = [MagicMock(id=f"b{i}", score=0.85 - i * 0.1, payload={
            "text": f"rec {i}", "source": "svc", "namespace": "b", "ts": 1.0,
        }) for i in range(5)]

        result_a = MagicMock()
        result_a.points = hits_a
        result_b = MagicMock()
        result_b.points = hits_b

        mock_qdrant = AsyncMock()
        mock_qdrant.query_points = AsyncMock(side_effect=[result_a, result_b])

        results = await router.fan_out_query(
            qdrant_client=mock_qdrant,
            query_vector=[0.1] * 1536,
            namespaces=["a", "b"],
            query_filter=None,
            top_k=3,
        )

        assert len(results) == 3
        # Should be sorted by score, best first
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


# --- Ingest routing ---


class TestIngestRouting:
    def test_ingest_routes_to_correct_collection(self) -> None:
        router = StoreRouter([
            StoreConfig(name="default", namespaces=["sales", "support"]),
            StoreConfig(name="eng", namespaces=["incidents"]),
        ])
        assert router.get_collection("sales") == "default"
        assert router.get_collection("incidents") == "eng"

    def test_ingest_unknown_namespace_raises(self) -> None:
        router = StoreRouter([
            StoreConfig(name="default", namespaces=["sales"]),
        ])
        with pytest.raises(ValueError):
            router.get_collection("unknown")


# --- Collection auto-creation ---


class TestCollectionCreation:
    async def test_creates_collections_for_all_stores(self) -> None:
        router = StoreRouter([
            StoreConfig(name="store_a", namespaces=["ns1"]),
            StoreConfig(name="store_b", namespaces=["ns2"]),
            StoreConfig(name="store_c", namespaces=["ns3"]),
        ])

        mock_qdrant = AsyncMock()
        mock_qdrant.collection_exists = AsyncMock(return_value=False)

        await router.ensure_collections(
            qdrant_client=mock_qdrant,
            dimension=1536,
        )

        # Should have checked existence for each store
        assert mock_qdrant.collection_exists.call_count == 3
        # Should have created each store
        assert mock_qdrant.create_collection.call_count == 3

    async def test_skips_existing_collections(self) -> None:
        router = StoreRouter([
            StoreConfig(name="existing", namespaces=["ns1"]),
            StoreConfig(name="new_one", namespaces=["ns2"]),
        ])

        mock_qdrant = AsyncMock()
        mock_qdrant.collection_exists = AsyncMock(
            side_effect=[True, False]
        )

        await router.ensure_collections(
            qdrant_client=mock_qdrant,
            dimension=1536,
        )

        # Only created the new one
        assert mock_qdrant.create_collection.call_count == 1
