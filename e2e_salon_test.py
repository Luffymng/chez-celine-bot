import asyncio
import logging
from datetime import datetime, timedelta, timezone

import asyncpg

import config
import database as db

logging.basicConfig(level=logging.WARNING)

DSN = "postgresql://artemknysevich@localhost:5432/restaurant_saas"
TEST_USER_ID = 999900001


async def create_salon_row() -> int:
    c = await asyncpg.connect(DSN)
    ids = await c.fetchval(
        "SELECT array_agg(id) FROM restaurants WHERE name = 'Салон «Тест»'"
    )
    if ids:
        for rid in ids:
            await c.execute("DELETE FROM bookings WHERE restaurant_id=$1", rid)
            await c.execute("DELETE FROM restaurants WHERE id=$1", rid)
    rid = await c.fetchval(
        "INSERT INTO restaurants (user_id, name, address, phone, hours, admin_ids, bot_type, services_txt, masters_txt, resource_units) "
        "VALUES (1, 'Салон «Тест»', 'ул. Красивая, 10', '+375 29 111-22-33', 'Пн-Вс 10-20', '', 'salon', $1, $2, 2) RETURNING id",
        "Стрижка, 30\nОкрашивание, 90\nМаникюр",
        "Иван\nОльга",
    )
    await c.close()
    return rid


async def build_harness(rid: int):
    import config as cfg

    cfg.DATABASE_URL = DSN
    cfg.RESTAURANT_ID = rid
    cfg.BOT_TOKEN = "123456:FAKE-TEST-TOKEN"

    await db.init_db()
    row = await db.get_restaurant(rid)
    assert row, "restaurant not found"
    cfg.apply_settings(row)

    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Chat, Message, Update, User
    from aiogram.types import CallbackQuery

    from aiogram.client.session.base import BaseSession

    class FakeSession(BaseSession):
        def __init__(self):
            super().__init__()
            self.journal = []
            self.mids = 100
            self.last_text = ""
            self.last_buttons = []

        async def close(self):
            return None

        async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
            yield b""

        def _msg(self, payload):
            self.mids += 1
            chat_id = payload.get("chat_id")
            if chat_id is None and payload.get("chat"):
                chat_id = payload["chat"].get("id")
            markup = payload.get("reply_markup") or {}
            self.last_buttons = [
                b["callback_data"]
                for row in markup.get("inline_keyboard", [])
                for b in row
                if b.get("callback_data")
            ]
            self.last_text = payload.get("text") or ""
            return Message(
                message_id=self.mids,
                date=datetime.now(timezone.utc),
                chat=Chat(id=chat_id, type="private"),
                text=payload.get("text"),
            )

        def record(self, payload: dict):
            self.last_text = payload.get("text") or ""
            markup = payload.get("reply_markup") or {}
            keys = markup.get("inline_keyboard") if isinstance(markup, dict) else None
            if isinstance(keys, list):
                self.last_buttons = [
                    b["callback_data"]
                    for row in keys
                    for b in row
                    if b.get("callback_data")
                ]

        async def make_request(self, bot, method, timeout=None):
            name = method.__api_method__
            payload = method.model_dump(exclude_none=True)
            self.journal.append((name, payload))
            if name in ("sendMessage", "editMessageText"):
                self.record(payload)
            ret = method.__returning__
            if ret is bool:
                return True
            if ret is Message:
                return self._msg(payload)
            if ret is User:
                return User(id=1, is_bot=True, first_name="test", username="testbot")
            return None

    session = FakeSession()
    bot = Bot(token=cfg.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=session)
    dp = Dispatcher(storage=MemoryStorage())

    from handlers import admin, booking, mine, start

    dp.include_router(start.router)
    dp.include_router(booking.router)
    dp.include_router(mine.router)
    dp.include_router(admin.router)

    def user() -> User:
        return User(id=TEST_USER_ID, is_bot=False, first_name="Клиент")

    def msg(text: str) -> Message:
        return Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=TEST_USER_ID, type="private"), from_user=user(), text=text)

    def cb(data: str, light: bool = True) -> CallbackQuery:
        return CallbackQuery(
            id=str(TEST_USER_ID * 10 + len(session.journal)),
            from_user=user(),
            chat_instance="1",
            message=msg("✍️") if light else None,
            data=data,
        )

    async def feed_message(text: str):
        await dp.feed_update(bot, Update(update_id=len(session.journal) + 1, message=msg(text)))

    async def feed_cb(data: str):
        await dp.feed_update(bot, Update(update_id=len(session.journal) + 2, callback_query=cb(data)))

    def show(text: str):
        print(f"   > {text}")

    return session, feed_message, feed_cb, show


