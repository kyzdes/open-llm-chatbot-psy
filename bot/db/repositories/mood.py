import aiosqlite


async def add_entry(
    db: aiosqlite.Connection,
    user_id: int,
    score: int,
    note: str | None = None,
) -> None:
    await db.execute(
        """
        INSERT INTO mood_entries (user_id, score, note)
        VALUES (?, ?, ?)
        """,
        (user_id, score, note),
    )
    await db.commit()


async def get_entries_range(
    db: aiosqlite.Connection,
    user_id: int,
    days: int = 7,
) -> list[dict]:
    cursor = await db.execute(
        """
        SELECT score, note, created_at
        FROM mood_entries
        WHERE user_id = ? AND created_at >= datetime('now', ?)
        ORDER BY created_at ASC
        """,
        (user_id, f"-{days} days"),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
