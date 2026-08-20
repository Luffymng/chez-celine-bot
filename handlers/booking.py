from datetime import date as date_cls

import config
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
from handlers.start import show_main_menu
from states import BookingState
from utils import booking_text, edit_or_send, format_date, format_duration, notify_admins

router = Router()


def is_small_group(guests: int) -> bool:
    return guests <= config.TABLE_CAPACITY


async def edit_question(event, state: FSMContext, text: str, kb=None):
    """Редактирует «текущий» вопрос в одном сообщении (если есть qid)."""
    data = await state.get_data()
    qid = data.get("qid")
    qchat = data.get("qchat")
    bot = getattr(event, "bot", None) or getattr(getattr(event, "message", None), "bot", None)
    if qid and qchat and bot is not None:
        try:
            await bot.edit_message_text(chat_id=qchat, message_id=qid, text=text, reply_markup=kb)
            return
        except TelegramBadRequest:
            pass
    await edit_or_send(event, text, kb)


async def safe_delete(message: Message):
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def delete_phone_kb(message: Message, state: FSMContext):
    data = await state.get_data()
    kb_id = data.get("phone_kb_id")
    if not kb_id:
        return
    try:
        await message.bot.delete_message(chat_id=message.chat.id, message_id=kb_id)
    except TelegramBadRequest:
        pass


async def show_time_choice(event, state: FSMContext):
    data = await state.get_data()
    iso = data["date"]
    guests = data["guests"]
    chosen_date = date_cls.fromisoformat(iso)
    slots = kb.restaurant_slots(chosen_date)

    if is_small_group(guests):
        available = []
        for slot in slots:
            if await db.free_tables(iso, slot) > 0:
                available.append(slot)
        if not available:
            await state.set_state(BookingState.choosing_date)
            today = date_cls.today()
            await edit_or_send(
                event,
                f"😔 К сожалению, на эту дату свободных 4-местных столов на {guests} чел. нет. "
                "Выберите другую дату:",
                kb.build_calendar(today.year, today.month),
            )
            return
        await state.set_state(BookingState.choosing_time)
        await edit_or_send(
            event,
            "🕐 <b>Шаг 4 из 7</b> — выберите время:",
            kb.build_time_slots(available),
        )
    else:
        await state.set_state(BookingState.choosing_time)
        await edit_or_send(
            event,
            "🕐 <b>Шаг 4 из 7</b> — выберите время:",
            kb.build_time_slots(slots),
        )


@router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(BookingState.choosing_date)
    today = date_cls.today()
    await edit_or_send(
        message,
        "📅 <b>Шаг 1 из 7</b> — выберите дату:",
        kb.build_calendar(today.year, today.month),
    )


