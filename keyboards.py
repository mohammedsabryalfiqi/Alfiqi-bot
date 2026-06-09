# keyboards.py
# 🎛️ ملف الأزرار والقوائم - V5.0 (زر بطاقة المستخدم)

import re as _re
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo,
    ReplyKeyboardRemove, MessageEntity,
)
from telegram.constants import MessageEntityType
from utils import data


# ═══════════════════════════════════════════════════════════════
#    🎨 دالة مساعدة: تحويل {EMOJI_ID} في label الزر
# ═══════════════════════════════════════════════════════════════

_EMOJI_PLACEHOLDER = "\U0001F4A0"   # 💠  placeholder مرئي بحجم إيموجي
_EMOJI_PATTERN     = _re.compile(r'\{(\d{10,})\}')

def resolve_button_label(label: str):
    """
    يحوّل label يحتوي على {EMOJI_ID} إلى (clean_label, entities_or_None).
    مثال: "مرحبا {5368324456789}" → ("مرحبا 💠", [MessageEntity(...)])
    إذا لم يوجد ID يعيد (label_as_is, None).
    """
    entities, result, offset, last_end = [], [], 0, 0
    for m in _EMOJI_PATTERN.finditer(label):
        prefix = label[last_end:m.start()]
        prefix_u16 = len(prefix.encode('utf-16-le')) // 2
        result.append(prefix)
        offset += prefix_u16
        result.append(_EMOJI_PLACEHOLDER)
        ph_u16 = len(_EMOJI_PLACEHOLDER.encode('utf-16-le')) // 2
        entities.append(MessageEntity(
            type=MessageEntityType.CUSTOM_EMOJI,
            offset=offset,
            length=ph_u16,
            custom_emoji_id=m.group(1),
        ))
        offset += ph_u16
        last_end = m.end()
    result.append(label[last_end:])
    clean = "".join(result)
    return clean, (entities if entities else None)

def btn(text, callback_data, style=None):
    if style:
        return InlineKeyboardButton(text, callback_data=callback_data, style=style)
    return InlineKeyboardButton(text, callback_data=callback_data)

# ═══════════════════════════════════════════════════════════════
#                      🔙 أزرار التنقل
# ═══════════════════════════════════════════════════════════════

def back_btn(to="main"):
    return InlineKeyboardMarkup([
        [btn("🔙 رجوع", to, "primary")]
    ])

def cancel_btn():
    return InlineKeyboardMarkup([
        [btn("❌ إلغاء", "cancel", "danger")]
    ])

# ═══════════════════════════════════════════════════════════════
#                      👑 القائمة الرئيسية
# ═══════════════════════════════════════════════════════════════

def main_menu():
    return InlineKeyboardMarkup([
        [
            btn("📊 الإحصائيات", "stats",    "primary"),
            btn("👥 المشرفين",   "admins",   "primary"),
        ],
        [
            btn("⚙️ الإعدادات",  "settings", "primary"),
            btn("📢 إذاعة",      "broadcast","primary"),
        ],
        [
            btn("🤖 الردود الذكية", "smart_replies", "primary"),
            btn("💬 ردود جاهزة",   "quick_replies", "primary"),
        ],
        [
            btn("🚫 المحظورين",  "banned_list", "danger"),
            btn("⭐ VIP",        "vip_list",    "primary"),
        ],
        [
            btn("🔍 بحث",   "search", "primary"),
            btn("📖 الدليل", "guide",  "primary"),
        ],
        [
            btn("👥 مستخدمين البوت", "users_list", "primary"),
        ],
        [
            btn("🟢 الأزرار الدائمة", "pbuttons", "primary"),
        ],
    ])

# ═══════════════════════════════════════════════════════════════
#                      📊 الإحصائيات
# ═══════════════════════════════════════════════════════════════

def stats_menu():
    return InlineKeyboardMarkup([
        [btn("🏆 أنشط المستخدمين", "top_users", "primary")],
        [btn("🔄 تحديث",            "stats",     "primary")],
        [btn("🔙 رجوع",             "main",      "primary")],
    ])

