"""Хранение access-токенов FatSecret (OAuth 1.0) для пользователей бота, по Telegram ID."""

from dataclasses import dataclass

import aiosqlite

from storage.db import DB_PATH


@dataclass
class FatSecretTokens:
    oauth_token: str
    oauth_token_secret: str


async def get_tokens(telegram_id: int) -> FatSecretTokens | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT oauth_token, oauth_token_secret FROM fatsecret_accounts WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        return None

    return FatSecretTokens(oauth_token=row[0], oauth_token_secret=row[1])


async def save_tokens(telegram_id: int, oauth_token: str, oauth_token_secret: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO fatsecret_accounts (telegram_id, oauth_token, oauth_token_secret)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                oauth_token = excluded.oauth_token,
                oauth_token_secret = excluded.oauth_token_secret,
                linked_at = datetime('now')
            """,
            (telegram_id, oauth_token, oauth_token_secret),
        )
        await db.commit()
