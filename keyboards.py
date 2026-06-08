# keyboards.py
# 🎛️ ملف الأزرار والقوائم - V5.0 (زر بطاقة المستخدم)

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from utils import data

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
    has_menu   = "✅" if data.get("menu_buttons") else "❌"
    return InlineKeyboardMarkup([
        [btn("📝 رسائل البوت",             "msg_settings",   "primary")],
        [btn(f"{away_icon} وضع الغياب",    "away_settings",  "primary")],
        [btn(f"{smart_icon} الردود الذكية","toggle_smart",   "primary")],
        [btn("🔗 إدارة الروابط",           "links_settings", "success")],
        [btn(f"{has_menu} القائمة الدائمة", "menu_buttons_settings", "success")],
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

    # أزرار التفاعل — يضغط عليها الأونر، تظهر للمستخدم ويصله إشعار
    row_reactions = [
        InlineKeyboardButton("❤️", callback_data=f"react_{user_id}_❤️"),
        InlineKeyboardButton("👍", callback_data=f"react_{user_id}_👍"),
        InlineKeyboardButton("😂", callback_data=f"react_{user_id}_😂"),
        InlineKeyboardButton("🔥", callback_data=f"react_{user_id}_🔥"),
        InlineKeyboardButton("👏", callback_data=f"react_{user_id}_👏"),
    ]

    rows = [row0, row1, row_reactions]

    quick_btns = []
    for title in list(data["quick_replies"].keys())[:3]:
        quick_btns.append(btn(f"💬 {title[:8]}", f"sendqr_{user_id}_{title}", "primary"))
    if quick_btns:
        rows.append(quick_btns)

    return InlineKeyboardMarkup(rows)


def incoming_msg_btns_reacted(user_id, emoji: str):
    """نفس الأزرار لكن مع إبراز الإيموجي اللي الأونر اختاره"""
    uid            = str(user_id)
    is_user_vip    = uid in data["vip_users"]
    is_user_banned = uid in data["banned"]
    user_name      = data["users"].get(uid, {}).get("name", "مجهول")

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

    EMOJIS = ["❤️", "👍", "😂", "🔥", "👏"]
    row_reactions = []
    for em in EMOJIS:
        label = f"✅{em}" if em == emoji else em
        row_reactions.append(InlineKeyboardButton(label, callback_data=f"react_{user_id}_{em}"))

    rows = [row0, row1, row_reactions]

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
#              🟢 أزرار الروابط (تظهر للمستخدم في الترحيب)
# ═══════════════════════════════════════════════════════════════

def welcome_links_btns():
    """أزرار خضراء للروابط تظهر للمستخدم تحت رسالة الترحيب"""
    links = data.get("links", {})
    owner_link  = links.get("owner_account", "")
    group_link  = links.get("doctor_fonts_group", "")
    owner_label = links.get("owner_label", "👤 حساب المالك") or "👤 حساب المالك"
    group_label = links.get("group_label", "👨‍💻 مجموعة دكتور خطوط") or "👨‍💻 مجموعة دكتور خطوط"

    rows = []
    if owner_link:
        rows.append([InlineKeyboardButton(owner_label, url=owner_link)])
    if group_link:
        rows.append([InlineKeyboardButton(group_label, url=group_link)])

    return InlineKeyboardMarkup(rows) if rows else None


# ═══════════════════════════════════════════════════════════════
#              ⚙️ إدارة الروابط (صفحة الأدمن)
# ═══════════════════════════════════════════════════════════════

def links_settings_menu():
    """قائمة إدارة الروابط في لوحة الأدمن"""
    links = data.get("links", {})
    owner_set = "✅" if links.get("owner_account") else "❌"
    group_set = "✅" if links.get("doctor_fonts_group") else "❌"
    return InlineKeyboardMarkup([
        [btn(f"{owner_set} رابط حساب المالك",         "edit_owner_link",       "success")],
        [btn("✏️ تعديل نص زر المالك",                  "edit_owner_label",      "primary")],
        [btn(f"{group_set} رابط مجموعة دكتور خطوط",   "edit_group_link",       "success")],
        [btn("✏️ تعديل نص زر المجموعة",                "edit_group_label",      "primary")],
        [btn("🔙 رجوع", "settings", "primary")],
    ])

# ═══════════════════════════════════════════════════════════════
#        📋 القائمة الدائمة للمستخدم (Reply Keyboard)
# ═══════════════════════════════════════════════════════════════

def user_reply_keyboard():
    """
    ينشئ ReplyKeyboard دائمة من أزرار menu_buttons المحفوظة.
    إذا لا توجد أزرار يُعيد None.
    الأزرار تُوزَّع صفَّين صفَّين.
    """
    buttons = data.get("menu_buttons", [])
    if not buttons:
        return None
    rows = []
    row = []
    for i, btn_data in enumerate(buttons):
        row.append(KeyboardButton(btn_data["text"]))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def remove_reply_keyboard():
    return ReplyKeyboardRemove()


# ═══════════════════════════════════════════════════════════════
#        ⚙️ إدارة أزرار القائمة الدائمة (صفحة الأدمن)
# ═══════════════════════════════════════════════════════════════

def menu_buttons_admin():
    """قائمة إدارة الأزرار الدائمة في لوحة الأدمن"""
    buttons = data.get("menu_buttons", [])
    rows = []
    for i, b in enumerate(buttons):
        short = b["text"][:20]
        rows.append([
            btn(f"🔤 {short}", f"mb_noop_{i}", "primary"),
            btn("🗑️", f"mb_del_{i}", "danger"),
        ])
    rows.append([btn("➕ إضافة زر", "mb_add", "success")])
    if buttons:
        rows.append([btn("🗑️ حذف الكل", "mb_clear", "danger")])
    rows.append([btn("🔙 رجوع", "settings", "primary")])
    return InlineKeyboardMarkup(rows)
