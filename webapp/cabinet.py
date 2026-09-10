import os
import re
import sys
import urllib.parse
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cabinet_db as cdb
import config
import kinds
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(PROJ_ROOT, "data", "uploads")
UPLOAD_PREFIX = os.path.join("data", "uploads")
ALLOWED_MEDIA = {
    "menu_pdf": {".pdf"},
    "restaurant_photo": {".jpg", ".jpeg", ".png", ".webp", ".gif"},
    "about_video": {".mp4", ".mov", ".webm", ".mkv"},
}
MAX_UPLOAD_MB = 60

app = Flask(__name__)
app.secret_key = config.CABINET_SECRET
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

STATUS_LABELS = {
    "all": "Все",
    "pending": "Неподтверждённые",
    "confirmed": "Подтверждённые",
    "cancelled": "Отменённые",
}
USER_STATUS_LABELS = {
    "trial": "Пробный",
    "active": "Оплачен",
    "pending": "Ожидает оплату",
    "blocked": "Заблокирован",
}
PLAN_PERIOD = "месяц"


# === Помощники доступа ===

def _ensure_db():
    cdb.ensure_schema()


def _current_user() -> dict | None:
    uid = session.get("user_id")
    if not uid:
        return None
    user = cdb.get_user(uid)
    if user and user["status"] == "trial" and user["trial_ends_at"]:
        if user["trial_ends_at"] < date.today():
            cdb.set_user_status(uid, "blocked")
            user["status"] = "blocked"
    return user


def _is_allowed(user: dict) -> bool:
    return user is not None and (user["is_admin"] or user["status"] in ("trial", "active"))


