from datetime import date, datetime

import asyncpg

import config

_pool: asyncpg.Pool | None = None


def _time_to_min(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def _rid() -> int:
    return config.RESTAURANT_ID


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'trial',
    trial_ends_at DATE,
    is_admin BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS restaurants (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    token TEXT UNIQUE,
    admin_ids TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    hours TEXT NOT NULL DEFAULT '',
    instagram TEXT NOT NULL DEFAULT '',
    telegram_link TEXT NOT NULL DEFAULT '',
    open_hour INTEGER NOT NULL DEFAULT 12,
    close_hour INTEGER NOT NULL DEFAULT 23,
    weekend_open_hour INTEGER NOT NULL DEFAULT 12,
    weekend_close_hour INTEGER NOT NULL DEFAULT 23,
    slot_minutes INTEGER NOT NULL DEFAULT 30,
    min_guests INTEGER NOT NULL DEFAULT 1,
    max_guests INTEGER NOT NULL DEFAULT 8,
    table_capacity INTEGER NOT NULL DEFAULT 4,
    default_tables INTEGER NOT NULL DEFAULT 12,
    min_tables INTEGER NOT NULL DEFAULT 1,
    max_tables INTEGER NOT NULL DEFAULT 50,
    duration_options TEXT NOT NULL DEFAULT '60,90,120,150,180',
    reminder_day_hours INTEGER NOT NULL DEFAULT 24,
    reminder_hour_hours INTEGER NOT NULL DEFAULT 2,
    menu_pdf TEXT NOT NULL DEFAULT '',
    restaurant_photo TEXT NOT NULL DEFAULT '',
    about_video TEXT NOT NULL DEFAULT '',
    bot_type TEXT NOT NULL DEFAULT 'restaurant',
    services_txt TEXT NOT NULL DEFAULT '',
    masters_txt TEXT NOT NULL DEFAULT '',
    resource_units INTEGER NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    guest_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    guests INTEGER NOT NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 120,
    tables_needed INTEGER NOT NULL DEFAULT 1,
    service_name TEXT NOT NULL DEFAULT '',
    master_name TEXT NOT NULL DEFAULT '',
    comment TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    reminder_day_sent BOOLEAN NOT NULL DEFAULT false,
    reminder_hour_sent BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bookings_restaurant_date
    ON bookings (restaurant_id, date, time);
"""


def _parse_duration(raw: str) -> list[int]:
    return [int(x) for x in (raw or "").split(",") if x.strip().isdigit()]


async def init_db() -> None:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=10)
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA)
        # Миграция: поле владельца для старых баз
        col = await conn.fetchval(
            "SELECT 1 FROM information_schema.columns"
            " WHERE table_name='restaurants' AND column_name='user_id'"
        )
        if not col:
            await conn.execute("ALTER TABLE restaurants ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
        for ddl in (
            "ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS bot_type TEXT NOT NULL DEFAULT 'restaurant'",
            "ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS services_txt TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS masters_txt TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS resource_units INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS service_name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS master_name TEXT NOT NULL DEFAULT ''",
        ):
            await conn.execute(ddl)
        # Ресторан по умолчанию, если настроек ещё нет
        row = await conn.fetchrow("SELECT id FROM restaurants WHERE id = $1", config.RESTAURANT_ID)
        if row is None:
            await create_restaurant(name="Ваш ресторан")


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# === Настройки ресторана ===

async def get_restaurant(restaurant_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM restaurants WHERE id = $1", restaurant_id)
        return dict(row) if row else None


async def get_restaurant_by_token(token: str) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM restaurants WHERE token = $1", token)
        return dict(row) if row else None


async def create_restaurant(*, name: str, token: str = "", admin_ids: str = "", user_id: int | None = None) -> int:
    async with _pool.acquire() as conn:
        rid = await conn.fetchval(
            "INSERT INTO restaurants (name, token, admin_ids, user_id) VALUES ($1, $2, $3, $4)"
            " RETURNING id",
            name, token or None, admin_ids, user_id,
        )
        return rid


async def list_restaurants() -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM restaurants ORDER BY id")
        return [dict(r) for r in rows]


async def update_restaurant(restaurant_id: int, **fields) -> None:
    allowed = {
        "name", "token", "admin_ids", "address", "phone", "hours", "instagram",
        "telegram_link", "open_hour", "close_hour", "weekend_open_hour",
        "weekend_close_hour", "slot_minutes", "min_guests", "max_guests",
        "table_capacity", "default_tables", "min_tables", "max_tables",
        "duration_options", "reminder_day_hours", "reminder_hour_hours",
        "menu_pdf", "restaurant_photo", "about_video", "active",
        "bot_type", "services_txt", "masters_txt", "resource_units",
    }
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(fields))
    values = list(fields.values()) + [restaurant_id]
    async with _pool.acquire() as conn:
        await conn.execute(f"UPDATE restaurants SET {sets} WHERE id = ${len(fields)+1}", *values)


# === Столы ===

async def get_table_count() -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT default_tables FROM restaurants WHERE id = $1", _rid()
        )
        return row["default_tables"] if row else config.DEFAULT_TABLES


async def set_table_count(count: int) -> None:
    count = max(config.MIN_TABLES, min(config.MAX_TABLES, count))
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE restaurants SET default_tables = $1 WHERE id = $2", count, _rid()
        )


async def free_tables(on_date: str, time: str) -> int:
    """Сколько столов свободно в слоте (учитывает длительность броней, компании <= capacity)."""
    total = await get_table_count()
    target = _time_to_min(time)
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT time, duration_minutes FROM bookings"
            " WHERE restaurant_id = $1 AND date = $2 AND status != 'cancelled' AND guests <= $3",
            _rid(), on_date, config.TABLE_CAPACITY,
        )
    occupied = 0
    for row in rows:
        start = _time_to_min(row["time"])
        end = start + row["duration_minutes"]
        if start <= target < end:
            occupied += 1
    return total - occupied


async def free_master_slots(on_date: str, slot: str, master: str) -> int:
    """Свободных окон у мастера в слоте (1 окно = 1 запись по умолчанию).

    Учитывает длительность записей и resource_units (параллельных окон)."""
    units = config.RESOURCE_UNITS
    target = _time_to_min(slot)
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT time, duration_minutes FROM bookings"
            " WHERE restaurant_id = $1 AND date = $2 AND master_name = $3"
            " AND status != 'cancelled'",
            _rid(), on_date, master,
        )
    occupied = 0
    for b in rows:
        start = _time_to_min(b["time"])
        end = start + b["duration_minutes"]
        if start <= target < end:
            occupied += 1
    return units - occupied


# === Брони ===

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
    service_name: str = "",
    master_name: str = "",
) -> int:
    async with _pool.acquire() as conn:
        bid = await conn.fetchval(
            "INSERT INTO bookings"
            " (restaurant_id, user_id, guest_name, phone, date, time, guests,"
            "  duration_minutes, tables_needed, service_name, master_name, comment, created_at)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13) RETURNING id",
            _rid(), user_id, guest_name, phone, date, time, guests,
            duration_minutes, tables_needed, service_name, master_name, comment,
            datetime.now(),
        )
        return bid


async def get_booking(booking_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM bookings WHERE id = $1", booking_id)
        return dict(row) if row else None


async def list_bookings_restaurant(
    restaurant_id: int,
    *,
    status: str | None = None,
    on_date: str | None = None,
    upcoming: bool = False,
    limit: int = 200,
) -> list[dict]:
    """Брони конкретного ресторана (для веб-кабинета)."""
    async with _pool.acquire() as conn:
        if upcoming:
            rows = await conn.fetch(
                "SELECT * FROM bookings WHERE restaurant_id = $1 AND date >= $2"
                " AND status != 'cancelled' ORDER BY date, time LIMIT $3",
                restaurant_id, date.today().isoformat(), limit,
            )
        elif status:
            rows = await conn.fetch(
                "SELECT * FROM bookings WHERE restaurant_id = $1 AND status = $2"
                " ORDER BY date, time LIMIT $3",
                restaurant_id, status, limit,
            )
        elif on_date:
            rows = await conn.fetch(
                "SELECT * FROM bookings WHERE restaurant_id = $1 AND date = $2"
                " AND status != 'cancelled' ORDER BY time LIMIT $3",
                restaurant_id, on_date, limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM bookings WHERE restaurant_id = $1"
                " ORDER BY created_at DESC LIMIT $2",
                restaurant_id, limit,
            )
        return [dict(r) for r in rows]


async def list_bookings(
    *,
    status: str | None = None,
    on_date: str | None = None,
    upcoming: bool = False,
    limit: int = 10,
) -> list[dict]:
    async with _pool.acquire() as conn:
        if upcoming:
            rows = await conn.fetch(
                "SELECT * FROM bookings WHERE restaurant_id = $1 AND date >= $2"
                " AND status != 'cancelled' ORDER BY date, time LIMIT $3",
                _rid(), date.today().isoformat(), limit,
            )
        elif status:
            rows = await conn.fetch(
                "SELECT * FROM bookings WHERE restaurant_id = $1 AND status = $2"
                " ORDER BY date, time LIMIT $3",
                _rid(), status, limit,
            )
        elif on_date:
            rows = await conn.fetch(
                "SELECT * FROM bookings WHERE restaurant_id = $1 AND date = $2"
                " AND status != 'cancelled' ORDER BY time LIMIT $3",
                _rid(), on_date, limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM bookings WHERE restaurant_id = $1"
                " ORDER BY created_at DESC LIMIT $2",
                _rid(), limit,
            )
        return [dict(r) for r in rows]


async def set_status(booking_id: int, status: str) -> bool:
    async with _pool.acquire() as conn:
        updated = await conn.execute(
            "UPDATE bookings SET status = $1 WHERE id = $2", status, booking_id
        )
        return updated.endswith(" 1")


async def list_user_bookings(user_id: int) -> list[dict]:
    """Активные (не отменённые) брони пользователя на сегодня и позже."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM bookings WHERE restaurant_id = $1 AND user_id = $2"
            " AND date >= $3 AND status != 'cancelled' ORDER BY date, time",
            _rid(), user_id, date.today().isoformat(),
        )
        return [dict(r) for r in rows]


async def has_overlap(user_id: int, on_date: str, time: str, duration_minutes: int) -> bool:
    """Пересекается ли новая бронь по времени с активными бронями пользователя."""
    start_new = _time_to_min(time)
    end_new = start_new + duration_minutes
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT time, duration_minutes FROM bookings"
            " WHERE restaurant_id = $1 AND user_id = $2 AND date = $3"
            " AND status != 'cancelled'",
            _rid(), user_id, on_date,
        )
    for row in rows:
        start = _time_to_min(row["time"])
        end = start + row["duration_minutes"]
        if max(start, start_new) < min(end, end_new):
            return True
    return False


async def mark_reminder_sent(booking_id: int, kind: str) -> None:
    column = "reminder_day_sent" if kind == "day" else "reminder_hour_sent"
    async with _pool.acquire() as conn:
        await conn.execute(
            f"UPDATE bookings SET {column} = true WHERE id = $1", booking_id
        )


async def export_bookings(upcoming: bool = False) -> list[dict]:
    async with _pool.acquire() as conn:
        if upcoming:
            rows = await conn.fetch(
                "SELECT * FROM bookings WHERE restaurant_id = $1 AND date >= $2"
                " AND status != 'cancelled' ORDER BY date, time",
                _rid(), date.today().isoformat(),
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM bookings WHERE restaurant_id = $1 ORDER BY created_at DESC",
                _rid(),
            )
        return [dict(r) for r in rows]