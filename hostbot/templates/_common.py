"""
أدوات مشتركة بين قوالب البوتات:
• تحميل/حفظ ملفات JSON داخل مجلد كل بوت
• تنسيق HTML آمن
• ذكر المستخدم
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from telegram import MessageEntity, Update, User, Chat
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

VALID_BUTTON_STYLES = {"primary", "success", "danger"}

# وسم إيموجي بريميوم
PREMIUM_EMOJI_RE = re.compile(r"\{(\d{5,})\}")
PREMIUM_EMOJI_FALLBACK = "🔥"

TELEGRAM_HTML_TAG_RE = re.compile(
    r"</?(?:b|strong|i|em|u|ins|s|strike|del|tg-spoiler|code|pre|"
    r"blockquote|tg-emoji|a)(?:\s[^>]*)?>",
    re.IGNORECASE,
)


def bot_dir(bot_id: int) -> Path:
    from ..storage import get_bot_dir
    return get_bot_dir(bot_id)


def load_json(bot_id: int, name: str, default: Any) -> Any:
    from ..storage import load_json as _lj
    return _lj(bot_id, name, default)


def save_json(bot_id: int, name: str, data: Any):
    from ..storage import save_json as _sj
    _sj(bot_id, name, data)


def inc_stat(bot_id: int, key: str, n: int = 1):
    stats = load_json(bot_id, "stats.json", {"messages_in": 0, "messages_out": 0,
                                             "users": 0, "started_at": int(time.time())})
    stats[key] = int(stats.get(key, 0)) + n
    save_json(bot_id, "stats.json", stats)
    from ..storage import inc_bot_messages
    inc_bot_messages(bot_id, n)


def safe_html(value, fallback="—") -> str:
    return html.escape(str(value or fallback))


def user_mention(user: User | Chat) -> str:
    if isinstance(user, Chat):
        name = " ".join(filter(None, [user.first_name, user.last_name])) or "مجهول"
        uid = user.id
        uname = user.username
    else:
        name = user.full_name or "مجهول"
        uid = user.id
        uname = user.username
    if uname:
        return f'<a href="https://t.me/{uname}">{html.escape(name)}</a>'
    return f'<a href="tg://user?id={uid}">{html.escape(name)}</a>'


def render_premium_emojis(text: str) -> str:
    return PREMIUM_EMOJI_RE.sub(
        lambda m: f'<tg-emoji emoji-id="{m.group(1)}">{PREMIUM_EMOJI_FALLBACK}</tg-emoji>',
        text,
    )


def prepare_ai_telegram_html(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^\s*```(?:html|HTML)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text).strip()
    if not text:
        return "عذراً، لم يصل رد من الذكاء الاصطناعي."
    if not TELEGRAM_HTML_TAG_RE.search(text):
        text = html.escape(text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
        text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
        text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
        text = re.sub(r"\[([^\]]+)\]\((https?://[^\)\s]+)\)", r'<a href="\2">\1</a>', text)
    return render_premium_emojis(text)


def make_reply_params(msg_id, allow=True):
    from telegram import ReplyParameters
    return ReplyParameters(message_id=msg_id, allow_sending_without_reply=allow)


async def notify_owner(ctx: ContextTypes.DEFAULT_TYPE, owner_id: int, text: str,
                        parse_mode=ParseMode.HTML, **kw):
    try:
        return await ctx.bot.send_message(owner_id, text, parse_mode=parse_mode, **kw)
    except Exception as e:
        logger.warning(f"notify owner {owner_id} failed: {e}")


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def parse_buttons_text(raw: str) -> list[dict]:
    """يتوقع: نص | رابط | لون(اختياري) في كل سطر"""
    buttons = []
    for line in raw.strip().splitlines():
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        btn = {"text": parts[0], "url": parts[1]}
        if len(parts) > 2 and parts[2].lower() in VALID_BUTTON_STYLES:
            btn["style"] = parts[2].lower()
        else:
            btn["style"] = "success"
        if btn["text"] and btn["url"].startswith(("http://", "https://", "t.me/", "tg:")):
            buttons.append(btn)
        elif btn["text"] and btn["url"]:
            # السماح بروابط t.me بلا بروتوكول
            btn["url"] = "https://" + btn["url"]
            buttons.append(btn)
    return buttons
