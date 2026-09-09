"""Супервизор: боты ресторанов + управляющий бот платформы.

Один bot.py на каждый ресторан с токеном (restaurants.token, active).
Плюс один platform_manager.py, если задан PLATFORM_BOT_TOKEN.
Запуск: python supervisor.py
"""
import logging
import os
import signal
import subprocess
import sys
import time

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHECK_INTERVAL = int(os.getenv("SUPERVISOR_INTERVAL", "20"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "supervisor.log")),
        logging.StreamHandler(),
    ],
)


def desired_restaurants():
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT id, name, token FROM restaurants"
            " WHERE token IS NOT NULL AND trim(token) != '' AND active"
            " ORDER BY id"
        ).fetchall()


def _log_file(rid):
    path = os.path.join(BASE_DIR, f"bot_{rid}.log")
    return open(path, "a"), path


class BotProcess:
    def __init__(self, rid, name, token):
        self.rid = rid
        self.name = name
        self.token = token
        self.proc = None
        self.bad_token = False
        self.rapid = 0
        self.last_start = 0

    def start(self):
        env = os.environ.copy()
        env["RESTAURANT_ID"] = str(self.rid)
        env["BOT_TOKEN"] = self.token
        log, path = _log_file(self.rid)
        self.proc = subprocess.Popen(
            [sys.executable, "bot.py"],
            cwd=BASE_DIR,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        self.last_start = time.time()
        self.rapid += 1
        logging.info("Запущен бот #%s (%s) pid=%s log=%s", self.rid, self.name, self.proc.pid, path)

    def check(self):
        if self.proc is None:
            return
        code = self.proc.poll()
        if code is None:
            return
        self.bad_token = code == 2
        logging.warning("Бот #%s (%s) вышел с кодом %s", self.rid, self.name, code)
        self.proc = None

    def restart_if_needed(self):
        if self.proc is not None:
            return
        if self.bad_token:
            return
        if time.time() - self.last_start < 15:
            return  # слишком быстрый рестарт — бот валится при старте
        if self.rapid >= 5:
            logging.warning("Бот #%s — падает при старте, пауза 5 минут", self.rid)
            if time.time() - self.last_start < 300:
                return
            self.rapid = 0
        self.start()

    def stop(self):
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            logging.info("Остановлен бот #%s (%s)", self.rid, self.name)
        self.proc = None


class PlatformProcess:
    """Управляющий бот (создание ботов для ресторанов)."""

    SCRIPT = "platform_manager.py"
    LOG = os.path.join(BASE_DIR, "platform.log")

    def __init__(self):
        self.proc = None
        self.last_start = 0
        self.rapid = 0

    def start(self):
        log = open(self.LOG, "a")
        self.proc = subprocess.Popen(
            [sys.executable, self.SCRIPT],
            cwd=BASE_DIR,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        self.last_start = time.time()
        self.rapid += 1
        logging.info("Запущен управляющий бот pid=%s log=%s", self.proc.pid, self.LOG)

    def check(self):
        if self.proc is None:
            return
        code = self.proc.poll()
        if code is None:
            return
        logging.warning("Управляющий бот вышел с кодом %s", code)
        self.proc = None

    def restart_if_needed(self):
        if self.proc is not None:
            return
        if time.time() - self.last_start < 15:
            return
        if self.rapid >= 5:
            logging.warning("Управляющий бот падает при старте, пауза 5 минут")
            if time.time() - self.last_start < 300:
                return
            self.rapid = 0
        self.start()

    def stop(self):
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            logging.info("Остановлен управляющий бот")
        self.proc = None


def main():
    processes = {}
    platform = PlatformProcess() if config.PLATFORM_BOT_TOKEN else None
    logging.info(
        "Супервизор запущен (интервал %ss, платформенный бот: %s)",
        CHECK_INTERVAL,
        "да" if platform else "нет",
    )
    try:
        while True:
            try:
                desired = desired_restaurants()
            except Exception:
                logging.exception("Ошибка чтения БД")
                desired = []
            desired_map = {r["id"]: r for r in desired}

            # Запустить новые / обновить токен
            for rid, row in desired_map.items():
                bp = processes.get(rid)
                if bp is None:
                    bp = BotProcess(rid, row["name"], row["token"])
                    processes[rid] = bp
                    bp.start()
                elif bp.token != row["token"]:
                    logging.info("Токен #%s изменился — перезапуск", rid)
                    bp.stop()
                    bp.token = row["token"]
                    bp.bad_token = False
                    bp.rapid = 0
                    bp.start()

            # Остановить ненужные
            for rid in list(processes):
                if rid not in desired_map:
                    bp = processes.pop(rid)
                    bp.stop()

            # Проверить живых
            for bp in processes.values():
                bp.check()
                bp.restart_if_needed()

            # Платформенный бот
            if platform is not None:
                platform.check()
                platform.restart_if_needed()

            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        for bp in processes.values():
            bp.stop()
        if platform is not None:
            platform.stop()
        logging.info("Супервизор остановлен")


if __name__ == "__main__":
    main()