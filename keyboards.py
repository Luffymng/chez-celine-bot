import calendar
from datetime import date, datetime, time as dt_time

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

import config

MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🍽 Забронировать столик", callback_data="book")],
        [InlineKeyboardButton(text="📋 Мои брони", callback_data="mine")],
        [InlineKeyboardButton(text="📖 Меню", callback_data="menu")],
        [InlineKeyboardButton(text="ℹ️ О нас", callback_data="about")],
        [InlineKeyboardButton(text="🕐 Часы работы", callback_data="hours")],
        [InlineKeyboardButton(text="📞 Контакты", callback_data="contacts")],
    ]
    if config.INSTAGRAM and config.INSTAGRAM.startswith(("http://", "https://")):
        rows.append([InlineKeyboardButton(text="📷 Instagram", url=config.INSTAGRAM)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ В меню", callback_data="main")]]
    )


def build_calendar(
    year: int,
    month: int,
    prefix: str = "cal",
    cancel_cb: str = "book:cancel",
) -> InlineKeyboardMarkup:
    today = date.today()
    rows = [
        [InlineKeyboardButton(text=f"📅 {MONTHS_RU[month - 1]} {year}", callback_data="cal:ignore")],
        [
            InlineKeyboardButton(text=w, callback_data="cal:ignore")
            for w in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
        ],
    ]
    for week in calendar.monthcalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="cal:ignore"))
                continue
            d = date(year, month, day)
            if d < today:
                row.append(InlineKeyboardButton(text="•", callback_data="cal:ignore"))
            else:
                row.append(InlineKeyboardButton(text=str(day), callback_data=f"{prefix}:date:{d.isoformat()}"))
        rows.append(row)

    prev = date(year - 1, 12, 1) if month == 1 else date(year, month - 1, 1)
    next_ = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    rows.append(
        [
            InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:nav:{prev.isoformat()}"),
            InlineKeyboardButton(text="Сегодня", callback_data=f"{prefix}:nav:{today.isoformat()}"),
            InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:nav:{next_.isoformat()}"),
        ]
    )
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_time_slots(slots: list[str]) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for label in slots:
        row.append(InlineKeyboardButton(text=label, callback_data=f"time:{label}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="book:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def restaurant_slots(chosen_date: date) -> list[str]:
    """Все технические слоты ресторана на дату (без учёта занятости столов).

    В выходные открытие раньше (10:00), в будни — 12:00.
    Поддерживает ночные часы (например, 12:00–02:00).
    """
    now = datetime.now()
    if chosen_date.weekday() >= 5:
        open_hour, close_hour = config.WEEKEND_OPEN_HOUR, config.WEEKEND_CLOSE_HOUR
    else:
        open_hour, close_hour = config.OPEN_HOUR, config.CLOSE_HOUR
    slots = []
    if open_hour < close_hour:
        for hour in range(open_hour, close_hour):
            for minute in range(0, 60, config.SLOT_MINUTES):
                slot = dt_time(hour, minute)
                if chosen_date == now.date() and datetime.combine(chosen_date, slot) <= now:
                    continue
                slots.append(f"{hour:02d}:{minute:02d}")
    else:
        for hour in range(open_hour, 24):
            for minute in range(0, 60, config.SLOT_MINUTES):
                slot = dt_time(hour, minute)
                if chosen_date == now.date() and datetime.combine(chosen_date, slot) <= now:
                    continue
                slots.append(f"{hour:02d}:{minute:02d}")
        for hour in range(0, close_hour):
            for minute in range(0, 60, config.SLOT_MINUTES):
                slots.append(f"{hour:02d}:{minute:02d}")
    return slots


def build_guests_kb() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for n in range(1, config.MAX_GUESTS + 1):
        row.append(InlineKeyboardButton(text=f"{n} 👤", callback_data=f"guests:{n}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="book:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_duration_kb() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for minutes in config.DURATION_OPTIONS:
        label = f"{minutes // 60}.5 ч" if minutes % 60 else f"{minutes // 60} ч"
        row.append(InlineKeyboardButton(text=label, callback_data=f"duration:{minutes}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="book:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_comment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Пропустить ➡️", callback_data="comment:skip")]]
    )


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поделиться номером", request_contact=True)],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="book:confirm")],
            [InlineKeyboardButton(text="✏️ Изменить", callback_data="book:edit")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="book:cancel")],
        ]
    )


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Неподтверждённые", callback_data="adm:list:pending")],
            [InlineKeyboardButton(text="📋 Сегодня", callback_data="adm:list:today")],
            [InlineKeyboardButton(text="🗓 Завтра", callback_data="adm:list:tomorrow")],
            [InlineKeyboardButton(text="📅 Предстоящие", callback_data="adm:list:upcoming")],
            [InlineKeyboardButton(text="📊 Занятость", callback_data="adm:occupancy")],
            [InlineKeyboardButton(text="🪑 Столы", callback_data="adm:tables")],
            [InlineKeyboardButton(text="📤 Экспорт", callback_data="adm:export")],
            [InlineKeyboardButton(text="🏠 В меню гостя", callback_data="main")],
        ]
    )


def admin_export_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📤 Все брони", callback_data="adm:export:all"),
                InlineKeyboardButton(text="📤 Предстоящие", callback_data="adm:export:upcoming"),
            ],
            [InlineKeyboardButton(text="↩️ В админ-меню", callback_data="adm:menu")],
        ]
    )


def admin_occupancy_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Другая дата", callback_data="adm:occupancy")],
            [InlineKeyboardButton(text="↩️ В админ-меню", callback_data="adm:menu")],
        ]
    )


def user_booking_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить бронь", callback_data=f"mine:cancel:{booking_id}")],
            [InlineKeyboardButton(text="↩️ К моим броням", callback_data="mine")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="main")],
        ]
    )


def user_cancel_confirm_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, отменить", callback_data=f"mine:cancel_yes:{booking_id}"),
                InlineKeyboardButton(text="↩️ Нет", callback_data="mine"),
            ]
        ]
    )


def build_admin_tables_kb(count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="−", callback_data="adm:tables:dec"),
                InlineKeyboardButton(text=f"🪑 {count} столов", callback_data="adm:tables:ignore"),
                InlineKeyboardButton(text="+", callback_data="adm:tables:inc"),
            ],
            [InlineKeyboardButton(text="↩️ В админ-меню", callback_data="adm:menu")],
        ]
    )


def admin_booking_kb(b: dict) -> InlineKeyboardMarkup:
    rows = []
    if b["status"] == "pending":
        rows.append(
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm:confirm:{b['id']}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm:cancel:{b['id']}"),
            ]
        )
    elif b["status"] == "confirmed":
        rows.append([InlineKeyboardButton(text="❌ Отменить бронь", callback_data=f"adm:cancel:{b['id']}")])
    rows.append([InlineKeyboardButton(text="↩️ В админ-меню", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
