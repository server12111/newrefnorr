"""Telegram Premium custom emoji IDs for InlineKeyboardButton.icon_custom_emoji_id.

IMPORTANT: a bot may only use custom emoji if its owner has Telegram Premium, or
if the bot purchased a username on Fragment. Without that, Telegram accepts the
field and renders nothing - so button icons silently disappear. ENABLED gates
this: when off we fall back to plain unicode emoji in the button text instead.
Flip it in /admin -> Настройки (premium_emoji_enabled) once the bot qualifies.
"""

STAR = "5870801633104891858"       # ⭐️ stars / balance / withdraw
KEYBOARD = "5873204392429096339"   # ⌨ (not currently assigned to any button)
PROFILE = "5870994129244131212"    # 👤
USERS = "6032594876506312598"      # 👥
CHECK = "5870633910337015697"      # ✅ confirm / enabled
CROSS = "5870657884844462243"      # ❌ cancel / disabled
PLAY = "5870921127685001066"       # ▶ go / proceed
PIN = "5870930744116776638"        # 📌
TROPHY = "5870684638195748414"     # 🏆 top / leaderboard
LINK = "5769289093221454192"       # 🔗
PHOTO = "6035128606563241721"      # 🖼
GIFT = "6032644646587338669"       # 🎁
UNLOCK = "6037496202990194718"     # 🔓
LOCK = "6037249452824072506"       # 🔒
CHART = "5938539885907415367"      # 📈 stats
BACK = "5352759161945867747"       # 🔙 (replaces ◀️)
NEXT = "5951966593624839282"       # ➡️
SKIP = "5199750831766784538"       # ⏩ (replaces ⏭)
REFRESH = "5454074580010295588"    # 🔄
TASKS = "5435970940670320222"      # 📋
MEGAPHONE = "6039381989985882045"  # 📢
SCROLL = "5294106646170049573"     # 📜
TICKET = "5377599075237502153"     # 🎟
DIAMOND = "5229173741451230931"    # 💎
GEAR = "5408910121264756249"       # ⚙
PENCIL = "5395444784611480792"     # ✏️
PLUS = "5397916757333654639"       # ➕
MINUS = "5418206758365574104"      # ➖
THINK = "5379852863621051620"      # 🤔 (replaces 🆔)
CHAT = "5870984130560266604"       # 💬
POINT_DOWN = "5949485038830625261" # 👇
SMILE = "5323553002080972814"      # 😀
HOURGLASS = "5213452215527677338"  # ⏳
MONEY = "4965219701572503640"      # 💰

# unicode emoji -> premium id, used by outgoing_format for message text
# (<tg-emoji>) and for any button whose text starts with one of these
EMOJI_IDS = {
    "◀": BACK, "🔙": BACK,
    "➡": NEXT,
    "⏭": SKIP, "⏩": SKIP,
    "🔄": REFRESH,
    "📋": TASKS,
    "📢": MEGAPHONE,
    "📜": SCROLL,
    "🎟": TICKET,
    "💎": DIAMOND,
    "⚙": GEAR,
    "✏": PENCIL,
    "➕": PLUS,
    "➖": MINUS,
    "🆔": THINK, "🤔": THINK,
    "💬": CHAT,
    "👥": USERS,
    "👤": PROFILE,
    "👇": POINT_DOWN,
    "😀": SMILE,
    "⭐": STAR,
    "✅": CHECK,
    "❌": CROSS,
    "▶": PLAY,
    "📌": PIN,
    "🏆": TROPHY,
    "🔗": LINK,
    "🖼": PHOTO,
    "🎁": GIFT,
    "🔓": UNLOCK,
    "🔒": LOCK,
    "📈": CHART,
    "⏳": HOURGLASS,
    "💰": MONEY,
}

ENABLED = False


def set_enabled(value: bool) -> None:
    global ENABLED
    ENABLED = value


def label(text: str, fallback: str, emoji_id: str) -> tuple[str, dict]:
    """Returns (button text, extra kwargs) - a premium icon when the bot can use
    custom emoji, otherwise the plain unicode emoji baked into the text."""
    if ENABLED:
        return text, {"icon_custom_emoji_id": emoji_id}
    return f"{fallback} {text}", {}
