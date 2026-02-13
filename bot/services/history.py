import aiosqlite

from bot.db.repositories.conversation import estimate_tokens
from bot.db.repositories.settings import get_setting
from bot.utils.constants import MAX_HISTORY_TOKENS
from bot.utils.prompts import SYSTEM_PROMPT

# When a role/task is active, leave room for the injected master prompt
MAX_HISTORY_TOKENS_WITH_ROLE = 60_000


async def build_messages(
    db: aiosqlite.Connection,
    conversation: list[dict],
    *,
    role_prompt: str | None = None,
    task_prompt: str | None = None,
) -> list[dict]:
    """Build the messages list for the LLM.

    If task_prompt is set, it is injected as a fake user/assistant pair at the
    top (after system), and the history budget is reduced.
    If role_prompt is set (free chat within role), it replaces the system prompt.
    """
    # Determine system prompt
    if role_prompt:
        system_content = role_prompt
    else:
        system_content = await get_setting(db, "system_prompt", SYSTEM_PROMPT)

    system_msg = {"role": "system", "content": system_content}
    system_tokens = estimate_tokens(system_content)

    # Budget for conversation history
    budget = MAX_HISTORY_TOKENS - system_tokens
    if task_prompt:
        task_tokens = estimate_tokens(task_prompt) + 20  # +20 for the assistant ack
        budget = MAX_HISTORY_TOKENS_WITH_ROLE - system_tokens - task_tokens

    # Select messages from history (most recent first)
    selected: list[dict] = []
    used = 0
    for msg in reversed(conversation):
        t = msg.get("tokens_est") or estimate_tokens(msg["content"])
        if used + t > budget:
            break
        selected.append({"role": msg["role"], "content": msg["content"]})
        used += t

    selected.reverse()

    # Assemble final messages
    result = [system_msg]

    if task_prompt:
        # Inject master prompt as a fake user/assistant exchange
        result.append({"role": "user", "content": task_prompt})
        result.append({"role": "assistant", "content": "Понял. Готов работать по этому заданию."})

    result.extend(selected)
    return result
