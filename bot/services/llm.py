import asyncio
import html
import re
import time
import logging

import aiohttp

from bot.config import settings
from bot.utils.constants import LLM_TIMEOUT

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]
_MODELS_CACHE_TTL = 600  # 10 minutes

_think_pattern = re.compile(r"<think>.*?</think>", re.DOTALL)
_models_cache: list[dict] = []
_cache_ts: float = 0
_models_lock = asyncio.Lock()

_session: aiohttp.ClientSession | None = None


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def close_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None


def _strip_think(text: str) -> str:
    return _think_pattern.sub("", text).strip()


async def fetch_free_models() -> list[dict]:
    """Fetch free models from OpenRouter that support system prompts.

    Returns list of dicts with 'id' and 'name' keys. Uses 10-min cache.
    """
    global _models_cache, _cache_ts

    if _models_cache and (time.time() - _cache_ts) < _MODELS_CACHE_TTL:
        return _models_cache

    async with _models_lock:
        # Double-check after acquiring lock
        if _models_cache and (time.time() - _cache_ts) < _MODELS_CACHE_TTL:
            return _models_cache

        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
        }
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            session = _get_session()
            async with session.get(OPENROUTER_MODELS_URL, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    logger.warning("OpenRouter models API returned %s", resp.status)
                    return []
                data = await resp.json()
        except Exception:
            logger.exception("Failed to fetch models from OpenRouter")
            return []

        models = []
        for m in data.get("data", []):
            pricing = m.get("pricing", {})
            prompt_price = pricing.get("prompt", "1")
            completion_price = pricing.get("completion", "1")
            if prompt_price != "0" or completion_price != "0":
                continue
            # Skip models that don't support chat / system messages
            arch = m.get("architecture", {})
            if arch.get("modality", "") == "image->text":
                continue
            models.append({"id": m["id"], "name": m.get("name", m["id"])})

        models.sort(key=lambda x: x["name"])
        _models_cache = models
        _cache_ts = time.time()
        return models


async def validate_model(model: str) -> str | None:
    """Test if a model supports system messages.

    Returns None on success, or an error description string.
    """
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Reply with OK."},
            {"role": "user", "content": "ping"},
        ],
        "max_tokens": 1,
    }
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        session = _get_session()
        async with session.post(
            OPENROUTER_URL, json=payload, headers=headers, timeout=timeout
        ) as resp:
            if resp.status == 200:
                return None
            body = await resp.text()
            logger.warning("Model validation failed for %s: %s %s", model, resp.status, body)
            return f"Модель <code>{model}</code> вернула ошибку {resp.status}. Возможно, она не поддерживает system-промпты."
    except Exception as e:
        logger.warning("Model validation error for %s: %s", model, e)
        return f"Не удалось проверить модель <code>{model}</code>: {html.escape(str(e))}"


async def chat_completion(
    messages: list[dict],
    model: str,
) -> str:
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "include_reasoning": False,
    }

    timeout = aiohttp.ClientTimeout(total=LLM_TIMEOUT)
    data: dict | None = None

    for attempt in range(MAX_RETRIES):
        try:
            session = _get_session()
            async with session.post(
                OPENROUTER_URL, json=payload, headers=headers, timeout=timeout
            ) as resp:
                if resp.status == 429:
                    body = await resp.text()
                    logger.warning(
                        "Rate limited (attempt %d/%d): %s",
                        attempt + 1, MAX_RETRIES, body,
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return "Извини, AI-сервис временно перегружен. Попробуй через минуту."

                if resp.status != 200:
                    body = await resp.text()
                    logger.error("OpenRouter error %s: %s", resp.status, body)
                    return "Извини, произошла ошибка при обращении к AI. Попробуй ещё раз чуть позже."

                try:
                    data = await resp.json()
                except (ValueError, aiohttp.ContentTypeError) as e:
                    body = await resp.text()
                    logger.error("Invalid JSON from OpenRouter: %s — %s", e, body[:500])
                    return "Извини, получен некорректный ответ от AI. Попробуй ещё раз."
        except asyncio.TimeoutError:
            logger.warning("LLM timeout (attempt %d/%d)", attempt + 1, MAX_RETRIES)
            if attempt < MAX_RETRIES - 1:
                continue
            return "Извини, AI долго думает и не успел ответить. Попробуй ещё раз."
        except aiohttp.ClientError as e:
            logger.error("HTTP error: %s", e)
            return "Извини, ошибка соединения с AI. Попробуй ещё раз."
        else:
            break

    if data is None:
        return "Извини, не удалось получить ответ от AI. Попробуй ещё раз."

    try:
        raw = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        logger.error("Unexpected OpenRouter response: %s", data)
        return "Извини, получен некорректный ответ от AI. Попробуй ещё раз."

    return _strip_think(raw) if raw else "..."


# ---------------------------------------------------------------------------
# Task-based model resolution
# ---------------------------------------------------------------------------

# Patterns for matching free model IDs by category
TASK_ROUTING: dict[str, list[str]] = {
    "reasoning": ["deepseek", "qwen"],
    "creative": ["llama", "gemma", "mistral"],
    "analytical": ["qwen", "deepseek", "nemotron"],
    "structured": ["deepseek", "qwen"],
}


async def resolve_model_for_task(category: str) -> str | None:
    """Pick the best available free model for a given task category.

    Returns model ID or None if no matching model found (caller should fall
    back to the global default).
    """
    patterns = TASK_ROUTING.get(category, [])
    if not patterns:
        return None

    models = await fetch_free_models()
    if not models:
        return None

    for pattern in patterns:
        for m in models:
            mid = m["id"].lower()
            if pattern in mid:
                return m["id"]

    # No match — return None, let caller use default
    return None
