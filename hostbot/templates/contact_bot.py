"""
قالب بوت التواصل (Contact Bot).
كل نسخة مُستضافة لها OWNER_ID خاص بها (صاحب البوت اللي أضاف التوكن)،
ولها مجلد بيانات مستقل فيه settings.json, users.json, banned.json, msg_map.json, إلخ.

الميزات:
• ترحيب مخصص + أزرار
• تحويل جميع رسائل الأعضاء لصاحب البوت
• رد ثنائي الاتجاه (Reply على المحوَّلة يردّ على العضو)
• رد سريع، رد تلقائي بالكلمات، رد بالذكاء الاصطناعي
• حظر/كتم/تأجيل/حذف رسائل العضو
• بث للجميع، تثبيت عام
• حماية محتوى، إيموجي بريميوم، نسخ احتياطي/استعادة
"""

from __future__ import annotations

import asyncio
import json
import html
import logging
import os
import re
import time
import urllib.error
import urllib.request
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", category=UserWarning,
                        message=r".*CallbackQueryHandler.*")

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    LinkPreviewOptions, ReactionTypeEmoji, ReplyParameters, MessageEntity,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, MessageReactionHandler, ChatMemberHandler,
    filters, ContextTypes, Defaults,
)

from ._common import (
    VALID_BUTTON_STYLES, bot_dir, load_json, save_json, safe_html,
    user_mention, render_premium_emojis, prepare_ai_telegram_html,
    make_reply_params, parse_buttons_text,
)
from .. import storage

logger = logging.getLogger(__name__)

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


# ═══════════════════════════════════════════════════════════
#  الإعدادات الافتراضية
# ═══════════════════════════════════════════════════════════

DEFAULT_WELCOME = (
    "مرحبًا بك في بوت التواصل. 👋\n\n"
    "يمكنك إرسال رسائلك واستفساراتك، وسيتم الاطلاع عليها والرد في أقرب وقت."
)
DEFAULT_BUTTONS: list[dict] = []
DEFAULT_AWAY_MSG = "🌙 أنا حالياً غير متاح. سيتم الرد على رسالتك في أقرب وقت ممكن."
DEFAULT_QUICK_REPLY = "⚡ تم استلام رسالتك، سيتم الرد عليك في أقرب وقت."
DEFAULT_AI_INSTRUCTIONS = (
    "أنت مساعد ذكي ولبق لبوت تليجرام. مهمتك الرد على استفسارات المستخدمين "
    "بأسلوب احترافي ومختصر ومفيد ومهذب. أرسل الرد بصيغة Telegram HTML فقط."
)


# ═══════════════════════════════════════════════════════════
#  حالات المحادثة
# ═══════════════════════════════════════════════════════════

(AWAIT_WELCOME, AWAIT_BUTTONS, AWAIT_BROADCAST, AWAIT_AWAY,
 AWAIT_AUTO_KW, AWAIT_QUICK, AWAIT_AI_PROMPT, AWAIT_AI_KEY,
 AWAIT_AI_MODEL, AWAIT_BAN_REASON) = range(10)


