"""Configuration — all env var reads happen here."""

from __future__ import annotations

import logging
import os

log = logging.getLogger("tilth")

_warned_missing_url = False


def gateway_url() -> str:
    """Return the gateway URL, or empty string if unset."""
    global _warned_missing_url  # noqa: PLW0603
    url = os.environ.get("TILTH_GATEWAY_URL", "")
    if not url and not _warned_missing_url:
        log.warning(
            "TILTH_GATEWAY_URL is not set — send() calls will be dropped"
        )
        _warned_missing_url = True
    return url


def identity() -> str:
    """Return the workload identity, or empty string if unset."""
    return os.environ.get("TILTH_IDENTITY", "")


def queue_size() -> int:
    """Return the max queue size."""
    return int(os.environ.get("TILTH_QUEUE_SIZE", "10000"))


def timeout_s() -> float:
    """Return the HTTP timeout in seconds."""
    return float(os.environ.get("TILTH_TIMEOUT_S", "5.0"))


def is_disabled() -> bool:
    """Return True if TILTH_DISABLE=1."""
    return os.environ.get("TILTH_DISABLE", "") == "1"
