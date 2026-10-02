"""
بوت التواصل
python-telegram-bot >= 22.8
"""

import json
import html
import logging
import os
import re
import shutil
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

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

# ═══════════════════════════════════════════════════════════════
#  إعدادات أساسية
# ═══════════════════════════════════════════════════════════════

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID  = int(os.environ.get("OWNER_ID", "0"))

if not BOT_TOKEN or not OWNER_ID:
    raise SystemExit(
        "لازم تحدد BOT_TOKEN و OWNER_ID كمتغيرات بيئة قبل تشغيل البوت.\n"
        "مثال (Linux/Mac):\n"
        "  export BOT_TOKEN=\"8905466188:AAGxiQT0wGykoPChvRdasusvPr4Kxtwh_E0\"\n"
        "  export OWNER_ID=\"5231453921\"\n"
        "أو حطهم في ملف .env مع مكتبة python-dotenv."
    )

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

# ═══════════════════════════════════════════════════════════════
#  ملفات التخزين
# ═══════════════════════════════════════════════════════════════

_VOLUME_MOUNT_PATH = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
DATA_DIR = Path(_VOLUME_MOUNT_PATH) if _VOLUME_MOUNT_PATH else Path(".")

if _VOLUME_MOUNT_PATH:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SystemExit(
            f"لا يمكن الوصول إلى Volume في {_VOLUME_MOUNT_PATH}: {e}"
        )

_DATA_FILENAMES = (
    "settings.json", "banned.json", "users.json", "msg_map.json",
    "old_stats.json", "user_state.json", "user_stats.json",
    "message_records.json", "audit_log.json",
)


def _migrate_legacy_files_to_volume():
    """
    ينقل ملفات النسخة السابقة من مجلد التطبيق إلى Volume مرة واحدة إذا كانت
    ما زالت موجودة. لا يستبدل أي ملف موجود بالفعل داخل Volume.
    """
    if not _VOLUME_MOUNT_PATH:
        return
    for filename in _DATA_FILENAMES:
        legacy = Path(filename)
        target = DATA_DIR / filename
        try:
            if legacy.resolve() == target.resolve():
                continue
            if legacy.exists() and not target.exists():
                shutil.copy2(legacy, target)
                logger.info(f"تم نقل ملف الحالة إلى Volume: {filename}")
        except OSError as e:
            logger.warning(f"تعذر نقل ملف الحالة {filename} إلى Volume: {e}")


_migrate_legacy_files_to_volume()

SETTINGS_FILE  = DATA_DIR / "settings.json"
BANNED_FILE    = DATA_DIR / "banned.json"
USERS_FILE     = DATA_DIR / "users.json"
MSG_MAP_FILE   = DATA_DIR / "msg_map.json"
OLD_STATS_FILE = DATA_DIR / "old_stats.json"  # يحتفظ بإحصائيات النسخة القديمة بعد الاستعادة (للمرجعية فقط)
USER_STATE_FILE = DATA_DIR / "user_state.json"
USER_STATS_FILE = DATA_DIR / "user_stats.json"
MESSAGE_RECORDS_FILE = DATA_DIR / "message_records.json"
AUDIT_LOG_FILE = DATA_DIR / "audit_log.json"

DEFAULT_WELCOME = (
    "مرحبًا بك في بوت التواصل. 👋\n\n"
    "يمكنك إرسال رسائلك، استفساراتك، ارسل رسالاتك بوضوح مفصل ، وسيتم الاطلاع عليها والرد في أقرب وقت."
)
DEFAULT_BUTTONS = [
    {"text": "خاص المدير", "url": "https://t.me/hamo_alfiqi", "style": "success"},
    {"text": "مجموعة الدكتور",     "url": "https://t.me/alfiqifont", "style": "success"},
]
DEFAULT_AWAY_MSG = (
    "🌙 أنا حالياً غير متاح.\n"
    "سيتم الرد على رسالتك في أقرب وقت ممكن، شكراً على تواصلك! 🙏"
)
DEFAULT_QUICK_REPLY_MSG = (
    "⚡ تم استلام رسالتك، سيتم الرد عليك في أقرب وقت ممكن. شكراً لتواصلك! 🙏"
)
DEFAULT_AI_INSTRUCTIONS = (
    "أنت مساعد ذكي ولبق لبوت تليجرام. مهمتك الرد على استفسارات ورسائل المستخدمين "
    "بأسلوب احترافي ومختصر ومفيد ومهذب. أرسل الرد بصيغة Telegram HTML فقط، "
    "واستخدم عند الحاجة الوسوم المدعومة مثل <b> و<i> و<u> و<s> و<code> و<pre> "
    "و<blockquote>، مع الحفاظ على الاقتباسات والأسطر والقوائم. لا تستخدم Markdown "
    "ولا تضع الرد داخل ```."
)
DEFAULT_AI_MODEL = "gpt-4o-mini"
DEFAULT_AI_BASE_URL = "https://api.openai.com/v1"

