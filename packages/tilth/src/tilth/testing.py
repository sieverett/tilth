"""Test helpers for tilth consumers."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator
from unittest.mock import patch


@dataclass
class Recorded:
    """A captured send() call."""

    text: str
    namespace: str
    metadata: dict[str, Any]


@contextlib.contextmanager
def recording() -> Generator[list[Recorded], None, None]:
    """Capture send() calls in-process without starting the worker.

    Usage::

        with recording() as records:
            send("hello", namespace="test")
        assert len(records) == 1
    """
    records: list[Recorded] = []

    def _fake_send(text: str, *, namespace: str, **metadata: Any) -> None:
        records.append(Recorded(text=text, namespace=namespace, metadata=metadata))

    with (
        patch("tilth.send", _fake_send),
        patch("tilth._client.send", _fake_send),
    ):
        yield records
