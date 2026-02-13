import aiosqlite


async def get_or_create_user(
    db: aiosqlite.Connection,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    language_code: str | None = None,
) -> dict:
    await db.execute(
        """
        INSERT INTO users (user_id, username, first_name, language_code)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            language_code = excluded.language_code
        """,
        (user_id, username, first_name, language_code),
    )
    await db.commit()

    cursor = await db.execute(
        "SELECT * FROM users WHERE user_id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    return dict(row)
