import csv
import io
from datetime import date, timedelta

import config
import database as db
import keyboards as kb
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from utils import STATUS_TEXT, booking_text, edit_or_send, format_date

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("🚫 У вас нет доступа к панели администратора.")
        return
    await message.answer(
        "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
        reply_markup=kb.admin_menu_kb(),
    )


@router.callback_query(F.data == "adm:menu")
async def adm_menu(event: CallbackQuery):
    if not is_admin(event.from_user.id):
        await event.answer("🚫 Нет доступа")
        return
    await edit_or_send(
        event,
        "🛠 <b>Панель администратора</b>\n\nВыберите раздел:",
        kb.admin_menu_kb(),
    )


@router.callback_query(F.data.startswith("adm:list:"))
async def adm_list(event: CallbackQuery):
    if not is_admin(event.from_user.id):
        await event.answer("🚫 Нет доступа")
        return
    kind = event.data.removeprefix("adm:list:")
    if kind == "pending":
        bookings = await db.list_bookings(status="pending")
        title = "🔄 <b>Неподтверждённые брони</b>"
    elif kind == "today":
        bookings = await db.list_bookings(on_date=date.today().isoformat())
        title = "📋 <b>Брони на сегодня</b>"
    elif kind == "tomorrow":
        bookings = await db.list_bookings(on_date=(date.today() + timedelta(days=1)).isoformat())
        title = "🗓 <b>Брони на завтра</b>"
    else:
        bookings = await db.list_bookings(upcoming=True)
        title = "📅 <b>Предстоящие брони</b>"

    if not bookings:
        await edit_or_send(event, "📭 Список пуст.", kb.admin_menu_kb())
        return

    await edit_or_send(event, f"{title}\n\nПоказано {len(bookings[:10])} из {len(bookings)}:", None)
    for b in bookings[:10]:
        await event.message.answer(booking_text(b), reply_markup=kb.admin_booking_kb(b))


@router.callback_query(F.data.startswith("adm:tables"))
async def adm_tables(event: CallbackQuery):
    if not is_admin(event.from_user.id):
        await event.answer("🚫 Нет доступа")
        return
    if event.data == "adm:tables:ignore":
        await event.answer()
        return

    count = await db.get_table_count()
    if event.data == "adm:tables:inc":
        await db.set_table_count(count + 1)
    elif event.data == "adm:tables:dec":
        await db.set_table_count(count - 1)

    count = await db.get_table_count()
    await edit_or_send(
        event,
        f"🪑 <b>Столы</b>\n\n4-местные столы: <b>{count}</b>\n"
        f"({config.MIN_TABLES}–{config.MAX_TABLES})\n\n"
        "Изменение применяется мгновенно к доступности времени для гостей.",
        kb.build_admin_tables_kb(count),
    )


@router.callback_query(F.data.startswith("adm:confirm:"))
async def adm_confirm(event: CallbackQuery, bot):
    if not is_admin(event.from_user.id):
        await event.answer("🚫 Нет доступа")
        return
    booking_id = int(event.data.removeprefix("adm:confirm:"))
    booking = await db.get_booking(booking_id)
    if not booking:
        await event.answer("Бронь не найдена")
        return
    if booking["status"] != "pending":
        await event.answer("Эта бронь уже обработана")
        return

    await db.set_status(booking_id, "confirmed")
    booking = await db.get_booking(booking_id)
    await event.message.edit_text(booking_text(booking), reply_markup=None)
    await event.answer("✅ Подтверждено")

    await bot.send_message(
        booking["user_id"],
        "🎉 <b>Ваша бронь подтверждена!</b>\n\n"
        + booking_text(booking)
        + f"\n\nЖдём вас! Вопросы: {config.RESTAURANT_PHONE}",
    )


