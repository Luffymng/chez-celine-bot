import asyncio
import hashlib
import json
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
import database as db
from handlers import admin, booking, mine, start
from reminder import reminder_loop

logging.basicConfig(level=logging.INFO)


def _settings_hash(restaurant: dict) -> str:
    data = {k: v for k, v in restaurant.items() if k not in ("created_at", "updated_at")}
    for k, v in list(data.items()):
        if isinstance(v, bool) or v is None:
            data[k] = str(v)
        elif not isinstance(v, (int, float, str)):
            data[k] = json.dumps(v, ensure_ascii=False, default=str)
    s = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(s.encode("utf-8")).hexdigest()


async def refresh_settings_loop() -> None:
    last_hash = None
    while True:
        try:
            restaurant = await db.get_restaurant(config.RESTAURANT_ID)
            if restaurant:
                config.apply_settings(restaurant)
                new_hash = _settings_hash(restaurant)
                if new_hash != last_hash:
                    last_hash = new_hash
                    logging.info(
                        "Настройки обновлены из БД: %s (id=%s)",
                        config.RESTAURANT_NAME,
                        config.RESTAURANT_ID,
                    )
        except Exception:
            logging.exception("Ошибка обновления настроек")
        await asyncio.sleep(30)


async def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан. Скопируйте .env.example в .env и заполните.")

    await db.init_db()

    restaurant = await db.get_restaurant(config.RESTAURANT_ID)
    if not restaurant:
        raise SystemExit(f"Ресторан с id={config.RESTAURANT_ID} не найден в БД.")
    config.apply_settings(restaurant)
    logging.info("Настройки загружены: %s (id=%s)", config.RESTAURANT_NAME, config.RESTAURANT_ID)

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(booking.router)
    dp.include_router(mine.router)
    dp.include_router(admin.router)

    asyncio.create_task(reminder_loop(bot))
    asyncio.create_task(refresh_settings_loop())

    logging.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
