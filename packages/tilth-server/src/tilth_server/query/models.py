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


class SchemaResponse(BaseModel):
    """Response body for GET /schema."""

    namespaces: list[str]
    record_fields: dict[str, str]
    metadata_fields: dict[str, str]
    filterable_keys: list[str]
    embed_model: str


RECORD_FIELDS: dict[str, str] = {
    "text": "string — the record content",
    "source": "string — who wrote it (gateway-set)",
    "namespace": "string — logical partition",
    "ts": "float — unix timestamp (gateway-set)",
    "content_hash": "string — sha256 prefix of scrubbed text (gateway-set)",
    "request_id": "string — per-request UUID (gateway-set)",
    "client_ip": "string — caller IP (gateway-set)",
    "user_agent": "string — caller user-agent (gateway-set)",
}

METADATA_FIELDS: dict[str, str] = {
    "severity": "info | warn | error",
    "env": "prod | staging | dev",
    "trace_id": "string — correlation ID",
    "subject_id": "string — entity ID (deal, customer, etc.)",
    "ttl_days": "integer — retention hint",
}

FILTERABLE_KEYS: list[str] = ["severity", "env", "subject_id", "trace_id"]


class DeleteRequest(BaseModel):
    """Request body for DELETE /records/{record_id}."""

    reason: str = Field(min_length=1)


class DeleteResponse(BaseModel):
    """Response body for DELETE /records/{record_id}."""

    status: str = "deleted"
    record_id: str


class UpdateRequest(BaseModel):
    """Request body for PATCH /records/{record_id}."""

    text: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class UpdateResponse(BaseModel):
    """Response body for PATCH /records/{record_id}."""

    status: str = "updated"
    new_id: str
    supersedes: str
