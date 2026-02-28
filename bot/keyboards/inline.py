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
    models: list[dict], current_model: str
) -> InlineKeyboardMarkup:
    """Build inline keyboard for model selection."""
    rows = []
    for idx, m in enumerate(models):
        check = "\u2713 " if m["id"] == current_model else ""
        label = f"{check}{m['name']}"
        if len(label) > 60:
            label = label[:57] + "..."
        rows.append([InlineKeyboardButton(text=label, callback_data=f"model:{idx}")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="model:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