@router.callback_query(F.data == "book")
async def cb_book(event: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(BookingState.choosing_date)
    today = date_cls.today()
    await edit_or_send(
        event,
        "📅 <b>Шаг 1 из 7</b> — выберите дату:",
        kb.build_calendar(today.year, today.month),
    )


@router.callback_query(F.data.startswith("cal:"))
async def calendar_handler(event: CallbackQuery, state: FSMContext):
    data = event.data

    if data.startswith("cal:date:"):
        iso = data.removeprefix("cal:date:")
        await state.update_data(date=iso)
        await state.set_state(BookingState.choosing_guests)
        await edit_or_send(
            event,
            "👥 <b>Шаг 2 из 7</b> — сколько гостей будет за столом?",
            kb.build_guests_kb(),
        )
    elif data.startswith("cal:nav:"):
        iso = data.removeprefix("cal:nav:")
        d = date_cls.fromisoformat(iso)
        await edit_or_send(
            event,
            "📅 <b>Шаг 1 из 7</b> — выберите дату:",
            kb.build_calendar(d.year, d.month),
        )
    else:
        await event.answer()


@router.callback_query(F.data.startswith("guests:"))
async def guests_handler(event: CallbackQuery, state: FSMContext):
    guests = int(event.data.removeprefix("guests:"))
    await state.update_data(guests=guests)
    await state.set_state(BookingState.choosing_duration)
    await edit_or_send(
        event,
        "⏳ <b>Шаг 3 из 7</b> — сколько времени планируете у нас провести?",
        kb.build_duration_kb(),
    )


@router.callback_query(F.data.startswith("duration:"))
async def duration_handler(event: CallbackQuery, state: FSMContext):
    minutes = int(event.data.removeprefix("duration:"))
    await state.update_data(duration=minutes)
    await show_time_choice(event, state)


@router.callback_query(F.data.startswith("time:"))
async def time_handler(event: CallbackQuery, state: FSMContext):
    await state.update_data(time=event.data.removeprefix("time:"))
    await state.set_state(BookingState.entering_name)
    await edit_or_send(
        event,
        "👤 <b>Шаг 5 из 7</b> — как к вам обращаться?\n\n"
        "<i>Напишите имя в ответном сообщении.</i>",
    )
    await state.update_data(qid=event.message.message_id, qchat=event.message.chat.id)


@router.message(BookingState.entering_name)
async def get_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    await safe_delete(message)
    if not 2 <= len(name) <= 60:
        await edit_question(
            message, state, "😅 Пожалуйста, введите имя (от 2 до 60 символов):"
        )
        return
    await state.update_data(name=name)
    await state.set_state(BookingState.entering_phone)
    await edit_question(
        message,
        state,
        "📞 <b>Шаг 6 из 7</b> — поделитесь номером телефона:\n\n"
        "<i>Нажмите кнопку ниже или введите номер вручную, "
        "например: +375 29 123-45-67</i>",
    )
    kb_msg = await message.answer("👇 Нажмите кнопку ниже:", reply_markup=kb.phone_kb())
    await state.update_data(phone_kb_id=kb_msg.message_id)


@router.message(BookingState.entering_phone, F.contact)
async def get_phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number or ""
    await safe_delete(message)
    await delete_phone_kb(message, state)
    if not phone:
        await edit_question(
            message, state, "😅 Не удалось получить номер. Введите его вручную:"
        )
        return
    await state.update_data(phone=phone)
    await state.set_state(BookingState.entering_comment)
    await edit_question(
        message,
        state,
        "💬 <b>Шаг 7 из 7</b> — оставьте комментарий (необязательно):\n\n"
        "<i>Например: детское кресло, юбилей, столик у окна…</i>",
        kb.skip_comment_kb(),
    )


@router.message(BookingState.entering_phone)
async def get_phone(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    await safe_delete(message)
    await delete_phone_kb(message, state)
    if text.lower() in ("отмена", "cancel"):
        await edit_question(
            message, state, "🚫 Бронирование отменено.", kb.main_menu_kb()
        )
        await state.clear()
        return
    digits = "".join(ch for ch in text if ch.isdigit())
    if not 7 <= len(digits) <= 15:
        await edit_question(
            message,
            state,
            "😅 Похоже, номер неполный. Введите номер ещё раз:",
        )
        return
    await state.update_data(phone=text)
    await state.set_state(BookingState.entering_comment)
    await edit_question(
        message,
        state,
        "💬 <b>Шаг 7 из 7</b> — оставьте комментарий (необязательно):\n\n"
        "<i>Например: детское кресло, юбилей, столик у окна…</i>",
        kb.skip_comment_kb(),
    )


@router.callback_query(F.data == "comment:skip")
async def skip_comment(event: CallbackQuery, state: FSMContext):
    await state.update_data(comment=None)
    await show_confirm(event, state)


@router.message(BookingState.entering_comment)
async def get_comment(message: Message, state: FSMContext):
    comment = (message.text or "").strip()
    await safe_delete(message)
    if len(comment) > 500:
        await edit_question(
            message,
            state,
            "😅 Слишком длинный комментарий. Пожалуйста, до 500 символов:",
        )
        return
    await state.update_data(comment=comment or None)
    await show_confirm(message, state)


async def show_confirm(event, state: FSMContext):
    data = await state.get_data()
    table_label = (
        "🪑 Стол: 4-местный"
        if is_small_group(data["guests"])
        else "🪑 Стол: большой (на 5–8 чел.)"
    )
    text = (
        "📝 <b>Проверьте бронь:</b>\n\n"
        f"📅 {format_date(data['date'])} в {data['time']}\n"
        f"⏳ На {format_duration(data['duration'])}\n"
        f"👥 Гостей: {data['guests']}\n"
        f"{table_label}\n"
        f"👤 {data['name']}\n"
        f"📞 {data['phone']}"
    )
    if data.get("comment"):
        text += f"\n💬 {data['comment']}"
    text += "\n\nВсё верно?"
    await state.set_state(BookingState.confirming)
    await edit_question(event, state, text, kb.confirm_kb())


@router.callback_query(F.data == "book:confirm")
async def confirm_booking(event: CallbackQuery, state: FSMContext, bot):
    data = await state.get_data()

    if is_small_group(data["guests"]) and await db.free_tables(data["date"], data["time"]) < 1:
        await event.answer("😔 Увы, это время только что заняли. Выберите другое")
        await show_time_choice(event, state)
        return

    if await db.has_overlap(event.from_user.id, data["date"], data["time"], data["duration"]):
        await state.clear()
        await edit_or_send(
            event,
            "😔 У вас уже есть бронь на это же время.\n\n"
            "Проверить свои брони можно в разделе «📋 Мои брони».",
            kb.main_menu_kb(),
        )
        return

    booking_id = await db.create_booking(
        user_id=event.from_user.id,
        guest_name=data["name"],
        phone=data["phone"],
        date=data["date"],
        time=data["time"],
        guests=data["guests"],
        duration_minutes=data["duration"],
        tables_needed=1,
        comment=data.get("comment"),
    )
    await state.clear()
    success = (
        "🎉 <b>Заявка отправлена!</b>\n\n"
        f"Ваша бронь №{booking_id}: {format_date(data['date'])} в {data['time']}, "
        f"на {format_duration(data['duration'])}, {data['guests']} чел.\n\n"
        "Мы свяжемся с вами для подтверждения.\n\n"
        f"Вопросы? Звоните: {config.RESTAURANT_PHONE}"
    )
    await edit_or_send(event, success, kb.main_menu_kb())

    booking = await db.get_booking(booking_id)
    if booking:
        await notify_admins(bot, booking)


@router.callback_query(F.data == "book:edit")
async def edit_booking(event: CallbackQuery, state: FSMContext):
    await state.set_state(BookingState.choosing_date)
    today = date_cls.today()
    await edit_or_send(
        event,
        "📅 <b>Шаг 1 из 7</b> — выберите дату:",
        kb.build_calendar(today.year, today.month),
    )


@router.callback_query(F.data == "book:cancel")
async def cancel_booking(event: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main_menu(event)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await show_main_menu(message)
