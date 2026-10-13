"""
طبقة محاكاة مشتركة لاختبارات البوت بدون اتصال حقيقي بتيليجرام.

بتعمل import لملف bot-3.py داخل مجلد مؤقت (حتى لا تُكتب ملفات الحالة
في المستودع) وبتوفر بوت/رسائل/سياق وهمي مع دوال تحقق بسيطة.
"""
import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BOT_PATH = REPO_ROOT / "bot-3.py"

os.environ.setdefault("BOT_TOKEN", "123456:TEST")
os.environ.setdefault("OWNER_ID", "111111")

WORKDIR = Path(tempfile.mkdtemp(prefix="alfiqi-bot-tests-"))
os.chdir(WORKDIR)

_spec = importlib.util.spec_from_file_location("botmod", str(BOT_PATH))
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

OWNER = mod.OWNER_ID

FAILURES: list[str] = []
PASSED = [0]


def check(name, got, expected):
    ok = got == expected
    PASSED[0] += 1 if ok else 0
    print(("✅ " if ok else "❌ ") + name + ("" if ok else f"\n     got={got!r}\n     exp={expected!r}"))
    if not ok:
        FAILURES.append(name)


def check_true(name, condition, extra=""):
    ok = bool(condition)
    PASSED[0] += 1 if ok else 0
    print(("✅ " if ok else "❌ ") + name + (f" — {extra}" if not ok and extra else ""))
    if not ok:
        FAILURES.append(name)


def summary(suite: str) -> int:
    print()
    if FAILURES:
        print(f"❌ {suite}: {len(FAILURES)} فشل من {PASSED[0] + len(FAILURES)} فحص")
        for item in FAILURES:
            print("   -", item)
        return 1
    print(f"🎉 {suite}: {PASSED[0]} فحص نجح")
    return 0


# ══════════════════════════════════════════════════════════════
#  الطبقة الوهمية
# ══════════════════════════════════════════════════════════════

class FakeUser:
    def __init__(self, uid, name="عضو", username=None, is_bot=False):
        self.id = uid
        self.full_name = name
        self.first_name = name
        self.last_name = None
        self.username = username
        self.is_bot = is_bot


class FakeChat(FakeUser):
    type = "private"
    bio = "بايو"
    photo = None


_id = [10000]


def next_id():
    _id[0] += 1
    return _id[0]


class FakeMessage:
    def __init__(self, text=None, chat_id=OWNER, message_id=None, user=None,
                 reply_to=None, caption=None, entities=None):
        self.text = text
        self.caption = caption
        self.chat_id = chat_id
        self.chat = FakeChat(chat_id)
        self.message_id = message_id or next_id()
        self.from_user = user or FakeUser(chat_id)
        self.reply_to_message = reply_to
        self.entities = entities or []
        self.caption_entities = []
        for attr in ("photo", "video", "document", "animation", "audio", "voice",
                     "video_note", "sticker", "pinned_message", "media_group_id"):
            setattr(self, attr, None)
        self.outgoing_replies = []

    async def reply_text(self, text, **kw):
        sent = FakeMessage(text=text, chat_id=self.chat_id)
        self.outgoing_replies.append(sent)
        BOT.log.append({"type": "reply_text", "chat_id": self.chat_id, "text": text,
                        "kw": kw, "id": sent.message_id})
        return sent

    async def delete(self):
        return True


def make_update(msg, edited=False):
    return types.SimpleNamespace(
        effective_message=msg,
        message=None if edited else msg,
        edited_message=msg if edited else None,
        effective_user=msg.from_user,
        effective_chat=msg.chat,
        callback_query=None,
    )


class FakeQuery:
    def __init__(self, data, message):
        self.data = data
        self.message = message
        self.from_user = message.from_user
        self.answers = []
        self.edited = []

    async def answer(self, text=None, show_alert=False, **kw):
        self.answers.append((text, show_alert))

    async def edit_message_text(self, text, **kw):
        self.edited.append(("text", text, kw))

    async def edit_message_caption(self, caption=None, **kw):
        self.edited.append(("caption", caption, kw))

    async def edit_message_reply_markup(self, reply_markup=None, **kw):
        self.edited.append(("markup", reply_markup, kw))

    def make_update(self):
        return types.SimpleNamespace(
            callback_query=self, effective_message=self.message,
            effective_user=self.from_user, effective_chat=self.message.chat,
        )


