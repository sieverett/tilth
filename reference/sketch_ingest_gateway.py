"""Reference sketch — NOT the final implementation.

Shows the FastAPI + batched-writer + Presidio pattern. Missing pieces:
- YAML policy file loading (uses inline dict here)
- Health/metrics endpoints
- Rate limiting
- Proper startup/shutdown of Presidio (warm load)
- Comprehensive error handling
- Metric increments throughout

Use for the structural pattern (lifespan, batcher, policy check ordering),
not for the production code.
"""

import os, time, uuid, asyncio, logging
from typing import Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel, Field, field_validator
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from openai import AsyncOpenAI
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

log = logging.getLogger("ingest")

QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_KEY = os.environ["QDRANT_API_KEY"]
COLLECTION = "org_memory"
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536
MAX_TEXT_BYTES = 32 * 1024
BATCH_SIZE = 64
BATCH_WINDOW_MS = 200

WRITE_POLICY: dict[str, set[str]] = {
    "checkout-svc":  {"checkout"},
    "support-bot":   {"support"},
    "billing-job":   {"billing"},
}


def caller_identity(request: Request) -> str:
    ident = request.headers.get("x-workload-identity")
    if not ident or ident not in WRITE_POLICY:
        raise HTTPException(401, "unknown caller")
    return ident


analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()
PII_ENTITIES = ["EMAIL_ADDRESS", "CREDIT_CARD", "US_SSN", "PHONE_NUMBER",
                "IP_ADDRESS", "IBAN_CODE"]


def scrub(text: str) -> str:
    findings = analyzer.analyze(text=text, entities=PII_ENTITIES, language="en")
    if not findings:
        return text
    return anonymizer.anonymize(text=text, analyzer_results=findings).text


ALLOWED_META_KEYS = {"env", "severity", "trace_id", "subject_id", "ttl_days"}


class IngestRequest(BaseModel):
    text: str = Field(min_length=1)
    namespace: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def _size(cls, v):
        if len(v.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError("text too large")
        return v

    @field_validator("metadata")
    @classmethod
    def _meta(cls, v):
        bad = set(v) - ALLOWED_META_KEYS
        if bad:
            raise ValueError(f"disallowed metadata keys: {bad}")
        return v


class BatchWriter:
    def __init__(self, qdrant: AsyncQdrantClient, openai: AsyncOpenAI):
        self.q: asyncio.Queue = asyncio.Queue(maxsize=10_000)
        self.qdrant = qdrant
        self.openai = openai
        self.task: asyncio.Task | None = None

    async def submit(self, point: dict):
        try:
            self.q.put_nowait(point)
        except asyncio.QueueFull:
            log.warning("ingest queue full, dropping")

    async def run(self):
        while True:
            batch = [await self.q.get()]
            deadline = time.monotonic() + BATCH_WINDOW_MS / 1000
            while len(batch) < BATCH_SIZE:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                try:
                    batch.append(await asyncio.wait_for(self.q.get(), timeout))
                except asyncio.TimeoutError:
                    break
            try:
                await self._flush(batch)
            except Exception:
                log.exception("flush failed")

    async def _flush(self, batch: list[dict]):
        texts = [b["text"] for b in batch]
        resp = await self.openai.embeddings.create(model=EMBED_MODEL, input=texts)
        points = [
            PointStruct(id=b["id"], vector=e.embedding, payload=b["payload"])
            for b, e in zip(batch, resp.data)
        ]
        await self.qdrant.upsert(collection_name=COLLECTION, points=points)


writer: BatchWriter | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global writer
    qdrant = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY)
    openai = AsyncOpenAI()
    if not await qdrant.collection_exists(COLLECTION):
        await qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
    writer = BatchWriter(qdrant, openai)
    writer.task = asyncio.create_task(writer.run())
    yield
    writer.task.cancel()
    await qdrant.close()


app = FastAPI(lifespan=lifespan)


@app.post("/ingest", status_code=202)
async def ingest(req: IngestRequest, caller: str = Depends(caller_identity)):
    allowed = WRITE_POLICY.get(caller, set())
    if req.namespace not in allowed:
        raise HTTPException(403, f"{caller} cannot write to {req.namespace}")

    text = scrub(req.text)
    payload = {
        "text": text,
        "source": caller,
        "namespace": req.namespace,
        "ts": time.time(),
        **req.metadata,
    }
    await writer.submit({
        "id": str(uuid.uuid4()),
        "text": text,
        "payload": payload,
    })
    return {"status": "accepted"}
