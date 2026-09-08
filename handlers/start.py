import os

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

import config
import keyboards as kb
from utils import edit_or_send

router = Router()


def _welcome() -> str:
    return (
        f"🍽 <b>{config.RESTAURANT_NAME}</b>\n\n"
        f"📍 {config.RESTAURANT_ADDRESS}\n"
        f"🕐 {config.RESTAURANT_HOURS}\n\n"
        "Забронируйте столик прямо в Telegram — это займёт пару минут 😉"
    )


def _about() -> str:
    return (
        f"🏠 <b>{config.RESTAURANT_NAME}</b>\n\n"
        f"📍 {config.RESTAURANT_ADDRESS}\n"
        f"📞 {config.RESTAURANT_PHONE}\n"
        f"📷 {config.INSTAGRAM}"
    )


def _hours() -> str:
    return (
        "🕐 <b>Часы работы</b>\n\n"
        f"{config.RESTAURANT_HOURS}\n\n"
        "Бронирование столиков возможно в рабочее время ресторана."
    )


def _contacts() -> str:
    return (
        "📞 <b>Контакты</b>\n\n"
        f"📍 Адрес: {config.RESTAURANT_ADDRESS}\n"
        f"📞 Телефон: {config.RESTAURANT_PHONE}\n"
        f"📷 Instagram: {config.INSTAGRAM}\n"
        f"🕐 {config.RESTAURANT_HOURS}"
    )


def _menu_fallback() -> str:
    return (
        f"📖 <b>Меню «{config.RESTAURANT_NAME}»</b>\n\n"
        "Меню скоро появится здесь! А пока загляните в наш Instagram — "
        "публикуем новинки и сезонные блюда."
    )


def _menu_caption() -> str:
    return f"📖 <b>Меню «{config.RESTAURANT_NAME}»</b>"


async def show_main_menu(event):
    await edit_or_send(event, _welcome(), kb.main_menu_kb())


@router.message(CommandStart())
async def cmd_start(message: Message):
    if config.RESTAURANT_PHOTO and os.path.exists(config.RESTAURANT_PHOTO):
        await message.answer_photo(
            FSInputFile(config.RESTAURANT_PHOTO),
            caption=_welcome(),
            reply_markup=kb.main_menu_kb(),
        )
    else:
        await message.answer(_welcome(), reply_markup=kb.main_menu_kb())


@router.callback_query(F.data == "main")
async def cb_main(event, state: FSMContext):
    await state.clear()
    msg = event.message
    # Медиа-сообщения (видео/фото) нельзя заменить текстом — удаляем и шлём меню заново
    if msg.video or msg.photo or msg.document or msg.audio or msg.animation:
        await msg.delete()
        await msg.answer(_welcome(), reply_markup=kb.main_menu_kb())
        await event.answer()
    else:
        await show_main_menu(event)


@router.callback_query(F.data == "menu")
async def cb_menu(event):
    if config.MENU_PDF and os.path.exists(config.MENU_PDF):
        await event.message.answer_document(
            FSInputFile(config.MENU_PDF),
            caption=_menu_caption(),
        )
        await event.answer()
    else:
        await edit_or_send(event, _menu_fallback(), kb.main_menu_kb())


@router.callback_query(F.data == "about")
async def cb_about(event):
    if config.ABOUT_VIDEO and os.path.exists(config.ABOUT_VIDEO):
        await event.message.answer_video(
            FSInputFile(config.ABOUT_VIDEO),
            caption=_about(),
            reply_markup=kb.back_to_menu_kb(),
        )
        await event.answer()
    else:
        await edit_or_send(event, _about(), kb.back_to_menu_kb())


@router.callback_query(F.data == "hours")
async def cb_hours(event):
    await edit_or_send(event, _hours(), kb.back_to_menu_kb())


@router.callback_query(F.data == "contacts")
async def cb_contacts(event):
    await edit_or_send(event, _contacts(), kb.back_to_menu_kb())