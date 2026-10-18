"""Request middleware applied to every outgoing message/edit:

* bare links in message text/captions are wrapped in <code> (monospace, tap to copy);
* when premium emoji are enabled, known unicode emoji in text become
  <tg-emoji> and a leading emoji on an inline button becomes its
  icon_custom_emoji_id - so every screen gets them without touching each
  handler.
"""
import re

from aiogram.client.default import Default
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.methods import (
    EditMessageCaption,
    EditMessageReplyMarkup,
    EditMessageText,
    SendAnimation,
    SendDocument,
    SendMessage,
    SendPhoto,
    SendVideo,
)
from aiogram.types import InlineKeyboardMarkup

import premium_emoji as pe

_TEXT_METHODS = (SendMessage, EditMessageText)
_CAPTION_METHODS = (SendPhoto, SendVideo, SendAnimation, SendDocument, EditMessageCaption)
_MARKUP_METHODS = _TEXT_METHODS + _CAPTION_METHODS + (EditMessageReplyMarkup,)

# segments that must be left untouched: code/pre blocks, existing custom
# emoji, links and any other tag
_PROTECTED = re.compile(
    r"(<code>.*?</code>|<pre>.*?</pre>|<tg-emoji[^>]*>.*?</tg-emoji>|<a\s[^>]*>.*?</a>|<[^>]+>)",
    re.S,
)
_URL = re.compile(r"((?:https?://|(?<![\w./])t\.me/)[^\s<>\"']+)")
_EMOJI = re.compile(
    "(" + "|".join(sorted((re.escape(e) for e in pe.EMOJI_IDS), key=len, reverse=True)) + ")️?"
)


def _emojify(text: str) -> str:
    if not pe.ENABLED:
        return text
    return _EMOJI.sub(
        lambda m: f'<tg-emoji emoji-id="{pe.EMOJI_IDS[m.group(1)]}">{m.group(0)}</tg-emoji>', text
    )


def _format_plain(text: str) -> str:
    out = []
    for i, part in enumerate(_URL.split(text)):
        out.append(f"<code>{part}</code>" if i % 2 else _emojify(part))
    return "".join(out)


def format_html(text: str) -> str:
    out = []
    for i, part in enumerate(_PROTECTED.split(text)):
        out.append(part if i % 2 else _format_plain(part))
    return "".join(out)


def _format_markup(markup):
    if not pe.ENABLED or not isinstance(markup, InlineKeyboardMarkup):
        return markup
    rows = []
    for row in markup.inline_keyboard:
        new_row = []
        for btn in row:
            m = _EMOJI.match(btn.text)
            if m and not btn.icon_custom_emoji_id:
                rest = btn.text[m.end():].lstrip()
                if rest:
                    btn = btn.model_copy(
                        update={"text": rest, "icon_custom_emoji_id": pe.EMOJI_IDS[m.group(1)]}
                    )
            new_row.append(btn)
        rows.append(new_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _is_html(method) -> bool:
    mode = getattr(method, "parse_mode", None)
    return isinstance(mode, Default) or (isinstance(mode, str) and mode.upper() == "HTML")


class OutgoingFormatMiddleware(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        try:
            if isinstance(method, _TEXT_METHODS) and method.text and _is_html(method):
                method.text = format_html(method.text)
            elif isinstance(method, _CAPTION_METHODS) and method.caption and _is_html(method):
                method.caption = format_html(method.caption)
            if isinstance(method, _MARKUP_METHODS) and method.reply_markup is not None:
                method.reply_markup = _format_markup(method.reply_markup)
        except Exception:
            pass  # never block a message because of cosmetics
        return await make_request(bot, method)
