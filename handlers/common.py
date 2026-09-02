from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "Привет! Отправь фото еды, и я оценю КБЖУ и запишу в дневник питания.\n\n"
        "Перед этим привяжи свой аккаунт FatSecret командой /link_fatsecret."
    )
