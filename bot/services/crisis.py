import logging

from bot.utils.crisis_keywords import CRISIS_PATTERN
from bot.utils.prompts import CRISIS_LLM_PROMPT
from bot.services.llm import chat_completion

logger = logging.getLogger(__name__)


def keyword_check(text: str) -> str | None:
    m = CRISIS_PATTERN.search(text.lower())
    return m.group(0) if m else None


async def llm_crisis_check(text: str, model: str) -> bool:
    prompt = CRISIS_LLM_PROMPT.format(message=text)
    messages = [{"role": "user", "content": prompt}]
    try:
        result = await chat_completion(messages, model)
        return "CRISIS" in result.upper()
    except Exception:
        logger.exception("LLM crisis check failed")
        return False
