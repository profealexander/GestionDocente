"""Access level helpers for SchoolAI bot.

Levels (ordered):
  superadmin  — ADMIN_TELEGRAM_ID in .env — full access always
  admin       — teacher with cargo in (rector, vicerrector, coordinador, inspector)
  secretaria  — teacher with cargo=secretaria
  teacher     — any linked teacher without institutional cargo
  none        — unregistered user
"""

from schoolai.config import settings

# Cargos that grant admin-level access (permissions TBD per cargo later)
ADMIN_CARGOS = {"rector", "vicerrector", "coordinador", "inspector"}
ALL_CARGOS = ADMIN_CARGOS | {"secretaria"}


async def get_access_level(telegram_id: int) -> str:
    """Return the access level for a given telegram_id."""
    if settings.admin_telegram_id and telegram_id == settings.admin_telegram_id:
        return "superadmin"

    from schoolai.db.connection import get_db_session
    from schoolai.skills.db.position_service import get_admin_cargo

    from schoolai.skills.db.schedule_service import get_teacher_by_telegram

    async with get_db_session() as session:
        teacher = await get_teacher_by_telegram(session, telegram_id)
        if not teacher:
            return "none"
        cargo = await get_admin_cargo(session, telegram_id)

    if cargo in ADMIN_CARGOS:
        return "admin"
    if cargo == "secretaria":
        return "secretaria"
    return "teacher"


def is_admin(level: str) -> bool:
    return level in ("superadmin", "admin")


def is_superadmin(telegram_id: int) -> bool:
    return bool(settings.admin_telegram_id and telegram_id == settings.admin_telegram_id)
