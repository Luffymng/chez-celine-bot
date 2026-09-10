from datetime import date as date_cls

import config
import kinds
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
import keyboards as kb
from handlers.start import show_main_menu
from states import BookingState
from utils import booking_short, edit_or_send, format_date, format_duration, notify_admins

router = Router()

# ─── Утилиты ────────────────────────────────────────────────────────

def _cfg():
    return kinds.get_kind(config.BOT_TYPE)

def _steps():
    return _cfg()["steps"]

STEP_KEY = {
    "date": "date", "guests": "guests", "duration": "duration",
    "service": "service", "master": "master", "time": "time",
    "name": "name", "phone": "phone", "comment": "comment",
}


def _first_unfilled_token(data: dict) -> str | None:
    for token in _steps():
        if token == "master" and not config.MASTERS:
            continue
        if token == "service" and not config.SERVICES:
            continue
        if token not in data:
            return token
    return None


def _step_label(token: str, idx: int, total: int) -> str:
    kind = _cfg()
    master_l = kind.get("master_label") or "мастер"
    labels = {
        "date": "выберите дату",
        "guests": "сколько гостей будет за столом?",
        "duration": "сколько времени планируете у нас провести?",
        "service": f"выберите услугу",
        "master": f"выберите {master_l}",
        "time": "выберите время",
        "name": "как к вам обращаться?",
        "phone": "поделитесь номером телефона",
        "comment": "оставьте комментарий (необязательно)",
    }
    emoji = {"date": "📅", "guests": "👥", "duration": "⏳", "service": "💈", "master": "👤",
             "time": "🕐", "name": "👤", "phone": "📞", "comment": "💬"}.get(token, "")
    return f"{emoji} <b>Шаг {idx} из {total}</b> — {labels.get(token, token)}:"


def is_small_group(guests: int) -> bool:
    return guests <= config.TABLE_CAPACITY


# ─── Шаги: спрос ────────────────────────────────────────────────────

async def ask_date(event, state: FSMContext):
    await state.set_state(BookingState.choosing_date)
    today = date_cls.today()
    total = len(_steps())
    idx = _steps().index("date") + 1
    await edit_or_send(event, _step_label("date", idx, total), kb.build_calendar(today.year, today.month))


async def ask_guests(event, state: FSMContext):
    await state.set_state(BookingState.choosing_guests)
    total = len(_steps())
    idx = _steps().index("guests") + 1
    await edit_or_send(event, _step_label("guests", idx, total), kb.build_guests_kb())


async def ask_duration(event, state: FSMContext):
    await state.set_state(BookingState.choosing_duration)
    total = len(_steps())
    idx = _steps().index("duration") + 1
    await edit_or_send(event, _step_label("duration", idx, total), kb.build_duration_kb())


async def ask_service(event, state: FSMContext):
    await state.set_state(BookingState.choosing_service)
    total = len(_steps())
    idx = _steps().index("service") + 1
    if not config.SERVICES:
        await edit_or_send(event,
            "⚠ В конструкторе пока нет услуг.\nДобавьте их в раздел «Услуги» в настройках бота.",
            kb.main_menu_kb())
        await state.clear()
        return
    await edit_or_send(event, _step_label("service", idx, total), kb.build_services_kb())


async def ask_master(event, state: FSMContext):
    await state.set_state(BookingState.choosing_master)
    total = len(_steps())
    idx = _steps().index("master") + 1
    if not config.MASTERS:
        await edit_or_send(event,
            "⚠ В конструкторе пока нет мастеров.\nДобавьте их в раздел «Мастера» в настройках бота.",
            kb.main_menu_kb())
        await state.clear()
        return
    await edit_or_send(event, _step_label("master", idx, total), kb.build_masters_kb())


async def _slots_for_date(iso: str) -> list[str]:
    return kb.restaurant_slots(date_cls.fromisoformat(iso))


