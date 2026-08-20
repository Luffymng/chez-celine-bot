from datetime import date, datetime

import aiosqlite

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    guest_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    guests INTEGER NOT NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 120,
    tables_needed INTEGER NOT NULL DEFAULT 1,
    comment TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
)
"""

SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

MIGRATIONS = [
    ("ALTER TABLE bookings ADD COLUMN duration_minutes INTEGER NOT NULL DEFAULT 120", "duration_minutes"),
    ("ALTER TABLE bookings ADD COLUMN tables_needed INTEGER NOT NULL DEFAULT 1", "tables_needed"),
    ("ALTER TABLE bookings ADD COLUMN reminder_day_sent INTEGER NOT NULL DEFAULT 0", "reminder_day_sent"),
    ("ALTER TABLE bookings ADD COLUMN reminder_hour_sent INTEGER NOT NULL DEFAULT 0", "reminder_hour_sent"),
]


def _time_to_min(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


async def init_db() -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(SCHEMA)
        await db.execute(SETTINGS_SCHEMA)
        columns = {row[1] for row in await (await db.execute("PRAGMA table_info(bookings)")).fetchall()}
        for statement, column in MIGRATIONS:
            if column not in columns:
                await db.execute(statement)
        # Ключ tables_4 (миграция со старого ключа tables)
        row = await (await db.execute("SELECT value FROM settings WHERE key = 'tables_4'")).fetchone()
        if row is None:
            old = await (await db.execute("SELECT value FROM settings WHERE key = 'tables'")).fetchone()
            value = old[0] if old else str(config.DEFAULT_TABLES)
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('tables_4', ?)", (value,))
        await db.commit()


async def get_setting(key: str, default: str | None = None) -> str | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default


async def set_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()


async def get_table_count() -> int:
    raw = await get_setting("tables_4")
    return int(raw) if raw and raw.isdigit() else config.DEFAULT_TABLES


async def set_table_count(count: int) -> None:
    count = max(config.MIN_TABLES, min(config.MAX_TABLES, count))
    await set_setting("tables_4", str(count))


async def free_tables(on_date: str, time: str) -> int:
    """Сколько 4-местных столов свободно в слоте on_date/time.

    Учитывает длительность броней и только компании до 4 человек
    (большие группы садятся за столы на 5–8 чел., они не лимитируются).
    """
    total = await get_table_count()
    target = _time_to_min(time)
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT time, duration_minutes FROM bookings"
            " WHERE date = ? AND status != 'cancelled' AND guests <= ?",
            (on_date, config.TABLE_CAPACITY),
        )
        rows = await cur.fetchall()
    occupied = 0
    for row in rows:
        start = _time_to_min(row["time"])
        end = start + row["duration_minutes"]
        if start <= target < end:
            occupied += 1
    return total - occupied


async def create_booking(
    user_id: int,
    guest_name: str,
    phone: str,
    date: str,
    time: str,
    guests: int,
    duration_minutes: int,
    tables_needed: int,
    comment: str | None,
) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO bookings"
            " (user_id, guest_name, phone, date, time, guests, duration_minutes, tables_needed, comment, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                guest_name,
                phone,
                date,
                time,
                guests,
                duration_minutes,
                tables_needed,
                comment,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        await db.commit()
        return cur.lastrowid


async def get_booking(booking_id: int) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def list_bookings(
    *,
    status: str | None = None,
    on_date: str | None = None,
    upcoming: bool = False,
    limit: int = 10,
) -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if upcoming:
            cur = await db.execute(
                "SELECT * FROM bookings WHERE date >= ? AND status != 'cancelled'"
                " ORDER BY date, time LIMIT ?",
                (date.today().isoformat(), limit),
            )
        elif status:
            cur = await db.execute(
                "SELECT * FROM bookings WHERE status = ? ORDER BY date, time LIMIT ?",
                (status, limit),
            )
        elif on_date:
            cur = await db.execute(
                "SELECT * FROM bookings WHERE date = ? AND status != 'cancelled' ORDER BY time LIMIT ?",
                (on_date, limit),
            )
        else:
            cur = await db.execute("SELECT * FROM bookings ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def set_status(booking_id: int, status: str) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("UPDATE bookings SET status = ? WHERE id = ?", (status, booking_id))
        await db.commit()
        return cur.rowcount > 0


async def list_user_bookings(user_id: int) -> list[dict]:
    """Активные (не отменённые) брони пользователя на сегодня и позже."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM bookings WHERE user_id = ? AND date >= ? AND status != 'cancelled'"
            " ORDER BY date, time",
            (user_id, date.today().isoformat()),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def has_overlap(user_id: int, on_date: str, time: str, duration_minutes: int) -> bool:
    """Пересекается ли новая бронь по времени с активными бронями пользователя."""
    start_new = _time_to_min(time)
    end_new = start_new + duration_minutes
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT time, duration_minutes FROM bookings"
            " WHERE user_id = ? AND date = ? AND status != 'cancelled'",
            (user_id, on_date),
        )
        rows = await cur.fetchall()
    for row in rows:
        start = _time_to_min(row["time"])
        end = start + row["duration_minutes"]
        if max(start, start_new) < min(end, end_new):
            return True
    return False


async def mark_reminder_sent(booking_id: int, kind: str) -> None:
    column = "reminder_day_sent" if kind == "day" else "reminder_hour_sent"
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(f"UPDATE bookings SET {column} = 1 WHERE id = ?", (booking_id,))
        await db.commit()


async def export_bookings(upcoming: bool = False) -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if upcoming:
            cur = await db.execute(
                "SELECT * FROM bookings WHERE date >= ? AND status != 'cancelled' ORDER BY date, time",
                (date.today().isoformat(),),
            )
        else:
            cur = await db.execute("SELECT * FROM bookings ORDER BY created_at DESC")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
