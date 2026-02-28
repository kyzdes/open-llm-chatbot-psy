import asyncio
import logging

from aiogram import Router, F
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from bot.db.engine import get_db
from bot.db.repositories.user import get_or_create_user
from bot.db.repositories.conversation import add_message, get_messages
from bot.db.repositories.crisis import log_crisis_event
from bot.db.repositories.settings import get_setting
from bot.services.llm import chat_completion
from bot.services.history import build_messages
from bot.utils.prompts import CRISIS_RESPONSE
from bot.utils.formatting import md_to_html, sanitize_html
from bot.utils.constants import TYPING_INTERVAL, SETTING_CURRENT_MODEL
from bot.config import settings as app_settings

logger = logging.getLogger(__name__)

_MAX_CHUNK = 3500

router = Router()


def _split_response(text: str, max_len: int = _MAX_CHUNK) -> list[str]:
    """Split text on paragraph boundaries, falling back to sentence/hard split."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    _STRATEGIES = [
        ("\n\n", 2),  # paragraph boundary
        ("\n", 1),    # single newline
        (". ", 1),    # sentence boundary (keep the dot, skip the space)
        (" ", 1),     # word boundary
    ]

    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        cut = -1
        skip = 0
        for sep, sep_skip in _STRATEGIES:
            pos = text.rfind(sep, 0, max_len)
            if pos > 0:
                # For ". " keep the dot in the chunk
                cut = pos if sep != ". " else pos + 1
                skip = sep_skip if sep != ". " else 1
                break

        if cut <= 0:
            cut = max_len
            skip = 0

        chunks.append(text[:cut])
        text = text[cut + skip:]

    return chunks


async def _typing_keepalive(chat_id: int, bot, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TYPING_INTERVAL)
            break
        except asyncio.TimeoutError:
            continue


async def _safe_answer(message: Message, text: str) -> None:
    """Convert LLM Markdown to HTML, send with fallback to plain text."""
    html_text = sanitize_html(md_to_html(text))
    try:
        await message.answer(html_text, parse_mode="HTML")
    except TelegramBadRequest:
        await message.answer(text)


@router.message(F.text)
async def handle_text(message: Message, crisis_keyword: str | None = None) -> None:
    user_id = message.from_user.id
    text = message.text

    async with get_db() as db:
        await get_or_create_user(
            db,
            user_id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            language_code=message.from_user.language_code,
        )

        await add_message(db, user_id, "user", text)

        # Crisis handling
        crisis_sent = False
        if crisis_keyword:
            await log_crisis_event(db, user_id, "keyword", crisis_keyword)
            await message.answer(CRISIS_RESPONSE, parse_mode="HTML")
            crisis_sent = True

        model = await get_setting(db, SETTING_CURRENT_MODEL, app_settings.default_model)

        conversation = await get_messages(db, user_id)
        messages = await build_messages(db, conversation)

        if crisis_sent:
            messages.append({
                "role": "system",
                "content": "ВНИМАНИЕ: пользователь выразил кризисные мысли. "
                "Контакты горячих линий уже показаны. "
                "Ответь с максимальной эмпатией и поддержкой. "
                "Не игнорируй тему, но и не усиливай кризис.",
            })

        # Start typing indicator
        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(
            _typing_keepalive(message.chat.id, message.bot, stop_typing)
        )

        try:
            response = await chat_completion(messages, model)
        except Exception:
            logger.exception("Unexpected LLM error for user %s", user_id)
            response = "Извини, произошла ошибка. Попробуй ещё раз."
        finally:
            stop_typing.set()
            await typing_task

        if not response or not response.strip():
            response = "Извини, произошла ошибка. Попробуй ещё раз."

        await add_message(db, user_id, "assistant", response)

    for chunk in _split_response(response):
        await _safe_answer(message, chunk)
