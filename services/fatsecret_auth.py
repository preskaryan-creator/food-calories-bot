"""OAuth-механизмы FatSecret Platform API.

- OAuth 2.0 (client_credentials, scope=basic) — для не привязанных к пользователю
  методов вроде foods.search и food.get.
- OAuth 1.0 three-legged (HMAC-SHA1, через requests_oauthlib) — для привязки аккаунта
  пользователя и для food_entry.create, которая пишет в его личный дневник.

Все запросы requests_oauthlib синхронные, поэтому оборачиваются в asyncio.to_thread,
чтобы не блокировать event loop aiogram.
"""

import asyncio
import time

import httpx
from requests_oauthlib import OAuth1Session

import config

REST_ENDPOINT = "https://platform.fatsecret.com/rest/server.api"

_OAUTH2_TOKEN_URL = "https://oauth.fatsecret.com/connect/token"
_REQUEST_TOKEN_URL = "https://authentication.fatsecret.com/oauth/request_token"
_AUTHORIZE_URL = "https://authentication.fatsecret.com/oauth/authorize"
_ACCESS_TOKEN_URL = "https://authentication.fatsecret.com/oauth/access_token"

_oauth2_token: str | None = None
_oauth2_token_expires_at: float = 0.0


async def get_oauth2_token() -> str:
    """Возвращает bearer-токен OAuth 2.0 (scope=basic), кэшируя его на время жизни (24ч)."""
    global _oauth2_token, _oauth2_token_expires_at

    if _oauth2_token and time.monotonic() < _oauth2_token_expires_at:
        return _oauth2_token

    async with httpx.AsyncClient() as client:
        response = await client.post(
            _OAUTH2_TOKEN_URL,
            auth=(config.FATSECRET_CLIENT_ID, config.FATSECRET_CLIENT_SECRET),
            data={"grant_type": "client_credentials", "scope": "basic"},
        )
        response.raise_for_status()
        payload = response.json()

    _oauth2_token = payload["access_token"]
    _oauth2_token_expires_at = time.monotonic() + payload["expires_in"] - 60
    return _oauth2_token


def _oauth1_session(
    resource_owner_key: str | None = None,
    resource_owner_secret: str | None = None,
    callback_uri: str | None = None,
) -> OAuth1Session:
    return OAuth1Session(
        client_key=config.FATSECRET_CONSUMER_KEY,
        client_secret=config.FATSECRET_CONSUMER_SECRET,
        resource_owner_key=resource_owner_key,
        resource_owner_secret=resource_owner_secret,
        callback_uri=callback_uri,
        signature_method="HMAC-SHA1",
    )


async def start_account_link() -> tuple[str, str, str]:
    """Запрашивает request token (oauth_callback=oob) и возвращает ссылку на авторизацию.

    Возвращает (authorize_url, oauth_token, oauth_token_secret). oauth_token и
    oauth_token_secret нужно временно сохранить (например, в FSM-состоянии) до момента,
    когда пользователь пришлёт PIN — они понадобятся для finish_account_link.
    """
    session = _oauth1_session(callback_uri="oob")

    token = await asyncio.to_thread(session.fetch_request_token, _REQUEST_TOKEN_URL)

    authorize_url = f"{_AUTHORIZE_URL}?oauth_token={token['oauth_token']}"
    return authorize_url, token["oauth_token"], token["oauth_token_secret"]


async def finish_account_link(oauth_token: str, oauth_token_secret: str, pin: str) -> tuple[str, str]:
    """Обменивает request token + PIN (oauth_verifier) на постоянный access token пользователя.

    Возвращает (access_token, access_token_secret) — их нужно сохранить в storage,
    привязанными к Telegram ID пользователя.
    """
    session = _oauth1_session(resource_owner_key=oauth_token, resource_owner_secret=oauth_token_secret)

    token = await asyncio.to_thread(session.fetch_access_token, _ACCESS_TOKEN_URL, verifier=pin)

    return token["oauth_token"], token["oauth_token_secret"]


async def signed_user_request(access_token: str, access_token_secret: str, params: dict) -> dict:
    """Выполняет подписанный OAuth 1.0 запрос от имени пользователя (например, food_entry.create)."""
    session = _oauth1_session(resource_owner_key=access_token, resource_owner_secret=access_token_secret)

    def _request() -> dict:
        response = session.post(REST_ENDPOINT, data={**params, "format": "json"})
        response.raise_for_status()
        return response.json()

    return await asyncio.to_thread(_request)
