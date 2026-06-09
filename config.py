# config.py
# ⚙️ الإعدادات + البيانات + الدوال المساعدة - V7.0 (Telegram Backup)

import os
import json
import asyncio
from datetime import datetime

# ═══════════════════════════════════════════════════════════════
#                    🔐 المتغيرات السرية
# ═══════════════════════════════════════════════════════════════

BOT_TOKEN   = os.environ.get("BOT_TOKEN", "")
OWNER_ID    = int(os.environ.get("OWNER_ID", "0"))
BACKUP_CHAT = int(os.environ.get("BACKUP_CHAT", "5231453921"))

DATA_FILE = "/tmp/bot_data.json"   # مؤقت – البيانات الحقيقية في Telegram

# ═══════════════════════════════════════════════════════════════
#                      💾 البيانات الافتراضية
# ═══════════════════════════════════════════════════════════════

DEFAULT_DATA = {
    "messages": {
        "welcome":              "✨ أهلاً بك يا {name}\n\n📩 أرسل رسالتك وسيتم الرد عليك قريباً ❤️",
        "away":                 "⏰ نحن غير متواجدين حالياً، سنرد عليك فور عودتنا",
        "received":             "✅ تم استلام رسالتك! انتظر الرد ❤️",
        "banned":               "🚫 أنت محظور من استخدام البوت",
        "returned_after_block": "عوداً حميداً {name} 😊\n\nسعيدون بعودتك! أرسل رسالتك وسيتم الرد عليك ❤️",
        "send_prompt":          "📩 أرسل رسالتك الآن وسيتم الرد عليك قريباً",
    },
    "status": {
        "is_away":             False,
        "smart_reply_enabled": True,
    },
    "users":        {},
    "admins":       {},
    "banned":       [],
    "vip_users":    [],
    "smart_replies":{},
    "quick_replies":{},
    "user_notes":   {},
    "msg_map":      {},
    "emoji_packs":  [],
    "persistent_buttons": [],   # [{label, type:"text"|"url", value}]
    "received_msgs": {},        # uid -> message_id لرسالة "تم الاستلام" الحالية
    "stats": {
        "total_received": 0,
        "total_sent":     0,
        "today_received": 0,
        "today_sent":     0,
        "today_date":     "",
    },
    "_backup_message_id": None,   # ID رسالة الباكب في Telegram
}

# ═══════════════════════════════════════════════════════════════
#               💾 تحميل وحفظ البيانات (ملف مؤقت)
# ═══════════════════════════════════════════════════════════════

def _merge_defaults(loaded: dict) -> dict:
    for key, val in DEFAULT_DATA.items():
        if key not in loaded:
            loaded[key] = val.copy() if isinstance(val, (dict, list)) else val
        elif isinstance(val, dict):
            for sub, sub_val in val.items():
                loaded[key].setdefault(sub, sub_val)
    return loaded


def load_data() -> dict:
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return _merge_defaults(json.load(f))
    except Exception as e:
        print(f"❌ خطأ في تحميل البيانات المحلية: {e}")
    return json.loads(json.dumps(DEFAULT_DATA))


def save_data() -> bool:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ البيانات المحلية: {e}")
        return False


# المتغير العام للبيانات
data = load_data()

# ═══════════════════════════════════════════════════════════════
#               ☁️ Telegram Backup - استعادة عبر /restore
# ═══════════════════════════════════════════════════════════════

async def restore_from_telegram(bot) -> bool:
    """stub — الاستعادة تتم عبر /restore في main.py"""
    return False


