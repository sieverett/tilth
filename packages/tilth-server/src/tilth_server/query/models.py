"""Pydantic request/response models for the query gateway."""

from typing import Any

from pydantic import BaseModel, Field, field_validator

MAX_TOP_K = 20
MAX_QUERY_BYTES = 4096


class QueryRequest(BaseModel):
    """Request body for POST /query."""

    query: str = Field(min_length=1)
    namespaces: list[str] | None = None
    top_k: int = Field(default=5, ge=1, le=MAX_TOP_K)
    filters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query")
    @classmethod
    def validate_query_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > MAX_QUERY_BYTES:
            raise ValueError("query too large")
        return v


class QueryResult(BaseModel):
    """A single result in the query response."""

    id: str
    score: float
    source: str
    namespace: str
    ts: float
    content_hash: str | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    content: str


class QueryResponse(BaseModel):
    """Response body for POST /query."""

    results: list[QueryResult]
