"""Batch writer — async queue to embed and upsert to Qdrant."""

import asyncio
import contextlib
import logging
import time
from typing import Any

from prometheus_client import Counter, Histogram
from qdrant_client.models import PointStruct

log = logging.getLogger("tilth.ingest.batcher")

FLUSH_FAILED = Counter(
    "tilth_ingest_flush_failed_total",
    "Number of failed batch flush operations",
)
BATCH_SIZE_HIST = Histogram(
    "tilth_ingest_batch_size",
    "Number of items per flush batch",
)
EMBED_LATENCY = Histogram(
    "tilth_ingest_embed_latency_seconds",
    "Time spent calling the embedding API",
)
UPSERT_LATENCY = Histogram(
    "tilth_ingest_upsert_latency_seconds",
    "Time spent upserting to Qdrant",
)


class BatchWriter:
    """Batches ingest items and flushes them to Qdrant via embeddings."""

    def __init__(
        self,
        qdrant: Any,
        embedding_client: Any,
        collection_name: str,
        batch_size: int = 64,
        batch_window_ms: int = 200,
        queue_max: int = 10_000,
    ) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=queue_max)
        self.qdrant = qdrant
        self.embedding_client = embedding_client
        self.collection_name = collection_name
        self.batch_size = batch_size
        self.batch_window_ms = batch_window_ms
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the background batch writer task."""
        self._task = asyncio.create_task(self._run())

    async def stop(self, timeout: float = 5.0) -> None:
        """Stop the batch writer, draining remaining items."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(self._task, timeout=timeout)

    def submit_nowait(self, item: dict[str, Any]) -> None:
        """Submit an item to the queue. Raises asyncio.QueueFull if full."""
        self.queue.put_nowait(item)

    @property
    def queue_depth(self) -> int:
        return self.queue.qsize()

    async def _run(self) -> None:
        """Main loop: pull items, batch, embed, upsert."""
        try:
            while True:
                # Block for first item
                batch = [await self.queue.get()]
                deadline = time.monotonic() + self.batch_window_ms / 1000

                # Collect more items until batch full or deadline
                while len(batch) < self.batch_size:
                    timeout = deadline - time.monotonic()
                    if timeout <= 0:
                        break
                    try:
                        item = await asyncio.wait_for(
                            self.queue.get(), timeout=timeout
                        )
                        batch.append(item)
                    except TimeoutError:
                        break

                try:
                    await self._flush(batch)
                except Exception:
                    log.exception("flush failed for batch of %d items", len(batch))
                    FLUSH_FAILED.inc()
        except asyncio.CancelledError:
            # Drain remaining items on shutdown
            remaining: list[dict[str, Any]] = []
            while not self.queue.empty():
                try:
                    remaining.append(self.queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if remaining:
                try:
                    await self._flush(remaining)
                except Exception:
                    log.exception("flush failed during shutdown drain")
                    FLUSH_FAILED.inc()

    async def _flush(self, batch: list[dict[str, Any]]) -> None:
        """Embed and upsert a batch of items."""
        BATCH_SIZE_HIST.observe(len(batch))

        texts = [item["text"] for item in batch]

        start = time.monotonic()
        vectors = await self.embedding_client.embed(texts)
        EMBED_LATENCY.observe(time.monotonic() - start)

        points = [
            PointStruct(
                id=item["id"],
                vector=vec,
                payload=item["payload"],
            )
            for item, vec in zip(batch, vectors, strict=True)
        ]

        start = time.monotonic()
        await self.qdrant.upsert(
            collection_name=self.collection_name, points=points
        )
        UPSERT_LATENCY.observe(time.monotonic() - start)
