import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cabinet_db as cdb
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("CABINET_SECRET", "change-me-cabinet-secret")

CABINET_PASSWORD = os.getenv("CABINET_PASSWORD", "admin123")

STATUS_LABELS = {
    "all": "Все",
    "pending": "Неподтверждённые",
    "confirmed": "Подтверждённые",
    "cancelled": "Отменённые",
}


def _login_required(view):
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == CABINET_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        flash("Неверный пароль", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@_login_required
def index():
    restaurants = cdb.list_restaurants()
    return render_template("restaurants.html", restaurants=restaurants)


@app.route("/restaurant/<int:rid>")
@_login_required
def dashboard(rid: int):
    restaurant = cdb.get_restaurant(rid)
    if not restaurant:
        flash("Ресторан не найден", "error")
        return redirect(url_for("index"))
    today = date.today().isoformat()
    pending = cdb.list_bookings(rid, status="pending")
    today_b = cdb.list_bookings(rid, on_date=today)
    upcoming = cdb.list_bookings(rid, upcoming=True)
    return render_template(
        "dashboard.html",
        r=restaurant,
        pending=pending,
        today_b=today_b,
        upcoming=upcoming,
        today=today,
        status_labels=STATUS_LABELS,
    )


@app.route("/create", methods=["POST"])
@_login_required
def create():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Укажите название ресторана", "error")
        return redirect(url_for("index"))
    rid = cdb.create_restaurant(name)
    flash("Ресторан создан. Заполните настройки.", "ok")
    return redirect(url_for("edit", rid=rid))


@app.route("/restaurant/<int:rid>/edit", methods=["GET", "POST"])
@_login_required
def edit(rid: int):
    if request.method == "POST":
        cdb.update_restaurant(
            rid,
            name=request.form.get("name", ""),
            token=request.form.get("token", ""),
            admin_ids=request.form.get("admin_ids", ""),
            address=request.form.get("address", ""),
            phone=request.form.get("phone", ""),
            hours=request.form.get("hours", ""),
            instagram=request.form.get("instagram", ""),
            telegram_link=request.form.get("telegram_link", ""),
            open_hour=_int(request.form.get("open_hour")),
            close_hour=_int(request.form.get("close_hour")),
            weekend_open_hour=_int(request.form.get("weekend_open_hour")),
            weekend_close_hour=_int(request.form.get("weekend_close_hour")),
            slot_minutes=_int(request.form.get("slot_minutes")),
            min_guests=_int(request.form.get("min_guests")),
            max_guests=_int(request.form.get("max_guests")),
            table_capacity=_int(request.form.get("table_capacity")),
            default_tables=_int(request.form.get("default_tables")),
            min_tables=_int(request.form.get("min_tables")),
            max_tables=_int(request.form.get("max_tables")),
            duration_options=request.form.get("duration_options", ""),
            reminder_day_hours=_int(request.form.get("reminder_day_hours")),
            reminder_hour_hours=_int(request.form.get("reminder_hour_hours")),
            menu_pdf=request.form.get("menu_pdf", ""),
            restaurant_photo=request.form.get("restaurant_photo", ""),
            about_video=request.form.get("about_video", ""),
            active=request.form.get("active") == "on",
        )
        flash("Настройки сохранены", "ok")
        return redirect(url_for("dashboard", rid=rid))
    restaurant = cdb.get_restaurant(rid)
    if not restaurant:
        flash("Ресторан не найден", "error")
        return redirect(url_for("index"))
    return render_template("edit.html", r=restaurant)


@app.route("/restaurant/<int:rid>/bookings")
@_login_required
def bookings(rid: int):
    restaurant = cdb.get_restaurant(rid)
    status = request.args.get("status", "all")
    on_date = request.args.get("on_date", "")
    upcoming = request.args.get("upcoming", "") == "1"
    if status == "all":
        items = cdb.list_bookings(rid, on_date=on_date or None, upcoming=upcoming)
    else:
        items = cdb.list_bookings(rid, status=status)
    return render_template(
        "bookings.html",
        r=restaurant,
        items=items,
        status=status,
        on_date=on_date,
        upcoming=upcoming,
        status_labels=STATUS_LABELS,
        today=date.today().isoformat(),
    )


@app.route("/restaurant/<int:rid>/booking/<int:bid>/status", methods=["POST"])
@_login_required
def set_status(rid: int, bid: int):
    new_status = request.form.get("status")
    if new_status in ("pending", "confirmed", "cancelled"):
        cdb.set_status(bid, new_status)
    return redirect(url_for("bookings", rid=rid))


@app.route("/restaurant/<int:rid>/tables", methods=["POST"])
@_login_required
def set_tables(rid: int):
    count = _int(request.form.get("count")) or 0
    restaurant = cdb.get_restaurant(rid)
    bounded = max(restaurant["min_tables"], min(count, restaurant["max_tables"]))
    cdb.update_restaurant(rid, default_tables=bounded)
    flash("Количество столов обновлено", "ok")
    return redirect(url_for("dashboard", rid=rid))


def _int(value) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)