def _login_required(view):
    def wrapper(*args, **kwargs):
        user = _current_user()
        if not user:
            return redirect(url_for("login"))
        kwargs["user"] = user
        return view(*args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def _subscribed_required(view):
    def wrapper(*args, **kwargs):
        user = _current_user()
        if not user:
            return redirect(url_for("login"))
        if not _is_allowed(user):
            return redirect(url_for("subscribe"))
        kwargs["user"] = user
        return view(*args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def _can_r(user: dict, rid: int) -> bool:
    return cdb.get_restaurant(rid, user["id"], user.get("is_admin")) is not None


# === Аутентификация ===

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = cdb.get_user_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            return redirect(url_for("index"))
        flash("Неверный e-mail или пароль", "error")
    return render_template(
        "login.html",
        plan_price=config.PLAN_PRICE,
        plan_period=PLAN_PERIOD,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not name or not EMAIL_RE.match(email) or len(password) < 6:
            flash("Проверьте имя, e-mail и пароль (мин. 6 символов)", "error")
        elif cdb.get_user_by_email(email):
            flash("Этот e-mail уже зарегистрирован. Войдите.", "error")
        else:
            uid = cdb.create_user(
                email,
                generate_password_hash(password),
                name,
                config.TRIAL_DAYS,
            )
            if email == config.ADMIN_EMAIL:
                cdb.set_user_status(uid, "active")
                cdb.set_user_admin(uid, True)
            session["user_id"] = uid
            return redirect(url_for("index", welcome=1))
    return render_template(
        "register.html",
        trial_days=config.TRIAL_DAYS,
        plan_price=config.PLAN_PRICE,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# === Оплата (гейт входа) ===

@app.route("/subscribe")
def subscribe():
    user = _current_user()
    if user and _is_allowed(user):
        return redirect(url_for("index"))
    return render_template(
        "subscribe.html",
        user=user,
        plan_price=config.PLAN_PRICE,
        plan_period=PLAN_PERIOD,
    )


@app.route("/subscribe/request", methods=["POST"])
def subscribe_request():
    user = _current_user()
    if user and _is_allowed(user):
        return redirect(url_for("index"))
    if user:
        cdb.set_user_status(user["id"], "pending")
        flash("Заявка отправлена. Активируем после подтверждения оплаты.", "ok")
    return redirect(url_for("login"))


# === Конструктор ===

@app.route("/")
@_subscribed_required
def index(user):
    _ensure_db()
    restaurants = cdb.list_restaurants(user["id"], user.get("is_admin"))
    welcome = request.args.get("welcome")
    return render_template("restaurants.html", user=user, restaurants=restaurants,
                           welcome=welcome, plan_price=config.PLAN_PRICE,
                           trial_days=config.TRIAL_DAYS,
                           kinds_list=kinds.KINDS) 


@app.route("/create", methods=["POST"])
@_subscribed_required
def create(user):
    _ensure_db()
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Укажите название бизнеса", "error")
        return redirect(url_for("index"))
    bot_type = request.form.get("bot_type")
    if bot_type not in kinds.KINDS:
        bot_type = "restaurant"
    rid = cdb.create_restaurant(name, user["id"], bot_type)
    return redirect(url_for("edit", rid=rid))


@app.route("/restaurant/<int:rid>")
@_subscribed_required
def dashboard(rid: int, user):
    _ensure_db()
    if not _can_r(user, rid):
        flash("Доступ запрещён", "error")
        return redirect(url_for("index"))
    restaurant = cdb.get_restaurant(rid, user["id"], user.get("is_admin"))
    today = date.today().isoformat()
    stats = cdb.booking_stats(rid, today)
    pending = cdb.list_bookings(rid, status="pending")
    today_b = cdb.list_bookings(rid, on_date=today)
    remain = max(0, int(restaurant["default_tables"] or 0) - len(today_b))
    return render_template(
        "dashboard.html", user=user, r=restaurant,
        kind=kinds.get_kind(restaurant.get("bot_type")),
        stats=stats, pending=pending, today_b=today_b, today=today, remain=remain,
        status_labels=STATUS_LABELS,
        now=datetime.now(),
    )


@app.route("/restaurant/<int:rid>/edit", methods=["GET", "POST"])
@_subscribed_required
def edit(rid: int, user):
    _ensure_db()
    if not _can_r(user, rid):
        flash("Доступ запрещён", "error")
        return redirect(url_for("index"))
    restaurant = cdb.get_restaurant(rid, user["id"], user.get("is_admin"))
    if request.method == "POST":
        def nv(name):
            """Пустое число -> сохранить прежнее значение (не NULL)."""
            val = _int(request.form.get(name))
            return restaurant[name] if val is None else val
        token = (request.form.get("token") or "").strip()
        if request.form.get("remove_token"):
            token = ""
        elif not token and restaurant["token"]:
            token = restaurant["token"]  # пустое поле — не стираем рабочий токен
        dup = cdb.get_restaurant_by_token(token, exclude_rid=rid) if token else None
        if dup:
            flash(f"Токен уже используется рестораном «{dup['name']}» (#{dup['id']}). Каждый бот — свой токен от @BotFather.", "error")
            return redirect(url_for("edit", rid=rid))
        bad_link = None
        links = {}
        for key, label in (("instagram", "Instagram"), ("telegram_link", "Telegram")):
            v = _link(request.form.get(key))
            if v is None:
                bad_link = label
                break
            links[key] = v
        if bad_link:
            flash(f"Некорректный URL в поле «{bad_link}»: нужен адрес вида https://site.com/…", "error")
            return redirect(url_for("edit", rid=rid))
        try:
            bot_type = request.form.get("bot_type", restaurant["bot_type"] or "restaurant")
            if bot_type not in kinds.KINDS:
                bot_type = "restaurant"
            type_changed = bot_type != (restaurant["bot_type"] or "restaurant")
            cdb.update_restaurant(
                rid,
                name=request.form.get("name", ""),
                token=token,
                admin_ids=request.form.get("admin_ids", ""),
                address=request.form.get("address", ""),
                phone=request.form.get("phone", ""),
                hours=request.form.get("hours", ""),
                instagram=links["instagram"],
                telegram_link=links["telegram_link"],
                open_hour=nv("open_hour"),
                close_hour=nv("close_hour"),
                weekend_open_hour=nv("weekend_open_hour"),
                weekend_close_hour=nv("weekend_close_hour"),
                slot_minutes=nv("slot_minutes"),
                min_guests=nv("min_guests"),
                max_guests=nv("max_guests"),
                table_capacity=nv("table_capacity"),
                default_tables=nv("default_tables"),
                min_tables=nv("min_tables"),
                max_tables=nv("max_tables"),
                duration_options=request.form.get("duration_options", ""),
                reminder_day_hours=nv("reminder_day_hours"),
                reminder_hour_hours=nv("reminder_hour_hours"),
                menu_pdf=_media_field("menu_pdf", restaurant["menu_pdf"]),
                restaurant_photo=_media_field("restaurant_photo", restaurant["restaurant_photo"]),
                about_video=_media_field("about_video", restaurant["about_video"]),
                active=request.form.get("active") == "on",
                bot_type=bot_type,
                services_txt=request.form.get("services_txt", "") or "",
                masters_txt=request.form.get("masters_txt", "") or "",
                resource_units=max(1, (nv("resource_units") or 1)),
            )
        except Exception:
            app.logger.exception("Ошибка сохранения")
            flash("Не удалось сохранить: проверьте заполнение полей", "error")
            return redirect(url_for("edit", rid=rid))
        if type_changed:
            flash(
                f"Тип бота изменён на {kinds.KINDS[bot_type]['icon']} {kinds.KINDS[bot_type]['label']} — "
                "бот перезапустится с новым сценарием записи",
                "ok",
            )
        flash("Изменения сохранены и переданы боту", "ok")
        return redirect(url_for("edit", rid=rid))
    return render_template("edit.html", user=user, r=restaurant,
                           kind=kinds.get_kind(restaurant.get("bot_type")),
                           kinds_list=kinds.KINDS,
                           platform_enabled=bool(config.PLATFORM_BOT_TOKEN and config.PLATFORM_USERNAME),
                           platform_username=config.PLATFORM_USERNAME)


@app.route("/restaurant/<int:rid>/bookings")
@_subscribed_required
def bookings(rid: int, user):
    _ensure_db()
    if not _can_r(user, rid):
        flash("Доступ запрещён", "error")
        return redirect(url_for("index"))
    restaurant = cdb.get_restaurant(rid, user["id"], user.get("is_admin"))
    status = request.args.get("status", "all")
    on_date = request.args.get("on_date", "")
    upcoming = request.args.get("upcoming", "") == "1"
    if status == "all":
        items = cdb.list_bookings(rid, on_date=on_date or None, upcoming=upcoming)
    else:
        items = cdb.list_bookings(rid, status=status)
    return render_template(
        "bookings.html", user=user, r=restaurant, items=items,
        kind=kinds.get_kind(restaurant.get("bot_type")),
        status=status, on_date=on_date, upcoming=upcoming,
        status_labels=STATUS_LABELS, today=date.today().isoformat(),
    )


@app.route("/restaurant/<int:rid>/booking/<int:bid>/status", methods=["POST"])
@_subscribed_required
def set_status(rid: int, bid: int, user):
    if not _can_r(user, rid):
        flash("Доступ запрещён", "error")
        return redirect(url_for("index"))
    new_status = request.form.get("status")
    if new_status in ("pending", "confirmed", "cancelled"):
        cdb.set_status(bid, new_status)
    return redirect(url_for("dashboard", rid=rid))


@app.route("/restaurant/<int:rid>/tables", methods=["POST"])
@_subscribed_required
def set_tables(rid: int, user):
    if not _can_r(user, rid):
        flash("Доступ запрещён", "error")
        return redirect(url_for("index"))
    count = _int(request.form.get("count")) or 0
    restaurant = cdb.get_restaurant(rid, user["id"], user.get("is_admin"))
    bounded = max(restaurant["min_tables"], min(count, restaurant["max_tables"]))
    cdb.update_restaurant(rid, default_tables=bounded)
    flash("Количество столов обновлено", "ok")
    return redirect(url_for("dashboard", rid=rid))


@app.route("/restaurant/<int:rid>/preview")
@_subscribed_required
def preview(rid: int, user):
    _ensure_db()
    if not _can_r(user, rid):
        flash("Доступ запрещён", "error")
        return redirect(url_for("index"))
    restaurant = cdb.get_restaurant(rid, user["id"], user.get("is_admin"))
    return render_template(
        "preview.html",
        user=user,
        r=restaurant,
        kind=kinds.get_kind(restaurant.get("bot_type")),
        services=kinds.parse_services_txt(restaurant.get("services_txt")),
        masters=kinds.parse_masters_txt(restaurant.get("masters_txt")),
    )


# === Админ платформы ===

def _admin_required(view):
    def wrapper(*args, **kwargs):
        user = _current_user()
        if not user or not user.get("is_admin"):
            return redirect(url_for("index"))
        kwargs["user"] = user
        return view(*args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


@app.route("/admin/users")
@_admin_required
def admin_users(user):
    _ensure_db()
    users = cdb.list_users()
    return render_template("admin_users.html", user=user, users=users,
                           status_labels=USER_STATUS_LABELS,
                           today=date.today())


@app.route("/admin/users/<int:uid>/status", methods=["POST"])
@_admin_required
def admin_set_status(uid: int, user):
    status = request.form.get("status")
    if status in ("trial", "active", "pending", "blocked"):
        cdb.set_user_status(uid, status)
        flash("Статус пользователя обновлён", "ok")
    return redirect(url_for("admin_users"))


def _int(value) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _link(value) -> str | None:
    """Нормализует ссылку: добавляет https:// и отсекает мусор вида
    https://instagram/luffy. None — если URL непохож на настоящий."""
    v = (value or "").strip()
    if not v:
        return ""
    if not v.startswith(("http://", "https://")):
        v = "https://" + v
    host = urllib.parse.urlparse(v).netloc
    if not host or ("." not in host and host != "localhost"):
        return None
    return v


def _remove_old(prev: str):
    if not prev or not prev.startswith(UPLOAD_PREFIX):
        return
    p = os.path.normpath(os.path.join(PROJ_ROOT, prev))
    if p.startswith(UPLOAD_DIR) and os.path.isfile(p):
        try:
            os.remove(p)
        except OSError:
            pass
        try:
            d = os.path.dirname(p)
            if not os.listdir(d):
                os.rmdir(d)
        except OSError:
            pass


def _save_upload(field: str) -> str | None:
    f = request.files.get("file_" + field)
    if not f or not f.filename:
        return None
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_MEDIA[field]:
        flash(f"Файл «{os.path.basename(f.filename)}» не подходит для этого поля", "error")
        return None
    d = os.path.join(UPLOAD_DIR, field)
    os.makedirs(d, exist_ok=True)
    f.save(os.path.join(d, "file" + ext))
    return os.path.join(UPLOAD_PREFIX, field, "file" + ext)


def _media_field(field: str, prev: str) -> str:
    new = _save_upload(field)
    if new:
        _remove_old(prev)
        return new
    if prev and (request.form.get("remove_media") or request.form.get("remove_" + field)):
        _remove_old(prev)
        return ""
    return prev


@app.errorhandler(RequestEntityTooLarge)
def _too_large(e):
    rid = request.view_args.get("rid") if request.view_args else None
    if rid:
        flash(f"Файл больше {MAX_UPLOAD_MB} МБ — не загружен", "error")
        return redirect(url_for("edit", rid=rid))
    return redirect(url_for("index"))


if __name__ == "__main__":
    _ensure_db()
    cdb.ensure_admin(
        config.ADMIN_EMAIL,
        generate_password_hash(config.ADMIN_PASSWORD) if config.ADMIN_PASSWORD else "",
    )
    port = int(os.getenv("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)