# ═══════════════════════════════════════════════════════════════
#                      👥 المشرفين
# ═══════════════════════════════════════════════════════════════

def admins_menu():
    btns = []
    for uid, info in data["admins"].items():
        name = info.get("name", "مشرف")[:20]
        btns.append([btn(f"🟢 {name}", f"admin_{uid}", "primary")])
    if not btns:
        btns.append([btn("📭 لا يوجد مشرفين", "none")])
    btns.append([btn("➕ إضافة مشرف", "add_admin", "primary")])
    btns.append([btn("🔙 رجوع",        "main",      "primary")])
    return InlineKeyboardMarkup(btns)

def admin_perms_menu(admin_id):
    perms = data["admins"].get(admin_id, {})
    can_reply     = "✅" if perms.get("can_reply",     False) else "❌"
    can_broadcast = "✅" if perms.get("can_broadcast", False) else "❌"
    can_ban       = "✅" if perms.get("can_ban",       False) else "❌"
    return InlineKeyboardMarkup([
        [btn(f"{can_reply} الرد على الرسائل",  f"perm_reply_{admin_id}",     "primary")],
        [btn(f"{can_broadcast} إرسال إذاعة",   f"perm_broadcast_{admin_id}", "primary")],
        [btn(f"{can_ban} حظر المستخدمين",       f"perm_ban_{admin_id}",       "primary")],
        [btn("🗑️ إزالة المشرف", f"remove_admin_{admin_id}", "danger")],
        [btn("🔙 رجوع",          "admins",                  "primary")],
    ])

def select_user_menu():
    btns = []
    users = list(data["users"].items())[-15:]
    for uid, info in users:
        if uid not in data["admins"]:
            name = info.get("name", "مجهول")[:20]
            btns.append([btn(f"👤 {name}", f"make_admin_{uid}", "primary")])
    if not btns:
        btns.append([btn("📭 لا يوجد مستخدمين", "none")])
    btns.append([btn("📝 إدخال آيدي", "admin_by_id", "primary")])
    btns.append([btn("🔙 رجوع",       "admins",      "primary")])
    return InlineKeyboardMarkup(btns)

# ═══════════════════════════════════════════════════════════════
#                      ⚙️ الإعدادات
# ═══════════════════════════════════════════════════════════════

def settings_menu():
    away_icon  = "🟢" if data["status"]["is_away"]             else "🔴"
    smart_icon = "🟢" if data["status"]["smart_reply_enabled"] else "🔴"
    return InlineKeyboardMarkup([
        [btn("📝 رسائل البوت",             "msg_settings",  "primary")],
        [btn(f"{away_icon} وضع الغياب",    "away_settings", "primary")],
        [btn(f"{smart_icon} الردود الذكية","toggle_smart",  "primary")],
        [btn("🔙 رجوع", "main",            "primary")],
    ])

def msg_settings_menu():
    return InlineKeyboardMarkup([
        [btn("👋 رسالة الترحيب", "edit_welcome", "primary")],
        [
            btn("🖼 صورة الواجهة", "set_welcome_media", "primary"),
            btn("🗑 حذف الصورة",   "clear_welcome_media", "danger"),
        ],
        [btn("⏰ رسالة الغياب",      "edit_away",           "primary")],
        [btn("✅ رسالة الاستلام",    "edit_received",       "primary")],
        [btn("🔓 رسالة العودة بعد الحظر", "edit_returned_block", "primary")],
        [btn("🔙 رجوع",              "settings",            "primary")],
    ])

def away_menu():
    is_away      = data["status"]["is_away"]
    toggle_text  = "🔴 تعطيل الغياب" if is_away else "🟢 تفعيل الغياب"
    toggle_style = "danger" if is_away else "primary"
    return InlineKeyboardMarkup([
        [btn(toggle_text,         "toggle_away", toggle_style)],
        [btn("✏️ تعديل الرسالة", "edit_away",   "primary")],
        [btn("🔙 رجوع",           "settings",    "primary")],
    ])

