"""
Слой данных бота: SQLite через aiosqlite.

Храним только идентификатор пользователя и служебные даты —
никаких доходов и расходов, это живёт в приложении.
"""
import os
import aiosqlite
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "bot.db")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init() -> None:
    async with aiosqlite.connect(DB_PATH) as con:
        await con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id       INTEGER PRIMARY KEY,
                username      TEXT,
                first_seen    TEXT NOT NULL,
                subscribed_at TEXT,
                last_seen     TEXT NOT NULL
            )
        """)
        await con.commit()


async def touch_user(user_id: int, username: str | None) -> None:
    """Зарегистрировать пользователя при первом /start."""
    now = _now()
    async with aiosqlite.connect(DB_PATH) as con:
        await con.execute(
            """INSERT INTO users (user_id, username, first_seen, last_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET username = excluded.username""",
            (user_id, username, now, now),
        )
        await con.commit()


async def mark_subscribed(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as con:
        await con.execute(
            """UPDATE users SET subscribed_at = ?
               WHERE user_id = ? AND subscribed_at IS NULL""",
            (_now(), user_id),
        )
        await con.commit()


async def update_last_seen(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as con:
        await con.execute("UPDATE users SET last_seen = ? WHERE user_id = ?",
                          (_now(), user_id))
        await con.commit()
