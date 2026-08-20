import os

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

import config
import keyboards as kb
from utils import edit_or_send

router = Router()

WELCOME = (
    "🍽 <b>Chez Céline</b> — ресторан европейской кухни с французским характером в центре Минска.\n\n"
    "Современная гастрономия, уютная атмосфера французского бистро, "
    "летняя терраса и живая музыка.\n\n"
    "Бронируйте столик прямо в Telegram — это займёт пару минут 😉"
)

ABOUT = (
    "🏠 <b>О ресторане Chez Céline</b>\n\n"
    "📍 ул. Интернациональная, 25А (метро Немига)\n"
    "🍷 Европейская кухня с французским характером\n"
    "☀️ Летняя терраса\n"
    "🎤 Живая музыка\n"
    "🎉 Банкеты до 90 гостей\n\n"
    "Современная гастрономия в уютной атмосфере французского бистро.\n"
    "Бронируйте столик прямо в Telegram!"
)

HOURS = (
    "🕐 <b>Часы работы</b>\n\n"
    f"{config.RESTAURANT_HOURS}\n\n"
    "Бронирование столиков возможно в рабочее время ресторана."
)

CONTACTS = (
    "📞 <b>Контакты</b>\n\n"
    f"📍 Адрес: {config.RESTAURANT_ADDRESS}\n"
    f"📞 Телефон: {config.RESTAURANT_PHONE}\n"
    f"📷 Instagram: {config.INSTAGRAM}\n"
    f"🕐 {config.RESTAURANT_HOURS}"
)

MENU_FALLBACK = (
    "📖 <b>Меню «Chez Céline»</b>\n\n"
    "Меню скоро появится здесь! А пока загляните в наш Instagram — "
    "публикуем новинки и сезонные блюда."
)


async def show_main_menu(event, text: str = WELCOME):
    await edit_or_send(event, text, kb.main_menu_kb())


@router.message(CommandStart())
async def cmd_start(message: Message):
    if config.RESTAURANT_PHOTO and os.path.exists(config.RESTAURANT_PHOTO):
        await message.answer_photo(
            FSInputFile(config.RESTAURANT_PHOTO),
            caption=WELCOME,
            reply_markup=kb.main_menu_kb(),
        )
    else:
        await message.answer(WELCOME, reply_markup=kb.main_menu_kb())


@router.callback_query(F.data == "main")
async def cb_main(event, state: FSMContext):
    await state.clear()
    msg = event.message
    # Медиа-сообщения (видео/фото) нельзя заменить текстом — удаляем и шлём меню заново
    if msg.video or msg.photo or msg.document or msg.audio or msg.animation:
        await msg.delete()
        await msg.answer(WELCOME, reply_markup=kb.main_menu_kb())
        await event.answer()
    else:
        await show_main_menu(event)


@router.callback_query(F.data == "menu")
async def cb_menu(event):
    if config.MENU_PDF and os.path.exists(config.MENU_PDF):
        await event.message.answer_document(
            FSInputFile(config.MENU_PDF),
            caption="📖 <b>Меню «Chez Céline»</b>",
        )
        await event.answer()
    else:
        await edit_or_send(event, MENU_FALLBACK, kb.main_menu_kb())


@router.callback_query(F.data == "about")
async def cb_about(event):
    if config.ABOUT_VIDEO and os.path.exists(config.ABOUT_VIDEO):
        await event.message.answer_video(
            FSInputFile(config.ABOUT_VIDEO),
            caption=ABOUT,
            reply_markup=kb.back_to_menu_kb(),
        )
        await event.answer()
    else:
        await edit_or_send(event, ABOUT, kb.back_to_menu_kb())


@router.callback_query(F.data == "hours")
async def cb_hours(event):
    await edit_or_send(event, HOURS, kb.back_to_menu_kb())


@router.callback_query(F.data == "contacts")
async def cb_contacts(event):
    await edit_or_send(event, CONTACTS, kb.back_to_menu_kb())
