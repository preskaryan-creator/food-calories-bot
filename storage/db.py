"""Подключение к SQLite и инициализация схемы."""

from pathlib import Path

import aiosqlite

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bot.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fatsecret_accounts (
    telegram_id INTEGER PRIMARY KEY,
    oauth_token TEXT NOT NULL,
    oauth_token_secret TEXT NOT NULL,
    linked_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
