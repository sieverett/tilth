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
from tilth_server.ingest.models import IngestRequest, IngestResponse
from tilth_server.ingest.scrubber import scrub_text

log = logging.getLogger("tilth.ingest")


def create_app(
    policy_path: str,
    qdrant_client: Any,
    openai_client: Any,
    analyzer: Any,
    anonymizer: Any,
    collection_name: str = "tilth",
    embed_model: str = "text-embedding-3-small",
    embed_dim: int = 1536,
    batch_size: int = 64,
    batch_window_ms: int = 200,
    batch_queue_max: int = 10_000,
    max_text_bytes: int = 32768,
    skip_collection_check: bool = False,
    _capture_queue: list[dict[str, Any]] | None = None,
) -> FastAPI:
    """Create a configured ingest gateway FastAPI app.

    Args:
        policy_path: path to write-policy.yaml.
        qdrant_client: AsyncQdrantClient instance.
        openai_client: AsyncOpenAI instance.
        analyzer: Presidio AnalyzerEngine instance.
        anonymizer: Presidio AnonymizerEngine instance.
        collection_name: Qdrant collection name.
        embed_model: embedding model name.
        embed_dim: embedding vector dimension.
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

    writer = BatchWriter(
        qdrant=qdrant_client,
        openai=openai_client,
        collection_name=collection_name,
        embed_model=embed_model,
        batch_size=batch_size,
        batch_window_ms=batch_window_ms,
        queue_max=batch_queue_max,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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

        # Content hash
        content_hash = hashlib.sha256(scrubbed.encode()).hexdigest()[:16]

        # Build payload
        request_id = str(uuid.uuid4())
        payload: dict[str, Any] = {
            "text": scrubbed,
            "source": caller,  # from header, never from body
            "namespace": body.namespace,
            "ts": time.time(),
            "content_hash": content_hash,
            "request_id": request_id,
            "client_ip": request.client.host if request.client else "",
            "user_agent": request.headers.get("user-agent", ""),
            **body.metadata,
        }

        item = {
            "id": request_id,
            "text": scrubbed,
            "payload": payload,
        }

        # Testing hook
        if _capture_queue is not None:
            _capture_queue.append(item)

        # Submit to batch queue
        try:
            writer.submit_nowait(item)
        except asyncio.QueueFull as exc:
            raise HTTPException(
                status_code=503,
                detail="service overloaded, retry later",
            ) from exc

        return IngestResponse()

    return app
