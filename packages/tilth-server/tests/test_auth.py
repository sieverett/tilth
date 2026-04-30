"""Tests for shared auth module."""

import pytest
from fastapi import HTTPException
from tilth_server._shared.auth import extract_caller_identity


class TestExtractCallerIdentity:
    def test_missing_header_raises_401(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            extract_caller_identity(header_value=None, known_callers={"svc-a"})
        assert exc_info.value.status_code == 401

    def test_empty_header_raises_401(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            extract_caller_identity(header_value="", known_callers={"svc-a"})
        assert exc_info.value.status_code == 401

    def test_unknown_caller_raises_401(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            extract_caller_identity(
                header_value="unknown-svc", known_callers={"svc-a"}
            )
        assert exc_info.value.status_code == 401

    def test_valid_caller_returns_identity(self) -> None:
        result = extract_caller_identity(
            header_value="svc-a", known_callers={"svc-a", "svc-b"}
        )
        assert result == "svc-a"
