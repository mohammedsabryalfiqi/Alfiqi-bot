"""اختبارات 🔄 محرك تنسيق النصوص (كشف تلقائي / تحويل / تصحيح / تقسيم)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fakes import mod, check, check_true, summary, use_bot  # noqa: E402

from telegram import MessageEntity, InlineKeyboardMarkup, InlineKeyboardButton  # noqa: E402
from telegram.constants import ParseMode  # noqa: E402
from telegram.error import BadRequest  # noqa: E402

# ══ 1) الكشف التلقائي ══
check("كشف HTML", mod.detect_text_format("<b>نص</b>"), "html")
check("كشف HTML (blockquote)", mod.detect_text_format("نص <blockquote>اقتباس</blockquote>"), "html")
check("كشف Markdown (**)", mod.detect_text_format("**عريض**"), "markdown")
check("كشف Markdown (__)", mod.detect_text_format("__تحت__"), "markdown")
check("كشف Markdown (||)", mod.detect_text_format("||مخفي||"), "markdown")
check("كشف Markdown (`)", mod.detect_text_format("`كود`"), "markdown")
check("كشف Markdown (~)", mod.detect_text_format("~شطب~"), "markdown")
check("كشف Markdown (رابط)", mod.detect_text_format("[اضغط](https://t.me/x)"), "markdown")
check("نص عادي", mod.detect_text_format("أهلاً بك في البوت"), "plain")
check("نص فيه < و > عادي", mod.detect_text_format("3 < 4 و 5 > 2"), "plain")
check("يوزر فيه شرطة سفلية مش Markdown", mod.detect_text_format("t.me/hamo_alfiqi"), "plain")
check("نجمة واحدة مش Markdown", mod.detect_text_format("قائمة * مهمة"), "plain")

# ══ 2) Markdown → HTML ══
check("عريض", mod.markdown_to_html("**عريض**"), "<b>عريض</b>")
check("مائل *", mod.markdown_to_html("*مائل*"), "<i>مائل</i>")
check("مائل _", mod.markdown_to_html("_مائل_"), "<i>مائل</i>")
check("تحته خط", mod.markdown_to_html("__تحت__"), "<u>تحت</u>")
check("شطب ~", mod.markdown_to_html("~شطب~"), "<s>شطب</s>")
check("شطب ~~", mod.markdown_to_html("~~شطب~~"), "<s>شطب</s>")
check("مخفي", mod.markdown_to_html("||مخفي||"), "<tg-spoiler>مخفي</tg-spoiler>")
check("كود", mod.markdown_to_html("`كود`"), "<code>كود</code>")
check("رابط", mod.markdown_to_html("[اضغط](https://t.me/x)"), '<a href="https://t.me/x">اضغط</a>')
check("كود بلغة", mod.markdown_to_html("```python\nprint(1)\n```"),
      '<pre><code class="language-python">print(1)</code></pre>')
check("كود محمي من التحويل", mod.markdown_to_html("`**مش عريض**`"), "<code>**مش عريض**</code>")
check("تهريب HTML داخل Markdown", mod.markdown_to_html("**a** <script>x</script>"),
      "<b>a</b> &lt;script&gt;x&lt;/script&gt;")
check("تنسيق مختلط", mod.markdown_to_html("**عريض** و`كود` و||مخفي||"),
      "<b>عريض</b> و<code>كود</code> و<tg-spoiler>مخفي</tg-spoiler>")
check("سطور متعددة", mod.markdown_to_html("**أول**\nثاني"), "<b>أول</b>\nثاني")

# ══ 3) تنظيف HTML ══
check("إغلاق الوسم المفتوح", mod.sanitize_telegram_html("<b>نص"), "<b>نص</b>")
check("إغلاق وسم إقفال زائد", mod.sanitize_telegram_html("نص</b>"), "نص")
check("وسم غير مدعوم يتهرب", mod.sanitize_telegram_html("<script>alert(1)</script>"),
      "&lt;script&gt;alert(1)&lt;/script&gt;")
check("تصحيح التداخل", mod.sanitize_telegram_html("<b><i>نص</b></i>"), "<b><i>نص</i></b>")
check("رابط صحيح", mod.sanitize_telegram_html('<a href="https://t.me/x">نص</a>'),
      '<a href="https://t.me/x">نص</a>')
check("رابط بدون href", mod.sanitize_telegram_html("<a>نص</a>"), "نص")
check("span spoiler قديم", mod.sanitize_telegram_html('<span class="tg-spoiler">نص</span>'),
      "<tg-spoiler>نص</tg-spoiler>")
check("strong → b", mod.sanitize_telegram_html("<strong>نص</strong>"), "<b>نص</b>")
check("em → i", mod.sanitize_telegram_html("<em>نص</em>"), "<i>نص</i>")
check("del → s", mod.sanitize_telegram_html("<del>نص</del>"), "<s>نص</s>")
check("كيان & موجود", mod.sanitize_telegram_html("a &amp; b"), "a &amp; b")
check("أمبرساند عادي يتهرب", mod.sanitize_telegram_html("a & b"), "a &amp; b")
check("إيموجي بريميوم محفوظ", mod.sanitize_telegram_html('<tg-emoji emoji-id="5386419798677874707">🔥</tg-emoji>'),
      '<tg-emoji emoji-id="5386419798677874707">🔥</tg-emoji>')
check("blockquote محفوظ", mod.sanitize_telegram_html("<blockquote>اقتباس</blockquote>"),
      "<blockquote>اقتباس</blockquote>")
check("pre + code محفوظ", mod.sanitize_telegram_html('<pre><code class="language-py">x=1</code></pre>'),
      '<pre><code class="language-py">x=1</code></pre>')
check("وسم مغلق ذاتياً يتجاهل", mod.sanitize_telegram_html("نص<br/>نص"), "نص&lt;br/&gt;نص")

# ══ 4) تنسيق تيليجرام الأصلي (entities) ══
def ent(type_, offset, length, **kw):
    return MessageEntity(type=type_, offset=offset, length=length, **kw)

check("entities عريض", mod.entities_to_html("hello world", [ent("bold", 0, 5)]),
      "<b>hello</b> world")
check("entities رابط", mod.entities_to_html("اضغط هنا",
      [ent("text_link", 0, 8, url="https://t.me/x")]),
      '<a href="https://t.me/x">اضغط هنا</a>')
check("entities كود بلغة", mod.entities_to_html("print(1)", [ent("pre", 0, 8, language="python")]),
      '<pre><code class="language-python">print(1)</code></pre>')
check("entities إيموجي بريميوم",
      mod.entities_to_html("🔥 نص", [ent("custom_emoji", 0, 2, custom_emoji_id="5386419798677874707")]),
      '<tg-emoji emoji-id="5386419798677874707">🔥</tg-emoji> نص')
check("entities متجاورة", mod.entities_to_html("عريض مائل",
      [ent("bold", 0, 4), ent("italic", 5, 4)]), "<b>عريض</b> <i>مائل</i>")
check("entities متداخلة", mod.entities_to_html("نص",
      [ent("bold", 0, 2), ent("italic", 0, 2)]), "<b><i>نص</i></b>")
check("entities بدون تنسيق", mod.entities_to_html("نص < عادي", []), "نص &lt; عادي")

# offsets بـ UTF-16 مع إيموجي
text_emoji = "😀😀 عريض"          # كل إيموجي = وحدتين UTF-16
offset = mod.utf16_len("😀😀 ")     # = 5
check("entities مع إيموجي (UTF-16)",
      mod.entities_to_html(text_emoji, [ent("bold", offset, mod.utf16_len("عريض"))]),
      "😀😀 <b>عريض</b>")

# ══ 5) normalize ══
t, pm, ents = mod.normalize_formatted_text("**نص**")
check("normalize markdown", (t, pm, ents), ("<b>نص</b>", ParseMode.HTML, None))
t, pm, ents = mod.normalize_formatted_text("<b>نص")
check("normalize html مكسور", (t, pm, ents), ("<b>نص</b>", ParseMode.HTML, None))
t, pm, ents = mod.normalize_formatted_text("نص عادي")
check("normalize نص عادي", (t, pm, ents), ("نص عادي", None, None))
t, pm, ents = mod.normalize_formatted_text("نص {5386419798677874707}")
check("normalize بريميوم في نص عادي", t,
      'نص <tg-emoji emoji-id="5386419798677874707">🔥</tg-emoji>')
check_true("normalize بريميوم → HTML", pm == ParseMode.HTML)
t, pm, ents = mod.normalize_formatted_text("hello", [ent("bold", 0, 5)])
check("normalize entities", (t, pm, ents), ("<b>hello</b>", ParseMode.HTML, None))
t, pm, ents = mod.normalize_formatted_text("<b>نص</b> و** markdown")
check_true("HTML بياخد الأولوية", t.startswith("<b>نص</b>"), t)

# ══ 6) تقسيم الرسائل الطويلة ══
long_text = ("<b>" + ("كلمة " * 2000) + "</b>")
parts = mod.split_formatted_text(long_text, ParseMode.HTML)
check_true("الرسالة الطويلة اتقسمت", len(parts) > 1, str(len(parts)))
check_true("كل جزء داخل الحد", all(len(p) <= 4096 for p in parts),
           str(max(len(p) for p in parts)))
check_true("كل جزء وسومه مقفولة", all(mod.sanitize_telegram_html(p) == p for p in parts),
           str([p[:40] for p in parts if mod.sanitize_telegram_html(p) != p][:1]))
check_true("كل جزء يبدأ بـ <b>", all(p.startswith("<b>") for p in parts))
check_true("كل جزء ينتهي بـ </b>", all(p.endswith("</b>") for p in parts))
check("النص القصير مايتقسمش", mod.split_formatted_text("<b>قصير</b>", ParseMode.HTML),
      ["<b>قصير</b>"])
plain_long = "كلمة " * 2000
parts = mod.split_formatted_text(plain_long, None)
check_true("نص عادي طويل في جزء واحد (لا حد)", len(parts) == 1)

# تقسيم مع سطور
lines_text = "\n".join(f"<b>سطر {i}</b>" for i in range(600))
parts = mod.split_formatted_text(lines_text, ParseMode.HTML)
check_true("التقسيم عند حدود الأسطر", all(p.startswith("<b>سطر") for p in parts),
           str([p[:20] for p in parts][:3]))

# تقسيم entities
ent_text = "كلمة " * 2000
entities = [ent("bold", 0, mod.utf16_len("كلمة")), ent("italic", mod.utf16_len("كلمة "), mod.utf16_len("كلمة"))]
parts = mod.split_entities_message(ent_text, entities)
check_true("تقسيم entities لأجزاء", len(parts) > 1, str(len(parts)))
first_text, first_ents = parts[0]
check_true("الكيانات في الجزء الأول صحيحة",
           first_ents and first_ents[0].offset == 0 and first_ents[0].length == mod.utf16_len("كلمة"),
           str(first_ents))
check_true("كل جزء entities ضمن طوله",
           all(all(e.offset + e.length <= mod.utf16_len(t) for e in (es or []))
               for t, es in parts))

# ══ 7) send_formatted مع بوت وهمي ══
class RecBot:
    """بوت وهمي يسجل الاستدعاءات ويرفض HTML لو مطلوب."""

    def __init__(self, fail_html=False):
        self.calls = []
        self.fail_html = fail_html

    async def send_message(self, chat_id, text, **kw):
        if kw.get("parse_mode") and self.fail_html:
            raise BadRequest("Can't parse entities: unexpected end tag")
        self.calls.append({"chat_id": chat_id, "text": text, **kw})
        return type("M", (), {"message_id": len(self.calls), "chat_id": chat_id})()


async def send_tests():
    bot = RecBot()
    await mod.send_formatted(bot, 42, "**عريض** ونص عادي")
    check_true("send_formatted حوّل Markdown",
               bot.calls[0]["text"] == "<b>عريض</b> ونص عادي"
               and bot.calls[0]["parse_mode"] == ParseMode.HTML, str(bot.calls[0]))

    bot = RecBot()
    await mod.send_formatted(bot, 42, "نص عادي بدون تنسيق")
    check_true("نص عادي بدون parse_mode", bot.calls[0].get("parse_mode") is None, str(bot.calls[0]))

    bot = RecBot()
    long_md = "**" + ("كلمة " * 2000) + "**"
    sent = await mod.send_formatted(bot, 42, long_md,
                                    reply_markup=InlineKeyboardMarkup(
                                        [[InlineKeyboardButton("زر", url="https://t.me/x")]]))
    check_true("رسالة طويلة اتقسمت لأكتر من جزء", len(bot.calls) > 1, str(len(bot.calls)))
    check_true("الكيبورد على آخر جزء فقط",
               bot.calls[-1].get("reply_markup") is not None
               and all("reply_markup" not in c for c in bot.calls[:-1]),
               str([bool(c.get("reply_markup")) for c in bot.calls]))
    check_true("كل الأجزاء HTML صالح",
               all(mod.sanitize_telegram_html(c["text"]) == c["text"] for c in bot.calls))

    bot = RecBot(fail_html=True)
    sent = await mod.send_formatted(bot, 42, "<b>مكسور")
    check_true("عند رفض تيليجرام يُرسل نص عادي",
               len(bot.calls) == 1 and bot.calls[0].get("parse_mode") is None
               and "مكسور" in bot.calls[0]["text"], str(bot.calls))

    bot = RecBot()
    await mod.send_formatted(bot, 42, "hello", entities=[ent("bold", 0, 5)])
    check_true("مسار entities الأصلي",
               bot.calls[0]["text"] == "<b>hello</b>"
               and bot.calls[0]["parse_mode"] == ParseMode.HTML, str(bot.calls[0]))

    # caption limit
    bot = RecBot()
    await mod.send_formatted(bot, 42, "x" * 3000, limit=mod.TG_CAPTION_LIMIT)
    check_true("حد الكابشن محترم", all(len(c["text"]) <= mod.TG_CAPTION_LIMIT for c in bot.calls),
               str([len(c["text"]) for c in bot.calls]))

    # رسالة فاضية
    bot = RecBot()
    await mod.send_formatted(bot, 42, "")
    check_true("رسالة فاضية ما تكسرش", len(bot.calls) == 1)


asyncio.run(send_tests())

sys.exit(summary("محرك التنسيق"))
