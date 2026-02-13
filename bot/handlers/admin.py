import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.db.engine import get_db
from bot.db.repositories.settings import set_setting, get_setting, delete_setting
from bot.services.llm import validate_model, fetch_free_models
from bot.keyboards.inline import model_select_keyboard
from bot.utils.constants import ADMIN_ID
from bot.utils.prompts import SYSTEM_PROMPT
from bot.config import settings as app_settings

logger = logging.getLogger(__name__)

router = Router()

# Temporary storage: maps message_id -> model list for that message
_model_lists: dict[int, list[dict]] = {}


@router.message(Command("modelchange"))
async def cmd_modelchange(message: Message) -> None:
    if message.from_user.id != ADMIN_ID:
        await message.answer("Эта команда доступна только администратору.")
        return

    db = await get_db()
    try:
        current = await get_setting(db, "current_model", app_settings.default_model)
    finally:
        await db.close()

    await message.answer("Загружаю список моделей...")
    models = await fetch_free_models()

    if not models:
        await message.answer(
            f"Не удалось получить список моделей.\n"
            f"Текущая модель: <code>{current}</code>",
            parse_mode="HTML",
        )
        return

    kb, truncated = model_select_keyboard(models, current)
    text = f"Текущая модель: <code>{current}</code>\n\nВыбери новую модель:"
    if truncated:
        text += f"\n<i>(показаны первые 20 из {len(models)})</i>"
    sent = await message.answer(text, reply_markup=kb, parse_mode="HTML")
    _model_lists[sent.message_id] = models


@router.callback_query(F.data.startswith("model:"))
async def model_chosen(callback: CallbackQuery) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только для администратора.", show_alert=True)
        return

    data = callback.data.split(":")[1]

    if data == "cancel":
        _model_lists.pop(callback.message.message_id, None)
        await callback.message.edit_text("Выбор модели отменён.")
        await callback.answer()
        return

    try:
        idx = int(data)
    except ValueError:
        await callback.answer("Некорректный выбор.", show_alert=True)
        return

    models = _model_lists.get(callback.message.message_id)
    if models is None:
        await callback.answer("Список устарел, вызовите /modelchange заново.", show_alert=True)
        return

    if idx < 0 or idx >= len(models):
        await callback.answer("Модель не найдена. Попробуй /modelchange заново.", show_alert=True)
        return

    model = models[idx]
    model_id = model["id"]
    model_name = model["name"]

    await callback.message.edit_text(f"Проверяю модель <code>{model_name}</code>...", parse_mode="HTML")

    error = await validate_model(model_id)
    if error:
        _model_lists.pop(callback.message.message_id, None)
        await callback.message.edit_text(f"Модель отклонена: {error}", parse_mode="HTML")
        await callback.answer()
        return

    db = await get_db()
    try:
        await set_setting(db, "current_model", model_id)
    finally:
        await db.close()

    _model_lists.pop(callback.message.message_id, None)

    await callback.message.edit_text(
        f"Модель изменена на: <b>{model_name}</b>\n<code>{model_id}</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("setprompt"))
async def cmd_setprompt(message: Message) -> None:
    if message.from_user.id != ADMIN_ID:
        await message.answer("Эта команда доступна только администратору.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        db = await get_db()
        try:
            current = await get_setting(db, "system_prompt", SYSTEM_PROMPT)
        finally:
            await db.close()
        await message.answer(
            f"Текущий системный промпт:\n\n{current}",
        )
        return

    new_prompt = args[1].strip()
    db = await get_db()
    try:
        await set_setting(db, "system_prompt", new_prompt)
    finally:
        await db.close()

    logger.info("System prompt changed by user_id=%s", message.from_user.id)
    await message.answer("Системный промпт обновлён.")


@router.message(Command("resetprompt"))
async def cmd_resetprompt(message: Message) -> None:
    if message.from_user.id != ADMIN_ID:
        await message.answer("Эта команда доступна только администратору.")
        return

    db = await get_db()
    try:
        await delete_setting(db, "system_prompt")
    finally:
        await db.close()

    logger.info("System prompt reset to default by user_id=%s", message.from_user.id)
    await message.answer("Системный промпт сброшен на стандартный.")
