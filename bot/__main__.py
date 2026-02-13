import asyncio
import logging

from aiogram.types import BotCommand

from bot.db.engine import init_db
from bot.loader import create_bot, create_dispatcher
from bot.services.llm import close_session


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    logger.info("Initializing database...")
    await init_db()

    bot = create_bot()
    dp = create_dispatcher()

    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Начать диалог"),
            BotCommand(command="help", description="Список команд"),
            BotCommand(command="mood", description="Записать настроение"),
            BotCommand(command="diary", description="Дневник за неделю"),
            BotCommand(command="breathe", description="Дыхательная техника"),
            BotCommand(command="ground", description="Техника заземления"),
            BotCommand(command="reset", description="Очистить историю"),
        ])
        logger.info("Bot commands menu set.")
    except Exception:
        logger.warning("Failed to set bot commands menu, continuing anyway.", exc_info=True)

    logger.info("Starting FreePsy bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await close_session()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
