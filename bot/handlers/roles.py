"""Handler for /role command — business role & task selection."""

import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.db.engine import get_db
from bot.db.repositories.conversation import delete_messages
from bot.db.repositories.settings import get_setting, set_setting, delete_setting
from bot.keyboards.inline import role_select_keyboard, task_select_keyboard
from bot.services.roles import ROLES, get_role, get_task, OutputFormat

logger = logging.getLogger(__name__)

router = Router()

# Helpers for per-user role/task keys
_K_ROLE = "user:{}:role"
_K_TASK = "user:{}:task"


async def get_user_role_task(db, user_id: int) -> tuple[str | None, str | None]:
    """Return (role_id, task_id) for a user."""
    role_id = await get_setting(db, _K_ROLE.format(user_id))
    task_id = await get_setting(db, _K_TASK.format(user_id))
    return role_id, task_id


async def _set_user_role(db, user_id: int, role_id: str | None) -> None:
    if role_id is None:
        await delete_setting(db, _K_ROLE.format(user_id))
    else:
        await set_setting(db, _K_ROLE.format(user_id), role_id)


async def _set_user_task(db, user_id: int, task_id: str | None) -> None:
    if task_id is None:
        await delete_setting(db, _K_TASK.format(user_id))
    else:
        await set_setting(db, _K_TASK.format(user_id), task_id)


def _format_label(fmt: OutputFormat) -> str:
    labels = {
        OutputFormat.PDF: "PDF",
        OutputFormat.EXCEL: "Excel",
        OutputFormat.MARKDOWN: "Markdown",
        OutputFormat.TEXT: "текст",
    }
    return labels.get(fmt, "текст")


# -----------------------------------------------------------------------
# /role command
# -----------------------------------------------------------------------

@router.message(Command("role"))
async def cmd_role(message: Message) -> None:
    db = await get_db()
    try:
        role_id, task_id = await get_user_role_task(db, message.from_user.id)
    finally:
        await db.close()

    status = ""
    if role_id:
        role = get_role(role_id)
        if role:
            status = f"\nСейчас: {role.emoji} <b>{role.name}</b>"
            if task_id:
                task = get_task(task_id)
                if task:
                    status += f" \u2192 {task.emoji} {task.name}"

    await message.answer(
        f"Выбери бизнес-роль:{status}",
        reply_markup=role_select_keyboard(role_id),
        parse_mode="HTML",
    )


# -----------------------------------------------------------------------
# Callbacks: role:*, task:*
# -----------------------------------------------------------------------

@router.callback_query(F.data.startswith("role:"))
async def role_callback(callback: CallbackQuery) -> None:
    data = callback.data[5:]  # after "role:"
    user_id = callback.from_user.id

    # Back to role list
    if data == "back":
        db = await get_db()
        try:
            role_id, _ = await get_user_role_task(db, user_id)
        finally:
            await db.close()
        await callback.message.edit_text(
            "Выбери бизнес-роль:",
            reply_markup=role_select_keyboard(role_id),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Reset role
    if data == "reset":
        db = await get_db()
        try:
            await _set_user_role(db, user_id, None)
            await _set_user_task(db, user_id, None)
            await delete_messages(db, user_id)
        finally:
            await db.close()
        await callback.message.edit_text(
            "Роль сброшена. История очищена.\nТеперь я снова FreePsy-психолог \U0001f499"
        )
        await callback.answer()
        return

    # Free chat within role — just clear task
    if data == "chat":
        db = await get_db()
        try:
            role_id, _ = await get_user_role_task(db, user_id)
            await _set_user_task(db, user_id, None)
            await delete_messages(db, user_id)
        finally:
            await db.close()
        role = get_role(role_id) if role_id else None
        if role:
            await callback.message.edit_text(
                f"{role.emoji} <b>{role.name}</b> — свободный диалог\n\n"
                f"Задавай любые вопросы по теме. Чтобы сменить роль: /role",
                parse_mode="HTML",
            )
        await callback.answer()
        return

    # Selected a role — show tasks
    role = get_role(data)
    if not role:
        await callback.answer("Роль не найдена.", show_alert=True)
        return

    db = await get_db()
    try:
        await _set_user_role(db, user_id, role.id)
        await _set_user_task(db, user_id, None)
        await delete_messages(db, user_id)
    finally:
        await db.close()

    await callback.message.edit_text(
        f"{role.emoji} <b>{role.name}</b>\n{role.description}\n\nВыбери задачу:",
        reply_markup=task_select_keyboard(role),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("task:"))
async def task_callback(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректный формат.", show_alert=True)
        return

    _, role_id, task_id = parts
    user_id = callback.from_user.id

    role = get_role(role_id)
    task = get_task(task_id)
    if not role or not task:
        await callback.answer("Задача не найдена.", show_alert=True)
        return

    db = await get_db()
    try:
        await _set_user_role(db, user_id, role.id)
        await _set_user_task(db, user_id, task.id)
        await delete_messages(db, user_id)
    finally:
        await db.close()

    fmt_label = _format_label(task.output_format)

    await callback.message.edit_text(
        f"{role.emoji} <b>{role.name}</b> \u2192 {task.emoji} <b>{task.name}</b>\n\n"
        f"{task.description}.\n\n"
        f"Формат: <b>{fmt_label}</b>\n\n"
        "Опиши свой контекст — продукт, бизнес, задачу — и я подготовлю результат.",
        parse_mode="HTML",
    )
    await callback.answer()
