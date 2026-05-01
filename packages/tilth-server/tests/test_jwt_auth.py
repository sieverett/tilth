"""Tests for JWT authentication middleware."""

import time

import jwt
import pytest
from tilth_server._shared.auth import (
    AuthMode,
    JWTAuthenticator,
    extract_caller_identity,
)

SIGNING_KEY = "test-secret-key-for-unit-tests"


def _make_token(
    sub: str,
    roles: list[str] | None = None,
    expired: bool = False,
) -> str:
    payload = {
        "sub": sub,
        "iat": time.time(),
        "exp": time.time() + (-3600 if expired else 3600),
    }
    if roles is not None:
        payload["roles"] = roles
    return jwt.encode(payload, SIGNING_KEY, algorithm="HS256")


# --- Auth mode selection ---


class TestAuthMode:
    def test_dev_mode_uses_header(self) -> None:
        """In dev mode, x-workload-identity header is trusted."""
        known = {"test-svc"}
        result = extract_caller_identity(
            header_value="test-svc",
            known_callers=known,
            mode=AuthMode.DEV,
        )
        assert result == "test-svc"

    def test_prod_mode_requires_jwt(self) -> None:
        """In prod mode, missing Authorization header → 401."""
        known = {"test-svc"}
        authenticator = JWTAuthenticator(
            signing_key=SIGNING_KEY, algorithm="HS256"
        )
        with pytest.raises(Exception, match="401"):
            extract_caller_identity(
                header_value=None,
                known_callers=known,
                mode=AuthMode.PROD,
                jwt_authenticator=authenticator,
                authorization_header=None,
            )

    def test_prod_mode_valid_token(self) -> None:
        """In prod mode, valid JWT extracts subject as caller."""
        known = {"test-svc"}
        authenticator = JWTAuthenticator(
            signing_key=SIGNING_KEY, algorithm="HS256"
        )
        token = _make_token(sub="test-svc")
        result = extract_caller_identity(
            header_value=None,
            known_callers=known,
            mode=AuthMode.PROD,
            jwt_authenticator=authenticator,
            authorization_header=f"Bearer {token}",
        )
        assert result == "test-svc"

    def test_prod_mode_unknown_subject_401(self) -> None:
        """In prod mode, valid JWT with unknown subject → 401."""
        known = {"test-svc"}
        authenticator = JWTAuthenticator(
            signing_key=SIGNING_KEY, algorithm="HS256"
        )
        token = _make_token(sub="unknown-svc")
        with pytest.raises(Exception, match="401"):
            extract_caller_identity(
                header_value=None,
                known_callers=known,
                mode=AuthMode.PROD,
                jwt_authenticator=authenticator,
                authorization_header=f"Bearer {token}",
            )


# --- JWT validation ---


class TestJWTAuthenticator:
    def test_valid_token(self) -> None:
        auth = JWTAuthenticator(signing_key=SIGNING_KEY, algorithm="HS256")
        token = _make_token(sub="my-service")
        claims = auth.validate(token)
        assert claims["sub"] == "my-service"

    def test_expired_token_raises(self) -> None:
        auth = JWTAuthenticator(signing_key=SIGNING_KEY, algorithm="HS256")
        token = _make_token(sub="my-service", expired=True)
        with pytest.raises(Exception, match="expired|invalid"):
            auth.validate(token)

    def test_invalid_signature_raises(self) -> None:
        auth = JWTAuthenticator(signing_key=SIGNING_KEY, algorithm="HS256")
        token = jwt.encode(
            {"sub": "hacker", "exp": time.time() + 3600},
            "wrong-key",
            algorithm="HS256",
        )
        with pytest.raises(Exception, match="invalid"):
            auth.validate(token)

    def test_missing_sub_raises(self) -> None:
        auth = JWTAuthenticator(signing_key=SIGNING_KEY, algorithm="HS256")
        token = jwt.encode(
            {"exp": time.time() + 3600},
            SIGNING_KEY,
            algorithm="HS256",
        )
        with pytest.raises(Exception, match="sub"):
            auth.validate(token)


# --- Admin role check ---


class TestAdminAuth:
    def test_admin_role_in_token(self) -> None:
        auth = JWTAuthenticator(signing_key=SIGNING_KEY, algorithm="HS256")
        token = _make_token(sub="admin-user", roles=["admin"])
        claims = auth.validate(token)
        assert auth.has_role(claims, "admin")

    def test_no_admin_role(self) -> None:
        auth = JWTAuthenticator(signing_key=SIGNING_KEY, algorithm="HS256")
        token = _make_token(sub="normal-user", roles=["reader"])
        claims = auth.validate(token)
        assert not auth.has_role(claims, "admin")

    def test_no_roles_claim(self) -> None:
        auth = JWTAuthenticator(signing_key=SIGNING_KEY, algorithm="HS256")
        token = _make_token(sub="basic-user")
        claims = auth.validate(token)
        assert not auth.has_role(claims, "admin")
