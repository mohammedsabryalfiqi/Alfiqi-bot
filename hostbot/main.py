"""
Alfiqi Bot Hosting Platform — البوت الرئيسي للمنصة.

المستخدم يتفاعل مع هذا البوت عشان:
  • يبدأ بكتابة /start
  • يضيف توكن بوت صنعه من @BotFather
  • يختار القالب (تواصل / حماية)
  • يشغّل البوت، يوقفه، يشوف حالته، يحذفه، يعدّل إعداداته
  • المالك الأساسي (OWNER_ID) يقدر يضيف "مديرين" ويرى كل البوتات

كل بوت مُضاف يعمل كـ Application ptb مستقل داخل نفس العملية.
"""

from __future__ import annotations

import html
import warnings

# إخماد تحذير PTB المعروف الخاص بـ CallbackQueryHandler + per_message=False
# (طبيعي في لوحات التنقل التي لا تحتاج تتبُّع كل رسالة).
warnings.filterwarnings("ignore", category=UserWarning,
                        message=r".*CallbackQueryHandler.*")
import logging
import os
import re
import time
from typing import Any

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    LinkPreviewOptions, BotCommand,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError, InvalidToken
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ChatMemberHandler,
    filters, ContextTypes, Defaults,
)

from . import storage
from .manager import (
    BOT_TYPES, start_bot, stop_bot, restart_bot, is_running,
    running_count, stop_all, uptime as bot_uptime,
)

logger = logging.getLogger(__name__)

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

# ═══════════════════════════════════════════════════════════
#  Config
# ═══════════════════════════════════════════════════════════

HOST_BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

if not HOST_BOT_TOKEN or not OWNER_ID:
    raise SystemExit(
        "لازم تحدد BOT_TOKEN و OWNER_ID (توكن بوت المنصة نفسه) "
        "في متغيرات البيئة."
    )

# حالات المحادثة لإضافة بوت
(ASK_TOKEN, ASK_TYPE, ASK_CONFIRM_DELETE, ASK_BROADCAST) = range(4)


# ═══════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════

def _mk_btn(text, style=None, **kw):
    api_kwargs = {}
    if style in ("primary", "success", "danger"):
        api_kwargs["style"] = style
    if api_kwargs:
        kw.setdefault("api_kwargs", {}).update(api_kwargs)
    return InlineKeyboardButton(text, **kw)


def is_authorized(user_id: int) -> bool:
    return storage.is_owner(user_id, OWNER_ID)


def _bot_type_label(type_key: str) -> str:
    return BOT_TYPES.get(type_key, {}).get("name", type_key)


def _status_label(bot: dict) -> str:
    if bot["status"] == "running":
        return "🟢 شغّال"
    if bot["status"] == "error":
        return "🔴 خطأ"
    return "⚪ متوقف"


