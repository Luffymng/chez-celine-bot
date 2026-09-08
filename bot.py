import asyncio
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


async def refresh_settings_loop() -> None:
    while True:
        try:
            restaurant = await db.get_restaurant(config.RESTAURANT_ID)
            if restaurant:
                config.apply_settings(restaurant)
        except Exception:
            logging.exception("Ошибка обновления настроек")
        await asyncio.sleep(60)


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