# ═══════════════════════════════════════════════════════════════
#                      🤖 الردود الذكية
# ═══════════════════════════════════════════════════════════════

def smart_replies_menu():
    btns = []
    replies = list(data["smart_replies"].items())[:10]
    for trigger, _ in replies:
        short = trigger[:20] + "..." if len(trigger) > 20 else trigger
        btns.append([btn(f"💬 {short}", f"view_sr_{trigger[:30]}", "primary")])
    if not btns:
        btns.append([btn("📭 لا يوجد ردود", "none")])
    btns.append([btn("➕ إضافة رد",    "add_sr",      "primary")])
    btns.append([btn("📋 إضافة قائمة", "add_sr_bulk", "primary")])
    if data["smart_replies"]:
        btns.append([btn("🗑️ حذف الكل", "delete_all_sr", "danger")])
    btns.append([btn("🔙 رجوع", "main", "primary")])
    return InlineKeyboardMarkup(btns)

def view_sr_menu(trigger):
    return InlineKeyboardMarkup([
        [btn("🗑️ حذف", f"del_sr_{trigger[:30]}", "danger")],
        [btn("🔙 رجوع", "smart_replies",          "primary")],
    ])

# ═══════════════════════════════════════════════════════════════
#                      💬 الردود الجاهزة
# ═══════════════════════════════════════════════════════════════

def quick_replies_menu():
    btns = []
    for title in data["quick_replies"].keys():
        btns.append([btn(f"💬 {title}", f"view_qr_{title}", "primary")])
    if not btns:
        btns.append([btn("📭 لا يوجد ردود", "none")])
    btns.append([btn("➕ إضافة رد", "add_qr", "primary")])
    btns.append([btn("🔙 رجوع",     "main",   "primary")])
    return InlineKeyboardMarkup(btns)

def view_qr_menu(title):
    return InlineKeyboardMarkup([
        [btn("🗑️ حذف", f"del_qr_{title}", "danger")],
        [btn("🔙 رجوع", "quick_replies",   "primary")],
    ])

# ═══════════════════════════════════════════════════════════════
#                      👥 مستخدمين البوت
# ═══════════════════════════════════════════════════════════════

def users_list_menu(page=0, page_size=8):
    users = list(data["users"].items())
    total = len(users)
    start = page * page_size
    end   = min(start + page_size, total)
    rows  = []
    for uid, info in users[start:end]:
        name   = info.get("name", "مجهول")[:18]
        badge  = " ⭐" if uid in data["vip_users"] else (" 🚫" if uid in data["banned"] else "")
        rows.append([btn(f"👤 {name}{badge}", f"user_{uid}", "primary")])
    # أزرار التنقل
    nav = []
    if page > 0:
        nav.append(btn("◀️ السابق", f"users_page_{page-1}", "primary"))
    nav.append(btn(f"{start+1}-{end} / {total}", "none", "primary"))
    if end < total:
        nav.append(btn("التالي ▶️", f"users_page_{page+1}", "primary"))
    if nav:
        rows.append(nav)
    rows.append([btn("🔙 رجوع", "back_main", "primary")])
    return InlineKeyboardMarkup(rows)

# ═══════════════════════════════════════════════════════════════
#                      🚫 المحظورين
# ═══════════════════════════════════════════════════════════════

def banned_menu():
    btns = []
    for uid in data["banned"][:15]:
        name = data["users"].get(uid, {}).get("name", uid)[:20]
        btns.append([btn(f"🚷 {name}", f"unban_{uid}", "primary")])
    if not btns:
        btns.append([btn("📭 لا يوجد محظورين", "none")])
    btns.append([btn("➕ حظر بالآيدي", "ban_by_id", "danger")])
    btns.append([btn("🔙 رجوع",        "main",      "primary")])
    return InlineKeyboardMarkup(btns)

# ═══════════════════════════════════════════════════════════════
#                      ⭐ VIP
# ═══════════════════════════════════════════════════════════════

