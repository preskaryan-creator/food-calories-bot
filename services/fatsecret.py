"""Поиск продуктов и запись в дневник питания через FatSecret Platform API.

foods.search и food.get идут через OAuth 2.0 (не привязаны к пользователю).
food_entry.create требует food_id + serving_id (в бесплатном тарифе нет способа
записать полностью произвольные калории/БЖУ — см. обсуждение) и подписывается
OAuth 1.0 от имени привязанного аккаунта пользователя.
"""

import httpx
from dataclasses import dataclass

from services import fatsecret_auth
from storage import fatsecret_tokens


def _as_list(value):
    """FatSecret отдаёт единственный результат объектом, а не списком из одного элемента."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


@dataclass
class FatSecretFoodMatch:
    food_id: str
    food_name: str
    brand_name: str | None
    description: str


@dataclass
class FatSecretServing:
    serving_id: str
    description: str
    metric_amount: float | None
    metric_unit: str | None
    calories: float
    protein: float
    fat: float
    carbs: float


@dataclass
class ServingChoice:
    serving: FatSecretServing
    number_of_units: float
    matched_by_grams: bool


async def search_food(query: str, max_results: int = 3) -> list[FatSecretFoodMatch]:
    """Ищет продукты в FatSecret по названию (foods.search)."""
    token = await fatsecret_auth.get_oauth2_token()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            fatsecret_auth.REST_ENDPOINT,
            params={
                "method": "foods.search",
                "search_expression": query,
                "max_results": max_results,
                "format": "json",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        payload = response.json()

    raw_foods = _as_list(payload.get("foods", {}).get("food"))

    return [
        FatSecretFoodMatch(
            food_id=food["food_id"],
            food_name=food["food_name"],
            brand_name=food.get("brand_name"),
            description=food.get("food_description", ""),
        )
        for food in raw_foods
    ]


async def get_food_servings(food_id: str) -> list[FatSecretServing]:
    """Возвращает список доступных порций (serving) для продукта (food.get)."""
    token = await fatsecret_auth.get_oauth2_token()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            fatsecret_auth.REST_ENDPOINT,
            params={"method": "food.get.v4", "food_id": food_id, "format": "json"},
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        payload = response.json()

    raw_servings = _as_list(payload.get("food", {}).get("servings", {}).get("serving"))

    servings = []
    for raw in raw_servings:
        metric_unit = raw.get("metric_serving_unit")
        metric_amount = raw.get("metric_serving_amount")
        servings.append(
            FatSecretServing(
                serving_id=raw["serving_id"],
                description=raw.get("serving_description", ""),
                metric_amount=float(metric_amount) if metric_amount is not None else None,
                metric_unit=metric_unit,
                calories=float(raw["calories"]),
                protein=float(raw["protein"]),
                fat=float(raw["fat"]),
                carbs=float(raw["carbohydrate"]),
            )
        )
    return servings


def pick_serving_for_grams(servings: list[FatSecretServing], target_grams: float) -> ServingChoice:
    """Подбирает порцию, ближайшую по граммовке к оценённому весу компонента.

    Предпочитает порции, заданные в граммах (metric_unit == "g") — тогда количество
    порций масштабируется точно под target_grams. Если таких нет, берёт первую
    доступную порцию с number_of_units=1 и помечает matched_by_grams=False, чтобы
    вызывающий код мог предупредить пользователя о возможной неточности.
    """
    gram_servings = [s for s in servings if s.metric_unit == "g" and s.metric_amount]

    if gram_servings:
        serving = min(gram_servings, key=lambda s: abs(s.metric_amount - target_grams))
        number_of_units = target_grams / serving.metric_amount
        return ServingChoice(serving=serving, number_of_units=number_of_units, matched_by_grams=True)

    serving = servings[0]
    return ServingChoice(serving=serving, number_of_units=1.0, matched_by_grams=False)


async def add_food_entry(
    telegram_id: int,
    food_id: str,
    serving_id: str,
    number_of_units: float,
    entry_name: str,
    meal: str = "other",
) -> None:
    """Записывает продукт в дневник питания пользователя (food_entry.create).

    Требует, чтобы пользователь уже привязал аккаунт FatSecret (см. fatsecret_auth
    и storage.fatsecret_tokens) — иначе поднимает RuntimeError.
    """
    tokens = await fatsecret_tokens.get_tokens(telegram_id)
    if tokens is None:
        raise RuntimeError("Аккаунт FatSecret не привязан для этого пользователя.")

    await fatsecret_auth.signed_user_request(
        tokens.oauth_token,
        tokens.oauth_token_secret,
        {
            "method": "food_entry.create",
            "food_id": food_id,
            "serving_id": serving_id,
            "number_of_units": number_of_units,
            "meal": meal,
            "food_entry_name": entry_name,
        },
    )