def _bot_list_kb(bots: list[dict], admin_view: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for b in bots:
        name = b.get("bot_name") or b.get("bot_username") or f"بوت #{b['id']}"
        status = "🟢" if b["status"] == "running" else ("🔴" if b["status"] == "error" else "⚪")
        label = f"{status} {name}"[:40]
        rows.append([_mk_btn(label, "primary" if b["status"]=="running" else "success",
                            callback_data=f"h_view:{b['id']}")])
    rows.append([_mk_btn("➕ إضافة بوت جديد", "primary", callback_data="h_add")])
    if admin_view:
        rows.append([_mk_btn("🌐 لوحة الأدمن", "danger", callback_data="h_admin")])
    return InlineKeyboardMarkup(rows)


async def _main_menu_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bots = storage.list_bots(user.id)
    if is_authorized(user.id) and user.id == OWNER_ID:
        all_bots = storage.list_bots()
        others = [b for b in all_bots if b["owner_id"] != OWNER_ID]
    else:
        others = []

    total = len(bots) + len(others)
    running = sum(1 for b in storage.list_bots() if b["status"] == "running")

    text = (
        f"🚀 <b>منصة استضافة بوتات تلجرام</b>\n\n"
        f"مرحباً {html.escape(user.full_name)} 👋\n"
        f"البوتات المستضافة حالياً: <b>{len(storage.list_bots())}</b> | "
        f"الشغّالة: <b>{running_count()}</b>\n\n"
    )
    if not bots and not others:
        text += (
            "ما عندك أي بوت مستضاف بعد.\n"
            "طريقة الإنشاء:\n"
            "1. افتح @BotFather واصنع بوت جديد، خد التوكن.\n"
            "2. ارجع لهنا واضغط «إضافة بوت جديد».\n"
            "3. اختر النوع (تواصل أو حماية مجموعات).\n"
            "4. هتقدر تشغّله وتوقفه من لوحة التحكم."
        )
    return text


# ═══════════════════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════════════════

async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """يبث رسالة لكل المستخدمين المخوّلين للمنصة (مالك + مدراء)."""
    user = update.effective_user
    if user.id != OWNER_ID:
        return
    await update.message.reply_text(
        "📢 أرسل الرسالة المراد بثها لجميع المدراء.\nأو /cancel")
    return ASK_BROADCAST


async def recv_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID:
        return ConversationHandler.END
    msg = update.effective_message
    admins = set(storage.list_admins()) | {OWNER_ID}
    ok = fail = 0
    for uid in admins:
        try:
            await ctx.bot.copy_message(uid, update.effective_chat.id, msg.message_id)
            ok += 1
        except TelegramError:
            fail += 1
    await msg.reply_text(f"✅ البث انتهى — نجح: {ok} | فشل: {fail}")
    return ConversationHandler.END


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if chat.type != "private":
        await update.message.reply_text(
            "البوت يعمل في الخاص فقط.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("افتح الخاص", url=f"https://t.me/{ctx.bot.username}")
            ]]))
        return
    bots = storage.list_bots(user.id) if is_authorized(user.id) else []
    if not is_authorized(user.id):
        await update.message.reply_text(
            "⚠️ هذه المنصة خاصة بالمدعوين فقط. تواصل مع المالك للحصول على صلاحية."
        )
        return
    kb = _bot_list_kb(bots, admin_view=(user.id == OWNER_ID))
    await update.message.reply_text(await _main_menu_text(update, ctx),
                                     parse_mode=ParseMode.HTML, reply_markup=kb)


# ═══════════════════════════════════════════════════════════
#  Callbacks
# ═══════════════════════════════════════════════════════════

