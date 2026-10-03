"""
تخزين سجل البوتات المستضافة في SQLite — مع قفل بسيط للكتابة عشان
كل الـ coroutines اللي بتعدّل نفس الصف ماتضاربش.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("HOSTBOT_DATA_DIR", "hostbot/data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "hosting.db"
BOTS_DATA_DIR = DATA_DIR / "bots"
BOTS_DATA_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_db():
    with _lock, _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS bots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id      INTEGER NOT NULL,
                token         TEXT    NOT NULL UNIQUE,
                bot_username  TEXT,
                bot_name      TEXT,
                bot_type      TEXT    NOT NULL DEFAULT 'contact',
                status        TEXT    NOT NULL DEFAULT 'stopped', -- stopped | running | error
                settings      TEXT    NOT NULL DEFAULT '{}',
                error_msg     TEXT,
                created_at    INTEGER NOT NULL,
                last_started  INTEGER,
                uptime_start  INTEGER,
                total_msgs    INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS global_settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_bots_owner ON bots(owner_id);
            """
        )


# ═══════════════════════════════════════════════════════════
#  بوتات مستضافة
# ═══════════════════════════════════════════════════════════

def list_bots(owner_id: int | None = None) -> list[dict]:
    with _lock, _conn() as c:
        if owner_id is None:
            rows = c.execute("SELECT * FROM bots ORDER BY id").fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM bots WHERE owner_id=? ORDER BY id",
                (owner_id,),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_bot(bot_id: int) -> dict | None:
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM bots WHERE id=?", (bot_id,)).fetchone()
    return _row_to_dict(r) if r else None


def get_bot_by_token(token: str) -> dict | None:
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM bots WHERE token=?", (token,)).fetchone()
    return _row_to_dict(r) if r else None


def get_bot_dir(bot_id: int) -> Path:
    d = BOTS_DATA_DIR / str(bot_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def add_bot(owner_id: int, token: str, bot_type: str, username: str | None = None,
            name: str | None = None) -> int:
    now = int(time.time())
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO bots(owner_id, token, bot_username, bot_name, bot_type, "
            "status, settings, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (owner_id, token, username, name, bot_type, "stopped", "{}", now),
        )
        bid = cur.lastrowid
    get_bot_dir(bid)
    return bid


def update_bot(bot_id: int, **fields: Any):
    if not fields:
        return
    if "settings" in fields and not isinstance(fields["settings"], str):
        fields["settings"] = json.dumps(fields["settings"], ensure_ascii=False)
    keys = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [bot_id]
    with _lock, _conn() as c:
        c.execute(f"UPDATE bots SET {keys} WHERE id=?", vals)


def delete_bot(bot_id: int):
    with _lock, _conn() as c:
        c.execute("DELETE FROM bots WHERE id=?", (bot_id,))


def bot_owner(bot_id: int) -> int | None:
    with _lock, _conn() as c:
        r = c.execute("SELECT owner_id FROM bots WHERE id=?", (bot_id,)).fetchone()
    return int(r["owner_id"]) if r else None


def inc_bot_messages(bot_id: int, n: int = 1):
    with _lock, _conn() as c:
        c.execute(
            "UPDATE bots SET total_msgs = total_msgs + ? WHERE id=?",
            (n, bot_id),
        )


def _row_to_dict(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    try:
        d["settings"] = json.loads(d.get("settings") or "{}")
    except Exception:
        d["settings"] = {}
    return d


# ═══════════════════════════════════════════════════════════
#  إعدادات عامة
# ═══════════════════════════════════════════════════════════

def get_global(key: str, default: str | None = None) -> str | None:
    with _lock, _conn() as c:
        r = c.execute("SELECT value FROM global_settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_global(key: str, value: str):
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO global_settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ═══════════════════════════════════════════════════════════
#  دوال مساعدة لملفات JSON داخل مجلد كل بوت
# ═══════════════════════════════════════════════════════════

def load_json(bot_id: int, filename: str, default):
    path = get_bot_dir(bot_id) / filename
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json(bot_id: int, filename: str, data):
    path = get_bot_dir(bot_id) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════
#  Owners registry (لمن يملك حق إنشاء بوتات)
# ═══════════════════════════════════════════════════════════

def is_owner(user_id: int, owner_id_env: int) -> bool:
    """
    المالك الأساسي هو OWNER_ID من البيئة.
    أي مستخدم يضيفه المالك يصبح "مدير" ويقدر ينشئ بوتات أيضاً.
    """
    if user_id == owner_id_env:
        return True
    owners = json.loads(get_global("admins", "[]") or "[]")
    return int(user_id) in {int(x) for x in owners}


def add_admin(user_id: int):
    owners = json.loads(get_global("admins", "[]") or "[]")
    if user_id not in owners:
        owners.append(int(user_id))
        set_global("admins", json.dumps(owners))


def remove_admin(user_id: int):
    owners = json.loads(get_global("admins", "[]") or "[]")
    owners = [int(x) for x in owners if int(x) != int(user_id)]
    set_global("admins", json.dumps(owners))


def list_admins() -> list[int]:
    return json.loads(get_global("admins", "[]") or "[]")


init_db()
