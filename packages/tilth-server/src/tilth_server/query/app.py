"""FastAPI app for the query gateway."""

import hashlib
import json
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from tilth_server._shared.auth import extract_caller_identity
from tilth_server._shared.health import create_health_router
from tilth_server._shared.policy import load_policy
from tilth_server._shared.rate_limit import TokenBucket
from tilth_server.query.filters import build_qdrant_filter, escape_closing_tag
from tilth_server.query.models import (
    FILTERABLE_KEYS,
    METADATA_FIELDS,
    RECORD_FIELDS,
    QueryRequest,
    QueryResponse,
    QueryResult,
    SchemaResponse,
)

log = logging.getLogger("tilth.query")
audit_log = logging.getLogger("tilth.audit")


def create_app(
    policy_path: str,
    qdrant_client: Any,
    embedding_client: Any,
    collection_name: str = "tilth",
    max_top_k: int = 20,
    max_query_bytes: int = 4096,
) -> FastAPI:
    """Create a configured query gateway FastAPI app.

    Args:
        policy_path: path to read-policy.yaml.
        qdrant_client: AsyncQdrantClient instance.
        embedding_client: EmbeddingClient instance (from models.py).
        collection_name: Qdrant collection name.
        max_top_k: maximum top_k value.
        max_query_bytes: maximum query size in bytes.
    """
    policy = load_policy(policy_path)
    known_callers = set(policy.keys())

    rate_limiter = TokenBucket(rate=30.0, burst=60)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        yield

    app = FastAPI(lifespan=lifespan)

    health_router = create_health_router()
    app.include_router(health_router)

    @app.post("/query", response_model=QueryResponse)
    async def query(request: Request, body: QueryRequest) -> QueryResponse:
        # Auth
        header_value = request.headers.get("x-workload-identity")
        caller = extract_caller_identity(header_value, known_callers)

        # Rate limit
        if not rate_limiter.consume(caller):
            raise HTTPException(status_code=429, detail="rate limited")

        # Compute effective namespaces
        permitted = policy.get(caller, set())
        if body.namespaces is None:
            effective = sorted(permitted)
        else:
            requested = set(body.namespaces)
            denied = requested - permitted
            if denied:
                raise HTTPException(
                    status_code=403,
                    detail={"denied": sorted(denied)},
                )
            effective = sorted(requested)

        # Validate filters and build Qdrant filter
        qfilter = build_qdrant_filter(effective, body.filters)

        # Embed query
        vectors = await embedding_client.embed([body.query])
        query_vector = vectors[0]

        # Search Qdrant
        hits = await qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=qfilter,
            limit=body.top_k,
            with_payload=True,
        )

        # Build results
        results: list[QueryResult] = []
        for hit in hits:
            payload = hit.payload
            safe_text = escape_closing_tag(payload.get("text", ""))
            content = (
                f'<retrieved_document source="{payload["source"]}" '
                f'ts="{payload["ts"]}">\n'
                f"{safe_text}\n"
                f"</retrieved_document>"
            )
            results.append(
                QueryResult(
                    id=str(hit.id),
                    score=hit.score,
                    source=payload["source"],
                    namespace=payload["namespace"],
                    ts=payload["ts"],
                    content_hash=payload.get("content_hash"),
                    request_id=payload.get("request_id"),
                    client_ip=payload.get("client_ip"),
                    user_agent=payload.get("user_agent"),
                    content=content,
                )
            )

        # Audit log — structured JSON, no raw query or results
        query_hash = hashlib.sha256(body.query.encode()).hexdigest()[:16]
        audit_log.info(
            json.dumps(
                {
                    "event": "query",
                    "ts": time.time(),
                    "caller": caller,
                    "query_hash": query_hash,
                    "namespaces": effective,
                    "filters": body.filters,
                    "n_results": len(results),
                }
            )
        )

        return QueryResponse(results=results)

    @app.get("/schema", response_model=SchemaResponse)
    async def schema(request: Request) -> SchemaResponse:
        """Return the data model, with namespaces scoped to the caller."""
        header_value = request.headers.get("x-workload-identity")
        caller = extract_caller_identity(header_value, known_callers)
        caller_namespaces = sorted(policy.get(caller, set()))

        return SchemaResponse(
            namespaces=caller_namespaces,
            record_fields=RECORD_FIELDS,
            metadata_fields=METADATA_FIELDS,
            filterable_keys=FILTERABLE_KEYS,
            embed_model=embedding_client.model_name,
        )

    return app
