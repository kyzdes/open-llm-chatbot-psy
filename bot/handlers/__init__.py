from aiogram import Dispatcher

from bot.handlers import start, techniques, mood, admin, reset, therapy


def register_all_handlers(dp: Dispatcher) -> None:
    dp.include_router(start.router)
    dp.include_router(techniques.router)
    dp.include_router(mood.router)
    dp.include_router(admin.router)
    dp.include_router(reset.router)
    # therapy MUST be last — it's a catch-all for text messages
    dp.include_router(therapy.router)