async def main() -> None:
    rid = await create_salon_row()
    print(f"Создан тестовый салон: id={rid}, bot_type=salon")

    session, feed_message, feed_cb, show = await build_harness(rid)

    show("клиент шлёт /book")
    await feed_message("/book")
    show(session.last_text.splitlines()[0])
    assert session.last_buttons[:2] and session.last_buttons[0].startswith("services:"), session.last_buttons

    show("выбирает услугу #0")
    await feed_cb(session.last_buttons[0])
    show(session.last_text.splitlines()[0])
    assert session.last_buttons[0].startswith("master:"), session.last_buttons
    master_btn = session.last_buttons[0]

    show("выбирает мастера")
    await feed_cb(master_btn)
    show(session.last_text.splitlines()[0])
    date_btns = [d for d in session.last_buttons if d.startswith("cal:date:")]
    assert date_btns, "нет дат в календаре"

    iso = await pick_future_weekday()
    assert any(d == f"cal:date:{iso}" for d in date_btns), "нет нужной даты"
    show(f"выбирает дату {iso}")
    await feed_cb(f"cal:date:{iso}")
    show(session.last_text.splitlines()[0])
    time_btns = [d for d in session.last_buttons if d.startswith("time:")]
    assert time_btns, "нет слотов времени"
    show(f"слоты: {time_btns}")

    show("выбирает время")
    await feed_cb(time_btns[0])
    show(session.last_text.splitlines()[0])

    show("вводит имя")
    await feed_message("Тестович")
    show(session.last_text.splitlines()[0])

    show("вводит телефон")
    await feed_message("+375 29 111-22-33")
    show(session.last_text.splitlines()[0])

    show("вводит комментарий")
    await feed_message("Хочу к окну")
    show(session.last_text.replace("\n", " / "))

    show("подтверждает")
    await feed_cb("book:confirm")
    sent_texts = [p.get("text") or "" for _, p in session.journal]
    success = [t for t in sent_texts if "Заявка отправлена" in t]
    assert success, "\n".join(sent_texts)
    show(success[-1].splitlines()[0])

    for b in await verify_booking(rid, TEST_USER_ID, session):
        print(b)

    await db.close_db()


async def pick_future_weekday() -> str:
    d = datetime.now().date() + timedelta(days=7)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()


async def verify_booking(rid, user_id, session) -> list[str]:
    c = await asyncpg.connect(DSN)
    row = await c.fetchrow(
        "SELECT date, time, guests, duration_minutes, service_name, master_name, comment, status FROM bookings "
        "WHERE restaurant_id=$1 AND user_id=$2 ORDER BY id DESC LIMIT 1",
        rid, user_id,
    )
    await c.close()
    checks = [
        ("service_name='Стрижка'", row["service_name"] == "Стрижка", row["service_name"]),
        ("master_name='Иван'", row["master_name"] == "Иван", row["master_name"]),
        ("comment сохранён", row["comment"] == "Хочу к окну", row["comment"]),
        ("status=pending", row["status"] == "pending", row["status"]),
    ]
    out = []
    for label, ok, val in checks:
        out.append(f"   [{'OK' if ok else 'FAIL'}] {label} = {val!r}")
    return out


if __name__ == "__main__":
    asyncio.run(main())