import os

from dotenv import load_dotenv

load_dotenv()

# === Параметры инстанса (env) ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{os.getenv('PGUSER', '')}@{os.getenv('PGHOST', 'localhost')}:5432/restaurant_saas",
).strip()
RESTAURANT_ID = int(os.getenv("RESTAURANT_ID", "1"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

# === Веб-конструктор ===
CABINET_SECRET = os.getenv("CABINET_SECRET", "change-me-cabinet-secret")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@bot.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
PLAN_PRICE = int(os.getenv("PLAN_PRICE", "1500"))
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "7"))

# Админы ресторана — загружаются из БД, тут только запасной вариант
ADMIN_IDS: list[int] = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]

# === Настройки ресторана (загружаются из БД при старте, здесь — дефолты) ===
RESTAURANT_NAME = ""
RESTAURANT_ADDRESS = ""
RESTAURANT_PHONE = ""
RESTAURANT_HOURS = ""
INSTAGRAM = ""
TELEGRAM_LINK = ""

OPEN_HOUR = 12
CLOSE_HOUR = 23
WEEKEND_OPEN_HOUR = 12
WEEKEND_CLOSE_HOUR = 23
SLOT_MINUTES = 30
MIN_GUESTS = 1
MAX_GUESTS = 8

TABLE_CAPACITY = 4
DEFAULT_TABLES = 12
MIN_TABLES = 1
MAX_TABLES = 50
DURATION_OPTIONS = [60, 90, 120, 150, 180]

REMINDER_DAY_HOURS = 24
REMINDER_HOURS = 2

MENU_PDF = ""
RESTAURANT_PHOTO = ""
ABOUT_VIDEO = ""


def apply_settings(data: dict | None) -> None:
    """Заполняет глобальные настройки из строки ресторана (БД)."""
    if not data:
        return
    global ADMIN_IDS
    mapping = {
        "RESTAURANT_NAME": "name",
        "RESTAURANT_ADDRESS": "address",
        "RESTAURANT_PHONE": "phone",
        "RESTAURANT_HOURS": "hours",
        "INSTAGRAM": "instagram",
        "TELEGRAM_LINK": "telegram_link",
        "OPEN_HOUR": "open_hour",
        "CLOSE_HOUR": "close_hour",
        "WEEKEND_OPEN_HOUR": "weekend_open_hour",
        "WEEKEND_CLOSE_HOUR": "weekend_close_hour",
        "SLOT_MINUTES": "slot_minutes",
        "MIN_GUESTS": "min_guests",
        "MAX_GUESTS": "max_guests",
        "TABLE_CAPACITY": "table_capacity",
        "DEFAULT_TABLES": "default_tables",
        "MIN_TABLES": "min_tables",
        "MAX_TABLES": "max_tables",
        "DURATION_OPTIONS": "duration_options",
        "REMINDER_DAY_HOURS": "reminder_day_hours",
        "REMINDER_HOURS": "reminder_hour_hours",
        "MENU_PDF": "menu_pdf",
        "RESTAURANT_PHOTO": "restaurant_photo",
        "ABOUT_VIDEO": "about_video",
    }
    for attr, key in mapping.items():
        if key == "duration_options":
            globals()[attr] = [int(x) for x in str(data.get(key) or "").split(",") if x.strip().isdigit()]
            continue
        globals()[attr] = data.get(key)

    admin_raw = data.get("admin_ids") or ""
    ids = [int(x) for x in str(admin_raw).split(",") if x.strip().isdigit()]
    if ids:
        ADMIN_IDS = ids