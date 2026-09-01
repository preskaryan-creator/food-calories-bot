"""Распознавание еды на фото через Anthropic (Claude) vision API."""

from dataclasses import dataclass


@dataclass
class FoodRecognitionResult:
    name: str
    calories: float
    protein: float
    fat: float
    carbs: float


async def recognize_food(image_bytes: bytes) -> FoodRecognitionResult:
    """Отправляет фото в Claude API и возвращает распознанное блюдо с оценкой КБЖУ.

    TODO: реализовать вызов Anthropic API и промпт для распознавания.
    """
    raise NotImplementedError