async def _master_available_slots(iso: str, master: str) -> list[str]:
    all_slots = await _slots_for_date(iso)
    available = []
    for slot in all_slots:
        if await db.free_master_slots(iso, slot, master) > 0:
            available.append(slot)
    return available


async def ask_time(event, state: FSMContext):
    data = await state.get_data()
    iso = data["date"]
    total = len(_steps())
    idx = _steps().index("time") + 1
    kind = _cfg()
    if kind.get("masters") and config.MASTERS and data.get("master"):
        master = config.MASTERS[int(data["master"])] if data["master"].isdigit() else data["master"]
        available = await _master_available_slots(iso, master)
        fallback_msg = f"😔 У мастера {master} нет свободных окон на эту дату."
    elif kind.get("tables") and is_small_group(data.get("guests", 1)):
        all_slots = await _slots_for_date(iso)
        available = [s for s in all_slots if await db.free_tables(iso, s) > 0]
        fallback_msg = "😔 К сожалению, на эту дату свободных столиков нет."
    else:
        available = await _slots_for_date(iso)
        fallback_msg = "😔 На эту дату слотов нет."

    if not available:
        await state.set_state(BookingState.choosing_date)
        today = date_cls.today()
        await edit_or_send(event, f"{fallback_msg}\nВыберите другую дату:", kb.build_calendar(today.year, today.month))
        return

    await state.set_state(BookingState.choosing_time)
    await edit_or_send(event, _step_label("time", idx, total), kb.build_time_slots(available))


async def ask_name(event, state: FSMContext):
    await state.set_state(BookingState.entering_name)
    total = len(_steps())
    idx = _steps().index("name") + 1
    await edit_or_send(event, _step_label("name", idx, total) + "\n\n<i>Напишите имя в ответном сообщении.</i>")
    qid = getattr(event, "message_id", None) or getattr(getattr(event, "message", None), "message_id", None)
    qchat = getattr(event, "chat", None) or getattr(getattr(event, "message", None), "chat", None)
    if qid and qchat is not None:
        await state.update_data(qid=qid, qchat=qchat.id)


async def ask_phone(event, state: FSMContext):
    await state.set_state(BookingState.entering_phone)
    total = len(_steps())
    idx = _steps().index("phone") + 1
    text = (
        _step_label("phone", idx, total)
        + "\n\n<i>Нажмите кнопку ниже или введите номер вручную, например: +375 29 123-45-67</i>"
    )
    await edit_or_send(event, text)
    msg = getattr(event, "message", None) or event
    if isinstance(msg, Message):
        kb_msg = await msg.answer("👇 Нажмите кнопку ниже:", reply_markup=kb.phone_kb())
        await state.update_data(phone_kb_id=kb_msg.message_id)


async def ask_comment(event, state: FSMContext):
    await state.set_state(BookingState.entering_comment)
    total = len(_steps())
    idx = _steps().index("comment") + 1
    text = _step_label("comment", idx, total) + "\n\n<i>Например: детское кресло, юбилей, столик у окна…</i>"
    await edit_or_send(event, text, kb.skip_comment_kb())


async def advance(event, state: FSMContext):
    data = await state.get_data()
    token = _first_unfilled_token(data)
    if token is None:
        await show_confirm(event, state)
        return
    await {"date": ask_date, "guests": ask_guests, "duration": ask_duration,
           "service": ask_service, "master": ask_master, "time": ask_time,
           "name": ask_name, "phone": ask_phone, "comment": ask_comment,
    }[token](event, state)


# ─── Бронирование ────────────────────────────────────────────────────

async def edit_question(event, state: FSMContext, text: str, kb_obj=None):
    data = await state.get_data()
    qid = data.get("qid")
    qchat = data.get("qchat")
    bot = getattr(event, "bot", None) or getattr(getattr(event, "message", None), "bot", None)
    if qid and qchat and bot is not None:
        try:
            await bot.edit_message_text(chat_id=qchat, message_id=qid, text=text, reply_markup=kb_obj)
            return
        except TelegramBadRequest:
            pass
    await edit_or_send(event, text, kb_obj)


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


