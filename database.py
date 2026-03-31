import sqlite3
import time
from config import RANKS

DB_PATH = "gerda.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id             INTEGER PRIMARY KEY,
                username            TEXT,
                full_name           TEXT,
                nickname            TEXT,
                nickname_expires_at INTEGER DEFAULT 0,
                messages            INTEGER DEFAULT 0,
                warnings            INTEGER DEFAULT 0,
                joined_at           INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS spam_tracker (
                user_id      INTEGER PRIMARY KEY,
                count        INTEGER DEFAULT 0,
                window_start INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS chat_activity (
                id               INTEGER PRIMARY KEY,
                last_message_at  INTEGER DEFAULT 0
            );
        """)
        # Добавляем колонку если её нет (для существующих БД)
        try:
            conn.execute("ALTER TABLE users ADD COLUMN nickname_expires_at INTEGER DEFAULT 0")
            conn.commit()
        except Exception:
            pass  # колонка уже есть

        conn.execute("""
            INSERT OR IGNORE INTO chat_activity (id, last_message_at)
            VALUES (1, ?)
        """, (int(time.time()),))
        conn.commit()


# ───── Пользователи ─────

def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()


def upsert_user(user_id: int, username: str, full_name: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                full_name = excluded.full_name
        """, (user_id, username, full_name))
        conn.commit()


def increment_messages(user_id: int) -> int:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET messages = messages + 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        row = conn.execute(
            "SELECT messages FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["messages"] if row else 0


def add_warning(user_id: int) -> int:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET warnings = warnings + 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        row = conn.execute(
            "SELECT warnings FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["warnings"] if row else 0


def reset_warnings(user_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET warnings = 0 WHERE user_id = ?", (user_id,)
        )
        conn.commit()


def set_nickname(user_id: int, nickname: str, expires_at: int = 0):
    """Устанавливает прозвище. expires_at=0 — постоянное, иначе временное."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET nickname = ?, nickname_expires_at = ? WHERE user_id = ?",
            (nickname, expires_at, user_id)
        )
        conn.commit()


def set_shame_nickname(user_id: int, nickname: str, hours: int = 6):
    """Позорное прозвище на N часов."""
    expires_at = int(time.time()) + hours * 3600
    set_nickname(user_id, nickname, expires_at)


def get_active_nickname(row) -> str | None:
    """Возвращает прозвище если оно ещё активно, иначе None."""
    if not row["nickname"]:
        return None
    expires_at = row["nickname_expires_at"] or 0
    # expires_at == 0 означает постоянное прозвище
    if expires_at == 0 or int(time.time()) < expires_at:
        return row["nickname"]
    return None


def expire_shame_nicknames():
    """Сбрасывает истёкшие позорные прозвища."""
    now = int(time.time())
    with get_conn() as conn:
        conn.execute("""
            UPDATE users
            SET nickname = NULL, nickname_expires_at = 0
            WHERE nickname_expires_at > 0 AND nickname_expires_at <= ?
        """, (now,))
        conn.commit()


def get_top_users(limit: int = 10):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users ORDER BY messages DESC LIMIT ?", (limit,)
        ).fetchall()


# ───── Ранги ─────

def get_rank(messages: int) -> str:
    rank = RANKS[0][1]
    for threshold, title in RANKS:
        if messages >= threshold:
            rank = title
    return rank


def get_next_rank(messages: int):
    for i, (threshold, title) in enumerate(RANKS):
        if messages < threshold:
            return title, threshold - messages
    return None, 0


# ───── Антиспам ─────

def check_spam(user_id: int, max_msgs: int, interval: int) -> bool:
    now = int(time.time())
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM spam_tracker WHERE user_id = ?", (user_id,)
        ).fetchone()

        if not row:
            conn.execute(
                "INSERT INTO spam_tracker (user_id, count, window_start) VALUES (?, 1, ?)",
                (user_id, now)
            )
            conn.commit()
            return False

        if now - row["window_start"] > interval:
            conn.execute(
                "UPDATE spam_tracker SET count = 1, window_start = ? WHERE user_id = ?",
                (now, user_id)
            )
            conn.commit()
            return False

        new_count = row["count"] + 1
        conn.execute(
            "UPDATE spam_tracker SET count = ? WHERE user_id = ?",
            (new_count, user_id)
        )
        conn.commit()
        return new_count > max_msgs


# ───── Активность чата ─────

def update_chat_activity():
    with get_conn() as conn:
        conn.execute(
            "UPDATE chat_activity SET last_message_at = ? WHERE id = 1",
            (int(time.time()),)
        )
        conn.commit()


def get_last_activity() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT last_message_at FROM chat_activity WHERE id = 1"
        ).fetchone()
        return row["last_message_at"] if row else 0
