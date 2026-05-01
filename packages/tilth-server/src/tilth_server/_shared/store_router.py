"""Multi-store namespace routing.

Routes namespaces to Qdrant collections based on a stores config.
Supports fan-out queries across multiple stores with score-based merge.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import yaml

log = logging.getLogger("tilth.store_router")


@dataclass
class StoreConfig:
    """A single store definition."""

    name: str
    namespaces: list[str] = field(default_factory=list)


def load_store_config(path: str) -> list[StoreConfig]:
    """Load store configuration from YAML.

    Raises FileNotFoundError if the file doesn't exist.
    Raises ValueError on duplicate namespaces across stores.
    """
    with open(path) as f:
        raw = yaml.safe_load(f)

    stores: list[StoreConfig] = []
    seen_namespaces: dict[str, str] = {}

    for entry in raw.get("stores", []):
        name = entry["name"]
        namespaces = entry.get("namespaces", [])

        for ns in namespaces:
            if ns in seen_namespaces:
                raise ValueError(
                    f"duplicate namespace {ns!r}: appears in both "
                    f"{seen_namespaces[ns]!r} and {name!r}"
                )
            seen_namespaces[ns] = name

        stores.append(StoreConfig(name=name, namespaces=namespaces))

    return stores


class StoreRouter:
    """Routes namespaces to Qdrant collections."""

    def __init__(
        self, stores: list[StoreConfig], default_store: str = "default"
    ) -> None:
        self._stores = stores
        self._default_store = default_store
        self._ns_to_collection: dict[str, str] = {}
        for store in stores:
            for ns in store.namespaces:
                if ns == "*":
                    continue  # wildcard handled via default
                self._ns_to_collection[ns] = store.name
        # Ensure default store exists in the store list
        store_names = {s.name for s in stores}
        if default_store not in store_names:
            self._default_store = stores[0].name if stores else "default"

    @property
    def store_names(self) -> list[str]:
        return [s.name for s in self._stores]

    @property
    def all_namespaces(self) -> list[str]:
        return list(self._ns_to_collection.keys())

    def get_collection(self, namespace: str) -> str:
        """Return the collection name for a namespace.

        Unknown namespaces route to the default store.
        """
        return self._ns_to_collection.get(namespace, self._default_store)

    def get_collections_for_namespaces(
        self, namespaces: list[str]
    ) -> dict[str, list[str]]:
        """Group namespaces by their collection.

        Returns {collection_name: [namespaces_in_that_collection]}.
        """
        result: dict[str, list[str]] = {}
        for ns in namespaces:
            collection = self.get_collection(ns)
            result.setdefault(collection, []).append(ns)
        return result

    def needs_fanout(self, namespaces: list[str]) -> bool:
        """Return True if the namespaces span multiple stores."""
        collections = {self.get_collection(ns) for ns in namespaces}
        return len(collections) > 1

    async def fan_out_query(
        self,
        qdrant_client: Any,
        query_vector: list[float],
        namespaces: list[str],
        query_filter: Any,
        top_k: int,
    ) -> list[Any]:
        """Query across stores, merge results by score.

        If all namespaces are in one store, queries directly (no fan-out).
        If namespaces span stores, queries each in parallel and merges.
        """
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            MatchAny,
        )

        collections = self.get_collections_for_namespaces(namespaces)

        if len(collections) == 1:
            # Single store — direct query
            collection_name = next(iter(collections))
            result = await qdrant_client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
            return result.points

        # Multi-store fan-out
        async def _query_store(
            collection_name: str, store_namespaces: list[str]
        ) -> list[Any]:
            # Build a filter scoped to this store's namespaces
            ns_filter = Filter(
                must=[
                    FieldCondition(
                        key="namespace",
                        match=MatchAny(any=store_namespaces),
                    )
                ]
            )
            result = await qdrant_client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=ns_filter,
                limit=top_k,
                with_payload=True,
            )
            return result.points

        # Query all stores in parallel
        tasks = [
            _query_store(coll, nss)
            for coll, nss in collections.items()
        ]
        all_results = await asyncio.gather(*tasks)

        # Merge and sort by score descending
        merged = []
        for hits in all_results:
            merged.extend(hits)
        merged.sort(key=lambda h: h.score, reverse=True)

        return merged[:top_k]

    async def ensure_collections(
        self,
        qdrant_client: Any,
        dimension: int,
    ) -> None:
        """Create Qdrant collections for all stores that don't exist."""
        from qdrant_client.models import Distance, VectorParams

        for store in self._stores:
            if not await qdrant_client.collection_exists(store.name):
                await qdrant_client.create_collection(
                    collection_name=store.name,
                    vectors_config=VectorParams(
                        size=dimension,
                        distance=Distance.COSINE,
                    ),
                )
                log.info(
                    "Created collection %s (dim=%d)", store.name, dimension
                )
