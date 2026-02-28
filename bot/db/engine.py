import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import aiosqlite

from bot.config import settings
from bot.db.models import SCHEMA

_db_path = settings.db_path


async def _connect() -> aiosqlite.Connection:
    db = await aiosqlite.connect(_db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA busy_timeout=5000")
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    db = await _connect()
    try:
        yield db
    finally:
        await db.close()


async def init_db() -> None:
    os.makedirs(os.path.dirname(_db_path), exist_ok=True)
    async with get_db() as db:
        for statement in SCHEMA:
            await db.execute(statement)
        await db.commit()
