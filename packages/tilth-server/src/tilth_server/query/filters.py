"""Qdrant filter construction and closing-tag escape."""

from typing import Any

from fastapi import HTTPException
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
)

ALLOWED_FILTER_KEYS = {"severity", "env", "subject_id", "trace_id"}


def build_qdrant_filter(
    namespaces: list[str],
    filters: dict[str, Any],
) -> Filter:
    """Build a Qdrant Filter from effective namespaces and user-supplied filters.

    Raises HTTPException(400) for disallowed filter keys.
    """
    bad_keys = set(filters) - ALLOWED_FILTER_KEYS
    if bad_keys:
        raise HTTPException(
            status_code=400,
            detail=f"disallowed filter keys: {sorted(bad_keys)}",
        )

    must = [
        FieldCondition(key="namespace", match=MatchAny(any=namespaces))
    ]

    for key, value in filters.items():
        must.append(FieldCondition(key=key, match=MatchValue(value=value)))

    return Filter(must=must)


def escape_closing_tag(text: str) -> str:
    """Escape </retrieved_document> in text to prevent injection.

    Any occurrence of the closing tag is replaced with </retrieved_document_>
    so that a poisoned record cannot break the XML framing used by the
    query gateway response.
    """
    return text.replace("</retrieved_document>", "</retrieved_document_>")