@router.callback_query(F.data.startswith("adm:cancel:"))
async def adm_cancel(event: CallbackQuery, bot):
    if not is_admin(event.from_user.id):
        await event.answer("🚫 Нет доступа")
        return
    booking_id = int(event.data.removeprefix("adm:cancel:"))
    booking = await db.get_booking(booking_id)
    if not booking:
        await event.answer("Бронь не найдена")
        return
    if booking["status"] == "cancelled":
        await event.answer("Бронь уже отменена")
        return

    await db.set_status(booking_id, "cancelled")
    booking = await db.get_booking(booking_id)
    await event.message.edit_text(booking_text(booking), reply_markup=None)
    await event.answer("❌ Отменено")

    await bot.send_message(
        booking["user_id"],
        "😔 <b>К сожалению, ваша бронь отменена.</b>\n\n"
        + booking_text(booking)
        + f"\n\nПозвоните нам для уточнения: {config.RESTAURANT_PHONE}",
    )


@router.callback_query(F.data == "adm:export")
async def adm_export(event: CallbackQuery):
    if not is_admin(event.from_user.id):
        await event.answer("🚫 Нет доступа")
        return
    await edit_or_send(
        event,
        "📤 <b>Экспорт броней</b>\n\nВыберите, какие брони выгрузить в CSV:",
        kb.admin_export_kb(),
    )


@router.callback_query(F.data.startswith("adm:export:"))
async def adm_export_run(event: CallbackQuery):
    if not is_admin(event.from_user.id):
        await event.answer("🚫 Нет доступа")
        return
    upcoming = event.data == "adm:export:upcoming"
    bookings = await db.export_bookings(upcoming=upcoming)

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        ["ID", "Дата", "Время", "Длительность(мин)", "Гостей", "Услуга", "Мастер", "Имя", "Телефон", "Комментарий", "Статус", "Создано"]
    )
    for b in bookings:
        writer.writerow(
            [
                b["id"],
                b["date"],
                b["time"],
                b.get("duration_minutes", 120),
                b["guests"],
                b.get("service_name") or "",
                b.get("master_name") or "",
                b["guest_name"],
                b["phone"],
                b.get("comment") or "",
                STATUS_TEXT.get(b["status"], b["status"]),
                b["created_at"],
            ]
        )
    data = buffer.getvalue().encode("utf-8-sig")
    filename = "bookings_upcoming.csv" if upcoming else "bookings_all.csv"
    await event.message.answer_document(
        BufferedInputFile(data, filename=filename),
        caption=f"📤 Броней в файле: {len(bookings)}",
    )
    await event.answer()


@router.callback_query(F.data.startswith("adm:occ"))
async def adm_occupancy(event: CallbackQuery):
    if not is_admin(event.from_user.id):
        await event.answer("🚫 Нет доступа")
        return
    data = event.data

    if data == "adm:occupancy":
        today = date.today()
        await edit_or_send(
            event,
            "📊 <b>Занятость</b>\n\nВыберите дату:",
            kb.build_calendar(today.year, today.month, prefix="adm:occ", cancel_cb="adm:menu"),
        )
    elif data.startswith("adm:occ:nav:"):
        iso = data.removeprefix("adm:occ:nav:")
        d = date.fromisoformat(iso)
        await edit_or_send(
            event,
            "📊 <b>Занятость</b>\n\nВыберите дату:",
            kb.build_calendar(d.year, d.month, prefix="adm:occ", cancel_cb="adm:menu"),
        )
    elif data.startswith("adm:occ:date:"):
        iso = data.removeprefix("adm:occ:date:")
        total = await db.get_table_count()
        lines = [
            f"📊 <b>Занятость на {format_date(iso)}</b>",
            f"🪑 4-местных столов: {total}\n",
        ]
        for slot in kb.restaurant_slots(date.fromisoformat(iso)):
            free = await db.free_tables(iso, slot)
            mark = " ✅" if free else " ⚠️ занято"
            lines.append(f"{slot} — {free} свободно{mark}")
        await edit_or_send(event, "\n".join(lines), kb.admin_occupancy_kb())
    else:
        await event.answer()