class ContactBotRuntime:
    """الحالة الذاكرية لكل نسخة بوت تواصل."""

    def __init__(self, record: dict, host_app: Application):
        self.bot_id = int(record["id"])
        self.token = record["token"]
        self.owner_id = int(record["owner_id"])
        self.host_app = host_app  # تطبيق المنصة (نستخدمه لإشعارات المالك العام إن لزم)
        self.msg_map: dict[int, tuple[int, int | None]] = {}  # owner_msg_id → (uid, user_msg_id)
        self.reply_map: dict[int, tuple[int, int]] = {}       # sent_at_user → (owner_reply_id, uid)
        self.owner_sent_map: dict[int, dict] = {}
        self.pending_silent: dict[int, int] = {}              # owner_id → uid بانتظار رسالة صامتة

    # ── إعدادات ────────────────────────────────────────────
    def settings_file(self) -> Path:
        return bot_dir(self.bot_id) / "settings.json"

    def load_settings(self) -> dict:
        d = load_json(self.bot_id, "settings.json", {})
        d.setdefault("welcome", DEFAULT_WELCOME)
        d.setdefault("buttons", list(DEFAULT_BUTTONS))
        d.setdefault("away_enabled", False)
        d.setdefault("away_msg", DEFAULT_AWAY_MSG)
        d.setdefault("autoresponder_enabled", False)
        d.setdefault("auto_replies", [])
        d.setdefault("quick_reply_enabled", False)
        d.setdefault("quick_reply_msg", DEFAULT_QUICK_REPLY)
        d.setdefault("ai_enabled", False)
        d.setdefault("ai_instructions", DEFAULT_AI_INSTRUCTIONS)
        d.setdefault("ai_api_key", "")
        d.setdefault("ai_model", "gpt-4o-mini")
        d.setdefault("ai_base_url", "https://api.openai.com/v1")
        d.setdefault("protect_content_enabled", False)
        d.setdefault("global_pin", {"source_message_id": None, "targets": {}, "updated_at": 0})
        return d

    def save_settings(self, s: dict):
        save_json(self.bot_id, "settings.json", s)

    def protect_kwargs(self, chat_id: int) -> dict:
        try:
            if chat_id is not None and int(chat_id) == self.owner_id:
                return {}
            if self.load_settings().get("protect_content_enabled"):
                return {"protect_content": True}
        except Exception:
            pass
        return {}

    # ── مستخدمون/محظورون ──────────────────────────────────
    def load_users(self) -> set[int]:
        return set(load_json(self.bot_id, "users.json", []))

    def save_users(self, u: set[int]):
        save_json(self.bot_id, "users.json", list(u))

    def load_banned(self) -> set[int]:
        records = load_json(self.bot_id, "banned.json", {})
        now = time.time()
        active = set()
        changed = False
        if isinstance(records, list):
            new_records = {}
            for i, x in enumerate(records):
                if isinstance(x, dict) and x.get("user_id"):
                    new_records[str(x["user_id"])] = x
                elif isinstance(x, (int, str)):
                    try:
                        new_records[str(int(x))] = {
                            "user_id": int(x), "reason": "لم يُحدد",
                            "banned_at": 0, "expires_at": None, "duration_key": "permanent"
                        }
                    except (TypeError, ValueError):
                        pass
            records = new_records
            changed = True
        kept = {}
        for k, v in records.items():
            try:
                expires = v.get("expires_at")
                if expires and float(expires) <= now:
                    changed = True
                    continue
                kept[k] = v
                active.add(int(k))
            except Exception:
                pass
        if changed:
            save_json(self.bot_id, "banned.json", kept)
        return active

    def save_banned_set(self, b: set[int]):
        # نحتفظ بسجلات الحظر الموجودة ونضيف الجدد بدون سبب
        current = load_json(self.bot_id, "banned.json", {})
        if isinstance(current, list):
            current = {str(x.get("user_id", i)): x for i, x in enumerate(current) if isinstance(x, dict)}
        for uid in b:
            key = str(int(uid))
            if key not in current:
                current[key] = {
                    "user_id": int(uid),
                    "reason": "لم يُحدد سبب",
                    "banned_at": time.time(),
                    "expires_at": None,
                    "duration_key": "permanent",
                }
        # احذف اللي خرجوا من المجموعة
        wanted = {str(int(x)) for x in b}
        current = {k: v for k, v in current.items() if k in wanted}
        save_json(self.bot_id, "banned.json", current)

    def ban_user(self, uid: int, reason: str = "", duration_key: str = "permanent"):
        BAN_OPTS = {
            "1h": 3600, "6h": 6*3600, "12h": 12*3600,
            "1d": 86400, "3d": 3*86400, "7d": 7*86400, "30d": 30*86400,
            "permanent": None,
        }
        secs = BAN_OPTS.get(duration_key)
        now = time.time()
        expires = (now + secs) if secs else None
        current = load_json(self.bot_id, "banned.json", {})
        if isinstance(current, list):
            current = {}
        current[str(int(uid))] = {
            "user_id": int(uid),
            "reason": reason or "لم يُحدد سبب",
            "banned_at": now,
            "expires_at": expires,
            "duration_key": duration_key,
        }
        save_json(self.bot_id, "banned.json", current)

        # جدولة فك الحظر
        if expires and hasattr(self, "_job_register"):
            self._schedule_unban(uid, expires)

    def unban_user(self, uid: int):
        current = load_json(self.bot_id, "banned.json", {})
        if isinstance(current, list):
            current = {}
        current.pop(str(int(uid)), None)
        save_json(self.bot_id, "banned.json", current)

    def _schedule_unban(self, uid: int, at: float):
        pass  # سيتم تنفيذه في build() باستخدام job_queue

    # ── msg_map ────────────────────────────────────────────
    def load_msg_map(self):
        raw = load_json(self.bot_id, "msg_map.json", {})
        self.msg_map = {int(k): tuple(v) for k, v in raw.items()}

    def save_msg_map(self):
        save_json(self.bot_id, "msg_map.json",
                  {str(k): list(v) for k, v in self.msg_map.items()})

    def record_message(self, uid: int, side: str, message_id: int, kind: str):
        """تسجيل رسالة في سجل الرسائل (لإمكانية الحذف لاحقاً)."""
        if side not in ("owner", "user"):
            return
        records = load_json(self.bot_id, "message_records.json", {})
        key = str(int(uid))
        b = records.setdefault(key, {"owner": [], "user": [], "created_at": time.time()})
        if "owner" not in b or not isinstance(b["owner"], list):
            b["owner"] = []
        if "user" not in b or not isinstance(b["user"], list):
            b["user"] = []
        items = b[side]
        if not any(int(i.get("id", 0)) == int(message_id) for i in items):
            items.append({"id": int(message_id), "kind": kind, "created_at": time.time()})
        save_json(self.bot_id, "message_records.json", records)

    # ── AI ─────────────────────────────────────────────────
    def _ai_sync_call(self, prompt: str, system: str, api_key: str,
                      model: str, base_url: str) -> str:
        url = base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0",
        }
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "temperature": 0.7,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res["choices"][0]["message"]["content"].strip()

    async def ai_reply(self, prompt: str) -> str:
        s = self.load_settings()
        api_key = s.get("ai_api_key", "").strip()
        if not api_key:
            raise RuntimeError("مفتاح الذكاء الاصطناعي غير مضبوط.")
        system = s.get("ai_instructions", DEFAULT_AI_INSTRUCTIONS) + (
            "\n\nتنسيق الإرسال: Telegram HTML فقط، بدون Markdown أو ```."
        )
        return await asyncio.to_thread(
            self._ai_sync_call, prompt, system, api_key,
            s.get("ai_model", "gpt-4o-mini"),
            s.get("ai_base_url", "https://api.openai.com/v1"),
        )

    # ── لوحة المالك ───────────────────────────────────────
    def _mk_btn(self, text: str, style: str | None = None, **kw) -> InlineKeyboardButton:
        api_kwargs: dict = {}
        if style in VALID_BUTTON_STYLES:
            api_kwargs["style"] = style
        m = list(PREMIUM_EMOJI_RE.finditer(text))
        if m:
            api_kwargs["icon_custom_emoji_id"] = m[0].group(1)
            text = PREMIUM_EMOJI_RE.sub("", text)
            text = re.sub(r"\s{2,}", " ", text).strip()
        if api_kwargs:
            kw.setdefault("api_kwargs", {}).update(api_kwargs)
        return InlineKeyboardButton(text, **kw)

    def owner_keyboard(self) -> InlineKeyboardMarkup:
        s = self.load_settings()
        rows = [
            [self._mk_btn("✏️ رسالة الترحيب", "primary", callback_data="c_edit_welcome"),
             self._mk_btn("🔗 الأزرار", "primary", callback_data="c_edit_buttons")],
            [self._mk_btn("👁️ عرض الإعدادات", "primary", callback_data="c_view_set")],
            [self._mk_btn("📢 بث للجميع", "primary", callback_data="c_broadcast")],
            [self._mk_btn("👥 المستخدمون", "primary", callback_data="c_users:0"),
             self._mk_btn("🚫 المحظورون", "danger", callback_data="c_banned_list")],
            [self._mk_btn(
                ("🟢 وضع الغياب: مفعّل" if s["away_enabled"] else "🔴 وضع الغياب: معطّل"),
                "success" if s["away_enabled"] else "danger",
                callback_data="c_toggle_away")],
            [self._mk_btn("✏️ تعديل رسالة الغياب", "primary", callback_data="c_edit_away")],
            [self._mk_btn(
                ("🟢 الرد التلقائي: مفعّل" if s.get("autoresponder_enabled") else "🔴 الرد التلقائي: معطّل"),
                "success" if s.get("autoresponder_enabled") else "danger",
                callback_data="c_auto_menu")],
            [self._mk_btn(
                ("🟢 الرد السريع: مفعّل" if s.get("quick_reply_enabled") else "🔴 الرد السريع: معطّل"),
                "success" if s.get("quick_reply_enabled") else "danger",
                callback_data="c_quick_menu")],
            [self._mk_btn(
                ("🟢 الذكاء الاصطناعي: مفعّل" if s.get("ai_enabled") else "🔴 الذكاء الاصطناعي: معطّل"),
                "success" if s.get("ai_enabled") else "danger",
                callback_data="c_ai_menu")],
            [self._mk_btn(
                ("🟢 حماية المحتوى: مفعّلة" if s.get("protect_content_enabled") else "🔴 حماية المحتوى: معطّلة"),
                "success" if s.get("protect_content_enabled") else "danger",
                callback_data="c_toggle_protect")],
            [self._mk_btn("🔄 إعادة الإعدادات", "danger", callback_data="c_reset")],
        ]
        return InlineKeyboardMarkup(rows)

    def welcome_kb(self, buttons: list[dict]) -> InlineKeyboardMarkup:
        kb = []
        row = []
        for b in buttons:
            row.append(self._mk_btn(b["text"], b.get("style", "success"), url=b["url"]))
            if len(row) == 2:
                kb.append(row); row = []
        if row:
            kb.append(row)
        return InlineKeyboardMarkup(kb)


