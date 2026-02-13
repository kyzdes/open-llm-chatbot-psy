from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from bot.db.engine import get_db
from bot.db.repositories.user import get_or_create_user
from bot.utils.prompts import WELCOME_MESSAGE, HELP_MESSAGE

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    db = await get_db()
    try:
        await get_or_create_user(
            db,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            language_code=message.from_user.language_code,
        )
    finally:
        await db.close()
    await message.answer(WELCOME_MESSAGE, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_MESSAGE, parse_mode="HTML")
