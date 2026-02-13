from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.services.crisis import keyword_check


class CrisisCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if event.text:
            matched = keyword_check(event.text)
            data["crisis_keyword"] = matched
        else:
            data["crisis_keyword"] = None
        return await handler(event, data)
