"""Health check endpoint — for monitoring and Docker healthchecks."""

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Health check", include_in_schema=True)
async def health():
    """Returns the operational status of the API, database, and Redis."""
    status = {"api": "ok", "db": "unknown", "redis": "unknown"}

    # ── Database ──────────────────────────────────────────────────────────────
    try:
        from schoolai.db.connection import async_session

        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        status["db"] = "ok"
    except Exception as exc:
        status["db"] = f"error: {exc}"

    # ── Redis ─────────────────────────────────────────────────────────────────
    try:
        from schoolai.bot.state_store import _redis_client

        if _redis_client is None:
            status["redis"] = "not configured"
        else:
            _redis_client.ping()
            status["redis"] = "ok"
    except Exception as exc:
        status["redis"] = f"error: {exc}"

    return status
