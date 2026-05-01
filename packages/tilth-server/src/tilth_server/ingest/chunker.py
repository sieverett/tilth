"""Text chunking with sentence-boundary splitting."""

import re
import uuid
from dataclasses import dataclass


@dataclass
class ChunkedRecord:
    """A chunk of text with its position in the group."""

    text: str
    chunk_group_id: str
    chunk_index: int
    chunk_total: int


# Sentence-ending patterns: period, question mark, exclamation, or newline
# followed by whitespace or end of string
_SENTENCE_END = re.compile(r"[.!?\n]\s*")


def _find_split_point(text: str, max_bytes: int) -> int:
    """Find the best split point at or before max_bytes.

    Prefers sentence boundaries (. ! ? or newline). Falls back to
    the byte limit if no sentence boundary is found.
    """
    # Find the byte position limit
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return len(text)

    # Decode back to find the character boundary at max_bytes
    # (don't cut in the middle of a multi-byte character)
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    char_limit = len(truncated)

    # Search backwards from the limit for a sentence boundary
    best = -1
    for match in _SENTENCE_END.finditer(text[:char_limit]):
        best = match.end()

    if best > 0:
        return best

    # No sentence boundary found — split at the byte limit
    return char_limit


def chunk_text(
    text: str,
    chunk_size: int = 32 * 1024,
) -> list[ChunkedRecord]:
    """Split text into chunks at sentence boundaries.

    Args:
        text: the text to chunk.
        chunk_size: max bytes per chunk (default 32KB).

    Returns:
        List of ChunkedRecord. Single-element list if text fits in one chunk.
    """
    group_id = str(uuid.uuid4())

    if len(text.encode("utf-8")) <= chunk_size:
        return [
            ChunkedRecord(
                text=text,
                chunk_group_id=group_id,
                chunk_index=0,
                chunk_total=1,
            )
        ]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining.encode("utf-8")) <= chunk_size:
            chunks.append(remaining)
            break

        split_at = _find_split_point(remaining, chunk_size)
        if split_at == 0:
            # Safety: if we can't find any split point, take one character
            split_at = 1

        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]

    return [
        ChunkedRecord(
            text=chunk,
            chunk_group_id=group_id,
            chunk_index=i,
            chunk_total=len(chunks),
        )
        for i, chunk in enumerate(chunks)
    ]