def vip_menu():
    btns = []
    for uid in data["vip_users"][:15]:
        name = data["users"].get(uid, {}).get("name", uid)[:20]
        btns.append([btn(f"⭐ {name}", f"unvip_{uid}", "primary")])
    if not btns:
        btns.append([btn("📭 لا يوجد VIP", "none")])
    btns.append([btn("➕ إضافة VIP", "add_vip", "primary")])
    btns.append([btn("🔙 رجوع",      "main",    "primary")])
    return InlineKeyboardMarkup(btns)

# ═══════════════════════════════════════════════════════════════
#                      📢 الإذاعة
# ═══════════════════════════════════════════════════════════════

def broadcast_menu():
    total = len(data["users"])
    vip   = len(data["vip_users"])
    return InlineKeyboardMarkup([
        [btn(f"📢 إذاعة للكل ({total})", "bc_all",  "primary")],
        [btn(f"⭐ إذاعة VIP ({vip})",    "bc_vip",  "primary")],
        [btn("👤 إرسال لمستخدم",          "bc_user", "primary")],
        [btn("🔙 رجوع",                    "main",    "primary")],
    ])

# ═══════════════════════════════════════════════════════════════
#                      🔍 البحث
# ═══════════════════════════════════════════════════════════════

def search_menu():
    return InlineKeyboardMarkup([
        [btn("🔍 بحث بالاسم",  "search_name", "primary")],
        [btn("🆔 بحث بالآيدي", "search_id",   "primary")],
        [btn("🔙 رجوع",         "main",        "primary")],
    ])

def search_results_menu(results):
    btns = []
    for uid, info in results[:10]:
        name   = info.get("name", "مجهول")[:20]
        vip    = "⭐" if uid in data["vip_users"] else ""
        banned = "🚫" if uid in data["banned"]    else ""
        btns.append([btn(f"{vip}{banned} {name}", f"user_{uid}", "primary")])
    if not btns:
        btns.append([btn("❌ لا توجد نتائج", "none")])
    btns.append([btn("🔙 رجوع", "search", "primary")])
    return InlineKeyboardMarkup(btns)

# ═══════════════════════════════════════════════════════════════
#                      📖 الدليل
# ═══════════════════════════════════════════════════════════════

def guide_menu():
    return InlineKeyboardMarkup([
        [btn("📩 الرد على الرسائل", "guide_reply",     "primary")],
        [btn("🤖 الردود الذكية",    "guide_smart",     "primary")],
        [btn("😀 التفاعلات",         "guide_reactions", "primary")],
        [btn("🗑️ حذف الرسائل",      "guide_delete",    "primary")],
        [btn("📋 الأوامر",            "guide_commands",  "primary")],
        [btn("🔙 رجوع",               "main",            "primary")],
    ])

# ═══════════════════════════════════════════════════════════════
#               💬 أزرار الرسائل الواردة
# ═══════════════════════════════════════════════════════════════

def incoming_msg_btns(user_id):
    uid            = str(user_id)
    is_user_vip    = uid in data["vip_users"]
    is_user_banned = uid in data["banned"]
    user_name      = data["users"].get(uid, {}).get("name", "مجهول")

    # زر البطاقة التعريفية باسم المستخدم
    badge = " ⭐" if is_user_vip else (" 🚫" if is_user_banned else "")
    row0 = [btn(f"👤 {user_name}{badge}", f"user_{user_id}", "primary")]

    row1 = [
        btn("↩️ رد", f"reply_{user_id}", "primary"),
        btn(
            "✅ فك حظر" if is_user_banned else "🚫 حظر",
            f"unban_{user_id}" if is_user_banned else f"ban_{user_id}",
            "primary" if is_user_banned else "danger",
        ),
    ]
    rows = [row0, row1]

    quick_btns = []
    for title in list(data["quick_replies"].keys())[:3]:
        quick_btns.append(btn(f"💬 {title[:8]}", f"sendqr_{user_id}_{title}", "primary"))
    if quick_btns:
        rows.append(quick_btns)

    return InlineKeyboardMarkup(rows)

