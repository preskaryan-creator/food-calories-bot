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
    confirming_grams = State()


def _parse_grams(text: str) -> float | None:
    cleaned = text.strip().lower().replace(",", ".")
    for suffix in ("гр", "г", "g"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
            break
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value > 0 else None


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
    await state.update_data(items=items, index=0, logged=0)

    await _advance(message, state)


async def _advance(message: Message, state: FSMContext) -> None:
    """Показывает подтверждение для текущего компонента или завершает сценарий."""
    data = await state.get_data()
    items = data["items"]
    index = data["index"]

    while index < len(items):
        item = items[index]
        candidates = await fatsecret.search_food(item["search_name_en"])
        if candidates:
            break
        await message.answer(f"Не нашёл «{item['name']}» в базе FatSecret, пропускаю.")
        index += 1
    else:
        logged = data.get("logged", 0)
        await state.clear()
        await message.answer(
            f"Готово! Занесено в дневник питания FatSecret: {logged} из {len(items)}."
        )
        return

    await state.set_state(FoodLogging.choosing_match)
    await state.update_data(index=index)

    translations = await vision.translate_to_russian([c.food_name for c in candidates])
    if len(translations) != len(candidates):
        translations = [c.food_name for c in candidates]

    builder = InlineKeyboardBuilder()
    for candidate, label in zip(candidates, translations):
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


async def _show_grams_prompt(
    message: Message,
    item: dict,
    grams: float,
    metric_amount: float,
    reference_units: float,
    calories_per_unit: float,
) -> None:
    number_of_units = (grams / metric_amount) * reference_units
    calories = calories_per_unit * number_of_units

    builder = InlineKeyboardBuilder()
    builder.button(text="Подтвердить", callback_data="fsgrams:confirm")
    builder.button(text="Пропустить", callback_data="fsgrams:skip")
    builder.adjust(1)

    await message.answer(
        f"«{item['name']}»: вес порции ~{grams:.0f} г (~{calories:.0f} ккал).\n"
        "Если вес на фото отличается от реального — пришлите точный вес в граммах, "
        "или нажмите «Подтвердить».",
        reply_markup=builder.as_markup(),
    )


async def _finalize_entry(
    message: Message,
    state: FSMContext,
    telegram_id: int,
    item: dict,
    index: int,
    food_id: str,
    serving_id: str,
    number_of_units: float,
    calories_per_unit: float,
    note: str = "",
) -> None:
    try:
        await fatsecret.add_food_entry(telegram_id, food_id, serving_id, number_of_units, entry_name=item["name"])
    except Exception:
        await message.answer(f"«{item['name']}»: не удалось записать в дневник FatSecret.")
        await state.set_state(FoodLogging.choosing_match)
        await state.update_data(index=index + 1)
    else:
        logged_calories = calories_per_unit * number_of_units
        await message.answer(f"«{item['name']}» записано в дневник: ~{logged_calories:.0f} ккал{note}.")
        data = await state.get_data()
        await state.set_state(FoodLogging.choosing_match)
        await state.update_data(index=index + 1, logged=data.get("logged", 0) + 1)

    await _advance(message, state)


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
        await state.update_data(index=index + 1)
        await _advance(callback.message, state)
        return

    food_id = choice
    try:
        servings = await fatsecret.get_food_servings(food_id)
        serving_choice = fatsecret.pick_serving_for_grams(servings, item["portion_grams"])
    except Exception:
        await callback.message.edit_text(f"«{item['name']}»: не удалось получить данные о продукте.")
        await state.update_data(index=index + 1)
        await _advance(callback.message, state)
        return

    await callback.message.edit_reply_markup(reply_markup=None)

    if not serving_choice.matched_by_grams:
        await _finalize_entry(
            callback.message,
            state,
            callback.from_user.id,
            item,
            index,
            food_id,
            serving_choice.serving.serving_id,
            serving_choice.number_of_units,
            serving_choice.serving.calories_per_unit,
            note=" (порция подобрана приблизительно)",
        )
        return

    grams = item["portion_grams"]
    await state.set_state(FoodLogging.confirming_grams)
    await state.update_data(
        pending={
            "food_id": food_id,
            "serving_id": serving_choice.serving.serving_id,
            "metric_amount": serving_choice.serving.metric_amount,
            "reference_units": serving_choice.serving.reference_units,
            "calories_per_unit": serving_choice.serving.calories_per_unit,
            "grams": grams,
        }
    )
    await _show_grams_prompt(
        callback.message,
        item,
        grams,
        serving_choice.serving.metric_amount,
        serving_choice.serving.reference_units,
        serving_choice.serving.calories_per_unit,
    )


@router.message(FoodLogging.confirming_grams, F.text)
async def handle_grams_text(message: Message, state: FSMContext) -> None:
    grams = _parse_grams(message.text)
    if grams is None:
        await message.answer("Не понял вес. Пришлите число в граммах, например 150.")
        return

    data = await state.get_data()
    pending = data["pending"]
    pending["grams"] = grams
    await state.update_data(pending=pending)

    item = data["items"][data["index"]]
    await _show_grams_prompt(
        message, item, grams, pending["metric_amount"], pending["reference_units"], pending["calories_per_unit"]
    )


@router.callback_query(FoodLogging.confirming_grams, F.data == "fsgrams:confirm")
async def handle_grams_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    data = await state.get_data()
    pending = data["pending"]
    index = data["index"]
    item = data["items"][index]

    number_of_units = (pending["grams"] / pending["metric_amount"]) * pending["reference_units"]
    await _finalize_entry(
        callback.message,
        state,
        callback.from_user.id,
        item,
        index,
        pending["food_id"],
        pending["serving_id"],
        number_of_units,
        pending["calories_per_unit"],
    )


@router.callback_query(FoodLogging.confirming_grams, F.data == "fsgrams:skip")
async def handle_grams_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    data = await state.get_data()
    index = data["index"]
    item = data["items"][index]

    await callback.message.answer(f"«{item['name']}»: пропущено.")
    await state.set_state(FoodLogging.choosing_match)
    await state.update_data(index=index + 1)
    await _advance(callback.message, state)
