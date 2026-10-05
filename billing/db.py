"""SQLite persistence for users, sessions, magic links, subscriptions."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

_LOCK = threading.Lock()
_DB_PATH = Path(os.environ.get("AE_BILLING_DB", Path(__file__).resolve().parent.parent / "billing.db"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def db():
    with _LOCK:
        con = _connect()
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def init_db():
    with db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT UNIQUE,
              telegram_id TEXT UNIQUE,
              telegram_username TEXT,
              display_name TEXT,
              created_at TEXT NOT NULL,
              last_login_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
              token TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS magic_links (
              token TEXT PRIMARY KEY,
              email TEXT NOT NULL,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              used_at TEXT
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              plan TEXT NOT NULL,
              status TEXT NOT NULL,
              paystack_reference TEXT UNIQUE,
              amount_cents INTEGER,
              currency TEXT DEFAULT 'ZAR',
              started_at TEXT,
              expires_at TEXT,
              created_at TEXT NOT NULL,
              raw_json TEXT,
              FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_subs_user ON subscriptions(user_id);
            CREATE INDEX IF NOT EXISTS idx_subs_status ON subscriptions(status);
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            """
        )


def upsert_email_user(email: str, display_name: str | None = None) -> int:
    email = email.strip().lower()
    now = _iso()
    with db() as con:
        row = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if row:
            con.execute(
                "UPDATE users SET last_login_at=?, display_name=COALESCE(?, display_name) WHERE id=?",
                (now, display_name, row["id"]),
            )
            return int(row["id"])
        cur = con.execute(
            "INSERT INTO users(email, display_name, created_at, last_login_at) VALUES (?,?,?,?)",
            (email, display_name or email.split("@")[0], now, now),
        )
        return int(cur.lastrowid)


def upsert_telegram_user(telegram_id: str, username: str | None = None, display_name: str | None = None) -> int:
    telegram_id = str(telegram_id).strip()
    now = _iso()
    with db() as con:
        row = con.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if row:
            con.execute(
                "UPDATE users SET last_login_at=?, telegram_username=COALESCE(?, telegram_username), "
                "display_name=COALESCE(?, display_name) WHERE id=?",
                (now, username, display_name, row["id"]),
            )
            return int(row["id"])
        cur = con.execute(
            "INSERT INTO users(telegram_id, telegram_username, display_name, created_at, last_login_at) "
            "VALUES (?,?,?,?,?)",
            (telegram_id, username, display_name or username or f"tg:{telegram_id}", now, now),
        )
        return int(cur.lastrowid)


def get_user(user_id: int) -> dict | None:
    with db() as con:
        row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def create_session(user_id: int, days: int = 30) -> str:
    import secrets
    token = secrets.token_urlsafe(32)
    now = _utc_now()
    with db() as con:
        con.execute(
            "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
            (token, user_id, _iso(now), _iso(now + timedelta(days=days))),
        )
    return token


def session_user(token: str | None) -> dict | None:
    if not token:
        return None
    now = _iso()
    with db() as con:
        row = con.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token=? AND s.expires_at > ?",
            (token, now),
        ).fetchone()
        return dict(row) if row else None


def destroy_session(token: str | None):
    if not token:
        return
    with db() as con:
        con.execute("DELETE FROM sessions WHERE token=?", (token,))


def create_magic_link(email: str, hours: int = 2) -> str:
    import secrets
    email = email.strip().lower()
    token = secrets.token_urlsafe(24)
    now = _utc_now()
    with db() as con:
        con.execute(
            "INSERT INTO magic_links(token, email, created_at, expires_at) VALUES (?,?,?,?)",
            (token, email, _iso(now), _iso(now + timedelta(hours=hours))),
        )
    return token


def consume_magic_link(token: str) -> str | None:
    """Return email if valid unused link, else None."""
    now = _iso()
    with db() as con:
        row = con.execute(
            "SELECT * FROM magic_links WHERE token=? AND used_at IS NULL AND expires_at > ?",
            (token, now),
        ).fetchone()
        if not row:
            return None
        con.execute("UPDATE magic_links SET used_at=? WHERE token=?", (now, token))
        return row["email"]


def active_paid_count(now: datetime | None = None) -> int:
    now_s = _iso(now)
    with db() as con:
        row = con.execute(
            "SELECT COUNT(DISTINCT user_id) AS n FROM subscriptions "
            "WHERE status='active' AND (expires_at IS NULL OR expires_at > ?)",
            (now_s,),
        ).fetchone()
        return int(row["n"] if row else 0)


def user_active_subscription(user_id: int, now: datetime | None = None) -> dict | None:
    now_s = _iso(now)
    with db() as con:
        row = con.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND status='active' "
            "AND (expires_at IS NULL OR expires_at > ?) ORDER BY expires_at DESC LIMIT 1",
            (user_id, now_s),
        ).fetchone()
        return dict(row) if row else None


def create_pending_subscription(user_id: int, plan: str, reference: str, amount_cents: int) -> int:
    with db() as con:
        cur = con.execute(
            "INSERT INTO subscriptions(user_id, plan, status, paystack_reference, amount_cents, "
            "currency, created_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, plan, "pending", reference, amount_cents, "ZAR", _iso()),
        )
        return int(cur.lastrowid)


def activate_subscription(reference: str, plan: str, days: int, raw: dict | None = None) -> dict | None:
    now = _utc_now()
    expires = now + timedelta(days=days)
    with db() as con:
        row = con.execute(
            "SELECT * FROM subscriptions WHERE paystack_reference=?", (reference,)
        ).fetchone()
        if not row:
            return None
        con.execute(
            "UPDATE subscriptions SET status='active', plan=?, started_at=?, expires_at=?, raw_json=? "
            "WHERE paystack_reference=?",
            (plan, _iso(now), _iso(expires), json.dumps(raw or {}), reference),
        )
        row2 = con.execute(
            "SELECT * FROM subscriptions WHERE paystack_reference=?", (reference,)
        ).fetchone()
        return dict(row2) if row2 else None


def get_subscription_by_reference(reference: str) -> dict | None:
    with db() as con:
        row = con.execute(
            "SELECT * FROM subscriptions WHERE paystack_reference=?", (reference,)
        ).fetchone()
        return dict(row) if row else None


# Ensure schema on import
init_db()
