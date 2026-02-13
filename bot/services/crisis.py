import logging

import aiosqlite

from bot.utils.crisis_keywords import ALL_CRISIS_KEYWORDS
from bot.utils.prompts import CRISIS_LLM_PROMPT
from bot.services.llm import chat_completion

logger = logging.getLogger(__name__)


def keyword_check(text: str) -> str | None:
    lower = text.lower()
    for kw in ALL_CRISIS_KEYWORDS:
        if kw in lower:
            return kw
    return None


async def llm_crisis_check(text: str, model: str) -> bool:
    prompt = CRISIS_LLM_PROMPT.format(message=text)
    messages = [{"role": "user", "content": prompt}]
    try:
        result = await chat_completion(messages, model)
        return "CRISIS" in result.upper()
    except Exception:
        logger.exception("LLM crisis check failed")
        return False


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
