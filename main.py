import asyncio
import logging

from aiogram import Bot, Dispatcher

import config
from handlers import router


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
