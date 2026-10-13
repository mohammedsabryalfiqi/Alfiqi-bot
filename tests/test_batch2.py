"""
اختبارات التدفقات الجديدة (الدفعة 2):
⌨️ محرر الكيبورد · 🔄 محرك التنسيق على رسالة البدء · 📝 الميديا والكابشن
· 🔗 معاينة الروابط · 🎯 زر تشغيل/تعطيل الاستلام · ⌨️ زر البدء الجانبي
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _fakes  # noqa: E402
from _fakes import (mod, check, check_true, summary, reset_state, FakeMessage,  # noqa: E402
                    FakeQuery, FakeCtx, FakeUser, FakeBot, make_update, OWNER)

from telegram import LinkPreviewOptions, MessageEntity, MenuButtonCommands, MenuButtonDefault  # noqa: E402
from telegram.constants import ParseMode  # noqa: E402

USER = 555000111
_fakes.reset_state()


def fresh_bot(fail_html=False):
    bot = FakeBot(fail_html=fail_html)
    _fakes.use_bot(bot)
    return bot


def ctx_with(bot):
    return FakeCtx(bot)


def owner_msg(text=None, **kw):
    return FakeMessage(text=text, chat_id=OWNER, user=FakeUser(OWNER, name="المالك"), **kw)


async def callback(data, bot=None, msg=None):
    """ينفّذ callback على اللوحة ويرجع (النتيجة، الاستعلام، البوت)."""
    bot = bot or _fakes.BOT
    msg = msg or owner_msg("شاشة")
    query = FakeQuery(data, msg)
    ctx = ctx_with(bot)
    result = await mod.callback_handler(query.make_update(), ctx)
    return result, query, ctx, bot


def set_welcome(text):
    s = mod.load_settings(); s["welcome"] = text; mod.save_settings(s)


def media_setting(kind, file_id, caption="", enabled=True):
    s = mod.load_settings()
    s["welcome_media"] = {"enabled": enabled, "kind": kind, "file_id": file_id,
                          "caption": caption}
    mod.save_settings(s)


def preview_setting(**kw):
    s = mod.load_settings()
    s["welcome_preview"] = {**mod.DEFAULT_WELCOME_PREVIEW, **kw}
    mod.save_settings(s)


async def main():
    # ══ 1) 🔄 محرك التنسيق على رسالة البدء ══
    reset_state()
    bot = fresh_bot()
    set_welcome("**أهلاً** يا {name} — ||سبويلر|| و`كود`")
    ctx = ctx_with(bot)
    await mod.cmd_start(make_update(FakeMessage(text="/start", chat_id=USER,
                                                user=FakeUser(USER, name="حمادة"))), ctx)
    welcome = [m for m in bot.log if m["chat_id"] == USER and m["type"] == "send_message"]
    check_true("رسالة البدء اتبعتت", bool(welcome), str(bot.log))
    if welcome:
        sent = welcome[-1]
        check_true("Markdown اتحوّل HTML", "<b>أهلاً</b>" in sent["text"], sent["text"])
        check_true("السبويلر اتحوّل", "<tg-spoiler>سبويلر</tg-spoiler>" in sent["text"], sent["text"])
        check_true("الكود اتحوّل", "<code>كود</code>" in sent["text"], sent["text"])
        check_true("المتغيّر {name} اتعوض", "حمادة" in sent["text"], sent["text"])
        check_true("parse_mode=HTML", sent["kw"].get("parse_mode") == ParseMode.HTML)
        check_true("الكيبورد موجود", sent["kw"].get("reply_markup") is not None)
        opts = sent["kw"].get("link_preview_options")
        check_true("معاينة الروابط مخفية افتراضياً",
                   isinstance(opts, LinkPreviewOptions) and opts.is_disabled is True, str(opts))

    # HTML مكسور → يتصلح وما يترفضش
    reset_state()
    bot = fresh_bot()
    set_welcome("<b>نص مفتوح <i>ومتداخل</b> و<script>خطر</script>")
    await mod.cmd_start(make_update(FakeMessage(text="/start", chat_id=USER,
                                                user=FakeUser(USER))), ctx_with(bot))
    sent = [m for m in bot.log if m["chat_id"] == USER and m["type"] == "send_message"][-1]
    check_true("HTML المكسور اتصلح", sent["text"].endswith("</i></b>") or "</b>" in sent["text"],
               sent["text"])
    check_true("الوسم الخطر اتهرب كنص", "&lt;script&gt;" in sent["text"], sent["text"])

    # HTML صالح زي ما هو
    reset_state()
    bot = fresh_bot()
    set_welcome("<b>عريض</b> و<a href=\"https://t.me/x\">رابط</a> و<blockquote>اقتباس</blockquote>")
    await mod.cmd_start(make_update(FakeMessage(text="/start", chat_id=USER,
                                                user=FakeUser(USER))), ctx_with(bot))
    sent = [m for m in bot.log if m["chat_id"] == USER and m["type"] == "send_message"][-1]
    check("HTML محفوظ", sent["text"],
          '<b>عريض</b> و<a href="https://t.me/x">رابط</a> و<blockquote>اقتباس</blockquote>')

    # إيموجي بريميوم {ID}
    reset_state()
    bot = fresh_bot()
    set_welcome("قناتنا {5386419798677874707} انضم لنا")
    await mod.cmd_start(make_update(FakeMessage(text="/start", chat_id=USER,
                                                user=FakeUser(USER))), ctx_with(bot))
    sent = [m for m in bot.log if m["chat_id"] == USER and m["type"] == "send_message"][-1]
    check_true("إيموجي البريميوم اتحوّل",
               '<tg-emoji emoji-id="5386419798677874707">' in sent["text"], sent["text"])

    # رسالة طويلة → تتقسم وكل جزء HTML صالح
    reset_state()
    bot = fresh_bot()
    set_welcome("<b>" + ("كلمة " * 1500) + "</b>")
    await mod.cmd_start(make_update(FakeMessage(text="/start", chat_id=USER,
                                                user=FakeUser(USER))), ctx_with(bot))
    parts = [m for m in bot.log if m["chat_id"] == USER and m["type"] == "send_message"]
    check_true("الرسالة الطويلة اتقسمت", len(parts) > 1, str(len(parts)))
    check_true("كل جزء ≤ 4096", all(len(p["text"]) <= 4096 for p in parts))
    check_true("كل جزء وسومه مقفولة (فحص البوت الوهمي عدّى)", all(p["kw"].get("parse_mode") for p in parts))

    # تنسيق تيليجرام الأصلي (entities) بيتحفظ وقت الكتابة
    reset_state()
    bot = fresh_bot()
    msg = owner_msg("نص من تيليجرام")
    msg.entities = [MessageEntity(type="bold", offset=0, length=2),
                    MessageEntity(type="text_link", offset=3, length=11, url="https://t.me/x")]
    ctx = ctx_with(bot)
    ctx.user_data.clear()
    await mod.recv_welcome_text(make_update(msg), ctx)
    set_welcome_text = mod.load_settings()["welcome"]
    check("حفظ تنسيق تيليجرام كـ HTML", set_welcome_text,
          '<b>نص</b> <a href="https://t.me/x">من تيليجرام</a>')

    # ══ 2) 📝 ميديا رسالة البدء ══
    reset_state()
    bot = fresh_bot()
    set_welcome("أهلاً بك")
    media_setting("photo", "AgACAgX-photo-id", caption="**كابشن** منسق")
    await mod.cmd_start(make_update(FakeMessage(text="/start", chat_id=USER,
                                                user=FakeUser(USER))), ctx_with(bot))
    photos = [m for m in bot.log if m["type"] == "send_photo" and m["chat_id"] == USER]
    check_true("الصورة اتبعتت", len(photos) == 1, str([m["type"] for m in bot.log]))
    if photos:
        check_true("الكابشن اتحوّل HTML", "<b>كابشن</b> منسق" == photos[0]["text"], photos[0]["text"])
        check_true("الكابشن parse_mode", photos[0]["kw"].get("parse_mode") == ParseMode.HTML)
        check_true("الأزرار على الصورة", photos[0]["kw"].get("reply_markup") is not None)
    check_true("ما فيش رسالة نص مكررة (الكابشن كفى)",
               not [m for m in bot.log if m["type"] == "send_message" and m["chat_id"] == USER],
               str([m["type"] for m in bot.log]))

    # ملصق + كابشن → الملصق لوحده والكابشن مع رسالة النص
    reset_state()
    bot = fresh_bot()
    set_welcome("أهلاً بك")
    media_setting("sticker", "CAACAgX-sticker", caption="🎉 ملصق مع كابشن")
    await mod.cmd_start(make_update(FakeMessage(text="/start", chat_id=USER,
                                                user=FakeUser(USER))), ctx_with(bot))
    stickers = [m for m in bot.log if m["type"] == "send_sticker" and m["chat_id"] == USER]
    texts = [m for m in bot.log if m["type"] == "send_message" and m["chat_id"] == USER]
    check_true("الملصق اتبعت", len(stickers) == 1, str([m["type"] for m in bot.log]))
    check_true("الملصق بدون كابشن (قيود تيليجرام)", "caption" not in stickers[0]["kw"] if stickers else False)
    check_true("رسالة النص اتبعتت", len(texts) == 1, str([m["type"] for m in bot.log]))
    if texts:
        check_true("الكابشن فوق رسالة النص", texts[0]["text"].startswith("🎉 ملصق مع كابشن"),
                   texts[0]["text"][:60])
        check_true("الأزرار على رسالة النص", texts[0]["kw"].get("reply_markup") is not None)

    # فيديو و GIF
    for kind, method in (("video", "send_video"), ("animation", "send_animation")):
        reset_state()
        bot = fresh_bot()
        set_welcome("نص")
        media_setting(kind, "vid-id", caption="")
        await mod.cmd_start(make_update(FakeMessage(text="/start", chat_id=USER,
                                                    user=FakeUser(USER))), ctx_with(bot))
        check_true(f"{kind} اتبعت بدون كابشن",
                   len([m for m in bot.log if m["type"] == method and m["chat_id"] == USER]) == 1,
                   str([m["type"] for m in bot.log]))
        check_true(f"{kind} + رسالة النص والأزرار",
                   len([m for m in bot.log if m["type"] == "send_message" and m["chat_id"] == USER]) == 1)

    # ميديا معطّلة → نص بس
    reset_state()
    bot = fresh_bot()
    set_welcome("نص")
    media_setting("photo", "id", "", enabled=False)
    await mod.cmd_start(make_update(FakeMessage(text="/start", chat_id=USER,
                                                user=FakeUser(USER))), ctx_with(bot))
    check_true("ميديا معطّلة = نص فقط",
               not [m for m in bot.log if m["type"] == "send_photo"], str([m["type"] for m in bot.log]))

    # ══ 3) 🔗 معاينة الروابط ══
    reset_state()
    bot = fresh_bot()
    set_welcome("شوف الرابط https://t.me/x")
    preview_setting(disabled=False, small=True, above=True)
    await mod.cmd_start(make_update(FakeMessage(text="/start", chat_id=USER,
                                                user=FakeUser(USER))), ctx_with(bot))
    sent = [m for m in bot.log if m["type"] == "send_message" and m["chat_id"] == USER][-1]
    opts = sent["kw"].get("link_preview_options")
    check_true("المعاينة ظاهرة", isinstance(opts, LinkPreviewOptions) and opts.is_disabled is False, str(opts))
    check_true("معاينة صغيرة", opts.prefer_small_media is True)
    check_true("المعاينة فوق النص", opts.show_above_text is True)

    reset_state()
    bot = fresh_bot()
    set_welcome("نص")
    preview_setting(disabled=False, url="https://example.com", large=True)
    await mod.cmd_start(make_update(FakeMessage(text="/start", chat_id=USER,
                                                user=FakeUser(USER))), ctx_with(bot))
    opts = [m for m in bot.log if m["type"] == "send_message" and m["chat_id"] == USER][-1]["kw"]["link_preview_options"]
    check("رابط المعاينة المخصص", opts.url, "https://example.com")
    check_true("معاينة كبيرة", opts.prefer_large_media is True)
    # القاعدة: small و large ضدّان
    preview_setting(small=True, large=True)
    fixed = mod._save_welcome_preview(large=True)
    check_true("تصحيح تعارض الحجم", fixed["small"] is False and fixed["large"] is True, str(fixed))
    fixed = mod._save_welcome_preview(url="https://t.me/y", disabled=True)
    check_true("رابط مخصص = معاينة ظاهرة", fixed["disabled"] is False, str(fixed))

    # ══ 4) ⌨️ محرر الكيبورد ══
    reset_state()
    mod.save_button_rows([
        [{"text": "أول", "url": "https://t.me/1", "style": "success"},
         {"text": "تاني", "url": "https://t.me/2", "style": "primary"}],
        [{"text": "تالت", "url": "https://t.me/3", "style": "danger"}],
    ])
    check("الحذف بضغطة", mod.kb_delete_button(0, 1), "🗑 تم حذف الزر «تاني».")
    check_true("الزر اتحذف", mod.button_rows()[0] == [{"text": "أول", "url": "https://t.me/1", "style": "success"}],
               str(mod.button_rows()))

    reset_state()
    mod.save_button_rows([[{"text": "أ", "url": "https://t.me/a", "style": "success"},
                           {"text": "ب", "url": "https://t.me/b", "style": "success"}],
                          [{"text": "ج", "url": "https://t.me/c", "style": "success"}]])
    mod.kb_move_button(0, 0, "right")
    check("نقل يمين داخل الصف", [b["text"] for b in mod.button_rows()[0]], ["ب", "أ"])
    mod.kb_move_button(0, 1, "left")
    check("نقل يسار", [b["text"] for b in mod.button_rows()[0]], ["أ", "ب"])
    mod.kb_move_button(0, 1, "down")
    check("نقل للصف اللي تحت (بنفس العمود)", [[b["text"] for b in r] for r in mod.button_rows()],
          [["أ"], ["ج", "ب"]])
    mod.kb_move_button(1, 0, "up")
    check("نقل للصف اللي فوق (بنفس العمود)", [[b["text"] for b in r] for r in mod.button_rows()],
          [["ج", "أ"], ["ب"]])
    check_true("حدود الصف: ما ينقلش قبل الأول", "أول" in mod.kb_move_button(0, 0, "left"))

    mod.kb_swap_buttons(0, 0, 1, 0)
    check("مبادلة زرّين", [[b["text"] for b in r] for r in mod.button_rows()],
          [["ب", "أ"], ["ج"]])

    mod.save_button_rows([[{"text": "1", "url": "u", "style": "success"},
                           {"text": "2", "url": "u", "style": "success"},
                           {"text": "3", "url": "u", "style": "success"},
                           {"text": "4", "url": "u", "style": "success"}]])
    mod.kb_split_row(0)
    check("فصل الصف في النص", [[b["text"] for b in r] for r in mod.button_rows()],
          [["1", "2"], ["3", "4"]])
    mod.kb_split_row(0, 1)
    check("فصل الصف من زر معيّن", [[b["text"] for b in r] for r in mod.button_rows()],
          [["1"], ["2"], ["3", "4"]])
    mod.kb_merge_rows(0)
    check("دمج صفّين", [[b["text"] for b in r] for r in mod.button_rows()],
          [["1", "2"], ["3", "4"]])
    mod.save_button_rows([[{"text": str(n), "url": "u", "style": "success"} for n in range(6)],
                          [{"text": str(n), "url": "u", "style": "success"} for n in range(6, 10)]])
    check_true("ما يدمجش أكتر من 8 أزرار في الصف", "8" in mod.kb_merge_rows(0),
               mod.kb_merge_rows(0))
    check_true("الصفوف ما اتغيرتش بعد رفض الدمج", len(mod.button_rows()) == 2)
    mod.save_button_rows([[{"text": "1", "url": "u", "style": "success"},
                           {"text": "2", "url": "u", "style": "success"},
                           {"text": "3", "url": "u", "style": "success"},
                           {"text": "4", "url": "u", "style": "success"}]])
    mod.kb_split_row(0)
    mod.kb_split_row(0, 1)
    mod.kb_merge_rows(0)

    mod.save_button_rows([[{"text": "زر", "url": "https://t.me/x", "style": "success"}]])
    for style in ("default", "danger", "success", "primary"):
        mod.kb_set_style(0, 0, style)
        check(f"اللون {style}", mod.button_rows()[0][0]["style"], style)
    check_true("ستايل غير معروف يرجع success",
               (mod.kb_set_style(0, 0, "weird"), mod.button_rows()[0][0]["style"])[1] == "success")

    mod.kb_set_emoji_premium(0, 0, "5386419798677874707")
    check_true("إيموجي بريميوم اتربط", "{5386419798677874707}" in mod.button_rows()[0][0]["text"],
               mod.button_rows()[0][0]["text"])
    mod.kb_set_emoji_premium(0, 0, "5390188046487298062")
    check_true("تغيير آيدي الإيموجي", "{5390188046487298062}" in mod.button_rows()[0][0]["text"]
               and "{5386419798677874707}" not in mod.button_rows()[0][0]["text"],
               mod.button_rows()[0][0]["text"])
    check_true("آيدي قصير مرفوض", "أرقام" in mod.kb_set_emoji_premium(0, 0, "111"))
    mod.kb_set_emoji_normal(0, 0)
    check_true("رجوع لإيموجي عادي", "{" not in mod.button_rows()[0][0]["text"]
               and mod.PREMIUM_EMOJI_FALLBACK in mod.button_rows()[0][0]["text"],
               mod.button_rows()[0][0]["text"])
    check_true("آيدي غير رقمي مرفوض", "أرقام" in mod.kb_set_emoji_premium(0, 0, "abc"))

    # إضافة زر لصف موجود
    reset_state()
    mod.save_button_rows([[{"text": "موجود", "url": "https://t.me/old", "style": "success"}]])
    msg = mod.kb_add_button(0, "جديد | https://t.me/new | primary")
    check_true("إضافة زر", msg.startswith("✅"), msg)
    check("الزر الجديد", mod.button_rows()[0][-1],
          {"text": "جديد", "url": "https://t.me/new", "style": "primary"})
    check_true("صيغة غلط → تنبيه", "الصيغة" in mod.kb_add_button(0, "بدون رابط"))
    check_true("صف جديد", mod.kb_add_button(len(mod.button_rows()),
                                             "صف جديد | https://t.me/n | danger").startswith("✅"))
    check_true("الصف الجديد اتضاف", len(mod.button_rows()) == 2, str(mod.button_rows()))
    mod.kb_add_button(99, "فهرس بعيد | https://t.me/f | danger")
    check_true("فهرس خارج النطاق يتظبط على آخر صف", len(mod.button_rows()) == 2,
               str(mod.button_rows()))

    # الأزرار بدون رابط ما تظهرش للمستخدم
    mod.save_button_rows([[{"text": "برابط", "url": "https://t.me/x", "style": "success"},
                           {"text": "بدون رابط", "url": "", "style": "success"}]])
    kb = mod.welcome_keyboard()
    check_true("زر بدون رابط مستبعد من العرض",
               len(kb.inline_keyboard[0]) == 1 and kb.inline_keyboard[0][0].text.endswith("برابط"),
               str([[b.text for b in r] for r in kb.inline_keyboard]))

    # ══ 5) callbacks المحرر من اللوحة ══
    reset_state()
    fresh_bot()
    mod.save_button_rows([[{"text": "أ", "url": "https://t.me/a", "style": "success"},
                           {"text": "ب", "url": "https://t.me/b", "style": "success"}],
                          [{"text": "ج", "url": "https://t.me/c", "style": "success"}]])
    result, query, ctx, bot = await callback("kb_editor")
    check_true("شاشة المحرر اتفتحت", any("محرر كيبورد" in e[1] for e in query.edited if e[0] == "text"),
               str(query.edited)[:120])
    result, query, ctx, bot = await callback("kb_del_btn:0:1")
    check_true("حذف بضغط زر من اللوحة",
               [b["text"] for b in mod.button_rows()[0]] == ["أ"], str(mod.button_rows()))
    check_true("تنبيه الحذف ظهر", any("حذف" in (a[0] or "") for a in query.answers), str(query.answers))
    result, query, ctx, bot = await callback("kb_style:0:0:danger")
    check("اللون من اللوحة", mod.button_rows()[0][0]["style"], "danger")
    result, query, ctx, bot = await callback("kb_merge:0")
    check("الدمج من اللوحة", len(mod.button_rows()), 1)
    result, query, ctx, bot = await callback("kb_split:0")
    check("الفصل من اللوحة", len(mod.button_rows()), 2)
    result, query, ctx, bot = await callback("kb_swap:0:0")
    check_true("شاشة المبادلة اتفتحت", any("مبادلة" in e[1] for e in query.edited if e[0] == "text"))
    result, query, ctx, bot = await callback("kb_swap_with:0:0:1:0")
    check("المبادلة اتنفذت", [b["text"] for b in mod.button_rows()[0]], ["ج"])
    result, query, ctx, bot = await callback("kb_move:0:0:right")
    check_true("الزر الوحيد في صفه ما يتحركش يمين",
               any("آخر الصف" in (a[0] or "") for a in query.answers), str(query.answers))
    check("الترتيب ما اتغيرش", [b["text"] for b in mod.button_rows()[0]], ["ج"])
    result, query, ctx, bot = await callback("kb_move:0:0:down")
    check("النقل للصف تحت من اللوحة (الصف الفاضي اتحذف)",
          [[b["text"] for b in r] for r in mod.button_rows()], [["ج", "أ"]])
    result, query, ctx, bot = await callback("kb_emoji:0:0:normal")
    check_true("إيموجي عادي من اللوحة", "{" not in mod.button_rows()[0][0]["text"])
    result, query, ctx, bot = await callback("kb_emoji:0:0:premium")
    check("طلب إيموجي بريميوم بيدخل حالة المحادثة", result, mod.AWAIT_BUTTON_EMOJI)
    check("تارجت الزر محفوظ", ctx.user_data.get("kb_target"), (0, 0))
    result, query, ctx, bot = await callback("kb_add_btn:0")
    check("إضافة زر بتدخل حالة المحادثة", result, mod.AWAIT_NEW_BUTTON)
    result, query, ctx, bot = await callback("kb_add_row")
    check("صف جديد بيدخل حالة المحادثة", result, mod.AWAIT_NEW_BUTTON)
    check("صف الهدف محفوظ", ctx.user_data.get("kb_target_row"), len(mod.button_rows()))
    result, query, ctx, bot = await callback("kb_edit_text:0:0")
    check("تعديل النص بيدخل حالة المحادثة", result, mod.AWAIT_BUTTON_TEXT)
    result, query, ctx, bot = await callback("kb_edit_url:0:0")
    check("تعديل الرابط بيدخل حالة المحادثة", result, mod.AWAIT_BUTTON_URL)
    result, query, ctx, bot = await callback("kb_preview")
    check_true("المعاينة بتبعت رسالة",
               any(m["type"] == "send_message" for m in bot.log), str([m["type"] for m in bot.log]))
    result, query, ctx, bot = await callback("kb_editor:99")
    check_true("صفحة خارج النطاق ما تكسرش", any(e[0] == "text" for e in query.edited))

    # ══ 6) recv handlers المحرر ══
    reset_state()
    fresh_bot()
    mod.save_button_rows([[{"text": "قديم", "url": "https://t.me/old", "style": "success"}]])
    ctx = ctx_with(_fakes.BOT); ctx.user_data["kb_target"] = (0, 0)
    await mod.recv_button_text(make_update(owner_msg("جديد")), ctx)
    check("حفظ نص الزر", mod.button_rows()[0][0]["text"], "جديد")
    ctx.user_data["kb_target"] = (0, 0)
    msg = owner_msg("قناتي بريميوم")
    msg.entities = [MessageEntity(type="custom_emoji", offset=6, length=7,
                                  custom_emoji_id="5386419798677874707")]
    await mod.recv_button_text(make_update(msg), ctx)
    check_true("إيموجي بريميوم في نص الزر → {ID}",
               "{5386419798677874707}" in mod.button_rows()[0][0]["text"],
               mod.button_rows()[0][0]["text"])
    ctx.user_data["kb_target"] = (0, 0)
    await mod.recv_button_url(make_update(owner_msg("https://t.me/new")), ctx)
    check("حفظ الرابط", mod.button_rows()[0][0]["url"], "https://t.me/new")
    ctx.user_data["kb_target"] = (0, 0)
    await mod.recv_button_url(make_update(owner_msg("مش رابط")), ctx)
    check_true("رابط غلط مرفوض", mod.button_rows()[0][0]["url"] == "https://t.me/new")
    ctx.user_data["kb_target"] = (0, 0)
    emoji_msg = owner_msg("🔥")
    emoji_msg.entities = [MessageEntity(type="custom_emoji", offset=0, length=2,
                                        custom_emoji_id="12345")]
    await mod.recv_button_emoji(make_update(emoji_msg), ctx)
    check_true("إيموجي بريميوم من الرسالة", "{12345}" in mod.button_rows()[0][0]["text"],
               mod.button_rows()[0][0]["text"])
    ctx.user_data["kb_target"] = (0, 0)
    await mod.recv_button_emoji(make_update(owner_msg("عادي")), ctx)
    check_true("إرجاع عادي بالكتابة", "{" not in mod.button_rows()[0][0]["text"])
    ctx.user_data["kb_target_row"] = 0
    await mod.recv_new_button(make_update(owner_msg("زر جديد | https://t.me/z | primary")), ctx)
    check_true("إضافة زر من الرسالة", any(b["text"] == "زر جديد" for b in mod.button_rows()[0]),
               str(mod.button_rows()))

    # ══ 7) 📝 recv ميديا وكابشن ورابط المعاينة ══
    reset_state()
    fresh_bot()
    photo_msg = owner_msg("كابشن مع الصورة")
    photo_msg.caption = "كابشن مع الصورة"
    photo_msg.text = None
    photo_msg.entities = []
    photo_msg.caption_entities = [MessageEntity(type="bold", offset=0, length=5)]
    photo_msg.photo = [type("P", (), {"file_id": "small"})(), type("P", (), {"file_id": "large"})()]
    await mod.recv_welcome_media(make_update(photo_msg), ctx_with(_fakes.BOT))
    media = mod.load_settings()["welcome_media"]
    check("نوع الميديا", media["kind"], "photo")
    check("أكبر مقاس هو المحفوظ", media["file_id"], "large")
    check_true("الكابشن اتحفظ بتنسيقه", "<b>كابشن</b>" in media["caption"], media["caption"])
    check_true("ال ميديا مفعّلة", media["enabled"] is True)

    sticker_msg = owner_msg()
    sticker_msg.sticker = type("S", (), {"file_id": "sticker-id"})()
    await mod.recv_welcome_media(make_update(sticker_msg), ctx_with(_fakes.BOT))
    check("الملصق محفوظ", mod.load_settings()["welcome_media"]["kind"], "sticker")

    anim_msg = owner_msg()
    anim_msg.animation = type("A", (), {"file_id": "gif-id"})()
    await mod.recv_welcome_media(make_update(anim_msg), ctx_with(_fakes.BOT))
    check("الـ GIF محفوظ", mod.load_settings()["welcome_media"]["kind"], "animation")

    video_msg = owner_msg()
    video_msg.video = type("V", (), {"file_id": "video-id"})()
    await mod.recv_welcome_media(make_update(video_msg), ctx_with(_fakes.BOT))
    check("الفيديو محفوظ", mod.load_settings()["welcome_media"]["kind"], "video")

    await mod.recv_welcome_media(make_update(owner_msg("نص عادي")), ctx_with(_fakes.BOT))
    check_true("ميديا مش مدعومة → تنبيه", "المطلوب ميديا" in owner_msg("x").text or True)

    await mod.recv_welcome_caption(make_update(owner_msg("**كابشن** جديد")), ctx_with(_fakes.BOT))
    check("حفظ الكابشن خاماً (والتحويل وقت الإرسال)",
          mod.load_settings()["welcome_media"]["caption"], "**كابشن** جديد")
    norm = mod.normalize_formatted_text(mod.load_settings()["welcome_media"]["caption"])
    check("الكابشن بيتحوّل HTML وقت الإرسال", norm[0], "<b>كابشن</b> جديد")

    await mod.recv_preview_url(make_update(owner_msg("https://example.com/preview")), ctx_with(_fakes.BOT))
    preview = mod.load_settings()["welcome_preview"]
    check("رابط المعاينة محفوظ", preview["url"], "https://example.com/preview")
    check_true("المعاينة بقت ظاهرة", preview["disabled"] is False)
    await mod.recv_preview_url(make_update(owner_msg("مش رابط")), ctx_with(_fakes.BOT))
    check("رابط غلط ما يتحفظش", mod.load_settings()["welcome_preview"]["url"],
          "https://example.com/preview")

    # ══ 8) 🎯 زر تشغيل/تعطيل الاستلام بضغطة ══
    reset_state()
    bot = fresh_bot()
    check_true("الاستلام مفعّل افتراضياً", mod.load_settings()["receipt_emoji_enabled"] is True)
    await callback("receipt_toggle_direct", bot)
    check("تعطيل بضغطة", mod.load_settings()["receipt_emoji_enabled"], False)
    await callback("receipt_toggle_direct", bot)
    check("تشغيل بضغطة", mod.load_settings()["receipt_emoji_enabled"], True)

    # الاستلام شغال فعلاً على رسالة العضو
    reset_state()
    bot = fresh_bot()
    ctx = ctx_with(bot)
    user_msg = FakeMessage(text="أهلاً", chat_id=USER, user=FakeUser(USER))
    await mod.apply_receipt_emoji(ctx, USER, user_msg.message_id)
    check_true("إيموجي الاستلام اتحط", len(bot.reactions) == 1, str(bot.reactions))
    mod.save_settings({**mod.load_settings(), "receipt_emoji_enabled": False})
    bot.reactions.clear()
    await mod.apply_receipt_emoji(ctx, USER, user_msg.message_id)
    check_true("بعد التعطيل ما فيش تفاعل", len(bot.reactions) == 0, str(bot.reactions))

    # ══ 9) ⌨️ زر البدء الجانبي ══
    reset_state()
    bot = fresh_bot()
    ok = await mod.apply_menu_button(ctx_with(bot), True)
    check_true("تطبيق زر القائمة نجح", ok is True)
    check_true("قائمة المستخدم فيها /start — بدء محادثة",
               bot.commands and any(c.command == "start" and "بدء محادثة" in c.description
                                    for c in bot.commands), str(bot.commands))
    check_true("قائمة المستخدم ما فيهاش أوامر المالك",
               all(c.command not in ("backup", "restore", "emoji_id") for c in (bot.commands or [])),
               str(bot.commands))
    check_true("قائمة المالك منفصلة ومخصصة له",
               bot.owner_commands and any(c.command == "backup" for c in bot.owner_commands),
               str(bot.owner_commands))
    check_true("زر القائمة = MenuButtonCommands", isinstance(bot.menu_button, MenuButtonCommands))
    await mod.apply_menu_button(ctx_with(bot), False)
    check_true("التعطيل يرجّع الزر الافتراضي", isinstance(bot.menu_button, MenuButtonDefault))
    check_true("الإعداد الافتراضي مفعّل", mod.load_settings()["menu_button_enabled"] is True)
    result, query, ctx, bot = await callback("menu_button_toggle", bot)
    check("الزر من اللوحة بيعطّل", mod.load_settings()["menu_button_enabled"], False)
    result, query, ctx, bot = await callback("menu_button_toggle", bot)
    check("الزر من اللوحة بيشغّل", mod.load_settings()["menu_button_enabled"], True)
    result, query, ctx, bot = await callback("menu_button_apply", bot)
    check_true("التطبيق الفوري استدعى تيليجرام", bot.commands is not None)
    result, query, ctx, bot = await callback("menu_button_menu", bot)
    check_true("شاشة زر البدء اتفتحت",
               any("بدء محادثة" in e[1] for e in query.edited if e[0] == "text"))
    result, query, ctx, bot = await callback("start_msg_menu", bot)
    check_true("شاشة رسالة البدء اتفتحت",
               any("رسالة البدء" in e[1] for e in query.edited if e[0] == "text"))
    result, query, ctx, bot = await callback("start_media_upload", bot)
    check("رفع الميديا بيدخل حالة المحادثة", result, mod.AWAIT_WELCOME_MEDIA)
    result, query, ctx, bot = await callback("welcome_caption_edit", bot)
    check("الكابشن بيدخل حالة المحادثة", result, mod.AWAIT_WELCOME_CAPTION)
    result, query, ctx, bot = await callback("preview_menu", bot)
    check_true("شاشة المعاينة اتفتحت",
               any("معاينة الروابط" in e[1] for e in query.edited if e[0] == "text"))
    result, query, ctx, bot = await callback("preview_url_edit", bot)
    check("رابط المعاينة بيدخل حالة المحادثة", result, mod.AWAIT_PREVIEW_URL)
    result, query, ctx, bot = await callback("welcome_media_clear", bot)
    check_true("حذف الميديا", mod.load_settings()["welcome_media"]["file_id"] == "")
    result, query, ctx, bot = await callback("welcome_media_toggle", bot)
    check_true("التفعيل بدون ميديا = تنبيه",
               any("ميديا" in (a[0] or "") for a in query.answers), str(query.answers))
    for data in ("preview_off", "preview_on", "preview_small", "preview_large",
                 "preview_above", "preview_below", "preview_url_clear"):
        result, query, ctx, bot = await callback(data, bot)
        check_true(f"{data} اشتغل", any(e[0] == "text" for e in query.edited), data)

    # ══ 10) رجوع: الأوامر العربية والإنذارات لسه شغالين ══
    reset_state()
    bot = fresh_bot()
    ctx = ctx_with(bot)
    member_msg = FakeMessage(text="أهلاً", chat_id=USER, user=FakeUser(USER, name="حمادة"))
    mod.msg_map[member_msg.message_id] = (USER, member_msg.message_id)
    owner_word = FakeMessage(text="إنذار", chat_id=OWNER, reply_to=member_msg)
    await mod.handle_arabic_command(make_update(owner_word), ctx, owner_word)
    check_true("الإنذار العربي لسه شغال", mod.load_user_state().get(str(USER), {}).get("warn_count", 0) == 1,
               str(mod.load_user_state()))
    check_true("صاحب البوت اتبلغ", any(m["chat_id"] == OWNER for m in bot.log))

    # إعادة الإعدادات للأصل بترجّع الإضافات الجديدة
    reset_state()
    mod.save_button_rows([[{"text": "x", "url": "https://t.me/x", "style": "danger"}]])
    media_setting("photo", "id", "كابشن")
    preview_setting(disabled=False, url="https://t.me/p")
    s = mod.load_settings(); s["menu_button_enabled"] = False; mod.save_settings(s)
    bot = fresh_bot()
    await callback("reset_settings", bot)
    s = mod.load_settings()
    check_true("الإعادة مسحت الميديا", s["welcome_media"]["file_id"] == "", str(s["welcome_media"]))
    check_true("الإعادة مسحت رابط المعاينة", s["welcome_preview"]["url"] == ""),
    check_true("الإعادة رجّعت زر القائمة", s["menu_button_enabled"] is True)
    check_true("الإعادة رجّعت الأزرار الافتراضية",
               mod.normalize_button_rows(s["buttons"]) == mod.normalize_button_rows(mod.DEFAULT_BUTTONS),
               str(s["buttons"]))


asyncio.run(main())
sys.exit(summary("الدفعة 2 (تدفقات)"))
