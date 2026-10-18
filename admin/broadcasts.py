import asyncio

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database
from admin.common import AdminFilter
from states import AdminBroadcastStates

router = Router(name="admin_broadcasts")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data="ab:send", style=ButtonStyle.SUCCESS),
                InlineKeyboardButton(text="❌ Отмена", callback_data="ab:cancel", style=ButtonStyle.DANGER),
            ]
        ]
    )


@router.callback_query(F.data == "admin:broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminBroadcastStates.waiting_content)
    await callback.message.edit_text(
        "📢 Отправьте сообщение для рассылки (текст, фото, видео или документ, "
        "с подписью и обычной Telegram-разметкой)."
    )
    await callback.answer()


@router.message(AdminBroadcastStates.waiting_content)
async def broadcast_preview(message: Message, state: FSMContext) -> None:
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
    await state.set_state(AdminBroadcastStates.confirming)
    await message.answer(
        "📢 Предпросмотр рассылки выше.\n\nОтправить всем пользователям?", reply_markup=_confirm_kb()
    )


@router.callback_query(AdminBroadcastStates.confirming, F.data == "ab:cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.")
    await callback.answer()


async def _run_broadcast(bot, admin_id: int, chat_id: int, message_id: int, notify_chat_id: int) -> None:
    user_ids = await database.all_user_ids(only_active=True)
    sent = failed = blocked = 0
    for user_id in user_ids:
        for attempt in range(3):
            try:
                await bot.copy_message(chat_id=user_id, from_chat_id=chat_id, message_id=message_id)
                sent += 1
            except TelegramRetryAfter as exc:
                # flood limit - wait as Telegram asks and retry this user
                if attempt < 2:
                    await asyncio.sleep(exc.retry_after + 1)
                    continue
                failed += 1
            except TelegramForbiddenError:
                blocked += 1
            except Exception:
                failed += 1
            break
        await asyncio.sleep(0.05)

    await database.add_log(
        "admin", "broadcast", {"sent": sent, "failed": failed, "blocked": blocked}, admin_id=admin_id
    )
    await bot.send_message(
        notify_chat_id,
        f"📊 Рассылка завершена\n\n✅ Отправлено: {sent}\n❌ Ошибок: {failed}\n🚫 Заблокировали бота: {blocked}",
    )


@router.callback_query(AdminBroadcastStates.confirming, F.data == "ab:send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.message.edit_text("⏳ Рассылка запущена, отчёт придёт по завершении...")
    await callback.answer()
    asyncio.create_task(
        _run_broadcast(
            callback.bot, callback.from_user.id, data["chat_id"], data["message_id"], callback.message.chat.id
        )
    )
