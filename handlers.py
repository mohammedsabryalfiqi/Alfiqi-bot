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

import re as _re

def render_custom_emoji_message(text: str):
    """
    يحوّل نصاً يحتوي على {EMOJI_ID} إلى (نص_نظيف, قائمة_entities).
    
    مثال الاستخدام:
        مرحبا {5368324456789} كيف حالك {9876543210} ؟
    
    كل {ID} يتحوّل إلى:
      • حرف placeholder (نقطة ● غير مرئية) في النص
      • MessageEntity من نوع custom_emoji على موضع ذلك الحرف
    
    يُعيد (clean_text, entities) لاستخدامهما في:
        bot.send_message(text=clean_text, entities=entities)
    
    ملاحظة: لا يتوافق مع parse_mode — لا تمررهما معاً.
    """
    PLACEHOLDER = "\U0001F4A0"  # 💠 حرف مرئي بحجم إيموجي (1 UTF-16 codeunit)
    pattern = _re.compile(r'\{(\d{10,})\}')
    
    entities = []
    result = []
    offset = 0  # بالـ UTF-16 code units كما تتوقع تيليجرام
    
    last_end = 0
    for m in pattern.finditer(text):
        # الجزء قبل الـ token
        prefix = text[last_end:m.start()]
        # احسب UTF-16 length للـ prefix
        prefix_utf16_len = len(prefix.encode('utf-16-le')) // 2
        result.append(prefix)
        offset += prefix_utf16_len
        
        # أضف الـ placeholder
        result.append(PLACEHOLDER)
        placeholder_utf16_len = len(PLACEHOLDER.encode('utf-16-le')) // 2
        
        emoji_id = m.group(1)
        entities.append(
            MessageEntity(
                type=MessageEntityType.CUSTOM_EMOJI,
                offset=offset,
                length=placeholder_utf16_len,
                custom_emoji_id=emoji_id,
            )
        )
        offset += placeholder_utf16_len
        last_end = m.end()
    
    # الجزء المتبقي بعد آخر token
    result.append(text[last_end:])
    
    clean_text = "".join(result)
    return clean_text, entities if entities else None


async def send_with_custom_emoji(bot_or_msg, text: str, chat_id=None, **kwargs):
    """
    دالة مساعدة ترسل رسالة مع دعم {EMOJI_ID}.
    
    استخدام مع update.message:
        await send_with_custom_emoji(update.message, "مرحبا {5368324456789}")
    
    استخدام مع context.bot:
        await send_with_custom_emoji(context.bot, "مرحبا {5368324456789}", chat_id=uid)
    """
    from telegram import Message, Bot
    clean_text, entities = render_custom_emoji_message(text)
    
    # إزالة parse_mode لأنه لا يتوافق مع entities مخصصة
    kwargs.pop("parse_mode", None)
    
    if entities:
        kwargs["entities"] = entities
    
    if isinstance(bot_or_msg, Message):
        return await bot_or_msg.reply_text(clean_text, **kwargs)
    else:
        # bot object — يجب تمرير chat_id
        return await bot_or_msg.send_message(chat_id=chat_id, text=clean_text, **kwargs)


