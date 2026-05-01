"""FastAPI app for the ingest gateway."""

import asyncio
import hashlib
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from tilth_server._shared.auth import extract_caller_identity
from tilth_server._shared.health import create_health_router
from tilth_server._shared.policy import load_policy
from tilth_server._shared.rate_limit import TokenBucket
from tilth_server.ingest.batcher import BatchWriter
from tilth_server.ingest.chunker import chunk_text
from tilth_server.ingest.models import IngestRequest, IngestResponse
from tilth_server.ingest.scrubber import scrub_text

log = logging.getLogger("tilth.ingest")


def create_app(
    policy_path: str,
    qdrant_client: Any,
    embedding_client: Any,
    analyzer: Any,
    anonymizer: Any,
    collection_name: str = "tilth",
    store_router: Any | None = None,
    batch_size: int = 64,
    batch_window_ms: int = 200,
    batch_queue_max: int = 10_000,
    max_text_bytes: int = 256 * 1024,
    chunk_size: int = 32 * 1024,
    skip_collection_check: bool = False,
    _capture_queue: list[dict[str, Any]] | None = None,
) -> FastAPI:
    """Create a configured ingest gateway FastAPI app.

    Args:
        policy_path: path to write-policy.yaml.
        qdrant_client: AsyncQdrantClient instance.
        embedding_client: EmbeddingClient instance (from models.py).
        analyzer: Presidio AnalyzerEngine instance.
        anonymizer: Presidio AnonymizerEngine instance.
        collection_name: Qdrant collection name.
        batch_size: max items per embedding call.
        batch_window_ms: max wait before flushing partial batch.
        batch_queue_max: max items in batch writer queue.
        max_text_bytes: max text size in bytes.
        skip_collection_check: skip Qdrant collection validation (for tests).
        _capture_queue: if provided, submitted items are appended here (testing).
    """
    # Load policy at construction time (fail fast)
    policy = load_policy(policy_path)
    known_callers = set(policy.keys())

    rate_limiter = TokenBucket(rate=100.0, burst=200)

    resolve_fn = store_router.get_collection if store_router else None

    writer = BatchWriter(
        qdrant=qdrant_client,
        embedding_client=embedding_client,
        collection_name=collection_name,
        resolve_collection=resolve_fn,
        batch_size=batch_size,
        batch_window_ms=batch_window_ms,
        queue_max=batch_queue_max,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # Create collections
        if not skip_collection_check:
            try:
                if store_router:
                    await store_router.ensure_collections(
                        qdrant_client=qdrant_client,
                        dimension=embedding_client.dimension,
                    )
                else:
                    from qdrant_client.models import Distance, VectorParams

                    if not await qdrant_client.collection_exists(collection_name):
                        await qdrant_client.create_collection(
                            collection_name=collection_name,
                            vectors_config=VectorParams(
                                size=embedding_client.dimension,
                                distance=Distance.COSINE,
                            ),
                        )
                        log.info(
                            "Created Qdrant collection %s (dim=%d)",
                            collection_name,
                            embedding_client.dimension,
                        )
            except Exception:
                log.exception("Failed to initialize Qdrant collection")

        writer.start()
        yield
        await writer.stop(timeout=5.0)

    app = FastAPI(lifespan=lifespan)

    health_router = create_health_router(
        queue_depth_fn=lambda: writer.queue_depth
    )
    app.include_router(health_router)

    @app.post("/ingest", status_code=202, response_model=IngestResponse)
    async def ingest(request: Request, body: IngestRequest) -> IngestResponse:
        # Auth
        header_value = request.headers.get("x-workload-identity")
        caller = extract_caller_identity(header_value, known_callers)

        # Rate limit
        if not rate_limiter.consume(caller):
            raise HTTPException(status_code=429, detail="rate limited")

        # Text size validation
        if len(body.text.encode("utf-8")) > max_text_bytes:
            raise HTTPException(
                status_code=422,
                detail="text too large",
            )

        # Namespace authorization
        allowed = policy.get(caller, set())
        if body.namespace not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"{caller} cannot write to {body.namespace}",
            )

        # PII scrubbing
        scrubbed = scrub_text(body.text, analyzer=analyzer, anonymizer=anonymizer)

        # Chunk if needed
        chunks = chunk_text(scrubbed, chunk_size=chunk_size)

        if len(chunks) > 1:
            log.info(
                "Chunked %dKB text into %d records for namespace=%s",
                len(scrubbed.encode("utf-8")) // 1024,
                len(chunks),
                body.namespace,
            )

        now = time.time()
        client_ip = request.client.host if request.client else ""
        user_agent_val = request.headers.get("user-agent", "")

        for chunk in chunks:
            content_hash = hashlib.sha256(chunk.text.encode()).hexdigest()[:16]
            request_id = str(uuid.uuid4())

            payload: dict[str, Any] = {
                "text": chunk.text,
                "source": caller,
                "namespace": body.namespace,
                "ts": now,
                "content_hash": content_hash,
                "request_id": request_id,
                "client_ip": client_ip,
                "user_agent": user_agent_val,
                **body.metadata,
            }

            # Add chunk metadata if text was split
            if chunk.chunk_total > 1:
                payload["chunk_group_id"] = chunk.chunk_group_id
                payload["chunk_index"] = chunk.chunk_index
                payload["chunk_total"] = chunk.chunk_total

            item = {
                "id": request_id,
                "text": chunk.text,
                "payload": payload,
            }

            if _capture_queue is not None:
                _capture_queue.append(item)

            try:
                writer.submit_nowait(item)
            except asyncio.QueueFull as exc:
                raise HTTPException(
                    status_code=503,
                    detail="service overloaded, retry later",
                ) from exc

        return IngestResponse()

    return app