class FakeBot:
    username = "testbot"

    def __init__(self, fail_html=False):
        self.log = []
        self.reactions = []
        self.pinned = []
        self.fail_html = fail_html
        self.commands = None
        self.owner_commands = None
        self.menu_button = None

    # ── محاكاة فحص تيليجرام لوسوم HTML ──
    @staticmethod
    def validate_html(text):
        import re as _re
        stack = []
        for m in _re.finditer(r"<(/?)([a-zA-Z-]+)([^>]*)>", text or ""):
            closing, tag, rest = m.group(1), m.group(2).lower(), m.group(3)
            if tag in ("br",) or rest.endswith("/"):
                continue
            if closing:
                if not stack or stack[-1] != tag:
                    raise _bad_request("Can't parse entities: unexpected closing tag")
                stack.pop()
            else:
                stack.append(tag)
        if stack:
            raise _bad_request(f"Can't parse entities: unclosed tag {stack[-1]}")

    def _rec(self, kind, chat_id, text=None, **kw):
        if str(kw.get("parse_mode", "")) == "HTML":
            if self.fail_html:
                raise _bad_request("Can't parse entities: unexpected end tag")
            self.validate_html(text)
        if text is not None:
            limit = int(kw.get("_limit", 4096))
            assert len(text) <= limit, f"نص أطول من الحد: {len(text)}"
        msg = FakeMessage(text=text, chat_id=chat_id)
        self.log.append({"type": kind, "chat_id": chat_id, "text": text, "kw": kw,
                         "id": msg.message_id})
        return msg

    async def send_message(self, chat_id, text, **kw):
        return self._rec("send_message", chat_id, text, **kw)

    async def send_photo(self, chat_id, photo=None, caption=None, **kw):
        return self._rec("send_photo", chat_id, caption, **kw)

    async def send_video(self, chat_id, video=None, caption=None, **kw):
        return self._rec("send_video", chat_id, caption, **kw)

    async def send_animation(self, chat_id, animation=None, caption=None, **kw):
        return self._rec("send_animation", chat_id, caption, **kw)

    async def send_sticker(self, chat_id, sticker=None, **kw):
        return self._rec("send_sticker", chat_id, None, **kw)

    async def forward_message(self, chat_id, from_chat_id, message_id, **kw):
        return self._rec("forward_message", chat_id, f"[fwd {message_id}]", **kw)

    async def copy_message(self, chat_id, from_chat_id, message_id, **kw):
        return self._rec("copy_message", chat_id, f"[copy {message_id}]", **kw)

    async def set_message_reaction(self, chat_id, message_id, reaction=None, is_big=False):
        self.reactions.append({"chat_id": chat_id, "message_id": message_id,
                               "reaction": reaction, "is_big": is_big})
        return True

    async def pin_chat_message(self, chat_id, message_id, **kw):
        self.pinned.append(("pin", chat_id, message_id))
        return True

    async def unpin_chat_message(self, chat_id, message_id=None, **kw):
        self.pinned.append(("unpin", chat_id, message_id))
        return True

    async def delete_message(self, chat_id, message_id):
        return True

    async def get_chat(self, uid):
        return FakeChat(int(uid) if str(uid).lstrip("-").isdigit() else 999, name=f"user{uid}")

    async def send_document(self, chat_id, **kw):
        return self._rec("send_document", chat_id, "[doc]")

    async def send_chat_action(self, chat_id, action, **kw):
        self.log.append({"type": "chat_action", "chat_id": chat_id, "action": str(action)})
        return True

    async def set_my_commands(self, commands, scope=None, **kw):
        # نطاق المالك (شات المالك) بيتسجل لوحده عشان نفرّق القائمتين في الاختبار
        if scope is not None:
            self.owner_commands = commands
        else:
            self.commands = commands
        return True

    async def set_chat_menu_button(self, chat_id=None, menu_button=None, **kw):
        self.menu_button = menu_button
        return True


def _bad_request(message):
    from telegram.error import BadRequest
    return BadRequest(message)


BOT = FakeBot()


class FakeCtx:
    def __init__(self, bot=None):
        self.bot = bot if bot is not None else BOT
        self.job_queue = None
        self.user_data = {}
        self.args = []


def use_bot(bot):
    global BOT
    BOT = bot
    return bot


def sent_texts(chat_id, kind=None):
    return [m["text"] for m in BOT.log
            if m["chat_id"] == chat_id and (kind is None or m["type"] == kind)]


def reset_state():
    for path in (mod.SETTINGS_FILE, mod.USER_STATE_FILE, mod.BANNED_FILE, mod.USERS_FILE,
                 mod.MESSAGE_RECORDS_FILE, mod.AUDIT_LOG_FILE, mod.MSG_MAP_FILE,
                 mod.REPLY_MAP_FILE, mod.USER_STATS_FILE):
        try:
            path.unlink()
        except OSError:
            pass
    mod.msg_map.clear()
    mod.reply_map.clear()
    mod.owner_sent_map.clear()
    mod.pending_silent.clear()
    mod._local_pin_ids.clear()
    BOT.log.clear()
    BOT.reactions.clear()
    BOT.pinned.clear()
