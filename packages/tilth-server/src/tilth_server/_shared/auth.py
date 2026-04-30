"""Caller identity extraction from x-workload-identity header."""

from fastapi import HTTPException


def extract_caller_identity(
    header_value: str | None,
    known_callers: set[str],
) -> str:
    """Extract and validate caller identity from the workload header.

    Returns the caller string if valid.
    Raises HTTPException(401) if missing, empty, or unknown.
    """
    if not header_value or header_value not in known_callers:
        raise HTTPException(status_code=401, detail="unknown caller")
    return header_value
