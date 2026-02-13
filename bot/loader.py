from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.handlers import register_all_handlers
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.middlewares.crisis_check import CrisisCheckMiddleware


def create_bot() -> Bot:
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=None),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Register middlewares on message updates
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(CrisisCheckMiddleware())

    # Register all handlers
    register_all_handlers(dp)

    return dp
