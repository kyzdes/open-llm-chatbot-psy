import html

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.db.engine import get_db
from bot.db.repositories.mood import add_entry, get_entries_range
from bot.keyboards.inline import mood_keyboard
from bot.services.mood_analytics import weekly_summary

router = Router()


class MoodStates(StatesGroup):
    waiting_note = State()


async def _save_mood(user_id: int, score: int, note: str | None) -> None:
    async with get_db() as db:
        await add_entry(db, user_id, score, note)


@router.message(Command("mood"))
async def cmd_mood(message: Message) -> None:
    await message.answer(
        "Как ты себя чувствуешь? Оцени настроение от 1 до 10:",
        reply_markup=mood_keyboard(),
    )


@router.callback_query(F.data.startswith("mood:"))
async def mood_score_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        score = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    if not 1 <= score <= 10:
        await callback.answer("Оценка должна быть от 1 до 10.", show_alert=True)
        return

    await state.update_data(mood_score=score)
    await state.set_state(MoodStates.waiting_note)
    await callback.message.edit_text(
        f"Оценка: <b>{score}/10</b>\n\nХочешь добавить заметку? Напиши текст или отправь /skip",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(MoodStates.waiting_note, Command("cancel"))
async def mood_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Запись настроения отменена.")


@router.message(MoodStates.waiting_note, F.text.startswith("/"))
async def mood_ignore_commands(message: Message, state: FSMContext) -> None:
    """Save mood without note when another command arrives, then clear FSM."""
    data = await state.get_data()
    score = data["mood_score"]
    await _save_mood(message.from_user.id, score, None)
    await state.clear()
    await message.answer(
        f"Настроение <b>{score}/10</b> записано без заметки.",
        parse_mode="HTML",
    )


@router.message(MoodStates.waiting_note)
async def mood_note_received(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    score = data["mood_score"]
    note = None if message.text and message.text.strip() == "/skip" else message.text

    await _save_mood(message.from_user.id, score, note)
    await state.clear()

    note_text = f'\nЗаметка: <i>{html.escape(note)}</i>' if note else ""
    await message.answer(
        f"Записано! Настроение: <b>{score}/10</b>{note_text}",
        parse_mode="HTML",
    )


@router.message(Command("diary"))
async def cmd_diary(message: Message) -> None:
    async with get_db() as db:
        entries = await get_entries_range(db, message.from_user.id, days=7)

    text = weekly_summary(entries)
    await message.answer(text, parse_mode="HTML")
