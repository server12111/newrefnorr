import logging
import re
from dataclasses import dataclass, field

import aiohttp

logger = logging.getLogger("integrations")


@dataclass
class TaskItem:
    provider: str
    external_id: str
    title: str
    link: str
    reward: float = 0.0
    extra: dict = field(default_factory=dict)


# Only plain Telegram targets are offered as tasks: channels, chats/groups
# and bots. Mini apps, external sites, MAX and other off-Telegram resources
# are dropped - they can't be verified and the user asked not to show them.
_ALLOWED_KIND = re.compile(r"channel|chat|group|bot|канал|чат|групп|бот", re.I)
_BANNED_KIND = re.compile(
    r"resource|site|website|web|link|app|mini|max|referral|action|survey|install|game",
    re.I,
)


# Mini app links (t.me/<bot>/<app>, ?startapp=...) open a web app instead of
# the channel/bot itself - never offered, whatever the provider says the
# target is.
_MINI_APP = re.compile(r"[?&]startapp=|t\.me/[\w_]+/app|/webapp", re.I)


def is_mini_app(link: str | None) -> bool:
    return bool(link and _MINI_APP.search(link))


def is_telegram_target(kind: str | None = None, resource_id=None, link: str | None = None) -> bool:
    """kind - provider's own type/task label; resource_id - Telegram id of the
    target (channel -100..., bot/user positive); link - the task url."""
    if is_mini_app(link):
        return False
    if kind:
        if _BANNED_KIND.search(str(kind)) and not _ALLOWED_KIND.search(str(kind)):
            return False
        if _ALLOWED_KIND.search(str(kind)):
            return True
    if resource_id not in (None, "", "None", 0, "0"):
        return True
    if link:
        return bool(re.match(r"https?://(t\.me|telegram\.me|telegram\.dog)/", link.strip(), re.I))
    return False


class IntegrationError(Exception):
    pass


_session: aiohttp.ClientSession | None = None


async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
    return _session


async def close_session() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()
