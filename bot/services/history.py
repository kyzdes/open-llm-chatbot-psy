import aiosqlite

from bot.db.repositories.conversation import estimate_tokens
from bot.db.repositories.settings import get_setting
from bot.utils.constants import MAX_HISTORY_TOKENS
from bot.utils.prompts import SYSTEM_PROMPT


async def build_messages(db: aiosqlite.Connection, conversation: list[dict]) -> list[dict]:
    prompt = await get_setting(db, "system_prompt", SYSTEM_PROMPT)

    system_msg = {"role": "system", "content": prompt}
    system_tokens = estimate_tokens(prompt)
    budget = MAX_HISTORY_TOKENS - system_tokens

    selected: list[dict] = []
    used = 0

    for msg in reversed(conversation):
        t = msg.get("tokens_est") or estimate_tokens(msg["content"])
        if used + t > budget:
            break
        selected.append({"role": msg["role"], "content": msg["content"]})
        used += t

    selected.reverse()
    return [system_msg] + selected
