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
_MAX_RETRIES = 3
_RETRY_DELAYS = (2, 5, 10)
_MODELS_CACHE_TTL = 600  # 10 minutes

_think_re = re.compile(r"<think>.*?</think>", re.DOTALL)
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


def _auth_headers(*, with_content_type: bool = False) -> dict[str, str]:
    h: dict[str, str] = {"Authorization": f"Bearer {settings.openrouter_api_key}"}
    if with_content_type:
        h["Content-Type"] = "application/json"
    return h


def _strip_think(text: str) -> str:
    return _think_re.sub("", text).strip()


async def fetch_free_models() -> list[dict]:
    """Fetch free models from OpenRouter that support system prompts.

    Returns list of dicts with 'id' and 'name' keys. Uses 10-min cache.
    """
    global _models_cache, _cache_ts

    if _models_cache and (time.time() - _cache_ts) < _MODELS_CACHE_TTL:
        return _models_cache

    async with _models_lock:
        if _models_cache and (time.time() - _cache_ts) < _MODELS_CACHE_TTL:
            return _models_cache

        timeout = aiohttp.ClientTimeout(total=15)
        try:
            session = _get_session()
            async with session.get(
                OPENROUTER_MODELS_URL, headers=_auth_headers(), timeout=timeout
            ) as resp:
                if resp.status != 200:
                    logger.warning("OpenRouter models API returned %s", resp.status)
                    return []
                data = await resp.json()
        except Exception:
            logger.exception("Failed to fetch models from OpenRouter")
            return []

        candidates = []
        for m in data.get("data", []):
            pricing = m.get("pricing", {})
            if pricing.get("prompt", "1") != "0" or pricing.get("completion", "1") != "0":
                continue
            candidates.append({"id": m["id"], "name": m.get("name", m["id"])})

        # Quick-check all candidates in parallel; exclude only permanently broken ones
        async def _is_alive(model_id: str) -> bool:
            payload = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": "Reply OK."},
                    {"role": "user", "content": "ping"},
                ],
                "max_tokens": 1,
            }
            try:
                session = _get_session()
                async with session.post(
                    OPENROUTER_URL,
                    json=payload,
                    headers=_auth_headers(with_content_type=True),
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status in (400, 404):
                        body = await resp.text()
                        logger.info("Excluding %s: %s %s", model_id, resp.status, body[:120])
                        return False
                    return True
            except Exception:
                return True  # network error — assume alive

        results = await asyncio.gather(*[_is_alive(m["id"]) for m in candidates])
        models = [m for m, ok in zip(candidates, results) if ok]

        models.sort(key=lambda x: x["name"])
        _models_cache = models
        _cache_ts = time.time()
        logger.info("Fetched %d free models (%d alive)", len(candidates), len(models))
        return models


async def validate_model(model: str) -> str | None:
    """Test if a model supports system messages.

    Returns None on success, or an error description string.
    """
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
            OPENROUTER_URL,
            json=payload,
            headers=_auth_headers(with_content_type=True),
            timeout=timeout,
        ) as resp:
            if resp.status == 200:
                return None
            body = await resp.text()
            logger.warning("Model validation failed for %s: %s %s", model, resp.status, body)
            return (
                f"Модель <code>{model}</code> вернула ошибку {resp.status}. "
                "Возможно, она не поддерживает system-промпты."
            )
    except Exception as e:
        logger.warning("Model validation error for %s: %s", model, e)
        return f"Не удалось проверить модель <code>{model}</code>: {html.escape(str(e))}"


_FALLBACK_MODEL = "openrouter/free"


async def _single_completion(messages: list[dict], model: str) -> str | None:
    """Try one model. Returns response text on success, None on retryable failure."""
    payload = {
        "model": model,
        "messages": messages,
        "include_reasoning": False,
    }
    timeout = aiohttp.ClientTimeout(total=LLM_TIMEOUT)

    for attempt in range(_MAX_RETRIES):
        try:
            session = _get_session()
            async with session.post(
                OPENROUTER_URL,
                json=payload,
                headers=_auth_headers(with_content_type=True),
                timeout=timeout,
            ) as resp:
                if resp.status == 429 or resp.status >= 500:
                    body = await resp.text()
                    logger.warning(
                        "%s returned %s (attempt %d/%d): %s",
                        model, resp.status, attempt + 1, _MAX_RETRIES, body[:200],
                    )
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(_RETRY_DELAYS[attempt])
                        continue
                    return None

                if resp.status != 200:
                    body = await resp.text()
                    logger.error("OpenRouter error %s for %s: %s", resp.status, model, body[:300])
                    return None

                try:
                    data = await resp.json()
                except (ValueError, aiohttp.ContentTypeError) as e:
                    body = await resp.text()
                    logger.error("Invalid JSON from %s: %s — %s", model, e, body[:500])
                    return None
        except asyncio.TimeoutError:
            logger.warning("Timeout for %s (attempt %d/%d)", model, attempt + 1, _MAX_RETRIES)
            if attempt < _MAX_RETRIES - 1:
                continue
            return None
        except aiohttp.ClientError as e:
            logger.error("HTTP error for %s: %s", model, e)
            return None
        else:
            break
    else:
        return None

    try:
        raw = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        logger.error("Unexpected response from %s: %s", model, data)
        return None

    return _strip_think(raw) if raw else None


async def chat_completion(messages: list[dict], model: str) -> str:
    result = await _single_completion(messages, model)
    if result:
        return result

    if model != _FALLBACK_MODEL:
        logger.info("Falling back from %s to %s", model, _FALLBACK_MODEL)
        result = await _single_completion(messages, _FALLBACK_MODEL)
        if result:
            return result

    return "Извини, AI-сервис временно недоступен. Попробуй через минуту."