# ═══════════════════════════════════════════════════════════════
#                      👤 معلومات المستخدم
# ═══════════════════════════════════════════════════════════════

def user_info_menu(user_id):
    uid            = str(user_id)
    is_user_vip    = uid in data["vip_users"]
    is_user_banned = uid in data["banned"]
    return InlineKeyboardMarkup([
        [
            btn("↩️ رد",   f"reply_{user_id}",  "primary"),
            btn("📤 إرسال", f"sendto_{user_id}", "primary"),
        ],
        [
            btn(
                "❌ VIP" if is_user_vip else "⭐ VIP",
                f"unvip_{user_id}" if is_user_vip else f"addvip_{user_id}",
                "danger" if is_user_vip else "primary",
            ),
            btn(
                "✅ فك" if is_user_banned else "🚫 حظر",
                f"unban_{user_id}" if is_user_banned else f"ban_{user_id}",
                "primary" if is_user_banned else "danger",
            ),
        ],
        [btn("📝 ملاحظة", f"note_{user_id}", "primary")],
        [btn("🔙 رجوع",   "main",            "primary")],
    ])

# ═══════════════════════════════════════════════════════════════
#                      ✅ تأكيد
# ═══════════════════════════════════════════════════════════════

def confirm_menu(action, cancel_to="main"):
    return InlineKeyboardMarkup([
        [
            btn("✅ تأكيد", f"confirm_{action}", "primary"),
            btn("❌ إلغاء", cancel_to,            "danger"),
        ]
    ])

print("✅ تم تحميل keyboards.py V5.0")


# ═══════════════════════════════════════════════════════════════
#    🟢 الأزرار الدائمة — InlineKeyboard ملصق برسالة الترحيب
# ═══════════════════════════════════════════════════════════════

def persistent_kb():
    """
    InlineKeyboard ملصق برسالة الترحيب مباشرةً (مثل الصورة المرجعية).
    - أزرار النص  → callback_data="pbtn_text_{i}" بستايل primary (أخضر)
    - أزرار الرابط → url= مباشرةً (يفتح المتصفح)
    - يدعم {EMOJI_ID} في الـ label

    يعيد None إذا لا توجد أزرار.
    """
    buttons = data.get("persistent_buttons", [])
    if not buttons:
        return None

    rows = []
    row  = []
    for i, b in enumerate(buttons):
        raw_label   = b.get("label", "زر")
        clean_label, _ = resolve_button_label(raw_label)   # {ID} → placeholder

        if b.get("type") == "url":
            val = b.get("value", "")
            row.append(InlineKeyboardButton(clean_label, url=val))
        else:
            row.append(InlineKeyboardButton(
                clean_label,
                callback_data=f"pbtn_text_{i}",
            ))

        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)

    return InlineKeyboardMarkup(rows)


def pbuttons_menu():
    btns = []
    for i, b in enumerate(data.get("persistent_buttons", [])):
        icon = "🔗" if b.get("type") == "url" else "💬"
        btns.append([btn(f"{icon} {b.get('label','')[:25]}", f"pbtn_view_{i}", "primary")])
    if not btns:
        btns.append([btn("📭 لا توجد أزرار بعد", "none")])
    btns.append([btn("➕ إضافة زر نص", "pbtn_add_text", "primary")])
    btns.append([btn("🔗 إضافة زر رابط", "pbtn_add_url", "primary")])
    if data.get("persistent_buttons"):
        btns.append([btn("🗑️ حذف الكل", "pbtn_clear_all", "danger")])
    btns.append([btn("🔙 رجوع", "main", "primary")])
    return InlineKeyboardMarkup(btns)

def pbtn_view_menu(idx):
    return InlineKeyboardMarkup([
        [btn("🗑️ حذف هذا الزر", f"pbtn_del_{idx}", "danger")],
        [btn("🔙 رجوع", "pbuttons", "primary")],
    ])
