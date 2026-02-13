from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.utils.prompts import BREATHE_TECHNIQUE, GROUND_TECHNIQUE

router = Router()


@router.message(Command("breathe"))
async def cmd_breathe(message: Message) -> None:
    await message.answer(BREATHE_TECHNIQUE, parse_mode="HTML")


@router.message(Command("ground"))
async def cmd_ground(message: Message) -> None:
    await message.answer(GROUND_TECHNIQUE, parse_mode="HTML")
