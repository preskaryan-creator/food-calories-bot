"""Интеграция с FatSecret Platform API (OAuth 1.0): поиск продуктов и запись в дневник."""

from dataclasses import dataclass


@dataclass
class FatSecretFood:
    food_id: str
    name: str
    calories: float
    protein: float
    fat: float
    carbs: float


async def search_food(query: str) -> list[FatSecretFood]:
    """Ищет продукт в FatSecret по названию (foods.search).

    TODO: реализовать OAuth 1.0 запрос к FatSecret API.
    """
    raise NotImplementedError


async def add_food_entry(user_id: int, food: FatSecretFood) -> None:
    """Записывает продукт в дневник питания пользователя (food_entry.create).

    TODO: реализовать OAuth 1.0 запрос к FatSecret API.
    """
    raise NotImplementedError
