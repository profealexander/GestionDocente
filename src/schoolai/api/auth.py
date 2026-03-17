"""JWT authentication utilities for the SchoolAI REST API.

Flow:
  1. Client POSTs  { telegram_id, api_key }  to  POST /auth/token
  2. Server validates api_key == settings.api_secret
  3. Server resolves role (superadmin | admin | secretaria | teacher) from DB
  4. Server returns a signed JWT valid for settings.jwt_expire_hours
  5. Client includes  Authorization: Bearer <token>  on protected endpoints
  6. Dependency get_current_user() verifies the token and returns the payload

Configuration (.env):
  JWT_SECRET_KEY=<random 32+ char string>   # required for auth to work
  API_SECRET=<shared secret for clients>     # required for /auth/token
  JWT_EXPIRE_HOURS=24                        # optional, default 24
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from schoolai.config import settings

_ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=True)


# ── Token creation ────────────────────────────────────────────────────────────


def create_access_token(telegram_id: int, role: str) -> str:
    """Sign a JWT with telegram_id as subject and role as claim."""
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload: dict[str, Any] = {
        "sub": str(telegram_id),
        "role": role,
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def create_access_token_for_teacher(teacher_id: int, username: str, role: str) -> str:
    """Sign a JWT for PWA login (username/password flow)."""
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload: dict[str, Any] = {
        "sub": f"teacher:{teacher_id}",
        "username": username,
        "role": role,
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


# ── Token verification ────────────────────────────────────────────────────────


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict[str, Any]:
    """FastAPI dependency — extract and validate JWT from Authorization header.

    Returns dict with keys: telegram_id (int), role (str).
    Raises 401 on missing / invalid / expired tokens.
    Raises 503 if JWT is not configured on the server.
    """
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticación no configurada en el servidor.",
        )
    try:
        payload = jwt.decode(
            creds.credentials,
            settings.jwt_secret_key,
            algorithms=[_ALGORITHM],
        )
        sub: str = payload["sub"]
        role: str = payload.get("role", "teacher")
        if sub.startswith("teacher:"):
            return {"teacher_id": int(sub.split(":")[1]), "username": payload.get("username"), "role": role}
        return {"telegram_id": int(sub), "role": role}
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado. Solicita uno nuevo en /auth/token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
