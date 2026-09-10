"""Типы ботов-конструктора: ресторан, салон, клиника, фитнес.

Тип определяет набор шагов бронирования, тексты меню и карточки настроек.
Модуль не зависит от config — используется и ботом, и кабинетом, и превью.
"""

KINDS = {
    "restaurant": {
        "label": "Ресторан",
        "icon": "🍽",
        "blurb": "Рестораны, кафе и бары — бронь столиков",
        "book_label": "🍽 Забронировать столик",
        "menu_label": "Меню",
        "menu_emoji": "📖",
        "welcome_line": "Забронируйте столик прямо в Telegram — это займёт пару минут 😉",
        "master_label": "",
        "steps": ["date", "guests", "duration", "time", "name", "phone", "comment"],
        "confirm_kind": "table",
        "tables": True,
        "services": False,
        "masters": False,
    },
    "salon": {
        "label": "Салон / барбершоп",
        "icon": "💇",
        "blurb": "Барбершопы и салоны красоты — услуги и мастера",
        "book_label": "💇 Записаться",
        "menu_label": "Услуги",
        "menu_emoji": "💈",
        "welcome_line": "Запишитесь на услугу прямо в Telegram — это займёт пару минут 😉",
        "master_label": "мастер",
        "steps": ["service", "master", "date", "time", "name", "phone", "comment"],
        "confirm_kind": "appointment",
        "tables": False,
        "services": True,
        "masters": True,
    },
    "clinic": {
        "label": "Клиника / косметология",
        "icon": "🩺",
        "blurb": "Клиники, косметология, стоматология — специалисты",
        "book_label": "🩺 Записаться",
        "menu_label": "Услуги",
        "menu_emoji": "💉",
        "welcome_line": "Запишитесь к специалисту прямо в Telegram — это займёт пару минут 😉",
        "master_label": "специалист",
        "steps": ["service", "master", "date", "time", "name", "phone", "comment"],
        "confirm_kind": "appointment",
        "tables": False,
        "services": True,
        "masters": True,
    },
    "fit": {
        "label": "Фитнес / тренер",
        "icon": "🏋️",
        "blurb": "Фитнес-клубы и тренеры — тренировки по расписанию",
        "book_label": "🏋️ Записаться",
        "menu_label": "Тренировки",
        "menu_emoji": "💪",
        "welcome_line": "Запишитесь на тренировку прямо в Telegram — это займёт пару минут 😉",
        "master_label": "тренер",
        "steps": ["service", "master", "date", "time", "name", "phone", "comment"],
        "confirm_kind": "appointment",
        "tables": False,
        "services": True,
        "masters": True,
    },
}

DEFAULT_KIND = "restaurant"


def get_kind(code: str | None) -> dict:
    return KINDS.get(code or DEFAULT_KIND, KINDS[DEFAULT_KIND])


def parse_services_txt(raw: str | None) -> list[dict]:
    """Разбирает текстовый список услуг: каждая строка «Название:минуты»
    (разделители : , ; — или дефис). Если минуты не указаны — 30."""
    out: list[dict] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        name, minutes = line, 30
        for sep in (":", ",", ";", "—", "-"):
            if sep in line:
                left, rest = line.split(sep, 1)
                digits = "".join(ch for ch in rest if ch.isdigit())
                if digits:
                    minutes = int(digits)
                name = left.strip()
                break
        if name:
            out.append({"name": name, "minutes": minutes})
    return out


def parse_masters_txt(raw: str | None) -> list[str]:
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def fmt_minutes(minutes: int) -> str:
    if minutes % 60 == 0:
        return f"{minutes // 60} ч"
    if minutes < 60:
        return f"{minutes} мин"
    return f"{minutes // 60} ч {minutes % 60} мин"


def fmt_duration_dot(minutes: int) -> str:
    if minutes % 60 == 0:
        return f"{minutes // 60} ч"
    return f"{minutes / 60:.1f}".replace(".", ",") + " ч"