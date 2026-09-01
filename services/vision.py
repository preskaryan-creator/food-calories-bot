"""Распознавание еды на фото через Anthropic (Claude) vision API."""

import base64
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic

import config

MODEL = "claude-sonnet-5"

# Допустимое расхождение между заявленной калорийностью и калориями,
# посчитанными из БЖУ (4/9/4 ккал на грамм белков/жиров/углеводов).
_CALORIE_MISMATCH_TOLERANCE = 0.35

_client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

_REPORT_FOOD_TOOL = {
    "name": "report_food",
    "description": (
        "Сообщить список отдельных продуктов/компонентов, распознанных на фото, "
        "с оценкой КБЖУ для каждого."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": (
                    "Каждый значимый продукт на фото — отдельным элементом "
                    "(например, 'гречка', 'куриная грудка гриль', 'салат из огурцов'), "
                    "а не одним обобщённым названием блюда."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Короткое конкретное название продукта на русском.",
                        },
                        "portion_grams": {
                            "type": "number",
                            "description": "Оценённый вес порции этого продукта, граммы.",
                        },
                        "calories": {"type": "number", "description": "Калорийность порции, ккал."},
                        "protein": {"type": "number", "description": "Белки, г."},
                        "fat": {"type": "number", "description": "Жиры, г."},
                        "carbs": {"type": "number", "description": "Углеводы, г."},
                    },
                    "required": ["name", "portion_grams", "calories", "protein", "fat", "carbs"],
                },
            },
        },
        "required": ["items"],
    },
}

_SYSTEM_PROMPT = (
    "Ты — эксперт по питанию. По фотографии еды определи каждый значимый продукт "
    "или компонент отдельно (например, гарнир, мясо/рыбу, соус, салат — каждый своим "
    "элементом), а не одно обобщённое название блюда целиком. Для каждого компонента "
    "оцени размер порции в граммах и рассчитай количество калорий, белков, жиров "
    "и углеводов. Давай наилучшую оценку, даже если не уверен на 100%. Ответь "
    "вызовом инструмента report_food."
)


@dataclass
class FoodItem:
    name: str
    portion_grams: float
    calories: float
    protein: float
    fat: float
    carbs: float


@dataclass
class FoodRecognitionResult:
    items: list[FoodItem]
    warnings: list[str] = field(default_factory=list)

    @property
    def is_suspicious(self) -> bool:
        return bool(self.warnings)


def _validate_item(item: FoodItem) -> list[str]:
    warnings = []

    if item.portion_grams <= 0 or item.calories < 0 or item.protein < 0 or item.fat < 0 or item.carbs < 0:
        warnings.append(f"«{item.name}»: отрицательные или нулевые значения там, где не должно быть.")
        return warnings

    if item.calories == 0:
        warnings.append(f"«{item.name}»: калорийность равна 0.")
        return warnings

    expected_calories = item.protein * 4 + item.fat * 9 + item.carbs * 4
    if expected_calories > 0:
        mismatch = abs(item.calories - expected_calories) / expected_calories
        if mismatch > _CALORIE_MISMATCH_TOLERANCE:
            warnings.append(
                f"«{item.name}»: калорийность ({item.calories} ккал) не сходится с БЖУ "
                f"(ожидалось ~{expected_calories:.0f} ккал)."
            )

    return warnings


async def recognize_food(image_bytes: bytes, media_type: str = "image/jpeg") -> FoodRecognitionResult:
    """Отправляет фото в Claude API и возвращает распознанные компоненты с оценкой КБЖУ.

    Результат не ретраится автоматически при подозрительных значениях — сомнительные
    элементы помечаются в `warnings`, а решение (показать пользователю как есть или
    попросить поправить вручную) остаётся за вызывающим кодом.
    """
    response = await _client.messages.create(
        model=MODEL,
        max_tokens=1536,
        system=_SYSTEM_PROMPT,
        tools=[_REPORT_FOOD_TOOL],
        tool_choice={"type": "tool", "name": "report_food"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": "Распознай еду на фото."},
                ],
            }
        ],
    )

    tool_use = next(block for block in response.content if block.type == "tool_use")
    items = [FoodItem(**raw_item) for raw_item in tool_use.input["items"]]

    warnings = []
    for item in items:
        warnings.extend(_validate_item(item))

    return FoodRecognitionResult(items=items, warnings=warnings)
