"""Reference sketch — NOT the final implementation.

Shows the FastAPI + filter-construction + audit-log pattern. Missing:
- YAML policy file loading
- Health/metrics endpoints
- Rate limiting
- Closing-tag escape in retrieved text
- File-based audit log (uses log.info here)
- Comprehensive error handling

Use for the structural pattern, especially the namespace-intersection logic.
"""

import os, time, logging, hashlib
from typing import Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel, Field, field_validator
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
from openai import AsyncOpenAI

log = logging.getLogger("query")

QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_KEY = os.environ["QDRANT_API_KEY"]
COLLECTION = "org_memory"
EMBED_MODEL = "text-embedding-3-small"
MAX_TOP_K = 20
MAX_QUERY_BYTES = 4 * 1024

READ_POLICY: dict[str, set[str]] = {
    "support-agent": {"support", "billing"},
    "ops-copilot":   {"checkout", "billing", "support"},
}


def caller_identity(request: Request) -> str:
    ident = request.headers.get("x-workload-identity")
    if not ident or ident not in READ_POLICY:
        raise HTTPException(401, "unknown caller")
    return ident


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    namespaces: list[str] | None = None
    top_k: int = Field(default=5, ge=1, le=MAX_TOP_K)
    filters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query")
    @classmethod
    def _size(cls, v):
        if len(v.encode("utf-8")) > MAX_QUERY_BYTES:
            raise ValueError("query too large")
        return v


ALLOWED_FILTER_KEYS = {"severity", "env", "subject_id"}

qdrant: AsyncQdrantClient | None = None
openai: AsyncOpenAI | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global qdrant, openai
    qdrant = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY)
    openai = AsyncOpenAI()
    yield
    await qdrant.close()


app = FastAPI(lifespan=lifespan)


def audit(caller: str, query: str, namespaces: list[str], n: int):
    qhash = hashlib.sha256(query.encode()).hexdigest()[:16]
    log.info("read", extra={
        "caller": caller, "query_hash": qhash,
        "namespaces": namespaces, "n": n, "ts": time.time(),
    })


def build_filter(allowed_ns: list[str], extra: dict[str, Any]) -> Filter:
    must = [FieldCondition(key="namespace", match=MatchAny(any=allowed_ns))]
    bad = set(extra) - ALLOWED_FILTER_KEYS
    if bad:
        raise HTTPException(400, f"disallowed filter keys: {bad}")
    for k, v in extra.items():
        must.append(FieldCondition(key=k, match=MatchValue(value=v)))
    return Filter(must=must)


@app.post("/query")
async def query(req: QueryRequest, caller: str = Depends(caller_identity)):
    allowed = READ_POLICY[caller]
    if req.namespaces is None:
        effective = sorted(allowed)
    else:
        requested = set(req.namespaces)
        denied = requested - allowed
        if denied:
            raise HTTPException(403, f"{caller} cannot read: {sorted(denied)}")
        effective = sorted(requested)

    qfilter = build_filter(effective, req.filters)
    vec = (await openai.embeddings.create(
        model=EMBED_MODEL, input=req.query
    )).data[0].embedding

    hits = await qdrant.search(
        collection_name=COLLECTION,
        query_vector=vec,
        query_filter=qfilter,
        limit=req.top_k,
        with_payload=True,
    )

    audit(caller, req.query, effective, len(hits))

    results = [{
        "id": str(h.id),
        "score": h.score,
        "source": h.payload.get("source"),
        "namespace": h.payload.get("namespace"),
        "ts": h.payload.get("ts"),
        "content": (
            f'<retrieved_document source="{h.payload.get("source")}" '
            f'ts="{h.payload.get("ts")}">\n'
            f'{h.payload.get("text", "")}\n'
            '</retrieved_document>'
        ),
    } for h in hits]

    return {"results": results}
