from __future__ import annotations

from core.settings import settings
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)

# Tokens accepted in dev mode (non-empty string = valid for demo purposes).
# Production: replace with real JWT validation.
_DEV_TOKENS: set[str] = {"dev-token", "test-token"}


async def require_auth(request: Request) -> None:
    """FastAPI dependency: validate Bearer token or bypass if ADMIN_NOAUTH is set."""
    if settings.feature_admin_noauth:
        return

    credentials: HTTPAuthorizationCredentials | None = await _bearer_scheme(request)
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    if not _is_valid_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _is_valid_token(token: str) -> bool:
    return bool(token) and token in _DEV_TOKENS
