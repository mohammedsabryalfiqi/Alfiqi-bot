"""
اختبارات الانحدار (Regression) للميزات الأساسية + ربطها بمحرك التنسيق الجديد:
🎯 إيموجي الاستلام · 🪞 عكس التفاعلات · 🇸🇦 الأوامر العربية · ⚠️ الإنذارات
· الأوامر الإنجليزية الموازية · بطاقة الإنذار ورد المالك بـ &
"""
import asyncio
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _fakes  # noqa: E402
from _fakes import (mod, check, check_true, summary, reset_state, FakeMessage,  # noqa: E402
                    FakeCtx, FakeUser, FakeBot, make_update, OWNER)

from telegram import ReactionTypeEmoji  # noqa: E402
from telegram.constants import ParseMode  # noqa: E402

USER = 555000222


def fresh_bot(fail_html=False):
    bot = FakeBot(fail_html=fail_html)
    _fakes.use_bot(bot)
    return bot


def register_forwarded(user_msg: FakeMessage, fwd: FakeMessage):
    """يسجّل الرسالة المحوّلة عند المالك → (آيدي العضو، آيدي رسالته)."""
    mod.msg_map[fwd.message_id] = (user_msg.chat_id, user_msg.message_id)


async def main():
    # ══ 1) 🎯 إيموجي الاستلام ══
    reset_state()
    bot = fresh_bot()
    ctx = FakeCtx(bot)
    check_true("67 إيموجي استلام رسمي", len(mod.RECEIPT_EMOJIS) == 67, str(len(mod.RECEIPT_EMOJIS)))
    check_true("الإيموجي الافتراضي صالح", mod.DEFAULT_RECEIPT_EMOJI in mod.RECEIPT_EMOJIS)
    used = await mod.apply_receipt_emoji(ctx, USER, 9001)
    check("الإيموجي الافتراضي بيتحط", used, mod.DEFAULT_RECEIPT_EMOJI)
    check_true("التفاعل اتبعت لتيليجرام",
               bot.reactions and bot.reactions[-1]["message_id"] == 9001, str(bot.reactions))
    check_true("بدون حركة كبيرة افتراضياً", bot.reactions[-1]["is_big"] is False)

    s = mod.load_settings(); s["receipt_emoji_big"] = True; s["receipt_emoji"] = "❤"
    mod.save_settings(s)
    bot.reactions.clear()
    await mod.apply_receipt_emoji(ctx, USER, 9002)
    check_true("الحركة الكبيرة مفعّلة", bot.reactions[-1]["is_big"] is True)

    s = mod.load_settings(); s["receipt_emoji_enabled"] = False; mod.save_settings(s)
    bot.reactions.clear()
    used = await mod.apply_receipt_emoji(ctx, USER, 9003)
    check_true("التعطيل يمنع التفاعل", used is None and not bot.reactions, str(bot.reactions))

    s = mod.load_settings(); s.update({"receipt_emoji_enabled": True, "receipt_emoji": "random"})
    mod.save_settings(s)
    bot.reactions.clear()
    picked = {await mod.apply_receipt_emoji(ctx, USER, 9100 + i) for i in range(12)}
    check_true("الوضع العشوائي بيختار من المجموعة",
               picked and all(p in mod.RECEIPT_EMOJIS for p in picked if p), str(picked))
    check_true("العشوائي بيغيّر الإيموجي", len([p for p in picked if p]) > 1, str(picked))

    check("إيموجي غير مدعوم مرفوض", mod.normalize_receipt_emoji("🎯"), None)
    check_true("إيموجي صالح مقبول", mod.normalize_receipt_emoji("👍") in mod.RECEIPT_EMOJIS)
    check("كلمة random مقبولة", mod.normalize_receipt_emoji("random"), mod.RECEIPT_EMOJI_RANDOM)
    # وقت الاستخدام الفعلي: أي قيمة غير صالحة ترجع للإيموجي الاحتياطي
    check_true("الإيموجي الاحتياطي صالح", mod.FALLBACK_RECEIPT_EMOJI in mod.RECEIPT_EMOJIS)
    check("الاستخدام الفعلي بيرجع للاحتياطي",
          mod.resolve_receipt_emoji({"receipt_emoji": "🎯"}), mod.FALLBACK_RECEIPT_EMOJI)

    # ══ 2) 🪞 عكس التفاعلات ══
    reset_state()
    bot = fresh_bot()
    ctx = FakeCtx(bot)
    user_msg = FakeMessage(text="رسالة العضو", chat_id=USER, user=FakeUser(USER))
    fwd = FakeMessage(text="رسالة العضو", chat_id=OWNER)
    register_forwarded(user_msg, fwd)
    ok = await mod._mirror_emoji_reply_to_user(ctx, fwd, USER, user_msg.message_id, ["👍", "❤"])
    check_true("رد المالك بإيموجي بقى تفاعل عند العضو", ok is True)
    check_true("التفاعل اتبعت على رسالة العضو",
               bot.reactions and bot.reactions[-1]["chat_id"] == USER
               and bot.reactions[-1]["message_id"] == user_msg.message_id, str(bot.reactions))
    bot.reactions.clear()
    ok = await mod._mirror_emoji_reply_to_user(ctx, fwd, USER, None, ["👍"])
    check_true("بدون آيدي رسالة العضو ما يحصلش تفاعل", ok is False and not bot.reactions)

    # handle_reaction: المالك تفاعل على الرسالة المحوّلة → ينعكس عند العضو
    reset_state()
    bot = fresh_bot()
    ctx = FakeCtx(bot)
    user_msg = FakeMessage(text="أهلاً", chat_id=USER, user=FakeUser(USER))
    fwd = FakeMessage(text="أهلاً", chat_id=OWNER)
    register_forwarded(user_msg, fwd)
    reaction_update = types.SimpleNamespace(
        message_reaction=types.SimpleNamespace(
            user=FakeUser(OWNER, name="المالك"),
            chat=types.SimpleNamespace(id=OWNER, type="private"),
            message_id=fwd.message_id,
            old_reaction=[],
            new_reaction=[ReactionTypeEmoji("🔥")],
        ),
        effective_user=FakeUser(OWNER), effective_chat=None, effective_message=None,
        message=None, edited_message=None, callback_query=None,
    )
    await mod.handle_reaction(reaction_update, ctx)
    check_true("تفاعل المالك انعكس عند العضو",
               bot.reactions and bot.reactions[-1]["chat_id"] == USER, str(bot.reactions))
    # إزالة التفاعل → تُمسح عند العضو
    bot.reactions.clear()
    reaction_update.message_reaction.new_reaction = []
    await mod.handle_reaction(reaction_update, ctx)
    check_true("إزالة التفاعل بتُمسح عند العضو",
               bot.reactions and not bot.reactions[-1]["reaction"], str(bot.reactions))
    # المفتاح مطفي → لا عكس
    mod.save_settings({**mod.load_settings(), "reactions_mirror_enabled": False})
    bot.reactions.clear()
    reaction_update.message_reaction.new_reaction = [ReactionTypeEmoji("👍")]
    await mod.handle_reaction(reaction_update, ctx)
    check_true("تعطيل العكس من اللوحة محترم", not bot.reactions, str(bot.reactions))

    # ══ 3) 🇸🇦 الأوامر العربية ══
    for word, action in (("حظر", "ban"), ("فك حظر", "unban"), ("إنذار", "warn"),
                         ("انذار", "warn"), ("إلغاء الانذار", "unwarn"),
                         ("تثبيت", "pin"), ("تثبيت عام", "global_pin"),
                         ("إلغاء التثبيت", "unpin"), ("كتم 6 ساعات", "mute"),
                         ("الغاء الكتم", "unmute"), ("معلومات", "info"),
                         ("تأجيل 3 ساعات", "snooze"), ("حذف", "clear"),
                         ("صامت", "silent")):
        matched = mod.match_arabic_command(word)
        check_true(f"الكلمة «{word}» → {action}", bool(matched) and matched[0] == action,
                   str(matched))
    matched = mod.match_arabic_command("لوحة التحكم", allow_global=True)
    check_true("الأوامر العامة بتشتغل بدون رد", bool(matched) and matched[0] == "panel", str(matched))
    check_true("الأوامر العامة ممنوعة مع الرد",
               mod.match_arabic_command("لوحة التحكم", allow_global=False) is None)
    matched = mod.match_arabic_command("حظر 123456789 سبب الحظر")
    check_true("صيغة الآيدي بعد الكلمة", bool(matched) and matched[0] == "ban"
               and "123456789" in matched[1], str(matched))
    check_true("كلمة عادية مش أمر", mod.match_arabic_command("أهلاً يا صديقي") is None)
    check_true("الأمر الإنجليزي مش أمر عربي", mod.match_arabic_command("/ban") is None)
    check_true("البادئة & تمنع الأمر", mod.match_arabic_command("&حظر") is None)
    check_true("التشكيل والهمزات متسامح معها",
               bool(mod.match_arabic_command("إلغاء الإنذار")) and
               bool(mod.match_arabic_command("انذار")))

    # التنفيذ الفعلي: إنذار → ثم حظر دائم تلقائي
    reset_state()
    bot = fresh_bot()
    ctx = FakeCtx(bot)
    user_msg = FakeMessage(text="رسالة", chat_id=USER, user=FakeUser(USER, name="حمادة"))
    fwd = FakeMessage(text="رسالة", chat_id=OWNER)
    register_forwarded(user_msg, fwd)
    owner_word = FakeMessage(text="إنذار", chat_id=OWNER, reply_to=fwd)
    await mod.handle_arabic_command(make_update(owner_word), ctx, owner_word)
    check("الإنذار الأول اتسجل", mod.get_warn_count(USER), 1)
    check_true("رسالة الإنذار وصلت للعضو",
               any(m["chat_id"] == USER and "إنذار" in (m["text"] or "") for m in bot.log),
               str([m["text"][:40] for m in bot.log if m["chat_id"] == USER]))
    check_true("المالك اتبلغ بالإنذار",
               any(m["chat_id"] == OWNER and "تم توجيه إنذار" in (m["text"] or "") for m in bot.log),
               str([m["text"][:30] for m in bot.log if m["chat_id"] == OWNER]))
    check_true("العضو لسه مش محظور", USER not in mod.load_banned())

    fwd2 = FakeMessage(text="رسالة تانية", chat_id=OWNER)
    register_forwarded(FakeMessage(text="رسالة تانية", chat_id=USER), fwd2)
    owner_word2 = FakeMessage(text="إنذار مخالفة تانية", chat_id=OWNER, reply_to=fwd2)
    await mod.handle_arabic_command(make_update(owner_word2), ctx, owner_word2)
    check("الإنذار التاني = الحد الأقصى", mod.get_warn_count(USER), 2)
    check_true("الحظر الدائم التلقائي اشتغل", USER in mod.load_banned(), str(mod.load_banned()))
    check_true("سبب الحظر فيه استيفاء العدد",
               "استيفاء عدد الإنذارات" in str(mod.load_ban_records().get(str(USER), {})),
               str(mod.load_ban_records().get(str(USER))))
    check_true("العضو اتبلغ بالحظر",
               any(m["chat_id"] == USER and "حظر" in (m["text"] or "") for m in bot.log),
               str([m["text"][:40] for m in bot.log if m["chat_id"] == USER]))

    # فك الحظر يصفّر الإنذارات
    await mod._apply_unban(ctx, USER)
    check_true("فك الحظر صفّر الإنذارات", mod.get_warn_count(USER) == 0)
    check_true("العضو بقى غير محظور", USER not in mod.load_banned())

    # إيقاف نظام الإنذارات من اللوحة
    mod.save_settings({**mod.load_settings(), "warn_enabled": False})
    on, warn_max, auto = mod.warn_settings()
    check_true("التعطيل محترم", on is False, str((on, warn_max, auto)))
    mod.save_settings({**mod.load_settings(), "warn_enabled": True})

    # ══ 4) الأوامر الإنجليزية الموازية ══
    for name in ("warn", "unwarn", "mute", "unmute", "snooze", "pin", "unpin"):
        check_true(f"الأمر /{name} موجود في PARALLEL_COMMANDS", name in mod.PARALLEL_COMMANDS)
        check_true(f"الأمر /{name} له شرح", name in mod.PARALLEL_COMMAND_HELP)
    app = mod.build_app()
    registered = set()
    for h in app.handlers.get(0, []):
        if type(h).__name__ == "CommandHandler" and getattr(h, "commands", None):
            registered |= set(h.commands)
    for name in mod.PARALLEL_COMMANDS:
        check_true(f"الأمر /{name} مسجّل في build_app", name in registered, str(sorted(registered)))

    reset_state()
    bot = fresh_bot()
    ctx = FakeCtx(bot)
    user_msg = FakeMessage(text="نص", chat_id=USER, user=FakeUser(USER, name="حمادة"))
    fwd = FakeMessage(text="نص", chat_id=OWNER)
    register_forwarded(user_msg, fwd)
    owner_word = FakeMessage(text="/warn", chat_id=OWNER, reply_to=fwd)
    ctx.args = []
    await mod._make_parallel_command("warn")(make_update(owner_word), ctx)
    check("/warn بيعمل إنذار", mod.get_warn_count(USER), 1)
    ctx.args = []
    owner_unwarn = FakeMessage(text="/unwarn", chat_id=OWNER, reply_to=fwd)
    await mod._make_parallel_command("unwarn")(make_update(owner_unwarn), ctx)
    check("/unwarn بيلغي الإنذار", mod.get_warn_count(USER), 0)

    # ══ 5) بطاقة الإنذار مع محرك التنسيق ══
    reset_state()
    bot = fresh_bot()
    ctx = FakeCtx(bot)
    s = mod.load_settings()
    s["warn_message"] = "⚠️ **إنذار** يا {name}\nالسبب: {reason}\nالعدد: {count}/{max}"
    mod.save_settings(s)
    await mod._apply_warn(ctx, USER, reason="مخالفة")
    warn_msgs = [m for m in bot.log if m["chat_id"] == USER and m["type"] == "send_message"]
    check_true("رسالة الإنذار اتبعتت", bool(warn_msgs), str([m["type"] for m in bot.log]))
    if warn_msgs:
        text = warn_msgs[0]["text"]
        check_true("Markdown في القالب اتحوّل HTML", "<b>إنذار</b>" in text, text)
        check_true("المتغيّرات اتعوضت", "1/2" in text and "مخالفة" in text, text)

    # قالب HTML مكسور → الرسالة توصل برضه (حماية من الأخطاء)
    reset_state()
    bot = fresh_bot(fail_html=True)      # تيليجرام بيرفض أي HTML
    ctx = FakeCtx(bot)
    s = mod.load_settings()
    s["warn_message"] = "⚠️ <b>إنذار مفتوح {name} {reason}"
    mod.save_settings(s)
    await mod._apply_warn(ctx, USER, reason="سبب")
    warn_msgs = [m for m in bot.log if m["chat_id"] == USER]
    check_true("لو تيليجرام رفض التنسيق الرسالة بتوصل عادي", bool(warn_msgs),
               str([m["type"] for m in bot.log]))
    if warn_msgs:
        check_true("النسخة الاحتياطية نص عادي", warn_msgs[-1]["kw"].get("parse_mode") is None,
                   str(warn_msgs[-1]["kw"]))

    # ══ 6) رد المالك بـ & مع محرك التنسيق ══
    reset_state()
    bot = fresh_bot()
    ctx = FakeCtx(bot)
    user_msg = FakeMessage(text="سؤال", chat_id=USER, user=FakeUser(USER))
    fwd = FakeMessage(text="سؤال", chat_id=OWNER)
    register_forwarded(user_msg, fwd)
    owner_reply = FakeMessage(text="&**أهلاً** يا صديقي ||مخفي||", chat_id=OWNER, reply_to=fwd)
    await mod.handle_owner_reply(make_update(owner_reply), ctx)
    to_user = [m for m in bot.log if m["chat_id"] == USER and m["type"] == "send_message"]
    check_true("الرد بـ & وصل للمستخدم", bool(to_user), str([m["type"] for m in bot.log]))
    if to_user:
        check_true("تنسيق الـ Markdown اتحوّل", "<b>أهلاً</b>" in to_user[-1]["text"], to_user[-1]["text"])
        check_true("السبويلر اتحوّل", "<tg-spoiler>مخفي</tg-spoiler>" in to_user[-1]["text"],
                   to_user[-1]["text"])
        check_true("علامة & ما وصلتش", not to_user[-1]["text"].startswith("&"))
    check_true("الرد اتسجل في reply_map",
               bool(mod.reply_map) and any(v[1] == USER for v in mod.reply_map.values()),
               str(mod.reply_map))

    # ══ 7) رد عادي من المالك بيتنسخ كما هو (entities + ميديا) ══
    reset_state()
    bot = fresh_bot()
    ctx = FakeCtx(bot)
    user_msg = FakeMessage(text="سؤال", chat_id=USER, user=FakeUser(USER))
    fwd = FakeMessage(text="سؤال", chat_id=OWNER)
    register_forwarded(user_msg, fwd)
    owner_reply = FakeMessage(text="رد عادي <b>بدون</b> تحويل", chat_id=OWNER, reply_to=fwd)
    await mod.handle_owner_reply(make_update(owner_reply), ctx)
    copies = [m for m in bot.log if m["chat_id"] == USER and m["type"] == "copy_message"]
    check_true("الرد العادي بيتنسخ بـ copy_message (التنسيق الأصلي زي ما هو)",
               bool(copies), str([m["type"] for m in bot.log]))


asyncio.run(main())
sys.exit(summary("الميزات الأساسية"))
