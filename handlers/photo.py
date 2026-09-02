"""Обработка фото еды: распознавание -> подтверждение матчинга с FatSecret -> запись в дневник."""

import dataclasses

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services import fatsecret, vision
from storage import fatsecret_tokens

router = Router()


class FoodLogging(StatesGroup):
    choosing_match = State()


@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext) -> None:
    if await fatsecret_tokens.get_tokens(message.from_user.id) is None:
        await message.answer("Сначала привяжите аккаунт FatSecret: /link_fatsecret")
        return

    await message.answer("Распознаю еду на фото...")

    photo_file = await message.bot.get_file(message.photo[-1].file_id)
    buffer = await message.bot.download_file(photo_file.file_path)

    try:
        result = await vision.recognize_food(buffer.read())
    except Exception:
        await message.answer("Не удалось распознать фото, попробуйте другое.")
        return

    if not result.items:
        await message.answer("Не удалось найти еду на фото.")
        return

    if result.warnings:
        warnings_text = "\n".join(f"⚠️ {w}" for w in result.warnings)
        await message.answer(f"Есть сомнения в оценке:\n{warnings_text}")

    items = [dataclasses.asdict(item) for item in result.items]
    await state.set_state(FoodLogging.choosing_match)
    await state.update_data(items=items, index=0)

    await _advance(message, state)


async def _advance(message: Message, state: FSMContext) -> None:
    """Показывает подтверждение для текущего компонента или завершает сценарий."""
    data = await state.get_data()
    items = data["items"]
    index = data["index"]

    while index < len(items):
        item = items[index]
        candidates = await fatsecret.search_food(item["name"])
        if candidates:
            break
        await message.answer(f"Не нашёл «{item['name']}» в базе FatSecret, пропускаю.")
        index += 1
    else:
        await state.clear()
        await message.answer("Готово — все компоненты обработаны.")
        return

    await state.update_data(index=index)

    builder = InlineKeyboardBuilder()
    for candidate in candidates:
        label = candidate.food_name
        if candidate.brand_name:
            label = f"{label} ({candidate.brand_name})"
        builder.button(text=label[:60], callback_data=f"fsmatch:{candidate.food_id}")
    builder.button(text="Пропустить", callback_data="fsmatch:skip")
    builder.adjust(1)

    await message.answer(
        f"«{item['name']}» (~{item['portion_grams']:.0f} г, ~{item['calories']:.0f} ккал по оценке).\n"
        "Выберите подходящий продукт из FatSecret:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(FoodLogging.choosing_match, F.data.startswith("fsmatch:"))
async def handle_match_choice(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    data = await state.get_data()
    items = data["items"]
    index = data["index"]
    item = items[index]

    choice = callback.data.removeprefix("fsmatch:")

    if choice == "skip":
        await callback.message.edit_text(f"«{item['name']}»: пропущено.")
    else:
        food_id = choice
        try:
            servings = await fatsecret.get_food_servings(food_id)
            serving_choice = fatsecret.pick_serving_for_grams(servings, item["portion_grams"])
            await fatsecret.add_food_entry(
                callback.from_user.id,
                food_id,
                serving_choice.serving.serving_id,
                serving_choice.number_of_units,
                entry_name=item["name"],
            )
        except Exception:
            await callback.message.edit_text(f"«{item['name']}»: не удалось записать в дневник FatSecret.")
        else:
            logged_calories = serving_choice.serving.calories * serving_choice.number_of_units
            note = "" if serving_choice.matched_by_grams else " (порция подобрана приблизительно)"
            await callback.message.edit_text(f"«{item['name']}» записано: ~{logged_calories:.0f} ккал{note}.")

    await state.update_data(index=index + 1)
    await _advance(callback.message, state)
