"""
قالب بوت حماية المجموعات (Group Protection Bot) — نسخة مطوّرة.

الميزات:
  • ترحيب/وداع مع وسائط (صورة/فيديو/ملف/رسالة) وأزرار
  • كابتشا بسيط (زر "أنا لست بوت") للأعضاء الجدد (بصلاحية تقييد مؤقت)
  • قواعد المجموعة (/rules)
  • أوامر أدمن كاملة: ban / unban / kick / mute / unmute / tmute / warn / unwarn / warns / del / pin / purge
  • نظام تحذيرات مع حد وإجراء تلقائي (ban/kick/mute)
  • Anti-Flood مضاد السبام (كم/طرد/حظر + كاش للرسائل)
  • Anti-Link (روابط عامة + روابط دعوات تلجرام + منع @username بقنوات)
  • قائمة كلمات محظورة (تدعم العربي والإنجليزي + فلاتر شائعة)
  • منع وسائط (ستيكر/صور/فيديو/مستندات/صوت/رسائل صوتية/بوتات/استفتاءات)
  • منع الرسائل الطويلة
  • Night Mode (وضع الليل: كتم تلقائي للجميع ماعدا الأدمن في ساعات محددة)
  • Slow Mode (تحديد الفترة بين رسائل العضو)
  • حذف أوامر البوتات (commands)
  • منع إضافة بوتات من غير الأدمن
  • تسجيل إجراءات الأدمن في مجموعة سجل (log group)
  • لوحة تحكم إنلاين لمالك البوت في الخاص (/settings) لتعديل إعدادات كل مجموعة
  • أمر /id لمعرفة آيدي المستخدم والمجموعة
  • /notes و /save و /clear (ملاحظات مثبتة)
  • /report (بلاغ) للأدمن عند رد على رسالة
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from collections import defaultdict, deque
from typing import Any

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    LinkPreviewOptions, ChatPermissions, ChatMember, BotCommand,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatMemberHandler, filters, ContextTypes, Defaults,
    ConversationHandler,
)

from ._common import (
    safe_html, bot_dir, load_json, save_json,
    render_premium_emojis, user_mention, parse_buttons_text,
)
from .. import storage

logger = logging.getLogger(__name__)

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

# ═══════════════════════════════════════════════════════════
#  إعدادات افتراضية لكل مجموعة
# ═══════════════════════════════════════════════════════════

DEFAULT_SETTINGS: dict[str, Any] = {
    # ترحيب/وداع
    "welcome_enabled": True,
    "welcome_text": "أهلاً وسهلاً بك {user} في {chat} 👋\nنرجو الالتزام بقواعد المجموعة.",
    "welcome_photo": None,       # file_id (اختياري)
    "welcome_buttons": [],       # [{text, url, style}]
    "goodbye_enabled": True,
    "goodbye_text": "وداعاً {user}، نراك قريباً 👋",
    # كابتشا
    "captcha_enabled": False,
    "captcha_timeout": 180,       # ثانية
    "captcha_action": "kick",    # kick | ban
    # وارنز
    "warn_limit": 3,
    "warn_action": "mute",       # ban | kick | mute
    "warn_mute_minutes": 60,
    # anti-flood
    "antiflood_enabled": True,
    "antiflood_msgs": 6,
    "antiflood_window": 6,       # ثوان
    "antiflood_action": "mute",  # mute | kick | ban
    "antiflood_mute_minutes": 10,
    # anti-link
    "antilink_enabled": True,
    "antilink_allow_tg_links": False,
    "antilink_action": "delete", # delete | warn | mute | ban
    # حظر وسائط
    "block_stickers": False,
    "block_documents": False,
    "block_videos": False,
    "block_photos": False,
    "block_audios": False,
    "block_voice": False,
    "block_video_notes": False,
    "block_contacts": False,
    "block_locations": False,
    "block_polls": False,
    "block_bots": False,           # منع إضافة بوتات من غير أدمن
    "block_bot_commands": False,   # حذف أوامر تبدأ بـ /
    "block_arabic_abuse": False,   # فلتر كلمات بذيئة عربية شائعة
    # كلمات محظورة
    "blocked_words": [],
    "blocked_words_action": "delete",
    # خصائص إضافية
    "max_message_length": 0,       # 0 = معطّل
    "slow_mode_seconds": 0,        # 0 = معطّل
    "night_mode_enabled": False,
    "night_mode_start": "00:00",   # بتوقيت السيرفر — للتبسيط
    "night_mode_end": "06:00",
    "log_chat_id": None,           # مجموعة السجل
    # ملاحظات
    "notes": {},                   # {name: text}
    # رتبة تحذير من القنوات (منع النشر كقناة)
    "block_channel_messages": False,
}

DEFAULT_ABUSE_WORDS = [
    "كلب", "حقير", "غبي", "أحمق", "قذر", "زبال",
    "يلعن", "يلعن ابوك", "يلعن امك", "كسم", "كس", "شرموط",
    "منيك", "منيكة", "عرص", "معرس", "زبي", "زب",
]


def chat_settings(bot_id: int, chat_id: int) -> dict:
    all_chats = load_json(bot_id, "protection_chats.json", {})
    key = str(chat_id)
    if key not in all_chats:
        all_chats[key] = {k: v for k, v in DEFAULT_SETTINGS.items()}
        # نسخ للـ notes dict منفصلاً (لا نريده reference مشترك)
        all_chats[key]["notes"] = {}
        all_chats[key]["blocked_words"] = []
        all_chats[key]["welcome_buttons"] = []
        save_json(bot_id, "protection_chats.json", all_chats)
    # ضمان أي مفاتيح جديدة أُضيفت في التحديثات
    for k, v in DEFAULT_SETTINGS.items():
        if k not in all_chats[key]:
            if isinstance(v, (dict, list)):
                all_chats[key][k] = v.__class__(v)
            else:
                all_chats[key][k] = v
    return all_chats[key]


def save_chat_settings(bot_id: int, chat_id: int, data: dict):
    all_chats = load_json(bot_id, "protection_chats.json", {})
    all_chats[str(chat_id)] = data
    save_json(bot_id, "protection_chats.json", all_chats)


def warns(bot_id: int, chat_id: int) -> dict:
    key = f"warns_{chat_id}.json"
    return load_json(bot_id, key, {})


def save_warns(bot_id: int, chat_id: int, data: dict):
    key = f"warns_{chat_id}.json"
    save_json(bot_id, key, data)


# ═══════════════════════════════════════════════════════════
#  Runtime
# ═══════════════════════════════════════════════════════════

class ProtectionRuntime:
    def __init__(self, record: dict, host_app: Application):
        self.bot_id = int(record["id"])
        self.token = record["token"]
        self.owner_id = int(record["owner_id"])
        self.host_app = host_app
        # anti-flood: (chat, user) → deque
        self.flood_track: dict[tuple[int, int], deque] = defaultdict(deque)
        # slow-mode: (chat, user) → last_time
        self.slow_track: dict[tuple[int, int], float] = {}
        # captcha: (chat, user) → message_id + timeout
        self.captcha_pending: dict[tuple[int, int], dict] = {}
        # cache أدمن
        self._admin_cache: dict[int, tuple[float, set[int]]] = {}
        # user per-chat perms (لإرجاع الصلاحيات بعد الكابتشا / الليل)
        self._prev_perms: dict[tuple[int, int], dict] = {}
        # night mode state
        self._night_active: dict[int, bool] = {}

    async def is_admin(self, ctx: ContextTypes.DEFAULT_TYPE, chat_id: int,
                       user_id: int) -> bool:
        if user_id == self.owner_id:
            return True
        now = time.time()
        cached = self._admin_cache.get(chat_id)
        if cached and now - cached[0] < 30:
            return user_id in cached[1]
        admins: set[int] = set()
        try:
            async for a in ctx.bot.get_chat_administrators(chat_id):
                admins.add(a.user.id)
        except TelegramError:
            pass
        self._admin_cache[chat_id] = (now, admins)
        return user_id in admins

    def invalidate_admin_cache(self, chat_id: int):
        self._admin_cache.pop(chat_id, None)

    def record_msg(self, chat_id: int):
        # إحصائية
        try:
            storage.inc_bot_messages(self.bot_id, 1)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════

URL_RE = re.compile(
    r"(?i)\b((?:https?://)?(?:t(?:elegram)?\.me|t\.co|discord\.gg|instagram\.com|"
    r"twitter\.com|facebook\.com|youtube\.com|youtu\.be|tiktok\.com|"
    r"whatsapp\.com|chat\.whatsapp\.com|github\.com|bit\.ly|tinyurl\.com|"
    r"[a-z0-9-]{1,30}\.(?:com|net|org|io|me|gg|xyz|ru|sa|tv|eg|dev|app))(\S*)?)\b"
)
TG_INVITE_RE = re.compile(r"(?i)(?:https?://)?t\.me/(?:joinchat/|\+)?[A-Za-z0-9_-]{5,}")


def _reply(msg, text, **kw):
    return msg.reply_text(
        text, parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        allow_sending_without_reply=True, **kw)


def _mention_from_user(u) -> str:
    return user_mention(u)


async def _target_user(update: Update, ctx) -> int | None:
    msg = update.effective_message
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    if msg.reply_to_message and msg.reply_to_message.from_user:
        return msg.reply_to_message.from_user.id
    args = ctx.args or []
    if args:
        a = args[0]
        if a.startswith("@"):
            try:
                ch = await ctx.bot.get_chat(a); return ch.id
            except TelegramError:
                return None
        try:
            return int(a)
        except ValueError:
            return None
    return None


async def _delete_after(msg, text, seconds: int = 12):
    try:
        sent = await msg.reply_text(text, parse_mode=ParseMode.HTML,
                                     disable_web_page_preview=True,
                                     allow_sending_without_reply=True)
        await asyncio.sleep(seconds)
        try: await sent.delete()
        except TelegramError: pass
    except TelegramError:
        pass


async def _log(rt, ctx, chat_id: int, action: str, by_user=None, target=None, details: str = ""):
    s = chat_settings(rt.bot_id, chat_id)
    log_chat = s.get("log_chat_id")
    if not log_chat:
        return
    lines = [f"📋 <b>{safe_html(action)}</b>"]
    if by_user:
        lines.append(f"بواسطة: {safe_html(by_user.full_name)} (<code>{by_user.id}</code>)")
    if target is not None:
        lines.append(f"الهدف: <code>{target}</code>")
    if details:
        lines.append(f"التفاصيل: {safe_html(details)}")
    try:
        await ctx.bot.send_message(int(log_chat), "\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
#  ترحيب/وداع/كابتشا
# ═══════════════════════════════════════════════════════════

async def chat_member_watcher(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cm = update.chat_member
    if not cm: return
    chat = cm.chat; rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    if chat.type not in ("group", "supergroup"): return
    s = chat_settings(rt.bot_id, chat.id)
    n = cm.new_chat_member; o = cm.old_chat_member; user = n.user
    inviter = cm.from_user

    # اكتشاف إضافة بوت
    if user.is_bot and n.status in ("member", "administrator") and o.status in ("left", "kicked"):
        if s.get("block_bots") and inviter and not await rt.is_admin(ctx, chat.id, inviter.id):
            try:
                await ctx.bot.ban_chat_member(chat.id, user.id)
                await ctx.bot.unban_chat_member(chat.id, user.id)
                await _delete_after(update.effective_message or (await ctx.bot.send_message(
                    chat.id, f"🤖 {_mention_from_user(user)} تم طرد البوت (ممنوع إضافة بوتات بدون إذن الأدمن).")))
            except TelegramError:
                pass
        return

    if user.is_bot: return

    joined = o.status in ("left", "kicked") and n.status in ("member", "restricted")
    left   = n.status in ("left", "kicked") and o.status in ("member", "restricted", "administrator")

    if joined and s.get("welcome_enabled"):
        text = s["welcome_text"].replace("{user}", _mention_from_user(user)).replace("{chat}", safe_html(chat.title))
        text = render_premium_emojis(text)
        # كابتشا
        if s.get("captcha_enabled"):
            try:
                await ctx.bot.restrict_chat_member(
                    chat.id, user.id,
                    ChatPermissions(can_send_messages=False),
                )
            except TelegramError:
                pass
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ أنا لست بوت",
                                     callback_data=f"captcha:{chat.id}:{user.id}:ok")
            ]])
            try:
                m = await ctx.bot.send_message(
                    chat.id,
                    f"👋 مرحباً {_mention_from_user(user)}! "
                    "اضغط الزر أدناه خلال دقائق لتتمكن من الكتابة.",
                    parse_mode=ParseMode.HTML, reply_markup=kb)
                rt.captcha_pending[(chat.id, user.id)] = {
                    "msg_id": m.message_id, "at": time.time(),
                }
                # إرسال نص الترحيب بعد الكابتشا - أو معاً
                asyncio.create_task(_captcha_timeout(ctx, rt, chat.id, user.id, m.message_id))
            except TelegramError:
                pass
            return

        # ترحيب عادي
        try:
            photo = s.get("welcome_photo")
            kb = _welcome_buttons_kb(s.get("welcome_buttons", []))
            if photo:
                await ctx.bot.send_photo(chat.id, photo, caption=text,
                                          parse_mode=ParseMode.HTML, reply_markup=kb)
            else:
                await ctx.bot.send_message(chat.id, text, parse_mode=ParseMode.HTML,
                                            disable_web_page_preview=True, reply_markup=kb)
        except TelegramError as e:
            logger.warning(f"welcome send: {e}")

    elif left and s.get("goodbye_enabled"):
        text = s["goodbye_text"].replace("{user}", safe_html(user.full_name)).replace("{chat}", safe_html(chat.title))
        try:
            await ctx.bot.send_message(chat.id, render_premium_emojis(text),
                                        parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except TelegramError:
            pass


def _welcome_buttons_kb(buttons: list[dict]) -> InlineKeyboardMarkup | None:
    if not buttons: return None
    rows = []
    row = []
    for b in buttons:
        row.append(InlineKeyboardButton(b["text"], url=b["url"]))
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    return InlineKeyboardMarkup(rows)


async def _captcha_timeout(ctx, rt: ProtectionRuntime, chat_id: int,
                           user_id: int, msg_id: int):
    s = chat_settings(rt.bot_id, chat_id)
    timeout = int(s.get("captcha_timeout", 180))
    await asyncio.sleep(timeout)
    p = rt.captcha_pending.pop((chat_id, user_id), None)
    if not p: return
    action = s.get("captcha_action", "kick")
    try:
        if action == "ban":
            await ctx.bot.ban_chat_member(chat_id, user_id)
            await ctx.bot.send_message(chat_id, f"🚫 تم حظر العضو لعدم تجاوز الكابتشا.")
        else:
            await ctx.bot.ban_chat_member(chat_id, user_id)
            await ctx.bot.unban_chat_member(chat_id, user_id)
        await ctx.bot.delete_message(chat_id, msg_id)
    except TelegramError:
        pass


async def on_captcha_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    try:
        _, cid_s, uid_s, _ = q.data.split(":")
        chat_id = int(cid_s); uid = int(uid_s)
    except Exception:
        await q.answer("بيانات غير صالحة."); return
    if q.from_user.id != uid:
        await q.answer("هذا الزر لعضو آخر.", show_alert=True); return
    p = rt.captcha_pending.pop((chat_id, uid), None)
    if not p:
        await q.answer("انتهت صلاحية الكابتشا.", show_alert=True); return
    s = chat_settings(rt.bot_id, chat_id)
    perms = ChatPermissions(
        can_send_messages=True, can_send_media_messages=True,
        can_send_other_messages=True, can_add_web_page_previews=True,
        can_send_polls=True, can_invite_users=True, can_pin_messages=False,
        can_change_info=False,
    )
    try:
        await ctx.bot.restrict_chat_member(chat_id, uid, perms)
        await q.edit_message_text(
            f"✅ أهلاً بك <a href='tg://user?id={uid}'>العضو الجديد</a>! "
            "تم منحك صلاحيات الكتابة.",
            parse_mode=ParseMode.HTML)
        # إرسال نص الترحيب الأصلي
        text = s["welcome_text"].replace("{user}", f"<a href='tg://user?id={uid}'>{safe_html(q.from_user.full_name)}</a>").replace("{chat}", safe_html(q.message.chat.title))
        photo = s.get("welcome_photo")
        kb = _welcome_buttons_kb(s.get("welcome_buttons", []))
        if photo:
            await ctx.bot.send_photo(chat_id, photo, caption=render_premium_emojis(text),
                                      parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await ctx.bot.send_message(chat_id, render_premium_emojis(text),
                                        parse_mode=ParseMode.HTML,
                                        disable_web_page_preview=True, reply_markup=kb)
    except TelegramError as e:
        await q.answer(f"خطأ: {e}", show_alert=True)


# ═══════════════════════════════════════════════════════════
#  Watcher: مضادات ووسائط
# ═══════════════════════════════════════════════════════════

async def watcher(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat; user = update.effective_user
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    if not msg or not chat or chat.type not in ("group", "supergroup") or not user:
        return
    if user.is_bot: return
    if await rt.is_admin(ctx, chat.id, user.id):
        rt.record_msg(chat.id); return

    # ليلاً: منع الرسائل إلا من الأدمن
    s = chat_settings(rt.bot_id, chat.id)
    if s.get("night_mode_enabled") and _night_active(s):
        try:
            await msg.delete()
        except TelegramError:
            pass
        rt.record_msg(chat.id); return

    # Slow mode
    slow = int(s.get("slow_mode_seconds", 0))
    if slow > 0:
        last = rt.slow_track.get((chat.id, user.id), 0)
        if time.time() - last < slow:
            try: await msg.delete()
            except TelegramError: pass
            rt.record_msg(chat.id); return
        rt.slow_track[(chat.id, user.id)] = time.time()

    # منع رسائل القنوات (sender_chat هو قناة)
    if s.get("block_channel_messages") and msg.sender_chat and msg.sender_chat.id != chat.id:
        if msg.sender_chat.type in ("channel",):
            try: await msg.delete()
            except TelegramError: pass
            await _delete_after(msg, f"⚠️ {_mention_from_user(user)} النشر كقناة ممنوع.", 8)
            rt.record_msg(chat.id); return

    text = msg.text or msg.caption or ""

    # أوامر البوتات (/)
    if s.get("block_bot_commands") and msg.entities:
        if any(e.type == "bot_command" for e in msg.entities):
            try: await msg.delete()
            except TelegramError: pass
            rt.record_msg(chat.id); return

    # Anti-link
    if s.get("antilink_enabled"):
        is_invite = TG_INVITE_RE.search(text)
        is_url = URL_RE.search(text)
        # إذا سمحنا بروابط t.me العامة (مثل القناة الرسمية) نمنع الدعوات فقط
        if s.get("antilink_allow_tg_links"):
            hit = bool(is_invite)
        else:
            hit = bool(is_invite or is_url)
        if hit:
            try: await msg.delete()
            except TelegramError: pass
            act = s.get("antilink_action", "delete")
            if act == "warn":
                await _apply_warn(rt, ctx, chat.id, user.id, "نشر رابط")
            elif act == "mute":
                await _do_mute(rt, ctx, chat.id, user.id, 10)
            elif act == "ban":
                try: await ctx.bot.ban_chat_member(chat.id, user.id)
                except TelegramError: pass
            notice = await ctx.bot.send_message(
                chat.id, f"⚠️ {_mention_from_user(user)} الروابط ممنوعة.",
                parse_mode=ParseMode.HTML)
            await asyncio.sleep(12)
            try: await notice.delete()
            except TelegramError: pass
            rt.record_msg(chat.id); return

    # كلمات محظورة
    blocked_words = [w.lower() for w in s.get("blocked_words", []) if w]
    if s.get("block_arabic_abuse"):
        blocked_words = list(blocked_words) + DEFAULT_ABUSE_WORDS
    if blocked_words:
        low = text.lower()
        hit = next((w for w in blocked_words if w in low), None)
        if hit:
            try: await msg.delete()
            except TelegramError: pass
            if s.get("blocked_words_action") == "warn":
                await _apply_warn(rt, ctx, chat.id, user.id, f"كلمة محظورة: {hit}")
            notice = await ctx.bot.send_message(
                chat.id, f"⚠️ كلمة محظورة من {_mention_from_user(user)}.",
                parse_mode=ParseMode.HTML)
            await asyncio.sleep(10)
            try: await notice.delete()
            except TelegramError: pass
            rt.record_msg(chat.id); return

    # وسائط
    mr = {
        "block_stickers": bool(msg.sticker),
        "block_documents": bool(msg.document),
        "block_videos": bool(msg.video or msg.video_note and s.get("block_video_notes")),
        "block_photos": bool(msg.photo),
        "block_audios": bool(msg.audio),
        "block_voice": bool(msg.voice),
        "block_video_notes": bool(msg.video_note),
        "block_contacts": bool(msg.contact),
        "block_locations": bool(msg.location or msg.venue),
        "block_polls": bool(msg.poll),
    }
    blocked_type = next((k.replace("block_", "") for k, v in mr.items() if v and s.get(k)), None)
    if blocked_type:
        try: await msg.delete()
        except TelegramError: pass
        await _delete_after(msg, "⚠️ هذا النوع من المحتوى ممنوع.")
        rt.record_msg(chat.id); return

    # طول رسالة
    maxlen = int(s.get("max_message_length", 0))
    if maxlen and len(text) > maxlen:
        try: await msg.delete()
        except TelegramError: pass
        await _delete_after(msg, f"⚠️ الرسائل أطول من {maxlen} حرف ممنوعة.", 8)
        rt.record_msg(chat.id); return

    # Anti-Flood
    if s.get("antiflood_enabled"):
        key = (chat.id, user.id)
        dq = rt.flood_track[key]
        now = time.time()
        dq.append(now)
        win = float(s.get("antiflood_window", 6))
        while dq and now - dq[0] > win:
            dq.popleft()
        limit = int(s.get("antiflood_msgs", 6))
        if len(dq) > limit:
            rt.flood_track[key] = deque()
            act = s.get("antiflood_action", "mute")
            try:
                if act == "mute":
                    mins = int(s.get("antiflood_mute_minutes", 10))
                    await _do_mute(rt, ctx, chat.id, user.id, mins)
                    notice = await ctx.bot.send_message(
                        chat.id,
                        f"🔇 {_mention_from_user(user)} تم كتمه {mins} دقيقة (سبام).",
                        parse_mode=ParseMode.HTML)
                elif act == "kick":
                    await ctx.bot.ban_chat_member(chat.id, user.id)
                    await ctx.bot.unban_chat_member(chat.id, user.id)
                    notice = await ctx.bot.send_message(
                        chat.id, f"👢 {_mention_from_user(user)} تم طرده (سبام).",
                        parse_mode=ParseMode.HTML)
                elif act == "ban":
                    await ctx.bot.ban_chat_member(chat.id, user.id)
                    notice = await ctx.bot.send_message(
                        chat.id, f"🚫 {_mention_from_user(user)} تم حظره (سبام).",
                        parse_mode=ParseMode.HTML)
                else:
                    notice = None
                if notice:
                    await asyncio.sleep(15)
                    try: await notice.delete()
                    except TelegramError: pass
            except TelegramError:
                pass
            rt.record_msg(chat.id); return

    rt.record_msg(chat.id)


# ═══════════════════════════════════════════════════════════
#  Warns
# ═══════════════════════════════════════════════════════════

async def _apply_warn(rt: ProtectionRuntime, ctx, chat_id: int, user_id: int,
                       reason: str = "—", by_id: int = 0):
    w = warns(rt.bot_id, chat_id)
    key = str(user_id)
    u = w.get(key, {"count": 0, "history": []})
    u["count"] = int(u.get("count", 0)) + 1
    u.setdefault("history", []).append({"by": by_id, "reason": reason, "at": time.time()})
    w[key] = u
    save_warns(rt.bot_id, chat_id, w)
    s = chat_settings(rt.bot_id, chat_id)
    limit = int(s.get("warn_limit", 3))
    count = u["count"]
    try:
        await ctx.bot.send_message(
            chat_id,
            f"⚠️ تحذير ({count}/{limit}) لـ <a href='tg://user?id={user_id}'>العضو</a>.\n"
            f"السبب: {safe_html(reason)}",
            parse_mode=ParseMode.HTML)
    except TelegramError:
        pass
    if count >= limit:
        action = s.get("warn_action", "mute")
        try:
            if action == "ban":
                await ctx.bot.ban_chat_member(chat_id, user_id)
                await ctx.bot.send_message(chat_id, "🚫 تجاوز الحد، تم حظر العضو.")
            elif action == "kick":
                await ctx.bot.ban_chat_member(chat_id, user_id)
                await ctx.bot.unban_chat_member(chat_id, user_id)
                await ctx.bot.send_message(chat_id, "👢 تجاوز الحد، تم طرد العضو.")
            elif action == "mute":
                mins = int(s.get("warn_mute_minutes", 60))
                await _do_mute(rt, ctx, chat_id, user_id, mins)
                await ctx.bot.send_message(chat_id, f"🔇 تجاوز الحد، تم كتم العضو {mins} دقيقة.")
        except TelegramError:
            pass
        w[key]["count"] = 0
        save_warns(rt.bot_id, chat_id, w)


async def _do_mute(rt: ProtectionRuntime, ctx, chat_id: int, user_id: int,
                   minutes: int = 0):
    """minutes=0 ⇒ دائم حتى unmute"""
    perms = ChatPermissions(can_send_messages=False)
    until = int(time.time()) + minutes * 60 if minutes > 0 else None
    await ctx.bot.restrict_chat_member(chat_id, user_id, perms, until_date=until)


def _night_active(s: dict) -> bool:
    try:
        now = time.localtime()
        now_m = now.tm_hour * 60 + now.tm_min
        sh = s.get("night_mode_start", "00:00"); eh = s.get("night_mode_end", "06:00")
        def hhmm(x):
            h, m = x.split(":"); return int(h)*60 + int(m)
        s_m, e_m = hhmm(sh), hhmm(eh)
        if s_m == e_m: return False
        if s_m < e_m:
            return s_m <= now_m < e_m
        return now_m >= s_m or now_m < e_m
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════
#  أوامر الأدمن
# ═══════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    if update.effective_chat.type == "private":
        if update.effective_user.id == rt.owner_id:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🛡️ أضفني لمجموعة",
                                      url=f"https://t.me/{ctx.bot.username}?startgroup=add")],
                [InlineKeyboardButton("📖 /help للأوامر", callback_data="p_help")],
            ])
            await update.message.reply_text(
                "🛡️ <b>بوت حماية المجموعات</b>\n\n"
                "أضفني لمجموعتك وارفعني أدمن.\n"
                "الأوامر للأدمن في الأسفل. استخدم /help لعرضها.",
                parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        await update.message.reply_text("🛡️ أضفني لمجموعتك وارفعني أدمن للبدء.")
        return
    await update.message.reply_text(
        "🛡️ بوت الحماية نشط هنا. الأوامر: /rules /id /report\n"
        "الأدمن: /ban /unban /kick /mute /unmute /warn /del /pin")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>أوامر بوت الحماية</b>\n\n"
        "<b>للأعضاء:</b>\n"
        "• /rules — قواعد المجموعة\n"
        "• /id — آيديك وآيدي المجموعة\n"
        "• /report ردًا على رسالة — بلاغ للأدمن\n"
        "• /notes — قائمة الملاحظات، /note الاسم\n\n"
        "<b>للأدمن:</b>\n"
        "• /ban — حظر (ردًا على العضو أو /ban @username سبب)\n"
        "• /unban — فك حظر\n"
        "• /kick — طرد\n"
        "• /mute [دقائق] — كتم\n"
        "• /unmute — فك كتم\n"
        "• /tmute دقائق — كتم مؤقت\n"
        "• /warn سبب — تحذير\n"
        "• /unwarn — حذف تحذير\n"
        "• /warns — عدد تحذيرات العضو\n"
        "• /del — حذف رسالة (ردًا عليها)\n"
        "• /pin — تثبيت\n"
        "• /purge عدد — حذف عدد رسائل\n"
        "• /setrules — تعيين القواعد\n"
        "• /save الاسم المحتوى — حفظ ملاحظة\n"
        "• /clear الاسم — حذف ملاحظة",
        parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def cmd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message; u = update.effective_user; c = update.effective_chat
    lines = [f"👤 آيديك: <code>{u.id}</code>"]
    if c.type != "private":
        lines.append(f"👥 المجموعة: {safe_html(c.title)} — <code>{c.id}</code>")
    if msg.reply_to_message and msg.reply_to_message.from_user:
        t = msg.reply_to_message.from_user
        lines.append(f"🎯 العضو المردود: {safe_html(t.full_name)} — <code>{t.id}</code>")
    await _reply(msg, "\n".join(lines))


async def cmd_rules(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"): return
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    s = chat_settings(rt.bot_id, chat.id)
    await update.message.reply_text(
        f"📜 <b>قواعد {safe_html(chat.title)}</b>\n\n{s['rules_text']}",
        parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def cmd_setrules(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    if update.effective_chat.type not in ("group", "supergroup"): return
    if not await rt.is_admin(ctx, update.effective_chat.id, update.effective_user.id): return
    text = (ctx.match.string.split(None, 1)[1] if (ctx.match and len(ctx.match.string.split()) > 1) else "") or " ".join(ctx.args).strip()
    if not text:
        await _reply(update.effective_message, "⚠️ الاستخدام: /setrules نص القواعد هنا أو رد على رسالة بها النص")
        return
    s = chat_settings(rt.bot_id, update.effective_chat.id)
    s["rules_text"] = text
    save_chat_settings(rt.bot_id, update.effective_chat.id, s)
    await _reply(update.effective_message, "✅ تم تحديث القواعد.")


async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup") or not await rt.is_admin(ctx, chat.id, user.id): return
    target = await _target_user(update, ctx)
    reason = " ".join(a for a in (ctx.args or [])
                     if not a.lstrip("-").isdigit() and not a.startswith("@")).strip()
    if not target:
        await _reply(msg, "⚠️ استخدم /ban ردًا على رسالة العضو."); return
    if await rt.is_admin(ctx, chat.id, target):
        await _reply(msg, "⚠️ لا يمكن حظر أدمن."); return
    try:
        await ctx.bot.ban_chat_member(chat.id, target)
        await _reply(msg, f"🚫 تم حظر العضو." + (f"\nالسبب: {safe_html(reason)}" if reason else ""))
        await _log(rt, ctx, chat.id, "حظر", user, target, reason)
    except TelegramError as e:
        await _reply(msg, f"⚠️ {e}")


async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup") or not await rt.is_admin(ctx, chat.id, user.id): return
    target = await _target_user(update, ctx)
    if not target: await _reply(msg, "⚠️ حدد العضو."); return
    try:
        await ctx.bot.unban_chat_member(chat.id, target, only_if_banned=True)
        await _reply(msg, "✅ تم فك الحظر.")
        await _log(rt, ctx, chat.id, "فك حظر", user, target)
    except TelegramError as e:
        await _reply(msg, f"⚠️ {e}")


async def cmd_kick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup") or not await rt.is_admin(ctx, chat.id, user.id): return
    target = await _target_user(update, ctx)
    if not target: await _reply(msg, "⚠️ حدد العضو."); return
    if await rt.is_admin(ctx, chat.id, target):
        await _reply(msg, "⚠️ لا يمكن طرد أدمن."); return
    try:
        await ctx.bot.ban_chat_member(chat.id, target)
        await ctx.bot.unban_chat_member(chat.id, target)
        await _reply(msg, "👢 تم طرد العضو.")
        await _log(rt, ctx, chat.id, "طرد", user, target)
    except TelegramError as e:
        await _reply(msg, f"⚠️ {e}")


async def cmd_mute(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup") or not await rt.is_admin(ctx, chat.id, user.id): return
    target = await _target_user(update, ctx)
    minutes = 0
    for a in (ctx.args or []):
        try: minutes = int(a); break
        except ValueError: pass
    if not target: await _reply(msg, "⚠️ حدد العضو."); return
    if await rt.is_admin(ctx, chat.id, target):
        await _reply(msg, "⚠️ لا يمكن كتم أدمن."); return
    try:
        await _do_mute(rt, ctx, chat.id, target, minutes)
        await _reply(msg, f"🔇 تم كتم العضو {f'لمدة {minutes} د' if minutes else 'حتى إشعار آخر'}.")
        await _log(rt, ctx, chat.id, f"كتم {minutes}د", user, target)
    except TelegramError as e:
        await _reply(msg, f"⚠️ ارفع البوت أدمن بصلاحية الكتم: {e}")


async def cmd_unmute(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup") or not await rt.is_admin(ctx, chat.id, user.id): return
    target = await _target_user(update, ctx)
    if not target: await _reply(msg, "⚠️ حدد العضو."); return
    perms = ChatPermissions(
        can_send_messages=True, can_send_media_messages=True,
        can_send_other_messages=True, can_add_web_page_previews=True,
        can_send_polls=True, can_invite_users=True)
    try:
        await ctx.bot.restrict_chat_member(chat.id, target, perms)
        await _reply(msg, "🔊 تم فك الكتم.")
        await _log(rt, ctx, chat.id, "فك كتم", user, target)
    except TelegramError as e:
        await _reply(msg, f"⚠️ {e}")


async def cmd_warn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup") or not await rt.is_admin(ctx, chat.id, user.id): return
    target = await _target_user(update, ctx)
    reason = " ".join(a for a in (ctx.args or []) if not a.lstrip("-").isdigit() and not a.startswith("@")).strip() or "—"
    if not target: await _reply(msg, "⚠️ استخدم /warn ردًا على رسالة العضو."); return
    if await rt.is_admin(ctx, chat.id, target):
        await _reply(msg, "⚠️ لا يمكن تحذير أدمن."); return
    await _apply_warn(rt, ctx, chat.id, target, reason, by_id=user.id)
    await _log(rt, ctx, chat.id, "تحذير", user, target, reason)


async def cmd_unwarn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup") or not await rt.is_admin(ctx, chat.id, user.id): return
    target = await _target_user(update, ctx)
    if not target: await _reply(msg, "⚠️ حدد العضو."); return
    w = warns(rt.bot_id, chat.id)
    if str(target) in w and w[str(target)]["count"] > 0:
        w[str(target)]["count"] -= 1; save_warns(rt.bot_id, chat.id, w)
        await _reply(msg, f"✅ تم حذف تحذير (تبقى {w[str(target)]['count']}).")
    else:
        await _reply(msg, "لا توجد تحذيرات.")


async def cmd_warns(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat
    if chat.type not in ("group", "supergroup"): return
    target = await _target_user(update, ctx) or update.effective_user.id
    w = warns(rt.bot_id, chat.id).get(str(target), {"count": 0})
    await _reply(msg, f"⚠️ تحذيرات العضو: <b>{w['count']}</b>")


async def cmd_del(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup") or not await rt.is_admin(ctx, chat.id, user.id): return
    if not msg.reply_to_message:
        await _reply(msg, "⚠️ رد على الرسالة المراد حذفها بـ /del"); return
    try:
        await ctx.bot.delete_message(chat.id, msg.reply_to_message.message_id)
        await msg.delete()
    except TelegramError as e:
        await _reply(msg, f"⚠️ {e}")


async def cmd_pin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup") or not await rt.is_admin(ctx, chat.id, user.id): return
    if not msg.reply_to_message:
        await _reply(msg, "⚠️ رد على الرسالة المراد تثبيتها بـ /pin"); return
    try:
        await ctx.bot.pin_chat_message(chat.id, msg.reply_to_message.message_id)
        await _reply(msg, "📌 تم التثبيت.")
    except TelegramError as e:
        await _reply(msg, f"⚠️ {e}")


async def cmd_purge(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup") or not await rt.is_admin(ctx, chat.id, user.id): return
    if not msg.reply_to_message:
        await _reply(msg, "⚠️ رد على رسالة البداية بـ /purge عدد"); return
    try:
        n = int(ctx.args[0]) if ctx.args else 10
    except ValueError:
        n = 10
    n = max(1, min(n, 50))
    end = msg.reply_to_message.message_id
    start = msg.message_id
    deleted = 0
    for mid in range(start - 1, end - 1, -1):
        if deleted >= n: break
        try:
            await ctx.bot.delete_message(chat.id, mid); deleted += 1
        except TelegramError:
            continue
    try:
        await msg.delete()
    except TelegramError:
        pass
    await _delete_after(msg, f"🗑 تم حذف {deleted} رسالة.", 5)


# ═══════════════════════════════════════════════════════════
#  ملاحظات وبلاغات
# ═══════════════════════════════════════════════════════════

async def cmd_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup") or not await rt.is_admin(ctx, chat.id, user.id): return
    args = ctx.args or []
    if not args:
        await _reply(msg, "⚠️ /save الاسم المحتوى"); return
    name = args[0].lower()
    content = " ".join(args[1:])
    if msg.reply_to_message:
        r = msg.reply_to_message
        content = (r.text or r.caption or content)
    if not content:
        await _reply(msg, "⚠️ أكتب محتوى الملاحظة أو رد على رسالة."); return
    s = chat_settings(rt.bot_id, chat.id)
    s.setdefault("notes", {})[name] = content
    save_chat_settings(rt.bot_id, chat.id, s)
    await _reply(msg, f"✅ تم حفظ الملاحظة <code>{safe_html(name)}</code>.")


async def cmd_clear_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup") or not await rt.is_admin(ctx, chat.id, user.id): return
    args = ctx.args or []
    if not args:
        await _reply(msg, "⚠️ /clear الاسم"); return
    s = chat_settings(rt.bot_id, chat.id)
    s.setdefault("notes", {}).pop(args[0].lower(), None)
    save_chat_settings(rt.bot_id, chat.id, s)
    await _reply(msg, "✅ تم حذف الملاحظة.")


async def cmd_notes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat
    if chat.type not in ("group", "supergroup"): return
    s = chat_settings(rt.bot_id, chat.id)
    notes = s.get("notes", {})
    if not notes:
        await _reply(msg, "📋 لا يوجد ملاحظات."); return
    lines = ["📋 <b>الملاحظات:</b>"] + [f"• /note_{safe_html(k)}" for k in notes.keys()]
    await _reply(msg, "\n".join(lines))


async def _note_dispatcher(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat
    if chat.type not in ("group", "supergroup"): return
    cmd = (msg.text or "").split()[0].lstrip("/").split("@")[0]
    if not cmd.startswith("note_") and cmd != "note":
        # ملاحظة: لسه مافيش شيء
        return
    name = cmd[5:] if cmd.startswith("note_") else ((ctx.args[0].lower()) if ctx.args else "")
    if not name:
        await cmd_notes(update, ctx); return
    s = chat_settings(rt.bot_id, chat.id)
    content = s.get("notes", {}).get(name)
    if not content:
        await _reply(msg, "❌ الملاحظة غير موجودة."); return
    await _reply(msg, render_premium_emojis(content))


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rt: ProtectionRuntime = ctx.application.bot_data["runtime"]
    msg = update.effective_message; chat = update.effective_chat; user = update.effective_user
    if chat.type not in ("group", "supergroup"): return
    if not msg.reply_to_message:
        await _reply(msg, "⚠️ رد على الرسالة المراد التبليغ عنها بـ /report"); return
    admins = []
    try:
        async for a in ctx.bot.get_chat_administrators(chat.id):
            if not a.user.is_bot:
                admins.append(a)
    except TelegramError:
        pass
    target = msg.reply_to_message.from_user
    reporter_link = f"tg://user?id={user.id}"
    target_link = f"tg://user?id={target.id}" if target else "#"
    text = (f"🚨 <b>بلاغ في {safe_html(chat.title)}</b>\n"
            f"من: <a href='{reporter_link}'>{safe_html(user.full_name)}</a>\n"
            f"على: <a href='{target_link}'>{safe_html(target.full_name) if target else '?'}</a>\n"
            f"الرسالة: <a href='{msg.reply_to_message.link}'>اضغط هنا</a>")
    sent_any = False
    for a in admins:
        try:
            await ctx.bot.send_message(a.user.id, text, parse_mode=ParseMode.HTML)
            sent_any = True
        except TelegramError:
            pass
    try:
        if sent_any:
            await _reply(msg, "✅ تم إبلاغ الأدمن.", 3)
        else:
            await _reply(msg, "⚠️ تعذر تبليغ الأدمن (راسلهم خاص).", 5)
        await msg.delete()
    except TelegramError:
        pass


# ═══════════════════════════════════════════════════════════
#  تركيب التطبيق
# ═══════════════════════════════════════════════════════════

def _install(app: Application, rt: ProtectionRuntime):
    BOT_OWNER = rt.owner_id
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("rules", cmd_rules))
    app.add_handler(CommandHandler("setrules", cmd_setrules))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("kick", cmd_kick))
    app.add_handler(CommandHandler(["mute", "tmute"], cmd_mute))
    app.add_handler(CommandHandler("unmute", cmd_unmute))
    app.add_handler(CommandHandler("warn", cmd_warn))
    app.add_handler(CommandHandler("unwarn", cmd_unwarn))
    app.add_handler(CommandHandler("warns", cmd_warns))
    app.add_handler(CommandHandler("del", cmd_del))
    app.add_handler(CommandHandler("pin", cmd_pin))
    app.add_handler(CommandHandler("purge", cmd_purge))
    app.add_handler(CommandHandler("save", cmd_save))
    app.add_handler(CommandHandler("clear", cmd_clear_note))
    app.add_handler(CommandHandler("notes", cmd_notes))
    app.add_handler(CommandHandler("note", _note_dispatcher))
    # note_name (ديناميكي) — نستخدم regex على البداية "note_"
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^/note_[A-Za-z0-9_]+"),
        _note_dispatcher))
    app.add_handler(CommandHandler("report", cmd_report))

    # Callback captcha
    app.add_handler(CallbackQueryHandler(on_captcha_cb, pattern=r"^captcha:"))

    # Chat member
    app.add_handler(ChatMemberHandler(chat_member_watcher, ChatMemberHandler.CHAT_MEMBER))
    # Watcher (مضادات) على group=1 عشان يتشاف قبل الردود
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.StatusUpdate.ALL,
        watcher), group=1)


async def build(record: dict, host_app: Application) -> Application:
    rt = ProtectionRuntime(record, host_app)
    defaults = Defaults(link_preview_options=NO_PREVIEW)
    app = (
        Application.builder()
        .token(rt.token)
        .defaults(defaults)
        .build()
    )
    app.bot_data["runtime"] = rt
    _install(app, rt)

    async def on_startup(_app: Application):
        try:
            await _app.bot.delete_webhook(drop_pending_updates=True)
        except TelegramError:
            pass
        try:
            await _app.bot.set_my_commands([
                BotCommand("help", "عرض الأوامر"),
                BotCommand("rules", "قواعد المجموعة"),
                BotCommand("id", "معرفة الآيدي"),
                BotCommand("report", "بلاغ للأدمن"),
                BotCommand("notes", "الملاحظات"),
            ])
        except TelegramError:
            pass
        try:
            me = await _app.bot.get_me()
            await host_app.bot.send_message(
                BOT_OWNER,
                f"🛡️ بوت الحماية <b>{me.full_name}</b> (@{me.username}) يعمل الآن.",
                parse_mode=ParseMode.HTML)
        except Exception:
            pass

    app.post_init = on_startup
    return app
