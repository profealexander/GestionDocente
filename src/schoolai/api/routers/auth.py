"""Auth router — issue JWT tokens."""

import hmac
import time
from collections import defaultdict
from dataclasses import dataclass, field

import bcrypt as _bcrypt
from fastapi import APIRouter, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select

from schoolai.api.auth import create_access_token, create_access_token_for_teacher
from schoolai.config import settings
from schoolai.db.connection import async_session
from schoolai.db.models.teacher import Teacher
from schoolai.skills.db.position_service import get_admin_cargo

router = APIRouter(prefix="/auth", tags=["Auth"])

# ── Rate limiting (in-memory, per IP) ──────────────────────────────────────────

_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 10  # attempts per window


@dataclass
class _Bucket:
    attempts: list[float] = field(default_factory=list)


_rate_buckets: dict[str, _Bucket] = defaultdict(_Bucket)


def _check_rate_limit(ip: str) -> None:
    """Raise 429 if IP exceeded the rate limit window."""
    now = time.monotonic()
    bucket = _rate_buckets[ip]
    # prune expired
    bucket.attempts = [t for t in bucket.attempts if t > now - _RATE_LIMIT_WINDOW]
    if len(bucket.attempts) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiadas solicitudes. Intenta de nuevo en {_RATE_LIMIT_WINDOW}s.",
        )
    bucket.attempts.append(now)


class TokenRequest(BaseModel):
    telegram_id: int
    api_key: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    expires_in: int  # seconds


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Obtener token JWT",
    description=(
        "Autentica al cliente con `telegram_id` + `api_key` (secreto compartido) "
        "y devuelve un JWT válido para las rutas protegidas.\n\n"
        "Incluir el token en el header: `Authorization: Bearer <token>`"
    ),
)
async def get_token(request: Request, body: TokenRequest) -> TokenResponse:
    _check_rate_limit(request.client.host if request.client else "unknown")
    if not settings.api_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API secret no configurado en el servidor.",
        )
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT secret no configurado en el servidor.",
        )
    if not hmac.compare_digest(body.api_key, settings.api_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida.",
        )

    # Resolve role
    role = await _resolve_role(body.telegram_id)
    token = create_access_token(body.telegram_id, role)

    return TokenResponse(
        access_token=token,
        role=role,
        expires_in=settings.jwt_expire_hours * 3600,
    )


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login con usuario y contraseña (PWA)",
    description="Autentica con `username` + `password` y devuelve un JWT.",
)
async def login(request: Request, body: LoginRequest) -> TokenResponse:
    _check_rate_limit(request.client.host if request.client else "unknown")
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT secret no configurado en el servidor.",
        )

    async with async_session() as session:
        result = await session.execute(
            select(Teacher).where(Teacher.username == body.username, Teacher.is_active.is_(True)),
        )
        teacher = result.scalar_one_or_none()

    if not teacher or not teacher.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )

    if not _bcrypt.checkpw(body.password.encode(), teacher.password_hash.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )

    role = await _resolve_role(teacher.telegram_id) if teacher.telegram_id else "teacher"
    token = create_access_token_for_teacher(teacher.id, teacher.username, role)

    return TokenResponse(
        access_token=token,
        role=role,
        expires_in=settings.jwt_expire_hours * 3600,
    )


async def _resolve_role(telegram_id: int) -> str:
    """Determine role from DB + superadmin config."""
    from schoolai.bot.permissions import ADMIN_CARGOS, is_superadmin

    if is_superadmin(telegram_id):
        return "superadmin"

    try:
        async with async_session() as session:
            cargo = await get_admin_cargo(session, telegram_id)
        if cargo in ADMIN_CARGOS:
            return "admin"
        if cargo == "secretaria":
            return "secretaria"
    except Exception as exc:
        logger.warning(f"[auth] error resolviendo rol para {telegram_id}: {exc}")
        # DB no disponible → rol por defecto

    return "teacher"
