import asyncio
import logging

from aiogram import Router, F
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, BufferedInputFile

from bot.db.engine import get_db
from bot.db.repositories.user import get_or_create_user
from bot.db.repositories.conversation import add_message, get_messages
from bot.db.repositories.settings import get_setting
from bot.services.llm import chat_completion, resolve_model_for_task
from bot.services.history import build_messages
from bot.services.crisis import log_crisis_event
from bot.services.roles import get_role, get_task, OutputFormat
from bot.services.export import markdown_to_pdf, markdown_tables_to_excel, export_as_markdown
from bot.handlers.roles import get_user_role_task
from bot.utils.prompts import CRISIS_RESPONSE
from bot.utils.formatting import md_to_html, sanitize_html
from bot.utils.constants import TYPING_INTERVAL
from bot.config import settings as app_settings

logger = logging.getLogger(__name__)

_MAX_CHUNK = 3500  # leave room for HTML tags added by md_to_html

router = Router()


def _split_response(text: str, max_len: int = _MAX_CHUNK) -> list[str]:
    """Split text on paragraph boundaries, falling back to sentence/hard split."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Try splitting at paragraph boundary (double newline)
        cut = text.rfind("\n\n", 0, max_len)
        if cut > 0:
            chunks.append(text[: cut])
            text = text[cut + 2 :]
            continue

        # Try splitting at single newline
        cut = text.rfind("\n", 0, max_len)
        if cut > 0:
            chunks.append(text[: cut])
            text = text[cut + 1 :]
            continue

        # Try splitting at sentence boundary
        cut = text.rfind(". ", 0, max_len)
        if cut > 0:
            chunks.append(text[: cut + 1])
            text = text[cut + 2 :]
            continue

        # Hard split at space
        cut = text.rfind(" ", 0, max_len)
        if cut > 0:
            chunks.append(text[: cut])
            text = text[cut + 1 :]
            continue

        # Last resort: hard cut
        chunks.append(text[: max_len])
        text = text[max_len :]

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


async def _send_document(message: Message, buf, filename: str) -> None:
    """Send BytesIO as a document."""
    doc = BufferedInputFile(buf.read(), filename=filename)
    await message.answer_document(doc)


async def _send_with_export(
    message: Message,
    response: str,
    output_format: OutputFormat | None,
    task_name: str = "document",
) -> None:
    """Send the LLM response, optionally exporting as PDF/Excel."""
    if output_format == OutputFormat.PDF:
        buf = markdown_to_pdf(response, title=task_name)
        if buf:
            await _send_document(message, buf, f"{task_name}.pdf")
            # Also send a short text summary
            preview = response[:500] + ("..." if len(response) > 500 else "")
            await _safe_answer(message, preview + "\n\n\u2191 Полный документ — в PDF-файле выше.")
            return
        # Fallback: send as .md file
        buf = export_as_markdown(response, task_name)
        await _send_document(message, buf, f"{task_name}.md")
        await _safe_answer(message, "PDF не удалось сгенерировать, отправил как Markdown-файл.")
        return

    if output_format == OutputFormat.EXCEL:
        buf = markdown_tables_to_excel(response, title=task_name)
        if buf:
            await _send_document(message, buf, f"{task_name}.xlsx")
            # Also send the text response for context
            for chunk in _split_response(response):
                await _safe_answer(message, chunk)
            return
        # Fallback: no tables found, send text + .md
        buf = export_as_markdown(response, task_name)
        await _send_document(message, buf, f"{task_name}.md")
        await _safe_answer(message, "Таблицы не найдены для Excel, отправил как Markdown-файл.")
        return

    # TEXT or MARKDOWN or None — regular text output
    for chunk in _split_response(response):
        await _safe_answer(message, chunk)


@router.message(F.text)
async def handle_text(message: Message, crisis_keyword: str | None = None) -> None:
    user_id = message.from_user.id
    text = message.text

    db = await get_db()
    try:
        await get_or_create_user(
            db,
            user_id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            language_code=message.from_user.language_code,
        )

        # Save user message
        await add_message(db, user_id, "user", text)

        # Crisis handling
        crisis_sent = False
        if crisis_keyword:
            await log_crisis_event(db, user_id, "keyword", crisis_keyword)
            await message.answer(CRISIS_RESPONSE, parse_mode="HTML")
            crisis_sent = True

        # Check if user has an active role/task
        role_id, task_id = await get_user_role_task(db, user_id)

        role_obj = get_role(role_id) if role_id else None
        task_obj = get_task(task_id) if task_id else None

        # Determine prompts for injection
        role_prompt = role_obj.system_prompt if role_obj and not task_obj else None
        task_prompt = task_obj.master_prompt if task_obj else None
        output_format = task_obj.output_format if task_obj else None

        # Get model — task-specific or global default
        if task_obj:
            model = await resolve_model_for_task(task_obj.model_category.value)
            if not model:
                model = await get_setting(db, "current_model", app_settings.default_model)
        else:
            model = await get_setting(db, "current_model", app_settings.default_model)

        # Build history with prompt injection
        conversation = await get_messages(db, user_id)
        messages = await build_messages(
            db,
            conversation,
            role_prompt=role_prompt,
            task_prompt=task_prompt,
        )

        # If crisis was detected, add a note for the LLM
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

        # Call LLM
        try:
            response = await chat_completion(messages, model)
        except Exception:
            logger.exception("Unexpected LLM error for user %s", user_id)
            response = "Извини, произошла ошибка. Попробуй ещё раз."
        finally:
            stop_typing.set()
            await typing_task

        # Guard against empty response
        if not response or not response.strip():
            response = "Извини, произошла ошибка. Попробуй ещё раз."

        # Save assistant response
        await add_message(db, user_id, "assistant", response)

        # Send response with optional export
        task_name = task_obj.name if task_obj else "document"
        await _send_with_export(message, response, output_format, task_name)

    finally:
        await db.close()
