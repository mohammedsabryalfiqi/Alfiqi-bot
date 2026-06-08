# handlers.py
# 🎮 ملف المعالجات - V5.0 (بطاقة تعريفية + بدون إيموجيات مميزة)
# الملف 3 من 4

import asyncio
from datetime import datetime
from telegram import (
    Update,
    ReactionTypeEmoji,
    ReactionTypeCustomEmoji,
    MessageEntity,
    InputTextMessageContent,
    LinkPreviewOptions,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, MessageEntityType

# مكتبة إيموجيات تيليغرام المميزة
try:
    import emoji as emoji_lib
    EMOJI_LIB = True
except ImportError:
    EMOJI_LIB = False

def e(code: str) -> str:
    """اختصار لتحويل اسم الإيموجي أو إرجاعه كما هو"""
    if EMOJI_LIB:
        try:
            return emoji_lib.emojize(code, language='alias')
        except:
            return code
    return code

def md_escape(text: str) -> str:
    """تهريب الرموز الخاصة في Markdown v1 لمنع أخطاء parse_entities"""
    if not text:
        return ""
    # الرموز الخاصة في Markdown v1: * _ ` [
    for ch in ('\\', '*', '_', '`', '['):
        text = text.replace(ch, '\\' + ch)
    return text

from config import (
    OWNER_ID, data, save_data,
    is_owner, is_admin, can_reply, is_banned, is_vip,
    save_user, update_stats, get_smart_reply
)

# ═══════════════════════════════════════════════════════════════
#           🎭 دوال مساعدة للإيموجيات المميزة (Custom Emoji)
# ═══════════════════════════════════════════════════════════════

async def get_pack_sticker_ids(bot, pack_link: str) -> list:
    """
    يجلب قائمة {custom_emoji_id, file_id} من رابط حزمة الإيموجيات المميزة.
    الرابط مثل: https://t.me/addemoji/PackName  أو  t.me/addemoji/PackName
    يُعيد قائمة من dict: {"id": custom_emoji_id, "fid": file_id}
    """
    try:
        name = pack_link.strip().rstrip("/")
        for prefix in ["https://t.me/addemoji/", "http://t.me/addemoji/", "t.me/addemoji/"]:
            if name.lower().startswith(prefix):
                name = name[len(prefix):]
                break
        sticker_set = await bot.get_sticker_set(name)
        items = []
        for s in sticker_set.stickers:
            if s.custom_emoji_id:
                items.append({"id": s.custom_emoji_id, "fid": s.file_id})
        return items
    except Exception as ex:
        return []

def parse_emoji_token(token: str):
    """
    يحلل التوكن {N} أو {N|P} ويعيد (emoji_index, pack_index).
    الأرقام 1-based. يعيد None عند خطأ.
    """
    token = token.strip().lstrip("{").rstrip("}")
    if "|" in token:
        parts = token.split("|", 1)
        try:
            return int(parts[0].strip()), int(parts[1].strip())
        except ValueError:
            return None
    else:
        try:
            return int(token.strip()), 1
        except ValueError:
            return None

async def resolve_custom_emoji(bot, token: str):
    """
    يحوّل توكن {N} أو {N|P} إلى dict {"id": custom_emoji_id, "fid": file_id}.
    يعيد None إذا لم يوجد.
    """
    parsed = parse_emoji_token(token)
    if parsed is None:
        return None
    emoji_idx, pack_idx = parsed
    packs = data.get("emoji_packs", [])
    if pack_idx < 1 or pack_idx > len(packs):
        return None
    pack_entry = packs[pack_idx - 1]
    ids = pack_entry.get("ids", [])
    if not ids:
        fetched = await get_pack_sticker_ids(bot, pack_entry["link"])
        if not fetched:
            return None
        packs[pack_idx - 1]["ids"] = fetched
        save_data()
        ids = fetched
    if emoji_idx < 1 or emoji_idx > len(ids):
        return None
    item = ids[emoji_idx - 1]
    # دعم الصيغة القديمة (string) والجديدة (dict)
    if isinstance(item, str):
        return {"id": item, "fid": None}
    return item

from keyboards import (
    back_btn, cancel_btn, main_menu,
    stats_menu, admins_menu, admin_perms_menu, select_user_menu,
    settings_menu, msg_settings_menu, away_menu,
    smart_replies_menu, view_sr_menu,
    quick_replies_menu, view_qr_menu,
    banned_menu, vip_menu, broadcast_menu,
    search_menu, search_results_menu, guide_menu,
    incoming_msg_btns, incoming_msg_btns_reacted, user_info_menu, confirm_menu,
    users_list_menu,
    welcome_links_btns, links_settings_menu,
    user_reply_keyboard, remove_reply_keyboard, menu_buttons_admin
)

# ═══════════════════════════════════════════════════════════════
#              🔔 دالة إشعار المالك (جديد)
# ═══════════════════════════════════════════════════════════════

async def notify_owner(bot, user, event: str):
    """إرسال إشعار للمالك عند أحداث المستخدمين"""
    uid = str(user.id)

    # بيانات المستخدم
    name     = (user.first_name or "") + (" " + user.last_name if user.last_name else "")
    username = f"@{user.username}" if user.username else "لا يوجد"
    badges   = []
    if uid in data.get("vip_users", []):    badges.append("⭐ VIP")
    if uid in data.get("admins",     {}):   badges.append("👨‍💼 مشرف")
    badge_line = "  |  ".join(badges) if badges else ""

    # عدد رسائله السابقة
    msg_count = data["users"].get(uid, {}).get("msg_count", 0)

    if event == "new_user":
        icon  = "🆕"
        title = "مستخدم جديد دخل البوت"
    elif event == "returned_user":
        icon  = "🔄"
        title = "مستخدم عاد للبوت"
    elif event == "blocked_bot":
        icon  = "🚫"
        title = "مستخدم حظر البوت"
    elif event == "returned_after_block":
        icon  = "🔓"
        title = "مستخدم رفع الحظر وعاد للبوت"
    else:
        return

    text = (
        f"{icon} **{title}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 الاسم: **{name.strip() or 'بدون اسم'}**\n"
        f"🔗 اليوزر: {username}\n"
        f"🆔 الآيدي: `{uid}`\n"
        f"📊 رسائله: **{msg_count}**\n"
        f"🕐 الوقت: {datetime.now().strftime('%Y-%m-%d  %H:%M')}\n"
        + (f"🏷️ {badge_line}\n" if badge_line else "")
        + "━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    try:
        await bot.send_message(OWNER_ID, text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"⚠️ notify_owner error: {e}")


# ═══════════════════════════════════════════════════════════════
#                      🏠 أمر /start
# ═══════════════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /start"""
    user = update.effective_user
    uid  = str(user.id)

    is_new = uid not in data["users"]   # هل دخل لأول مرة؟
    save_user(user)
    context.user_data.clear()

    # محظور
    if is_banned(user.id):
        await update.message.reply_text(data["messages"]["banned"])
        return

    # المالك
    if is_owner(user.id):
        stats_data = data["stats"]
        away = "🔴 غائب" if data["status"]["is_away"] else "🟢 متاح"
        text = f"""👑 **لوحة تحكم المالك**
━━━━━━━━━━━━━━━━━━━━━━━━
مرحباً يا **{md_escape(user.first_name)}** 👋

📊 **الإحصائيات:**
├ 👥 المستخدمين: **{len(data['users'])}**
├ 👨‍💼 المشرفين: **{len(data['admins'])}**
├ ⭐ VIP: **{len(data['vip_users'])}**
├ 🚫 المحظورين: **{len(data['banned'])}**
├ 📨 رسائل اليوم: **{stats_data['today_received']}**
└ 📤 ردود اليوم: **{stats_data['today_sent']}**

📡 الحالة: {away}
━━━━━━━━━━━━━━━━━━━━━━━━"""
        await update.message.reply_text(text, reply_markup=main_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    # مشرف
    if is_admin(user.id):
        await update.message.reply_text(
            f"👨‍💼 **مرحباً أيها المشرف {md_escape(user.first_name)}**\n\nيمكنك الرد على الرسائل المحولة",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── إشعار المالك (مستخدم جديد أو عائد) ──
    event = "new_user" if is_new else "returned_user"
    await notify_owner(context.bot, user, event)

    # ── رسالة ترحيب خاصة لمن حظل البوت ورجع ──
    uid = str(user.id)
    previously_blocked = data["users"].get(uid, {}).get("blocked_bot") is False and \
                         data["users"].get(uid, {}).get("returned_bot_time")

    if previously_blocked:
        welcome = data["messages"].get(
            "returned_after_block",
            "عوداً حميداً 😊\n\nسعيدون بعودتك! أرسل رسالتك وسيتم الرد عليك ❤️"
        ).replace("{name}", md_escape(user.first_name or "عزيزي"))

    if previously_blocked:
        welcome = data["messages"].get(
            "returned_after_block",
            "عوداً حميداً 😊\n\nسعيدون بعودتك! أرسل رسالتك وسيتم الرد عليك ❤️"
        ).replace("{name}", md_escape(user.first_name or "عزيزي"))
        await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN)
        if data["status"]["is_away"]:
            await asyncio.sleep(1)
            await update.message.reply_text(data["messages"]["away"])
        return

    # مستخدم عادي
    welcome = data["messages"]["welcome"].replace("{name}", md_escape(user.first_name or "عزيزي"))
    if is_vip(user.id):
        welcome = f"⭐ **مرحباً VIP** ⭐\n\n{welcome}"

    # واجهة الترحيب — صورة أو ملصق مع زر
    welcome_media = data.get("welcome_media", {})
    media_file_id = welcome_media.get("file_id")
    media_type    = welcome_media.get("type")  # "photo" أو "sticker"

    from telegram import InlineKeyboardMarkup, InlineKeyboardButton

    # بناء أزرار الترحيب: زر الإرسال + أزرار الروابط الخضراء
    send_row = [InlineKeyboardButton("📩 أرسل رسالتك", callback_data="start_chat")]
    extra_links = welcome_links_btns()
    if extra_links and extra_links.inline_keyboard:
        view_btn = InlineKeyboardMarkup([send_row] + list(extra_links.inline_keyboard))
    else:
        view_btn = InlineKeyboardMarkup([send_row])

    # القائمة الدائمة (Reply Keyboard)
    persistent_kb = user_reply_keyboard()

    if media_file_id and media_type == "photo":
        await update.message.reply_photo(
            photo=media_file_id,
            caption=welcome,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=view_btn
        )
        if persistent_kb:
            await update.message.reply_text("📋", reply_markup=persistent_kb)
    elif media_file_id and media_type == "sticker":
        await update.message.reply_sticker(sticker=media_file_id)
        await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN,
                                        reply_markup=persistent_kb or view_btn)
    else:
        await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN,
                                        reply_markup=persistent_kb or view_btn)

    # رسالة الغياب
    if data["status"]["is_away"]:
        await asyncio.sleep(1)
        await update.message.reply_text(data["messages"]["away"])


# ═══════════════════════════════════════════════════════════════
#              🚫 معالج حظر البوت (جديد)
# ═══════════════════════════════════════════════════════════════

async def my_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يُفعَّل لما حد يحظر البوت أو يرجع يفتحه"""
    member = update.my_chat_member
    if not member:
        return

    user      = member.from_user
    new_status = member.new_chat_member.status   # "kicked" أو "member" إلخ

    if new_status == "kicked":
        # حظر البوت
        await notify_owner(context.bot, user, "blocked_bot")

        # تحديث البيانات: نضيف ملاحظة إنه حظر
        uid = str(user.id)
        save_user(user)
        if uid in data["users"]:
            data["users"][uid]["blocked_bot"]      = True
            data["users"][uid]["blocked_bot_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_data()

    elif new_status == "member":
        # فتح البوت من جديد بعد الحظر
        uid = str(user.id)
        if data["users"].get(uid, {}).get("blocked_bot"):
            # مسح علامة الحظر
            data["users"][uid]["blocked_bot"]       = False
            data["users"][uid]["returned_bot_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_data()
            await notify_owner(context.bot, user, "returned_after_block")


# ═══════════════════════════════════════════════════════════════
#                      🔘 معالج الأزرار
# ═══════════════════════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج ضغطات الأزرار"""
    query = update.callback_query
    user  = query.from_user
    cb    = query.data

    await query.answer()

    # ══════════════════════════════════════════════════════════
    #                    الأزرار الأساسية
    # ══════════════════════════════════════════════════════════

    if cb == "cancel":
        context.user_data.clear()
        await query.edit_message_text("✅ تم الإلغاء", reply_markup=back_btn())
        return

    if cb == "main":
        if not is_owner(user.id):
            await query.answer("⛔ للمالك فقط", show_alert=True)
            return
        context.user_data.clear()
        stats_data = data["stats"]
        away = "🔴 غائب" if data["status"]["is_away"] else "🟢 متاح"
        text = f"""👑 **لوحة تحكم المالك**
━━━━━━━━━━━━━━━━━━━━━━━━
📊 المستخدمين: **{len(data['users'])}** | 📨 اليوم: **{stats_data['today_received']}**
📡 الحالة: {away}
━━━━━━━━━━━━━━━━━━━━━━━━"""
        await query.edit_message_text(text, reply_markup=main_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "stats":
        if not is_owner(user.id): return
        s = data["stats"]

        # إحصاء من حظر البوت
        blocked_count = sum(1 for u in data["users"].values() if u.get("blocked_bot"))

        text = f"""📊 **إحصائيات البوت**
━━━━━━━━━━━━━━━━━━━━━━━━
👥 المستخدمين: **{len(data['users'])}**
👨‍💼 المشرفين: **{len(data['admins'])}**
⭐ VIP: **{len(data['vip_users'])}**
🚫 المحظورين: **{len(data['banned'])}**
🛑 حظروا البوت: **{blocked_count}**

📨 الواردة: **{s['total_received']}**
📤 المرسلة: **{s['total_sent']}**
📨 اليوم: **{s['today_received']}**
📤 اليوم: **{s['today_sent']}**

🤖 ردود ذكية: **{len(data['smart_replies'])}**
💬 ردود جاهزة: **{len(data['quick_replies'])}**
━━━━━━━━━━━━━━━━━━━━━━━━"""
        await query.edit_message_text(text, reply_markup=stats_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "top_users":
        if not is_owner(user.id): return
        users = sorted(data["users"].items(), key=lambda x: x[1].get("msg_count", 0), reverse=True)[:10]
        text = "🏆 **أنشط 10 مستخدمين:**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        for i, (uid, info) in enumerate(users, 1):
            raw_name = info.get("name", "مجهول")[:15]
            name = raw_name.replace("*", "").replace("_", "").replace("`", "")
            count = info.get("msg_count", 0)
            vip   = "⭐" if uid in data["vip_users"] else ""
            text += f"{i}. {vip}**{name}**: {count} رسالة\n"
        if not users:
            text += "لا يوجد مستخدمين بعد"
        await query.edit_message_text(text, reply_markup=back_btn("stats"), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "admins":
        if not is_owner(user.id): return
        await query.edit_message_text(
            f"👥 **إدارة المشرفين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 العدد: **{len(data['admins'])}**",
            reply_markup=admins_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "add_admin":
        if not is_owner(user.id): return
        await query.edit_message_text(
            "👥 **إضافة مشرف**\n━━━━━━━━━━━━━━━━━━━━━━━━\nاختر من المستخدمين:",
            reply_markup=select_user_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "admin_by_id":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "admin_id"
        await query.edit_message_text("📝 **أرسل آيدي المشرف:**", reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("make_admin_"):
        if not is_owner(user.id): return
        uid = cb[11:]
        data["admins"][uid] = {
            "name": data["users"].get(uid, {}).get("name", "مشرف"),
            "can_reply": True, "can_broadcast": False, "can_ban": False
        }
        save_data()
        await query.answer("✅ تم إضافة المشرف", show_alert=True)
        await query.edit_message_text(
            f"👥 **المشرفين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 العدد: **{len(data['admins'])}**",
            reply_markup=admins_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("admin_"):
        if not is_owner(user.id): return
        uid  = cb[6:]
        info = data["admins"].get(uid, {})
        admin_name = info.get('name', 'مشرف').replace("*", "").replace("_", "").replace("`", "")
        text = f"👤 **إدارة المشرف**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📛 الاسم: **{admin_name}**\n🆔 `{uid}`\n━━━━━━━━━━━━━━━━━━━━━━━━"
        await query.edit_message_text(text, reply_markup=admin_perms_menu(uid), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("perm_"):
        if not is_owner(user.id): return
        parts = cb.split("_")
        perm  = parts[1]
        uid   = parts[2]
        key   = f"can_{perm}"
        if uid in data["admins"]:
            data["admins"][uid][key] = not data["admins"][uid].get(key, False)
            save_data()
        info = data["admins"].get(uid, {})
        text = f"👤 **إدارة المشرف**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📛 الاسم: **{info.get('name', 'مشرف')}**\n🆔 `{uid}`"
        await query.edit_message_text(text, reply_markup=admin_perms_menu(uid), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("remove_admin_"):
        if not is_owner(user.id): return
        uid = cb[13:]
        if uid in data["admins"]:
            del data["admins"][uid]
            save_data()
        await query.answer("✅ تم إزالة المشرف", show_alert=True)
        await query.edit_message_text(
            f"👥 **المشرفين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 العدد: **{len(data['admins'])}**",
            reply_markup=admins_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "settings":
        if not is_owner(user.id): return
        await query.edit_message_text("⚙️ **الإعدادات**\n━━━━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=settings_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "msg_settings":
        if not is_owner(user.id): return
        await query.edit_message_text("📝 **رسائل البوت**\n━━━━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=msg_settings_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "start_chat":
        await query.answer()
        await query.message.reply_text("📩 أرسل رسالتك الآن وسيتم الرد عليك قريباً ")
        return

    if cb == "users_list":
        if not is_owner(user.id): return
        total = len(data["users"])
        await query.edit_message_text(
            f"👥 **مستخدمين البوت** — {total} مستخدم",
            reply_markup=users_list_menu(0),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if cb.startswith("users_page_"):
        if not is_owner(user.id): return
        page = int(cb.split("_")[-1])
        total = len(data["users"])
        await query.edit_message_text(
            f"👥 **مستخدمين البوت** — {total} مستخدم",
            reply_markup=users_list_menu(page),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if cb == "back_main":
        if not is_owner(user.id): return
        away = "🔴 غائب" if data["status"]["is_away"] else "🟢 متاح"
        text = (
            "👑 **لوحة تحكم المالك**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 المستخدمين: **{len(data['users'])}**\n"
            f"📡 الحالة: {away}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await query.edit_message_text(text, reply_markup=main_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "edit_welcome":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "edit_welcome"
        await query.edit_message_text(
            f"✏️ **رسالة الترحيب الحالية:**\n\n{data['messages']['welcome']}\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n📝 أرسل الرسالة الجديدة\n💡 استخدم {{name}} لاسم المستخدم",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "set_welcome_media":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "set_welcome_media"
        await query.edit_message_text(
            "🖼 أرسل صورة أو ملصق ليظهر كواجهة الترحيب\n\n"
            "سيظهر للمستخدم مع نص الترحيب وزر 'أرسل رسالتك'",
            reply_markup=back_btn("msg_settings")
        )
        return

    if cb == "clear_welcome_media":
        if not is_owner(user.id): return
        data["welcome_media"] = {}
        save_data()
        await query.answer("✅ تم حذف صورة الواجهة", show_alert=True)
        return

    if cb == "edit_away":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "edit_away"
        await query.edit_message_text(
            f"✏️ **رسالة الغياب الحالية:**\n\n{data['messages']['away']}\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n📝 أرسل الرسالة الجديدة:",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "edit_received":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "edit_received"
        await query.edit_message_text(
            f"✏️ **رسالة الاستلام الحالية:**\n\n{data['messages']['received']}\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n📝 أرسل الرسالة الجديدة:",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "edit_returned_block":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "edit_returned_block"
        current = data["messages"].get("returned_after_block", "عوداً حميداً {name} 😊")
        await query.edit_message_text(
            f"✏️ **رسالة العودة بعد الحظر الحالية:**\n\n{current}\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n📝 أرسل الرسالة الجديدة\n💡 استخدم {{name}} لاسم المستخدم",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "away_settings":
        if not is_owner(user.id): return
        status = "🟢 **مفعل**" if data["status"]["is_away"] else "🔴 **معطل**"
        await query.edit_message_text(
            f"⏰ **وضع الغياب**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 الحالة: {status}\n\n📝 الرسالة:\n{data['messages']['away']}",
            reply_markup=away_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "toggle_away":
        if not is_owner(user.id): return
        data["status"]["is_away"] = not data["status"]["is_away"]
        save_data()
        status = "✅ تم تفعيل الغياب" if data["status"]["is_away"] else "❌ تم تعطيل الغياب"
        await query.answer(status, show_alert=True)
        status_text = "🟢 **مفعل**" if data["status"]["is_away"] else "🔴 **معطل**"
        await query.edit_message_text(
            f"⏰ **وضع الغياب**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 الحالة: {status_text}",
            reply_markup=away_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "toggle_smart":
        if not is_owner(user.id): return
        data["status"]["smart_reply_enabled"] = not data["status"]["smart_reply_enabled"]
        save_data()
        status = "✅ تم تفعيل الردود الذكية" if data["status"]["smart_reply_enabled"] else "❌ تم تعطيلها"
        await query.answer(status, show_alert=True)
        await query.edit_message_text("⚙️ **الإعدادات**\n━━━━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=settings_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "links_settings":
        if not is_owner(user.id): return
        links = data.get("links", {})
        owner_val   = links.get("owner_account")  or "لم يُضبط بعد"
        group_val   = links.get("doctor_fonts_group") or "لم يُضبط بعد"
        owner_label = links.get("owner_label", "👤 حساب المالك") or "👤 حساب المالك"
        group_label = links.get("group_label", "👨‍💻 مجموعة دكتور خطوط") or "👨‍💻 مجموعة دكتور خطوط"
        await query.edit_message_text(
            f"🔗 **إدارة الروابط**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 حساب المالك:\n`{owner_val}`\n"
            f"📝 نص الزر: {owner_label}\n\n"
            f"👨‍💻 مجموعة دكتور خطوط:\n`{group_val}`\n"
            f"📝 نص الزر: {group_label}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 هذه الأزرار تظهر للمستخدمين في رسالة الترحيب\n"
            f"✨ يمكن إضافة إيموجي بريميوم في نص الزر",
            reply_markup=links_settings_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "edit_owner_link":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "edit_owner_link"
        current = data.get("links", {}).get("owner_account", "")
        current_text = f"\n\n📌 الرابط الحالي:\n`{current}`" if current else ""
        await query.edit_message_text(
            f"✏️ **تعديل رابط حساب المالك**\n━━━━━━━━━━━━━━━━━━━━━━━━{current_text}\n\n"
            f"📝 أرسل الرابط الجديد (مثال: https://t.me/username)\n"
            f"أو أرسل **حذف** لإزالة الرابط",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "edit_group_link":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "edit_group_link"
        current = data.get("links", {}).get("doctor_fonts_group", "")
        current_text = f"\n\n📌 الرابط الحالي:\n`{current}`" if current else ""
        await query.edit_message_text(
            f"✏️ **تعديل رابط مجموعة دكتور خطوط**\n━━━━━━━━━━━━━━━━━━━━━━━━{current_text}\n\n"
            f"📝 أرسل الرابط الجديد (مثال: https://t.me/groupname)\n"
            f"أو أرسل **حذف** لإزالة الرابط",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "edit_owner_label":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "edit_owner_label"
        current = data.get("links", {}).get("owner_label", "👤 حساب المالك")
        await query.edit_message_text(
            f"✏️ **تعديل نص زر حساب المالك**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 النص الحالي: {current}\n\n"
            f"📝 أرسل النص الجديد للزر\n"
            f"✨ يمكنك إرسال إيموجي بريميوم مع النص",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "edit_group_label":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "edit_group_label"
        current = data.get("links", {}).get("group_label", "👨‍💻 مجموعة دكتور خطوط")
        await query.edit_message_text(
            f"✏️ **تعديل نص زر مجموعة دكتور خطوط**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 النص الحالي: {current}\n\n"
            f"📝 أرسل النص الجديد للزر\n"
            f"✨ يمكنك إرسال إيموجي بريميوم مع النص",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    # ── إدارة القائمة الدائمة ──
    if cb == "menu_buttons_settings":
        if not is_owner(user.id): return
        count = len(data.get("menu_buttons", []))
        await query.edit_message_text(
            f"📋 **القائمة الدائمة للمستخدمين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 عدد الأزرار: **{count}**\n\n"
            f"💡 هذه الأزرار تظهر دائماً في الأسفل للمستخدم\n"
            f"✨ تدعم الإيموجي البريميوم\n"
            f"📐 تُرتَّب صفَّين صفَّين",
            reply_markup=menu_buttons_admin(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "mb_add":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "mb_add"
        await query.edit_message_text(
            "➕ **إضافة زر للقائمة الدائمة**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📝 أرسل نص الزر\n"
            "✨ يمكنك إرسال إيموجي بريميوم مع النص",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("mb_del_"):
        if not is_owner(user.id): return
        idx = int(cb.split("_")[-1])
        buttons = data.get("menu_buttons", [])
        if 0 <= idx < len(buttons):
            removed = buttons.pop(idx)
            data["menu_buttons"] = buttons
            save_data()
            await query.answer(f"🗑️ تم حذف: {removed['text'][:15]}", show_alert=True)
        count = len(data.get("menu_buttons", []))
        await query.edit_message_text(
            f"📋 **القائمة الدائمة للمستخدمين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 عدد الأزرار: **{count}**",
            reply_markup=menu_buttons_admin(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "mb_clear":
        if not is_owner(user.id): return
        data["menu_buttons"] = []
        save_data()
        await query.answer("🗑️ تم حذف كل الأزرار", show_alert=True)
        await query.edit_message_text(
            "📋 **القائمة الدائمة للمستخدمين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📊 عدد الأزرار: **0**",
            reply_markup=menu_buttons_admin(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("mb_noop_"):
        await query.answer()
        return

    if cb == "smart_replies":
        if not is_owner(user.id): return
        count  = len(data["smart_replies"])
        status = "🟢 مفعل" if data["status"]["smart_reply_enabled"] else "🔴 معطل"
        await query.edit_message_text(
            f"🤖 **الردود الذكية** ({status})\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 العدد: **{count}**\n\n💡 يرد البوت تلقائياً عند كتابة كلمة معينة",
            reply_markup=smart_replies_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "add_sr":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "sr_trigger"
        await query.edit_message_text(
            "➕ **إضافة رد ذكي**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📝 أرسل **الكلمة المفعّلة:**\n\nمثال: السلام عليكم",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "add_sr_bulk":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "sr_bulk"
        await query.edit_message_text(
            "📋 **إضافة قائمة ردود**\n━━━━━━━━━━━━━━━━━━━━━━━━\nأرسل بالتنسيق:\n**الكلمة ، الرد**\n\nمثال:\nالسلام عليكم ، وعليكم السلام\nكيف الحال ، بخير الحمد لله",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("view_sr_"):
        if not is_owner(user.id): return
        trigger_part = cb[8:]
        full_trigger = None
        for t in data["smart_replies"]:
            if t.startswith(trigger_part) or trigger_part in t:
                full_trigger = t
                break
        if full_trigger:
            response = data["smart_replies"][full_trigger]
            await query.edit_message_text(
                f"💬 **رد ذكي**\n━━━━━━━━━━━━━━━━━━━━━━━━\n🔹 الكلمة:\n{full_trigger}\n\n🔸 الرد:\n{response}",
                reply_markup=view_sr_menu(full_trigger[:30]), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("del_sr_"):
        if not is_owner(user.id): return
        trigger_part = cb[7:]
        for t in list(data["smart_replies"].keys()):
            if t.startswith(trigger_part) or trigger_part in t:
                del data["smart_replies"][t]
                save_data()
                break
        await query.answer("✅ تم الحذف", show_alert=True)
        await query.edit_message_text(
            f"🤖 **الردود الذكية**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 العدد: **{len(data['smart_replies'])}**",
            reply_markup=smart_replies_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "delete_all_sr":
        if not is_owner(user.id): return
        await query.edit_message_text("⚠️ **حذف كل الردود الذكية؟**",
            reply_markup=confirm_menu("delete_sr", "smart_replies"), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "confirm_delete_sr":
        if not is_owner(user.id): return
        data["smart_replies"] = {}
        save_data()
        await query.answer("✅ تم حذف الكل", show_alert=True)
        await query.edit_message_text(
            "🤖 **الردود الذكية**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 العدد: **0**",
            reply_markup=smart_replies_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "quick_replies":
        if not is_owner(user.id): return
        await query.edit_message_text(
            f"💬 **الردود الجاهزة**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 العدد: **{len(data['quick_replies'])}**",
            reply_markup=quick_replies_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "add_qr":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "qr_title"
        await query.edit_message_text("📝 **أرسل عنوان الرد:**\n(مثال: شكر، ترحيب)",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("view_qr_"):
        if not is_owner(user.id): return
        title   = cb[8:]
        content = data["quick_replies"].get(title, "")
        await query.edit_message_text(f"💬 **{title}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n{content}",
            reply_markup=view_qr_menu(title), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("del_qr_"):
        if not is_owner(user.id): return
        title = cb[7:]
        if title in data["quick_replies"]:
            del data["quick_replies"][title]
            save_data()
        await query.answer("✅ تم الحذف", show_alert=True)
        await query.edit_message_text(
            f"💬 **الردود الجاهزة**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 العدد: **{len(data['quick_replies'])}**",
            reply_markup=quick_replies_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "banned_list":
        if not is_owner(user.id): return
        await query.edit_message_text(
            f"🚫 **المحظورين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 العدد: **{len(data['banned'])}**\n\n💡 اضغط للإلغاء",
            reply_markup=banned_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "ban_by_id":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "ban_id"
        await query.edit_message_text("📝 **أرسل آيدي المستخدم للحظر:**",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("ban_"):
        uid = cb[4:]
        if uid not in data["banned"]:
            data["banned"].append(uid)
            save_data()
            await query.answer("✅ تم الحظر", show_alert=True)
        return

    if cb.startswith("unban_"):
        uid = cb[6:]
        if uid in data["banned"]:
            data["banned"].remove(uid)
            save_data()
            await query.answer("✅ تم إلغاء الحظر", show_alert=True)
        if is_owner(user.id):
            try:
                await query.edit_message_text(
                    f"🚫 **المحظورين**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 العدد: **{len(data['banned'])}**",
                    reply_markup=banned_menu(), parse_mode=ParseMode.MARKDOWN)
            except:
                pass
        return

    if cb == "vip_list":
        if not is_owner(user.id): return
        await query.edit_message_text(
            f"⭐ **VIP**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 العدد: **{len(data['vip_users'])}**\n\n💡 اضغط للإزالة",
            reply_markup=vip_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "add_vip":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "vip_id"
        await query.edit_message_text("📝 **أرسل آيدي المستخدم:**",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("addvip_"):
        uid = cb[7:]
        if uid not in data["vip_users"]:
            data["vip_users"].append(uid)
            save_data()
            await query.answer("⭐ تم إضافته لـ VIP", show_alert=True)
        return

    if cb.startswith("unvip_"):
        uid = cb[6:]
        if uid in data["vip_users"]:
            data["vip_users"].remove(uid)
            save_data()
            await query.answer("✅ تم إزالته من VIP", show_alert=True)
        if is_owner(user.id):
            try:
                await query.edit_message_text(
                    f"⭐ **VIP**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📊 العدد: **{len(data['vip_users'])}**",
                    reply_markup=vip_menu(), parse_mode=ParseMode.MARKDOWN)
            except:
                pass
        return

    if cb == "broadcast":
        if not is_owner(user.id): return
        await query.edit_message_text("📢 **الإذاعة**\n━━━━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=broadcast_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "bc_all":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "broadcast_all"
        await query.edit_message_text(
            f"📢 **إذاعة للكل**\n━━━━━━━━━━━━━━━━━━━━━━━━\n👥 سيتم الإرسال لـ **{len(data['users'])}** مستخدم\n\n💡 أرسل الرسالة:",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "bc_vip":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "broadcast_vip"
        await query.edit_message_text(
            f"⭐ **إذاعة VIP**\n━━━━━━━━━━━━━━━━━━━━━━━━\n👥 سيتم الإرسال لـ **{len(data['vip_users'])}** مستخدم\n\n💡 أرسل الرسالة:",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "bc_user":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "bc_user_id"
        await query.edit_message_text("📤 **إرسال لمستخدم**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📝 أرسل الآيدي:",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "search":
        if not is_owner(user.id): return
        await query.edit_message_text("🔍 **البحث**\n━━━━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=search_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "search_name":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "search_name"
        await query.edit_message_text("🔍 **البحث بالاسم**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📝 أرسل الاسم:",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "search_id":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "search_id"
        await query.edit_message_text("🔍 **البحث بالآيدي**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📝 أرسل الآيدي:",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("user_"):
        if not is_owner(user.id): return
        uid  = cb[5:]
        info = data["users"].get(uid, {})
        if info:
            badges = []
            if uid in data["vip_users"]: badges.append("⭐ VIP")
            if uid in data["banned"]:    badges.append("🚫 محظور")
            if uid in data["admins"]:    badges.append("👨‍💼 مشرف")
            if info.get("blocked_bot"):  badges.append("🛑 حظر البوت")
            note       = data["user_notes"].get(uid, "لا يوجد")
            import html as html_mod
            def h(t): return html_mod.escape(str(t))
            uname_val  = info.get("username") or ""
            uname_line = f"@{h(uname_val)}" if uname_val else "لا يوجد"
            badge_line = "  •  ".join(badges) if badges else ""
            msg_count  = info.get("msg_count", 0)
            joined     = info.get("joined", "?")
            lines = [
                "\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557",
                "\u2551  \U0001f464  \u0628\u0637\u0627\u0642\u0629 \u0627\u0644\u0645\u0633\u062a\u062e\u062f\u0645   \u2551",
                "\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d",
                "",
                f"<b>\U0001f4db  {h(info.get('name','\u0645\u062c\u0647\u0648\u0644'))}</b>",
                f"\U0001f517  {uname_line}",
                f"\U0001f194  <code>{uid}</code>",
                "",
                "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
                f"\U0001f4ca  \u0627\u0644\u0631\u0633\u0627\u0626\u0644:  <b>{msg_count}</b>",
                f"\U0001f4c5  \u0627\u0646\u0636\u0645:     {joined}",
                f"\U0001f4dd  \u0645\u0644\u0627\u062d\u0638\u0629:   {h(note)}",
            ]
            if badge_line:
                lines.append(f"\U0001f3f7  {badge_line}")
            lines.append("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
            text = "\n".join(lines)
            await query.edit_message_text(text, reply_markup=user_info_menu(int(uid)), parse_mode=ParseMode.HTML)
        else:
            await query.answer("المستخدم غير موجود في القاعدة", show_alert=True)
        return

    if cb.startswith("note_"):
        if not is_owner(user.id): return
        uid = cb[5:]
        context.user_data["waiting"] = f"note_{uid}"
        await query.message.reply_text("📝 **أرسل الملاحظة:**", reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("sendto_"):
        if not is_owner(user.id): return
        uid = cb[7:]
        context.user_data["waiting"] = f"sendto_{uid}"
        await query.message.reply_text("📤 **أرسل الرسالة:**", reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("reply_"):
        uid  = cb[6:]
        context.user_data["replying_to"] = uid
        name = data["users"].get(uid, {}).get("name", uid)
        await query.message.reply_text(
            f"💬 **الرد على {name}**\n━━━━━━━━━━━━━━━━━━━━━━━━\n📝 أرسل ردك الآن:",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb.startswith("sendqr_"):
        parts   = cb.split("_", 2)
        uid     = parts[1]
        title   = parts[2] if len(parts) > 2 else ""
        content = data["quick_replies"].get(title, "")
        if content:
            try:
                await context.bot.send_message(int(uid), content)
                update_stats("sent")
                await query.answer("✅ تم الإرسال", show_alert=True)
            except Exception as e:
                await query.answer(f"❌ فشل: {e}", show_alert=True)
        return

    if cb == "guide":
        if not is_owner(user.id): return
        await query.edit_message_text("📖 **دليل الاستخدام**\n━━━━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=guide_menu(), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "guide_reply":
        text = "📩 **الرد على الرسائل**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n**1️⃣ بالزر:**\n• اضغط ↩️ رد\n• اكتب ردك\n\n**2️⃣ بالريبلاي:**\n• Reply على الرسالة المحولة\n• اكتب ردك"
        await query.edit_message_text(text, reply_markup=back_btn("guide"), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "guide_smart":
        text = "🤖 **الردود الذكية**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n**الفكرة:**\nيرد البوت تلقائياً عند كلمة معينة\n\n**إضافة:**\nاذهب للردود الذكية → إضافة"
        await query.edit_message_text(text, reply_markup=back_btn("guide"), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "guide_reactions":
        text = ("😀 **التفاعلات**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "**تفاعل عادي على رسالة المستخدم:**\n"
                "Reply + `ص 😂` → يضع تفاعل إيموجي عادي\n"
                "Reply + `ص 🫡` → تفاعل عسكري\n\n"
                "**⭐️ إيموجي بريميوم في الرد:**\n"
                "عند الرد النصي العادي، يُضاف تلقائياً\n"
                "إيموجي بريميوم من الحزمة الأولى في أول الرسالة\n\n"
                "**ملاحظة:** التفاعلات المدفوعة `{N}` غير مفعّلة\n"
                "استخدم `ص` + إيموجي عادي فقط\n\n"
                "**إدارة الحزم:**\n"
                "• `حزمة رابط` → إضافة حزمة\n"
                "• `حزم` → عرض الحزم\n"
                "• `استعراض` → عرض كل الإيموجيات بأرقامها\n"
                "• `حذف حزمة N` → حذف\n"
                "• `تحديث حزمة N` → تحديث")
        await query.edit_message_text(text, reply_markup=back_btn("guide"), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "guide_delete":
        text = "🗑️ **حذف الرسائل**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n**الطريقة:**\n1. Reply على رسالتك المرسلة\n2. اكتب: `مسح`"
        await query.edit_message_text(text, reply_markup=back_btn("guide"), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "guide_commands":
        text = ("📋 **الأوامر**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "`حظر ID` - حظر\n`فك ID` - فك حظر\n`vip ID` - إضافة VIP\n"
                "`أرسل ID رسالة` - إرسال\n`معلومات ID` - معلومات\n"
                "`مسح` - حذف (Reply)\n`ص 😂` - تفاعل عادي (Reply)\n"
                "`ص 🫡` - تفاعل عسكري (Reply)\n"
                "`ؤ نص` - تعديل الرسالة (Reply)\n"
                "`حظر` - حظر بالريبلاي\n`كتم` - كتم/إلغاء كتم (Reply)\n\n"
                "**⭐️ إيموجي بريميوم تلقائي:**\n"
                "يُضاف تلقائياً عند الرد النصي إذا وُجدت حزمة\n\n"
                "**حزم الإيموجيات:**\n"
                "`حزمة رابط` - إضافة حزمة\n"
                "`حزم` - عرض الحزم\n"
                "`استعراض` - عرض كل الإيموجيات بأرقامها\n"
                "`حذف حزمة N` - حذف\n"
                "`تحديث حزمة N` - تحديث")
        await query.edit_message_text(text, reply_markup=back_btn("guide"), parse_mode=ParseMode.MARKDOWN)
        return

    if cb == "none":
        return

    # ── معالج أزرار التفاعل — الأونر يضغط وتوصل للمستخدم ──
    if cb.startswith("react_"):
        # react_{user_id}_{emoji}
        parts = cb.split("_", 2)
        if len(parts) < 3:
            return
        react_uid = parts[1]
        react_emoji = parts[2]

        # إشعار المستخدم بالتفاعل
        user_name_owner = (query.from_user.first_name or "") + (" " + query.from_user.last_name if query.from_user.last_name else "")
        try:
            await context.bot.send_message(
                int(react_uid),
                f"{react_emoji} تفاعل معك صاحب البوت على رسالتك!",
            )
        except Exception:
            pass

        # تحديث الأزرار لإظهار التفاعل المختار
        try:
            from keyboards import incoming_msg_btns_reacted
            await query.edit_message_reply_markup(
                reply_markup=incoming_msg_btns_reacted(int(react_uid), react_emoji)
            )
        except Exception:
            pass

        await query.answer(f"{react_emoji} تم إرسال التفاعل!", show_alert=False)
        return


# ═══════════════════════════════════════════════════════════════
#                      💬 معالج الرسائل
# ═══════════════════════════════════════════════════════════════

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    msg  = update.message

    # ✅ تجاهل رسائل المجموعات والقنوات - البوت يعمل فقط في المحادثات الخاصة
    if msg.chat.type in ("group", "supergroup", "channel"):
        # يمكن للبوت أن يكون مساعداً في المجموعة بدون ما يعالج الرسائل كبوت تواصل
        return

    user = update.effective_user

    save_user(user)

    if is_banned(user.id):
        return

    waiting = context.user_data.get("waiting")

    if waiting == "edit_welcome" and msg.text:
        data["messages"]["welcome"] = msg.text
        save_data(); context.user_data.clear()
        await msg.reply_text("✅ تم حفظ رسالة الترحيب!", reply_markup=back_btn("msg_settings"))
        return

    if waiting == "set_welcome_media":
        if msg.photo:
            data["welcome_media"] = {"file_id": msg.photo[-1].file_id, "type": "photo"}
            save_data(); context.user_data.clear()
            await msg.reply_text("✅ تم حفظ صورة الواجهة!", reply_markup=back_btn("msg_settings"))
        elif msg.sticker:
            data["welcome_media"] = {"file_id": msg.sticker.file_id, "type": "sticker"}
            save_data(); context.user_data.clear()
            await msg.reply_text("✅ تم حفظ الملصق كواجهة!", reply_markup=back_btn("msg_settings"))
        else:
            await msg.reply_text("⚠️ أرسل صورة أو ملصق فقط")
        return

    if waiting == "edit_away" and msg.text:
        data["messages"]["away"] = msg.text
        save_data(); context.user_data.clear()
        await msg.reply_text("✅ تم حفظ رسالة الغياب!", reply_markup=back_btn("away_settings"))
        return

    if waiting == "edit_received" and msg.text:
        data["messages"]["received"] = msg.text
        save_data(); context.user_data.clear()
        await msg.reply_text("✅ تم حفظ رسالة الاستلام!", reply_markup=back_btn("msg_settings"))
        return

    if waiting == "edit_returned_block" and msg.text:
        data["messages"]["returned_after_block"] = msg.text
        save_data(); context.user_data.clear()
        await msg.reply_text("✅ تم حفظ رسالة العودة بعد الحظر!", reply_markup=back_btn("msg_settings"))
        return

    if waiting == "edit_owner_link" and msg.text:
        if "links" not in data:
            data["links"] = {"owner_account": "", "doctor_fonts_group": ""}
        if msg.text.strip().lower() == "حذف":
            data["links"]["owner_account"] = ""
            save_data(); context.user_data.clear()
            await msg.reply_text("🗑 تم حذف رابط حساب المالك", reply_markup=back_btn("links_settings"))
        else:
            data["links"]["owner_account"] = msg.text.strip()
            save_data(); context.user_data.clear()
            await msg.reply_text("✅ تم حفظ رابط حساب المالك!", reply_markup=back_btn("links_settings"))
        return

    if waiting == "edit_group_link" and msg.text:
        if "links" not in data:
            data["links"] = {"owner_account": "", "doctor_fonts_group": ""}
        if msg.text.strip().lower() == "حذف":
            data["links"]["doctor_fonts_group"] = ""
            save_data(); context.user_data.clear()
            await msg.reply_text("🗑 تم حذف رابط مجموعة دكتور خطوط", reply_markup=back_btn("links_settings"))
        else:
            data["links"]["doctor_fonts_group"] = msg.text.strip()
            save_data(); context.user_data.clear()
            await msg.reply_text("✅ تم حفظ رابط مجموعة دكتور خطوط!", reply_markup=back_btn("links_settings"))
        return

    if waiting == "edit_owner_label":
        # دعم الإيموجي البريميوم: نحفظ النص كما هو (التيليغرام يرسله مع entities)
        if not msg.text and not msg.caption:
            return
        label_text = msg.text or msg.caption or ""
        if not label_text.strip():
            return
        if "links" not in data:
            data["links"] = {"owner_account": "", "doctor_fonts_group": "",
                             "owner_label": "👤 حساب المالك", "group_label": "👨‍💻 مجموعة دكتور خطوط"}
        data["links"]["owner_label"] = label_text
        save_data(); context.user_data.clear()
        await msg.reply_text(
            f"✅ تم حفظ نص زر حساب المالك!\n\n📝 النص الجديد: {label_text}",
            reply_markup=back_btn("links_settings"))
        return

    if waiting == "edit_group_label":
        if not msg.text and not msg.caption:
            return
        label_text = msg.text or msg.caption or ""
        if not label_text.strip():
            return
        if "links" not in data:
            data["links"] = {"owner_account": "", "doctor_fonts_group": "",
                             "owner_label": "👤 حساب المالك", "group_label": "👨‍💻 مجموعة دكتور خطوط"}
        data["links"]["group_label"] = label_text
        save_data(); context.user_data.clear()
        await msg.reply_text(
            f"✅ تم حفظ نص زر مجموعة دكتور خطوط!\n\n📝 النص الجديد: {label_text}",
            reply_markup=back_btn("links_settings"))
        return

    if waiting == "mb_add":
        btn_text = msg.text or msg.caption or ""
        if not btn_text.strip():
            await msg.reply_text("❌ أرسل نص الزر", reply_markup=cancel_btn())
            return
        if "menu_buttons" not in data:
            data["menu_buttons"] = []
        data["menu_buttons"].append({"text": btn_text})
        save_data(); context.user_data.clear()
        count = len(data["menu_buttons"])
        await msg.reply_text(
            f"✅ تم إضافة الزر!\n\n📝 النص: {btn_text}\n📊 إجمالي الأزرار: {count}",
            reply_markup=back_btn("menu_buttons_settings"))
        return

    if waiting == "sr_trigger" and msg.text:
        context.user_data["sr_trigger"] = msg.text.strip()
        context.user_data["waiting"]    = "sr_response"
        await msg.reply_text(f"✅ الكلمة: **{msg.text}**\n\n📝 الآن أرسل **الرد:**",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if waiting == "sr_response" and msg.text:
        trigger = context.user_data.get("sr_trigger", "")
        data["smart_replies"][trigger] = msg.text.strip()
        save_data(); context.user_data.clear()
        await msg.reply_text("✅ تم إضافة الرد الذكي!", reply_markup=back_btn("smart_replies"))
        return

    if waiting == "sr_bulk" and msg.text:
        lines = msg.text.strip().split("\n")
        added = 0
        for line in lines:
            sep = "،" if "،" in line else ","
            if sep in line:
                parts = line.split(sep, 1)
                if len(parts) == 2:
                    t, r = parts[0].strip(), parts[1].strip()
                    if t and r:
                        data["smart_replies"][t] = r
                        added += 1
        save_data(); context.user_data.clear()
        await msg.reply_text(f"✅ تم إضافة **{added}** رد!", reply_markup=back_btn("smart_replies"), parse_mode=ParseMode.MARKDOWN)
        return

    if waiting == "qr_title" and msg.text:
        context.user_data["qr_title"] = msg.text.strip()
        context.user_data["waiting"]  = "qr_content"
        await msg.reply_text("📝 أرسل **محتوى** الرد:", reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN)
        return

    if waiting == "qr_content" and msg.text:
        title = context.user_data.get("qr_title", "رد")
        data["quick_replies"][title] = msg.text
        save_data(); context.user_data.clear()
        await msg.reply_text("✅ تم الحفظ!", reply_markup=back_btn("quick_replies"))
        return

    if waiting == "admin_id" and msg.text:
        uid = msg.text.strip()
        if uid.isdigit():
            data["admins"][uid] = {"name": "مشرف", "can_reply": True, "can_broadcast": False, "can_ban": False}
            save_data()
            await msg.reply_text(f"✅ تم إضافة `{uid}` كمشرف", reply_markup=back_btn("admins"), parse_mode=ParseMode.MARKDOWN)
        else:
            await msg.reply_text("❌ آيدي غير صحيح", reply_markup=back_btn("admins"))
        context.user_data.clear()
        return

    if waiting == "ban_id" and msg.text:
        uid = msg.text.strip()
        if uid.isdigit() and uid not in data["banned"]:
            data["banned"].append(uid)
            save_data()
            await msg.reply_text(f"✅ تم حظر `{uid}`", reply_markup=back_btn("banned_list"), parse_mode=ParseMode.MARKDOWN)
        context.user_data.clear()
        return

    if waiting == "vip_id" and msg.text:
        uid = msg.text.strip()
        if uid.isdigit() and uid not in data["vip_users"]:
            data["vip_users"].append(uid)
            save_data()
            await msg.reply_text(f"⭐ تم إضافة `{uid}` لـ VIP", reply_markup=back_btn("vip_list"), parse_mode=ParseMode.MARKDOWN)
        context.user_data.clear()
        return

    if waiting and waiting.startswith("note_") and msg.text:
        uid = waiting[5:]
        data["user_notes"][uid] = msg.text.strip()
        save_data(); context.user_data.clear()
        await msg.reply_text("✅ تم حفظ الملاحظة!", reply_markup=back_btn())
        return

    if waiting and waiting.startswith("sendto_"):
        uid = waiting[7:]
        try:
            await context.bot.copy_message(int(uid), msg.chat_id, msg.message_id)
            update_stats("sent")
            await msg.reply_text("✅ تم الإرسال!", reply_markup=back_btn())
        except Exception as e:
            await msg.reply_text(f"❌ فشل: {e}", reply_markup=back_btn())
        context.user_data.clear()
        return

    if waiting == "search_name" and msg.text:
        q       = msg.text.strip().lower()
        results = [(uid, info) for uid, info in data["users"].items() if q in info.get("name", "").lower()]
        context.user_data.clear()
        if results:
            await msg.reply_text(f"🔍 **النتائج ({len(results)}):**", reply_markup=search_results_menu(results), parse_mode=ParseMode.MARKDOWN)
        else:
            await msg.reply_text("❌ لا توجد نتائج", reply_markup=back_btn("search"))
        return

    if waiting == "search_id" and msg.text:
        uid  = msg.text.strip()
        info = data["users"].get(uid)
        context.user_data.clear()
        if info:
            await msg.reply_text("🔍 **تم العثور:**", reply_markup=search_results_menu([(uid, info)]), parse_mode=ParseMode.MARKDOWN)
        else:
            await msg.reply_text("❌ لم يتم العثور", reply_markup=back_btn("search"))
        return

    if waiting == "bc_user_id" and msg.text:
        uid = msg.text.strip()
        if uid.isdigit():
            context.user_data["bc_target"] = uid
            context.user_data["waiting"]   = "bc_user_msg"
            await msg.reply_text("📝 أرسل الرسالة:", reply_markup=cancel_btn())
        else:
            await msg.reply_text("❌ آيدي غير صحيح", reply_markup=cancel_btn())
        return

    if waiting == "bc_user_msg":
        uid = context.user_data.get("bc_target")
        try:
            await context.bot.copy_message(int(uid), msg.chat_id, msg.message_id)
            update_stats("sent")
            await msg.reply_text("✅ تم الإرسال!", reply_markup=back_btn("broadcast"))
        except Exception as e:
            await msg.reply_text(f"❌ فشل: {e}", reply_markup=back_btn("broadcast"))
        context.user_data.clear()
        return

    if waiting == "broadcast_all":
        context.user_data.clear()
        status_msg = await msg.reply_text("📤 جاري الإرسال...")
        success, failed = 0, 0
        for uid in list(data["users"].keys()):
            if uid not in data["banned"]:
                try:
                    await context.bot.copy_message(int(uid), msg.chat_id, msg.message_id)
                    success += 1
                except:
                    failed += 1
                await asyncio.sleep(0.03)
        data["stats"]["total_sent"] += success
        save_data()
        await status_msg.edit_text(f"✅ **تمت الإذاعة**\n✅ نجح: {success}\n❌ فشل: {failed}",
            reply_markup=back_btn("broadcast"), parse_mode=ParseMode.MARKDOWN)
        return

    if waiting == "broadcast_vip":
        context.user_data.clear()
        status_msg = await msg.reply_text("📤 جاري الإرسال...")
        success, failed = 0, 0
        for uid in data["vip_users"]:
            try:
                await context.bot.copy_message(int(uid), msg.chat_id, msg.message_id)
                success += 1
            except:
                failed += 1
            await asyncio.sleep(0.03)
        await status_msg.edit_text(f"⭐ **تمت الإذاعة**\n✅ نجح: {success}\n❌ فشل: {failed}",
            reply_markup=back_btn("broadcast"), parse_mode=ParseMode.MARKDOWN)
        return

    replying_to = context.user_data.get("replying_to")
    if replying_to:
        context.user_data.clear()
        try:
            sent = await context.bot.copy_message(int(replying_to), msg.chat_id, msg.message_id)
            update_stats("sent")
            data["msg_map"][str(msg.message_id)] = {"user_id": replying_to, "sent_id": sent.message_id}
            save_data()
            await msg.reply_text("✅ تم إرسال الرد!", reply_markup=back_btn())
        except Exception as e:
            await msg.reply_text(f"❌ فشل: {e}", reply_markup=back_btn())
        return

    # رسالة من مستخدم عادي
    if not is_owner(user.id) and not is_admin(user.id):
        uid = str(user.id)

        # ── تحقق إذا الرسالة من زر القائمة الدائمة ──
        menu_btns = data.get("menu_buttons", [])
        if msg.text and menu_btns:
            matched = next((b for b in menu_btns if b["text"] == msg.text), None)
            if matched:
                # الزر ضُغط — أرسله للأونر كرسالة عادية بدون معالجة إضافية
                pass  # يكمل التدفق الطبيعي ويُحوَّل للأونر

        # فحص الكتم - لو مكتوم نتجاهل الرسالة بصمت
        if uid in data.get("muted", []):
            return

        if uid in data["users"]:
            data["users"][uid]["msg_count"] = data["users"][uid].get("msg_count", 0) + 1
        update_stats("received")

        # ── رد المستخدم على رسالة محددة من البوت ──
        # لو المستخدم عمل Reply على رسالة من البوت، نحدد أي رسالة للأونر يتم الرد عليها
        reply_to_owner_msg_id = None
        if msg.reply_to_message:
            replied_bot_msg_id = msg.reply_to_message.message_id
            # بحث سريع بالـ key المباشر أولاً
            reverse_key = f"usr_{replied_bot_msg_id}_{uid}"
            reverse_info = data["msg_map"].get(reverse_key)
            if reverse_info and reverse_info.get("owner_msg_id"):
                reply_to_owner_msg_id = int(reverse_info["owner_msg_id"])
            else:
                # fallback: بحث في كامل الـ map
                for owner_mid, info in data["msg_map"].items():
                    if (str(info.get("user_id")) == uid
                            and info.get("sent_id") == replied_bot_msg_id
                            and not info.get("is_header")):
                        reply_to_owner_msg_id = int(owner_mid)
                        break

        if msg.text:
            smart = get_smart_reply(msg.text)
            if smart:
                await msg.reply_text(smart)

        try:
            user_name  = data["users"].get(uid, {}).get("name", "مجهول")
            username_s = data["users"].get(uid, {}).get("username", "")
            uname_tag  = f" @{username_s}" if username_s else ""
            is_reply_ctx = "↩️ رد على رسالتك" if reply_to_owner_msg_id else ""
            # ── زر بطاقة المستخدم تحت الرسالة مباشرة ──
            from keyboards import incoming_msg_btns
            btn_markup = incoming_msg_btns(int(uid))
            reply_label = f"↩️ رد على رسالتك" if is_reply_ctx else None

            # ── حذف رسالة التأكيد السابقة للمستخدم إن وجدت ──
            prev_conf_id = data["users"].get(uid, {}).get("last_confirmation_msg_id")
            if prev_conf_id:
                try:
                    await context.bot.delete_message(chat_id=msg.chat_id, message_id=int(prev_conf_id))
                except Exception:
                    pass
                data["users"][uid]["last_confirmation_msg_id"] = None

            # forward الرسالة كما هي بدون أي إضافة
            fwd = await msg.forward(OWNER_ID)

            if fwd is None:
                raise Exception("فشل إرسال الرسالة للمالك")

            # ── إرسال رسالة بجانب الـ forward للأونر مع أزرار التفاعل ──
            from keyboards import incoming_msg_btns
            reaction_btns = incoming_msg_btns(int(uid))
            reaction_msg = await context.bot.send_message(
                OWNER_ID,
                f"📩 رسالة من **{md_escape(user_name)}**{uname_tag} | `{uid}`",
                parse_mode="Markdown",
                reply_markup=reaction_btns,
                reply_to_message_id=fwd.message_id
            )

            data["msg_map"][str(fwd.message_id)] = {
                "user_id": uid,
                "user_msg_id": msg.message_id,
                "reaction_msg_id": reaction_msg.message_id
            }
            # ربط رسالة التفاعل بـ msg_map أيضاً
            data["msg_map"][str(reaction_msg.message_id)] = {
                "user_id": uid,
                "user_msg_id": msg.message_id,
                "is_reaction_msg": True
            }
            save_data()

            # ── إرسال رسالة تأكيد للمستخدم ──
            received_text = data["messages"].get("received", "✅ تم إرسال رسالتك بنجاح! انتظر الرد ❤️")
            conf_msg = await msg.reply_text(received_text)
            # حفظ id رسالة التأكيد لحذفها عند الرسالة القادمة
            data["users"][uid]["last_confirmation_msg_id"] = conf_msg.message_id
            save_data()

            # إرسال للمشرفين (forward بسيط)
            for admin_id, admin_info in data["admins"].items():
                if admin_info.get("can_reply"):
                    try:
                        await msg.forward(int(admin_id))
                    except:
                        pass

            if data["status"]["is_away"]:
                await asyncio.sleep(1)
                await msg.reply_text(data["messages"]["away"])

        except Exception as e:
            print(f"❌ خطأ في إرسال رسالة للمالك: {e}")
            # إشعار الأونر بالخطأ
            try:
                await context.bot.send_message(
                    OWNER_ID,
                    f"⚠️ فشل استقبال رسالة\n👤 {uid}\nالخطأ: `{str(e)[:100]}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass
        return

    # الرد بالريبلاي
    if msg.reply_to_message and (is_owner(user.id) or can_reply(user.id)):
        replied      = msg.reply_to_message
        target_id    = None
        target_msg_id = None

        map_info = data["msg_map"].get(str(replied.message_id))
        if map_info:
            target_id     = map_info.get("user_id")
            target_msg_id = map_info.get("user_msg_id")

        if not target_id:
            fwd_user = getattr(replied, 'forward_from', None)
            if fwd_user:
                target_id = str(fwd_user.id)
                # نحاول نجيب user_msg_id من msg_map
                for mid, info in list(data["msg_map"].items())[-200:]:
                    if str(info.get("user_id")) == target_id and info.get("user_msg_id"):
                        target_msg_id = info.get("user_msg_id")
                        break

        if not target_id:
            fwd_name = getattr(replied, 'forward_sender_name', None)
            if fwd_name:
                for mid, info in list(data["msg_map"].items())[-100:]:
                    uname = data["users"].get(info.get("user_id", ""), {}).get("name", "")
                    if uname == fwd_name:
                        target_id     = info.get("user_id")
                        target_msg_id = info.get("user_msg_id")
                        break

        if target_id:
            text = msg.text or ""

            if text.strip() == "مسح":
                try:
                    map_info = data["msg_map"].get(str(replied.message_id))
                    if map_info and map_info.get("sent_id"):
                        await context.bot.delete_message(int(target_id), map_info["sent_id"])
                    await msg.delete()
                    await replied.delete()
                    confirm = await context.bot.send_message(msg.chat_id, "🗑️ تم الحذف")
                    await asyncio.sleep(2)
                    await confirm.delete()
                except Exception as e:
                    await msg.reply_text(f"❌ فشل: {e}")
                return

            # ── تعديل الرسالة المرسلة ──
            if text.strip().startswith("ؤ "):
                new_text = text.strip()[2:].strip()
                if new_text:
                    map_info = data["msg_map"].get(str(replied.message_id))
                    sent_msg_id = map_info.get("sent_id") if map_info else None
                    edited = False
                    if sent_msg_id and target_id:
                        try:
                            await context.bot.edit_message_text(
                                chat_id=int(target_id),
                                message_id=int(sent_msg_id),
                                text=new_text
                            )
                            edited = True
                        except Exception as ex:
                            pass
                    if edited:
                        try:
                            await msg.delete()
                        except:
                            pass
                        confirm = await context.bot.send_message(
                            msg.chat_id,
                            f"✏️ **تم تعديل الرسالة** ✅\n━━━━━━━━━━━━━━━━━━━━━━━━\n📝 {new_text[:80]}{'...' if len(new_text) > 80 else ''}",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        await asyncio.sleep(3)
                        try:
                            await confirm.delete()
                        except:
                            pass
                    else:
                        await msg.reply_text(
                            "❌ **تعذّر التعديل**\n💡 الرسالة قديمة أو لم تُرسَل كنص",
                            parse_mode=ParseMode.MARKDOWN
                        )
                return

            # ── حظر المستخدم بالريبلاي ──
            if text.strip() == "حظر":
                uid = str(target_id)
                if uid not in data["banned"]:
                    data["banned"].append(uid)
                    save_data()
                user_name = data["users"].get(uid, {}).get("name", uid)
                confirm = await context.bot.send_message(
                    msg.chat_id,
                    f"🚫 **تم حظر المستخدم**\n━━━━━━━━━━━━━━━━━━━━━━━━\n👤 {md_escape(user_name)}\n🆔 `{uid}`",
                    parse_mode=ParseMode.MARKDOWN
                )
                try:
                    await msg.delete()
                except:
                    pass
                await asyncio.sleep(3)
                try:
                    await confirm.delete()
                except:
                    pass
                return

            # ── كتم المستخدم (تجاهل رسائله مؤقتاً) بالريبلاي ──
            if text.strip() == "كتم":
                uid = str(target_id)
                if "muted" not in data:
                    data["muted"] = []
                if uid not in data["muted"]:
                    data["muted"].append(uid)
                    save_data()
                    muted_status = "🔇 **تم كتم المستخدم**"
                else:
                    data["muted"].remove(uid)
                    save_data()
                    muted_status = "🔊 **تم إلغاء كتم المستخدم**"
                user_name = data["users"].get(uid, {}).get("name", uid)
                confirm = await context.bot.send_message(
                    msg.chat_id,
                    f"{muted_status}\n━━━━━━━━━━━━━━━━━━━━━━━━\n👤 {md_escape(user_name)}\n🆔 `{uid}`",
                    parse_mode=ParseMode.MARKDOWN
                )
                try:
                    await msg.delete()
                except:
                    pass
                await asyncio.sleep(3)
                try:
                    await confirm.delete()
                except:
                    pass
                return

            if text.strip().startswith("ص "):
                emoji_raw = text.strip()[2:].strip()
                if emoji_raw and target_msg_id:
                    try:
                        # ── تفاعل عادي فقط على رسالة المستخدم (بدون إيموجيات مدفوعة) ──
                        if emoji_raw.startswith("{") and emoji_raw.endswith("}"):
                            await msg.reply_text(
                                "⚠️ **التفاعلات المميزة المدفوعة غير مفعّلة**\n"
                                "💡 استخدم: `ص 🫡` أو أي إيموجي عادي",
                                parse_mode=ParseMode.MARKDOWN
                            )
                        else:
                            # ── إيموجي عادي → تفاعل على رسالة المستخدم ──
                            reaction = [ReactionTypeEmoji(emoji_raw)]
                            await context.bot.set_message_reaction(
                                chat_id=int(target_id),
                                message_id=int(target_msg_id),
                                reaction=reaction
                            )
                            await msg.delete()
                    except Exception as ex:
                        await msg.reply_text(f"❌ فشل: {ex}")
                elif emoji_raw and not target_msg_id:
                    await msg.reply_text("⚠️ لم أتمكن من تحديد رسالة المستخدم\n💡 تأكد أن البوت يحفظ user_msg_id في msg_map")
                return

            try:
                # ── الرد العادي → يُرسل مع reply_to_message_id ليظهر للمستخدم على أي رسالة ──
                reply_target = int(target_msg_id) if target_msg_id else None

                sent = await context.bot.copy_message(
                        int(target_id),
                        msg.chat_id,
                        msg.message_id,
                        reply_to_message_id=reply_target
                    )

                update_stats("sent")
                # نحفظ: رسالة الأونر (msg.message_id) → sent_id عند المستخدم
                # وأيضاً: sent_id عند المستخدم → owner_msg_id (عشان المستخدم يقدر يرد)
                data["msg_map"][str(msg.message_id)] = {"user_id": target_id, "sent_id": sent.message_id}
                # ربط عكسي: رسالة المرسلة للمستخدم → رسالة الأونر
                data["msg_map"]["usr_" + str(sent.message_id) + "_" + str(target_id)] = {
                    "owner_msg_id": msg.message_id,
                    "user_id": target_id
                }
                save_data()
            except Exception as e:
                await msg.reply_text(f"❌ فشل: {e}")
        else:
            await msg.reply_text("❌ لم أتمكن من تحديد المستخدم\n💡 استخدم زر ↩️ رد")
        return

    # الأوامر النصية
    if msg.text and is_owner(user.id):
        text = msg.text.strip()

        if text.startswith("حظر "):
            uid = text[4:].strip()
            if uid.isdigit() and uid not in data["banned"]:
                data["banned"].append(uid); save_data()
                await msg.reply_text(f"✅ تم حظر `{uid}`", parse_mode=ParseMode.MARKDOWN)
            return

        if text.startswith("فك "):
            uid = text[3:].strip()
            if uid in data["banned"]:
                data["banned"].remove(uid); save_data()
                await msg.reply_text(f"✅ تم فك حظر `{uid}`", parse_mode=ParseMode.MARKDOWN)
            return

        if text.startswith("vip "):
            uid = text[4:].strip()
            if uid.isdigit() and uid not in data["vip_users"]:
                data["vip_users"].append(uid); save_data()
                await msg.reply_text(f"⭐ تم إضافة `{uid}`", parse_mode=ParseMode.MARKDOWN)
            return

        if text.startswith("unvip "):
            uid = text[6:].strip()
            if uid in data["vip_users"]:
                data["vip_users"].remove(uid); save_data()
                await msg.reply_text(f"✅ تم إزالة `{uid}`", parse_mode=ParseMode.MARKDOWN)
            return

        if text.startswith("معلومات "):
            uid  = text[9:].strip()
            info = data["users"].get(uid, {})
            if info:
                await msg.reply_text(
                    f"👤 **{info.get('name')}**\n🆔 `{uid}`\n📊 {info.get('msg_count', 0)} رسالة",
                    parse_mode=ParseMode.MARKDOWN)
            return

        if text.startswith("أرسل ") or text.startswith("ارسل "):
            parts = text.split(" ", 2)
            if len(parts) >= 3 and parts[1].isdigit():
                try:
                    await context.bot.send_message(int(parts[1]), parts[2])
                    update_stats("sent")
                    await msg.reply_text("✅ تم!")
                except Exception as e:
                    await msg.reply_text(f"❌ {e}")
            return

        # ── إدارة حزم الإيموجيات المميزة ──
        # إضافة حزمة: "حزمة رابط"
        if text.startswith("حزمة ") and len(text.split()) >= 2:
            link = text.split(" ", 1)[1].strip()
            if not data.get("emoji_packs"):
                data["emoji_packs"] = []
            # فحص التكرار
            existing = [p["link"] for p in data["emoji_packs"]]
            if link in existing:
                pack_num = existing.index(link) + 1
                await msg.reply_text(
                    f"⚠️ الحزمة موجودة بالفعل برقم **{pack_num}**",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            # جلب الإيموجيات
            status = await msg.reply_text("⏳ جاري جلب الحزمة...")
            ids = await get_pack_sticker_ids(context.bot, link)
            if not ids:
                await status.edit_text(
                    "❌ **فشل جلب الحزمة**\n"
                    "💡 تأكد أن الرابط صحيح وأن الحزمة تحتوي على إيموجيات مميزة\n"
                    "📌 مثال: `https://t.me/addemoji/PackName`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            data["emoji_packs"].append({"link": link, "ids": ids})
            save_data()
            pack_num = len(data["emoji_packs"])
            await status.edit_text(
                f"✅ **تم إضافة الحزمة رقم {pack_num}**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 الرابط: `{link}`\n"
                f"🎭 عدد الإيموجيات: **{len(ids)}**\n\n"
                f"💡 **طريقة الاستخدام:**\n"
                f"• Reply + `ص {{1}}` → الإيموجي الأول من الحزمة 1\n"
                f"• Reply + `ص {{3|{pack_num}}}` → الإيموجي الثالث من الحزمة {pack_num}",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # ── استعراض: عرض كل إيموجيات الحزم مع أرقامها ──
        if text.strip() == "استعراض":
            packs = data.get("emoji_packs", [])

            # ── أولاً: التفاعلات العادية ──
            VALID_TELEGRAM_REACTIONS = [
                "👍","👎","❤","🔥","🥰","👏","😁","🤔","🤯","😱",
                "🤬","😢","🎉","🤩","🤮","💩","🙏","👌","🕊","🤡",
                "🥱","🥴","😍","🐳","❤‍🔥","🌚","🌭","💯","🤣","⚡",
                "🍌","🏆","💔","🤨","😐","🍓","🍾","💋","🖕","😈",
                "😴","😭","🤓","👻","👨‍💻","👀","🎃","🙈","😇","😨",
                "🤝","✍","🤗","🫡","🎅","🎄","☃","💅","🤪","🗿",
                "🆒","💘","🙉","🦄","😘","💊","🙊","😎","👾","🤷‍♂",
                "🤷","🤷‍♀","😡"
            ]
            lines = ["🎭 **استعراض الإيموجيات**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"]
            lines.append("**✅ التفاعلات العادية المدعومة:**\n")
            lines.append("💡 الاستخدام: `ص إيموجي` (Reply)\n\n")
            row = []
            for i, em in enumerate(VALID_TELEGRAM_REACTIONS, 1):
                row.append(f"`{i}.`{em}")
                if len(row) == 5:
                    lines.append("  ".join(row) + "\n")
                    row = []
            if row:
                lines.append("  ".join(row) + "\n")

            # ── ثانياً: حزم الإيموجيات المميزة ──
            if packs:
                lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━\n")
                lines.append("**📦 حزم الإيموجيات المميزة:**\n")
                lines.append("💡 الاستخدام: `ص {رقم_الإيموجي|رقم_الحزمة}` (Reply)\n")
                for pi, pack in enumerate(packs, 1):
                    count = len(pack.get("ids", []))
                    lines.append(f"\n**📦 حزمة {pi}** — `{pack['link']}`\n")
                    lines.append(f"🎭 تحتوي على **{count}** إيموجي\n")
                    lines.append(f"💡 مثال: `ص {{1|{pi}}}` إلى `ص {{{count}|{pi}}}`\n")
            else:
                lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━\n")
                lines.append("📦 **لا توجد حزم مميزة محفوظة**\n")
                lines.append("💡 أضف حزمة بـ: `حزمة https://t.me/addemoji/PackName`\n")

            lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━")
            await msg.reply_text("".join(lines), parse_mode=ParseMode.MARKDOWN)
            return

        # عرض الحزم: "حزم"
        if text.strip() == "حزم":
            packs = data.get("emoji_packs", [])
            if not packs:
                await msg.reply_text(
                    "📦 **لا توجد حزم محفوظة**\n\n"
                    "💡 لإضافة حزمة:\n`حزمة https://t.me/addemoji/PackName`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            lines = ["📦 **الحزم المحفوظة:**\n━━━━━━━━━━━━━━━━━━━━━━━━"]
            for i, p in enumerate(packs, 1):
                count = len(p.get("ids", []))
                lines.append(f"**{i}.** `{p['link']}`\n    🎭 {count} إيموجي")
            lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("💡 `حذف حزمة N` لحذف حزمة\n💡 `تحديث حزمة N` لإعادة جلبها")
            await msg.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
            return

        # حذف حزمة: "حذف حزمة N"
        if text.startswith("حذف حزمة "):
            num_str = text[9:].strip()
            if num_str.isdigit():
                num = int(num_str)
                packs = data.get("emoji_packs", [])
                if 1 <= num <= len(packs):
                    removed = packs.pop(num - 1)
                    save_data()
                    await msg.reply_text(
                        f"🗑️ تم حذف الحزمة رقم **{num}**\n`{removed['link']}`\n\n"
                        f"📦 الحزم المتبقية: **{len(packs)}**",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await msg.reply_text(f"❌ رقم غير صحيح. الحزم المتاحة: 1 - {len(packs)}")
            return

        # تحديث حزمة (إعادة جلب): "تحديث حزمة N"
        if text.startswith("تحديث حزمة "):
            num_str = text[11:].strip()
            if num_str.isdigit():
                num = int(num_str)
                packs = data.get("emoji_packs", [])
                if 1 <= num <= len(packs):
                    status = await msg.reply_text("⏳ جاري التحديث...")
                    ids = await get_pack_sticker_ids(context.bot, packs[num - 1]["link"])
                    if ids:
                        packs[num - 1]["ids"] = ids
                        save_data()
                        await status.edit_text(
                            f"✅ **تم تحديث الحزمة {num}**\n🎭 العدد: **{len(ids)}** إيموجي",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    else:
                        await status.edit_text("❌ فشل التحديث")
                else:
                    await msg.reply_text(f"❌ رقم غير صحيح")
            return

print("✅ تم تحميل handlers.py V4.2")
