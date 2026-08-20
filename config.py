import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

# Информация о ресторане
RESTAURANT_NAME = "Chez Céline"
RESTAURANT_ADDRESS = "г. Минск, ул. Интернациональная, 25А (метро Немига)"
RESTAURANT_PHONE = "+375 44 577-11-22"
RESTAURANT_HOURS = "Пн–Вс: 12:00 – 02:00"
INSTAGRAM = "https://www.instagram.com/chez.celine.minsk"
TELEGRAM_LINK = ""  # добавьте, когда появится

# Параметры бронирования
OPEN_HOUR = 12          # открытие
CLOSE_HOUR = 2          # закрытие 02:00 (последний слот не включается)
WEEKEND_OPEN_HOUR = 12  # одинаково с буднями
WEEKEND_CLOSE_HOUR = 2
SLOT_MINUTES = 30       # шаг между слотами
MIN_GUESTS = 1
MAX_GUESTS = 8

# Столы
TABLE_CAPACITY = 4       # вместимость одного стола (4-местные)
DEFAULT_TABLES = 12      # кол-во столов по умолчанию (меняется в админ-панели)
MIN_TABLES = 1
MAX_TABLES = 50
DURATION_OPTIONS = [60, 90, 120, 150, 180]  # длительность визита, минуты

# Напоминания о брони
REMINDER_DAY_HOURS = 24   # напоминание за сутки
REMINDER_HOURS = 2        # напоминание за 2 часа
POLL_INTERVAL = 60        # как часто проверять напоминания, сек

# Файлы (положите в папку data/)
DB_PATH = "data/chez_celine.db"
MENU_PDF = ""  # "data/menu.pdf" — когда появится
RESTAURANT_PHOTO = ""  # "data/restaurant.jpg" — когда появится
ABOUT_VIDEO = "data/about.mp4"
