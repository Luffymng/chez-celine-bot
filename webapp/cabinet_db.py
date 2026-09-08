"""Синхронный доступ к БД для веб-конструктора (psycopg)."""
import os
import sys
from datetime import date, timedelta

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


_SCHEMA_MIGRATED = False


def ensure_schema():
    global _SCHEMA_MIGRATED
    if _SCHEMA_MIGRATED:
        return
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'trial',
                trial_ends_at DATE,
                is_admin BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMP NOT NULL DEFAULT now()
            )
        """)
        col = conn.execute(
            "SELECT 1 FROM information_schema.columns"
            " WHERE table_name='restaurants' AND column_name='user_id'"
        ).fetchone()
        if not col:
            conn.execute(
                "ALTER TABLE restaurants ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE"
            )
        conn.execute(
            "UPDATE restaurants SET user_id = NULL WHERE user_id NOT IN "
            "(SELECT id FROM users) AND user_id IS NOT NULL"
        )
    _SCHEMA_MIGRATED = True


# === Пользователи ===

def get_user(user_id: int) -> dict | None:
    with _conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


def get_user_by_email(email: str) -> dict | None:
    with _conn() as conn:
        return conn.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()


def create_user(email: str, password_hash: str, name: str, trial_days: int) -> int:
    with _conn() as conn:
        return conn.execute(
            "INSERT INTO users (email, password_hash, name, trial_ends_at)"
            " VALUES (%s, %s, %s, %s) RETURNING id",
            (email, password_hash, name, date.today() + timedelta(days=trial_days)),
        ).fetchone()["id"]


def set_user_status(user_id: int, status: str):
    with _conn() as conn:
        conn.execute("UPDATE users SET status = %s WHERE id = %s", (status, user_id))


def set_user_admin(user_id: int, is_admin: bool):
    with _conn() as conn:
        conn.execute("UPDATE users SET is_admin = %s WHERE id = %s", (is_admin, user_id))


def ensure_admin(email: str, password_hash: str) -> int | None:
    user = get_user_by_email(email)
    if user:
        set_user_admin(user["id"], True)
        return user["id"]
    if not password_hash:
        return None
    uid = create_user(email, password_hash, "Администратор", 0)
    set_user_status(uid, "active")
    set_user_admin(uid, True)
    return uid


def list_users() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT u.*, (SELECT COUNT(*) FROM restaurants r WHERE r.user_id = u.id"
            " AND r.active) AS active_bots FROM users u ORDER BY u.id"
        ).fetchall()
        for row in rows:
            row["_bots"] = conn.execute(
                "SELECT id, name, active FROM restaurants WHERE user_id = %s ORDER BY id",
                (row["id"],),
            ).fetchall()
        return rows


# === Рестораны (скоуп владельца) ===

def list_restaurants(user_id: int | None = None, is_admin: bool = False):
    if is_admin:
        with _conn() as conn:
            return conn.execute(
                "SELECT * FROM restaurants ORDER BY id "
                "LIMIT 500"
            ).fetchall()
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM restaurants WHERE user_id = %s ORDER BY id", (user_id,)
        ).fetchall()


def get_restaurant(rid: int, user_id: int | None = None, is_admin: bool = False) -> dict | None:
    with _conn() as conn:
        if is_admin:
            return conn.execute("SELECT * FROM restaurants WHERE id = %s", (rid,)).fetchone()
        return conn.execute(
            "SELECT * FROM restaurants WHERE id = %s AND user_id = %s", (rid, user_id)
        ).fetchone()


def create_restaurant(name: str, user_id: int | None = None):
    with _conn() as conn:
        return conn.execute(
            "INSERT INTO restaurants (name, user_id) VALUES (%s, %s) RETURNING id",
            (name, user_id),
        ).fetchone()["id"]


def update_restaurant(rid: int, **fields):
    fields = {k: v for k, v in fields.items() if k in ALLOWED_COLUMNS}
    if not fields:
        return
    sets = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [rid]
    with _conn() as conn:
        conn.execute(f"UPDATE restaurants SET {sets} WHERE id = %s", values)


def list_bookings(rid: int, status: str | None = None, on_date: str | None = None,
                  upcoming: bool = False, limit: int = 500):
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


def booking_stats(rid: int, today: str) -> dict:
    with _conn() as conn:
        def cnt(sql, *args):
            return conn.execute(sql, args).fetchone()["count"]
        return {
            "today": cnt(
                "SELECT COUNT(*) FROM bookings WHERE restaurant_id = %s AND date = %s"
                " AND status != 'cancelled'", rid, today),
            "upcoming": cnt(
                "SELECT COUNT(*) FROM bookings WHERE restaurant_id = %s AND date >= %s"
                " AND status != 'cancelled'", rid, date.today().isoformat()),
            "pending": cnt(
                "SELECT COUNT(*) FROM bookings WHERE restaurant_id = %s AND status = 'pending'",
                rid),
            "confirmed": cnt(
                "SELECT COUNT(*) FROM bookings WHERE restaurant_id = %s AND status = 'confirmed'",
                rid),
        }


def set_status(bid: int, status: str):
    with _conn() as conn:
        conn.execute(
            "UPDATE bookings SET status = %s WHERE id = %s", (status, bid)
        )