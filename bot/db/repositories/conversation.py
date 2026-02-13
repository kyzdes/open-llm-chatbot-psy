import aiosqlite


def estimate_tokens(text: str) -> int:
    return max(1, len(text.encode("utf-8")) // 4)


async def add_message(
    db: aiosqlite.Connection,
    user_id: int,
    role: str,
    content: str,
) -> None:
    tokens_est = estimate_tokens(content)
    await db.execute(
        """
        INSERT INTO conversation_messages (user_id, role, content, tokens_est)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, role, content, tokens_est),
    )
    await db.commit()


async def get_messages(
    db: aiosqlite.Connection,
    user_id: int,
) -> list[dict]:
    cursor = await db.execute(
        """
        SELECT role, content, tokens_est, created_at
        FROM conversation_messages
        WHERE user_id = ?
        ORDER BY created_at ASC
        """,
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def delete_messages(
    db: aiosqlite.Connection,
    user_id: int,
) -> int:
    cursor = await db.execute(
        "DELETE FROM conversation_messages WHERE user_id = ?",
        (user_id,),
    )
    await db.commit()
    return cursor.rowcount
