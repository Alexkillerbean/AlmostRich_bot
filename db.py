"""
Слой данных бота: SQLite через aiosqlite.

Храним только идентификатор пользователя и служебные даты —
доходы и расходы живут в приложении, здесь их нет.
"""
from __future__ import annotations  # str | None работает на Python < 3.10

import os
from datetime import datetime, timezone

import aiosqlite

# bothost (и подобные) задают DATA_DIR как постоянный том; локально — рядом с кодом.
DB_PATH = os.path.join(os.getenv("DATA_DIR", "."), "bot.db")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init() -> None:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
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
