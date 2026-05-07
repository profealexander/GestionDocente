"""SchoolAI REST API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from loguru import logger

from schoolai.api.routers import (
    attendance,
    auth,
    dev,
    grades,
    health,
    homework,
    llm_stats,
    scores,
    students,
    subjects,
    whatsapp_webhook,
)
from schoolai.config import settings as _settings


# ── Startup validation ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    if not _settings.jwt_secret_key:
        if _settings.debug:
            logger.warning(
                "JWT_SECRET_KEY no configurado — tokens firmados con clave vacía. "
                "Establece JWT_SECRET_KEY en .env antes de usar en producción."
            )
        else:
            raise RuntimeError(
                "JWT_SECRET_KEY está vacío. Configura esta variable en .env antes de iniciar la API."
            )
    if _settings.redis_url:
        from schoolai.bot.state import init_redis
        init_redis(_settings.redis_url)
    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    lifespan=lifespan,
    title="SchoolAI API",
    version="1.0.0",
    swagger_ui_init_oauth={"usePkceWithAuthorizationCodeGrant": True},
    description=(
        "REST API for SchoolAI — school assistant for teachers.\n\n"
        "## Documentation\n"
        "- **`/docs`** — Interactive API explorer (Swagger UI)\n"
        "- **`/redoc`** — Technical reference (ReDoc)\n"
        "- **`/openapi.json`** — OpenAPI schema\n\n"
        "## Resources\n"
        "- **Grades** — School grade catalog with level and sublevel\n"
        "- **Subjects** — Academic subject catalog\n"
        "- **Students** — Student roster by grade\n"
        "- **Homework** — Register and query academic tasks\n"
        "- **Attendance** — Absence, tardiness and justified records\n"
    ),
    contact={
        "name": "SchoolAI",
        "email": "admin@schoolai.edu",
    },
    license_info={
        "name": "Private",
    },
    # Disable default docs — we serve custom ones below
    docs_url=None,
    redoc_url=None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────

_origins = [o.strip() for o in _settings.cors_origins.split(",") if o.strip()] or ["*"]
# allow_credentials=True is only valid when origins are explicit (not "*")
_allow_credentials = "*" not in _origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(grades.router)
app.include_router(subjects.router)
app.include_router(students.router)
app.include_router(homework.router)
app.include_router(attendance.router)
app.include_router(scores.router)
app.include_router(llm_stats.router)
app.include_router(dev.router)
app.include_router(whatsapp_webhook.router)


# ── Custom docs ───────────────────────────────────────────────────────────────


@app.get("/docs", include_in_schema=False, tags=["Documentation"])
async def swagger_ui():
    """Interactive API explorer for developers."""
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="SchoolAI API — Swagger UI",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
    )


@app.get("/redoc", include_in_schema=False, tags=["Documentation"])
async def redoc():
    """Technical API reference."""
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="SchoolAI API — ReDoc",
        redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
    )


@app.get("/", include_in_schema=False)
async def root():
    return {
        "app": "SchoolAI API",
        "version": "1.0.0",
        "docs": {
            "swagger": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        },
    }


# ── Custom OpenAPI schema ─────────────────────────────────────────────────────


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        contact=app.contact,
        routes=app.routes,
    )
    schema["info"]["x-logo"] = {"url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"}
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT obtenido en POST /auth/token",
        },
    }
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