async def restore_from_file(bot, document) -> bool:
    """
    يستعيد البيانات من ملف JSON أرسله المالك عبر /restore.
    يُستدعى من main.py عند استقبال الملف.
    """
    global data
    try:
        file    = await bot.get_file(document.file_id)
        content = await file.download_as_bytearray()
        loaded  = json.loads(content.decode("utf-8"))
        data.update(_merge_defaults(loaded))
        save_data()
        print("✅ تم استعادة البيانات من ملف JSON")
        return True
    except Exception as e:
        print(f"❌ فشل استعادة الباكب: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
#               ☁️ Telegram Backup - حفظ دوري
# ═══════════════════════════════════════════════════════════════

async def backup_to_telegram(bot) -> bool:
    """
    يرسل البيانات كاملة كملف JSON إلى BACKUP_CHAT.
    يُحدّث رسالة الباكب القديمة أو يرسل رسالة جديدة.
    """
    global data
    try:
        import io
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        file_obj = io.BytesIO(content)
        file_obj.name = "bot_data.json"

        msg_id = data.get("_backup_message_id")

        # نحذف الرسالة القديمة لو موجودة
        if msg_id:
            try:
                await bot.delete_message(chat_id=BACKUP_CHAT, message_id=msg_id)
            except Exception:
                pass

        # نبعت الملف الجديد
        sent = await bot.send_document(
            chat_id=BACKUP_CHAT,
            document=file_obj,
            caption=f"🔒 #BACKUP\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        )
        data["_backup_message_id"] = sent.message_id
        save_data()
        print(f"✅ تم حفظ الباكب في Telegram (msg_id={sent.message_id})")
        return True
    except Exception as e:
        print(f"❌ خطأ في الباكب: {e}")
        return False


def save_data_and_schedule_backup(bot=None) -> bool:
    """يحفظ محلياً + يجدول باكب Telegram."""
    result = save_data()
    if bot:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(backup_to_telegram(bot))
        except Exception:
            pass
    return result


# ═══════════════════════════════════════════════════════════════
#                      🔧 دوال مساعدة
# ═══════════════════════════════════════════════════════════════

def is_owner(user_id) -> bool:
    try:
        return int(user_id) == OWNER_ID
    except (TypeError, ValueError):
        return False


def is_admin(user_id) -> bool:
    return str(user_id) in data["admins"] or is_owner(user_id)


def can_reply(user_id) -> bool:
    if is_owner(user_id):
        return True
    admin = data["admins"].get(str(user_id), {})
    return admin.get("can_reply", False)


def is_banned(user_id) -> bool:
    return str(user_id) in data["banned"]


def is_vip(user_id) -> bool:
    return str(user_id) in data["vip_users"]


def save_user(user) -> None:
    uid = str(user.id)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    info = data["users"].get(uid)
    if info is None:
        data["users"][uid] = {
            "name":      user.first_name or "مجهول",
            "username":  user.username or "",
            "joined":    now,
            "last_seen": now,
            "msg_count": 0,
        }
    else:
        info["last_seen"] = now
        info["name"]      = user.first_name or "مجهول"
        info["username"]  = user.username or ""
    save_data()


def update_stats(stat_type: str) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    stats = data["stats"]
    if stats["today_date"] != today:
        stats["today_received"] = 0
        stats["today_sent"]     = 0
        stats["today_date"]     = today

    if stat_type == "received":
        stats["total_received"] += 1
        stats["today_received"] += 1
    elif stat_type == "sent":
        stats["total_sent"] += 1
        stats["today_sent"] += 1
    save_data()


def get_smart_reply(text: str):
    if not data["status"].get("smart_reply_enabled"):
        return None
    text_lower = (text or "").strip().lower()
    if not text_lower:
        return None
    for trigger, response in data["smart_replies"].items():
        t = trigger.lower()
        if t in text_lower or text_lower in t:
            return response
    return None


# ═══════════════════════════════════════════════════════════════
#                      ✅ تأكيد التحميل
# ═══════════════════════════════════════════════════════════════

print("=" * 50)
print("✅ تم تحميل config.py  (V7 – Telegram Backup)")
print(f"👑 OWNER_ID    = {OWNER_ID}")
print(f"💾 BACKUP_CHAT = {BACKUP_CHAT}")
print("=" * 50)