@router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext):
    await state.clear()
    await advance(message, state)


@router.callback_query(F.data == "book")
async def cb_book(event: CallbackQuery, state: FSMContext):
    await state.clear()
    await advance(event, state)


@router.callback_query(F.data.startswith("cal:"))
async def calendar_handler(event: CallbackQuery, state: FSMContext):
    data = event.data
    if data.startswith("cal:date:"):
        iso = data.removeprefix("cal:date:")
        await state.update_data(date=iso)
        await advance(event, state)
    elif data.startswith("cal:nav:"):
        iso = data.removeprefix("cal:nav:")
        d = date_cls.fromisoformat(iso)
        await edit_or_send(event, _step_label("date", _steps().index("date") + 1, len(_steps())),
                           kb.build_calendar(d.year, d.month))
    else:
        await event.answer()


@router.callback_query(F.data.startswith("guests:"))
async def guests_handler(event: CallbackQuery, state: FSMContext):
    guests = int(event.data.removeprefix("guests:"))
    await state.update_data(guests=guests)
    await advance(event, state)


@router.callback_query(F.data.startswith("duration:"))
async def duration_handler(event: CallbackQuery, state: FSMContext):
    minutes = int(event.data.removeprefix("duration:"))
    await state.update_data(duration=minutes)
    await advance(event, state)


@router.callback_query(F.data.startswith("services:"))
async def service_handler(event: CallbackQuery, state: FSMContext):
    idx = int(event.data.removeprefix("services:"))
    svc = config.SERVICES[idx]
    await state.update_data(service={"name": svc["name"], "minutes": svc["minutes"]})
    await advance(event, state)


@router.callback_query(F.data.startswith("master:"))
async def master_handler(event: CallbackQuery, state: FSMContext):
    idx = int(event.data.removeprefix("master:"))
    name = config.MASTERS[idx]
    await state.update_data(master=name)
    await advance(event, state)


@router.callback_query(F.data.startswith("time:"))
async def time_handler(event: CallbackQuery, state: FSMContext):
    await state.update_data(time=event.data.removeprefix("time:"))
    await advance(event, state)


@router.message(BookingState.entering_name)
async def get_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    await safe_delete(message)
    if not 2 <= len(name) <= 60:
        await edit_question(message, state, "😅 Пожалуйста, введите имя (от 2 до 60 символов):")
        return
    await state.update_data(name=name)
    await advance(message, state)


@router.message(BookingState.entering_phone, F.contact)
async def get_phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number or ""
    await safe_delete(message)
    await delete_phone_kb(message, state)
    if not phone:
        await edit_question(message, state, "😅 Не удалось получить номер. Введите его вручную:")
        return
    await state.update_data(phone=phone)
    await advance(message, state)


