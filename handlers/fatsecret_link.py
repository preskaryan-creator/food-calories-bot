"""Привязка аккаунта FatSecret: /link_fatsecret -> ссылка на авторизацию -> PIN -> access token."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from services import fatsecret_auth
from storage import fatsecret_tokens

router = Router()


class FatSecretLink(StatesGroup):
    waiting_for_pin = State()


@router.message(Command("link_fatsecret"))
async def start_link(message: Message, state: FSMContext) -> None:
    authorize_url, oauth_token, oauth_token_secret = await fatsecret_auth.start_account_link()

    await state.set_state(FatSecretLink.waiting_for_pin)
    await state.update_data(oauth_token=oauth_token, oauth_token_secret=oauth_token_secret)

    await message.answer(
        "Перейдите по ссылке, войдите в свой аккаунт FatSecret и разрешите доступ:\n"
        f"{authorize_url}\n\n"
        "FatSecret покажет PIN-код — пришлите его следующим сообщением.\n"
        "Чтобы отменить, отправьте /cancel."
    )


@router.message(Command("cancel"), FatSecretLink.waiting_for_pin)
async def cancel_link(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Привязка аккаунта отменена.")


@router.message(FatSecretLink.waiting_for_pin, F.text)
async def finish_link(message: Message, state: FSMContext) -> None:
    pin = message.text.strip()
    data = await state.get_data()

    try:
        access_token, access_token_secret = await fatsecret_auth.finish_account_link(
            data["oauth_token"], data["oauth_token_secret"], pin
        )
    except Exception:
        await message.answer(
            "Не получилось привязать аккаунт — возможно, PIN введён неверно или ссылка "
            "устарела. Начните заново: /link_fatsecret"
        )
        await state.clear()
        return

    await fatsecret_tokens.save_tokens(message.from_user.id, access_token, access_token_secret)
    await state.clear()
    await message.answer("Аккаунт FatSecret успешно привязан.")
