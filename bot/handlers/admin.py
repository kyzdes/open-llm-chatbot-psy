import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.db.engine import get_db
from bot.db.repositories.settings import set_setting, get_setting, delete_setting
from bot.services.llm import validate_model, fetch_free_models
from bot.keyboards.inline import model_select_keyboard
from bot.filters.admin import IsAdmin
from bot.utils.constants import SETTING_CURRENT_MODEL, SETTING_SYSTEM_PROMPT
from bot.utils.prompts import SYSTEM_PROMPT
from bot.config import settings as app_settings

logger = logging.getLogger(__name__)

router = Router()

# Temporary storage: maps message_id -> model list for that message
_model_lists: dict[int, list[dict]] = {}


@router.message(Command("modelchange"), IsAdmin())
async def cmd_modelchange(message: Message) -> None:
    async with get_db() as db:
        current = await get_setting(db, SETTING_CURRENT_MODEL, app_settings.default_model)

    await message.answer("Загружаю список моделей...")
    models = await fetch_free_models()

    if not models:
        await message.answer(
            f"Не удалось получить список моделей.\n"
            f"Текущая модель: <code>{current}</code>",
            parse_mode="HTML",
        )
        return

    kb = model_select_keyboard(models, current)
    text = f"Текущая модель: <code>{current}</code>\n\nВыбери новую модель:"
    sent = await message.answer(text, reply_markup=kb, parse_mode="HTML")
    _model_lists[sent.message_id] = models


@router.callback_query(F.data.startswith("model:"), IsAdmin())
async def model_chosen(callback: CallbackQuery) -> None:
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

    async with get_db() as db:
        await set_setting(db, SETTING_CURRENT_MODEL, model_id)

    _model_lists.pop(callback.message.message_id, None)

    await callback.message.edit_text(
        f"Модель изменена на: <b>{model_name}</b>\n<code>{model_id}</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("setprompt"), IsAdmin())
async def cmd_setprompt(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        async with get_db() as db:
            current = await get_setting(db, SETTING_SYSTEM_PROMPT, SYSTEM_PROMPT)
        await message.answer(
            f"Текущий системный промпт:\n\n{current}",
        )
        return

    new_prompt = args[1].strip()
    async with get_db() as db:
        await set_setting(db, SETTING_SYSTEM_PROMPT, new_prompt)

    logger.info("System prompt changed by user_id=%s", message.from_user.id)
    await message.answer("Системный промпт обновлён.")


@router.message(Command("resetprompt"), IsAdmin())
async def cmd_resetprompt(message: Message) -> None:
    async with get_db() as db:
        await delete_setting(db, SETTING_SYSTEM_PROMPT)

    logger.info("System prompt reset to default by user_id=%s", message.from_user.id)
    await message.answer("Системный промпт сброшен на стандартный.")
