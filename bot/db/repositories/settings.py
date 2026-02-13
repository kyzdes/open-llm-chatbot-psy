import aiosqlite


async def get_setting(
    db: aiosqlite.Connection,
    key: str,
    default: str | None = None,
) -> str | None:
    cursor = await db.execute(
        "SELECT value FROM bot_settings WHERE key = ?", (key,)
    )
    row = await cursor.fetchone()
    if row:
        return row["value"]
    return default


async def set_setting(
    db: aiosqlite.Connection,
    key: str,
    value: str,
) -> None:
    await db.execute(
        """
        INSERT INTO bot_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    await db.commit()


async def delete_setting(
    db: aiosqlite.Connection,
    key: str,
) -> None:
    await db.execute("DELETE FROM bot_settings WHERE key = ?", (key,))
    await db.commit()
