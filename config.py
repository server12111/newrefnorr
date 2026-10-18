import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

SUBGRAM_TOKEN = os.getenv("SUBGRAM_TOKEN", "")
FLYER_TOKEN = os.getenv("FLYER_TOKEN", "")
TGRASS_TOKEN = os.getenv("TGRASS_TOKEN", "")
BOTOHUB_TOKEN = os.getenv("BOTOHUB_TOKEN", "")
TRAFFY_TOKEN = os.getenv("TRAFFY_TOKEN", "")
AXIONNA_TOKEN = os.getenv("AXIONNA_TOKEN", "")

DB_PATH = os.getenv("DB_PATH", "bot.db")
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", os.path.join("logs", "bot.log"))

# Default values, overridable at runtime via admin panel -> settings table.
DEFAULT_SETTINGS = {
    "referral_required_tasks": "8",
    "referral_reward": "5",
    "task_reward": "1",
    "min_withdraw": "25",
    # Off by default: Telegram silently drops custom emoji unless the bot's
    # owner has Premium or the bot bought a Fragment username.
    "premium_emoji_enabled": "0",
    "registration_enabled": "1",
    "withdraw_enabled": "1",
    "integration_subgram_enabled": "1",
    "integration_flyer_enabled": "1",
    "integration_tgrass_enabled": "1",
    "integration_botohub_enabled": "1",
    "integration_traffy_enabled": "1",
    "integration_axionna_enabled": "1",
    "gift_bear_price": "15",
    "gift_bear_id": "5170233102089322756",
    "withdraw_admin_channel": "@SixSevenAdmin1",
    "withdraw_public_channel": "@VpRefinityBot",
    "withdraw_amounts": "25,50,100",
    "withdraw_method_min_amount": "50",
    "ad_block_text": "Тут могла быть ваша реклама",
    "ad_block_url": "",
    "text_welcome": (
        "😀 Привет, {name}!\n\n"
        "Копи ⭐ Stars: выполняй задания, зови друзей и получай награды.\n\n"
        "Выбирай раздел ниже 👇"
    ),
    "text_tasks_intro": "Подписывайся на каналы и выполняй простые задания — за каждое получаешь {tasks_reward} ⭐.",
    "text_profile_footer": "Есть промокод? Активируй его кнопкой ниже 👇",
    "text_withdraw_intro": "⭐ Ваш баланс: {balance}\n\nМинимальная сумма вывода: {min} ⭐",
    "text_withdraw_created": (
        "✅ Заявка создана!\n\n📤 Сумма: {amount} ⭐\n👤 Получатель: @{recipient}\n🆔 Заявка: #{id}\n\n"
        "Следите за статусом заявки в нашем канале 👇"
    ),
    "text_withdraw_accepted": "✅ Заявка принята\n\n📤 Сумма: {amount} ⭐\n🆔 Заявка: #{id}",
    "text_review_request": (
        "😋 Пожалуйста оставьте отзыв со скрином в комментариях под этим постом\n"
        "Ссылка на канал с отзывами: https://t.me/SrvNkOtzovI/8\n"
        "👇👇👇👇👇👇"
    ),
    # threshold_invites:reward pairs - the highest threshold met wins. Applies
    # only to the #1 spot on the DAILY invites leaderboard (admin-triggered,
    # not automatic - see admin/statistics.py).
    "daily_invite_prize_tiers": "10:15,50:25,130:50",
}