async def callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    await q.answer()
    user = update.effective_user

    if d == "h_add":
        if not is_authorized(user.id):
            await q.edit_message_text("⚠️ غير مصرح."); return ConversationHandler.END
        await q.edit_message_text(
            "✏️ <b>إضافة بوت جديد</b>\n\n"
            "أرسل الآن <b>توكن البوت</b> اللي صنعته من @BotFather "
            "(صيغته تشبه: 123456789:ABCdef...).\n\n"
            "أرسل /cancel للإلغاء.",
            parse_mode=ParseMode.HTML)
        return ASK_TOKEN

    if d == "h_admin":
        if user.id != OWNER_ID: return ConversationHandler.END
        all_bots = storage.list_bots()
        admins = storage.list_admins()
        lines = ["🌐 <b>لوحة الأدمن</b>\n", f"إجمالي البوتات: <b>{len(all_bots)}</b> | شغّالة: <b>{running_count()}</b>\n"]
        # مدراء
        lines.append("<b>المدراء:</b>")
        if not admins:
            lines.append("• لا يوجد (فقط المالك الأساسي).")
        else:
            for a in admins:
                lines.append(f"• <code>{a}</code>")
        # كل البوتات
        lines.append("\n<b>كل البوتات:</b>")
        for b in all_bots:
            lines.append(f"• #{b['id']} {_status_label(b)} {_bot_type_label(b['bot_type'])} — مالك <code>{b['owner_id']}</code>")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة مدير", callback_data="h_add_admin")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="h_back_main")],
        ])
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=kb)
        return ConversationHandler.END

    if d == "h_add_admin":
        if user.id != OWNER_ID: return ConversationHandler.END
        await q.edit_message_text(
            "✏️ أرسل <b>ID المستخدم</b> اللي عايز تضيفه كمدير (يمكنه إنشاء بوتات).\n\nأو /cancel",
            parse_mode=ParseMode.HTML)
        ctx.user_data["awaiting_admin_id"] = True
        return ASK_TOKEN  # إعادة استخدام نفس الحالة (نستقبل نص)

    if d == "h_back_main":
        bots = storage.list_bots(user.id)
        await q.edit_message_text(await _main_menu_text(update, ctx),
                                   parse_mode=ParseMode.HTML,
                                   reply_markup=_bot_list_kb(bots, admin_view=(user.id == OWNER_ID)))
        return ConversationHandler.END

    if d.startswith("h_view:"):
        bot_id = int(d.split(":")[1])
        b = storage.get_bot(bot_id)
        if not b: await q.edit_message_text("البوت غير موجود."); return ConversationHandler.END
        if b["owner_id"] != user.id and user.id != OWNER_ID:
            await q.answer("غير مصرح."); return ConversationHandler.END
        await _show_bot_view(q, ctx, b)
        return ConversationHandler.END

    if d.startswith("h_start:"):
        bot_id = int(d.split(":")[1])
        b = storage.get_bot(bot_id)
        if not b or (b["owner_id"] != user.id and user.id != OWNER_ID):
            return ConversationHandler.END
        await q.edit_message_text("⏳ جاري تشغيل البوت...")
        ok, msg = await start_bot(ctx.application, bot_id)
        b = storage.get_bot(bot_id)
        await q.edit_message_text(
            f"{'✅' if ok else '⚠️'} {html.escape(msg)}",
            parse_mode=ParseMode.HTML,
            reply_markup=_bot_view_kb(b))
        return ConversationHandler.END

    if d.startswith("h_stop:"):
        bot_id = int(d.split(":")[1])
        b = storage.get_bot(bot_id)
        if not b or (b["owner_id"] != user.id and user.id != OWNER_ID):
            return ConversationHandler.END
        ok, msg = await stop_bot(bot_id)
        b = storage.get_bot(bot_id)
        await q.edit_message_text(
            f"{'✅' if ok else '⚠️'} {html.escape(msg)}",
            reply_markup=_bot_view_kb(b))
        return ConversationHandler.END

    if d.startswith("h_restart:"):
        bot_id = int(d.split(":")[1])
        b = storage.get_bot(bot_id)
        if not b or (b["owner_id"] != user.id and user.id != OWNER_ID):
            return ConversationHandler.END
        await q.edit_message_text("⏳ جاري إعادة التشغيل...")
        ok, msg = await restart_bot(ctx.application, bot_id)
        b = storage.get_bot(bot_id)
        await q.edit_message_text(
            f"{'✅' if ok else '⚠️'} {html.escape(msg)}",
            parse_mode=ParseMode.HTML,
            reply_markup=_bot_view_kb(b))
        return ConversationHandler.END

    if d.startswith("h_del:"):
        bot_id = int(d.split(":")[1])
        b = storage.get_bot(bot_id)
        if not b or (b["owner_id"] != user.id and user.id != OWNER_ID):
            return ConversationHandler.END
        ctx.user_data["pending_delete"] = bot_id
        await q.edit_message_text(
            f"⚠️ <b>تأكيد حذف البوت</b>\n\n"
            f"هل أنت متأكد من حذف البوت <b>{html.escape(b.get('bot_name') or '#'+str(b_id))}</b>؟\n"
            "سيتم إيقافه وحذف سجله نهائياً (بيانات المستخدمين ستبقى في مجلد البوت).",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 نعم، احذف", callback_data=f"h_del_confirm:{bot_id}",
                                      api_kwargs={"style": "danger"})],
                [InlineKeyboardButton("إلغاء", callback_data=f"h_view:{bot_id}")],
            ]))
        return ConversationHandler.END

    if d.startswith("h_del_confirm:"):
        bot_id = int(d.split(":")[1])
        b = storage.get_bot(bot_id)
        if not b or (b["owner_id"] != user.id and user.id != OWNER_ID):
            return ConversationHandler.END
        await stop_bot(bot_id)
        storage.delete_bot(bot_id)
        bots = storage.list_bots(user.id)
        await q.edit_message_text("🗑 تم حذف البوت.",
                                   reply_markup=_bot_list_kb(bots, admin_view=(user.id == OWNER_ID)))
        return ConversationHandler.END

    if d.startswith("h_type:"):
        _, bot_type = d.split(":", 1)
        if bot_type not in BOT_TYPES: return ConversationHandler.END
        token = ctx.user_data.get("pending_token")
        if not token: return ConversationHandler.END
        ctx.user_data["pending_type"] = bot_type
        await q.edit_message_text(
            f"📋 ملخص البوت الجديد:\n\n"
            f"النوع: <b>{BOT_TYPES[bot_type]['name']}</b>\n"
            f"التوكن: <code>{token[:10]}…{token[-6:]}</code>\n\n"
            f"سيتم إنشاء البوت وهو في حالة «متوقف» حتى تضغط «تشغيل» من لوحته.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ تأكيد وإنشاء", callback_data="h_create_confirm",
                                      api_kwargs={"style": "success"})],
                [InlineKeyboardButton("إلغاء", callback_data="h_back_main")],
            ]))
        return ASK_CONFIRM_DELETE  # مجرد حالة انتظار (النص مش مطلوب)

    if d == "h_create_confirm":
        token = ctx.user_data.pop("pending_token", None)
        btype = ctx.user_data.pop("pending_type", None)
        if not token or not btype:
            await q.edit_message_text("⚠️ انتهت الجلسة.")
            return ConversationHandler.END
        # تحقق من التوكن (سريع)
        try:
            from telegram import Bot
            tmp = Bot(token=token)
            me = await tmp.get_me()
            await tmp.close()
        except InvalidToken:
            await q.edit_message_text("⚠️ التوكن غير صالح، أعد المحاولة من /start.")
            return ConversationHandler.END
        except TelegramError as e:
            await q.edit_message_text(f"⚠️ فشل التحقق من التوكن: {html.escape(str(e))}")
            return ConversationHandler.END
        # لا نسمح بتكرار نفس التوكن
        existing = storage.get_bot_by_token(token)
        if existing:
            await q.edit_message_text(
                f"⚠️ هذا التوكن مضاف مسبقاً (بوت #{existing['id']}).")
            return ConversationHandler.END
        bid = storage.add_bot(user.id, token, btype, username=me.username,
                              name=me.full_name or me.first_name)
        b = storage.get_bot(bid)
        await q.edit_message_text(
            f"✅ تم إنشاء البوت <b>{html.escape(me.full_name)}</b> (@{me.username}) بنجاح!\n\n"
            f"النوع: {_bot_type_label(btype)}\n\n"
            "اضغط «تشغيل» لبدء استقبال التحديثات.",
            parse_mode=ParseMode.HTML,
            reply_markup=_bot_view_kb(b))
        return ConversationHandler.END

    return ConversationHandler.END


