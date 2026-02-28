from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from bot.utils.constants import ADMIN_ID

_DENY_MSG = "Эта команда доступна только администратору."


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if user is None or user.id != ADMIN_ID:
            if isinstance(event, CallbackQuery):
                await event.answer("Только для администратора.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer(_DENY_MSG)
            return False
        return True
