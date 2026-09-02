from aiogram import Router

from . import common, fatsecret_link, photo

router = Router()
router.include_router(common.router)
router.include_router(fatsecret_link.router)
router.include_router(photo.router)
