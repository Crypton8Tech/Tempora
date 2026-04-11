"""Start / main-menu handler."""

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.keyboards import main_menu_kb

router = Router()

WELCOME = (
    "🕰 <b>Добро пожаловать в TemporaShop!</b>\n\n"
    "Элитные часы и аксессуары.\n"
    "Выберите раздел:"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(WELCOME, reply_markup=main_menu_kb())


@router.callback_query(F.data == "main")
async def cb_main(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    # If current message is a photo we can't edit_text — delete & send new
    try:
        await cb.message.edit_text(WELCOME, reply_markup=main_menu_kb())
    except Exception:
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.message.answer(WELCOME, reply_markup=main_menu_kb())


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()
