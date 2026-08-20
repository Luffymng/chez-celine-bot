from datetime import datetime
from html import escape

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

import config

MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

STATUS_TEXT = {
    "pending": "⏳ Ожидает подтверждения",
    "confirmed": "✅ Подтверждена",
    "cancelled": "❌ Отменена",
}


def format_date(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{int(day)} {MONTHS_RU[int(month) - 1]} {year} г."


def format_duration(minutes: int) -> str:
    if minutes % 60:
        return f"{minutes // 60}.5 ч"
    return f"{minutes // 60} ч"


def tables_needed(guests: int) -> int:
    capacity = config.TABLE_CAPACITY
    return max(1, (guests + capacity - 1) // capacity)


def table_label(guests: int) -> str:
    return "🪑 Стол: 4-местный" if guests <= config.TABLE_CAPACITY else "🪑 Стол: большой (на 5–8 чел.)"


def booking_text(b: dict) -> str:
    lines = [
        f"🔖 <b>Бронь №{b['id']}</b>",
        f"📅 {format_date(b['date'])} в {b['time']}",
        f"⏳ На {format_duration(b.get('duration_minutes') or 120)}",
        f"👥 Гостей: {b['guests']}",
        table_label(b['guests']),
        f"👤 {escape(b['guest_name'])}",
        f"📞 {escape(b['phone'])}",
    ]
    if b.get("comment"):
        lines.append(f"💬 {escape(b['comment'])}")
    lines.append(f"Статус: {STATUS_TEXT.get(b['status'], b['status'])}")
    return "\n".join(lines)


async def edit_or_send(event, text: str, kb=None):
    """Заменяет текст сообщения, либо шлёт новое, если редактировать нельзя."""
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            await event.message.answer(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


async def notify_admins(bot, booking: dict):
    from keyboards import admin_booking_kb

    text = "🆕 <b>Новая заявка на бронь!</b>\n\n" + booking_text(booking)
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=admin_booking_kb(booking))
        except Exception:
            import logging
            logging.exception("Не удалось уведомить администратора %s", admin_id)