def _bot_view_kb(b: dict) -> InlineKeyboardMarkup:
    bid = b["id"]
    running = b["status"] == "running"
    rows = []
    # زر فتح البوت
    if b.get("bot_username"):
        rows.append([InlineKeyboardButton(
            "💬 فتح البوت", url=f"https://t.me/{b['bot_username']}")])
    if running:
        rows.append([
            _mk_btn("⏸ إيقاف", "danger", callback_data=f"h_stop:{bid}"),
            _mk_btn("🔄 إعادة تشغيل", "primary", callback_data=f"h_restart:{bid}"),
        ])
    else:
        rows.append([_mk_btn("▶️ تشغيل", "success", callback_data=f"h_start:{bid}")])
    rows.append([_mk_btn("🗑 حذف البوت", "danger", callback_data=f"h_del:{bid}")])
    rows.append([_mk_btn("🔙 قائمة بوتاتي", "primary", callback_data="h_back_main")])
    return InlineKeyboardMarkup(rows)


async def _show_bot_view(q, ctx: ContextTypes.DEFAULT_TYPE, b: dict):
    name = b.get("bot_name") or "—"
    uname = f"@{b['bot_username']}" if b.get("bot_username") else "—"
    status = _status_label(b)
    btype = _bot_type_label(b["bot_type"])
    tpl = BOT_TYPES.get(b["bot_type"], {})
    desc = tpl.get("description", "")
    token_disp = (b["token"][:10] + "…" + b["token"][-6:]) if len(b["token"]) > 20 else "—"
    up = bot_uptime(b["id"])
    up_text = ""
    if up > 0:
        h = int(up // 3600); m = int((up % 3600) // 60)
        up_text = f"مدة التشغيل: {h}س {m}د\n"
    err = ""
    if b.get("error_msg"):
        err = f"\n⚠️ <b>آخر خطأ:</b> {html.escape(b['error_msg'][:300])}"

    await q.edit_message_text(
        f"🤖 <b>{html.escape(name)}</b> ({html.escape(uname)})\n\n"
        f"الحالة: {status}\n"
        f"النوع: {btype}\n"
        f"التوكن: <code>{token_disp}</code>\n"
        f"عدد الرسائل: <b>{b.get('total_msgs', 0)}</b>\n"
        f"{up_text}"
        f"تاريخ الإضافة: {time.strftime('%Y-%m-%d %H:%M', time.localtime(b['created_at']))}\n\n"
        f"<i>{html.escape(desc[:300])}</i>"
        f"{err}\n\n"
        f"<b>💡 طريقة الاستخدام:</b>\n"
        + (
            "اذهب للبوت وابعت /panel لعرض لوحة التحكم الخاصة به. "
            "المالك هو حسابك (اللي ضاف التوكن)." if b["bot_type"] == "contact"
            else "أضف البوت لمجموعتك وارفعه أدمن مع صلاحيات الحذف والحظر والكتم، "
                 "وستعمل أوامر الحماية تلقائياً."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=_bot_view_kb(b),
    )


# ═══════════════════════════════════════════════════════════
#  استقبال التوكن والنوع
# ═══════════════════════════════════════════════════════════

async def recv_token(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id): return ConversationHandler.END

    # لو المستخدم بيدخل ID مدير جوه لوحة الأدمن
    if ctx.user_data.get("awaiting_admin_id"):
        ctx.user_data.pop("awaiting_admin_id")
        try:
            aid = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("⚠️ الآيدي يجب أن يكون رقم.")
            return ConversationHandler.END
        storage.add_admin(aid)
        await update.message.reply_text(
            f"✅ تمت إضافة <code>{aid}</code> كمدير.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 لوحة الأدمن", callback_data="h_admin")
            ]]))
        return ConversationHandler.END

    token = update.message.text.strip()
    if not re.match(r"^\d{6,12}:[A-Za-z0-9_-]{20,}$", token):
        await update.message.reply_text(
            "⚠️ الصيغة لا تبدو كتوكن صالح (مثال: 123456789:ABCdef...).\n"
            "أعد الإرسال أو /cancel.")
        return ASK_TOKEN

    # تحقق سريع
    try:
        from telegram import Bot
        tmp = Bot(token=token)
        me = await tmp.get_me()
        await tmp.close()
    except InvalidToken:
        await update.message.reply_text("⚠️ التوكن غير صالح، أعد الإرسال أو /cancel.")
        return ASK_TOKEN
    except TelegramError as e:
        await update.message.reply_text(f"⚠️ فشل الاتصال بتليجرام: {html.escape(str(e))}")
        return ASK_TOKEN

    existing = storage.get_bot_by_token(token)
    if existing:
        await update.message.reply_text(
            f"⚠️ هذا التوكن مضاف بالفعل (بوت #{existing['id']}).",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="h_back_main")
            ]]))
        return ConversationHandler.END

    ctx.user_data["pending_token"] = token
    await update.message.reply_text(
        f"✅ تم التحقق من التوكن (@{me.username}).\n\n"
        f"اختر نوع البوت:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(BOT_TYPES["contact"]["name"], callback_data="h_type:contact",
                                   api_kwargs={"style": "primary"})],
            [InlineKeyboardButton(BOT_TYPES["protection"]["name"], callback_data="h_type:protection",
                                   api_kwargs={"style": "success"})],
            [InlineKeyboardButton("إلغاء", callback_data="h_back_main")],
        ]))
    return ASK_TYPE


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("pending_token", None)
    ctx.user_data.pop("pending_type", None)
    ctx.user_data.pop("pending_delete", None)
    ctx.user_data.pop("awaiting_admin_id", None)
    user = update.effective_user
    bots = storage.list_bots(user.id)
    await update.message.reply_text("❌ ألغيت.",
        reply_markup=_bot_list_kb(bots, admin_view=(user.id == OWNER_ID)))
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
#  أوامر إدارية للمالك
# ═══════════════════════════════════════════════════════════

