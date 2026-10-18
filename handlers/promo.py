from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.user import back_kb, cancel_kb
from services.promo_service import PromoError, activate_promo
from states import PromoStates

router = Router(name="promo")


@router.callback_query(F.data == "profile:promo")
async def promo_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PromoStates.waiting_code)
    await state.update_data(prompt_chat_id=callback.message.chat.id, prompt_message_id=callback.message.message_id)
    await callback.message.edit_text("🎟 Введите промокод:", reply_markup=cancel_kb("profile:reopen"))
    await callback.answer()


@router.message(PromoStates.waiting_code)
async def promo_receive(message: Message, state: FSMContext) -> None:
    code = (message.text or "").strip()
    if not code:
        await message.answer("❌ Отправьте промокод текстом.")
        return
    data = await state.get_data()
    await state.clear()

    try:
        reward = await activate_promo(message.from_user.id, code)
        result_text = f"✅ Промокод активирован!\n\n🎁 Вы получили: {reward:g} ⭐"
    except PromoError as exc:
        result_text = f"❌ {exc}"

    prompt_chat_id = data.get("prompt_chat_id")
    prompt_message_id = data.get("prompt_message_id")
    try:
        await message.delete()
    except Exception:
        pass

    if prompt_chat_id and prompt_message_id:
        try:
            await message.bot.edit_message_text(
                result_text,
                chat_id=prompt_chat_id,
                message_id=prompt_message_id,
                reply_markup=back_kb("profile:reopen"),
            )
            return
        except Exception:
            pass
    await message.answer(result_text, reply_markup=back_kb("profile:reopen"))
