import os

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

import config
import kinds
import keyboards as kb
from utils import edit_or_send

router = Router()


def _welcome() -> str:
    k = kinds.get_kind(config.BOT_TYPE)
    return (
        f"{k['icon']} <b>{config.RESTAURANT_NAME}</b>\n\n"
        f"📍 {config.RESTAURANT_ADDRESS}\n"
        f"🕐 {config.RESTAURANT_HOURS}\n\n"
        f"{k['welcome_line']}"
    )


def _about() -> str:
    parts = [
        f"🏠 <b>{config.RESTAURANT_NAME}</b>\n",
        f"📍 {config.RESTAURANT_ADDRESS}",
        f"📞 {config.RESTAURANT_PHONE}",
    ]
    if config.INSTAGRAM:
        parts.append(f"📷 {config.INSTAGRAM}")
    return "\n".join(parts)


def _hours() -> str:
    return (
        "🕐 <b>Часы работы</b>\n\n"
        f"{config.RESTAURANT_HOURS}\n\n"
        "Запись доступна в рабочее время."
    )


def _contacts() -> str:
    parts = [
        "📞 <b>Контакты</b>\n",
        f"📍 Адрес: {config.RESTAURANT_ADDRESS}",
        f"📞 Телефон: {config.RESTAURANT_PHONE}",
    ]
    if config.INSTAGRAM:
        parts.append(f"📷 Instagram: {config.INSTAGRAM}")
    parts.append(f"🕐 {config.RESTAURANT_HOURS}")
    return "\n".join(parts)


def _menu_fallback() -> str:
    k = kinds.get_kind(config.BOT_TYPE)
    return (
        f"{k['menu_emoji']} <b>{k['menu_label']} «{config.RESTAURANT_NAME}»</b>\n\n"
        f"{k['menu_label']} скоро появится. А пока загляните в наш Instagram."
    )


def _menu_caption() -> str:
    k = kinds.get_kind(config.BOT_TYPE)
    return f"{k['menu_emoji']} <b>{k['menu_label']} «{config.RESTAURANT_NAME}»</b>"


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