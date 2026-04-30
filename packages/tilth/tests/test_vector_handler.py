"""Tests for VectorHandler."""

from __future__ import annotations

import logging

from tilth.testing import recording


def test_vector_handler_does_not_raise() -> None:
    """VectorHandler.emit() must never raise, even when send would drop."""
    from tilth import VectorHandler

    handler = VectorHandler(namespace="checkout")
    handler.setLevel(logging.WARNING)

    logger = logging.getLogger("test_vh")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    with recording() as records:
        # This should not raise
        logger.warning("something went wrong")
        logger.error("critical failure")
        logger.info("this is below handler level, should not appear")

    assert len(records) == 2
    assert "something went wrong" in records[0].text
    assert records[0].metadata["severity"] == "warning"
    assert records[1].metadata["severity"] == "error"

    logger.removeHandler(handler)


def test_vector_handler_extra_metadata() -> None:
    """VectorHandler passes extra_metadata to send()."""
    from tilth import VectorHandler

    handler = VectorHandler(
        namespace="support", extra_metadata={"env": "prod"}
    )
    handler.setLevel(logging.WARNING)

    logger = logging.getLogger("test_vh_meta")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    with recording() as records:
        logger.warning("test message")

    assert len(records) == 1
    assert records[0].metadata["env"] == "prod"
    assert records[0].metadata["severity"] == "warning"

    logger.removeHandler(handler)
