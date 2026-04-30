"""tilth — fire-and-forget semantic memory client for services."""

from __future__ import annotations

import logging
from typing import Any

from tilth._client import asend as asend
from tilth._client import send as send


class VectorHandler(logging.Handler):
    """Logging handler that forwards records to tilth.send().

    Usage::

        handler = VectorHandler(namespace="checkout")
        handler.setLevel(logging.WARNING)
        logging.getLogger().addHandler(handler)
    """

    def __init__(
        self,
        namespace: str,
        *,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._namespace = namespace
        self._extra_metadata: dict[str, Any] = extra_metadata or {}

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            meta = {
                "severity": record.levelname.lower(),
                **self._extra_metadata,
            }
            send(msg, namespace=self._namespace, **meta)
        except Exception:
            self.handleError(record)


__all__ = ["send", "asend", "VectorHandler"]
