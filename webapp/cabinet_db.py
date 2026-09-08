"""Синхронный доступ к БД для веб-кабинета (psycopg)."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg
from psycopg.rows import dict_row

import config

ALLOWED_COLUMNS = {
    "name", "token", "admin_ids", "address", "phone", "hours", "instagram",
    "telegram_link", "open_hour", "close_hour", "weekend_open_hour",
    "weekend_close_hour", "slot_minutes", "min_guests", "max_guests",
    "table_capacity", "default_tables", "min_tables", "max_tables",
    "duration_options", "reminder_day_hours", "reminder_hour_hours",
    "menu_pdf", "restaurant_photo", "about_video", "active",
}


def _conn():
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row)


def list_restaurants():
    with _conn() as conn:
        return conn.execute("SELECT * FROM restaurants ORDER BY id").fetchall()


def get_restaurant(rid: int):
    with _conn() as conn:
        return conn.execute("SELECT * FROM restaurants WHERE id = %s", (rid,)).fetchone()


def create_restaurant(name: str):
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO restaurants (name) VALUES (%s) RETURNING id", (name,)
        )
        return cur.fetchone()["id"]


def update_restaurant(rid: int, **fields):
    fields = {k: v for k, v in fields.items() if k in ALLOWED_COLUMNS}
    if not fields:
        return
    sets = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [rid]
    with _conn() as conn:
        conn.execute(f"UPDATE restaurants SET {sets} WHERE id = %s", values)


def list_bookings(rid: int, status: str | None = None, on_date: str | None = None,
                  upcoming: bool = False, limit: int = 300):
    with _conn() as conn:
        if upcoming:
            rows = conn.execute(
                "SELECT * FROM bookings WHERE restaurant_id = %s AND date >= %s"
                " AND status != 'cancelled' ORDER BY date, time LIMIT %s",
                (rid, date.today().isoformat(), limit),
            ).fetchall()
        elif status:
            rows = conn.execute(
                "SELECT * FROM bookings WHERE restaurant_id = %s AND status = %s"
                " ORDER BY date, time LIMIT %s",
                (rid, status, limit),
            ).fetchall()
        elif on_date:
            rows = conn.execute(
                "SELECT * FROM bookings WHERE restaurant_id = %s AND date = %s"
                " AND status != 'cancelled' ORDER BY time LIMIT %s",
                (rid, on_date, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM bookings WHERE restaurant_id = %s"
                " ORDER BY created_at DESC LIMIT %s",
                (rid, limit),
            ).fetchall()
        return rows


def set_status(bid: int, status: str):
    with _conn() as conn:
        conn.execute(
            "UPDATE bookings SET status = %s WHERE id = %s", (status, bid)
        )


def table_count(rid: int) -> int:
    r = get_restaurant(rid)
    return r["default_tables"] if r else 0