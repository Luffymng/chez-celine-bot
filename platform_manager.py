"""Управляющий бот платформы: создание ботов для ресторанов одним нажатием.

Работает с токеном PLATFORM_BOT_TOKEN. Пользователь нажимает на сайте
t.me/<username>?start=makebot_<rid> -> мы берём запрос в БД (bot_request_user),
присылаем кнопку request_managed_bot. После создания бота в диалоге Telegram
приходит update managed_bot -> получаем токен getManagedBotToken -> вписываем
в restaurants.token. Никаких зависимостей от aiogram (сырой long polling).

Запуск: python platform_manager.py
"""
import json
import logging
import os
import re
import sys
import time
import urllib.request
import urllib.error

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API = "https://api.telegram.org/bot"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "platform.log")),
        logging.StreamHandler(),
    ],
)


def _conn():
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row)


def tg(method: str, params: dict | None = None, timeout: float = 60) -> dict:
    url = API + config.PLATFORM_BOT_TOKEN + "/" + method
    data = json.dumps(params or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as e:
        body = json.loads(e.read() or b"{}")
    if not body.get("ok"):
        raise RuntimeError(f"{method}: {body.get('description')}")
    return body


def _slug(name: str, rid: int) -> str:
    s = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")
    s = re.sub(r"_+", "_", s)[:24]
    if not s or not s[0].isalpha():
        s = f"restaurant_{s}" if s else "restaurant"
    if not s.endswith("_bot"):
        s += f"_{rid}"[:2] + "_bot"
    return s


def handle_message(msg: dict):
    chat = msg.get("chat") or {}
    user = msg.get("from") or {}
    uid = user.get("id")
    text = msg.get("text") or ""
    if not uid or not chat.get("id"):
        return
    m = re.match(r"^/start\s+(makebot_\d+)$", text.strip()) if text else None
    if not m:
        text_preview = (text or "").splitlines()[0][:60] if text else ""
        if (text or "").startswith("/start"):
            tg("sendMessage", {
                "chat_id": chat["id"],
                "text": "Привет! Кнопку «Создать бота» нужно нажимать из кабинета БотКонструктора.",
            })
        else:
            logging.info("Сообщение от %s (rid?) без вызова: %r", uid, text_preview)
        return
    rid = int(m.group(1).split("_", 1)[1])
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, name, admin_ids FROM restaurants WHERE id = %s", (rid,)
        ).fetchone()
    if not row:
        tg("sendMessage", {"chat_id": chat["id"], "text": "Ресторан не найден."})
        return
    admins = [int(x) for x in str(row["admin_ids"] or "").split(",") if x.strip().isdigit()]
    if not admins or uid not in admins:
        tg("sendMessage", {
            "chat_id": chat["id"],
            "text": "Этот аккаунт не числится администратором ресторана. "
                    "Впишите свой Telegram ID в поле «Админы» в кабинете.",
        })
        return
    with _conn() as conn:
        conn.execute("UPDATE restaurants SET bot_request_user = %s WHERE id = %s", (uid, rid))
    name = (row["name"] or "Restaurant")[:64]
    username = _slug(row["name"] or "", rid)
    tg("sendMessage", {
        "chat_id": chat["id"],
        "text": (
            f'Создаю бота для ресторана «{name}».\n\n'
            "Нажмите кнопку ниже, затем в диалоге Telegram подтвердите имя "
            "и username бота (можно изменить). Токен подставится сам."
        ),
        "reply_markup": {
            "keyboard": [[{
                "text": "⚡ Создать бота",
                "request_managed_bot": {
                    "request_id": rid,
                    "suggested_name": name,
                    "suggested_username": username,
                },
            }]],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        },
    })


def handle_managed_bot(update: dict):
    mb = update.get("managed_bot") or {}
    creator = mb.get("user") or {}
    new_bot = mb.get("bot") or {}
    cid = creator.get("id")
    new_id = new_bot.get("id")
    if not cid or not new_id:
        return
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, name FROM restaurants"
            " WHERE bot_request_user = %s AND (token IS NULL OR token = '')"
            " ORDER BY id LIMIT 1",
            (cid,),
        ).fetchone()
    if not row:
        logging.warning("Управляемый бот %s создан, но запрос не найден (cid=%s)", new_id, cid)
        return
    try:
        token = tg("getManagedBotToken", {"user_id": new_id})["result"]
    except RuntimeError as exc:
        logging.error("getManagedBotToken: %s", exc)
        return
    with _conn() as conn:
        conn.execute(
            "UPDATE restaurants SET token = %s, bot_request_user = NULL WHERE id = %s",
            (token, row["id"]),
        )
    username = new_bot.get("username")
    logging.info("Бот @%s (#id=%s) создан -> сохранён в ресторан #%s", username, new_id, row["id"])
    tg("sendMessage", {
        "chat_id": cid,
        "text": (
            f"Готово! Бот @{username or new_id} создан, токен вписан в кабинет.\n\n"
            "Осталось: включить тумблер «Бот включён» и сохранить настройки в кабинете."
        ),
    })


ALLOWED_UPDATES = ["message", "managed_bot"]


def main():
    if not config.PLATFORM_BOT_TOKEN:
        logging.error("PLATFORM_BOT_TOKEN не задан — управляющий бот не запущен")
        return
    offset = None
    updates_seen = 0
    last_heartbeat = 0.0
    logging.info("Управляющий бот запущен (%s)", config.PLATFORM_USERNAME or config.PLATFORM_BOT_TOKEN[:10])
    while True:
        try:
            params = {"timeout": 50, "allowed_updates": ALLOWED_UPDATES}
            if offset is not None:
                params["offset"] = offset
            result = tg("getUpdates", params)["result"]
            updates_seen += len(result)
            if time.time() - last_heartbeat >= 600:
                last_heartbeat = time.time()
                logging.info(
                    "getUpdates ok (offset=%s, всего обработано обновлений: %s)",
                    offset, updates_seen,
                )
            for update in result:
                offset = update["update_id"] + 1
                try:
                    if "message" in update:
                        handle_message(update["message"])
                    elif "managed_bot" in update:
                        handle_managed_bot(update)
                except Exception:
                    logging.exception("Ошибка обработки update %s", update.get("update_id"))
        except Exception:
            logging.exception("getUpdates")
            time.sleep(5)


if __name__ == "__main__":
    main()