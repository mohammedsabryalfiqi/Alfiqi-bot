"""
اختبارات واجهة اللوحة: كل الشاشات تُبنى بنجاح، والأزرار داخل حدود تيليجرام،
وكل callback_data له فرع معالجة، وكل حالة محادثة مسجّلة.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fakes import mod, check_true, summary, reset_state  # noqa: E402

reset_state()

MAX_BUTTON_TEXT = 64
MAX_CALLBACK_DATA = 64
MAX_MESSAGE_TEXT = 4096

source = Path(mod.__file__).read_text(encoding="utf-8")

# كل القيم/البوادئ اللي callback_handler بيعالجها
handled_exact = set(re.findall(r'data == "([^"]+)"', source))
handled_prefix = set(re.findall(r'data\.startswith\("([^"]+)"\)', source))
handled_split = set(re.findall(r'data\.split\(":"\)\[0\] == "([^"]+)"', source))


def is_handled(callback_data: str) -> bool:
    if callback_data in handled_exact or callback_data in handled_split:
        return True
    return any(callback_data.startswith(prefix) for prefix in handled_prefix)


collected: set[str] = set()


def scan_keyboard(markup, screen: str):
    """يمسح كيبورد شاشة ويتأكد من الحدود ويسجّل كل callback_data."""
    if markup is None:
        return
    for row in markup.inline_keyboard:
        for button in row:
            collected.add(button.callback_data or "")
            check_true(f"[{screen}] نص الزر ≤{MAX_BUTTON_TEXT}: {button.text[:20]}",
                       len(button.text or "") <= MAX_BUTTON_TEXT, str(len(button.text or "")))
            if button.callback_data:
                check_true(f"[{screen}] callback_data ≤{MAX_CALLBACK_DATA}: {button.callback_data}",
                           len(button.callback_data) <= MAX_CALLBACK_DATA,
                           str(len(button.callback_data)))


def scan(screen: str, text, markup):
    check_true(f"[{screen}] نص الشاشة ≤{MAX_MESSAGE_TEXT}",
               len(text or "") <= MAX_MESSAGE_TEXT, str(len(text or "")))
    check_true(f"[{screen}] فيه محتوى", bool((text or "").strip()))
    scan_keyboard(markup, screen)


# ══ شاشات اللوحة الأساسية ══
s = mod.load_settings()
# كيبورد فيه صفوف متعددة وأشكال وألوان وإيموجي بريميوم
mod.save_button_rows([
    [{"text": "قناتي {5386419798677874707}", "url": "https://t.me/x", "style": "primary"},
     {"text": "الدعم", "url": "https://t.me/y", "style": "danger"}],
    [{"text": "الموقع", "url": "https://example.com", "style": "success"}],
    [{"text": "زر افتراضي", "url": "https://t.me/z", "style": "default"},
     {"text": "زر تاني", "url": "https://t.me/w", "style": "primary"},
     {"text": "زر تالت", "url": "https://t.me/v", "style": "success"}],
])
s = mod.load_settings()
s["welcome_media"] = {"enabled": True, "kind": "sticker",
                      "file_id": "CAACAgIAAxk", "caption": "<b>أهلاً</b> 👋"}
s["welcome_preview"] = {"disabled": False, "url": "https://t.me/x",
                        "small": True, "large": False, "above": True}
mod.save_settings(s)

scan("لوحة المالك", "لوحة", mod.owner_panel_keyboard())
scan("محرر الكيبورد", *mod.keyboard_editor_view(0))
scan("تعديل زر", *mod.button_editor_view(0, 0))
scan("ألوان الزر", *mod.button_style_view(0, 0))
scan("إيموجي الزر", *mod.button_emoji_view(0, 0))
scan("نقل الزر", *mod.button_move_view(0, 0))
scan("مبادلة زر", *mod.button_swap_pick_view(0, 0))
scan("رسالة البدء", *mod.start_message_menu_view())
scan("معاينة الروابط", *mod.preview_menu_view())
scan("زر البدء الجانبي", *mod.menu_button_view())
scan("إيموجي الاستلام", *mod.receipt_emoji_menu_view())
scan("الأوامر العربية", *mod.arabic_cmd_menu_view())
scan("الإنذارات", *mod.warn_menu_view())
scan("كيبورد رسالة البدء", "رسالة", mod.welcome_keyboard())

# ══ شاشات الدفعة 3: الذكاء الاصطناعي، سجل الرسائل، بطاقة العضو ══
scan("الذكاء الاصطناعي", *mod.ai_reply_menu_view())
scan("الذكاء الاصطناعي — متقدم", *mod.ai_advanced_menu_view())

_msgs_uid = 777000111
for _n in range(20):
    mod.record_message(_msgs_uid, "user", 40000 + _n, "incoming", preview=f"معاينة رسالة {_n}")
    mod.record_message(_msgs_uid, "owner", 41000 + _n, "forward", preview=f"معاينة رسالة {_n}")
mod.record_message(_msgs_uid, "user", 42000, "action_card")          # نوع بدون نص
mod.record_message(_msgs_uid, "user", 42001, "welcome")              # رسالة قديمة بدون معاينة
for _page in range(0, 4):
    scan(f"سجل رسائل العضو ص{_page}", *mod.user_messages_view(_msgs_uid, _page))
scan("سجل رسائل عضو فاضي", *mod.user_messages_view(999888777, 0))
scan("بطاقة العضو الكاملة",
     *mod._build_user_details_view(_msgs_uid, {"full_name": "اسم العضو", "username": "member"}))
scan("كيبورد إجراءات العضو", "إجراءات", mod._user_action_keyboard(_msgs_uid))
scan("كيبورد إجراءات من رسالة", "إجراءات", mod._user_action_keyboard(_msgs_uid, 42))

# صفحات المحرر كلها
mod.save_button_rows([[{"text": f"زر{i}", "url": "https://t.me/x", "style": "success"}
                       for i in range(2)] for _ in range(12)])
for page in range(0, 4):
    scan(f"محرر صفحة {page}", *mod.keyboard_editor_view(page))

# ══ كل callback_data له فرع معالجة ══
missing = sorted({c for c in collected if c and not is_handled(c)})
check_true("كل callback_data له فرع في callback_handler", not missing, str(missing))

# ══ كل حالات المحادثة مسجّلة في build_app ══
app = mod.build_app()
registered_states = set()
for handler in app.handlers.get(0, []):
    if type(handler).__name__ == "ConversationHandler":
        registered_states |= set(handler.states.keys())
for state_name in ("AWAIT_BUTTON_TEXT", "AWAIT_BUTTON_URL", "AWAIT_BUTTON_EMOJI",
                   "AWAIT_NEW_BUTTON", "AWAIT_WELCOME_MEDIA", "AWAIT_WELCOME_CAPTION",
                   "AWAIT_PREVIEW_URL", "AWAIT_WARN_TEXT", "AWAIT_RECEIPT_EMOJI",
                   "AWAIT_AI_SETTING"):
    value = getattr(mod, state_name)
    check_true(f"الحالة {state_name} مسجّلة", value in registered_states,
               f"{value} not in {sorted(registered_states)}")

# ══ ترحيل الشكل القديم للأزرار (قائمة مسطّحة → صفوف) ══
flat = [
    {"text": "أ", "url": "https://t.me/a", "style": "success"},
    {"text": "ب", "url": "https://t.me/b", "style": "danger"},
    {"text": "ج", "url": "https://t.me/c", "style": "primary"},
]
rows = mod.normalize_button_rows(flat)
check_true("ترحيل القائمة المسطّحة لصفوف (زرّين في الصف)",
           rows == [[flat[0], flat[1]], [flat[2]]], str(rows))
check_true("الشكل الجديد زي ما هو",
           mod.normalize_button_rows([rows[0], rows[1]]) == [rows[0], rows[1]])
check_true("قايمة فاضية", mod.normalize_button_rows([]) == [])
check_true("زر بدون ستايل صالح", mod.normalize_button_rows([{"text": "x", "url": "u"}])[0][0]["style"] == "success")

sys.exit(summary("واجهة اللوحة"))
