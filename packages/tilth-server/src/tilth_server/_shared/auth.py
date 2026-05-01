"""Authentication — dev mode (header) and prod mode (JWT).

Dev mode: trusts x-workload-identity header. No verification.
Prod mode: validates JWT from Authorization header. Subject claim
becomes the caller identity. Roles claim used for admin access.

Set via TILTH_AUTH_MODE env var: "dev" (default) or "prod".
"""

import enum
import logging
from typing import Any

from fastapi import HTTPException

log = logging.getLogger("tilth.auth")


class AuthMode(enum.Enum):
    DEV = "dev"
    PROD = "prod"


class JWTAuthenticator:
    """Validates JWT tokens and extracts claims."""

    def __init__(self, signing_key: str, algorithm: str = "HS256") -> None:
        import jwt as _jwt

        self._jwt = _jwt
        self._signing_key = signing_key
        self._algorithm = algorithm

    def validate(self, token: str) -> dict[str, Any]:
        """Validate a JWT token and return its claims.

        Raises ValueError on invalid/expired tokens or missing sub claim.
        """
        try:
            claims = self._jwt.decode(
                token,
                self._signing_key,
                algorithms=[self._algorithm],
            )
        except self._jwt.ExpiredSignatureError as exc:
            raise ValueError("token expired") from exc
        except self._jwt.InvalidTokenError as exc:
            raise ValueError("invalid token") from exc

        if "sub" not in claims:
            raise ValueError("token missing sub claim")

        return claims

    def has_role(self, claims: dict[str, Any], role: str) -> bool:
        """Check if the token claims include a specific role."""
        roles = claims.get("roles", [])
        return role in roles


def extract_caller_identity(
    header_value: str | None,
    known_callers: set[str],
    *,
    mode: AuthMode = AuthMode.DEV,
    jwt_authenticator: JWTAuthenticator | None = None,
    authorization_header: str | None = None,
) -> str:
    """Extract and validate caller identity.

    In DEV mode: trusts x-workload-identity header.
    In PROD mode: validates JWT from Authorization header.

    Returns the caller string if valid.
    Raises HTTPException(401) if authentication fails.
    """
    if mode == AuthMode.DEV:
        if not header_value or header_value not in known_callers:
            raise HTTPException(status_code=401, detail="unknown caller")
        return header_value

    # PROD mode — JWT
    if jwt_authenticator is None:
        raise HTTPException(
            status_code=500,
            detail="JWT authenticator not configured",
        )

    if not authorization_header:
        raise HTTPException(
            status_code=401, detail="missing Authorization header"
        )

    # Extract Bearer token
    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401, detail="invalid Authorization header format"
        )

    token = parts[1]
    try:
        claims = jwt_authenticator.validate(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None

    caller = claims["sub"]
    if caller not in known_callers:
        raise HTTPException(status_code=401, detail="unknown caller")

    return caller


def require_admin(
    jwt_authenticator: JWTAuthenticator | None,
    authorization_header: str | None,
    mode: AuthMode,
) -> None:
    """Require admin role for mutation operations.

    In DEV mode: no-op (all callers are admin).
    In PROD mode: validates JWT has admin role.

    Raises HTTPException(403) if not admin.
    """
    if mode == AuthMode.DEV:
        return

    if jwt_authenticator is None or not authorization_header:
        raise HTTPException(status_code=403, detail="admin access required")

    parts = authorization_header.split(" ", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=403, detail="admin access required")

    try:
        claims = jwt_authenticator.validate(parts[1])
    except ValueError:
        raise HTTPException(
            status_code=403, detail="admin access required"
        ) from None

    if not jwt_authenticator.has_role(claims, "admin"):
        raise HTTPException(status_code=403, detail="admin role required")
