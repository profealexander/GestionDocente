"""Verify database connection and ORM model."""

import asyncio
import sys

sys.path.insert(0, "src")

from schoolai.config import settings
from schoolai.db.connection import async_session
from schoolai.db.models import Homework
from sqlalchemy import select


async def main() -> None:
    print(f"Connecting to: {settings.database_url}")
    async with async_session() as session:
        result = await session.execute(
            select(Homework).order_by(Homework.id.desc()).limit(5)
        )
        rows = result.scalars().all()
        print(f"\nLast {len(rows)} homework records:")
        for hw in rows:
            print(f"  [{hw.id}] {hw.course!r:20} | {hw.homework[:50]!r} | open={hw.is_open}")

    print("\nConnection OK")


if __name__ == "__main__":
    asyncio.run(main())