async def cmd_addadmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args:
        await update.message.reply_text("الاستخدام: /addadmin USER_ID"); return
    try:
        aid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ ID غير صالح."); return
    storage.add_admin(aid)
    await update.message.reply_text(f"✅ تمت إضافة <code>{aid}</code> كمدير.",
                                     parse_mode=ParseMode.HTML)


async def cmd_deladmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args:
        await update.message.reply_text("الاستخدام: /deladmin USER_ID"); return
    try:
        aid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ ID غير صالح."); return
    storage.remove_admin(aid)
    await update.message.reply_text(f"✅ تمت إزالة <code>{aid}</code> من المدراء.",
                                     parse_mode=ParseMode.HTML)


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    all_bots = storage.list_bots()
    running = sum(1 for b in all_bots if b["status"] == "running")
    lines = [
        f"📊 <b>إحصائيات المنصة</b>\n",
        f"إجمالي البوتات: <b>{len(all_bots)}</b>",
        f"الشغّالة حالياً: <b>{running}</b>",
        f"المتوقفة: <b>{sum(1 for b in all_bots if b['status']=='stopped')}</b>",
        f"بها خطأ: <b>{sum(1 for b in all_bots if b['status']=='error')}</b>\n",
        "<b>الأنواع:</b>",
    ]
    by_type: dict[str, int] = {}
    for b in all_bots:
        by_type[b["bot_type"]] = by_type.get(b["bot_type"], 0) + 1
    for t, c in by_type.items():
        lines.append(f"• {_bot_type_label(t)}: {c}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════════════════════
#  Auto-start bots at platform startup
# ═══════════════════════════════════════════════════════════

async def autostart_bots(app: Application):
    """يشغّل تلقائياً أي بوت كان شغال قبل إعادة التشغيل (status=running)."""
    # انتظر قليلاً حتى يكتمل init
    await asyncio.sleep(2)
    bots = storage.list_bots()
    auto = [b for b in bots if b["status"] in ("running",)]
    if not auto:
        return
    logger.info(f"Autostarting {len(auto)} hosted bot(s)...")
    for b in auto:
        try:
            ok, msg = await start_bot(app, b["id"])
            logger.info(f"  autostart {b['id']} ({b.get('bot_username')}): {msg}")
        except Exception as e:
            logger.error(f"  autostart {b['id']} failed: {e}")


# ═══════════════════════════════════════════════════════════
#  Lifecycle
# ═══════════════════════════════════════════════════════════

async def on_startup(app: Application):
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
    except TelegramError:
        pass
    try:
        await app.bot.set_my_commands([
            BotCommand("start", "القائمة الرئيسية"),
            BotCommand("stats", "إحصائيات المنصة (للمالك)"),
        ])
    except TelegramError:
        pass
    # جدولة autostart كـ background task
    asyncio.create_task(autostart_bots(app))
    # إشعار المالك
    try:
        await app.bot.send_message(
            OWNER_ID,
            "🚀 <b>منصة استضافة البوتات تعمل الآن.</b>\n\n"
            "استخدم /start لفتح لوحة التحكم.",
            parse_mode=ParseMode.HTML)
    except TelegramError as e:
        logger.error(f"notify owner: {e}")


async def on_shutdown(app: Application):
    logger.info("Shutting down hosted bots...")
    await stop_all()


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    logger.error("خطأ غير متوقع", exc_info=ctx.error)
    try:
        await ctx.bot.send_message(
            OWNER_ID,
            f"⚠️ خطأ في بوت المنصة:\n<code>{html.escape(str(ctx.error))[:600]}</code>",
            parse_mode=ParseMode.HTML)
    except Exception:
        pass


def build_app() -> Application:
    defaults = Defaults(link_preview_options=NO_PREVIEW)
    app = (
        Application.builder()
        .token(HOST_BOT_TOKEN)
        .defaults(defaults)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )
    app.add_error_handler(on_error)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("addadmin", cmd_addadmin))
    app.add_handler(CommandHandler("deladmin", cmd_deladmin))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback), CommandHandler("broadcast", cmd_broadcast)],
        states={
            ASK_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_token)],
            ASK_TYPE: [CallbackQueryHandler(callback)],
            ASK_CONFIRM_DELETE: [CallbackQueryHandler(callback)],
            ASK_BROADCAST: [MessageHandler(~filters.COMMAND & filters.User(OWNER_ID), recv_broadcast)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True, per_user=True, per_message=False,
    )
    app.add_handler(conv)
    # لاستقبال الـ callback queries اللي ماتلتقطهوش الـ ConversationHandler
    # (مثل عندما تكون المحادثة انتهت لكن المستخدم ضغط زر قديم).
    app.add_handler(CallbackQueryHandler(callback), group=1)

    return app


def main():
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=logging.INFO,
    )
    # خفض إزعاج logs مكتبة httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)
    storage.init_db()
    app = build_app()
    logger.info("🚀 منصة استضافة البوتات قيد التشغيل.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