from keyboards import (
    persistent_kb, pbuttons_menu, pbtn_view_menu,
    back_btn, cancel_btn, main_menu,
    stats_menu, admins_menu, admin_perms_menu, select_user_menu,
    settings_menu, msg_settings_menu, away_menu,
    smart_replies_menu, view_sr_menu,
    quick_replies_menu, view_qr_menu,
    banned_menu, vip_menu, broadcast_menu,
    search_menu, search_results_menu, guide_menu,
    incoming_msg_btns, user_info_menu, confirm_menu,
    users_list_menu
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
        await send_with_custom_emoji(update.message, data["messages"]["banned"])
        return

    # المالك
    if is_owner(user.id):
        stats_data = data["stats"]
        away = "🔴 غائب" if data["status"]["is_away"] else "🟢 متاح"
        text = f"""👑 **لوحة تحكم المالك**
━━━━━━━━━━━━━━━━━━━━━━━━
مرحباً يا **{user.first_name}** 👋

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
            f"👨‍💼 **مرحباً أيها المشرف {user.first_name}**\n\nيمكنك الرد على الرسائل المحولة",
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
        ).replace("{name}", user.first_name or "عزيزي")

    if previously_blocked:
        welcome = data["messages"].get(
            "returned_after_block",
            "عوداً حميداً 😊\n\nسعيدون بعودتك! أرسل رسالتك وسيتم الرد عليك ❤️"
        ).replace("{name}", user.first_name or "عزيزي")
        await send_with_custom_emoji(update.message, welcome)
        if data["status"]["is_away"]:
            await asyncio.sleep(1)
            await send_with_custom_emoji(update.message, data["messages"]["away"])
        return

    # مستخدم عادي
    welcome = data["messages"]["welcome"].replace("{name}", user.first_name or "عزيزي")
    if is_vip(user.id):
        welcome = f"⭐ **مرحباً VIP** ⭐\n\n{welcome}"

    # واجهة الترحيب — صورة أو ملصق مع زر
    welcome_media = data.get("welcome_media", {})
    media_file_id = welcome_media.get("file_id")
    media_type    = welcome_media.get("type")  # "photo" أو "sticker"

    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    view_btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("📩 أرسل رسالتك", callback_data="start_chat")
    ]])

    clean_welcome, welcome_entities = render_custom_emoji_message(welcome)
    if media_file_id and media_type == "photo":
        if welcome_entities:
            await update.message.reply_photo(
                photo=media_file_id,
                caption=clean_welcome,
                caption_entities=welcome_entities,
                reply_markup=view_btn
            )
        else:
            await update.message.reply_photo(
                photo=media_file_id,
                caption=welcome,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=view_btn
            )
    elif media_file_id and media_type == "sticker":
        await update.message.reply_sticker(sticker=media_file_id)
        await send_with_custom_emoji(update.message, welcome, reply_markup=view_btn)
    else:
        await send_with_custom_emoji(update.message, welcome, reply_markup=view_btn)

    # 🟢 الأزرار الدائمة للمستخدم
    try:
        kb = persistent_kb()
        if data.get("persistent_buttons"):
            await update.message.reply_text("⬇️ القائمة:", reply_markup=kb)
    except Exception as _e:
        print(f"persistent_kb error: {_e}")

    # رسالة الغياب
    if data["status"]["is_away"]:
        await asyncio.sleep(1)
        await send_with_custom_emoji(update.message, data["messages"]["away"])


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


    # ══════════════════════════════════════════════════════════
    #              🟢 الأزرار الدائمة (Persistent)
    # ══════════════════════════════════════════════════════════
    if cb == "pbuttons":
        if not is_owner(user.id): return
        count = len(data.get("persistent_buttons", []))
        await query.edit_message_text(
            f"🟢 **الأزرار الدائمة**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 العدد الحالي: **{count}**\n\n"
            f"الأزرار تظهر للمستخدم دائماً تحت حقل الكتابة.\n"
            f"💡 زر نص: يرد على المستخدم بنص جاهز\n"
            f"💡 زر رابط: يفتح صفحة ويب داخل تيليجرام",
            reply_markup=pbuttons_menu(), parse_mode=ParseMode.MARKDOWN,
        )
        return

    if cb == "pbtn_add_text":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "pbtn_text_label"
        await query.edit_message_text(
            "📝 **إضافة زر نص**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل **اسم الزر** (اللي هيظهر للمستخدم):",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN,
        )
        return

    if cb == "pbtn_add_url":
        if not is_owner(user.id): return
        context.user_data["waiting"] = "pbtn_url_label"
        await query.edit_message_text(
            "🔗 **إضافة زر رابط**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل **اسم الزر**:",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN,
        )
        return

    if cb.startswith("pbtn_view_"):
        if not is_owner(user.id): return
        idx = int(cb.split("_")[-1])
        pbtns = data.get("persistent_buttons", [])
        if 0 <= idx < len(pbtns):
            b = pbtns[idx]
            kind = "🔗 رابط" if b.get("type") == "url" else "💬 نص"
            await query.edit_message_text(
                f"🟢 **زر دائم**\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📛 الاسم: **{b.get('label','')}**\n"
                f"🏷️ النوع: {kind}\n"
                f"📝 القيمة:\n`{b.get('value','')[:200]}`",
                reply_markup=pbtn_view_menu(idx), parse_mode=ParseMode.MARKDOWN,
            )
        return

    if cb.startswith("pbtn_del_"):
        if not is_owner(user.id): return
        idx = int(cb.split("_")[-1])
        pbtns = data.get("persistent_buttons", [])
        if 0 <= idx < len(pbtns):
            pbtns.pop(idx)
            save_data()
            await query.answer("✅ تم الحذف", show_alert=True)
        await query.edit_message_text(
            f"🟢 **الأزرار الدائمة**\n📊 العدد: **{len(data.get('persistent_buttons', []))}**",
            reply_markup=pbuttons_menu(), parse_mode=ParseMode.MARKDOWN,
        )
        return

    if cb == "pbtn_clear_all":
        if not is_owner(user.id): return
        data["persistent_buttons"] = []
        save_data()
        await query.answer("✅ تم حذف الكل", show_alert=True)
        await query.edit_message_text(
            "🟢 **الأزرار الدائمة**\n📭 لا توجد أزرار",
            reply_markup=pbuttons_menu(), parse_mode=ParseMode.MARKDOWN,
        )
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
        kb = persistent_kb()
        if data.get("persistent_buttons"):
            await query.message.reply_text("📩 أرسل رسالتك الآن وسيتم الرد عليك قريباً ", reply_markup=kb)
        else:
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
                clean_content, content_entities = render_custom_emoji_message(content)
                await context.bot.send_message(
                    int(uid), clean_content,
                    entities=content_entities if content_entities else None
                )
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
        text = ("😀 **التفاعلات والإيموجيات المميزة**\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "**تفاعل عادي على رسالة المستخدم:**\n"
                "Reply + `ص 😂` → يضع تفاعل إيموجي عادي\n"
                "Reply + `ص 🫡` → تفاعل عسكري\n\n"
                "**⭐️ تفاعل بريميوم مميز:**\n"
                "Reply + `ص {N}` → الإيموجي N من الحزمة 1\n"
                "Reply + `ص {N|P}` → الإيموجي N من الحزمة P\n\n"
                "**⭐️ إيموجي مميز داخل الرسائل:**\n"
                "ضع `{ID_الإيموجي}` في أي رسالة تكتبها:\n"
                "مثال: `مرحبا {5368324456789} كيف حالك؟`\n"
                "يعمل في: رسالة الترحيب، الغياب، الاستلام،\n"
                "الردود الذكية، الردود الجاهزة، الأزرار الدائمة\n\n"
                "**كيف أحصل على ID الإيموجي؟**\n"
                "• افتح @stickers وابحث عن الإيموجي\n"
                "• أو أرسله للبوت @fStikBot\n\n"
                "**إدارة الحزم (للتفاعلات):**\n"
                "• `حزمة رابط` → إضافة حزمة\n"
                "• `استعراض` → عرض كل الإيموجيات بأرقامها\n"
                "• `حذف حزمة N` → حذف")
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


    if waiting == "pbtn_text_label" and msg.text:
        context.user_data["pbtn_label"] = msg.text.strip()[:30]
        context.user_data["waiting"] = "pbtn_text_value"
        await msg.reply_text(
            f"✅ الاسم: **{msg.text.strip()[:30]}**\n\n📝 الآن أرسل **النص** اللي هيرد على المستخدم:",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN,
        )
        return

    if waiting == "pbtn_text_value" and msg.text:
        label = context.user_data.get("pbtn_label", "زر")
        data.setdefault("persistent_buttons", []).append({
            "label": label, "type": "text", "value": msg.text,
        })
        save_data(); context.user_data.clear()
        await msg.reply_text(
            f"✅ تم إضافة الزر **{label}**\n\nاطلب من المستخدم /start علشان يظهر له.",
            reply_markup=back_btn("pbuttons"), parse_mode=ParseMode.MARKDOWN,
        )
        return

    if waiting == "pbtn_url_label" and msg.text:
        context.user_data["pbtn_label"] = msg.text.strip()[:30]
        context.user_data["waiting"] = "pbtn_url_value"
        await msg.reply_text(
            f"✅ الاسم: **{msg.text.strip()[:30]}**\n\n🔗 الآن أرسل **الرابط** (لازم يبدأ بـ https://):",
            reply_markup=cancel_btn(), parse_mode=ParseMode.MARKDOWN,
        )
        return

    if waiting == "pbtn_url_value" and msg.text:
        url = msg.text.strip()
        if not url.startswith("https://"):
            await msg.reply_text("❌ الرابط لازم يبدأ بـ https://", reply_markup=cancel_btn())
            return
        label = context.user_data.get("pbtn_label", "زر")
        data.setdefault("persistent_buttons", []).append({
            "label": label, "type": "url", "value": url,
        })
        save_data(); context.user_data.clear()
        await msg.reply_text(
            f"✅ تم إضافة زر الرابط **{label}**",
            reply_markup=back_btn("pbuttons"), parse_mode=ParseMode.MARKDOWN,
        )
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

        # فحص الكتم - لو مكتوم نتجاهل الرسالة بصمت
        if uid in data.get("muted", []):
            return

        # 🟢 اعتراض الأزرار الدائمة — لو النص بيطابق label لزر
        if msg.text:
            for pb in data.get("persistent_buttons", []):
                if msg.text.strip() == pb.get("label", "").strip():
                    val = pb.get("value", "")
                    if pb.get("type") == "url":
                        from telegram import InlineKeyboardButton as _IKB, InlineKeyboardMarkup as _IKM
                        await msg.reply_text(
                            pb.get("label", "🔗 رابط"),
                            reply_markup=_IKM([[_IKB("🔗 فتح الرابط", url=val)]])
                        )
                    else:
                        await send_with_custom_emoji(msg, val or pb.get("label", ""))
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
                await send_with_custom_emoji(msg, smart)

        try:
            user_name  = data["users"].get(uid, {}).get("name", "مجهول")
            username_s = data["users"].get(uid, {}).get("username", "")
            uname_tag  = f" @{username_s}" if username_s else ""
            is_reply_ctx = "↩️ رد على رسالتك" if reply_to_owner_msg_id else ""
            # ── زر بطاقة المستخدم تحت الرسالة مباشرة ──
            from keyboards import incoming_msg_btns
            btn_markup = incoming_msg_btns(int(uid))
            reply_label = f"↩️ رد على رسالتك" if is_reply_ctx else None

            # forward الرسالة كما هي بدون أي إضافة
            fwd = await msg.forward(OWNER_ID)

            if fwd is None:
                raise Exception("فشل إرسال الرسالة للمالك")

            data["msg_map"][str(fwd.message_id)] = {
                "user_id": uid,
                "user_msg_id": msg.message_id
            }
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
                await send_with_custom_emoji(msg, data["messages"]["away"])
            else:
                # ✅ رسالة "تم استقبال رسالتكم" — احذف القديمة وأرسل جديدة كرد على آخر رسالة
                try:
                    old_rcv_id = data.get("received_msgs", {}).get(uid)
                    if old_rcv_id:
                        try:
                            await context.bot.delete_message(chat_id=int(uid), message_id=int(old_rcv_id))
                        except Exception:
                            pass
                    rcv_text = data["messages"].get("received", "✅ تم استقبال رسالتكم")
                    clean_rcv, rcv_entities = render_custom_emoji_message(rcv_text)
                    sent_rcv = await msg.reply_text(
                        clean_rcv,
                        entities=rcv_entities if rcv_entities else None,
                        reply_to_message_id=msg.message_id,
                    )
                    data.setdefault("received_msgs", {})[uid] = sent_rcv.message_id
                    save_data()
                except Exception as _e:
                    print(f"received_msg error: {_e}")

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
                    f"🚫 **تم حظر المستخدم**\n━━━━━━━━━━━━━━━━━━━━━━━━\n👤 {user_name}\n🆔 `{uid}`",
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
                    f"{muted_status}\n━━━━━━━━━━━━━━━━━━━━━━━━\n👤 {user_name}\n🆔 `{uid}`",
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
                        # ── إيموجي مميز بريميوم {N} أو {N|P} → custom_emoji_id ──
                        if emoji_raw.startswith("{") and emoji_raw.endswith("}"):
                            emoji_item = await resolve_custom_emoji(context.bot, emoji_raw)
                            if emoji_item is None:
                                await msg.reply_text(
                                    "⚠️ **لم يُعثر على الإيموجي**\n"
                                    "💡 تأكد أنك أضفت الحزمة أولاً بـ: `حزمة رابط_الحزمة`\n"
                                    "📌 ثم استخدم: `ص {1}` أو `ص {1|2}`",
                                    parse_mode=ParseMode.MARKDOWN
                                )
                            else:
                                reaction = [ReactionTypeCustomEmoji(emoji_item["id"])]
                                await context.bot.set_message_reaction(
                                    chat_id=int(target_id),
                                    message_id=int(target_msg_id),
                                    reaction=reaction,
                                    is_big=False
                                )
                                await msg.delete()
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


# ═══════════════════════════════════════════════════════════════
#         💝 معالج تفاعلات المستخدم على رسائل البوت/المالك
# ═══════════════════════════════════════════════════════════════

async def reaction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يظهر للمالك أي تفاعل (عادي أو Premium custom emoji) من المستخدم."""
    mr = update.message_reaction
    if not mr:
        return
    user = mr.user
    if not user or is_owner(user.id):
        return

    uid = str(user.id)
    reacted_msg_id = mr.message_id  # message_id داخل محادثة المستخدم

    # حوّل التفاعلات الجديدة إلى نص قابل للعرض
    new_list = []
    for r in mr.new_reaction or []:
        if isinstance(r, ReactionTypeEmoji):
            new_list.append(r.emoji)
        elif isinstance(r, ReactionTypeCustomEmoji):
            new_list.append(f"⭐[premium:{r.custom_emoji_id}]")
    old_list = []
    for r in mr.old_reaction or []:
        if isinstance(r, ReactionTypeEmoji):
            old_list.append(r.emoji)
        elif isinstance(r, ReactionTypeCustomEmoji):
            old_list.append(f"⭐[premium:{r.custom_emoji_id}]")

    # حدد رسالة المالك الأصلية (في محادثته) المرتبطة بـ reacted_msg_id
    owner_orig_msg_id = None
    for owner_mid, info in data.get("msg_map", {}).items():
        try:
            if str(info.get("user_id")) == uid and int(info.get("sent_id", 0)) == int(reacted_msg_id):
                owner_orig_msg_id = int(owner_mid)
                break
        except Exception:
            continue

    user_name = data["users"].get(uid, {}).get("name", "مستخدم")
    if new_list:
        action = "💝 تفاعل"
        emojis_txt = " ".join(new_list)
    elif old_list:
        action = "🗑️ ألغى تفاعله"
        emojis_txt = " ".join(old_list)
    else:
        return

    text = (
        f"{action} **{user_name}**  ↩️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 `{uid}`\n"
        f"💬 الرسالة في محادثته: `{reacted_msg_id}`\n"
        f"🎭 التفاعل: {emojis_txt}"
    )

    try:
        if owner_orig_msg_id:
            await context.bot.send_message(
                OWNER_ID, text,
                reply_to_message_id=owner_orig_msg_id,
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await context.bot.send_message(OWNER_ID, text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"reaction_handler error: {e}")