@router.message(BookingState.entering_phone)
async def get_phone(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    await safe_delete(message)
    await delete_phone_kb(message, state)
    if text.lower() in ("отмена", "cancel"):
        await edit_question(message, state, "🚫 Бронирование отменено.", kb.main_menu_kb())
        await state.clear()
        return
    digits = "".join(ch for ch in text if ch.isdigit())
    if not 7 <= len(digits) <= 15:
        await edit_question(message, state, "😅 Похоже, номер неполный. Введите номер ещё раз:")
        return
    await state.update_data(phone=text)
    await advance(message, state)


@router.callback_query(F.data == "comment:skip")
async def skip_comment(event: CallbackQuery, state: FSMContext):
    await state.update_data(comment=None)
    await show_confirm(event, state)


@router.message(BookingState.entering_comment)
async def get_comment(message: Message, state: FSMContext):
    comment = (message.text or "").strip()
    await safe_delete(message)
    if len(comment) > 500:
        await edit_question(message, state, "😅 Слишком длинный комментарий. Пожалуйста, до 500 символов:")
        return
    await state.update_data(comment=comment or None)
    await show_confirm(message, state)


# ─── Подтверждение ───────────────────────────────────────────────────

async def show_confirm(event, state: FSMContext):
    data = await state.get_data()
    kind = _cfg()
    lines = ["📝 <b>Проверьте запись:</b>\n"]
    lines.append(f"📅 {format_date(data['date'])} в {data['time']}")
    if kind.get("tables"):
        lines.append(f"⏳ На {format_duration(data.get('duration', 120))}")
        lines.append(f"👥 Гостей: {data.get('guests', 1)}")
        lines.append("🪑 Стол: 4-местный" if is_small_group(data.get("guests", 1)) else "🪑 Стол: большой")
    else:
        svc = data.get("service")
        if svc:
            lines.append(f"💈 {svc['name']} ({kinds.fmt_minutes(svc['minutes'])})")
        mst = data.get("master")
        if mst:
            lines.append(f"👤 {mst}")
    lines.append(f"👤 {data['name']}")
    lines.append(f"📞 {data['phone']}")
    if data.get("comment"):
        lines.append(f"💬 {data['comment']}")
    lines.append("\nВсё верно?")
    await state.set_state(BookingState.confirming)
    await edit_question(event, state, "\n".join(lines), kb.confirm_kb())


@router.callback_query(F.data == "book:confirm")
async def confirm_booking(event: CallbackQuery, state: FSMContext, bot):
    data = await state.get_data()
    kind = _cfg()
    service_name = ""
    master_name = ""
    duration = data.get("duration", 120)
    guests = data.get("guests", 1)
    tables_needed = 1 if kind.get("tables") else 0

    if kind.get("services"):
        svc = data.get("service") or {}
        service_name = svc.get("name", "")
        duration = svc.get("minutes", 30)
    if kind.get("masters"):
        master_name = data.get("master") or ""

    if kind.get("tables") and is_small_group(guests) and await db.free_tables(data["date"], data["time"]) < 1:
        await event.answer("😔 Увы, это время только что заняли. Выберите другое")
        await ask_time(event, state)
        return

    if kind.get("masters") and master_name and config.MASTERS:
        if await db.free_master_slots(data["date"], data["time"], master_name) < 1:
            await event.answer("😔 У мастера это время только что заняли. Выберите другое")
            await ask_time(event, state)
            return

    if await db.has_overlap(event.from_user.id, data["date"], data["time"], duration):
        await state.clear()
        await edit_or_send(event,
            "😔 У вас уже есть бронь на это же время.\n\n"
            "Проверить свои брони можно в разделе «📋 Мои брони».", kb.main_menu_kb())
        return

    booking_id = await db.create_booking(
        user_id=event.from_user.id,
        guest_name=data["name"],
        phone=data["phone"],
        date=data["date"],
        time=data["time"],
        guests=guests,
        duration_minutes=duration,
        tables_needed=tables_needed,
        comment=data.get("comment"),
        service_name=service_name,
        master_name=master_name,
    )
    await state.clear()

    if kind.get("tables"):
        desc = f"{guests} чел., {format_duration(duration)}"
    else:
        parts = [service_name] if service_name else []
        if master_name:
            parts.append(master_name)
        desc = ", ".join(parts) or format_duration(duration)

    success = (
        "🎉 <b>Заявка отправлена!</b>\n\n"
        f"Ваша запись №{booking_id}: {format_date(data['date'])} в {data['time']}, {desc}\n\n"
        "Мы свяжемся с вами для подтверждения.\n\n"
        f"Вопросы? Звоните: {config.RESTAURANT_PHONE}"
    )
    await edit_or_send(event, success, kb.main_menu_kb())

    booking = await db.get_booking(booking_id)
    if booking:
        await notify_admins(bot, booking)


@router.callback_query(F.data == "book:edit")
async def edit_booking(event: CallbackQuery, state: FSMContext):
    await state.clear()
    await advance(event, state)


@router.callback_query(F.data == "book:cancel")
async def cancel_booking(event: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main_menu(event)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await show_main_menu(message)
