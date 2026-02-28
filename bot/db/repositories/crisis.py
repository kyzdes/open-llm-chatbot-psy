import aiosqlite


async def log_crisis_event(
    db: aiosqlite.Connection,
    user_id: int,
    trigger: str,
    matched: str | None,
) -> None:
    await db.execute(
        """
        INSERT INTO crisis_events (user_id, trigger, matched)
        VALUES (?, ?, ?)
        """,
        (user_id, trigger, matched),
    )
    await db.commit()
