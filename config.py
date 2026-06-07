# config.py
# ⚙️ الإعدادات + البيانات + الدوال المساعدة - V6.0 (MongoDB)

import os
import json
from datetime import datetime

# ═══════════════════════════════════════════════════════════════
#                    🔐 المتغيرات السرية
# ═══════════════════════════════════════════════════════════════

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID  = int(os.environ.get("OWNER_ID", "0"))
MONGO_URL = os.environ.get("MONGO_URL", "")   # ← متغير جديد في Railway

# ═══════════════════════════════════════════════════════════════
#                      💾 البيانات الافتراضية
# ═══════════════════════════════════════════════════════════════

DEFAULT_DATA = {
    "messages": {
        "welcome":  "✨ أهلاً بك يا {name}\n\n📩 أرسل رسالتك وسيتم الرد عليك قريباً ❤️",
        "away":     "⏰ نحن غير متواجدين حالياً، سنرد عليك فور عودتنا",
        "received": "✅ تم استلام رسالتك! انتظر الرد ❤️",
        "banned":   "🚫 أنت محظور من استخدام البوت",
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
    "stats": {
        "total_received": 0,
        "total_sent":     0,
        "today_received": 0,
        "today_sent":     0,
        "today_date":     "",
    },
}

# ═══════════════════════════════════════════════════════════════
#               💾 طبقة التخزين (MongoDB أو JSON كاحتياط)
# ═══════════════════════════════════════════════════════════════

# --- محاولة الاتصال بـ MongoDB ---
_mongo_col = None
if MONGO_URL:
    try:
        from pymongo import MongoClient
        _client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        _client.server_info()          # اختبار الاتصال فوراً
        _mongo_col = _client["bot_db"]["data"]
        print("✅ MongoDB متصل بنجاح")
    except Exception as _e:
        print(f"⚠️ فشل الاتصال بـ MongoDB: {_e}")
        print("⚠️ سيتم الاحتياط إلى ملف JSON محلي")
        _mongo_col = None
else:
    print("⚠️ MONGO_URL غير موجود – سيتم استخدام ملف JSON محلي")

DATA_FILE = os.environ.get("DATA_FILE", "bot_data.json")

# ═══════════════════════════════════════════════════════════════

def _merge_defaults(loaded: dict) -> dict:
    """يضيف أي مفاتيح ناقصة من DEFAULT_DATA."""
    for key, val in DEFAULT_DATA.items():
        if key not in loaded:
            loaded[key] = val.copy() if isinstance(val, (dict, list)) else val
        elif isinstance(val, dict):
            for sub, sub_val in val.items():
                loaded[key].setdefault(sub, sub_val)
    return loaded


def load_data() -> dict:
    """تحميل البيانات – MongoDB أولاً، ثم JSON كاحتياط."""
    # --- MongoDB ---
    if _mongo_col is not None:
        try:
            doc = _mongo_col.find_one({"_id": "main"})
            if doc:
                doc.pop("_id", None)
                return _merge_defaults(doc)
            # أول تشغيل – لا يوجد مستند بعد
            return json.loads(json.dumps(DEFAULT_DATA))
        except Exception as e:
            print(f"❌ خطأ في تحميل MongoDB: {e}")

    # --- JSON احتياطي ---
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return _merge_defaults(json.load(f))
    except Exception as e:
        print(f"❌ خطأ في تحميل JSON: {e}")

    return json.loads(json.dumps(DEFAULT_DATA))


def save_data() -> bool:
    """حفظ البيانات – MongoDB أولاً، ثم JSON كاحتياط."""
    # --- MongoDB ---
    if _mongo_col is not None:
        try:
            _mongo_col.replace_one(
                {"_id": "main"},
                {"_id": "main", **data},
                upsert=True,
            )
            return True
        except Exception as e:
            print(f"❌ خطأ في حفظ MongoDB: {e}")
            # لا نرجع False مباشرة – نجرب JSON كاحتياط

    # --- JSON احتياطي ---
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ JSON: {e}")
        return False


# المتغير العام للبيانات
data = load_data()

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
        stats["total_sent"]  += 1
        stats["today_sent"]  += 1
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
print("✅ تم تحميل config.py  (V6 – MongoDB)")
print(f"👑 OWNER_ID = {OWNER_ID}")
print(f"💾 وضع التخزين: {'MongoDB ☁️' if _mongo_col is not None else 'JSON محلي ⚠️'}")
if OWNER_ID == 0:
    print("⚠️ تحذير: OWNER_ID غير مضبوط! ضعه في متغيرات البيئة.")
if not BOT_TOKEN:
    print("⚠️ تحذير: BOT_TOKEN غير مضبوط! ضعه في متغيرات البيئة.")
if not MONGO_URL:
    print("⚠️ تحذير: MONGO_URL غير مضبوط! البيانات ستُمسح عند كل restart.")
print("=" * 50)
