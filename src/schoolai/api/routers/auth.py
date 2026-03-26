"""Auth router — issue JWT tokens."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from schoolai.api.auth import create_access_token, create_access_token_for_teacher
from schoolai.config import settings

router = APIRouter(prefix="/auth", tags=["Auth"])


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
async def get_token(body: TokenRequest) -> TokenResponse:
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
    if body.api_key != settings.api_secret:
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
async def login(body: LoginRequest) -> TokenResponse:
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT secret no configurado en el servidor.",
        )

    import bcrypt as _bcrypt
    from sqlalchemy import select

    from schoolai.db.connection import async_session
    from schoolai.db.models.teacher import Teacher

    async with async_session() as session:
        result = await session.execute(
            select(Teacher).where(Teacher.username == body.username, Teacher.is_active == True),  # noqa: E712
        )
        teacher = result.scalar_one_or_none()

    if not teacher or not teacher.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas.",
        )

    if not _bcrypt.checkpw(body.password.encode(), teacher.password_hash.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas.",
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
        from schoolai.db.connection import async_session
        from schoolai.skills.db.position_service import get_admin_cargo

        async with async_session() as session:
            cargo = await get_admin_cargo(session, telegram_id)
        if cargo in ADMIN_CARGOS:
            return "admin"
        if cargo == "secretaria":
            return "secretaria"
    except Exception:
        pass  # DB not reachable → default to teacher

    return "teacher"
