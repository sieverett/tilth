"""Pydantic request/response models for the ingest gateway."""

from typing import Any

from pydantic import BaseModel, Field, field_validator

ALLOWED_META_KEYS = {"env", "severity", "trace_id", "subject_id", "ttl_days"}
DEFAULT_MAX_TEXT_BYTES = 32768


class IngestRequest(BaseModel):
    """Request body for POST /ingest."""

    text: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Extra fields (like "source") are silently ignored
    model_config = {"extra": "ignore"}

    @field_validator("metadata")
    @classmethod
    def validate_metadata_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        bad = set(v) - ALLOWED_META_KEYS
        if bad:
            raise ValueError(f"disallowed metadata keys: {sorted(bad)}")
        return v


class IngestResponse(BaseModel):
    """Response body for POST /ingest (202)."""

    status: str = "accepted"
