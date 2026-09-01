from aiogram import F, Router
from aiogram.types import Message

from services import fatsecret, vision

router = Router()


@router.message(F.photo)
async def handle_photo(message: Message) -> None:
    """Принимает фото еды, распознаёт через vision-сервис и пишет в FatSecret.

    TODO: скачать фото, вызвать vision.recognize_food, найти продукт через
    fatsecret.search_food и записать через fatsecret.add_food_entry.
    """
    await message.answer("Обработка фото пока не реализована.")
