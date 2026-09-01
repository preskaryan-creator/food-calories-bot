# food-calories-bot

Telegram-бот для распознавания еды по фото и трекинга калорий с синхронизацией в FatSecret.

## Как это работает

1. Пользователь отправляет боту фото еды в Telegram.
2. Бот отправляет фото в Claude API (vision) — распознаёт блюдо и оценивает КБЖУ.
3. Бот ищет похожий продукт в FatSecret через `foods.search`.
4. Бот записывает результат в дневник питания пользователя через `food_entry.create` (FatSecret API, OAuth 1.0).

## Стек

- Python, [aiogram](https://docs.aiogram.dev/) — Telegram bot framework
- [Anthropic API](https://docs.anthropic.com/) (Claude, vision) — распознавание еды
- FatSecret Platform API (OAuth 1.0) — поиск продуктов и запись в дневник

## Структура проекта

```
main.py                 # точка входа бота
config.py               # загрузка переменных окружения
handlers/
    common.py            # /start и общие команды
    photo.py             # обработка фото еды
services/
    vision.py            # распознавание еды через Claude API
    fatsecret.py         # поиск продуктов и запись в дневник FatSecret
```

## Локальный запуск

1. Установить зависимости:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Скопировать `.env.example` в `.env` и заполнить переменные:

   ```bash
   cp .env.example .env
   ```

   - `TELEGRAM_BOT_TOKEN` — токен бота от [@BotFather](https://t.me/BotFather)
   - `ANTHROPIC_API_KEY` — ключ Anthropic API
   - `FATSECRET_CONSUMER_KEY`, `FATSECRET_CONSUMER_SECRET` — ключи приложения FatSecret Platform API

3. Запустить бота:

   ```bash
   python main.py
   ```
