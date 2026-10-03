"""
مدير تشغيل البوتات المستضافة — كل بوت يعمل كتطبيق ptb مستقل جوا نفس
الـ event loop، عبر run_polling في مهمة منفصلة.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from telegram.ext import Application
from telegram.error import TelegramError, InvalidToken

from . import storage
from .templates import contact_bot, protection_bot

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  أنواع البوتات المدعومة
# ═══════════════════════════════════════════════════════════

BOT_TYPES: dict[str, dict[str, Any]] = {
    "contact": {
        "name": "📩 بوت تواصل",
        "description": (
            "بوت رسائل خاص: يستقبل رسائل الأعضاء ويوصلها لصاحب البوت، مع لوحة تحكم، "
            "رد تلقائي، ذكاء اصطناعي، حظر/كتم/تأجيل، وبث للجميع."
        ),
        "builder": contact_bot.build,
    },
    "protection": {
        "name": "🛡️ بوت حماية مجموعات",
        "description": (
            "بوت إدارة وحماية للمجموعات: ترحيب/وداع، قواعد، حظر/طرد/كتم/تحذيرات، "
            "مضاد للفلاود/الروابط/الكلمات المحظورة، منع بعض الوسائط، وتسجيل الإجراءات."
        ),
        "builder": protection_bot.build,
    },
}


# ═══════════════════════════════════════════════════════════
#  الحالة الحية للبوتات العاملة
# ═══════════════════════════════════════════════════════════

class RunningBot:
    def __init__(self, app: Application, task: asyncio.Task, bot_id: int):
        self.app = app
        self.task = task
        self.bot_id = bot_id
        self.started_at = time.time()
        self._stopping = False

    async def stop(self):
        if self._stopping:
            return
        self._stopping = True
        try:
            # stop updater + finalize app
            if self.app.updater and self.app.updater.running:
                await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
        except Exception as e:
            logger.warning(f"stop bot {self.bot_id}: {e}")
        if not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass


_running: dict[int, RunningBot] = {}
_lock = asyncio.Lock()


# ═══════════════════════════════════════════════════════════
#  تشغيل/إيقاف
# ═══════════════════════════════════════════════════════════

async def start_bot(host_app: Application, bot_id: int) -> tuple[bool, str]:
    async with _lock:
        record = storage.get_bot(bot_id)
        if not record:
            return False, "البوت غير موجود."
        if bot_id in _running:
            return False, "البوت شغّال بالفعل."

        tpl = BOT_TYPES.get(record["bot_type"])
        if not tpl:
            return False, f"نوع البوت '{record['bot_type']}' غير مدعوم."

        token = record["token"].strip()
        if not token or ":" not in token:
            storage.update_bot(bot_id, status="error", error_msg="توكن غير صالح.")
            return False, "التوكن غير صالح."

        try:
            app: Application = await tpl["builder"](record, host_app)
        except Exception as e:
            logger.exception(f"بناء البوت {bot_id} فشل")
            storage.update_bot(bot_id, status="error", error_msg=f"فشل البناء: {e}")
            return False, f"فشل بناء البوت: {e}"

        # تحقق من صحة التوكن
        try:
            me = await app.bot.get_me()
            storage.update_bot(
                bot_id,
                bot_username=me.username,
                bot_name=me.full_name or me.first_name,
                error_msg=None,
            )
        except InvalidToken:
            storage.update_bot(bot_id, status="error", error_msg="التوكن غير صالح.")
            return False, "التوكن غير صالح (Invalid token)."
        except TelegramError as e:
            storage.update_bot(bot_id, status="error", error_msg=f"فشل التحقق: {e}")
            return False, f"فشل التحقق من التوكن: {e}"

        async def _runner():
            try:
                # run_polling يتولى initialize/start/updater/stop/shutdown
                await app.run_polling(
                    close_loop=False,
                    drop_pending_updates=True,
                    allowed_updates=["message", "edited_message", "callback_query",
                                     "message_reaction", "chat_member", "my_chat_member"],
                    stop_signals=None,  # المنصة الرئيسية هي اللي تتعامل مع signals
                )
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.exception(f"البوت {bot_id} توقف بخطأ")
                storage.update_bot(bot_id, status="error", error_msg=str(e)[:400])
                try:
                    await host_app.bot.send_message(
                        record["owner_id"],
                        f"⚠️ توقف البوت <b>{record.get('bot_name') or record['id']}</b> بخطأ:\n"
                        f"<code>{str(e)[:500]}</code>",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            finally:
                st = storage.get_bot(bot_id)
                if st and st["status"] == "running":
                    storage.update_bot(bot_id, status="stopped")
                _running.pop(bot_id, None)

        # قبل تشغيل المهمة نحدّث الحالة
        storage.update_bot(bot_id, status="running", last_started=int(time.time()),
                           error_msg=None)

        task = asyncio.create_task(_runner(), name=f"hosted-bot-{bot_id}")
        _running[bot_id] = RunningBot(app, task, bot_id)

        # انتظار قليل حتى نرى فشل فوري
        await asyncio.sleep(2)
        if task.done() and not task.cancelled():
            err = task.exception()
            if err:
                storage.update_bot(bot_id, status="error", error_msg=str(err)[:300])
                _running.pop(bot_id, None)
                return False, f"فشل تشغيل البوت: {err}"

        return True, f"تم تشغيل البوت @{me.username}."


async def stop_bot(bot_id: int) -> tuple[bool, str]:
    async with _lock:
        rb = _running.get(bot_id)
        if not rb:
            record = storage.get_bot(bot_id)
            if record and record["status"] == "running":
                storage.update_bot(bot_id, status="stopped")
            return False, "البوت ليس قيد التشغيل."
        await rb.stop()
        storage.update_bot(bot_id, status="stopped")
        _running.pop(bot_id, None)
    return True, "تم إيقاف البوت."


async def restart_bot(host_app: Application, bot_id: int) -> tuple[bool, str]:
    await stop_bot(bot_id)
    await asyncio.sleep(2)
    return await start_bot(host_app, bot_id)


def is_running(bot_id: int) -> bool:
    return bot_id in _running


def running_count() -> int:
    return len(_running)


def running_bot_app(bot_id: int) -> Application | None:
    rb = _running.get(bot_id)
    return rb.app if rb else None


def uptime(bot_id: int) -> float:
    rb = _running.get(bot_id)
    if not rb:
        return 0.0
    return time.time() - rb.started_at


async def stop_all():
    """يُستدعى عند إيقاف البوت الرئيسي."""
    async with _lock:
        bids = list(_running.keys())
    for bid in bids:
        try:
            await stop_bot(bid)
        except Exception:
            pass
