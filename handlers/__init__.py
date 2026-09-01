from aiogram import Router

from . import common, photo

router = Router()
router.include_router(common.router)
router.include_router(photo.router)
