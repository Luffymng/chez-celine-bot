import asyncio
import logging
from datetime import datetime

import config
import database as db
from utils import booking_text, format_date, format_duration

logger = logging.getLogger(__name__)

TOLERANCE = 5 * 60  # отправляем за 24ч/2ч с допуском до 5 минут раньше

DAY_MSG = (
    "⏰ <b>Напоминание о брони!</b>\n\n"
    "{text}\n\n"
    "Если планы изменились — отмените бронь в разделе «📋 Мои брони» "
    "или позвоните нам: {phone}"
)

HOUR_MSG = (
    "⏰ <b>Скоро ваша бронь!</b>\n\n"
    "{text}\n\n"
    "Ждём вас в Chez Céline!\n"
    "📍 {address} • {phone}"
)


def _booking_info(b: dict) -> str:
    return (
        f"Бронь №{b['id']}: {format_date(b['date'])} в {b['time']}, "
        f"на {format_duration(b.get('duration_minutes') or 120)}, "
        f"{b['guests']} чел."
    )


async def _send(bot, booking: dict, msg: str) -> None:
    try:
        await bot.send_message(booking["user_id"], msg)
    except Exception:
        logger.exception("Не удалось отправить напоминание для брони %s", booking["id"])


async def reminder_loop(bot) -> None:
    logger.info("Цикл напоминаний запущен")
    while True:
        try:
            await process_reminders(bot)
        except Exception:
            logger.exception("Ошибка в цикле напоминаний")
        await asyncio.sleep(config.POLL_INTERVAL)


async def process_reminders(bot) -> None:
    now = datetime.now()
    bookings = await db.list_bookings(status="confirmed", limit=1000)

    for b in bookings:
        start = datetime.fromisoformat(f"{b['date']}T{b['time']}")
        seconds_left = (start - now).total_seconds()
        day_gap = config.REMINDER_DAY_HOURS * 3600
        hour_gap = config.REMINDER_HOURS * 3600

        if not b.get("reminder_day_sent") and 0 <= seconds_left < day_gap + TOLERANCE:
            await _send(bot, b, DAY_MSG.format(text=_booking_info(b), phone=config.RESTAURANT_PHONE))
            await db.mark_reminder_sent(b["id"], "day")

        if not b.get("reminder_hour_sent") and 0 <= seconds_left < hour_gap + TOLERANCE:
            await _send(
                bot,
                b,
                HOUR_MSG.format(
                    text=_booking_info(b),
                    address=config.RESTAURANT_ADDRESS,
                    phone=config.RESTAURANT_PHONE,
                ),
            )
            await db.mark_reminder_sent(b["id"], "hour")