def _load(path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default

def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_settings():
    d = _load(SETTINGS_FILE, {})
    d.setdefault("welcome", DEFAULT_WELCOME)
    d.setdefault("buttons", DEFAULT_BUTTONS)
    d.setdefault("away_enabled", False)
    d.setdefault("away_msg", DEFAULT_AWAY_MSG)
    d.setdefault("autoresponder_enabled", False)
    d.setdefault("auto_replies", [])           # [{"keyword": "...", "reply": "..."}]
    d.setdefault("quick_reply_enabled", False)
    d.setdefault("quick_reply_msg", DEFAULT_QUICK_REPLY_MSG)
    d.setdefault("ai_enabled", False)
    d.setdefault("ai_instructions", DEFAULT_AI_INSTRUCTIONS)
    d.setdefault("ai_api_key", os.environ.get("AI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", ""))
    d.setdefault("ai_model", DEFAULT_AI_MODEL)
    d.setdefault("ai_base_url", DEFAULT_AI_BASE_URL)
    d.setdefault("protect_content_enabled", False)
    d.setdefault("global_pin", {
        "source_message_id": None,
        "targets": {},
        "updated_at": 0,
    })
    return d

def save_settings(d):    _save(SETTINGS_FILE, d)

def protect_kwargs(chat_id) -> dict:
    """
    يرجع {"protect_content": True} لو إعداد "حماية المحتوى" مفعّل والمستلم
    مش المالك، وإلا يرجع {} (من غير ما يعمل أي استثناء تحت أي ظرف، حتى لو
    فشلت قراءة ملف الإعدادات لأي سبب، عشان أي خطأ هنا ميكسرش إرسال الرسالة
    نفسها).
    """
    try:
        if chat_id is not None and int(chat_id) == OWNER_ID:
            return {}
        if load_settings().get("protect_content_enabled", False):
            return {"protect_content": True}
    except Exception as e:
        logger.error(f"protect_kwargs error: {e}")
    return {}
def _normalize_ban_record(uid, value=None) -> dict | None:
    """يحوّل سجلاً قديماً (ID فقط) أو جديداً إلى صيغة موحدة."""
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return None

    if isinstance(value, dict):
        try:
            expires_at = value.get("expires_at")
            expires_at = float(expires_at) if expires_at else None
        except (TypeError, ValueError):
            expires_at = None
        try:
            banned_at = float(value.get("banned_at") or time.time())
        except (TypeError, ValueError):
            banned_at = time.time()
        return {
            "user_id": uid,
            "reason": str(value.get("reason") or "لم يتم تحديد سبب"),
            "banned_at": banned_at,
            "expires_at": expires_at,
            "duration_key": str(value.get("duration_key") or "permanent"),
        }

    return {
        "user_id": uid,
        "reason": "لم يتم تحديد سبب",
        "banned_at": time.time(),
        "expires_at": None,
        "duration_key": "permanent",
    }


def load_ban_records() -> dict[str, dict]:
    """يقرأ الحظر بصيغة السجلات، مع دعم banned.json القديم الذي كان IDs فقط."""
    raw = _load(BANNED_FILE, [])
    records = {}
    if isinstance(raw, dict):
        iterator = raw.items()
    elif isinstance(raw, list):
        iterator = (
            (
                item.get("user_id") if isinstance(item, dict) else item,
                item if isinstance(item, dict) else None,
            )
            for item in raw
        )
    else:
        iterator = ()

    for uid, value in iterator:
        record = _normalize_ban_record(uid, value)
        if record:
            records[str(record["user_id"])] = record
    return records


def save_ban_records(records: dict[str, dict]):
    _save(BANNED_FILE, list(records.values()))


def _purge_expired_bans() -> dict[str, dict]:
    records = load_ban_records()
    now = time.time()
    active = {
        key: record
        for key, record in records.items()
        if not record.get("expires_at") or float(record["expires_at"]) > now
    }
    if len(active) != len(records):
        save_ban_records(active)
    return active


def load_banned():
    return {int(uid) for uid in _purge_expired_bans().keys()}


def save_banned(b):
    """توافق مع الاستدعاءات القديمة مع الحفاظ على بيانات السبب والمدة."""
    current = load_ban_records()
    wanted = set()
    for uid in b:
        try:
            wanted.add(int(uid))
        except (TypeError, ValueError):
            continue
    records = {}
    for uid in wanted:
        key = str(uid)
        records[key] = current.get(key) or _normalize_ban_record(uid)
    save_ban_records(records)
def load_users():        return set(_load(USERS_FILE, []))
def save_users(u):       _save(USERS_FILE, list(u))

def load_msg_map():
    """
    يحمّل msg_map من ملف على القرص عشان الروابط بين الرسائل المحوّلة
    والمستخدمين متمسحش من الذاكرة عند أي إعادة تشغيل للبوت (ديبلوي جديد،
    كراش، أو Railway بينام ويصحى).
    """
    raw = _load(MSG_MAP_FILE, {})
    return {int(k): tuple(v) for k, v in raw.items()}

def save_msg_map(m):
    _save(MSG_MAP_FILE, {str(k): list(v) for k, v in m.items()})


# ═══════════════════════════════════════════════════════════════
#  الحالة والإحصائيات والسجل — ميزات إدارة المستخدمين
# ═══════════════════════════════════════════════════════════════

SNOOZE_OPTIONS = {
    "1h": 3600,
    "4h": 4 * 3600,
    "tomorrow": 24 * 3600,
    "3d": 3 * 24 * 3600,
    "week": 7 * 24 * 3600,
}
SNOOZE_LABELS = {
    "1h": "ساعة",
    "4h": "4 ساعات",
    "tomorrow": "غداً",
    "3d": "3 أيام",
    "week": "أسبوع",
}
REMINDER_JOB_PREFIX = "snooze:"
BAN_JOB_PREFIX = "ban-expiry:"
DELETE_WINDOW_SECONDS = 48 * 3600
RECENT_DELETE_WINDOW_SECONDS = 24 * 3600

BAN_OPTIONS = {
    "1h": (3600, "ساعة واحدة"),
    "6h": (6 * 3600, "6 ساعات"),
    "12h": (12 * 3600, "12 ساعة"),
    "1d": (24 * 3600, "يوم واحد"),
    "3d": (3 * 24 * 3600, "3 أيام"),
    "7d": (7 * 24 * 3600, "7 أيام"),
    "14d": (14 * 24 * 3600, "14 يوم"),
    "30d": (30 * 24 * 3600, "30 يوم"),
    "permanent": (None, "بدون انتهاء / حتى فك يدوي"),
}


def load_user_state():
    return _load(USER_STATE_FILE, {})


def save_user_state(data):
    _save(USER_STATE_FILE, data)


def load_user_stats():
    return _load(USER_STATS_FILE, {})


def save_user_stats(data):
    _save(USER_STATS_FILE, data)


def load_message_records():
    return _load(MESSAGE_RECORDS_FILE, {})


def save_message_records(data):
    _save(MESSAGE_RECORDS_FILE, data)


def load_audit_log():
    return _load(AUDIT_LOG_FILE, [])


def save_audit_log(data):
    _save(AUDIT_LOG_FILE, data[-1000:])


def _uid_key(uid: int) -> str:
    return str(int(uid))


def _default_user_state():
    return {
        "muted_until": 0,
        "snoozed_until": 0,
        "pinned": False,
        "pinned_message_id": None,
        "updated_at": time.time(),
    }


def get_user_state(uid: int) -> dict:
    states = load_user_state()
    current = _default_user_state()
    current.update(states.get(_uid_key(uid), {}))
    return current


def update_user_state(uid: int, **changes) -> dict:
    states = load_user_state()
    current = get_user_state(uid)
    current.update(changes)
    current["updated_at"] = time.time()
    states[_uid_key(uid)] = current
    save_user_state(states)
    return current


def get_user_stats(uid: int) -> dict:
    stats = load_user_stats()
    current = {
        "message_count": 0,
        "last_contact": 0,
        "last_reply": 0,
    }
    current.update(stats.get(_uid_key(uid), {}))
    return current


def update_user_stats(uid: int, **changes) -> dict:
    stats = load_user_stats()
    current = get_user_stats(uid)
    current.update(changes)
    stats[_uid_key(uid)] = current
    save_user_stats(stats)
    return current


def append_audit(uid: int, action: str, details: str = ""):
    log = load_audit_log()
    log.append({
        "user_id": int(uid),
        "action": action,
        "details": details,
        "at": time.time(),
    })
    save_audit_log(log)


def _ensure_record_bucket(records, uid: int) -> dict:
    key = _uid_key(uid)
    bucket = records.setdefault(key, {
        "owner": [],
        "user": [],
        "created_at": time.time(),
    })
    bucket.setdefault("owner", [])
    bucket.setdefault("user", [])
    return bucket


def record_message(uid: int, side: str, message_id: int, kind: str):
    if not message_id or side not in ("owner", "user"):
        return
    records = load_message_records()
    bucket = _ensure_record_bucket(records, uid)
    items = bucket[side]
    if not any(int(item.get("id", 0)) == int(message_id) for item in items):
        items.append({
            "id": int(message_id),
            "kind": kind,
            "created_at": time.time(),
        })
        save_message_records(records)


def remove_recorded_message(uid: int, side: str, message_id: int):
    """يحذف رسالة واحدة من سجل الحذف بدون لمس بقية سجل المستخدم."""
    if side not in ("owner", "user") or not message_id:
        return
    records = load_message_records()
    bucket = records.get(_uid_key(uid))
    if not bucket:
        return
    kept = []
    for item in bucket.get(side, []):
        try:
            if int(item.get("id", 0)) != int(message_id):
                kept.append(item)
        except (TypeError, ValueError):
            kept.append(item)
    bucket[side] = kept
    save_message_records(records)


def _record_ids(uid: int, side: str) -> list[int]:
    bucket = load_message_records().get(_uid_key(uid), {})
    result = []
    for item in bucket.get(side, []):
        try:
            result.append(int(item["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    # تضمين روابط النسخ القديمة التي أُنشئت قبل تفعيل سجل الرسائل الجديد.
    for owner_id, (mapped_uid, user_message_id) in msg_map.items():
        if int(mapped_uid) != int(uid):
            continue
        if side == "owner":
            result.append(int(owner_id))
        elif user_message_id:
            result.append(int(user_message_id))
    return list(dict.fromkeys(result))


def _record_items(uid: int, side: str) -> list[dict]:
    bucket = load_message_records().get(_uid_key(uid), {})
    return list(bucket.get(side, []))


def find_user_by_owner_message(message_id: int) -> int | None:
    for uid, bucket in load_message_records().items():
        for item in bucket.get("owner", []):
            try:
                if int(item.get("id")) == int(message_id):
                    return int(uid)
            except (TypeError, ValueError):
                continue
    return None


def clear_message_records(uid: int):
    records = load_message_records()
    records.pop(_uid_key(uid), None)
    save_message_records(records)
    for owner_id, (mapped_uid, _) in list(msg_map.items()):
        if int(mapped_uid) == int(uid):
            msg_map.pop(owner_id, None)
    save_msg_map(msg_map)
    # إزالة الروابط المؤقتة حتى لا تستمر التفاعلات أو التعديلات على سجل محذوف.
    for sent_id, (_, mapped_uid) in list(globals().get("reply_map", {}).items()):
        if int(mapped_uid) == int(uid):
            reply_map.pop(sent_id, None)
    for owner_id, info in list(globals().get("owner_sent_map", {}).items()):
        if int(info.get("user_id", 0)) == int(uid):
            owner_sent_map.pop(owner_id, None)
    if globals().get("pending_silent", {}).get(OWNER_ID) == int(uid):
        pending_silent.pop(OWNER_ID, None)
    settings = load_settings()
    global_pin = settings.get("global_pin")
    if isinstance(global_pin, dict) and _uid_key(uid) in global_pin.get("targets", {}):
        global_pin["targets"].pop(_uid_key(uid), None)
        settings["global_pin"] = global_pin
        save_settings(settings)


def _remaining_text(until: float, now: float | None = None) -> str:
    if not until:
        return ""
    seconds = int(until - (now or time.time()))
    if seconds <= 0:
        return ""
    minutes = max(1, seconds // 60)
    if minutes < 60:
        return f"{minutes} د"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} س"
    return f"{hours // 24} يوم"


def user_status(uid: int, now: float | None = None) -> tuple[str, str]:
    now = now or time.time()
    if uid in load_banned():
        return "🚫", "محظور"
    state = get_user_state(uid)
    if state.get("muted_until", 0) > now:
        return "🔇", f"كتم ({_remaining_text(state['muted_until'], now)})"
    if state.get("snoozed_until", 0) > now:
        return "💤", f"تأجيل ({_remaining_text(state['snoozed_until'], now)})"
    return "🟢", "نشط"


def display_time(timestamp: float) -> str:
    if not timestamp:
        return "—"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _safe(value, fallback="—") -> str:
    return html.escape(str(value or fallback))

# ═══════════════════════════════════════════════════════════════
#  حالات ConversationHandler
# ═══════════════════════════════════════════════════════════════

AWAIT_WELCOME_TEXT     = 1
AWAIT_BUTTONS_TEXT     = 2
AWAIT_BROADCAST_MSG    = 3
AWAIT_AWAY_TEXT        = 4
AWAIT_AUTO_KEYWORD_ADD = 5
AWAIT_QUICK_REPLY_TEXT = 6
AWAIT_AI_INSTRUCTIONS  = 7
AWAIT_AI_KEY           = 8
AWAIT_AI_MODEL         = 9
AWAIT_BAN_REASON       = 10
# ═══════════════════════════════════════════════════════════════
#  خرائط الرسائل (ذاكرة)
#  msg_map        : owner_fwd_id → (user_id, user_msg_id | None)
#  reply_map      : sent_id_at_user → (owner_reply_id, user_id)
#  owner_sent_map : owner_msg_id → معلومات الرسالة اللي اتبعتت للمستخدم
#                    (عشان لو المالك عدّل رسالته تتعدل فعليًا عند المستخدم)
# ═══════════════════════════════════════════════════════════════

msg_map   = load_msg_map()
reply_map = {}
owner_sent_map = {}

# وضع الإرسال الصامت: owner_id → user_id بانتظار الرسالة التالية لترسل بدون "رد"
# يُفعَّل بالرد على رسالة محوّلة بأمر "ا" أو "أ" وحدها
pending_silent = {}

# يحتفظ بآخر وقت إرسال رسالة لكل مستخدم (Unix timestamp)
# البرق يُضاف فقط عند أول رسالة أو بعد انقطاع ساعة
user_last_msg_time = {}
REACTION_COOLDOWN = 3600  # ثانية = ساعة واحدة

# ═══════════════════════════════════════════════════════════════
#  مساعدات عامة
# ═══════════════════════════════════════════════════════════════

def user_mention(user):
    name = user.full_name or "مجهول"
    if user.username:
        return f'<a href="https://t.me/{user.username}">{name}</a>'
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def chat_mention(chat):
    """
    مثل user_mention لكن للـ Chat الخاص (private chat) اللي بيمثّل المستخدم.
    بيُستخدم في my_chat_member لأن new_chat_member.user هناك بيمثّل البوت نفسه،
    والبيانات الحقيقية للمستخدم اللي حظر/فك حظر البوت موجودة في mc.chat.
    """
    name = " ".join(filter(None, [chat.first_name, chat.last_name])) or "مجهول"
    if chat.username:
        return f'<a href="https://t.me/{chat.username}">{name}</a>'
    return f'<a href="tg://user?id={chat.id}">{name}</a>'

VALID_BUTTON_STYLES = {"primary", "success", "danger"}


def _button_text_and_api_kwargs(text: str, style: str | None = None):
    """
    يبني نصّ الزر + api_kwargs لدعم:
    - اللون (style: primary/success/danger)
    - إيموجي بريميوم على الزر عبر الصيغة {ID}

    ملاحظة مهمة (سبب المشكلة اللي كانت موجودة):
    تليجرام في الأزرار (InlineKeyboardButton) مش بيدعم "entities" جوه نص
    الزر زي ما بيحصل في نص الرسائل العادية. اللي بيدعمه فعليًا (من Bot API
    9.4) هو حقل مستقل اسمه icon_custom_emoji_id بيظهر بيه إيموجي واحد
    كـ "أيقونة" على الزر. الكود القديم كان بيبني "text_entities" وهو حقل
    مش موجود أصلاً في الـ API، فتليجرام كان بيتجاهله تمامًا ويظهر بس
    النص الاحتياطي (🔥) اللي اتحط مكان {ID} من غير ما يتحول لإيموجي بريميوم.
    """
    api_kwargs: dict = {}
    if style and style in VALID_BUTTON_STYLES:
        api_kwargs["style"] = style

    matches = list(PREMIUM_EMOJI_RE.finditer(text))
    if not matches:
        return text, api_kwargs

    # تليجرام بيسمح بإيموجي بريميوم واحد بس لكل زر (كأيقونة)، فبناخد أول
    # {ID} موجود في النص ونستخدمه.
    api_kwargs["icon_custom_emoji_id"] = matches[0].group(1)

    # نشيل كل صيغ {ID} من النص لأنها مش بتتحول لإيموجي جوه النص في الأزرار،
    # والإيموجي هيظهر تلقائي كأيقونة جنب النص.
    new_text = PREMIUM_EMOJI_RE.sub("", text)
    new_text = re.sub(r"\s{2,}", " ", new_text).strip()
    return new_text, api_kwargs


def _mk_btn(text: str, style: str | None = None, **kwargs) -> InlineKeyboardButton:
    """اختصار: يبني InlineKeyboardButton بلون + دعم {ID} لبريميوم."""
    new_text, api_kwargs = _button_text_and_api_kwargs(text, style)
    if api_kwargs:
        kwargs.setdefault("api_kwargs", {}).update(api_kwargs)
    return InlineKeyboardButton(new_text, **kwargs)


def welcome_keyboard(buttons):
    keyboard = []
    row = []
    for b in buttons:
        style = b.get("style", "success")
        if style not in VALID_BUTTON_STYLES:
            style = "success"
        row.append(_mk_btn(b["text"], style=style, url=b["url"]))
        if len(row) == 2:          # زرين جنب بعض في نفس الصف
            keyboard.append(row)
            row = []
    if row:                        # لو فضل زر لوحده (عدد فردي)
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def owner_panel_keyboard():
    s = load_settings()
    away_style = "success" if s["away_enabled"] else "danger"
    away_label = "🟢 وضع الغياب: مفعّل" if s["away_enabled"] else "🔴 وضع الغياب: معطّل"
    auto_style  = "success" if s.get("autoresponder_enabled") else "danger"
    auto_label  = "🟢 الرد التلقائي: مفعّل" if s.get("autoresponder_enabled") else "🔴 الرد التلقائي: معطّل"
    quick_style = "success" if s.get("quick_reply_enabled") else "danger"
    quick_label = "🟢 الرد السريع: مفعّل" if s.get("quick_reply_enabled") else "🔴 الرد السريع: معطّل"
    protect_style = "success" if s.get("protect_content_enabled") else "danger"
    protect_label = "🟢 حماية المحتوى: مفعّلة" if s.get("protect_content_enabled") else "🔴 حماية المحتوى: معطّلة"
    ai_style = "success" if s.get("ai_enabled") else "danger"
    ai_label = "🟢 الرد بالذكاء الاصطناعي: مفعّل" if s.get("ai_enabled") else "🔴 الرد بالذكاء الاصطناعي: معطّل"
    global_pin = _global_pin_data()
    global_pin_active = bool(
        global_pin.get("source_message_id") or global_pin.get("targets")
    )

    rows = [
        [
            _mk_btn("✏️ تعديل رسالة الترحيب", style="primary", callback_data="edit_welcome"),
            _mk_btn("🔗 تعديل أزرار الترحيب", style="primary", callback_data="edit_buttons"),
        ],
        [_mk_btn("👁️ عرض الإعدادات", style="primary", callback_data="view_settings")],
        [_mk_btn("📢 بث رسالة للجميع", style="primary", callback_data="broadcast")],
        [_mk_btn(
            "🗑 حذف رسائل آخر 24 ساعة",
            style="danger",
            callback_data="recent_delete_prompt",
        )],
        [_mk_btn(
            "🗑 حذف رسائل الغياب عند الجميع",
            style="danger",
            callback_data="away_delete_prompt",
        )],
        [
            _mk_btn("👥 قائمة المستخدمين", style="primary", callback_data="users_list:0"),
            _mk_btn("🚫 قائمة المحظورين", style="danger",  callback_data="banned_list"),
        ],
        [_mk_btn(away_label, style=away_style, callback_data="toggle_away")],
        [_mk_btn("✏️ تعديل رسالة الغياب", style="primary", callback_data="edit_away_msg")],
        [_mk_btn(f"🤖 الرد التلقائي — {auto_label[2:]}", style=auto_style, callback_data="auto_reply_menu")],
        [_mk_btn(f"⚡ الرد السريع — {quick_label[2:]}", style=quick_style, callback_data="quick_reply_menu")],
        [_mk_btn(f"🤖 الرد بالذكاء الاصطناعي — {ai_label[2:]}", style=ai_style, callback_data="ai_reply_menu")],
        [_mk_btn(protect_label, style=protect_style, callback_data="toggle_protect_content")],
        [_mk_btn("🔄 إعادة الإعدادات للأصل", style="danger", callback_data="reset_settings")],
    ]
    if global_pin_active:
        rows.insert(
            4,
            [_mk_btn(
                "🗑 حذف آخر رسالة عند المستخدمين",
                style="danger",
                callback_data="global_delete",
            )],
        )
    return InlineKeyboardMarkup(rows)


def make_rp(msg_id):
    return ReplyParameters(message_id=msg_id, allow_sending_without_reply=True)


# ═══════════════════════════════════════════════════════════════
#  Helpers لعرض تفاصيل المستخدمين
# ═══════════════════════════════════════════════════════════════

_user_info_cache: dict = {}   # uid → {"full_name", "username", "ts"}
_USER_CACHE_TTL = 600         # 10 دقائق


async def _fetch_user_info(ctx, uid: int) -> dict:
    """يجلب معلومات المستخدم كاملة مع كاش بسيط لتقليل استدعاءات get_chat."""
    now = time.time()
    cached = _user_info_cache.get(uid)
    if cached and now - cached.get("ts", 0) < _USER_CACHE_TTL:
        return cached
    info = {
        "full_name": None,
        "username": None,
        "bio": None,
        "photo_file_id": None,
        "ts": now,
    }
    try:
        chat = await ctx.bot.get_chat(uid)
        info["full_name"] = chat.full_name or (chat.first_name or "")
        info["username"]  = chat.username
        info["bio"] = getattr(chat, "bio", None)
        photo = getattr(chat, "photo", None)
        if photo:
            info["photo_file_id"] = getattr(photo, "big_file_id", None)
    except TelegramError:
        pass
    _user_info_cache[uid] = info
    return info


def _user_action_keyboard(uid: int, source_message_id: int | None = None):
    icon, label = user_status(uid)
    state = get_user_state(uid)
    if uid in load_banned():
        state_button = _mk_btn("✅ فك الحظر", style="success",
                               callback_data=f"do_unban:{uid}")
    else:
        state_button = _mk_btn("🚫 حظر", style="danger",
                               callback_data=f"do_ban:{uid}")

    mute_button = (
        _mk_btn("🔊 إلغاء الكتم", style="success", callback_data=f"unmute:{uid}")
        if state.get("muted_until", 0) > time.time()
        else _mk_btn("🔇 كتم 24 ساعة", style="primary", callback_data=f"mute:{uid}")
    )
    snooze_label = "✓ " + label if label.startswith("تأجيل") else "⏰ تأجيل"
    snooze_button = _mk_btn(
        snooze_label, style="success" if label.startswith("تأجيل") else "primary",
        callback_data=f"snooze_pick:{uid}",
    )
    pin_label = "📍 إلغاء التثبيت عندي" if state.get("pinned") else "📌 تثبيت عندي"
    rows = [
        [
            _mk_btn("👤 معلومات", style="primary", callback_data=f"user_card:{uid}"),
            state_button,
        ],
        [mute_button, snooze_button],
        [
            _mk_btn(pin_label, style="primary", callback_data=f"pin:{uid}"),
        ],
        [
            _mk_btn("🗑 حذف الكل", style="danger", callback_data=f"clear_prompt:{uid}"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def _user_card_text(uid: int, info: dict, heading: str = "👤 بطاقة المستخدم") -> str:
    icon, status = user_status(uid)
    stats = get_user_stats(uid)
    state = get_user_state(uid)
    bio = _safe(info.get("bio"), "لا يوجد")
    audits = [
        item for item in load_audit_log()
        if int(item.get("user_id", 0)) == int(uid)
    ][-3:]
    audit_lines = []
    for item in audits:
        details = str(item.get("details") or "").strip()
        suffix = f" — {html.escape(details)}" if details else ""
        audit_lines.append(
            f"• {html.escape(str(item.get('action', '')))}{suffix} — "
            f"{display_time(item.get('at', 0))}"
        )
    audit_text = "\n".join(audit_lines) or "لا يوجد"
    return (
        f"{heading}\n\n"
        f"الاسم: <b>{_safe(info.get('full_name'), 'مجهول')}</b>\n"
        f"اليوزر: {_safe('@' + info['username'] if info.get('username') else None)}\n"
        f"الآيدي: <code>{uid}</code>\n"
        f"البايو: {bio}\n\n"
        f"الحالة: {icon} <b>{html.escape(status)}</b>\n"
        f"📊 الرسائل: <b>{int(stats.get('message_count', 0))}</b>\n"
        f"آخر تواصل: {display_time(stats.get('last_contact', 0))}\n"
        f"آخر رد: {display_time(stats.get('last_reply', 0))}\n"
        f"📌 مثبت: {'نعم' if state.get('pinned') else 'لا'}\n\n"
        f"🧾 <b>آخر سجل:</b>\n{audit_text}"
    )


def _build_user_details_view(uid: int, info: dict):
    text = _user_card_text(uid, info, "👤 <b>تفاصيل المستخدم</b>")
    rows = []
    action_kb = _user_action_keyboard(uid)
    rows.extend(action_kb.inline_keyboard)
    if info.get("username"):
        rows.append([_mk_btn("💬 فتح المحادثة", style="primary",
                             url=f"https://t.me/{info['username']}")])
    rows.append([
        _mk_btn("👥 قائمة المستخدمين", style="primary", callback_data="users_list:0"),
        _mk_btn("🔙 اللوحة", style="primary", callback_data="back_panel"),
    ])
    return text, InlineKeyboardMarkup(rows)


async def _send_user_details(ctx, chat_id: int, uid: int, reply_to: int | None = None):
    info = await _fetch_user_info(ctx, uid)
    text, kb = _build_user_details_view(uid, info)
    kwargs = dict(chat_id=chat_id, parse_mode=ParseMode.HTML, reply_markup=kb)
    if reply_to:
        kwargs["reply_parameters"] = make_rp(reply_to)
    if info.get("photo_file_id"):
        sent = await ctx.bot.send_photo(
            photo=info["photo_file_id"], caption=text[:1024], **kwargs,
        )
    else:
        sent = await ctx.bot.send_message(text=text, **kwargs)
    if chat_id == OWNER_ID:
        record_message(uid, "owner", sent.message_id, "info_card")
    return sent


async def _refresh_user_card_message(query, ctx, uid: int):
    info = await _fetch_user_info(ctx, uid)
    text, kb = _build_user_details_view(uid, info)
    try:
        if getattr(query.message, "photo", None):
            await query.edit_message_caption(caption=text[:1024], reply_markup=kb,
                                              parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(text=text, reply_markup=kb,
                                          parse_mode=ParseMode.HTML)
    except TelegramError as e:
        logger.warning(f"تعذر تحديث بطاقة المستخدم {uid}: {e}")


async def _send_action_card(ctx, uid: int, forwarded_message_id: int):
    update_user_state(uid, last_forward_id=forwarded_message_id)
    info = await _fetch_user_info(ctx, uid)
    text = _user_card_text(uid, info, "📨 <b>رسالة جديدة من المستخدم</b>")
    try:
        card = await ctx.bot.send_message(
            OWNER_ID, text, parse_mode=ParseMode.HTML,
            reply_parameters=make_rp(forwarded_message_id),
            reply_markup=_user_action_keyboard(uid, forwarded_message_id),
        )
        record_message(uid, "owner", card.message_id, "action_card")
        return card
    except TelegramError as e:
        logger.error(f"فشل إرسال بطاقة إجراءات المستخدم {uid}: {e}")
        return None


def _cancel_snooze_jobs(job_queue, uid: int):
    if not job_queue:
        return
    for job in job_queue.get_jobs_by_name(f"{REMINDER_JOB_PREFIX}{uid}"):
        job.schedule_removal()


def _schedule_snooze(job_queue, uid: int, until: float):
    _cancel_snooze_jobs(job_queue, uid)
    if job_queue:
        job_queue.run_once(
            send_snooze_reminder,
            max(1, until - time.time()),
            data={"user_id": uid},
            name=f"{REMINDER_JOB_PREFIX}{uid}",
        )


async def send_snooze_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    data = getattr(ctx.job, "data", {}) or {}
    uid = int(data.get("user_id", 0))
    if not uid:
        return
    state = get_user_state(uid)
    if state.get("snoozed_until", 0) > time.time():
        _schedule_snooze(ctx.job_queue, uid, state["snoozed_until"])
        return
    update_user_state(uid, snoozed_until=0)
    append_audit(uid, "انتهاء التأجيل")
    info = await _fetch_user_info(ctx, uid)
    text = _user_card_text(uid, info, "💤 <b>حان وقت التذكير</b>")
    kb = InlineKeyboardMarkup([[
        _mk_btn("👤 فتح البطاقة", style="primary", callback_data=f"user_card:{uid}"),
        _mk_btn("⏰ تأجيل مرة أخرى", style="success", callback_data=f"snooze_pick:{uid}"),
    ]])
    try:
        reply_kwargs = {}
        if state.get("last_forward_id"):
            reply_kwargs["reply_parameters"] = make_rp(state["last_forward_id"])
        sent = await ctx.bot.send_message(
            OWNER_ID, text, parse_mode=ParseMode.HTML, reply_markup=kb,
            **reply_kwargs,
        )
        record_message(uid, "owner", sent.message_id, "snooze_reminder")
    except TelegramError as e:
        logger.error(f"فشل إرسال تذكير التأجيل {uid}: {e}")


def _clear_counts(uid: int) -> tuple[int, int]:
    return len(_record_ids(uid, "owner")), len(_record_ids(uid, "user"))


async def _delete_recorded_messages(ctx, uid: int) -> tuple[int, int]:
    records = load_message_records()
    bucket = records.get(_uid_key(uid), {})
    now = time.time()
    owner_ids = list(dict.fromkeys(_record_ids(uid, "owner")))
    user_ids = list(dict.fromkeys(_record_ids(uid, "user")))
    deleted_owner = deleted_user = 0

    for side, chat_id, ids in (
        ("owner", OWNER_ID, owner_ids),
        ("user", uid, user_ids),
    ):
        for message_id in ids:
            item = next(
                (x for x in bucket.get(side, []) if int(x.get("id", 0)) == message_id),
                {},
            )
            # Telegram يتجاهل ما مضى عليه أكثر من 48 ساعة؛ لا نرسل خطأ للمستخدم.
            if now - float(item.get("created_at", now)) > DELETE_WINDOW_SECONDS:
                continue
            try:
                await ctx.bot.delete_message(chat_id=chat_id, message_id=message_id)
                if side == "owner":
                    deleted_owner += 1
                else:
                    deleted_user += 1
            except TelegramError:
                pass

    clear_message_records(uid)
    return deleted_owner, deleted_user


def _target_user_from_owner_message(msg) -> int | None:
    replied = getattr(msg, "reply_to_message", None)
    if not replied:
        return None
    replied_id = replied.message_id
    if replied_id in msg_map:
        return int(msg_map[replied_id][0])
    return find_user_by_owner_message(replied_id)


async def _send_ban_confirmation(ctx, chat_id: int, uid: int, reply_to: int | None = None):
    return await _send_ban_confirmation_with_reason(
        ctx, chat_id, uid, reason="", reply_to=reply_to
    )


async def _send_ban_confirmation_with_reason(
    ctx, chat_id: int, uid: int, reason: str, reply_to: int | None = None
):
    info = await _fetch_user_info(ctx, uid)
    reason = (reason or "لم يتم تحديد سبب").strip()
    pending = ctx.user_data.setdefault("pending_bans", {})
    pending[str(uid)] = {"reason": reason}
    text = (
        f"⚠️ <b>تأكيد حظر المستخدم</b>\n\n"
        f"{_safe(info.get('full_name'), 'مجهول')} — <code>{uid}</code>\n"
        f"<b>سبب الحظر:</b> {html.escape(reason)}\n\n"
        "لن تصلك منه رسائل بعد الحظر. اختر مدة الحظر:"
    )
    rows = [
        [
            _mk_btn("1 ساعة", style="primary", callback_data=f"ban_pick:{uid}:1h"),
            _mk_btn("6 ساعات", style="primary", callback_data=f"ban_pick:{uid}:6h"),
            _mk_btn("12 ساعة", style="primary", callback_data=f"ban_pick:{uid}:12h"),
        ],
        [
            _mk_btn("يوم", style="primary", callback_data=f"ban_pick:{uid}:1d"),
            _mk_btn("3 أيام", style="primary", callback_data=f"ban_pick:{uid}:3d"),
            _mk_btn("7 أيام", style="primary", callback_data=f"ban_pick:{uid}:7d"),
        ],
        [
            _mk_btn("14 يوم", style="primary", callback_data=f"ban_pick:{uid}:14d"),
            _mk_btn("30 يوم", style="primary", callback_data=f"ban_pick:{uid}:30d"),
        ],
        [
            _mk_btn("♾️ دائم", style="danger", callback_data=f"ban_pick:{uid}:permanent"),
            _mk_btn("رجوع", style="primary", callback_data=f"user_card:{uid}"),
        ],
    ]
    kwargs = dict(
        chat_id=chat_id, text=text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows),
    )
    if reply_to:
        kwargs["reply_parameters"] = make_rp(reply_to)
    sent = await ctx.bot.send_message(**kwargs)
    record_message(uid, "owner", sent.message_id, "ban_confirmation")
    return sent


def _cancel_ban_expiry_jobs(job_queue, uid: int):
    if not job_queue:
        return
    for job in job_queue.get_jobs_by_name(f"{BAN_JOB_PREFIX}{uid}"):
        job.schedule_removal()


def _schedule_ban_expiry(job_queue, uid: int, expires_at: float | None):
    _cancel_ban_expiry_jobs(job_queue, uid)
    if job_queue and expires_at:
        job_queue.run_once(
            expire_ban,
            max(1, expires_at - time.time()),
            data={"user_id": uid},
            name=f"{BAN_JOB_PREFIX}{uid}",
        )


def _ban_duration_text(record: dict) -> str:
    expires_at = record.get("expires_at")
    if not expires_at:
        return "بدون انتهاء — حتى فك يدوي"
    remaining = _remaining_text(float(expires_at))
    return f"{remaining or 'ينتهي قريباً'} (حتى {display_time(float(expires_at))})"


async def _apply_ban(
    ctx, uid: int, reason: str = "", duration_key: str = "permanent"
):
    seconds, duration_label = BAN_OPTIONS.get(duration_key, BAN_OPTIONS["permanent"])
    now = time.time()
    expires_at = now + seconds if seconds else None
    reason = (reason or "لم يتم تحديد سبب").strip()
    records = load_ban_records()
    records[str(uid)] = {
        "user_id": int(uid),
        "reason": reason,
        "banned_at": now,
        "expires_at": expires_at,
        "duration_key": duration_key,
    }
    save_ban_records(records)
    update_user_state(uid, muted_until=0, snoozed_until=0)
    _cancel_snooze_jobs(ctx.job_queue, uid)
    _schedule_ban_expiry(ctx.job_queue, uid, expires_at)
    append_audit(
        uid,
        "حظر",
        f"السبب: {reason} | المدة: {duration_label}",
    )
    try:
        duration_text = (
            "بدون انتهاء — حتى فك يدوي"
            if not expires_at
            else f"حتى {display_time(expires_at)}"
        )
        notice = await ctx.bot.send_message(
            uid,
            f"🚫 <b>تم حظرك بسبب:</b> {html.escape(reason)}\n"
            f"مدة الحظر: {html.escape(duration_text)}",
            parse_mode=ParseMode.HTML,
        )
        record_message(uid, "user", notice.message_id, "ban_notice")
    except TelegramError:
        pass


async def _apply_unban(ctx, uid: int):
    records = load_ban_records()
    record = records.pop(str(uid), None)
    save_ban_records(records)
    _cancel_ban_expiry_jobs(ctx.job_queue, uid)
    details = ""
    if record:
        details = f"الحظر السابق — السبب: {record.get('reason', '—')}"
    append_audit(uid, "فك الحظر", details)
    try:
        notice = await ctx.bot.send_message(uid, "✅ تم رفع الحظر عنك، يمكنك التواصل مجدداً.")
        record_message(uid, "user", notice.message_id, "unban_notice")
    except TelegramError:
        pass


async def expire_ban(ctx: ContextTypes.DEFAULT_TYPE):
    data = getattr(ctx.job, "data", {}) or {}
    uid = int(data.get("user_id", 0))
    if not uid:
        return
    records = load_ban_records()
    record = records.get(str(uid))
    if not record:
        return
    expires_at = record.get("expires_at")
    if not expires_at:
        return
    if float(expires_at) > time.time():
        _schedule_ban_expiry(ctx.job_queue, uid, float(expires_at))
        return

    records.pop(str(uid), None)
    save_ban_records(records)
    append_audit(uid, "انتهاء الحظر", f"السبب: {record.get('reason', '—')}")
    try:
        notice = await ctx.bot.send_message(
            uid,
            "✅ انتهت مدة حظرك، يمكنك التواصل مع البوت مجدداً.",
        )
        record_message(uid, "user", notice.message_id, "ban_expired_notice")
    except TelegramError:
        pass


async def _apply_mute(ctx, uid: int):
    until = time.time() + 24 * 3600
    update_user_state(uid, muted_until=until)
    append_audit(uid, "كتم", "24 ساعة")


async def _toggle_pin(ctx, uid: int, message_id: int | None = None):
    state = get_user_state(uid)
    if state.get("pinned") and state.get("pinned_message_id"):
        try:
            await ctx.bot.unpin_chat_message(OWNER_ID, state["pinned_message_id"])
        except TelegramError:
            pass
        update_user_state(uid, pinned=False, pinned_message_id=None)
        append_audit(uid, "إلغاء التثبيت")
        return
    target_id = message_id
    if not target_id:
        owner_items = _record_ids(uid, "owner")
        target_id = owner_items[-1] if owner_items else None
    if not target_id:
        return
    try:
        await ctx.bot.pin_chat_message(OWNER_ID, target_id, disable_notification=True)
        update_user_state(uid, pinned=True, pinned_message_id=target_id)
        append_audit(uid, "تثبيت", f"رسالة {target_id}")
    except TelegramError as e:
        logger.warning(f"فشل تثبيت بطاقة المستخدم {uid}: {e}")


def _global_pin_data() -> dict:
    data = load_settings().get("global_pin")
    if not isinstance(data, dict):
        return {"source_message_id": None, "targets": {}, "updated_at": 0}
    targets = data.get("targets")
    data["targets"] = targets if isinstance(targets, dict) else {}
    return data


def _save_global_pin(data: dict):
    settings = load_settings()
    settings["global_pin"] = data
    save_settings(settings)


async def _delete_global_message(ctx) -> tuple[int, int, int]:
    """
    يحذف آخر رسالة عامة من محادثات المستخدمين، مع محاولة إلغاء تثبيتها أولاً.
    النتيجة: (تم الحذف، فشل الحذف، إجمالي النسخ المسجلة).
    """
    data = _global_pin_data()
    targets = dict(data.get("targets", {}))
    remaining = {}
    deleted = failed = 0
    for uid_s, message_id in targets.items():
        try:
            uid = int(uid_s)
            mid = int(message_id)
        except (TypeError, ValueError):
            failed += 1
            continue
        try:
            await ctx.bot.unpin_chat_message(chat_id=uid, message_id=mid)
        except TelegramError:
            # حذف الرسالة نفسها قد ينجح حتى لو لم يعد التثبيت موجوداً.
            pass
        try:
            await ctx.bot.delete_message(chat_id=uid, message_id=mid)
            remove_recorded_message(uid, "user", mid)
            deleted += 1
        except TelegramError:
            remaining[_uid_key(uid)] = mid
            failed += 1

    # نحتفظ فقط بالنسخ التي تعذر حذفها حتى يمكن إعادة المحاولة من الزر.
    _save_global_pin({
        "source_message_id": data.get("source_message_id") if remaining else None,
        "targets": remaining,
        "updated_at": time.time(),
    })
    return deleted, failed, len(targets)


async def _delete_recent_messages(ctx) -> tuple[int, int, int, int, int]:
    """
    يحذف كل الرسائل المسجلة خلال آخر 24 ساعة من شات المالك وشات الأعضاء.
    النتيجة: (حذف المالك، حذف الأعضاء، فشل المالك، فشل الأعضاء، الإجمالي).

    تُضاف نسخة التثبيت العامة ومصدرها إلى البحث حتى لو كان المالك حذف
    المصدر يدويًا من شاته، وبقيت النسخ عند الأعضاء.
    """
    cutoff = time.time() - RECENT_DELETE_WINDOW_SECONDS
    records = load_message_records()
    candidates = {}

    for uid_s, bucket in records.items():
        try:
            uid = int(uid_s)
        except (TypeError, ValueError):
            continue
        for side in ("owner", "user"):
            chat_id = OWNER_ID if side == "owner" else uid
            for item in bucket.get(side, []):
                try:
                    created_at = float(item.get("created_at", 0))
                    message_id = int(item.get("id", 0))
                except (TypeError, ValueError):
                    continue
                if message_id and created_at >= cutoff:
                    candidates.setdefault(
                        (chat_id, message_id), (uid, side)
                    )

    global_data = _global_pin_data()
    try:
        global_updated_at = float(global_data.get("updated_at", 0))
    except (TypeError, ValueError):
        global_updated_at = 0
    global_targets = dict(global_data.get("targets", {}))

    # النسخ العامة التي أُنشئت خلال آخر 24 ساعة، بما فيها النسخ القديمة
    # التي قد لا تكون موجودة في message_records.json.
    if global_updated_at >= cutoff:
        for uid_s, message_id in global_targets.items():
            try:
                uid = int(uid_s)
                mid = int(message_id)
            except (TypeError, ValueError):
                continue
            candidates.setdefault((uid, mid), (uid, "user"))

        try:
            source_id = int(global_data.get("source_message_id") or 0)
        except (TypeError, ValueError):
            source_id = 0
        if source_id:
            candidates.setdefault((OWNER_ID, source_id), (None, "owner"))

    deleted_owner = deleted_user = failed_owner = failed_user = 0
    successful = set()
    for (chat_id, message_id), (record_uid, side) in candidates.items():
        try:
            await ctx.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id,
            )
            successful.add((chat_id, message_id))
            if side == "owner":
                deleted_owner += 1
            else:
                deleted_user += 1
            if record_uid is not None:
                remove_recorded_message(record_uid, side, message_id)
        except TelegramError:
            if side == "owner":
                failed_owner += 1
            else:
                failed_user += 1

    # لا نفقد روابط النسخ التي تعذر حذفها؛ يمكن للمحاولة التالية التعامل معها.
    remaining_targets = {}
    for uid_s, message_id in global_targets.items():
        try:
            key = (int(uid_s), int(message_id))
        except (TypeError, ValueError):
            remaining_targets[uid_s] = message_id
            continue
        if key not in successful:
            remaining_targets[uid_s] = message_id

    source_id = global_data.get("source_message_id")
    try:
        source_key = (OWNER_ID, int(source_id)) if source_id else None
    except (TypeError, ValueError):
        source_key = None
    source_remaining = bool(source_id) and source_key not in successful
    _save_global_pin({
        "source_message_id": source_id if source_remaining else None,
        "targets": remaining_targets,
        "updated_at": global_data.get("updated_at", 0)
        if remaining_targets or source_remaining else 0,
    })

    return (
        deleted_owner,
        deleted_user,
        failed_owner,
        failed_user,
        len(candidates),
    )


async def _delete_away_messages(ctx) -> tuple[int, int, int]:
    """
    يحذف رسائل وضع الغياب المسجلة عند الأعضاء خلال آخر 48 ساعة.
    يعتمد على kind=away_reply، لذلك لا يهم إن تغيّر نص رسالة الغياب لاحقًا.
    """
    cutoff = time.time() - DELETE_WINDOW_SECONDS
    deleted = failed = total = 0
    for uid_s, bucket in load_message_records().items():
        try:
            uid = int(uid_s)
        except (TypeError, ValueError):
            continue
        for item in bucket.get("user", []):
            if item.get("kind") != "away_reply":
                continue
            try:
                created_at = float(item.get("created_at", 0))
                message_id = int(item.get("id", 0))
            except (TypeError, ValueError):
                continue
            if not message_id or created_at < cutoff:
                continue
            total += 1
            try:
                await ctx.bot.delete_message(
                    chat_id=uid,
                    message_id=message_id,
                )
                remove_recorded_message(uid, "user", message_id)
                deleted += 1
            except TelegramError:
                failed += 1
    return deleted, failed, total


async def _sync_global_pin_for_user(ctx, uid: int) -> bool:
    """يرسل آخر رسالة مثبّتة لمستخدم جديد ويثبت النسخة عنده."""
    if uid == OWNER_ID or uid in load_banned():
        return False
    data = _global_pin_data()
    source_message_id = data.get("source_message_id")
    if not source_message_id:
        return False
    key = _uid_key(uid)
    if key in data.get("targets", {}):
        return True
    try:
        sent = await ctx.bot.copy_message(
            chat_id=uid,
            from_chat_id=OWNER_ID,
            message_id=int(source_message_id),
            **protect_kwargs(uid),
        )
        sent_id = int(sent.message_id)
        record_message(uid, "user", sent_id, "global_pin")
        try:
            await ctx.bot.pin_chat_message(
                chat_id=uid,
                message_id=sent_id,
                disable_notification=True,
            )
        except TelegramError as e:
            logger.warning(f"تعذر تثبيت الرسالة العامة عند المستخدم الجديد {uid}: {e}")
        data.setdefault("targets", {})[key] = sent_id
        _save_global_pin(data)
        return True
    except TelegramError as e:
        logger.warning(f"تعذر إرسال الرسالة المثبتة للمستخدم الجديد {uid}: {e}")
        return False


async def _broadcast_and_pin_message(ctx, source_message_id: int) -> tuple[int, int, int]:
    """
    ينسخ رسالة المالك إلى المستخدمين غير المحظورين ثم يحاول تثبيت النسخ.
    النتيجة: (تم التثبيت، فشل التثبيت/الإرسال، عدد المتخطين).
    """
    # استبدال التثبيت السابق يحذف نسخه القديمة حتى لا تتراكم عند المستخدمين.
    await _delete_global_message(ctx)
    users = sorted(load_users() - load_banned() - {OWNER_ID})
    targets = {}
    pinned = failed = 0
    for uid in users:
        try:
            sent = await ctx.bot.copy_message(
                chat_id=uid,
                from_chat_id=OWNER_ID,
                message_id=source_message_id,
                **protect_kwargs(uid),
            )
            sent_id = int(sent.message_id)
            # نسجل النسخة حتى يحذفها /clear مع بقية محادثة المستخدم.
            record_message(uid, "user", sent_id, "global_pin")
            targets[_uid_key(uid)] = sent_id
            try:
                await ctx.bot.pin_chat_message(
                    chat_id=uid,
                    message_id=sent_id,
                    disable_notification=True,
                )
                pinned += 1
            except TelegramError as e:
                logger.warning(f"تعذر تثبيت الرسالة العامة عند {uid}: {e}")
                failed += 1
        except TelegramError as e:
            logger.warning(f"تعذر إرسال الرسالة العامة إلى {uid}: {e}")
            failed += 1

    _save_global_pin({
        "source_message_id": int(source_message_id),
        "targets": targets,
        "updated_at": time.time(),
    })
    return pinned, failed, len(users)


async def send_owner_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    يرسل لوحة تحكم المالك بشكل مقاوم للأعطال:
    - لو فشل بناء/إرسال الكيبورد الملوّن (api_kwargs style) لأي سبب،
      يحاول إرسالها بكيبورد عادي بدون ألوان بدل ما يفشل بصمت.
    - لو فشلت حتى المحاولة البديلة، يبلغ المالك بنص الخطأ نفسه
      بدل ما يختفي في لوجات Railway فقط.
    """
    try:
        await update.effective_message.reply_text(
            "⚙️ لوحة تحكم البوت\nمرحباً بك 👋",
            reply_markup=owner_panel_keyboard(),
        )
    except TelegramError as e:
        logger.error(f"فشل إرسال لوحة المالك بالكيبورد الملوّن: {e}")
        try:
            s = load_settings()
            plain_rows = [
                [InlineKeyboardButton("✏️ تعديل رسالة الترحيب", callback_data="edit_welcome"),
                 InlineKeyboardButton("🔗 تعديل أزرار الترحيب",  callback_data="edit_buttons")],
                [InlineKeyboardButton("👁️ عرض الإعدادات", callback_data="view_settings")],
                [InlineKeyboardButton("📢 بث رسالة للجميع", callback_data="broadcast")],
                [InlineKeyboardButton(
                    "🗑 حذف رسائل آخر 24 ساعة",
                    callback_data="recent_delete_prompt",
                )],
                [InlineKeyboardButton(
                    "🗑 حذف رسائل الغياب عند الجميع",
                    callback_data="away_delete_prompt",
                )],
                [InlineKeyboardButton("👥 قائمة المستخدمين", callback_data="users_list:0"),
                 InlineKeyboardButton("🚫 قائمة المحظورين", callback_data="banned_list")],
                [InlineKeyboardButton(
                    "🟢 وضع الغياب: مفعّل" if s["away_enabled"] else "🔴 وضع الغياب: معطّل",
                    callback_data="toggle_away")],
                [InlineKeyboardButton("✏️ تعديل رسالة الغياب", callback_data="edit_away_msg")],
                [InlineKeyboardButton(
                    "🟢 الرد التلقائي: مفعّل" if s.get("autoresponder_enabled") else "🔴 الرد التلقائي: معطّل",
                    callback_data="auto_reply_menu")],
                [InlineKeyboardButton(
                    "🟢 الرد السريع: مفعّل" if s.get("quick_reply_enabled") else "🔴 الرد السريع: معطّل",
                    callback_data="quick_reply_menu")],
                [InlineKeyboardButton(
                    "🟢 حماية المحتوى: مفعّلة" if s.get("protect_content_enabled") else "🔴 حماية المحتوى: معطّلة",
                    callback_data="toggle_protect_content")],
                [InlineKeyboardButton("🔄 إعادة الإعدادات للأصل", callback_data="reset_settings")],
            ]
            if _global_pin_data().get("source_message_id") or _global_pin_data().get("targets"):
                plain_rows.insert(
                    4,
                    [InlineKeyboardButton(
                        "🗑 حذف آخر رسالة عند المستخدمين",
                        callback_data="global_delete",
                    )],
                )
            plain_kb = InlineKeyboardMarkup(plain_rows)
            await update.effective_message.reply_text(
                "⚙️ لوحة تحكم البوت\nمرحباً بك 👋",
                reply_markup=plain_kb,
            )
        except TelegramError as e2:
            logger.error(f"فشلت المحاولة البديلة كمان: {e2}")
            try:
                await update.effective_message.reply_text(f"⚠️ تعذّر فتح لوحة التحكم:\n<code>{e2}</code>")
            except TelegramError:
                pass

# ═══════════════════════════════════════════════════════════════
#  إيموجي بريميوم بصيغة {ID} داخل نصوص الترحيب/الغياب
# ═══════════════════════════════════════════════════════════════

PREMIUM_EMOJI_RE = re.compile(r"\{(\d{5,})\}")
PREMIUM_EMOJI_FALLBACK = "🔥"  # الإيموجي الاحتياطي الظاهر لغير المشتركين في بريميوم

def render_premium_emojis(text: str) -> str:
    """
    يحوّل أي {ID} داخل النص إلى وسم <tg-emoji emoji-id="ID">🔥</tg-emoji>
    جاهز للإرسال بـ parse_mode=HTML. استخرج الـ ID من /emoji_id.
    مثال: "أهلاً بيك {5386419798677874707} في البوت"
    """
    return PREMIUM_EMOJI_RE.sub(
        lambda m: f'<tg-emoji emoji-id="{m.group(1)}">{PREMIUM_EMOJI_FALLBACK}</tg-emoji>',
        text,
    )

# ═══════════════════════════════════════════════════════════════
#  الرد التلقائي بالكلمات المسجلة
# ═══════════════════════════════════════════════════════════════

def find_auto_reply(text: str):
    """
    يبحث في الكلمات المسجّلة عن أول كلمة موجودة (كنص فرعي) داخل text
    (وحدها، ضمن جملة، أو ككابشن على وسيط). يُرجع dict {"keyword","reply"}
    أو None لو الميزة معطّلة أو ما فيش تطابق.
    """
    if not text:
        return None
    s = load_settings()
    if not s.get("autoresponder_enabled"):
        return None
    low = text.lower()
    for item in s.get("auto_replies", []):
        kw = (item.get("keyword") or "").strip()
        if kw and kw.lower() in low:
            return item
    return None


_GROQ_CACHED_MODEL = None

def _sync_call_ai(prompt: str, system_prompt: str, api_key: str, model: str, base_url: str) -> str:
    """استدعاء واجهة الذكاء الاصطناعي مع دعم الاستعلام الديناميكي عن الموديلات والتبديل التلقائي عند 404."""
    global _GROQ_CACHED_MODEL
    if not api_key:
        raise ValueError("مفتاح API غير متوفر.")
    api_key = api_key.strip()
    
    is_groq = api_key.startswith("gsk_")
    is_openrouter = api_key.startswith("sk-or-")

    if is_groq:
        if "openai.com" in base_url:
            base_url = "https://api.groq.com/openai/v1"
        
        # قائمة الموديلات التلقائية المتاحة لحسابات مطوري Groq
        groq_candidates = [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "groq/compound",
            "qwen/qwen3.8-27b",
        ]
        
        # محاولة جلب الموديلات المصرح بها للمفتاح الحالي مباشرة من Groq إذا لم تكن مخزنة مؤقتاً
        if not _GROQ_CACHED_MODEL:
            try:
                models_url = base_url.rstrip("/") + "/models"
                m_req = urllib.request.Request(
                    models_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }
                )
                with urllib.request.urlopen(m_req, timeout=5) as m_resp:
                    m_data = json.loads(m_resp.read().decode("utf-8"))
                    chat_models = [
                        m["id"] for m in m_data.get("data", [])
                        if "id" in m and not any(x in m["id"].lower() for x in ["whisper", "guard", "tts", "embedding", "orpheus", "canopy"])
                    ]
                    if chat_models:
                        # تقديم الموديلات المتوفرة في حساب المستخدم
                        ordered = [m for m in groq_candidates if m in chat_models]
                        for cm in chat_models:
                            if cm not in ordered:
                                ordered.append(cm)
                        groq_candidates = ordered
                        _GROQ_CACHED_MODEL = groq_candidates[0]
            except Exception as e:
                logger.warning(f"Dynamic Groq model lookup skipped: {e}")

        models_to_try = []
        if _GROQ_CACHED_MODEL:
            models_to_try.append(_GROQ_CACHED_MODEL)
        # إذا قام المالك بتعيين موديل خاص ليس قديماً أو غير مدعوم
        if model and not any(old in model.lower() for old in ["gpt-4", "gpt-3", "llama-3.1", "llama-3.3"]):
            if model not in models_to_try:
                models_to_try.insert(0, model)
        for c in groq_candidates:
            if c not in models_to_try:
                models_to_try.append(c)

    elif is_openrouter:
        if "openai.com" in base_url:
            base_url = "https://openrouter.ai/api/v1"
        models_to_try = [model] if (model and not model.startswith("gpt-")) else ["google/gemini-2.0-flash-001"]
    else:
        models_to_try = [model or "gpt-4o-mini"]

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    last_err = None
    for current_model in models_to_try:
        payload = {
            "model": current_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                _GROQ_CACHED_MODEL = current_model
                return res_data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            logger.error(f"AI API HTTP Error {e.code} for model {current_model}: {err_msg}")
            last_err = f"خطأ من مزود الذكاء الاصطناعي ({e.code}): {err_msg}"
            # إذا كان الخطأ 404 (الموديل غير متاح أو غير موجود لهذا الحساب)، نجرّب الموديل التالي تلقائياً
            if e.code == 404:
                continue
            raise RuntimeError(last_err)
        except Exception as e:
            logger.error(f"AI Call error for model {current_model}: {e}")
            last_err = str(e)
            continue

    if last_err:
        raise RuntimeError(last_err)
    raise RuntimeError("تعذر استلام رد من مزود الذكاء الاصطناعي.")

async def call_ai_service(prompt: str) -> str:
    """استدعاء غير متزامن للذكاء الاصطناعي بناءً على إعدادات المالك."""
    s = load_settings()
    api_key = s.get("ai_api_key", "").strip() or os.environ.get("AI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    system_prompt = (
        s.get("ai_instructions", DEFAULT_AI_INSTRUCTIONS).strip()
        + "\n\n"
        "تنسيق الإرسال الإلزامي: أعد النص بصيغة Telegram HTML فقط، "
        "ولا تستخدم Markdown أو ```، ويمكنك استخدام <b> و<i> و<u> و<s> "
        "و<tg-spoiler> و<code> و<pre> و<blockquote> والروابط عند الحاجة."
    )
    model = s.get("ai_model", DEFAULT_AI_MODEL)
    base_url = s.get("ai_base_url", DEFAULT_AI_BASE_URL)
    import asyncio
    return await asyncio.to_thread(_sync_call_ai, prompt, system_prompt, api_key, model, base_url)


_TELEGRAM_HTML_TAG_RE = re.compile(
    r"</?(?:b|strong|i|em|u|ins|s|strike|del|tg-spoiler|code|pre|"
    r"blockquote|tg-emoji)(?:\s[^>]*)?>",
    re.IGNORECASE,
)


def prepare_ai_telegram_html(text: str) -> str:
    """ينظف رد النموذج ويجعله قابلاً للإرسال بتنسيق Telegram HTML."""
    text = (text or "").strip()
    text = re.sub(r"^\s*```(?:html|HTML)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text).strip()
    if not text:
        return "عذراً، لم يصل رد من الذكاء الاصطناعي."

    # لو رجع النموذج Markdown رغم التعليمات، نحافظ على أبسط تنسيقات Markdown.
    if not _TELEGRAM_HTML_TAG_RE.search(text):
        text = html.escape(text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
        text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
        text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
        text = re.sub(
            r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
            r'<a href="\2">\1</a>',
            text,
        )
    return render_premium_emojis(text)


async def send_ai_reply_to_user(ctx, msg, text: str, user_id: int):
    """يرسل الرد بتنسيق HTML، مع fallback آمن إذا أرسل النموذج وسمًا غير صالح."""
    formatted = prepare_ai_telegram_html(text)
    try:
        return await msg.reply_text(
            formatted,
            parse_mode=ParseMode.HTML,
            **protect_kwargs(user_id),
        )
    except TelegramError as e:
        logger.warning(f"تعذر إرسال رد الذكاء الاصطناعي بتنسيق HTML: {e}")
        return await msg.reply_text(
            text,
            **protect_kwargs(user_id),
        )


def auto_reply_menu_view():
    s = load_settings()
    items = s.get("auto_replies", [])
    enabled = s.get("autoresponder_enabled", False)
    status = "🟢 مفعّل" if enabled else "🔴 معطّل"

    lines = [
        f"🤖 <b>الرد التلقائي على الكلمات</b>\n",
        f"الحالة: {status}\n",
        "عند التفعيل: لو المستخدم بعت كلمة مسجّلة (وحدها، ضمن جملة، "
        "أو في كابشن صورة)، هيرد عليه البوت تلقائياً بالرد المحفوظ، "
        "وهتوصلك رسالة توضّح إن الرد اتبعت.\n",
    ]
    rows = []
    if items:
        lines.append("📋 <b>الكلمات المسجّلة:</b>")
        for i, item in enumerate(items):
            kw = item.get("keyword", "")
            rp = item.get("reply", "")
            lines.append(f"{i+1}. <b>{kw}</b> ⬅️ {rp}")
            rows.append([_mk_btn(f"🗑️ حذف: {kw}"[:40], style="danger",
                                 callback_data=f"auto_reply_del:{i}")])
    else:
        lines.append("لا يوجد كلمات مسجّلة حالياً.")

    rows.insert(0, [_mk_btn("➕ إضافة كلمة جديدة", style="primary",
                            callback_data="auto_reply_add")])
    rows.insert(1, [_mk_btn(
        "🔴 تعطيل الرد التلقائي" if enabled else "🟢 تفعيل الرد التلقائي",
        style="danger" if enabled else "success",
        callback_data="auto_reply_toggle")])
    rows.append([_mk_btn("🔙 اللوحة", style="primary", callback_data="back_panel")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


def ai_reply_menu_view():
    s = load_settings()
    enabled = s.get("ai_enabled", False)
    status = "🟢 مفعّل" if enabled else "🔴 معطّل"
    key = s.get("ai_api_key", "").strip() or os.environ.get("AI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    key_status = f"✅ مضبوط (...{key[-4:]})" if key else "⚠️ غير مدخل"
    model = s.get("ai_model", DEFAULT_AI_MODEL)
    inst = str(s.get("ai_instructions", DEFAULT_AI_INSTRUCTIONS) or "")
    # Telegram يرفض تعديل الرسالة إذا تجاوز النص 4096 حرفاً. نعرض معاينة
    # قصيرة هنا فقط، مع بقاء الـ System Prompt الكامل محفوظاً ويُستخدم فعلياً.
    escaped_inst = html.escape(inst)
    inst_preview = escaped_inst[:1800]
    if len(escaped_inst) > 1800:
        inst_preview += "\n… (تم اختصار المعاينة؛ التعليمات الكاملة محفوظة)"

    text = (
        "🤖 <b>الرد بالذكاء الاصطناعي</b>\n\n"
        f"• <b>الحالة:</b> {status}\n"
        f"• <b>المفتاح (API Key):</b> {key_status}\n"
        f"• <b>الموديل:</b> <code>{model}</code>\n\n"
        "📝 <b>التعليمات المكتوبة (System Prompt):</b>\n"
        f"<i>{inst_preview}</i>\n\n"
        "💡 عند التفعيل: سيقوم الذكاء الاصطناعي بالرد فوراً على رسائل المستخدمين وفق هذه التعليمات، مع إشعارك بالرد."
    )
    kb = InlineKeyboardMarkup([
        [_mk_btn("🔴 تعطيل الذكاء الاصطناعي" if enabled else "🟢 تفعيل الذكاء الاصطناعي",
                 style="danger" if enabled else "success", callback_data="ai_reply_toggle")],
        [_mk_btn("✏️ تعديل التعليمات (Prompt)", style="primary", callback_data="ai_reply_edit_prompt")],
        [_mk_btn("🔑 تعديل مفتاح API Key", style="primary", callback_data="ai_reply_edit_key")],
        [_mk_btn("⚙️ تغيير اسم الموديل", style="primary", callback_data="ai_reply_edit_model")],
        [_mk_btn("🔙 اللوحة", style="primary", callback_data="back_panel")],
    ])
    return text, kb

def quick_reply_menu_view():
    s = load_settings()
    enabled = s.get("quick_reply_enabled", False)
    status = "🟢 مفعّل" if enabled else "🔴 معطّل"
    text = (
        f"⚡ <b>الرد السريع</b>\n\n"
        f"الحالة: {status}\n\n"
        f"عند التفعيل: أي رسالة يبعتها المستخدم (أو حتى أمر /start) "
        f"هيتم الرد عليها فقط بالنص المحفوظ هنا، بدل رسالة الترحيب أو "
        f"رسالة الغياب أو الرد التلقائي.\n\n"
        f"📝 <b>النص الحالي:</b>\n{s.get('quick_reply_msg', '')}"
    )
    kb = InlineKeyboardMarkup([
        [_mk_btn("🔴 تعطيل الرد السريع" if enabled else "🟢 تفعيل الرد السريع",
                style="danger" if enabled else "success",
                callback_data="quick_reply_toggle")],
        [_mk_btn("✏️ تعديل نص الرد السريع", style="primary", callback_data="quick_reply_edit")],
        [_mk_btn("🔙 اللوحة", style="primary", callback_data="back_panel")],
    ])
    return text, kb

# ═══════════════════════════════════════════════════════════════
#  أدوات معالجة أمر ق
# ═══════════════════════════════════════════════════════════════
def utf16_len(s: str) -> int:
    """طول النص بـ UTF-16 code units — نفس حساب تيليجرام للـ entity offset."""
    return len(s.encode("utf-16-le")) // 2

def get_q_prefix(text: str):
    """
    إن كان text يبدأ بـ 'ق' متبوعةً بمسافة أو وحدها يُعيد البادئة التي ستُحذف، وإلا None.
    البادئة = مسافات أمامية + 'ق' + المسافة بعدها.
    "قكلام" بدون مسافة → None (تُتجاهل).
    """
    stripped = text.lstrip()
    if not stripped.startswith("ق"):
        return None
        
    rest = stripped[1:]  # ما بعد 'ق'
    
    # يجب أن يكون ما بعد 'ق' إما مسافة أو لا شيء
    if rest and not rest.startswith(" "):
        return None
        
    leading = text[: len(text) - len(stripped)]
    space   = " " if rest.startswith(" ") else ""
    return leading + "ق" + space

def shift_entities(prefix: str, text: str, entities):
    """
    يحذف prefix من بداية text ويُصحّح offsets الـ entities بـ UTF-16.
    يبني MessageEntity بـ constructor مباشر (لا de_json، لا bot=None).
    يعيد (new_text, new_entities | None).
    """
    rc  = len(prefix)          # remove chars (Python)
    new_text = text[rc:]
    new_text_u16_len = utf16_len(new_text)  # طول النص الجديد بـ UTF-16

    if not entities:
        return new_text, None

    pfx_u16_len = utf16_len(prefix)
    result = []
    
    for e in entities:
        off = e.offset - pfx_u16_len
        lng = e.length
        
        # محذوف بالكامل
        if off + lng <= 0:
            continue                         
            
        if off < 0:
            lng = lng + off             # قلّص من البداية
            off = 0
            
        # قلّص من النهاية إذا تجاوزت حدود النص الجديد
        if off >= new_text_u16_len:
            continue
            
        if off + lng > new_text_u16_len:
            lng = new_text_u16_len - off
    
        if lng <= 0:
            continue
            
        kw = {"type": e.type, "offset": off, "length": lng}
        if e.url:             kw["url"]             = e.url
        if e.user:            kw["user"]            = e.user
        if e.language:        kw["language"]        = e.language
        if e.custom_emoji_id: kw["custom_emoji_id"] = e.custom_emoji_id
        
        result.append(MessageEntity(**kw))
        
    return new_text, result


# ═══════════════════════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if chat.type in ("group", "supergroup"):
        await update.message.reply_text(
            "اضغط الزر للتواصل بالخاص 👇",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("تواصل بالخاص 💬",
                                     url=f"https://t.me/{ctx.bot.username}")
            ]]),
        )
        return

    if user.id == OWNER_ID:
        await send_owner_panel(update, ctx)
        return

    users = load_users(); users.add(user.id); save_users(users)
    # نسجل أمر /start نفسه حتى يدخل في حذف المحادثة لاحقاً.
    record_message(user.id, "user", update.message.message_id, "start")
    s = load_settings()
    if s.get("quick_reply_enabled"):
        welcome_sent = await update.message.reply_text(
            render_premium_emojis(s.get("quick_reply_msg", DEFAULT_QUICK_REPLY_MSG)),
            parse_mode=ParseMode.HTML,
            **protect_kwargs(user.id),
        )
    else:
        welcome_text = s["welcome"].replace("{user_link}", user_mention(user)).replace("{owner_id}", str(OWNER_ID))
        welcome_text = render_premium_emojis(welcome_text)
        welcome_sent = await update.message.reply_text(
            welcome_text,
            reply_markup=welcome_keyboard(s["buttons"]),
            parse_mode=ParseMode.HTML,
            **protect_kwargs(user.id),
        )
    record_message(user.id, "user", welcome_sent.message_id, "welcome")
    # لو المالك مثبت رسالة عامة حالياً، يحصل المستخدم الجديد على نسخته
    # وتثبيتها تلقائياً مثل المستخدمين المسجلين قبل كده.
    await _sync_global_pin_for_user(ctx, user.id)
    uname    = f"@{user.username}" if user.username else "لا يوجد"
    join_msg = await ctx.bot.send_message(
        OWNER_ID,
        f"دخل شخص إلى البوت 👤\n\n"
        f"اسمه: {user.full_name} 🗣️\n"
        f"معرفه: {uname} 🌀\n"
        f"ايديه: <code>{user.id}</code> 🆔",
        parse_mode=ParseMode.HTML,
    )
    msg_map[join_msg.message_id] = (user.id, None)
    record_message(user.id, "owner", join_msg.message_id, "join_notice")
    save_msg_map(msg_map)

# ═══════════════════════════════════════════════════════════════
#  "بدء التشغيل" — نص بديل يفتح لوحة تحكم المالك في الخاص
#  (احتياطي في حال /start ما بيوصلش بسبب حظر أوامر قديم أو أي مشكلة مشابهة)
# ═══════════════════════════════════════════════════════════════

async def owner_panel_by_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_owner_panel(update, ctx)

# ═══════════════════════════════════════════════════════════════
#  تحويل رسائل المستخدمين للمالك
# ═══════════════════════════════════════════════════════════════

async def handle_user_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg  = update.effective_message

    users = load_users(); users.add(user.id); save_users(users)

    # ══ معالجة تعديل الرسالة ══════════════════════════════════
    if update.edited_message:
        # ابحث عن الرسالة المحوّلة في msg_map وعدّلها عند المالك
        edited_msg_id = msg.message_id
        for fwd_id, (uid, user_msg_id) in list(msg_map.items()):
            if uid == user.id and user_msg_id == edited_msg_id:
                try:
                    if msg.text:
                        await ctx.bot.edit_message_text(
                            chat_id=OWNER_ID,
                            message_id=fwd_id,
                            text=f"✏️ [تم التعديل]\n{msg.text}",
                        )
                    else:
                        # وسيط مع كابشن
                        new_caption = f"✏️ [تم التعديل]\n{msg.caption or ''}"
                        await ctx.bot.edit_message_caption(
                            chat_id=OWNER_ID,
                            message_id=fwd_id,
                            caption=new_caption,
                        )
                except TelegramError as e:
                    logger.warning(f"edit forward failed: {e}")
                    # إذا فشل التعديل (مثلاً رسالة محوّلة لا تقبل تعديل)، أرسل رسالة جديدة
                    try:
                        note = f"✏️ عدّل {user_mention(user)} رسالته:\n\n{msg.text or msg.caption or '[وسيط]'}"
                        await ctx.bot.send_message(
                            OWNER_ID, note, parse_mode=ParseMode.HTML,
                            reply_parameters=make_rp(fwd_id),
                        )
                    except TelegramError:
                        pass
                break
        return  # لا تُرسل رسالة جديدة عند التعديل

    await _fetch_user_info(ctx, user.id)
    current_stats = get_user_stats(user.id)
    update_user_stats(
        user.id,
        message_count=int(current_stats.get("message_count", 0)) + 1,
        last_contact=time.time(),
    )
    record_message(user.id, "user", msg.message_id, "incoming")

    # الحظر: لا رد ولا تحويل ولا بطاقة.
    if user.id in load_banned():
        return

    # الكتم: الرسائل تصل للبوت لكن تختفي بصمت من جهة المالك.
    if get_user_state(user.id).get("muted_until", 0) > time.time():
        return

    s = load_settings()

    # ══ الرد السريع: أولوية قصوى — يرد بنص واحد ثابت على أي رسالة ══
    if s.get("quick_reply_enabled"):
        quick_sent = await msg.reply_text(
            render_premium_emojis(s.get("quick_reply_msg", DEFAULT_QUICK_REPLY_MSG)),
            parse_mode=ParseMode.HTML,
            **protect_kwargs(user.id),
        )
        record_message(user.id, "user", quick_sent.message_id, "reception")
        fwd = await ctx.bot.forward_message(
            chat_id=OWNER_ID, from_chat_id=msg.chat_id, message_id=msg.message_id,
        )
        msg_map[fwd.message_id] = (user.id, msg.message_id)
        record_message(user.id, "owner", fwd.message_id, "forward")
        await _send_action_card(ctx, user.id, fwd.message_id)
        save_msg_map(msg_map)
        return

    # ══ الرد التلقائي بكلمة مسجّلة (نص وحده / ضمن جملة / كابشن صورة) ══
    auto_item = find_auto_reply(msg.text or msg.caption or "")
    auto_sent = None
    ai_sent = None
    ai_text = ""
    if auto_item:
        try:
            auto_sent = await ctx.bot.send_message(
                chat_id=user.id,
                text=render_premium_emojis(auto_item["reply"]),
                parse_mode=ParseMode.HTML,
                **protect_kwargs(user.id),
            )
            record_message(user.id, "user", auto_sent.message_id, "auto_reply")
        except TelegramError as e:
            logger.error(f"فشل إرسال الرد التلقائي: {e}")
    elif s.get("ai_enabled"):
        # ══ الرد بالذكاء الاصطناعي وفق التعليمات المكتوبة ══
        user_query = msg.text or msg.caption or ""
        if user_query:
            try:
                ai_text = await call_ai_service(user_query)
                ai_sent = await send_ai_reply_to_user(ctx, msg, ai_text, user.id)
                record_message(user.id, "user", ai_sent.message_id, "ai_reply")
            except Exception as e:
                logger.error(f"فشل استدعاء أو إرسال رد الذكاء الاصطناعي: {e}")
                try:
                    await ctx.bot.send_message(
                        chat_id=OWNER_ID,
                        text=f"⚠️ تعذّر رد الذكاء الاصطناعي للمستخدم {user_mention(user)}:\n<code>{html.escape(str(e))}</code>",
                        parse_mode=ParseMode.HTML
                    )
                except TelegramError:
                    pass
    elif s.get("away_enabled"):
        # وضع الغياب — يعمل فقط لو مفيش رد تلقائي بالكلمة أو ذكاء اصطناعي
        away_sent = await msg.reply_text(render_premium_emojis(s["away_msg"]), parse_mode=ParseMode.HTML,
                                         **protect_kwargs(user.id))
        record_message(user.id, "user", away_sent.message_id, "away_reply")

    # (تم إلغاء التفاعل التلقائي ⚡ بناءً على طلب المالك)

    fwd = await ctx.bot.forward_message(
        chat_id=OWNER_ID, from_chat_id=msg.chat_id, message_id=msg.message_id,
    )
    msg_map[fwd.message_id] = (user.id, msg.message_id)
    record_message(user.id, "owner", fwd.message_id, "forward")
    await _send_action_card(ctx, user.id, fwd.message_id)
    save_msg_map(msg_map)

    # ══ إبلاغ المالك أن البوت رد تلقائياً، بنفس شكل تأكيد الرد اليدوي ══
    if auto_item and auto_sent:
        reply_map[auto_sent.message_id] = (fwd.message_id, user.id)
        try:
            auto_owner_note = await ctx.bot.send_message(
                OWNER_ID,
                f"🤖 <b>رد تلقائي</b> — الكلمة: <code>{auto_item['keyword']}</code>\n\n"
                f"💬 {auto_item['reply']}",
                parse_mode=ParseMode.HTML,
                reply_parameters=make_rp(fwd.message_id),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "استرداد الرسالة 🗑️",
                        callback_data=f"recall:{user.id}:{auto_sent.message_id}",
                        api_kwargs={"style": "danger"},
                    )
                ]]),
            )
            record_message(user.id, "owner", auto_owner_note.message_id, "auto_reply_card")
        except TelegramError:
            pass

    # ══ إظهار رد الذكاء الاصطناعي للمالك وربطه بإمكانية الرد/الحذف ══
    if ai_sent:
        formatted_ai_text = prepare_ai_telegram_html(ai_text)
        owner_note = None
        owner_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🗑 حذف رد الذكاء الاصطناعي",
                callback_data=f"recall:{user.id}:{ai_sent.message_id}",
                api_kwargs={"style": "danger"},
            )
        ]])
        owner_text = (
            "🤖 <b>رد الذكاء الاصطناعي أُرسل للعضو</b>\n"
            "💡 للرد بنفسك: اضغط Reply على هذه الرسالة أو على رسالة العضو.\n\n"
            f"{formatted_ai_text}"
        )
        try:
            owner_note = await ctx.bot.send_message(
                OWNER_ID,
                owner_text,
                parse_mode=ParseMode.HTML,
                reply_parameters=make_rp(fwd.message_id),
                reply_markup=owner_markup,
            )
        except TelegramError:
            # لا نسمح بوسم غير صالح من النموذج أن يمنع إشعار المالك.
            try:
                owner_note = await ctx.bot.send_message(
                    OWNER_ID,
                    "🤖 <b>رد الذكاء الاصطناعي أُرسل للعضو</b>\n\n"
                    f"{html.escape(ai_text)}",
                    parse_mode=ParseMode.HTML,
                    reply_parameters=make_rp(fwd.message_id),
                    reply_markup=owner_markup,
                )
            except TelegramError:
                pass
        if owner_note:
            # الرد على إشعار الذكاء الاصطناعي يوجّه الرد اليدوي للعضو نفسه.
            msg_map[owner_note.message_id] = (user.id, msg.message_id)
            record_message(user.id, "owner", owner_note.message_id, "ai_reply_card")
            save_msg_map(msg_map)

# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
#  ردود المالك على المستخدمين
# ═══════════════════════════════════════════════════════════════

async def handle_owner_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    # ══ المالك عدّل رسالة سبق إرساله لها للمستخدم → نعدّلها فعليًا هناك ══
    # (بدل ما تتبعت رسالة جديدة أو يتغيّر وقتها)
    if update.edited_message:
        info = owner_sent_map.get(msg.message_id)
        if not info:
            return  # مفيش رسالة متبعتة مرتبطة بالتعديل ده، تجاهل
        user_id     = info["user_id"]
        sent_msg_id = info["sent_msg_id"]
        new_content = msg.text or msg.caption or ""
        if info.get("strip_amp") and new_content.startswith("&"):
            new_content = new_content[1:].strip()
        try:
            if info["kind"] == "text":
                await ctx.bot.edit_message_text(
                    chat_id=user_id, message_id=sent_msg_id, text=new_content,
                )
            else:
                await ctx.bot.edit_message_caption(
                    chat_id=user_id, message_id=sent_msg_id, caption=new_content,
                )
        except TelegramError as e:
            await msg.reply_text(f"⚠️ تعذّر تعديل الرسالة عند المستخدم: {e}")
            return
        await msg.reply_text("✅ تم تعديل الرسالة فعليًا عند المستخدم (بدون تغيير الوقت أو إرسالها من جديد).")
        return

    # ══ وضع الإرسال الصامت: لو مفعّل ورسالة جديدة (مش رد) ═══════
    # يبقى دي الرسالة المطلوب إرسالها بدون ظهورها كرد على المستخدم
    if not msg.reply_to_message and OWNER_ID in pending_silent:
        user_id = pending_silent.pop(OWNER_ID)
        try:
            sent = await ctx.bot.copy_message(
                chat_id=user_id, from_chat_id=OWNER_ID, message_id=msg.message_id,
                **protect_kwargs(user_id),
            )
        except TelegramError as e:
            await msg.reply_text(f"⚠️ فشل الإرسال: {e}")
            return
        reply_map[sent.message_id] = (msg.message_id, user_id)
        record_message(user_id, "user", sent.message_id, "owner_reply")
        record_message(user_id, "owner", msg.message_id, "owner_source")
        update_user_stats(user_id, last_reply=time.time())
        owner_sent_map[msg.message_id] = {
            "user_id": user_id, "sent_msg_id": sent.message_id,
            "kind": "text" if msg.text else "media", "strip_amp": False,
        }
        await msg.reply_text(
            "✅ تم الإرسال (بدون ظهوره كرد)",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "استرداد الرسالة 🗑️",
                    callback_data=f"recall:{user_id}:{sent.message_id}",
                    api_kwargs={"style": "danger"}
                )
            ]]),
        )
        return

    if not msg.reply_to_message:
        # ══ رد تلقائي بمعرّفات إيموجي بريميوم لو المالك بعت إيموجي بريميوم ══
        entities = list(msg.entities or []) + list(msg.caption_entities or [])
        custom = [e for e in entities if e.type == MessageEntity.CUSTOM_EMOJI]
        if custom:
            lines = [f"<code>{{{e.custom_emoji_id}}}</code>" for e in custom]
            await msg.reply_text(
                "✨ معرّفات الإيموجي البريميوم:\n\n" + "\n".join(lines) +
                "\n\nانسخ الكود بالكامل (بما فيه القوسين { }) وحطه في أي مكان جوه "
                "نص الترحيب/الغياب أو حتى في نص أزرار الترحيب.",
                parse_mode=ParseMode.HTML,
            )
            return
        return
    replied_id = msg.reply_to_message.message_id
    if replied_id not in msg_map:
        return
    user_id, user_msg_id = msg_map[replied_id]

    # ══ أمر "ا" / "أ" وحدها رداً على الرسالة المحوّلة ═════════════
    # يفعّل وضع الإرسال الصامت لنفس المستخدم؛ الرسالة الجاية (بدون رد) هتتبعتله عادية
    text_only = (msg.text or msg.caption or "").strip()
    if text_only in ("ا", "أ"):
        pending_silent[OWNER_ID] = user_id
        await msg.reply_text("✅ ابعت رسالتك دلوقتي، وهتوصل للمستخدم من غير ما تظهر كرد على رسالته.")
        return

    # ══ الرد بعلامة "&" في أول الرسالة ═════════════════════════════
    # بديل بخطوة واحدة: رد (reply) على أي رسالة محوّلة من المستخدم وابدأ
    # رسالتك بـ "&" فتتبعت له عادي بدون ما تظهر كرد على رسالة بعينها،
    # مع إنك بترد للمستخدم الصح من غير خطوتين زي أمر "ا".
    if text_only.startswith("&"):
        new_text = text_only[1:].strip()
        if not new_text:
            await msg.reply_text("⚠️ اكتب نص الرسالة بعد علامة &، مثال:\n&أهلاً بيك")
            return
        try:
            if msg.text:
                sent = await ctx.bot.send_message(chat_id=user_id, text=new_text,
                                                   **protect_kwargs(user_id))
            else:
                # وسيط (صورة/فيديو/ملف..) بكابشن يبدأ بـ & → يتبعت بنفس الوسيط
                # وكابشن جديد بدون علامة الـ & وبدون رد على رسالة بعينها
                sent = await ctx.bot.copy_message(
                    chat_id=user_id, from_chat_id=OWNER_ID, message_id=msg.message_id,
                    caption=new_text,
                    **protect_kwargs(user_id),
                )
        except TelegramError as e:
            await msg.reply_text(f"⚠️ فشل الإرسال: {e}")
            return
        reply_map[sent.message_id] = (msg.message_id, user_id)
        record_message(user_id, "user", sent.message_id, "owner_reply")
        record_message(user_id, "owner", msg.message_id, "owner_source")
        update_user_stats(user_id, last_reply=time.time())
        owner_sent_map[msg.message_id] = {
            "user_id": user_id, "sent_msg_id": sent.message_id,
            "kind": "text" if msg.text else "media", "strip_amp": True,
        }
        await msg.reply_text(
            "✅ تم الإرسال، وهيوصل للمستخدم من غير ما يظهر كرد على رسالة بعينها",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "استرداد الرسالة 🗑️",
                    callback_data=f"recall:{user_id}:{sent.message_id}",
                    api_kwargs={"style": "danger"}
                )
            ]]),
        )
        return

    try:
        sent = await ctx.bot.copy_message(
            chat_id=user_id, from_chat_id=OWNER_ID, message_id=msg.message_id,
            reply_parameters=make_rp(user_msg_id) if user_msg_id else None,
            **protect_kwargs(user_id),
        )
    except TelegramError as e:
        await msg.reply_text(f"⚠️ فشل الإرسال: {e}")
        return
    reply_map[sent.message_id] = (msg.message_id, user_id)
    record_message(user_id, "user", sent.message_id, "owner_reply")
    record_message(user_id, "owner", msg.message_id, "owner_source")
    update_user_stats(user_id, last_reply=time.time())
    owner_sent_map[msg.message_id] = {
        "user_id": user_id, "sent_msg_id": sent.message_id,
        "kind": "text" if msg.text else "media", "strip_amp": False,
    }

    # 🔴 التعديل هنا: إضافة api_kwargs لتلوين الزرار باللون الأحمر (danger)
    await msg.reply_text(
        "✅ تم الإرسال، وهيظهر للمستخدم كرد على رسالته",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "استرداد الرسالة 🗑️",
                callback_data=f"recall:{user_id}:{sent.message_id}",
                api_kwargs={"style": "danger"}
            )
        ]]),
    )

async def handle_private_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == OWNER_ID:
        await handle_owner_reply(update, ctx)
    else:
        await handle_user_message(update, ctx)

# ═══════════════════════════════════════════════════════════════
#  Callback Queries
# ═══════════════════════════════════════════════════════════════

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    await query.answer()

    if data.startswith("user_card:"):
        uid = int(data.split(":")[1])
        await _refresh_user_card_message(query, ctx, uid)
        return ConversationHandler.END

    if data.startswith("snooze_pick:"):
        uid = int(data.split(":")[1])
        kb = InlineKeyboardMarkup([
            [
                _mk_btn("1 ساعة", style="primary", callback_data=f"snooze:{uid}:1h"),
                _mk_btn("4 ساعات", style="primary", callback_data=f"snooze:{uid}:4h"),
            ],
            [
                _mk_btn("غداً", style="primary", callback_data=f"snooze:{uid}:tomorrow"),
                _mk_btn("بعد 3 أيام", style="primary", callback_data=f"snooze:{uid}:3d"),
            ],
            [
                _mk_btn("أسبوع", style="primary", callback_data=f"snooze:{uid}:week"),
                _mk_btn("رجوع", style="danger", callback_data=f"user_card:{uid}"),
            ],
        ])
        text = "⏰ <b>خذها بعدين، ذكّرني</b>\n\nاختر مدة التأجيل بضغطة واحدة:"
        try:
            if getattr(query.message, "photo", None):
                await query.edit_message_caption(caption=text, reply_markup=kb,
                                                  parse_mode=ParseMode.HTML)
            else:
                await query.edit_message_text(text, reply_markup=kb,
                                              parse_mode=ParseMode.HTML)
        except TelegramError:
            pass
        return ConversationHandler.END

    if data.startswith("snooze:"):
        _, uid_s, option = data.split(":")
        uid = int(uid_s)
        seconds = SNOOZE_OPTIONS.get(option)
        if not seconds:
            return ConversationHandler.END
        until = time.time() + seconds
        update_user_state(uid, snoozed_until=until, muted_until=0)
        append_audit(uid, "تأجيل", SNOOZE_LABELS[option])
        _schedule_snooze(ctx.job_queue, uid, until)
        await query.answer(f"⏰ تم التأجيل: {SNOOZE_LABELS[option]}", show_alert=False)
        await _refresh_user_card_message(query, ctx, uid)
        return ConversationHandler.END

    if data.startswith("mute:"):
        uid = int(data.split(":")[1])
        await _apply_mute(ctx, uid)
        await query.answer("🔇 تم الكتم لمدة 24 ساعة", show_alert=False)
        await _refresh_user_card_message(query, ctx, uid)
        return ConversationHandler.END

    if data.startswith("unmute:"):
        uid = int(data.split(":")[1])
        update_user_state(uid, muted_until=0)
        append_audit(uid, "إلغاء الكتم")
        await query.answer("🔊 تم إلغاء الكتم", show_alert=False)
        await _refresh_user_card_message(query, ctx, uid)
        return ConversationHandler.END

    if data.startswith("pin:"):
        uid = int(data.split(":")[1])
        await _toggle_pin(ctx, uid, query.message.message_id)
        await query.answer("📌 تم تحديث التثبيت", show_alert=False)
        await _refresh_user_card_message(query, ctx, uid)
        return ConversationHandler.END

    if data.startswith("clear_prompt:"):
        uid = int(data.split(":")[1])
        owner_count, user_count = _clear_counts(uid)
        text = (
            "⚠️ <b>تأكيد الحذف من الجهتين</b>\n\n"
            f"من محادثتك: <b>{owner_count}</b>\n"
            f"من محادثة المستخدم: <b>{user_count}</b>\n\n"
            "سيتم تجاهل الرسائل الأقدم من 48 ساعة بصمت وفق قيد Telegram."
        )
        kb = InlineKeyboardMarkup([[
            _mk_btn("🗑 نعم، احذف الكل", style="danger", callback_data=f"clear_yes:{uid}"),
            _mk_btn("إلغاء", style="primary", callback_data=f"user_card:{uid}"),
        ]])
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except TelegramError:
            try:
                await query.edit_message_caption(caption=text, reply_markup=kb,
                                                  parse_mode=ParseMode.HTML)
            except TelegramError:
                pass
        return ConversationHandler.END

    if data.startswith("clear_yes:"):
        uid = int(data.split(":")[1])
        owner_count, user_count = _clear_counts(uid)
        deleted_owner, deleted_user = await _delete_recorded_messages(ctx, uid)
        append_audit(uid, "حذف الكل",
                     f"المحاولة: {owner_count}/{user_count}، نجح: {deleted_owner}/{deleted_user}")
        try:
            await ctx.bot.send_message(
                OWNER_ID,
                "🗑 <b>اكتمل الحذف</b>\n\n"
                f"من محادثتك: {deleted_owner} من {owner_count}\n"
                f"من محادثة المستخدم: {deleted_user} من {user_count}\n"
                "الرسائل الأقدم من 48 ساعة أو غير القابلة للحذف تم تجاهلها بصمت.",
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            pass
        return ConversationHandler.END

    if data.startswith("ban_pick:"):
        _, uid_s, duration_key = data.split(":", 2)
        uid = int(uid_s)
        pending = ctx.user_data.get("pending_bans", {}).pop(str(uid), {})
        reason = pending.get("reason", "لم يتم تحديد سبب")
        await _apply_ban(ctx, uid, reason=reason, duration_key=duration_key)
        duration_label = BAN_OPTIONS.get(
            duration_key, BAN_OPTIONS["permanent"]
        )[1]
        await query.answer(f"🚫 تم الحظر: {duration_label}", show_alert=False)
        await _refresh_user_card_message(query, ctx, uid)
        return ConversationHandler.END

    if data.startswith("ban_yes:"):
        # توافق مع رسائل التأكيد القديمة التي كانت تستخدم هذا الزر.
        uid = int(data.split(":")[1])
        pending = ctx.user_data.get("pending_bans", {}).pop(str(uid), {})
        await _apply_ban(
            ctx, uid, reason=pending.get("reason", "لم يتم تحديد سبب"),
            duration_key="permanent",
        )
        await query.answer("🚫 تم الحظر وتسجيل العملية", show_alert=False)
        await _refresh_user_card_message(query, ctx, uid)
        return ConversationHandler.END

    if data.startswith("ban_no:"):
        uid = int(data.split(":")[1])
        await _refresh_user_card_message(query, ctx, uid)
        return ConversationHandler.END

    if data.startswith("do_ban:"):
        uid = int(data.split(":")[1])
        ctx.user_data["ban_reason_target"] = uid
        await query.edit_message_text(
            "✍️ اكتب سبب الحظر الآن في رسالة منفصلة.\n\n"
            "سيظهر السبب للمستخدم المحظور، وسيُحفظ في سجل الحظر.\n"
            "أرسل /cancel للإلغاء."
        )
        return AWAIT_BAN_REASON

    if data.startswith("do_unban:"):
        uid = int(data.split(":")[1])
        await _apply_unban(ctx, uid)
        await query.answer("✅ تم فك الحظر", show_alert=False)
        await _refresh_user_card_message(query, ctx, uid)
        return ConversationHandler.END

    if data.startswith("recall:"):
        _, uid_s, mid_s = data.split(":")
        try:
            await ctx.bot.delete_message(int(uid_s), int(mid_s))
            await query.edit_message_text("🗑️ تم حذف الرسالة من المستخدم.")
        except TelegramError as e:
            await query.edit_message_text(f"⚠️ تعذّر الحذف: {e}")
        return ConversationHandler.END

    if data == "edit_welcome":
        await query.edit_message_text(
            "✏️ أرسل نص رسالة الترحيب الجديدة.\n"
            "يمكنك استخدام {user_link} لذكر اسم المستخدم.\n\n"
            "لإضافة إيموجي بريميوم: استخدم /emoji_id علشان تجيب الكود، "
            "مثلاً {5386419798677874707}، وحطه جوه النص في أي مكان.\n\n"
            "أرسل /cancel للإلغاء.",
        )
        return AWAIT_WELCOME_TEXT

    if data == "edit_buttons":
        await query.edit_message_text(
            "🔗 أرسل أزرار الترحيب، كل سطر بالشكل:\n"
            "نص | رابط | اللون (اختياري)\n\n"
            "الألوان المدعومة:\n"
            "🔵 primary\n🟢 success\n🔴 danger\n\n"
            "لإضافة إيموجي بريميوم على الزر: استخدم /emoji_id علشان تجيب "
            "الكود وحط {ID} في أي مكان في نص الزر، هيظهر كأيقونة بجانب "
            "النص (إيموجي واحد بس لكل زر). لازم يكون عند صاحب البوت اشتراك "
            "Telegram Premium فعّال (أو أسماء مستخدمين إضافية من Fragment) "
            "علشان الإيموجي البريميوم يظهر صح.\n\n"
            "مثال:\n"
            "القناة الرسمية {5386419798677874707} | https://t.me/CHANNEL_USERNAME | primary\n\n"
            "أرسل /cancel للإلغاء.",
        )
        return AWAIT_BUTTONS_TEXT


    if data == "view_settings":
        s = load_settings()
        btns = "\n".join(f'{b["text"]} | {b["url"]}' for b in s["buttons"])
        away_status  = "🟢 مفعّل" if s.get("away_enabled") else "🔴 معطّل"
        auto_status  = "🟢 مفعّل" if s.get("autoresponder_enabled") else "🔴 معطّل"
        quick_status = "🟢 مفعّل" if s.get("quick_reply_enabled") else "🔴 معطّل"
        protect_status = "🟢 مفعّلة" if s.get("protect_content_enabled") else "🔴 معطّلة"
        ai_status    = "🟢 مفعّل" if s.get("ai_enabled") else "🔴 معطّل"
        ai_key       = "موجود ✅" if (s.get("ai_api_key") or os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY")) else "غير مدخل ❌"
        auto_count   = len(s.get("auto_replies", []))
        await query.message.reply_text(
            f"<b>📝 رسالة الترحيب:</b>\n{s['welcome']}\n\n<b>🔗 الأزرار:</b>\n{btns}\n\n"
            f"<b>🌙 وضع الغياب:</b> {away_status}\n"
            f"<b>🤖 الرد التلقائي:</b> {auto_status} ({auto_count} كلمة مسجّلة)\n"
            f"<b>⚡ الرد السريع:</b> {quick_status}\n"
            f"<b>🤖 الذكاء الاصطناعي:</b> {ai_status} (المفتاح: {ai_key})\n"
            f"<b>🔒 حماية المحتوى:</b> {protect_status}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="back_panel")
            ]]),
        )
        return ConversationHandler.END

    if data == "broadcast":
        await query.edit_message_text(
            "📢 أرسل الآن الرسالة أو الوسيط الذي تريد بثّه لجميع المستخدمين.\n\n"
            "أرسل /cancel للإلغاء.",
        )
        return AWAIT_BROADCAST_MSG

    if data == "away_delete_prompt":
        await query.edit_message_text(
            "⚠️ <b>تأكيد حذف رسائل الغياب</b>\n\n"
            "سيحاول البوت حذف كل الرسائل التي أرسلها تلقائيًا بسبب "
            "وضع الغياب من محادثات الأعضاء خلال آخر 48 ساعة.\n\n"
            "هذا يشمل الرسالة الظاهرة في الصورة حتى لو تغيّر نص رسالة الغياب "
            "بعد إرسالها.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                _mk_btn(
                    "🗑 نعم، احذف رسائل الغياب",
                    style="danger",
                    callback_data="away_delete_yes",
                ),
                _mk_btn("إلغاء", style="primary", callback_data="back_panel"),
            ]]),
        )
        return ConversationHandler.END

    if data == "away_delete_yes":
        deleted, failed, total = await _delete_away_messages(ctx)
        await query.answer("🗑 تم تنفيذ حذف رسائل الغياب", show_alert=False)
        try:
            await query.edit_message_text(
                "🗑 <b>تم تنفيذ حذف رسائل الغياب</b>\n\n"
                f"تم الحذف: {deleted} من {total}\n"
                f"تعذر الحذف: {failed}\n\n"
                "الرسائل الأقدم من 48 ساعة أو غير القابلة للحذف قد يرفضها Telegram.",
                parse_mode=ParseMode.HTML,
                reply_markup=owner_panel_keyboard(),
            )
        except TelegramError:
            await query.message.reply_text(
                "🗑 تم تنفيذ حذف رسائل الغياب.",
                reply_markup=owner_panel_keyboard(),
            )
        return ConversationHandler.END

    if data == "recent_delete_prompt":
        await query.edit_message_text(
            "⚠️ <b>تأكيد حذف رسائل آخر 24 ساعة</b>\n\n"
            "سيتم حذف الرسائل المسجلة خلال آخر 24 ساعة من:\n"
            "• محادثة المالك\n"
            "• محادثات الأعضاء\n"
            "• نسخ الرسالة المثبتة القديمة عند الأعضاء\n\n"
            "الرسائل الأقدم من ذلك لن تتأثر.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                _mk_btn(
                    "🗑 نعم، احذف آخر 24 ساعة",
                    style="danger",
                    callback_data="recent_delete_yes",
                ),
                _mk_btn("إلغاء", style="primary", callback_data="back_panel"),
            ]]),
        )
        return ConversationHandler.END

    if data == "recent_delete_yes":
        (
            deleted_owner,
            deleted_user,
            failed_owner,
            failed_user,
            total,
        ) = await _delete_recent_messages(ctx)
        await query.answer("🗑 تم تنفيذ حذف رسائل آخر 24 ساعة", show_alert=False)
        try:
            await query.edit_message_text(
                "🗑 <b>تم تنفيذ حذف رسائل آخر 24 ساعة</b>\n\n"
                f"من محادثة المالك: {deleted_owner} محذوفة، "
                f"{failed_owner} تعذر حذفها\n"
                f"من محادثات الأعضاء: {deleted_user} محذوفة، "
                f"{failed_user} تعذر حذفها\n"
                f"إجمالي الرسائل التي تمت معالجتها: {total}\n\n"
                "قد يرفض Telegram حذف بعض الرسائل المقيدة أو غير القابلة للحذف.",
                parse_mode=ParseMode.HTML,
                reply_markup=owner_panel_keyboard(),
            )
        except TelegramError:
            await query.message.reply_text(
                "🗑 تم تنفيذ حذف رسائل آخر 24 ساعة.",
                reply_markup=owner_panel_keyboard(),
            )
        return ConversationHandler.END

    if data == "global_delete":
        deleted, failed, total = await _delete_global_message(ctx)
        await query.answer("🗑 تم حذف النسخ عند المستخدمين", show_alert=False)
        try:
            await query.edit_message_text(
                "🗑 <b>تم تنفيذ حذف الرسالة عند المستخدمين</b>\n\n"
                f"تم الحذف: {deleted} من {total}\n"
                f"تعذر الحذف: {failed}\n"
                "النسخ الأقدم من 48 ساعة أو غير القابلة للحذف قد يرفضها Telegram.",
                parse_mode=ParseMode.HTML,
                reply_markup=owner_panel_keyboard(),
            )
        except TelegramError:
            await query.message.reply_text(
                "🗑 تم تنفيذ الحذف عند المستخدمين.",
                reply_markup=owner_panel_keyboard(),
            )
        return ConversationHandler.END

    if data == "banned_list":
        banned = sorted(load_banned())
        ban_records = load_ban_records()
        if not banned:
            await query.message.reply_text(
                "لا يوجد مستخدمون محظورون ✅",
                reply_markup=InlineKeyboardMarkup([[
                    _mk_btn("🔙 رجوع", style="primary", callback_data="back_panel")
                ]]),
            )
            return ConversationHandler.END

        lines = ["🚫 <b>قائمة المحظورين:</b>\n"]
        rows = []
        for uid in banned:
            info = await _fetch_user_info(ctx, uid)
            uname = f"@{info['username']}" if info.get("username") else "—"
            name  = info.get("full_name") or "مجهول"
            ban_record = ban_records.get(str(uid), {})
            reason = html.escape(str(ban_record.get("reason") or "لم يتم تحديد سبب"))
            duration = html.escape(_ban_duration_text(ban_record))
            lines.append(
                f"👤 <b>{name}</b>\n"
                f"   🆔 <code>{uid}</code>\n"
                f"   🌀 {uname}\n"
                f"   📝 السبب: {reason}\n"
                f"   ⏱ المدة: {duration}"
            )
            rows.append([_mk_btn(f"👁️ {name}"[:40], style="primary",
                                 callback_data=f"user_details:{uid}")])
        rows.append([_mk_btn("🔙 رجوع", style="primary", callback_data="back_panel")])
        await query.message.reply_text(
            "\n\n".join(lines), parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return ConversationHandler.END

    if data.startswith("users_list:"):
        page = int(data.split(":")[1])
        users = sorted(load_users())
        banned = load_banned()
        PER_PAGE = 8
        total_pages = max(1, (len(users) + PER_PAGE - 1) // PER_PAGE)
        page = max(0, min(page, total_pages - 1))
        start = page * PER_PAGE
        chunk = users[start:start + PER_PAGE]

        if not users:
            await query.message.reply_text(
                "لا يوجد مستخدمون بعد 📭",
                reply_markup=InlineKeyboardMarkup([[
                    _mk_btn("🔙 رجوع", style="primary", callback_data="back_panel")
                ]]),
            )
            return ConversationHandler.END

        rows = []
        for uid in chunk:
            info = await _fetch_user_info(ctx, uid)
            name = info.get("full_name") or f"user {uid}"
            is_banned = uid in banned
            label = ("🚫 " if is_banned else "✅ ") + name
            style = "danger" if is_banned else "success"
            rows.append([_mk_btn(label[:40], style=style,
                                 callback_data=f"user_details:{uid}")])

        nav = []
        if page > 0:
            nav.append(_mk_btn("◀️ السابق", style="primary",
                               callback_data=f"users_list:{page-1}"))
        nav.append(_mk_btn(f"صفحة {page+1}/{total_pages}", style="primary",
                           callback_data="noop"))
        if page < total_pages - 1:
            nav.append(_mk_btn("التالي ▶️", style="primary",
                               callback_data=f"users_list:{page+1}"))
        if nav:
            rows.append(nav)
        rows.append([_mk_btn("🔙 رجوع", style="primary", callback_data="back_panel")])

        await query.message.reply_text(
            f"👥 <b>قائمة المستخدمين ({len(users)}):</b>\n"
            f"✅ = نشط | 🚫 = محظور",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return ConversationHandler.END

    if data.startswith("user_details:"):
        uid = int(data.split(":")[1])
        await _send_user_details(ctx, query.message.chat_id, uid,
                                 reply_to=query.message.message_id)
        return ConversationHandler.END

    if data.startswith("do_ban:") or data.startswith("do_unban:"):
        action, uid_s = data.split(":")
        uid = int(uid_s)
        if action == "do_ban":
            await _apply_ban(ctx, uid, reason="لم يتم تحديد سبب")
            await query.answer("✅ تم الحظر", show_alert=False)
        else:
            await _apply_unban(ctx, uid)
            await query.answer("✅ تم فك الحظر", show_alert=False)
        # حدّث نفس الرسالة بتفاصيل المستخدم المحدّثة
        try:
            info = await _fetch_user_info(ctx, uid)
            text, kb = _build_user_details_view(uid, info)
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except TelegramError:
            pass
        return ConversationHandler.END

    if data == "noop":
        return ConversationHandler.END


    if data == "back_panel":
        await query.message.reply_text(
            "⚙️ لوحة تحكم البوت\nمرحباً بك 👋",
            reply_markup=owner_panel_keyboard(),
        )
        return ConversationHandler.END

    if data == "reset_settings":
        s = {"welcome": DEFAULT_WELCOME, "buttons": DEFAULT_BUTTONS,
             "away_enabled": False, "away_msg": DEFAULT_AWAY_MSG,
             "autoresponder_enabled": False, "auto_replies": [],
             "quick_reply_enabled": False, "quick_reply_msg": DEFAULT_QUICK_REPLY_MSG,
             "protect_content_enabled": False,
             # إعادة الإعدادات لا تلغي النسخة العامة أو زر حذفها.
             "global_pin": _global_pin_data(),
             }
        save_settings(s)
        await query.answer("✅ تم إعادة الإعدادات للأصل", show_alert=True)
        await query.edit_message_text(
            "⚙️ لوحة تحكم البوت\nمرحباً بك 👋",
            reply_markup=owner_panel_keyboard(),
        )
        return ConversationHandler.END

    if data == "toggle_away":
        s = load_settings()
        s["away_enabled"] = not s["away_enabled"]
        save_settings(s)
        status = "مفعّل 🟢" if s["away_enabled"] else "معطّل 🔴"
        await query.answer(f"وضع الغياب {status}", show_alert=True)
        await query.edit_message_text(
            "⚙️ لوحة تحكم البوت\nمرحباً بك 👋",
            reply_markup=owner_panel_keyboard(),
        )
        return ConversationHandler.END

    if data == "toggle_protect_content":
        s = load_settings()
        s["protect_content_enabled"] = not s.get("protect_content_enabled", False)
        save_settings(s)
        status = "مفعّلة 🟢" if s["protect_content_enabled"] else "معطّلة 🔴"
        await query.answer(f"حماية المحتوى {status}", show_alert=True)
        await query.edit_message_text(
            "⚙️ لوحة تحكم البوت\nمرحباً بك 👋",
            reply_markup=owner_panel_keyboard(),
        )
        return ConversationHandler.END

    if data == "edit_away_msg":
        s = load_settings()
        await query.edit_message_text(
            f"✉️ أرسل رسالة الغياب الجديدة.\n\n"
            f"الرسالة الحالية:\n{s['away_msg']}\n\n"
            f"لإضافة إيموجي بريميوم: استخدم /emoji_id علشان تجيب الكود، وحطه جوه النص.\n\n"
            f"أرسل /cancel للإلغاء.",
        )
        return AWAIT_AWAY_TEXT

    # ══ الرد التلقائي بالكلمات ═══════════════════════════════════

    if data == "auto_reply_menu":
        text, kb = auto_reply_menu_view()
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return ConversationHandler.END

    if data == "auto_reply_toggle":
        s = load_settings()
        s["autoresponder_enabled"] = not s.get("autoresponder_enabled", False)
        save_settings(s)
        status = "مفعّل 🟢" if s["autoresponder_enabled"] else "معطّل 🔴"
        await query.answer(f"الرد التلقائي {status}", show_alert=True)
        text, kb = auto_reply_menu_view()
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return ConversationHandler.END

    if data == "auto_reply_add":
        await query.edit_message_text(
            "➕ أرسل الكلمة والرد بالصيغة التالية (سطر واحد):\n"
            "الكلمة | الرد\n\n"
            "مثال:\n"
            "السعر | 🔥 السعر يبدأ من 50$، تواصل معنا للتفاصيل.\n\n"
            "ملاحظة: هيتم الرد تلقائياً لو المستخدم بعت هذه الكلمة وحدها، "
            "أو ضمن جملة، أو في كابشن على صورة.\n\n"
            "أرسل /cancel للإلغاء.",
        )
        return AWAIT_AUTO_KEYWORD_ADD

    if data.startswith("auto_reply_del:"):
        idx = int(data.split(":")[1])
        s = load_settings()
        items = s.get("auto_replies", [])
        if 0 <= idx < len(items):
            removed = items.pop(idx)
            s["auto_replies"] = items
            save_settings(s)
            await query.answer(f"🗑️ تم حذف الكلمة: {removed.get('keyword', '')}", show_alert=True)
        text, kb = auto_reply_menu_view()
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return ConversationHandler.END

    # ══ الرد بالذكاء الاصطناعي ══════════════════════════════════

    if data == "ai_reply_menu":
        text, kb = ai_reply_menu_view()
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return ConversationHandler.END

    if data == "ai_reply_toggle":
        s = load_settings()
        s["ai_enabled"] = not s.get("ai_enabled", False)
        save_settings(s)
        status = "مفعّل 🟢" if s["ai_enabled"] else "معطّل 🔴"
        await query.answer(f"الرد بالذكاء الاصطناعي {status}", show_alert=True)
        text, kb = ai_reply_menu_view()
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return ConversationHandler.END

    if data == "ai_reply_edit_prompt":
        s = load_settings()
        current_prompt = str(s.get("ai_instructions", DEFAULT_AI_INSTRUCTIONS) or "")
        escaped_prompt = html.escape(current_prompt)
        prompt_preview = escaped_prompt[:2600]
        if len(escaped_prompt) > 2600:
            prompt_preview += "\n… (تم اختصار المعاينة؛ أرسل تعليمات جديدة لاستبدالها)"
        await query.edit_message_text(
            "✏️ <b>أرسل التعليمات والتوجيهات المكتوبة للذكاء الاصطناعي (System Prompt):</b>\n\n"
            f"التعليمات الحالية:\n<i>{prompt_preview}</i>\n\n"
            "أرسل /cancel للإلغاء.",
            parse_mode=ParseMode.HTML,
        )
        return AWAIT_AI_INSTRUCTIONS

    if data == "ai_reply_edit_key":
        await query.edit_message_text(
            "🔑 <b>أرسل مفتاح الذكاء الاصطناعي (API Key):</b>\n\n"
            "يدعم مفاتيح OpenAI (sk-...) أو أي مزود متوافق (Groq, OpenRouter, DeepSeek).\n"
            "أرسل /cancel للإلغاء.",
            parse_mode=ParseMode.HTML,
        )
        return AWAIT_AI_KEY

    if data == "ai_reply_edit_model":
        s = load_settings()
        await query.edit_message_text(
            "⚙️ <b>أرسل اسم الموديل المطلوب استخدامه:</b>\n\n"
            f"الموديل الحالي: <code>{s.get('ai_model', DEFAULT_AI_MODEL)}</code>\n"
            "أمثلة: <code>gpt-4o-mini</code>, <code>gpt-4o</code>, <code>deepseek-chat</code>\n\n"
            "أرسل /cancel للإلغاء.",
            parse_mode=ParseMode.HTML,
        )
        return AWAIT_AI_MODEL

    # ══ الرد السريع ══════════════════════════════════════════════

    if data == "quick_reply_menu":
        text, kb = quick_reply_menu_view()
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return ConversationHandler.END

    if data == "quick_reply_toggle":
        s = load_settings()
        s["quick_reply_enabled"] = not s.get("quick_reply_enabled", False)
        save_settings(s)
        status = "مفعّل 🟢" if s["quick_reply_enabled"] else "معطّل 🔴"
        await query.answer(f"الرد السريع {status}", show_alert=True)
        text, kb = quick_reply_menu_view()
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return ConversationHandler.END

    if data == "quick_reply_edit":
        s = load_settings()
        await query.edit_message_text(
            f"✏️ أرسل نص الرد السريع الجديد.\n\n"
            f"النص الحالي:\n{s.get('quick_reply_msg', '')}\n\n"
            f"لإضافة إيموجي بريميوم: استخدم /emoji_id وحط الكود {{ID}} جوه النص.\n\n"
            f"أرسل /cancel للإلغاء.",
        )
        return AWAIT_QUICK_REPLY_TEXT

    return ConversationHandler.END

# ═══════════════════════════════════════════════════════════════
#  إعدادات الترحيب
# ═══════════════════════════════════════════════════════════════

async def recv_welcome_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    s = load_settings(); s["welcome"] = update.message.text; save_settings(s)
    await update.message.reply_text("✅ تم تحديث رسالة الترحيب.", reply_markup=owner_panel_keyboard())
    return ConversationHandler.END

async def recv_buttons_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    lines = update.message.text.strip().splitlines()
    buttons = []
    for line in lines:
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            btn = {"text": parts[0], "url": parts[1]}
            # التأكد من وجود لون صحيح
            if len(parts) > 2 and parts[2].lower() in ["primary", "success", "danger"]:
                btn["style"] = parts[2].lower()
            buttons.append(btn)
            
    if not buttons:
        await update.message.reply_text("⚠️ الصيغة غير صحيحة.\nمثال: نص | رابط | primary\nأو /cancel للإلغاء.")
        return AWAIT_BUTTONS_TEXT
        
    s = load_settings(); s["buttons"] = buttons; save_settings(s)
    await update.message.reply_text("✅ تم تحديث أزرار الترحيب بالألوان.", reply_markup=owner_panel_keyboard())
    return ConversationHandler.END


async def recv_broadcast_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    users = load_users(); msg = update.effective_message
    ok = fail = 0
    for uid in list(users):
        if uid == OWNER_ID: continue
        try:
            sent = await ctx.bot.copy_message(
                chat_id=uid,
                from_chat_id=OWNER_ID,
                message_id=msg.message_id,
                **protect_kwargs(uid),
            )
            record_message(uid, "user", sent.message_id, "broadcast")
            ok += 1
        except TelegramError:
            fail += 1
    await msg.reply_text(
        f"✅ انتهى البث\nتم الإرسال: {ok} ✔️\nفشل: {fail} ✖️",
        reply_markup=owner_panel_keyboard(),
    )
    return ConversationHandler.END


async def recv_away_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    s = load_settings(); s["away_msg"] = update.message.text; save_settings(s)
    await update.message.reply_text("✅ تم تحديث رسالة الغياب.", reply_markup=owner_panel_keyboard())
    return ConversationHandler.END

async def recv_auto_keyword_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    text = update.message.text.strip()
    if "|" not in text:
        await update.message.reply_text(
            "⚠️ الصيغة غير صحيحة.\nمثال: السعر | 🔥 السعر يبدأ من 50$\n"
            "أو /cancel للإلغاء."
        )
        return AWAIT_AUTO_KEYWORD_ADD
    keyword, reply = text.split("|", 1)
    keyword, reply = keyword.strip(), reply.strip()
    if not keyword or not reply:
        await update.message.reply_text(
            "⚠️ لازم تكتب كلمة ورد فعلي.\nمثال: السعر | 🔥 السعر يبدأ من 50$\n"
            "أو /cancel للإلغاء."
        )
        return AWAIT_AUTO_KEYWORD_ADD
    s = load_settings()
    items = s.get("auto_replies", [])
    items.append({"keyword": keyword, "reply": reply})
    s["auto_replies"] = items
    save_settings(s)
    await update.message.reply_text(f"✅ تم إضافة الكلمة: <b>{keyword}</b>", parse_mode=ParseMode.HTML)
    text_view, kb = auto_reply_menu_view()
    await update.message.reply_text(text_view, parse_mode=ParseMode.HTML, reply_markup=kb)
    return ConversationHandler.END

async def recv_ai_instructions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    s = load_settings()
    s["ai_instructions"] = update.message.text.strip()
    save_settings(s)
    await update.message.reply_text("✅ تم تحديث تعليمات الذكاء الاصطناعي بنجاح.", reply_markup=owner_panel_keyboard())
    return ConversationHandler.END

async def recv_ai_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    s = load_settings()
    s["ai_api_key"] = update.message.text.strip()
    save_settings(s)
    await update.message.reply_text("✅ تم حفظ مفتاح الذكاء الاصطناعي (API Key) بنجاح.", reply_markup=owner_panel_keyboard())
    return ConversationHandler.END

async def recv_ai_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    s = load_settings()
    s["ai_model"] = update.message.text.strip()
    save_settings(s)
    await update.message.reply_text(f"✅ تم تغيير الموديل إلى: {s['ai_model']}", reply_markup=owner_panel_keyboard())
    return ConversationHandler.END


async def recv_ban_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    uid = ctx.user_data.pop("ban_reason_target", None)
    reason = (update.message.text or "").strip()
    if not uid:
        await update.message.reply_text("⚠️ انتهت جلسة الحظر. أعد الضغط على زر الحظر.")
        return ConversationHandler.END
    if not reason:
        await update.message.reply_text("⚠️ اكتب سبباً واضحاً للحظر أو أرسل /cancel.")
        ctx.user_data["ban_reason_target"] = uid
        return AWAIT_BAN_REASON
    await _send_ban_confirmation_with_reason(
        ctx, update.effective_chat.id, int(uid), reason=reason
    )
    return ConversationHandler.END


async def recv_quick_reply_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return ConversationHandler.END
    s = load_settings(); s["quick_reply_msg"] = update.message.text; save_settings(s)
    await update.message.reply_text("✅ تم تحديث نص الرد السريع.", reply_markup=owner_panel_keyboard())
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("ban_reason_target", None)
    ctx.user_data.pop("pending_bans", None)
    await update.message.reply_text("❌ تم الإلغاء.", reply_markup=owner_panel_keyboard())
    return ConversationHandler.END

# ═══════════════════════════════════════════════════════════════
#  /ban  /unban
# ═══════════════════════════════════════════════════════════════

async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    msg = update.effective_message; target = None
    reason = ""
    if msg.reply_to_message:
        target = _target_user_from_owner_message(msg)
        reason = " ".join(ctx.args).strip()
    elif ctx.args:
        first = ctx.args[0]
        if first.startswith("@"):
            try:
                chat = await ctx.bot.get_chat(first)
                target = chat.id
            except TelegramError:
                await msg.reply_text("⚠️ لم يُعثر على المستخدم."); return
            reason = " ".join(ctx.args[1:]).strip()
        else:
            try:
                target = int(first)
            except ValueError:
                await msg.reply_text("⚠️ يرجى تحديد ID صحيح."); return
            reason = " ".join(ctx.args[1:]).strip()
    if not target:
        await msg.reply_text(
            "⚠️ لم يُحدَّد المستخدم.\n"
            "استخدم /ban سبب الحظر بالرد على رسالته، أو "
            "/ban USER_ID سبب الحظر."
        )
        return
    if not reason:
        await msg.reply_text(
            "⚠️ يجب كتابة سبب مخصص للحظر.\n"
            "مثال: /ban مخالفة قواعد التواصل"
        )
        return
    await _send_ban_confirmation_with_reason(
        ctx, msg.chat_id, target, reason=reason, reply_to=msg.message_id
    )

async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    msg = update.effective_message; target = None
    if msg.reply_to_message:
        target = _target_user_from_owner_message(msg)
    elif ctx.args:
        arg = ctx.args[0]
        if arg.startswith("@"):
            try: chat = await ctx.bot.get_chat(arg); target = chat.id
            except TelegramError:
                await msg.reply_text("⚠️ لم يُعثر على المستخدم."); return
        else:
            try: target = int(arg)
            except ValueError:
                await msg.reply_text("⚠️ ID غير صحيح."); return
    if not target:
        await msg.reply_text("⚠️ لم يُحدَّد المستخدم.\n/unban رداً على رسالته أو /unban USER_ID"); return
    await _apply_unban(ctx, target)
    await msg.reply_text(f"✅ تم رفع الحظر عن <code>{target}</code>.", parse_mode=ParseMode.HTML)

# ═══════════════════════════════════════════════════════════════
#  /info — عرض تفاصيل مستخدم بالرد على رسالته المحوّلة
# ═══════════════════════════════════════════════════════════════

async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    msg = update.effective_message
    target = None
    if msg.reply_to_message:
        target = _target_user_from_owner_message(msg)
    elif ctx.args:
        try: target = int(ctx.args[0])
        except ValueError:
            await msg.reply_text("⚠️ ID غير صحيح."); return
    if not target:
        await msg.reply_text(
            "⚠️ استخدم /info بالرد على رسالة مستخدم محوّلة، أو /info USER_ID"
        )
        return
    await _send_user_details(ctx, msg.chat_id, target, reply_to=msg.message_id)


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """يحذف السجل المرتبط بالمستخدم مباشرة عند الرد على رسالته."""
    if update.effective_user.id != OWNER_ID:
        return
    msg = update.effective_message
    target = _target_user_from_owner_message(msg)
    if not target and ctx.args:
        try:
            target = int(ctx.args[0])
        except ValueError:
            await msg.reply_text("⚠️ ID غير صحيح.")
            return
    if not target:
        await msg.reply_text("⚠️ استخدم /clear بالرد على رسالة المستخدم أو /clear USER_ID.")
        return
    owner_count, user_count = _clear_counts(target)
    deleted_owner, deleted_user = await _delete_recorded_messages(ctx, target)
    append_audit(
        target, "حذف مباشر",
        f"المحاولة: {owner_count}/{user_count}، نجح: {deleted_owner}/{deleted_user}",
    )
    await msg.reply_text(
        "🗑 تم تنفيذ الحذف مباشرة.\n\n"
        f"من محادثتك: {deleted_owner} من {owner_count}\n"
        f"من محادثة المستخدم: {deleted_user} من {user_count}\n"
        "الرسائل الأقدم من 48 ساعة تم تجاهلها بصمت."
    )


# ═══════════════════════════════════════════════════════════════
#  /forward — تحويل رسالة مستخدم إلى مستخدم تاني (المالك فقط)
# ═══════════════════════════════════════════════════════════════

async def cmd_forward(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    msg = update.effective_message

    if not msg.reply_to_message or msg.reply_to_message.message_id not in msg_map:
        await msg.reply_text(
            "⚠️ استخدم الأمر بالرد (reply) على الرسالة المحوّلة من المستخدم اللي عايز تبعتها لشخص تاني.\n"
            "مثال: /forward 123456789"
        )
        return

    if not ctx.args:
        await msg.reply_text(
            "⚠️ حدد آيدي المستخدم اللي عايز تحوّل له الرسالة.\n"
            "مثال: /forward 123456789"
        )
        return

    try:
        target = int(ctx.args[0])
    except ValueError:
        await msg.reply_text("⚠️ آيدي غير صحيح.")
        return

    source_msg_id = msg.reply_to_message.message_id
    source_user_id, _ = msg_map[source_msg_id]

    if target == source_user_id:
        await msg.reply_text("⚠️ هذه الرسالة أصلاً من هذا المستخدم.")
        return

    if target in load_banned():
        await msg.reply_text("⚠️ هذا المستخدم محظور من البوت، لا يمكن التحويل له.")
        return

    try:
        sent = await ctx.bot.copy_message(
            chat_id=target, from_chat_id=OWNER_ID, message_id=source_msg_id,
            **protect_kwargs(target),
        )
    except TelegramError as e:
        await msg.reply_text(f"⚠️ فشل تحويل الرسالة: {e}")
        return

    reply_map[sent.message_id] = (msg.message_id, target)
    await msg.reply_text(
        f"✅ تم تحويل الرسالة إلى المستخدم <code>{target}</code> بنجاح (بدون كشف هوية صاحبها الأصلي).",
        parse_mode=ParseMode.HTML,
    )


# ═══════════════════════════════════════════════════════════════
#  /backup  /restore — نسخ احتياطي واستعادة (المالك فقط)
# ═══════════════════════════════════════════════════════════════

BACKUP_KEYS = (
    "settings", "banned", "ban_records", "users", "user_state", "user_stats",
    "message_records", "audit_log",
)

def build_backup_dict():
    return {
        "settings": load_settings(),
        "banned":   list(load_banned()),
        "ban_records": list(_purge_expired_bans().values()),
        "users":    list(load_users()),
        "user_state": load_user_state(),
        "user_stats": load_user_stats(),
        "message_records": load_message_records(),
        "audit_log": load_audit_log(),
    }

async def cmd_backup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    msg = update.effective_message
    data = build_backup_dict()
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    tmp_path = Path(f"backup_{stamp}.json")
    _save(tmp_path, data)
    try:
        with open(tmp_path, "rb") as f:
            await ctx.bot.send_document(
                chat_id=OWNER_ID,
                document=f,
                filename=f"backup_{stamp}.json",
                caption=(
                    f"📦 نسخة احتياطية — {stamp}\n"
                    f"👥 مستخدمين: {len(data['users'])} | 🚫 محظورين: {len(data['banned'])}\n\n"
                    "لاستعادتها لاحقاً: أرسل هذا الملف مع كتابة /restore في نفس الرسالة (كابشن)، "
                    "أو أرسل /restore رداً على هذا الملف."
                ),
            )
    except TelegramError as e:
        await msg.reply_text(f"⚠️ فشل إنشاء النسخة الاحتياطية: {e}")
    finally:
        try: tmp_path.unlink()
        except OSError: pass

async def _do_restore(update: Update, ctx: ContextTypes.DEFAULT_TYPE, doc):
    msg = update.effective_message
    try:
        tg_file = await doc.get_file()
        raw = await tg_file.download_as_bytearray()
        data = json.loads(bytes(raw).decode("utf-8"))
    except (TelegramError, ValueError, UnicodeDecodeError) as e:
        await msg.reply_text(f"⚠️ الملف غير صالح أو تالف: {e}")
        return

    # نتعرّف على الملف سواء كان بصيغة النسخة الحالية (settings/banned/users)
    # أو صيغة نسخة قديمة (messages/status/users) — زي اللي بيرجعها بوت سابق
    recognized_keys = set(BACKUP_KEYS) | {"messages", "status"}
    if not isinstance(data, dict) or not any(k in data for k in recognized_keys):
        await msg.reply_text("⚠️ هذا الملف مش ملف نسخة احتياطية صالح لهذا البوت.")
        return

    restored = []

    # ── إعدادات (صيغة البوت الحالي) ──────────────────────────
    if "settings" in data and isinstance(data["settings"], dict):
        s = load_settings()
        s.update(data["settings"])
        save_settings(s)
        restored.append("⚙️ الإعدادات (الترحيب/الأزرار/الغياب)")

    if "user_state" in data and isinstance(data["user_state"], dict):
        current = load_user_state()
        current.update(data["user_state"])
        save_user_state(current)
        restored.append(f"⏰ حالات التأجيل/الكتم ({len(data['user_state'])})")

    if "user_stats" in data and isinstance(data["user_stats"], dict):
        current = load_user_stats()
        current.update(data["user_stats"])
        save_user_stats(current)
        restored.append(f"📊 إحصائيات المستخدمين ({len(data['user_stats'])})")

    if "message_records" in data and isinstance(data["message_records"], dict):
        current = load_message_records()
        current.update(data["message_records"])
        save_message_records(current)
        restored.append("🧾 سجل الرسائل")

    if "audit_log" in data and isinstance(data["audit_log"], list):
        save_audit_log(data["audit_log"])
        restored.append("📝 سجل العمليات")

    # ── محظورون (صيغة البوت الحالي) ──────────────────────────
    if "banned" in data and isinstance(data["banned"], list):
        try:
            new_banned = {int(x) for x in data["banned"]}
        except (TypeError, ValueError):
            new_banned = set()
        save_banned(load_banned() | new_banned)
        restored.append(f"🚫 المحظورون ({len(new_banned)})")

    if "ban_records" in data and isinstance(data["ban_records"], list):
        current = load_ban_records()
        restored_count = 0
        for item in data["ban_records"]:
            if not isinstance(item, dict):
                continue
            record = _normalize_ban_record(item.get("user_id"), item)
            if record:
                current[str(record["user_id"])] = record
                _schedule_ban_expiry(
                    ctx.job_queue,
                    int(record["user_id"]),
                    record.get("expires_at"),
                )
                restored_count += 1
        save_ban_records(current)
        restored.append(f"📝 تفاصيل الحظر (السبب والمدة): {restored_count}")

    # ── مستخدمون: يدعم صيغتين ─────────────────────────────────
    #   1) قائمة IDs بسيطة (صيغة البوت الحالي)
    #   2) dict فيه إحصائيات لكل مستخدم (صيغة نسخة قديمة)
    old_stats = None
    if "users" in data and isinstance(data["users"], dict):
        old_users_dict = data["users"]
        old_ids = set()
        for uid in old_users_dict.keys():
            try:
                old_ids.add(int(uid))
            except (TypeError, ValueError):
                continue
        save_users(load_users() | old_ids)
        old_stats = old_users_dict

        total_msgs = sum(
            u.get("msg_count", 0) for u in old_users_dict.values() if isinstance(u, dict)
        )
        blocked = sum(
            1 for u in old_users_dict.values()
            if isinstance(u, dict) and u.get("blocked_bot")
        )
        restored.append(
            f"👥 المستخدمون (من نسخة قديمة): {len(old_ids)}\n"
            f"   ✉️ إجمالي عدد رسائلهم المسجلة: {total_msgs}\n"
            f"   🚷 حاظرين البوت حالياً: {blocked}"
        )
    elif "users" in data and isinstance(data["users"], list):
        try:
            new_users = {int(x) for x in data["users"]}
        except (TypeError, ValueError):
            new_users = set()
        save_users(load_users() | new_users)
        restored.append(f"👥 المستخدمون ({len(new_users)})")

    # ── رسائل/حالة الغياب (صيغة نسخة قديمة) ──────────────────
    if "messages" in data and isinstance(data["messages"], dict):
        m = data["messages"]
        s = load_settings()
        if m.get("welcome"):
            # البوت القديم يستخدم {name} بدل {user_link} — نحوّلها للتوافق
            s["welcome"] = m["welcome"].replace("{name}", "{user_link}")
        if m.get("away"):
            s["away_msg"] = m["away"].replace("{name}", "{user_link}")
        if "status" in data and isinstance(data["status"], dict):
            s["away_enabled"] = bool(data["status"].get("is_away", s.get("away_enabled")))
        save_settings(s)
        restored.append("📝 رسائل الترحيب/الغياب (من نسخة قديمة)")

    if not restored:
        await msg.reply_text("⚠️ الملف لا يحتوي بيانات صالحة للاستعادة.")
        return

    # نحتفظ بالإحصائيات القديمة كاملة (الاسم/آخر ظهور/عدد الرسائل...) كمرجع
    if old_stats is not None:
        try:
            _save(OLD_STATS_FILE, old_stats)
        except OSError as e:
            logger.error(f"فشل حفظ old_stats.json: {e}")

    try:
        await msg.reply_text(
            "✅ تم استرجاع النسخة الاحتياطية بنجاح:\n\n" + "\n".join(restored),
            reply_markup=owner_panel_keyboard(),
        )
    except TelegramError as e:
        logger.error(f"فشل إرسال رسالة تأكيد الاسترجاع بالكيبورد: {e}")
        await msg.reply_text(
            "✅ تم استرجاع النسخة الاحتياطية بنجاح:\n\n" + "\n".join(restored)
        )

async def cmd_restore(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """يُستدعى إما بأمر /restore نصي (رداً على ملف JSON) أو عبر كابشن على الملف نفسه."""
    if update.effective_user.id != OWNER_ID:
        return
    msg = update.effective_message
    doc = msg.document
    if not doc and msg.reply_to_message:
        doc = msg.reply_to_message.document
    if not doc:
        await msg.reply_text(
            "⚠️ محتاج ملف الـ JSON بتاع النسخة الاحتياطية.\n"
            "اتبع واحدة من الطريقتين:\n"
            "1) ابعت الملف واكتب /restore في نفس الرسالة (كابشن).\n"
            "2) ابعت /restore رداً على الملف."
        )
        return
    await _do_restore(update, ctx, doc)

# ═══════════════════════════════════════════════════════════════
#  /emoji_id — استخراج معرف الإيموجي البريميوم (المالك فقط)
#
#  يشترط تليجرام أن يكون صاحب حساب البوت (المالك) مشتركاً في
#  Telegram Premium حتى يقدر البوت يبعت إيموجي بريميوم.
#  الطريقة: المالك يبعت /emoji_id ويلصق الإيموجي البريميوم بعده
#  في نفس الرسالة (مثال: /emoji_id 🔥) فيرد البوت بوسم HTML
#  جاهز يقدر يحطه في رسالة الترحيب أو الغياب.
# ═══════════════════════════════════════════════════════════════

async def cmd_emoji_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    msg = update.effective_message
    entities = msg.entities or []
    custom = [e for e in entities if e.type == MessageEntity.CUSTOM_EMOJI]

    if not custom:
        await msg.reply_text(
            "⚠️ محتاج تلصق إيموجي بريميوم بعد الأمر مباشرة.\n"
            "مثال: <code>/emoji_id 🔥</code> (حيث 🔥 هو الإيموجي البريميوم نفسه)\n\n"
            "ملاحظة: لازم يكون حسابك (المالك) مشترك Telegram Premium.",
            parse_mode=ParseMode.HTML,
        )
        return

    text = msg.text
    lines = []
    for e in custom:
        lines.append(f"<code>{{{e.custom_emoji_id}}}</code>")

    await msg.reply_text(
        "✅ استخرجت الـ ID بتاع الإيموجي:\n\n" + "\n".join(lines) +
        "\n\nانسخ الكود بالكامل (بما فيه القوسين { }) وحطه في أي مكان جوه نص "
        "رسالة الترحيب/الغياب، وهيتحول تلقائياً لإيموجي بريميوم عند الإرسال.",
        parse_mode=ParseMode.HTML,
    )

def build_premium_emoji_tag(emoji_id: str, fallback_emoji: str) -> str:
    """يبني وسم HTML لإيموجي بريميوم جاهز للإرسال بـ parse_mode=HTML."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback_emoji}</tg-emoji>'

# ═══════════════════════════════════════════════════════════════
#  أمر ق — مجموعات فقط، المالك فقط
#
#  الحالات:
#  A) ألبوم (media_group):
#     - نجمع كل الرسائل في buffer، ننتظر 1.2 ث، ثم:
#       * نرسل كل وسائط الألبوم واحدة واحدة بـ copy_message
#         (يدعم reply_parameters + تعديل كابشن أول رسالة)
#       * نحذف الأصليات
#
#  B) وسيط منفرد بكابشن يبدأ بـ "ق":
#     copy_message مع caption معدَّل + entities مُصحَّحة
#
#  B2) وسيط منفرد بدون كابشن (صورة/فيديو مجردة) رداً بـ "ق":
#     copy_message للوسيط كما هو
#
#  C) نص "ق نص":
#     send_message بـ entities مُصحَّحة
#
#  D) "ق" وحدها رداً على رسالة:
#     copy_message للرسالة المردود عليها
#
#  E) "ق" وحدها بدون رد: تجاهل
# ═══════════════════════════════════════════════════════════════

# buffer: group_id → {"msgs": [...], "rp": rp_obj}
_album_buffer: dict = {}

def _strip_q_prefix(text: str, entities):
    """
    يحذف بادئة "ق " أو "ق" من النص ويُصحح الـ entities.
    يعيد (new_text, new_entities).
    """
    prefix = get_q_prefix(text)
    if prefix is None:
        return text, entities

    # نحذف أيضاً المسافات الزائدة بعد البادئة
    raw_after = text[len(prefix):]
    stripped_after = raw_after.lstrip() if raw_after else raw_after
    extra     = len(raw_after) - len(stripped_after)
    full_pfx  = prefix + raw_after[:extra]
    return shift_entities(full_pfx, text, entities)


async def _flush_album(ctx, chat_id: int, group_id: str, rp_obj):
    """
    يُرسل ألبوم الوسائط المجمَّع بشكل احترافي:
    - يستخدم copy_message لكل رسالة حتى يدعم reply_parameters
    - يُعدِّل الكابشن على أول رسالة إن احتاج
    - يحذف الأصليات بعد النجاح
    """
    import asyncio

    entry = _album_buffer.pop(group_id, None)
    if not entry:
        return

    msgs: list = entry["msgs"]
    rp         = entry["rp"]

    if not msgs:
        return

    # رتّب الرسائل حسب message_id لضمان الترتيب الصحيح
    msgs.sort(key=lambda m: m.message_id)
    first = msgs[0]

    # احسب الكابشن المعدَّل للرسالة الأولى
    new_cap, new_ents = None, None
    if first.caption is not None:
        nc, ne = _strip_q_prefix(first.caption, first.caption_entities)
        new_cap  = nc.strip() or None
        new_ents = ne if new_cap else None

    sent_ok = True
    for i, m in enumerate(msgs):
        try:
            if i == 0:
                # أول رسالة: تحمل الكابشن المعدَّل + reply
                kwargs = dict(
                    chat_id=chat_id,
                    from_chat_id=chat_id,
                    message_id=m.message_id,
                )
                if rp:
                    kwargs["reply_parameters"] = rp
                if first.caption is not None:
                    kwargs["caption"]          = new_cap
                    kwargs["caption_entities"] = new_ents if new_cap else None
                await ctx.bot.copy_message(**kwargs)
            else:
                # بقية الرسائل: بدون كابشن، بدون reply
                await ctx.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=chat_id,
                    message_id=m.message_id,
                )
        except TelegramError as e:
            logger.error(f"ق-ألبوم رسالة {m.message_id}: {e}")
            sent_ok = False

    if sent_ok:
        for m in msgs:
            try:
                await m.delete()
            except TelegramError:
                pass


async def cmd_q(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    import asyncio

    msg  = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ("group", "supergroup") or user.id != OWNER_ID:
        return

    replied  = msg.reply_to_message
    reply_id = replied.message_id if replied else None
    rp_obj   = make_rp(reply_id) if reply_id else None

    has_media = bool(
        msg.photo or msg.video or msg.document or msg.animation
        or msg.audio or msg.voice or msg.video_note or msg.sticker
    )

    # ══ A: ألبوم (media_group) ════════════════════════════════════
    if msg.media_group_id:
        group_id = msg.media_group_id

        # تحقق: إن كان في كابشن يجب أن يبدأ بـ "ق"، وإلا نتجاهل
        if msg.caption is not None and get_q_prefix(msg.caption) is None:
            return

        if group_id not in _album_buffer:
            _album_buffer[group_id] = {"msgs": [], "rp": rp_obj}
            # جدوِّل الإرسال بعد 1.2 ث لضمان وصول كل رسائل الألبوم
            loop = asyncio.get_running_loop()
            loop.call_later(
                1.2,
                lambda gid=group_id, cid=chat.id, rp=rp_obj: asyncio.ensure_future(
                    _flush_album(ctx, cid, gid, rp)
                ),
            )

        _album_buffer[group_id]["msgs"].append(msg)
        return

    # ══ B: وسيط منفرد بكابشن يبدأ بـ "ق" ════════════════════════
    if has_media and msg.caption is not None:
        prefix = get_q_prefix(msg.caption)
        if prefix is None:
            return

        new_cap, new_ents = _strip_q_prefix(msg.caption, msg.caption_entities)
        new_cap  = new_cap.strip() or None
        new_ents = new_ents if new_cap else None

        try:
            if not new_cap:
                # كابشن "ق" فقط → أرسل الوسيط بدون كابشن نهائياً
                kw = dict(chat_id=chat.id, reply_parameters=rp_obj)
                if msg.photo:
                    await ctx.bot.send_photo(photo=msg.photo[-1].file_id, **kw)
                elif msg.video:
                    await ctx.bot.send_video(video=msg.video.file_id, **kw)
                elif msg.document:
                    await ctx.bot.send_document(document=msg.document.file_id, **kw)
                elif msg.animation:
                    await ctx.bot.send_animation(animation=msg.animation.file_id, **kw)
                elif msg.audio:
                    await ctx.bot.send_audio(audio=msg.audio.file_id, **kw)
                elif msg.voice:
                    await ctx.bot.send_voice(voice=msg.voice.file_id, **kw)
                elif msg.video_note:
                    await ctx.bot.send_video_note(video_note=msg.video_note.file_id, **kw)
                elif msg.sticker:
                    await ctx.bot.send_sticker(sticker=msg.sticker.file_id, **kw)
            else:
                # كابشن "ق نص" → copy_message مع الكابشن المعدَّل
                await ctx.bot.copy_message(
                    chat_id=chat.id,
                    from_chat_id=chat.id,
                    message_id=msg.message_id,
                    caption=new_cap,
                    caption_entities=new_ents,
                    reply_parameters=rp_obj,
                )
        except TelegramError as e:
            logger.error(f"ق-وسيط: {e}")
            return

        try: await msg.delete()
        except TelegramError: pass
        return

    # ══ B2: وسيط منفرد بدون كابشن رداً بـ "ق" ════════════════════
    if has_media and msg.caption is None:
        # يُتجاهل إلا إذا جاء رداً على رسالة أخرى
        # في هذه الحالة "ق" تعني: أعد إرسال هذا الوسيط
        if not replied:
            return
        try:
            await ctx.bot.copy_message(
                chat_id=chat.id,
                from_chat_id=chat.id,
                message_id=msg.message_id,
                reply_parameters=rp_obj,
            )
        except TelegramError as e:
            logger.error(f"ق-وسيط-بدون-كابشن: {e}")
            return
        try: await msg.delete()
        except TelegramError: pass
        return

    # ══ C / D / E: رسالة نصية ════════════════════════════════════
    if msg.text is None:
        return

    prefix = get_q_prefix(msg.text)
    if prefix is None:
        return

    new_text, new_ents = _strip_q_prefix(msg.text, msg.entities)

    # ══ D: "ق" وحدها رداً على رسالة ══════════════════════════════
    if not new_text.strip() and replied:
        try:
            await ctx.bot.copy_message(
                chat_id=chat.id,
                from_chat_id=chat.id,
                message_id=replied.message_id,
            )
        except TelegramError as e:
            logger.error(f"ق-إعادة: {e}")
            return
        try: await msg.delete()
        except TelegramError: pass
        return

    # ══ C: "ق نص" ══════════════════════════════════════════════
    if new_text.strip():
        # احذف أي أسطر فارغة في البداية وصحّح الـ entities
        leading_nl = len(new_text) - len(new_text.lstrip("\n"))
        if leading_nl:
            new_text, new_ents = shift_entities(new_text[:leading_nl], new_text, new_ents)
        try:
            await ctx.bot.send_message(
                chat_id=chat.id,
                text=new_text,
                entities=new_ents or None,
                reply_parameters=rp_obj,
                link_preview_options=NO_PREVIEW,
            )
        except TelegramError as e:
            logger.error(f"ق-نص: {e}")
            return
        try: await msg.delete()
        except TelegramError: pass
        return

    # ══ E: "ق" وحدها بدون رد → تجاهل ════════════════════════════


async def handle_owner_pinned_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    يلتقط تثبيت المالك الطبيعي من إعدادات الرسالة في محادثة البوت.
    لا يحتاج المالك إلى زر أو وضع خاص؛ نفس الرسالة تُنسخ وتُثبت عند الجميع.
    """
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat:
        return

    # Telegram ينشئ رسالة خدمة منفصلة عند تثبيت النسخة عند العضو، نصها
    # عادةً: «ثبّت البوت رسالة ...». نسجل رقمها أيضًا حتى يشملها الحذف.
    if chat.id != OWNER_ID:
        if getattr(msg, "pinned_message", None):
            record_message(chat.id, "user", msg.message_id, "pin_service")
        return

    pinned = getattr(msg, "pinned_message", None)
    if not pinned or not pinned.message_id:
        return
    try:
        pinned_count, failed, total = await _broadcast_and_pin_message(
            ctx, int(pinned.message_id)
        )
        await ctx.bot.send_message(
            OWNER_ID,
            "📌 <b>تمت مزامنة التثبيت تلقائياً</b>\n\n"
            f"المستخدمون المستهدفون: {total}\n"
            f"تم التثبيت عند: {pinned_count}\n"
            f"تعذر الإرسال أو التثبيت عند: {failed}\n\n"
            "يمكن حذف هذه النسخ من الزر التالي.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                _mk_btn(
                    "🗑 حذف الرسالة عند المستخدمين",
                    style="danger",
                    callback_data="global_delete",
                ),
            ]]),
        )
    except TelegramError as e:
        logger.error(f"فشل مزامنة التثبيت الطبيعي: {e}")


# ═══════════════════════════════════════════════════════════════
#  الرياكشن — handler موحّد للاتجاهين
# ═══════════════════════════════════════════════════════════════

async def handle_reaction(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    r = update.message_reaction
    if not r: return
    actor_id = r.user.id if r.user else None
    msg_id   = r.message_id
    chat_id  = r.chat.id

    # المالك → forward في شاته → يُعكَس على رسالة المستخدم
    if actor_id == OWNER_ID and chat_id == OWNER_ID and msg_id in msg_map:
        user_id, user_msg_id = msg_map[msg_id]
        if not user_msg_id: return
        new_r = r.new_reaction
        emoji = getattr(new_r[0], "emoji", "⚡") if new_r else "⚡"
        try:
            await ctx.bot.set_message_reaction(
                chat_id=user_id, message_id=user_msg_id,
                reaction=[ReactionTypeEmoji(emoji)],
            )
        except TelegramError as e: logger.error(f"reaction owner→user: {e}")
        return

    # المستخدم → رد المالك → يُعكَس على شات المالك
    if actor_id and actor_id != OWNER_ID and msg_id in reply_map:
        owner_reply_id, uid = reply_map[msg_id]
        if uid != actor_id: return
        new_r = r.new_reaction
        try:
            if new_r:
                emoji = getattr(new_r[0], "emoji", None)
                if emoji:
                    await ctx.bot.set_message_reaction(
                        chat_id=OWNER_ID, message_id=owner_reply_id,
                        reaction=[ReactionTypeEmoji(emoji)],
                    )
            else:
                await ctx.bot.set_message_reaction(
                    chat_id=OWNER_ID, message_id=owner_reply_id, reaction=[],
                )
        except TelegramError as e: logger.error(f"reaction user→owner: {e}")

# ═══════════════════════════════════════════════════════════════
#  إشعارات المجموعات
# ═══════════════════════════════════════════════════════════════

async def handle_chat_member_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cm = update.chat_member
    if not cm: return
    chat = cm.chat; old = cm.old_chat_member; new = cm.new_chat_member; user = new.user
    if user.is_bot: return
    old_s = old.status; new_s = new.status
    title = chat.title or "المجموعة"
    link  = f'<a href="https://t.me/{chat.username}">{title}</a>' if chat.username else title
    note  = None

    if new_s == "kicked" and old_s != "kicked":
        note = f"😭 | تم حظرك في مجموعة {link} للأسف"
    elif old_s == "kicked" and new_s in ("member", "left", "restricted"):
        note = f"❤️ | تم فك حظرك في مجموعة {link}"
    elif new_s == "left" and old_s == "member":
        if cm.from_user and cm.from_user.id != user.id:
            here = f'<a href="https://t.me/{chat.username}">هنا</a>' if chat.username else "المجموعة"
            note = f"💔 | لقد تم طردك من مجموعة {title} يمكنك العودة من {here}"
    elif new_s == "restricted" and old_s not in ("restricted", "kicked"):
        note = f"🔇 | تم كتمك في مجموعة {link}"
    elif old_s == "restricted" and new_s == "member":
        note = f"🔊 | تم فك كتمك في مجموعة {link}"

    if note:
        try: await ctx.bot.send_message(user.id, note, parse_mode=ParseMode.HTML)
        except TelegramError as e: logger.error(f"chat_member notify: {e}")

# ═══════════════════════════════════════════════════════════════
#  حماية من المجموعات الغريبة
# ═══════════════════════════════════════════════════════════════

async def handle_my_chat_member(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    mc = update.my_chat_member
    if not mc: return

    # ══ المستخدم حظر/فك حظر البوت في الخاص ══════════════════════
    if mc.chat.type == "private":
        old_s = mc.old_chat_member.status
        new_s = mc.new_chat_member.status
        # ملحوظة: new_chat_member.user هنا بيمثّل "البوت نفسه" مش المستخدم
        # (لأن my_chat_member بيتتبع حالة عضوية البوت). بيانات المستخدم
        # الحقيقي موجودة في mc.chat لأن الشات الخاص = المستخدم اللي بيكلم البوت.
        chat = mc.chat
        if chat.id == OWNER_ID:
            return
        if new_s == "kicked" and old_s != "kicked":
            try:
                await ctx.bot.send_message(
                    OWNER_ID,
                    f"🚫 المستخدم {chat_mention(chat)} (<code>{chat.id}</code>) قام بحظر البوت.",
                    parse_mode=ParseMode.HTML,
                )
            except TelegramError as e:
                logger.error(f"notify block: {e}")
        elif old_s == "kicked" and new_s == "member":
            try:
                await ctx.bot.send_message(
                    OWNER_ID,
                    f"✅ المستخدم {chat_mention(chat)} (<code>{chat.id}</code>) فكّ حظر البوت وبدأ استخدامه مجدداً.",
                    parse_mode=ParseMode.HTML,
                )
            except TelegramError as e:
                logger.error(f"notify unblock: {e}")
        return

    if mc.new_chat_member.status not in ("member", "administrator"): return
    if mc.chat.type not in ("group", "supergroup"): return
    owner_present = False
    try:
        member = await ctx.bot.get_chat_member(mc.chat.id, OWNER_ID)
        owner_present = member.status not in ("left", "kicked")
    except TelegramError:
        owner_present = False
    if not owner_present:
        try: await ctx.bot.send_message(mc.chat.id, "اعتذر، هذا البوت خاص، وداعاً 👋")
        except TelegramError: pass
        try: await ctx.bot.leave_chat(mc.chat.id)
        except TelegramError: pass

# ═══════════════════════════════════════════════════════════════
#  بناء التطبيق
# ═══════════════════════════════════════════════════════════════

async def on_startup(app: Application):
    """
    بما أن التوكن مُستخدَم من قبل في بوت سابق، ممكن يكون فيه Webhook قديم لسه
    متسجّل عند تيليجرام، وده بيمنع getUpdates (polling) من استقبال أي تحديثات
    زي /start بصمت من غير أي خطأ ظاهر. نمسحه هنا مع أي تحديثات معلّقة قديمة.
    """
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ تم مسح أي Webhook قديم وتحديثات معلّقة من التوكن.")
    except TelegramError as e:
        logger.error(f"فشل مسح الـ Webhook القديم: {e}")

    # إعادة جدولة التأجيلات بعد أي إعادة تشغيل أو نشر جديد.
    now = time.time()
    for uid_s, state in load_user_state().items():
        try:
            uid = int(uid_s)
            until = float(state.get("snoozed_until", 0))
        except (TypeError, ValueError):
            continue
        if until > now:
            _schedule_snooze(app.job_queue, uid, until)
        elif until:
            update_user_state(uid, snoozed_until=0)

    # إعادة جدولة انتهاء الحظر المؤقت بعد أي إعادة تشغيل أو نشر جديد.
    for uid_s, record in _purge_expired_bans().items():
        try:
            uid = int(uid_s)
            expires_at = record.get("expires_at")
            if expires_at:
                _schedule_ban_expiry(app.job_queue, uid, float(expires_at))
        except (TypeError, ValueError):
            continue

    # إشعار المالك أن البوت اشتغل — بيتبعت تلقائياً كل مرة يعمل فيها deploy
    try:
        await app.bot.send_message(OWNER_ID, "✅ البوت يعمل الآن 🚀")
    except TelegramError as e:
        logger.error(f"فشل إرسال رسالة بدء التشغيل للمالك: {e}")

async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    logger.error(f"حدث خطأ غير متوقع: {ctx.error}", exc_info=ctx.error)
    # نبلّغ المالك مباشرة بأي خطأ بدل ما يختفي بصمت في لوجات Railway فقط
    # (هي دي المشكلة اللي كانت بتخلي /start يفشل من غير أي إشعار)
    try:
        err_text = f"{ctx.error}"[:500]
        await ctx.bot.send_message(
            OWNER_ID,
            f"⚠️ حصل خطأ أثناء معالجة تحديث:\n<code>{err_text}</code>",
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        pass

def build_app():
    defaults = Defaults(link_preview_options=NO_PREVIEW)
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .defaults(defaults)
        .post_init(on_startup)
        .build()
    )
    app.add_error_handler(on_error)

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_handler)],
        states={
            AWAIT_WELCOME_TEXT:  [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER_ID), recv_welcome_text)],
            AWAIT_BUTTONS_TEXT:  [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER_ID), recv_buttons_text)],
            AWAIT_BROADCAST_MSG: [MessageHandler(~filters.COMMAND & filters.User(OWNER_ID), recv_broadcast_msg)],
            AWAIT_AWAY_TEXT:     [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER_ID), recv_away_text)],
            AWAIT_AUTO_KEYWORD_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER_ID), recv_auto_keyword_add)],
            AWAIT_QUICK_REPLY_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER_ID), recv_quick_reply_text)],
            AWAIT_AI_INSTRUCTIONS:  [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER_ID), recv_ai_instructions)],
            AWAIT_AI_KEY:           [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER_ID), recv_ai_key)],
            AWAIT_AI_MODEL:         [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER_ID), recv_ai_model)],
            AWAIT_BAN_REASON:       [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(OWNER_ID), recv_ban_reason)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True, per_user=True, per_message=False,
    )

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("ban",       cmd_ban))
    app.add_handler(CommandHandler("unban",     cmd_unban))
    app.add_handler(CommandHandler("info",      cmd_info))
    app.add_handler(CommandHandler("clear",     cmd_clear))
    app.add_handler(CommandHandler("forward",   cmd_forward))
    app.add_handler(CommandHandler("emoji_id",  cmd_emoji_id))
    app.add_handler(CommandHandler("backup",    cmd_backup))
    app.add_handler(CommandHandler("restore",   cmd_restore))
    # حالة: المالك يبعت ملف الـ JSON مع كتابة /restore في الكابشن (نفس الرسالة)
    app.add_handler(MessageHandler(
        filters.Document.ALL & filters.CaptionRegex(r"^/restore") & filters.User(OWNER_ID),
        cmd_restore,
    ))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.User(OWNER_ID), cmd_q))
    # تثبيت المالك من إعدادات الرسالة العادية → مزامنة تلقائية عند الجميع.
    app.add_handler(MessageHandler(
        filters.StatusUpdate.PINNED_MESSAGE,
        handle_owner_pinned_message,
    ))
    # "بدء التشغيل" في الخاص من المالك → يفتح لوحة التحكم (مسجّل قبل الهاندلر العام)
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.User(OWNER_ID) & filters.Regex(r"^\s*بدء التشغيل\s*$"),
        owner_panel_by_text,
    ))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, handle_private_message))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.UpdateType.EDITED_MESSAGE, handle_private_message))
    app.add_handler(MessageReactionHandler(handle_reaction))
    app.add_handler(ChatMemberHandler(handle_chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(handle_my_chat_member,     ChatMemberHandler.MY_CHAT_MEMBER))

    return app

# ═══════════════════════════════════════════════════════════════
#  نقطة الدخول
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = build_app()
    logger.info("🤖 البوت يعمل — python-telegram-bot v22.8+")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
