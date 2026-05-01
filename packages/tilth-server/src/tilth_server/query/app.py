"""FastAPI app for the query gateway."""

import hashlib
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from tilth_server._shared.auth import (
    AuthMode,
    JWTAuthenticator,
    extract_caller_identity,
    require_admin,
)
from tilth_server._shared.health import create_health_router
from tilth_server._shared.policy import load_policy
from tilth_server._shared.rate_limit import TokenBucket
from tilth_server.query.filters import build_qdrant_filter, escape_closing_tag
from tilth_server.query.models import (
    FILTERABLE_KEYS,
    METADATA_FIELDS,
    RECORD_FIELDS,
    DeleteRequest,
    DeleteResponse,
    QueryRequest,
    QueryResponse,
    QueryResult,
    SchemaResponse,
    UpdateRequest,
    UpdateResponse,
)

log = logging.getLogger("tilth.query")
audit_log = logging.getLogger("tilth.audit")


def create_app(
    policy_path: str,
    qdrant_client: Any,
    embedding_client: Any,
    collection_name: str = "tilth",
    store_router: Any | None = None,
    write_policy_path: str | None = None,
    auth_mode: AuthMode = AuthMode.DEV,
    jwt_authenticator: JWTAuthenticator | None = None,
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

    # Write policy for mutations (delete/update)
    write_policy: dict[str, set[str]] = {}
    if write_policy_path:
        write_policy = load_policy(write_policy_path)
        known_callers |= set(write_policy.keys())

    rate_limiter = TokenBucket(rate=30.0, burst=60)

    def _authenticate(request: Request) -> str:
        """Authenticate the caller based on auth mode."""
        return extract_caller_identity(
            header_value=request.headers.get("x-workload-identity"),
            known_callers=known_callers,
            mode=auth_mode,
            jwt_authenticator=jwt_authenticator,
            authorization_header=request.headers.get("authorization"),
        )

    def _require_admin(request: Request) -> None:
        """Require admin role for mutation operations."""
        require_admin(
            jwt_authenticator=jwt_authenticator,
            authorization_header=request.headers.get("authorization"),
            mode=auth_mode,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        yield

    app = FastAPI(lifespan=lifespan)

    health_router = create_health_router()
    app.include_router(health_router)

    @app.post("/query", response_model=QueryResponse)
    async def query(request: Request, body: QueryRequest) -> QueryResponse:
        # Auth
        caller = _authenticate(request)

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

        # Search Qdrant — fan out if namespaces span multiple stores
        if store_router and store_router.needs_fanout(effective):
            hits = await store_router.fan_out_query(
                qdrant_client=qdrant_client,
                query_vector=query_vector,
                namespaces=effective,
                query_filter=qfilter,
                top_k=body.top_k,
            )
        else:
            target_collection = (
                store_router.get_collection(effective[0])
                if store_router
                else collection_name
            )
            search_result = await qdrant_client.query_points(
                collection_name=target_collection,
                query=query_vector,
                query_filter=qfilter,
                limit=body.top_k,
                with_payload=True,
            )
            hits = search_result.points

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
        caller = _authenticate(request)
        caller_namespaces = sorted(policy.get(caller, set()))

        return SchemaResponse(
            namespaces=caller_namespaces,
            record_fields=RECORD_FIELDS,
            metadata_fields=METADATA_FIELDS,
            filterable_keys=FILTERABLE_KEYS,
            embed_model=embedding_client.model_name,
        )

    async def _get_record(record_id: str) -> Any:
        """Retrieve a record by ID. Returns None if not found."""
        results = await qdrant_client.retrieve(
            collection_name=collection_name,
            ids=[record_id],
            with_payload=True,
            with_vectors=False,
        )
        return results[0] if results else None

    def _check_write_access(caller: str, namespace: str) -> None:
        """Check caller has write access to the namespace."""
        allowed = write_policy.get(caller, set())
        if namespace not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"{caller} cannot modify records in {namespace}",
            )

    @app.delete(
        "/records/{record_id}", response_model=DeleteResponse
    )
    async def delete_record(
        request: Request, record_id: str, body: DeleteRequest
    ) -> DeleteResponse:
        """Hard delete a record. Audit logged. Requires admin in prod."""
        _require_admin(request)
        caller = _authenticate(request)

        record = await _get_record(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="record not found")

        namespace = record.payload.get("namespace", "")
        _check_write_access(caller, namespace)

        # Audit log before deletion
        audit_log.info(
            json.dumps(
                {
                    "event": "delete",
                    "ts": time.time(),
                    "caller": caller,
                    "record_id": record_id,
                    "namespace": namespace,
                    "source": record.payload.get("source"),
                    "content_hash": record.payload.get("content_hash"),
                    "reason": body.reason,
                }
            )
        )

        from qdrant_client.models import PointIdsList

        await qdrant_client.delete(
            collection_name=collection_name,
            points_selector=PointIdsList(points=[record_id]),
        )

        return DeleteResponse(record_id=record_id)

    @app.patch(
        "/records/{record_id}", response_model=UpdateResponse
    )
    async def update_record(
        request: Request, record_id: str, body: UpdateRequest
    ) -> UpdateResponse:
        """Soft-delete old record, create new one. Requires admin in prod."""
        _require_admin(request)
        caller = _authenticate(request)

        record = await _get_record(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="record not found")

        namespace = record.payload.get("namespace", "")
        _check_write_access(caller, namespace)

        # Embed new text
        vectors = await embedding_client.embed([body.text])

        # Build new record
        new_id = str(uuid.uuid4())
        new_content_hash = hashlib.sha256(
            body.text.encode()
        ).hexdigest()[:16]

        new_payload = {
            **record.payload,
            "text": body.text,
            "content_hash": new_content_hash,
            "request_id": new_id,
            "ts": time.time(),
            "supersedes": record_id,
        }

        # Mark old record as superseded
        old_payload = dict(record.payload)
        old_payload["superseded_by"] = new_id

        from qdrant_client.models import PointStruct

        # Upsert both: updated old record + new record
        await qdrant_client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=record_id,
                    vector=record.vector or vectors[0],
                    payload=old_payload,
                ),
                PointStruct(
                    id=new_id,
                    vector=vectors[0],
                    payload=new_payload,
                ),
            ],
        )

        previous_hash = record.payload.get("content_hash", "")
        audit_log.info(
            json.dumps(
                {
                    "event": "update",
                    "ts": time.time(),
                    "caller": caller,
                    "record_id": record_id,
                    "new_id": new_id,
                    "namespace": namespace,
                    "previous_content_hash": previous_hash,
                    "new_content_hash": new_content_hash,
                    "reason": body.reason,
                }
            )
        )

        return UpdateResponse(
            new_id=new_id,
            supersedes=record_id,
        )

    return app
