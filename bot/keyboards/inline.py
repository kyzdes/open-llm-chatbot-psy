from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def mood_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for start in range(1, 11, 5):
        row = [
            InlineKeyboardButton(text=str(i), callback_data=f"mood:{i}")
            for i in range(start, min(start + 5, 11))
        ]
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reset_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, очистить", callback_data="reset:confirm"),
                InlineKeyboardButton(text="Отмена", callback_data="reset:cancel"),
            ]
        ]
    )


def model_select_keyboard(
    models: list[dict], current_model: str, max_shown: int = 20
) -> tuple[InlineKeyboardMarkup, bool]:
    """Build inline keyboard for model selection.

    Returns (keyboard, truncated) where truncated=True if list was cut.
    """
    truncated = len(models) > max_shown
    shown = models[:max_shown]
    rows = []
    for idx, m in enumerate(shown):
        check = "\u2713 " if m["id"] == current_model else ""
        label = f"{check}{m['name']}"
        if len(label) > 60:
            label = label[:57] + "..."
        rows.append([InlineKeyboardButton(text=label, callback_data=f"model:{idx}")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="model:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows), truncated


# ---------------------------------------------------------------------------
# Role / task keyboards
# ---------------------------------------------------------------------------

def role_select_keyboard(current_role_id: str | None = None) -> InlineKeyboardMarkup:
    from bot.services.roles import ROLES

    rows: list[list[InlineKeyboardButton]] = []
    # 2 columns
    row: list[InlineKeyboardButton] = []
    for role in ROLES:
        check = "\u2713 " if role.id == current_role_id else ""
        label = f"{check}{role.emoji} {role.name}"
        row.append(InlineKeyboardButton(text=label, callback_data=f"role:{role.id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    # Bottom buttons
    bottom: list[InlineKeyboardButton] = []
    if current_role_id:
        bottom.append(InlineKeyboardButton(text="\u274c Сбросить роль", callback_data="role:reset"))
    rows.append(bottom) if bottom else None
    return InlineKeyboardMarkup(inline_keyboard=rows)


def task_select_keyboard(role) -> InlineKeyboardMarkup:
    """Build keyboard with tasks for the given Role, plus a free-chat button."""
    rows: list[list[InlineKeyboardButton]] = []
    for task in role.tasks:
        label = f"{task.emoji} {task.name}"
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"task:{role.id}:{task.id}",
        )])
    rows.append([InlineKeyboardButton(text="\U0001f4ac Свободный диалог", callback_data="role:chat")])
    rows.append([InlineKeyboardButton(text="\u2b05 Назад к ролям", callback_data="role:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
