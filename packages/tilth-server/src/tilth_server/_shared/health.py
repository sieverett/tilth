"""Health and metrics endpoints shared between gateways."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def create_health_router(
    queue_depth_fn: Callable[[], int] | None = None,
) -> APIRouter:
    """Create a router with /healthz and /metrics endpoints.

    Args:
        queue_depth_fn: optional callable returning the current queue depth
            (used by the ingest gateway).
    """
    router = APIRouter()

    @router.get("/healthz")
    async def healthz() -> dict[str, Any]:
        result: dict[str, Any] = {"ok": True}
        if queue_depth_fn is not None:
            result["queue_depth"] = queue_depth_fn()
        return result

    @router.get("/metrics")
    async def metrics() -> Response:
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    return router
