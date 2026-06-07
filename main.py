# main.py
# 🚀 ملف التشغيل الرئيسي - V7.0 (Telegram Backup)

import logging
from datetime import datetime

from telegram import Update, BotCommand, BotCommandScopeDefault, BotCommandScopeChat, MenuButtonCommands
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)

from config import (
    BOT_TOKEN,
    OWNER_ID,
    BACKUP_CHAT,
    data,
    save_data,
    is_owner,
    update_stats,
    restore_from_telegram,
    backup_to_telegram,
)
from handlers import (
    start_command,
    button_handler,
    message_handler,
    my_chat_member_handler,
)

# ═══════════════════════════════════════════════════════════════
#                      📝 إعداد اللوج
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#                      ⚠️ معالج الأخطاء
# ═══════════════════════════════════════════════════════════════

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("خطأ غير متوقع", exc_info=context.error)
    try:
        await context.bot.send_message(
            OWNER_ID,
            f"⚠️ **خطأ:**\n`{str(context.error)[:300]}`",
            parse_mode="Markdown",
        )
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
#                      🎮 الأوامر
# ═══════════════════════════════════════════════════════════════

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_owner(update.effective_user.id):
        text = """📖 **أوامر المالك**
━━━━━━━━━━━━━━━━━━━━━━━━
**الأساسية:**
• `/start` - لوحة التحكم
• `/help` - المساعدة
• `/stats` - إحصائيات
• `/ping` - فحص البوت
• `/backup` - حفظ باكب الآن

**الحظر:**
• `حظر ID` أو `/ban ID`
• `فك ID` أو `/unban ID`

**VIP:**
• `vip ID` أو `/vip ID`
• `unvip ID`

**الحذف والتعديل:**
• Reply + `مسح` - حذف الرسالة
• Reply + `ؤ نص جديد` - تعديل الرسالة

**التحكم بالمستخدمين (بالريبلاي):**
• Reply + `حظر` - حظر المستخدم فوراً
• Reply + `كتم` - كتم/إلغاء كتم

**التفاعل:**
• Reply + `ص 😂` - إضافة تفاعل على رسالة المستخدم
━━━━━━━━━━━━━━━━━━━━━━━━"""
    else:
        text = "📖 أرسل رسالتك وسيتم الرد عليك ❤️"
    await update.message.reply_text(text, parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    s = data["stats"]
    text = f"""📊 **إحصائيات سريعة**
━━━━━━━━━━━━━━━━━━━━━━━━
👥 المستخدمين: **{len(data['users'])}**
👨‍💼 المشرفين: **{len(data['admins'])}**
⭐ VIP: **{len(data['vip_users'])}**
🚫 المحظورين: **{len(data['banned'])}**
━━━━━━━━━━━━━━━━━━━━━━━━
📨 اليوم: **{s['today_received']}** وارد | **{s['today_sent']}** مرسل
📊 الإجمالي: **{s['total_received']}** | **{s['total_sent']}**
━━━━━━━━━━━━━━━━━━━━━━━━"""
    await update.message.reply_text(text, parse_mode="Markdown")


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = datetime.now()
    msg = await update.message.reply_text("🏓 ...")
    ms = (datetime.now() - start).total_seconds() * 1000
    await msg.edit_text(
        f"🏓 **Pong!**\n⚡ {ms:.0f}ms\n✅ البوت يعمل",
        parse_mode="Markdown",
    )


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حفظ باكب يدوي."""
    if not is_owner(update.effective_user.id):
        return
    msg = await update.message.reply_text("💾 جاري حفظ الباكب...")
    ok = await backup_to_telegram(context.bot)
    if ok:
        await msg.edit_text("✅ تم حفظ الباكب في Telegram بنجاح!")
    else:
        await msg.edit_text("❌ فشل حفظ الباكب، تحقق من اللوج")


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("❌ `/ban ID`", parse_mode="Markdown")
        return
    uid = context.args[0]
    if uid not in data["banned"]:
        data["banned"].append(uid)
        save_data()
        await update.message.reply_text(f"✅ تم حظر `{uid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ محظور مسبقاً")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("❌ `/unban ID`", parse_mode="Markdown")
        return
    uid = context.args[0]
    if uid in data["banned"]:
        data["banned"].remove(uid)
        save_data()
        await update.message.reply_text(f"✅ تم فك حظر `{uid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ غير محظور")


async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("❌ `/vip ID`", parse_mode="Markdown")
        return
    uid = context.args[0]
    if uid not in data["vip_users"]:
        data["vip_users"].append(uid)
        save_data()
        await update.message.reply_text(f"⭐ تم إضافة `{uid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ موجود مسبقاً")


async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ `/send ID الرسالة`", parse_mode="Markdown")
        return
    uid = context.args[0]
    text = " ".join(context.args[1:])
    try:
        await context.bot.send_message(int(uid), text)
        update_stats("sent")
        await update.message.reply_text("✅ تم!")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("❌ `/info ID`", parse_mode="Markdown")
        return
    uid = context.args[0]
    info = data["users"].get(uid, {})
    if not info:
        await update.message.reply_text("❌ غير موجود")
        return
    badges = []
    if uid in data["vip_users"]: badges.append("⭐")
    if uid in data["banned"]:    badges.append("🚫")
    if uid in data["admins"]:    badges.append("👨‍💼")
    text = f"""👤 **{info.get('name', 'مجهول')}** {''.join(badges)}
🆔 `{uid}`
🔗 @{info.get('username') or 'لا يوجد'}
📊 الرسائل: **{info.get('msg_count', 0)}**
📅 انضم: {info.get('joined', '?')}"""
    await update.message.reply_text(text, parse_mode="Markdown")


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    users = list(data["users"].items())[-10:]
    text = "👥 **آخر 10 مستخدمين:**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for uid, info in users:
        vip = "⭐" if uid in data["vip_users"] else ""
        ban = "🚫" if uid in data["banned"] else ""
        text += f"{vip}{ban} **{info.get('name', '?')[:15]}** | `{uid}`\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def bc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("❌ `/bc الرسالة`", parse_mode="Markdown")
        return
    text = " ".join(context.args)
    sent = failed = 0
    for uid in list(data["users"].keys()):
        try:
            await context.bot.send_message(int(uid), text)
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"📣 **الإذاعة انتهت**\n✅ تم: {sent}\n❌ فشل: {failed}",
        parse_mode="Markdown",
    )

# ═══════════════════════════════════════════════════════════════
#              ⏱️ باكب دوري كل ساعة
# ═══════════════════════════════════════════════════════════════

async def hourly_backup(context: ContextTypes.DEFAULT_TYPE):
    """يُنفّذ تلقائياً كل ساعة."""
    await backup_to_telegram(context.bot)

# ═══════════════════════════════════════════════════════════════
#                      🚀 post_init
# ═══════════════════════════════════════════════════════════════

async def post_init(application: Application):
    """يُنفّذ بعد تشغيل البوت — يستعيد البيانات من Telegram."""

    # ── 1. استعادة البيانات من Telegram ──
    print("🔄 جاري استعادة البيانات من Telegram...")
    restored = await restore_from_telegram(application.bot)

    # ── 2. باكب فوري عند البدء ──
    await backup_to_telegram(application.bot)

    # ── 3. أوامر القائمة ──
    user_cmds = [
        BotCommand('start', '🚀 بدء البوت'),
        BotCommand('help', '📖 المساعدة'),
    ]
    owner_cmds = user_cmds + [
        BotCommand('stats',  '📊 الإحصائيات'),
        BotCommand('ping',   '🏓 فحص البوت'),
        BotCommand('backup', '💾 حفظ باكب'),
        BotCommand('users',  '👥 آخر المستخدمين'),
        BotCommand('info',   'ℹ️ معلومات مستخدم'),
        BotCommand('send',   '✉️ إرسال رسالة'),
        BotCommand('bc',     '📣 إذاعة'),
        BotCommand('ban',    '🚫 حظر'),
        BotCommand('unban',  '✅ فك حظر'),
        BotCommand('vip',    '⭐ إضافة VIP'),
    ]
    try:
        await application.bot.set_my_commands(user_cmds, scope=BotCommandScopeDefault())
        if OWNER_ID:
            await application.bot.set_my_commands(owner_cmds, scope=BotCommandScopeChat(chat_id=OWNER_ID))
        await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception as e:
        logger.error("❌ فشل ضبط القائمة: %s", e)

    # ── 4. إشعار المالك ──
    try:
        await application.bot.send_message(
            OWNER_ID,
            f"""🚀 **البوت يعمل الآن!**
━━━━━━━━━━━━━━━━━━━━━━━━
✅ تم التشغيل بنجاح
📊 الإصدار: **V7.0**
💾 الباكب: **{'✅ تم الاستعادة' if restored else '🆕 بدء جديد'}**
👥 المستخدمين: **{len(data['users'])}**
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━━━━""",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("❌ فشل إرسال الإشعار: %s", e)

# ═══════════════════════════════════════════════════════════════
#                      🚀 التشغيل الرئيسي
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("🚀 بوت التواصل V7.0 – Telegram Backup")
    print(f"🔧 BOT_TOKEN:   {'✅ موجود' if BOT_TOKEN else '❌ مفقود'}")
    print(f"👑 OWNER_ID:    {OWNER_ID if OWNER_ID else '❌ مفقود'}")
    print(f"💾 BACKUP_CHAT: {BACKUP_CHAT}")
    print("=" * 55)

    if not BOT_TOKEN:
        print("❌ خطأ: BOT_TOKEN غير مضبوط.")
        return

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ── باكب دوري كل ساعة ──
    application.job_queue.run_repeating(hourly_backup, interval=3600, first=3600)

    # ── الأوامر ──
    commands = {
        "start":  start_command,
        "help":   help_command,
        "stats":  stats_command,
        "ping":   ping_command,
        "backup": backup_command,
        "ban":    ban_command,
        "unban":  unban_command,
        "vip":    vip_command,
        "send":   send_command,
        "info":   info_command,
        "users":  users_command,
        "bc":     bc_command,
    }
    for name, fn in commands.items():
        application.add_handler(CommandHandler(name, fn))

    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(
        ChatMemberHandler(my_chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER)
    )
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))
    application.add_error_handler(error_handler)

    print("✅ البوت يعمل الآن")
    print("=" * 55)

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
