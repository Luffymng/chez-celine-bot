import config
import database as db
import keyboards as kb
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from utils import booking_text, edit_or_send

router = Router()

EMPTY = (
    "📋 <b>Ваши брони</b>\n\n"
    "У вас пока нет активных броней. "
    "Забронируйте столик через главное меню 🍽"
)


@router.callback_query(F.data == "mine")
async def my_bookings(event: CallbackQuery, state: FSMContext):
    await state.clear()
    bookings = await db.list_user_bookings(event.from_user.id)
    if not bookings:
        await edit_or_send(event, EMPTY, kb.main_menu_kb())
        return

    text = "📋 <b>Ваши брони</b>\n\nВыберите, чтобы увидеть детали или отменить:"
    await edit_or_send(event, text, None)

    for b in bookings:
        await event.message.answer(booking_text(b), reply_markup=kb.user_booking_kb(b["id"]))


@router.callback_query(F.data.startswith("mine:cancel:"))
async def ask_cancel(event: CallbackQuery, state: FSMContext):
    await state.clear()
    booking_id = int(event.data.removeprefix("mine:cancel:"))
    booking = await db.get_booking(booking_id)
    if not booking or booking["user_id"] != event.from_user.id:
        await event.answer("Бронь не найдена")
        return
    await edit_or_send(
        event,
        "❓ <b>Отменить бронь?</b>\n\n" + booking_text(booking),
        kb.user_cancel_confirm_kb(booking_id),
    )


@router.callback_query(F.data.startswith("mine:cancel_yes:"))
async def do_cancel(event: CallbackQuery, state: FSMContext, bot):
    await state.clear()
    booking_id = int(event.data.removeprefix("mine:cancel_yes:"))
    booking = await db.get_booking(booking_id)
    if not booking or booking["user_id"] != event.from_user.id:
        await event.answer("Бронь не найдена")
        return
    if booking["status"] == "cancelled":
        await event.answer("Эта бронь уже отменена")
        return

    await db.set_status(booking_id, "cancelled")
    await edit_or_send(
        event,
        "🗑 <b>Бронь отменена.</b>\n\n" + booking_text(booking) + "\n\nЖдём вас в другой раз!",
        kb.main_menu_kb(),
    )

    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "🗑 <b>Гость отменил бронь.</b>\n\n" + booking_text(booking),
            )
        except Exception:
            import logging
            logging.exception("Не удалось уведомить админа %s", admin_id)
