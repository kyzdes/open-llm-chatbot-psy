from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.db.engine import get_db
from bot.db.repositories.conversation import delete_messages
from bot.keyboards.inline import reset_confirm_keyboard

router = Router()


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    await message.answer(
        "Ты уверен(а), что хочешь очистить всю историю диалога? Это действие нельзя отменить.",
        reply_markup=reset_confirm_keyboard(),
    )


@router.callback_query(F.data == "reset:confirm")
async def reset_confirmed(callback: CallbackQuery) -> None:
    async with get_db() as db:
        deleted = await delete_messages(db, callback.from_user.id)

    await callback.message.edit_text(
        f"История очищена. Удалено сообщений: {deleted}.\nМожем начать сначала 💙"
    )
    await callback.answer()


@router.callback_query(F.data == "reset:cancel")
async def reset_cancelled(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Отменено. История сохранена.")
    await callback.answer()
