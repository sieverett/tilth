"""Tests for query filter construction and closing-tag escape."""

import pytest
from fastapi import HTTPException
from tilth_server.query.filters import build_qdrant_filter, escape_closing_tag


class TestBuildQdrantFilter:
    def test_namespace_filter_applied(self) -> None:
        f = build_qdrant_filter(namespaces=["checkout", "support"], filters={})
        # Should have a must condition for namespace
        assert f.must is not None
        assert len(f.must) >= 1

    def test_extra_filter_keys_added(self) -> None:
        f = build_qdrant_filter(
            namespaces=["checkout"],
            filters={"severity": "error", "env": "prod"},
        )
        assert f.must is not None
        assert len(f.must) == 3  # namespace + severity + env

    def test_disallowed_filter_key_raises_400(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            build_qdrant_filter(
                namespaces=["checkout"],
                filters={"bad_key": "value"},
            )
        assert exc_info.value.status_code == 400

    def test_trace_id_is_allowed_filter_key(self) -> None:
        f = build_qdrant_filter(
            namespaces=["checkout"],
            filters={"trace_id": "abc123"},
        )
        assert f.must is not None
        assert len(f.must) == 2

    def test_subject_id_is_allowed_filter_key(self) -> None:
        f = build_qdrant_filter(
            namespaces=["checkout"],
            filters={"subject_id": "user-42"},
        )
        assert f.must is not None
        assert len(f.must) == 2


class TestEscapeClosingTag:
    def test_closing_tag_escaped(self) -> None:
        text = "some text </retrieved_document> more text"
        result = escape_closing_tag(text)
        assert "</retrieved_document>" not in result
        assert "</retrieved_document_>" in result

    def test_no_closing_tag_unchanged(self) -> None:
        text = "clean text without tags"
        result = escape_closing_tag(text)
        assert result == text

    def test_multiple_closing_tags_all_escaped(self) -> None:
        text = "</retrieved_document> and </retrieved_document>"
        result = escape_closing_tag(text)
        assert result.count("</retrieved_document_>") == 2
        assert "</retrieved_document>" not in result