# ═══════════════════════════════════════════════════════════
#  Handlers — دوال المعالجة (closures على الـ runtime)
# ═══════════════════════════════════════════════════════════

def _install_handlers(app: Application, rt: ContactBotRuntime):
    OWNER = rt.owner_id

    # ── /start ──────────────────────────────────────────
    async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat
        if chat.type in ("group", "supergroup"):
            await update.message.reply_text(
                "اضغط الزر للتواصل بالخاص 👇",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("تواصل بالخاص 💬",
                                         url=f"https://t.me/{ctx.bot.username}")
                ]]))
            return
        if user.id == OWNER:
            await update.message.reply_text(
                "⚙️ لوحة تحكم البوت\nمرحباً بك 👋",
                reply_markup=rt.owner_keyboard())
            return
        users = rt.load_users(); users.add(user.id); rt.save_users(users)
        s = rt.load_settings()
        if s.get("quick_reply_enabled"):
            sent = await update.message.reply_text(
                render_premium_emojis(s.get("quick_reply_msg", DEFAULT_QUICK_REPLY)),
                parse_mode=ParseMode.HTML, **rt.protect_kwargs(user.id))
        else:
            text = s["welcome"].replace("{user_link}", user_mention(user))
            sent = await update.message.reply_text(
                render_premium_emojis(text),
                reply_markup=rt.welcome_kb(s["buttons"]),
                parse_mode=ParseMode.HTML, **rt.protect_kwargs(user.id))
        # إشعار المالك
        uname = f"@{user.username}" if user.username else "لا يوجد"
        try:
            join = await ctx.bot.send_message(
                OWNER,
                f"👤 دخل شخص إلى البوت\n\n"
                f"الاسم: {user.full_name}\n"
                f"المعرف: {uname}\n"
                f"الآيدي: <code>{user.id}</code>",
                parse_mode=ParseMode.HTML,
            )
            rt.msg_map[join.message_id] = (user.id, None)
            rt.record_message(user.id, "owner", join.message_id, "join")
            rt.save_msg_map()
        except TelegramError:
            pass

    # ── تحويل رسائل الأعضاء ────────────────────────────
    async def user_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        msg = update.effective_message
        if user.id in rt.load_banned():
            return
        users = rt.load_users(); users.add(user.id); rt.save_users(users)
        s = rt.load_settings()

        # الرد السريع أولوية
        if s.get("quick_reply_enabled"):
            await msg.reply_text(
                render_premium_emojis(s.get("quick_reply_msg", DEFAULT_QUICK_REPLY)),
                parse_mode=ParseMode.HTML, **rt.protect_kwargs(user.id))
        # رد تلقائي بكلمة
        text_content = (msg.text or msg.caption or "")
        auto_item = None
        if s.get("autoresponder_enabled") and not s.get("quick_reply_enabled"):
            low = text_content.lower()
            for it in s.get("auto_replies", []):
                kw = (it.get("keyword") or "").strip()
                if kw and kw.lower() in low:
                    auto_item = it
                    break
            if auto_item:
                try:
                    await ctx.bot.send_message(
                        user.id, render_premium_emojis(auto_item["reply"]),
                        parse_mode=ParseMode.HTML, **rt.protect_kwargs(user.id))
                except TelegramError:
                    pass
            elif s.get("away_enabled"):
                await msg.reply_text(render_premium_emojis(s["away_msg"]),
                                     parse_mode=ParseMode.HTML, **rt.protect_kwargs(user.id))
        elif s.get("away_enabled") and not s.get("quick_reply_enabled"):
            await msg.reply_text(render_premium_emojis(s["away_msg"]),
                                 parse_mode=ParseMode.HTML, **rt.protect_kwargs(user.id))

        # رد ذكاء اصطناعي
        ai_reply_sent = None
        if s.get("ai_enabled") and not s.get("quick_reply_enabled") and not auto_item and text_content:
            try:
                ai_text = await rt.ai_reply(text_content)
                formatted = prepare_ai_telegram_html(ai_text)
                try:
                    ai_reply_sent = await msg.reply_text(
                        formatted, parse_mode=ParseMode.HTML,
                        **rt.protect_kwargs(user.id))
                except TelegramError:
                    ai_reply_sent = await msg.reply_text(ai_text, **rt.protect_kwargs(user.id))
            except Exception as e:
                logger.warning(f"AI reply failed: {e}")

        # تحويل الرسالة للمالك
        try:
            fwd = await ctx.bot.forward_message(OWNER, msg.chat_id, msg.message_id)
            rt.msg_map[fwd.message_id] = (user.id, msg.message_id)
            rt.record_message(user.id, "owner", fwd.message_id, "forward")
            rt.save_msg_map()
        except TelegramError as e:
            logger.warning(f"forward failed: {e}")
            return

        # إشعار المالك بالرد التلقائي / AI
        if auto_item:
            try:
                await ctx.bot.send_message(
                    OWNER,
                    f"🤖 <b>رد تلقائي</b> — الكلمة: <code>{safe_html(auto_item['keyword'])}</code>\n\n{auto_item['reply']}",
                    parse_mode=ParseMode.HTML,
                    reply_parameters=make_reply_params(fwd.message_id),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🗑 حذف الرد", callback_data=f"c_recall:{user.id}:0",
                                             api_kwargs={"style": "danger"})
                    ]]))
            except TelegramError:
                pass
        if ai_reply_sent:
            try:
                await ctx.bot.send_message(
                    OWNER,
                    "🤖 <b>رد الذكاء الاصطناعي أُرسل</b>\n\n" + prepare_ai_telegram_html(text_content and "[تم إرسال رد]"),
                    parse_mode=ParseMode.HTML,
                    reply_parameters=make_reply_params(fwd.message_id))
            except TelegramError:
                pass

    # ── رد المالك ─────────────────────────────────────
    async def owner_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        msg = update.effective_message
        if msg.text and msg.text.strip() == "/panel":
            await msg.reply_text("⚙️ لوحة تحكم البوت", reply_markup=rt.owner_keyboard())
            return
        if not msg.reply_to_message:
            return
        rid = msg.reply_to_message.message_id
        if rid not in rt.msg_map:
            return
        uid, user_mid = rt.msg_map[rid]
        try:
            sent = await ctx.bot.copy_message(
                chat_id=uid, from_chat_id=OWNER, message_id=msg.message_id,
                reply_parameters=make_reply_params(user_mid) if user_mid else None,
                **rt.protect_kwargs(uid))
        except TelegramError as e:
            await msg.reply_text(f"⚠️ فشل الإرسال: {e}")
            return
        rt.reply_map[sent.message_id] = (msg.message_id, uid)
        rt.record_message(uid, "user", sent.message_id, "owner_reply")
        rt.owner_sent_map[msg.message_id] = {"user_id": uid, "sent_msg_id": sent.message_id}
        await msg.reply_text("✅ تم الإرسال.",
                             reply_markup=InlineKeyboardMarkup([[
                                 InlineKeyboardButton("🗑 استرداد",
                                                      callback_data=f"c_recall:{uid}:{sent.message_id}",
                                                      api_kwargs={"style": "danger"})
                             ]]))

    async def private_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id == OWNER:
            await owner_reply(update, ctx)
        else:
            await user_message(update, ctx)

    # ── Callbacks (لوحة تحكم مبسّطة) ──────────────────
    async def cb_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        d = q.data
        await q.answer()
        if d == "c_edit_welcome":
            await q.edit_message_text("✏️ أرسل رسالة الترحيب الجديدة (أو /cancel):")
            return AWAIT_WELCOME
        if d == "c_edit_buttons":
            await q.edit_message_text(
                "🔗 أرسل الأزرار بصيغة: نص | رابط | لون (كل سطر زر).\n"
                "الألوان: primary / success / danger\n\nمثال:\nقناتي | https://t.me/xx | primary\nأو /cancel")
            return AWAIT_BUTTONS
        if d == "c_view_set":
            s = rt.load_settings()
            btns = "\n".join(f"• {b['text']} → {b['url']}" for b in s["buttons"]) or "لا يوجد"
            away = "🟢" if s["away_enabled"] else "🔴"
            ar = "🟢" if s.get("autoresponder_enabled") else "🔴"
            qr = "🟢" if s.get("quick_reply_enabled") else "🔴"
            ai = "🟢" if s.get("ai_enabled") else "🔴"
            prot = "🟢" if s.get("protect_content_enabled") else "🔴"
            await q.message.reply_text(
                f"<b>📝 الترحيب:</b>\n{s['welcome']}\n\n"
                f"<b>🔗 الأزرار:</b>\n{btns}\n\n"
                f"🌙 الغياب: {away} | 🤖 تلقائي: {ar} | ⚡ سريع: {qr}\n"
                f"🧠 AI: {ai} | 🔒 الحماية: {prot}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="c_back")
                ]]))
            return ConversationHandler.END
        if d == "c_toggle_away":
            s = rt.load_settings(); s["away_enabled"] = not s["away_enabled"]
            rt.save_settings(s)
            await q.edit_message_text("⚙️ لوحة التحكم", reply_markup=rt.owner_keyboard())
            return ConversationHandler.END
        if d == "c_toggle_protect":
            s = rt.load_settings()
            s["protect_content_enabled"] = not s.get("protect_content_enabled", False)
            rt.save_settings(s)
            await q.edit_message_text("⚙️ لوحة التحكم", reply_markup=rt.owner_keyboard())
            return ConversationHandler.END
        if d == "c_edit_away":
            await q.edit_message_text("✏️ أرسل رسالة الغياب الجديدة (أو /cancel):")
            return AWAIT_AWAY
        if d == "c_broadcast":
            await q.edit_message_text("📢 أرسل الرسالة/الوسيط اللي عايز تبثه للجميع (أو /cancel):")
            return AWAIT_BROADCAST
        if d == "c_reset":
            s = {"welcome": DEFAULT_WELCOME, "buttons": [], "away_enabled": False,
                 "away_msg": DEFAULT_AWAY_MSG, "autoresponder_enabled": False,
                 "auto_replies": [], "quick_reply_enabled": False,
                 "quick_reply_msg": DEFAULT_QUICK_REPLY,
                 "ai_enabled": False, "ai_instructions": DEFAULT_AI_INSTRUCTIONS,
                 "ai_api_key": "", "ai_model": "gpt-4o-mini",
                 "ai_base_url": "https://api.openai.com/v1",
                 "protect_content_enabled": False,
                 "global_pin": {"source_message_id": None, "targets": {}, "updated_at": 0}}
            rt.save_settings(s)
            await q.edit_message_text("✅ تمت إعادة الإعدادات للأصل.", reply_markup=rt.owner_keyboard())
            return ConversationHandler.END
        if d == "c_back":
            await q.message.reply_text("⚙️ لوحة التحكم", reply_markup=rt.owner_keyboard())
            return ConversationHandler.END
        if d == "c_auto_menu":
            s = rt.load_settings()
            en = s.get("autoresponder_enabled", False)
            items = s.get("auto_replies", [])
            lines = [f"🤖 <b>الرد التلقائي</b> — {'مفعّل' if en else 'معطّل'}\n"]
            rows = []
            for i, it in enumerate(items):
                lines.append(f"{i+1}. <b>{safe_html(it['keyword'])}</b> ⬅ {safe_html(it['reply'])[:50]}")
                rows.append([InlineKeyboardButton(f"🗑 {it['keyword']}"[:30],
                                                  callback_data=f"c_auto_del:{i}")])
            rows.insert(0, [InlineKeyboardButton(
                "🔴 تعطيل" if en else "🟢 تفعيل", callback_data="c_auto_toggle")])
            rows.insert(1, [InlineKeyboardButton("➕ إضافة كلمة", callback_data="c_auto_add")])
            rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="c_back")])
            await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML,
                                       reply_markup=InlineKeyboardMarkup(rows))
            return ConversationHandler.END
        if d == "c_auto_toggle":
            s = rt.load_settings()
            s["autoresponder_enabled"] = not s.get("autoresponder_enabled", False)
            rt.save_settings(s); await q.answer("تم التبديل")
            # إعادة رسم القائمة
            s = rt.load_settings()
            en = s.get("autoresponder_enabled")
            await q.edit_message_text(
                f"🤖 الرد التلقائي — {'مفعّل' if en else 'معطّل'}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="c_auto_menu")
                ]]))
            return ConversationHandler.END
        if d == "c_auto_add":
            await q.edit_message_text(
                "➕ أرسل الكلمة والرد بصيغة:\nالكلمة | الرد\n\nأو /cancel")
            return AWAIT_AUTO_KW
        if d.startswith("c_auto_del:"):
            idx = int(d.split(":")[1])
            s = rt.load_settings()
            items = s.get("auto_replies", [])
            if 0 <= idx < len(items):
                items.pop(idx); s["auto_replies"] = items; rt.save_settings(s)
            await q.answer("تم الحذف")
            # re-render simple
            await q.edit_message_text("🤖 تم تحديث القائمة.",
                                       reply_markup=InlineKeyboardMarkup([[
                                           InlineKeyboardButton("🔙 رجوع", callback_data="c_auto_menu")
                                       ]]))
            return ConversationHandler.END
        if d == "c_quick_menu":
            s = rt.load_settings()
            en = s.get("quick_reply_enabled", False)
            await q.edit_message_text(
                f"⚡ <b>الرد السريع</b> — {'مفعّل' if en else 'معطّل'}\n\n"
                f"النص الحالي:\n{safe_html(s.get('quick_reply_msg', ''))}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔴 تعطيل" if en else "🟢 تفعيل",
                                          callback_data="c_quick_toggle")],
                    [InlineKeyboardButton("✏️ تعديل النص", callback_data="c_quick_edit")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="c_back")],
                ]))
            return ConversationHandler.END
        if d == "c_quick_toggle":
            s = rt.load_settings()
            s["quick_reply_enabled"] = not s.get("quick_reply_enabled", False)
            rt.save_settings(s)
            await q.edit_message_text("⚙️ لوحة التحكم", reply_markup=rt.owner_keyboard())
            return ConversationHandler.END
        if d == "c_quick_edit":
            await q.edit_message_text("✏️ أرسل نص الرد السريع الجديد (أو /cancel):")
            return AWAIT_QUICK
        if d == "c_ai_menu":
            s = rt.load_settings()
            en = s.get("ai_enabled", False)
            key = s.get("ai_api_key", "")
            key_status = f"✅ (آخر 4 حروف: ...{key[-4:]})" if key else "⚠️ غير مدخل"
            await q.edit_message_text(
                f"🤖 <b>الذكاء الاصطناعي</b> — {'🟢 مفعّل' if en else '🔴 معطّل'}\n\n"
                f"المفتاح: {key_status}\n"
                f"الموديل: <code>{safe_html(s.get('ai_model', 'gpt-4o-mini'))}</code>\n",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔴 تعطيل" if en else "🟢 تفعيل",
                                          callback_data="c_ai_toggle")],
                    [InlineKeyboardButton("✏️ التعليمات", callback_data="c_ai_prompt")],
                    [InlineKeyboardButton("🔑 المفتاح", callback_data="c_ai_key")],
                    [InlineKeyboardButton("⚙️ الموديل", callback_data="c_ai_model")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="c_back")],
                ]))
            return ConversationHandler.END
        if d == "c_ai_toggle":
            s = rt.load_settings(); s["ai_enabled"] = not s.get("ai_enabled", False)
            rt.save_settings(s)
            await q.edit_message_text("⚙️ لوحة التحكم", reply_markup=rt.owner_keyboard())
            return ConversationHandler.END
        if d == "c_ai_prompt":
            await q.edit_message_text("✏️ أرسل التعليمات الجديدة للـ AI (System Prompt):\nأو /cancel")
            return AWAIT_AI_PROMPT
        if d == "c_ai_key":
            await q.edit_message_text("🔑 أرسل مفتاح الـ API Key:\nأو /cancel")
            return AWAIT_AI_KEY
        if d == "c_ai_model":
            await q.edit_message_text("⚙️ أرسل اسم الموديل (مثل gpt-4o-mini, deepseek-chat):\nأو /cancel")
            return AWAIT_AI_MODEL
        if d.startswith("c_recall:"):
            try:
                _, uid_s, mid_s = d.split(":")
                uid, mid = int(uid_s), int(mid_s)
                if mid:
                    await ctx.bot.delete_message(uid, mid)
                await q.edit_message_text("🗑 تم حذف الرد.")
            except Exception as e:
                await q.edit_message_text(f"⚠️ {e}")
            return ConversationHandler.END
        if d == "c_banned_list":
            banned = rt.load_banned()
            if not banned:
                await q.message.reply_text("لا يوجد محظورون ✅",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 رجوع", callback_data="c_back")]]))
                return ConversationHandler.END
            lines = ["🚫 <b>المحظورون:</b>\n"]
            for uid in list(banned)[:20]:
                lines.append(f"• <code>{uid}</code>")
            await q.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="c_back")]]))
            return ConversationHandler.END
        if d.startswith("c_users:"):
            users = sorted(rt.load_users())
            lines = [f"👥 <b>المستخدمون ({len(users)}):</b>\n"]
            for uid in users[:20]:
                lines.append(f"• <code>{uid}</code>")
            await q.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="c_back")]]))
            return ConversationHandler.END
        return ConversationHandler.END

    # ── استقبال المدخلات (Conversations) ──────────────
    async def recv_welcome(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER: return ConversationHandler.END
        s = rt.load_settings(); s["welcome"] = update.message.text; rt.save_settings(s)
        await update.message.reply_text("✅ تم التحديث.", reply_markup=rt.owner_keyboard())
        return ConversationHandler.END

    async def recv_buttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER: return ConversationHandler.END
        buttons = parse_buttons_text(update.message.text)
        s = rt.load_settings(); s["buttons"] = buttons; rt.save_settings(s)
        await update.message.reply_text(f"✅ تم حفظ {len(buttons)} زر.", reply_markup=rt.owner_keyboard())
        return ConversationHandler.END

    async def recv_away(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER: return ConversationHandler.END
        s = rt.load_settings(); s["away_msg"] = update.message.text; rt.save_settings(s)
        await update.message.reply_text("✅ تم التحديث.", reply_markup=rt.owner_keyboard())
        return ConversationHandler.END

    async def recv_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER: return ConversationHandler.END
        users = rt.load_users() - rt.load_banned() - {OWNER}
        ok = fail = 0
        for uid in users:
            try:
                await ctx.bot.copy_message(uid, OWNER, update.message.message_id,
                                           **rt.protect_kwargs(uid))
                ok += 1
            except TelegramError:
                fail += 1
        await update.message.reply_text(f"✅ البث انتهى — نجح: {ok} | فشل: {fail}",
                                        reply_markup=rt.owner_keyboard())
        return ConversationHandler.END

    async def recv_auto_kw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER: return ConversationHandler.END
        txt = update.message.text.strip()
        if "|" not in txt:
            await update.message.reply_text("⚠️ الصيغة: الكلمة | الرد")
            return AWAIT_AUTO_KW
        kw, rp = txt.split("|", 1)
        kw, rp = kw.strip(), rp.strip()
        if not kw or not rp:
            await update.message.reply_text("⚠️ الكلمة والرد مطلوبان.")
            return AWAIT_AUTO_KW
        s = rt.load_settings()
        s.setdefault("auto_replies", []).append({"keyword": kw, "reply": rp})
        rt.save_settings(s)
        await update.message.reply_text("✅ تم الإضافة.", reply_markup=rt.owner_keyboard())
        return ConversationHandler.END

    async def recv_quick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER: return ConversationHandler.END
        s = rt.load_settings(); s["quick_reply_msg"] = update.message.text; rt.save_settings(s)
        await update.message.reply_text("✅ تم التحديث.", reply_markup=rt.owner_keyboard())
        return ConversationHandler.END

    async def recv_ai_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER: return ConversationHandler.END
        s = rt.load_settings(); s["ai_instructions"] = update.message.text; rt.save_settings(s)
        await update.message.reply_text("✅ تم التحديث.", reply_markup=rt.owner_keyboard())
        return ConversationHandler.END

    async def recv_ai_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER: return ConversationHandler.END
        s = rt.load_settings(); s["ai_api_key"] = update.message.text.strip(); rt.save_settings(s)
        await update.message.reply_text("✅ تم الحفظ.", reply_markup=rt.owner_keyboard())
        return ConversationHandler.END

    async def recv_ai_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER: return ConversationHandler.END
        s = rt.load_settings(); s["ai_model"] = update.message.text.strip(); rt.save_settings(s)
        await update.message.reply_text("✅ تم التغيير.", reply_markup=rt.owner_keyboard())
        return ConversationHandler.END

    async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ ألغيت.", reply_markup=rt.owner_keyboard())
        return ConversationHandler.END

    # ── أوامر إدارية ───────────────────────────────────
    async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER: return
        msg = update.effective_message; target = None; reason = ""
        if msg.reply_to_message and msg.reply_to_message.message_id in rt.msg_map:
            target = rt.msg_map[msg.reply_to_message.message_id][0]
            reason = " ".join(ctx.args).strip()
        elif ctx.args:
            try: target = int(ctx.args[0])
            except ValueError:
                await msg.reply_text("⚠️ آيدي غير صالح."); return
            reason = " ".join(ctx.args[1:]).strip()
        if not target:
            await msg.reply_text("⚠️ حدّد المستخدم (ردًا على رسالته أو /ban ID سبب)."); return
        rt.ban_user(target, reason or "بدون سبب", "permanent")
        await msg.reply_text(f"🚫 تم حظر <code>{target}</code>.", parse_mode=ParseMode.HTML)

    async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER: return
        msg = update.effective_message; target = None
        if msg.reply_to_message and msg.reply_to_message.message_id in rt.msg_map:
            target = rt.msg_map[msg.reply_to_message.message_id][0]
        elif ctx.args:
            try: target = int(ctx.args[0])
            except ValueError: pass
        if not target:
            await msg.reply_text("⚠️ حدّد المستخدم."); return
        rt.unban_user(target)
        await msg.reply_text(f"✅ تم فك الحظر عن <code>{target}</code>.", parse_mode=ParseMode.HTML)

    async def cmd_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER: return
        await update.message.reply_text("⚙️ لوحة التحكم", reply_markup=rt.owner_keyboard())

    # ── تسجيل Handlers ────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("panel", cmd_panel))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_handler)],
        states={
            AWAIT_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER), recv_welcome)],
            AWAIT_BUTTONS: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER), recv_buttons)],
            AWAIT_AWAY:    [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER), recv_away)],
            AWAIT_BROADCAST: [MessageHandler(~filters.COMMAND & filters.User(OWNER), recv_broadcast)],
            AWAIT_AUTO_KW: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER), recv_auto_kw)],
            AWAIT_QUICK:   [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER), recv_quick)],
            AWAIT_AI_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER), recv_ai_prompt)],
            AWAIT_AI_KEY:  [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER), recv_ai_key)],
            AWAIT_AI_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER), recv_ai_model)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True, per_user=True, per_message=False,
    )
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, private_handler))

    # أمر بديل: أي رسالة نصية في الخاص من المالك مش رد على شيء → افتح اللوحة
    # (لا، بيستخدم /panel عوضاً عن ذلك.)

    # حماية من إضافة البوت لمجموعات غريبة بلا إذن المالك
    async def my_chat_member(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        mc = update.my_chat_member
        if not mc: return
        if mc.chat.type in ("group", "supergroup") and mc.new_chat_member.status in ("member", "administrator"):
            try:
                m = await ctx.bot.get_chat_member(mc.chat.id, OWNER)
                if m.status in ("left", "kicked"):
                    await ctx.bot.leave_chat(mc.chat.id)
            except TelegramError:
                pass

    app.add_handler(ChatMemberHandler(my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))


# ═══════════════════════════════════════════════════════════
#  نقطة البناء (يستدعيها المدير)
# ═══════════════════════════════════════════════════════════

async def build(record: dict, host_app: Application) -> Application:
    rt = ContactBotRuntime(record, host_app)
    rt.load_msg_map()

    defaults = Defaults(link_preview_options=NO_PREVIEW)
    app = (
        Application.builder()
        .token(rt.token)
        .defaults(defaults)
        .build()
    )
    app.bot_data["runtime"] = rt
    _install_handlers(app, rt)

    # post_init: نحذف webhook قديم ونبلّغ المالك
    async def _on_startup(_app: Application):
        try:
            await _app.bot.delete_webhook(drop_pending_updates=True)
        except TelegramError:
            pass
        try:
            me = await _app.bot.get_me()
            await host_app.bot.send_message(
                rt.owner_id,
                f"✅ بوت التواصل <b>{me.full_name}</b> (@{me.username}) يعمل الآن.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    app.post_init = _on_startup
    return app
